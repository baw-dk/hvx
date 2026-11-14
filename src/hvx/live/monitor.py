# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
LiveMonitor: keep a rolling window of live data and assess it continuously.

    sources ──refresh()──► rolling buffer (per point, bounded) ──► window rooms
                                                                   │
                       snapshot(): current values, live limit checks, rolling
                       EN 16798 assessment per room, portfolio summary
                       report():   full PortfolioReport over the window

Incremental: each refresh only asks sources for data newer than what is
buffered. Memory is bounded by ``window``. Input entities are not modified.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Dict, List, Mapping, Optional, Union

import pandas as pd

from hvx.core.entities import Building, Floor, Portfolio, Room
from hvx.core.filters.seasonal_filter import SeasonalFilter
from hvx.reporting import PortfolioReport, ReportBuilder, ReportConfig, RoomReport
from hvx.reporting.aggregate import summarize
from hvx.reporting.model import GroupSummary

from .base import TimeSeriesSource, as_utc, utcnow
from .bindings import DEFAULT_SOURCE, PointBinding, by_source, discover_bindings
from .limits import category_now, classify, en16798_limits, with_requirements

logger = logging.getLogger(__name__)
LIVE_PARAMETERS = ("temperature", "co2", "humidity")
_UNAVAILABLE = float("-inf")  # marker for explicit "unavailable" samples while resampling


@dataclass
class ParameterNow:
    value: Optional[float]
    timestamp: Optional[str]
    age_minutes: Optional[float]
    stale: bool
    status: str  # ok | low | high | stale | missing
    limits: Optional[tuple] = None


@dataclass
class RoomLiveState:
    room_id: str
    room_name: str
    building_id: Optional[str]
    current: Dict[str, ParameterNow] = field(default_factory=dict)
    category_now: Optional[str] = None
    alerts: List[str] = field(default_factory=list)
    window: Optional[RoomReport] = None


@dataclass
class LiveSnapshot:
    generated_at: str
    season: str
    window_start: str
    rooms: Dict[str, RoomLiveState]
    summary: GroupSummary

    @property
    def alerts(self) -> List[str]:
        return [f"{r.room_name}: {a}" for r in self.rooms.values() for a in r.alerts]


