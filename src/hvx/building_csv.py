# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
A building from one CSV per room: TAIL labels for each room and for the building, and the
full hvx indoor-climate report. Used by the TAIL web app (in the browser, with Pyodide).

Each room is a dict::

    {"name": "Room 1.12", "csv": "<CSV text>", "columns": {"CO2 (ppm)": "co2"},   # columns optional
     "volume_m3": 180, "area_m2": 60, "spot_values": {"reverberation_time": 0.6}}

The CSV format is the one of :mod:`hvx.tail_label` (a time column, then any of temperature,
CO2, humidity, noise, illuminance, PM2.5, NO2 ...; an outdoor temperature column is optional).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import pandas as pd

from hvx import tail_label
from hvx.core.schedules import OccupancySchedule
from hvx.standards.tail.aggregate import TAIL_DOMAIN_OF, typical_tail

RoomSpec = Dict[str, Any]


def _room_id(name: str, used: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", (name or "room").lower()).strip("_") or "room"
    rid, n = base, 2
    while rid in used:
        rid, n = f"{base}_{n}", n + 1
    used.add(rid)
    return rid


def _frames(rooms: Sequence[RoomSpec]) -> List[Tuple[RoomSpec, pd.DataFrame]]:
    if not rooms:
        raise ValueError("Add at least one room (one CSV file per room).")
    out = []
    for i, spec in enumerate(rooms):
        name = spec.get("name") or f"Room {i + 1}"
        try:
            out.append(({**spec, "name": name}, tail_label.read_measurements(spec["csv"], spec.get("columns"))))
        except ValueError as exc:
            raise ValueError(f"{name}: {exc}") from exc
    return out


def room_labels(rooms: Sequence[RoomSpec], **options: Any) -> List[Dict[str, Any]]:
    """TAIL label of every room (options as :func:`hvx.tail_label.assess`, shared by all rooms)."""
    labels = []
    for spec, frame in _frames(rooms):
        room_options = {**options, "name": spec["name"]}
        for key in ("volume_m3", "area_m2", "persons", "spot_values"):
            if spec.get(key) not in (None, "", {}):
                room_options[key] = spec[key]
        try:
            labels.append(tail_label.assess(frame, **room_options))
        except ValueError as exc:
            raise ValueError(f"{spec['name']}: {exc}") from exc
    return labels


def building_label(labels: Sequence[Dict[str, Any]], name: Optional[str] = None) -> Dict[str, Any]:
    """
    TAIL label of a building from its rooms' labels, as the TAIL sources prescribe
    (offices and hotels: paper Eq. 1, the mean of the rooms' parameter ratings; schools:
    the mean of the classrooms' domain ratings). Same shape as a room label, plus ``rooms``.
    """
    if not labels:
        raise ValueError("No room labels to combine.")
    group = typical_tail([
        {"profile": lab["profile"], "overall": lab["overall"], "domains": lab["domains"],
         "parameters": {p: v["rating"] for p, v in lab["parameters"].items()}}
        for lab in labels
    ])
    parameters = {}
    for p, rating in group["parameters"].items():
        rated = [lab["parameters"][p] for lab in labels if p in lab["parameters"]]
        counts: Dict[str, int] = {}
        for r in rated:
            counts[r["rating"]] = counts.get(r["rating"], 0) + 1
        means = [r["mean"] for r in rated if r.get("mean") is not None]
        parameters[p] = {
            "rating": rating, "domain": rated[0]["domain"] if rated else TAIL_DOMAIN_OF.get(p, "iaq"),
            "unit": rated[0].get("unit") if rated else None,
            "mean": round(sum(means) / len(means), 2) if means else None,
            "summary_value": None, "samples": len(rated), "rule": None,
            "adaptive": any(r.get("adaptive") for r in rated) or None,
            "distribution": counts,  # how many rooms have each rating
        }
    starts = [lab["coverage"]["start"] for lab in labels]
    ends = [lab["coverage"]["end"] for lab in labels]
    first = labels[0]
    hours = sorted(lab["occupied"]["hours"] for lab in labels)
    warnings = []
    if len({lab["profile"] for lab in labels}) > 1:
        warnings.append("The rooms were rated with different TAIL profiles.")
    return {
        "kind": "building",
        "name": name,
        "profile": first["profile"],
        "standard": first["standard"],
        "basis": group["basis"],
        "overall": group["overall"],
        "domains": group["domains"],
        "parameters": parameters,
        "not_rated": {},
        "extensions": {},
        "coverage": {"start": min(starts), "end": max(ends), "days": max(lab["coverage"]["days"] for lab in labels),
                     "step_minutes": first["coverage"]["step_minutes"],
                     "samples": sum(lab["coverage"]["samples"] for lab in labels), "completeness_pct": {}},
        "occupied": {**first["occupied"], "hours": hours[len(hours) // 2]},  # median room
        "rooms": [{"name": lab.get("name"), "overall": lab["overall"], "domains": lab["domains"]} for lab in labels],
        "distribution": group["distribution"],
        "warnings": warnings,
    }


def labels(rooms: Sequence[RoomSpec], building_name: Optional[str] = None, **options: Any) -> Dict[str, Any]:
    """Room labels and, with more than one room, the building label: ``{"rooms": [...], "building": {...}}``."""
    rooms_out = room_labels(rooms, **options)
    building = building_label(rooms_out, building_name) if len(rooms_out) > 1 else None
    return {"rooms": rooms_out, "building": building}


def profile_schedule(building_type: str, schedule: Union[None, OccupancySchedule, Dict[str, Any]] = None) -> OccupancySchedule:
    """``schedule`` as an :class:`OccupancySchedule`, or the TAIL profile's hours for the building type."""
    if isinstance(schedule, OccupancySchedule):
        return schedule
    if schedule:
        return OccupancySchedule.from_dict(schedule)
    hours = tail_label.default_hours(building_type)
    return OccupancySchedule(start=hours["start"], end=hours["end"], weekdays=tuple(hours["weekdays"]),
                             public_holidays=hours["profile"] != "hotel")


def hierarchy(
    rooms: Sequence[RoomSpec],
    building_name: str = "Building",
    building_type: str = "office",
    room_type: Optional[str] = None,
    mechanical_cooling: Optional[bool] = None,
    country: str = "DK",
):
    """``(portfolio, buildings, floors, rooms)`` for :class:`hvx.reporting.ReportBuilder`."""
    from hvx.core.entities import Building, Floor, Portfolio, Room
    from hvx.core.enums import SpatialEntityType

    frames = _frames(rooms)
    metadata: Dict[str, Any] = {}
    if mechanical_cooling is not None:
        metadata["mechanical_cooling"] = bool(mechanical_cooling)
    outdoor = next((f["outdoor_temperature"].dropna() for _, f in frames if "outdoor_temperature" in f.columns), None)
    if outdoor is not None and len(outdoor):
        metadata["climate_data"] = {"outdoor_temperature": {
            "timestamps": [t.isoformat() for t in outdoor.index], "values": [float(v) for v in outdoor]}}

    portfolio = Portfolio(id="portfolio", name=building_name, type=SpatialEntityType.PORTFOLIO, country=country)
    building = Building(id="building", name=building_name, parent_ids=[portfolio.id], building_type=building_type,
                        country=country, metadata=metadata)
    portfolio.add_building(building.id)
    floor = Floor(id="floor", name="", building_id=building.id, parent_ids=[building.id], floor_number=0)
    building.add_floor(floor.id)
    out_rooms: Dict[str, Room] = {}
    used: set = set()
    for spec, frame in frames:
        frame = frame.drop(columns=[c for c in tail_label.CONTEXT_COLUMNS if c in frame.columns])
        rid = _room_id(spec["name"], used)
        room = Room(id=rid, name=spec["name"], floor_id=floor.id, building_id=building.id, parent_ids=[floor.id],
                    room_type=spec.get("room_type") or room_type,
                    area_m2=spec.get("area_m2") or None, volume_m3=spec.get("volume_m3") or None)
        room.timestamps = [t.isoformat() for t in frame.index]
        room.timeseries_data = {c: [None if pd.isna(v) else float(v) for v in frame[c]] for c in frame.columns}
        floor.add_room(rid)
        building.add_room(rid)
        out_rooms[rid] = room
    return portfolio, {building.id: building}, {floor.id: floor}, out_rooms


def report(
    rooms: Sequence[RoomSpec],
    building_name: str = "Building",
    building_type: str = "office",
    room_type: Optional[str] = None,
    mechanical_cooling: Optional[bool] = None,
    country: str = "DK",
    language: str = "en",
    brand: Optional[str] = "baw",
    seasons: Sequence[str] = ("winter", "summer"),
    schedule: Union[None, OccupancySchedule, Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    The hvx report of the building: ``{"html": <self-contained HTML>, "data": <report as JSON data>}``.
    ``schedule`` (an :class:`OccupancySchedule` or its ``to_dict`` data) defaults to the TAIL
    profile's hours, so the report assesses the same hours as the labels.
    """
    import json

    from hvx.reporting import ReportBuilder, ReportConfig, render

    config = ReportConfig(
        title=building_name, language=language, branding=brand, seasons=tuple(seasons),
        default_country=country, default_building_type=building_type, mechanical_cooling=mechanical_cooling,
        occupancy=profile_schedule(building_type, schedule), parallel_backend="serial",
    )
    result = ReportBuilder(config).build(*hierarchy(rooms, building_name, building_type, room_type, mechanical_cooling, country))
    return {"html": render(result, "html"), "data": json.loads(render(result, "json"))}


__all__ = ["room_labels", "building_label", "labels", "profile_schedule", "hierarchy", "report"]
