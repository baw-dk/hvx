# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
ReportBuilder: entities in, :class:`PortfolioReport` out.

Rooms are analysed independently (serially, in threads, or in a process
pool) and then aggregated. Input entities are never modified.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial
from typing import Callable, Dict, Iterable, List, Mapping, Optional

from hvx.core.entities import Building, Floor, Portfolio, Room

from .aggregate import group_actions, highlights, summarize, worst_rooms
from .analysis import RoomTask, analyze_room
from .config import ReportConfig
from .model import BuildingReport, FloorReport, PortfolioReport, RoomReport

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]
UNASSIGNED = "__unassigned__"


class ReportBuilder:
    def __init__(self, config: Optional[ReportConfig] = None, progress: Optional[ProgressCallback] = None) -> None:
        self.config = config or ReportConfig()
        self.progress = progress

    # ------------------------------------------------------------------
    def build(
        self,
        portfolio: Portfolio,
        buildings: Mapping[str, Building],
        floors: Mapping[str, Floor],
        rooms: Mapping[str, Room],
        building_ids: Optional[Iterable[str]] = None,
    ) -> PortfolioReport:
        started = time.perf_counter()
        config = self.config
        if building_ids is not None:
            wanted = set(building_ids)
            buildings = {k: v for k, v in buildings.items() if k in wanted}
            rooms = {k: v for k, v in rooms.items() if self._building_id(v, floors) in wanted}

        tasks = [self._task(room, portfolio, buildings, floors) for room in rooms.values()]
        room_reports = self._run(tasks)
        room_reports.sort(key=lambda r: (r.building_name or "", r.floor_name or "", r.room_name))

        by_building: Dict[str, List[RoomReport]] = {}
        for r in room_reports:
            by_building.setdefault(r.building_id if r.building_id in buildings else UNASSIGNED, []).append(r)

        building_reports: List[BuildingReport] = []
        for bid, building in buildings.items():
            building_rooms = by_building.get(bid, [])
            building_reports.append(self._building_report(building, building_rooms, floors))
        if by_building.get(UNASSIGNED):
            orphan = Building(id=UNASSIGNED, name="Unassigned rooms")
            building_reports.append(self._building_report(orphan, by_building[UNASSIGNED], floors))
        building_reports.sort(key=lambda b: (b.building_id == UNASSIGNED, b.building_name))

        summary = summarize(room_reports, config)
        warnings = [f"{r.room_name}: {r.message}" for r in room_reports if r.status == "error"]
        report = PortfolioReport(
            portfolio_id=portfolio.id,
            portfolio_name=config.title or portfolio.name,
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            config=config.to_dict(),
            summary=summary,
            buildings=building_reports,
            rooms=room_reports,
            actions=group_actions(room_reports, config.max_actions, qualify=len(building_reports) > 1),
            worst_room_ids=worst_rooms(room_reports, config.top_n_rooms),
            warnings=warnings,
        )
        report.highlights = highlights(summary, building_reports, config)
        report.duration_s = round(time.perf_counter() - started, 2)
        logger.info("Report for %d rooms built in %.1fs", len(room_reports), report.duration_s)
        return report

    # ------------------------------------------------------------------
    @staticmethod
    def _building_id(room: Room, floors: Mapping[str, Floor]) -> Optional[str]:
        if room.building_id:
            return room.building_id
        floor = floors.get(room.floor_id or "")
        return floor.building_id if floor else None

    def _task(
        self,
        room: Room,
        portfolio: Portfolio,
        buildings: Mapping[str, Building],
        floors: Mapping[str, Floor],
    ) -> RoomTask:
        building_id = self._building_id(room, floors)
        building = buildings.get(building_id or "")
        floor = floors.get(room.floor_id or "")
        climate: Dict[str, dict] = {}
        holiday_periods: list = []
        timezone = None
        for source in (portfolio, building):
            meta = getattr(source, "metadata", None) or {}
            timezone = meta.get("timezone") or timezone
            for key in ("climate_data", "climate_timeseries"):
                if isinstance(meta.get(key), dict):
                    climate.update(meta[key])
            holiday_periods.extend(meta.get("holiday_periods") or [])
        if building_id and not room.building_id:
            room = room.model_copy(update={"building_id": building_id})
        return RoomTask(
            room=room,
            building_name=(building.name if building else None) or building_id,
            floor_name=floor.name if floor else None,
            country=(building.country if building else None) or portfolio.country,
            region=(building.region if building else None) or portfolio.region,
            building_type=building.building_type if building else None,
            climate=climate,
            holiday_periods=holiday_periods,
            timezone=timezone,
        )

    def _run(self, tasks: List[RoomTask]) -> List[RoomReport]:
        total = len(tasks)
        backend, workers = self.config.resolve_workers(total)
        worker = partial(analyze_room, config=self.config)
        results: List[RoomReport] = []

        def tick() -> None:
            if self.progress:
                self.progress(len(results), total)

        if backend == "serial" or total <= 1:
            for task in tasks:
                results.append(worker(task))
                tick()
            return results

        executor_cls = ProcessPoolExecutor if backend == "process" else ThreadPoolExecutor
        try:
            with executor_cls(max_workers=workers) as pool:
                for result in self._map(pool, worker, tasks, workers):
                    results.append(result)
                    tick()
        except Exception as exc:  # e.g. sandbox without multiprocessing
            if backend != "process" or results:
                raise
            logger.warning("Process pool unavailable (%s); falling back to serial analysis", exc)
            for task in tasks:
                results.append(worker(task))
                tick()
        return results

    @staticmethod
    def _map(pool: Executor, fn, tasks: List[RoomTask], workers: int):
        chunk = max(1, len(tasks) // (workers * 4))
        if isinstance(pool, ProcessPoolExecutor):
            return pool.map(fn, tasks, chunksize=chunk)
        return pool.map(fn, tasks)

    def _building_report(self, building: Building, rooms: List[RoomReport], floors: Mapping[str, Floor]) -> BuildingReport:
        config = self.config
        floor_groups: Dict[str, List[RoomReport]] = {}
        for r in rooms:
            if r.floor_id:
                floor_groups.setdefault(r.floor_id, []).append(r)
        floor_reports = []
        for fid, members in floor_groups.items():
            floor = floors.get(fid)
            floor_reports.append(
                FloorReport(
                    floor_id=fid,
                    floor_name=(floor.name if floor else fid),
                    floor_number=floor.floor_number if floor else None,
                    summary=summarize(members, config),
                )
            )
        floor_reports.sort(key=lambda f: (f.floor_number is None, f.floor_number or 0, f.floor_name))
        return BuildingReport(
            building_id=building.id,
            building_name=building.name or building.id,
            building_type=building.building_type,
            city=building.city,
            country=building.country,
            area_m2=building.area_m2,
            year_built=building.year_built,
            ifc_guid=building.ifc_guid,
            summary=summarize(rooms, config),
            floors=floor_reports,
            actions=group_actions(rooms, 3),
            worst_room_ids=worst_rooms(rooms, 5),
        )


def build_report(
    portfolio: Portfolio,
    buildings: Mapping[str, Building],
    floors: Mapping[str, Floor],
    rooms: Mapping[str, Room],
    config: Optional[ReportConfig] = None,
    **kwargs,
) -> PortfolioReport:
    return ReportBuilder(config).build(portfolio, buildings, floors, rooms, **kwargs)


__all__ = ["ReportBuilder", "build_report"]