class LiveMonitor:
    def __init__(
        self,
        portfolio: Portfolio,
        buildings: Mapping[str, Building],
        floors: Mapping[str, Floor],
        rooms: Mapping[str, Room],
        sources: Union[TimeSeriesSource, Mapping[str, TimeSeriesSource]],
        window: timedelta = timedelta(days=7),
        interval: str = "15min",
        timezone: str = "UTC",
        stale_after: timedelta = timedelta(hours=1),
        config: Optional[ReportConfig] = None,
        bindings: Optional[List[PointBinding]] = None,
    ) -> None:
        self.portfolio, self.buildings, self.floors, self.rooms = portfolio, dict(buildings), dict(floors), dict(rooms)
        self.sources: Dict[str, TimeSeriesSource] = (
            {DEFAULT_SOURCE: sources} if isinstance(sources, TimeSeriesSource) else dict(sources)
        )
        self.window = window
        self.interval = interval
        self.timezone = timezone
        self.stale_after = stale_after
        self.config = config or ReportConfig(include_simulations=False, parallel_backend="serial", min_samples_per_season=8)
        self.bindings = bindings if bindings is not None else discover_bindings(self.rooms.values())
        self._buffer: Dict[tuple, pd.Series] = {}
        unknown = {b.source for b in self.bindings} - set(self.sources)
        if unknown:
            raise ValueError(f"Bindings reference unknown source(s): {sorted(unknown)}")

    # ------------------------------------------------------------------
    def refresh(self, now: Optional[datetime] = None) -> int:
        """Pull new samples from every source; returns the number of new samples."""
        now = as_utc(now or utcnow())
        horizon = now - self.window
        added = 0
        for source_name, bindings in by_source(self.bindings).items():
            source = self.sources[source_name]
            points = sorted({b.point for b in bindings})
            # Ask from the oldest "last seen" point; points never seen start at the window edge.
            start = min((self._last(source_name, p) or horizon) for p in points)
            try:
                fetched = source.history(points, max(start, horizon), now)
            except Exception as exc:  # a dead source must not stop the others
                logger.warning("Source %s failed: %s", source_name, exc)
                continue
            for point, series in fetched.items():
                key = (source_name, point)
                old = self._buffer.get(key)
                merged = series if old is None else pd.concat([old, series])
                merged = merged[~merged.index.duplicated(keep="last")].sort_index()
                merged = merged[merged.index >= horizon]
                added += len(merged) - (0 if old is None else len(old[old.index >= horizon]))
                self._buffer[key] = merged
        return max(added, 0)

    def _last(self, source: str, point: str) -> Optional[datetime]:
        series = self._buffer.get((source, point))
        return series.index[-1].to_pydatetime() if series is not None and len(series) else None

    # ------------------------------------------------------------------
    def _grid(self, series: pd.Series, hold: bool, now: datetime) -> pd.Series:
        """Resample one point onto the regular grid."""
        if not hold:
            grid = series.resample(self.interval).mean()
            # Averaging only fills buckets with samples; bridge short gaps with the last value.
            return grid.ffill(limit=max(1, int(self.stale_after / pd.Timedelta(self.interval))))
        # Change-driven source: a value holds until the next sample, up to now;
        # an explicit NaN sample (unavailable) ends it.
        marked = series.fillna(_UNAVAILABLE)
        grid = marked.resample(self.interval).last()
        end = pd.Timestamp(now).floor(self.interval)
        if len(grid) and end > grid.index[-1]:
            grid = grid.reindex(pd.date_range(grid.index[0], end, freq=self.interval))
        grid = grid.ffill()
        return grid.where(grid != _UNAVAILABLE)

    def window_rooms(self, now: Optional[datetime] = None) -> Dict[str, Room]:
        """Copies of the rooms holding the buffered window, resampled to ``interval`` in local time."""
        now = as_utc(now or utcnow())
        per_room: Dict[str, Dict[str, pd.Series]] = {}
        for b in self.bindings:
            series = self._buffer.get((b.source, b.point))
            if series is None or series.empty:
                continue
            per_room.setdefault(b.room_id, {})[b.parameter] = self._grid(series, self.sources[b.source].hold_values, now)
        out: Dict[str, Room] = {}
        for room_id, room in self.rooms.items():
            params = per_room.get(room_id)
            if not params:
                out[room_id] = room.model_copy(update={"timeseries_data": {}, "timestamps": [], "computed_metrics": {}})
                continue
            frame = pd.concat(params, axis=1)
            frame.index = frame.index.tz_convert(self.timezone).tz_localize(None)
            frame = frame.dropna(how="all")
            out[room_id] = room.model_copy(
                update={
                    "timeseries_data": {c: frame[c].astype(float).tolist() for c in frame.columns},
                    "timestamps": [ts.isoformat() for ts in frame.index],
                    "computed_metrics": {},
                }
            )
        return out

    def current_season(self, now: Optional[datetime] = None) -> str:
        now = as_utc(now or utcnow())
        local = pd.Timestamp(now).tz_convert(self.timezone)
        heating = SeasonalFilter(f"heating:{self.portfolio.country or self.config.default_country}").months
        return "winter" if local.month in heating else "summer"

    def snapshot(self, now: Optional[datetime] = None, assess_window: bool = True) -> LiveSnapshot:
        now = as_utc(now or utcnow())
        season = self.current_season(now)
        target = self.config.target_category
        base_limits = en16798_limits(season)
        reports: Dict[str, RoomReport] = {}
        if assess_window:
            config = replace(self.config, seasons=(season,))
            report = ReportBuilder(config).build(self.portfolio, self.buildings, self.floors, self.window_rooms(now))
            reports = {r.room_id: r for r in report.rooms}

        rooms: Dict[str, RoomLiveState] = {}
        bindings_by_room: Dict[str, List[PointBinding]] = {}
        for b in self.bindings:
            bindings_by_room.setdefault(b.room_id, []).append(b)
        for room_id, room in self.rooms.items():
            limits = with_requirements(base_limits, target, room.ieq_requirements)
            state = RoomLiveState(room_id, room.name, room.building_id, window=reports.get(room_id))
            values: Dict[str, float] = {}
            for b in bindings_by_room.get(room_id, []):
                raw = self._buffer.get((b.source, b.point))
                hold = self.sources[b.source].hold_values
                bounds = limits.bounds(target, b.parameter)
                series = raw.dropna() if raw is not None else None
                if series is None or series.empty:
                    state.current[b.parameter] = ParameterNow(None, None, None, True, "missing", bounds)
                    state.alerts.append(f"No data for {b.parameter} ({b.point}).")
                    continue
                ts = series.index[-1]
                age = (pd.Timestamp(now) - ts).total_seconds() / 60.0
                value = float(series.iloc[-1])
                if hold:
                    # Change-driven: an unchanged value is still current; only "unavailable" is stale.
                    stale = bool(pd.isna(raw.iloc[-1]))
                    reason = f"{b.parameter} sensor is unavailable."
                else:
                    stale = age > self.stale_after.total_seconds() / 60.0
                    reason = f"{b.parameter} has not reported for {age:.0f} min."
                status = "stale" if stale else classify(value, bounds)
                state.current[b.parameter] = ParameterNow(round(value, 2), ts.isoformat(), round(age, 1), stale, status, bounds)
                if stale:
                    state.alerts.append(reason)
                    continue
                if b.parameter in LIVE_PARAMETERS:
                    values[b.parameter] = value
                if status != "ok" and bounds:
                    limit = bounds[1] if status == "high" else bounds[0]
                    state.alerts.append(f"{b.parameter} {value:g} is {'above' if status == 'high' else 'below'} the Category {target} limit ({limit:g}).")
            state.category_now = category_now(values, limits)
            rooms[room_id] = state

        return LiveSnapshot(
            generated_at=now.isoformat(timespec="seconds"),
            season=season,
            window_start=(now - self.window).isoformat(timespec="seconds"),
            rooms=rooms,
            summary=summarize(list(reports.values()), self.config) if reports else GroupSummary(rooms_total=len(rooms)),
        )

    def report(self, config: Optional[ReportConfig] = None, now: Optional[datetime] = None) -> PortfolioReport:
        """Full report over the buffered window."""
        return ReportBuilder(config or self.config).build(self.portfolio, self.buildings, self.floors, self.window_rooms(now))


__all__ = ["LiveMonitor", "LiveSnapshot", "RoomLiveState", "ParameterNow"]
