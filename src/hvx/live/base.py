"""
Live time-series sources.

A :class:`TimeSeriesSource` answers two questions for a set of point ids
(Home Assistant entity ids, BMS point names, MQTT topics, ...):

* ``history(points, start, end)`` -> ``{point: pd.Series}`` (UTC, tz-aware index)
* ``latest(points)`` -> ``{point: Reading}``

Sources only move numbers. Mapping points onto rooms/parameters is done with
:class:`PointBinding` (see :mod:`hvx.live.bindings`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional, Sequence

import pandas as pd


@dataclass(frozen=True)
class Reading:
    point: str
    value: float
    timestamp: datetime  # tz-aware UTC
    unit: Optional[str] = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def empty_series() -> pd.Series:
    return pd.Series([], index=pd.DatetimeIndex([], tz="UTC"), dtype=float)


def to_series(pairs: Iterable[tuple]) -> pd.Series:
    """Build a sorted, de-duplicated UTC series from ``(timestamp, value)`` pairs."""
    pairs = list(pairs)
    if not pairs:
        return empty_series()
    index = pd.to_datetime([p[0] for p in pairs], utc=True, format="mixed")
    series = pd.Series([float(p[1]) for p in pairs], index=index, dtype=float)
    series = series[~series.index.duplicated(keep="last")].sort_index()
    return series


# Unit normalisation to the model's units (°C, ppm, %RH).
def normalize_unit(value: float, unit: Optional[str]) -> float:
    if unit in ("°F", "F", "degF"):
        return (value - 32.0) * 5.0 / 9.0
    if unit == "K":
        return value - 273.15
    return value


class TimeSeriesSource(ABC):
    """
    Base class for live sources.

    ``hold_values``: True for change-driven sources (Home Assistant, BACnet COV,
    MQTT retained state) where a value stays valid until the next sample, and an
    explicit NaN sample marks "unavailable". False for periodic sources where
    each sample stands for its own moment and silence means missing data.
    """

    name: str = "source"
    hold_values: bool = False

    @abstractmethod
    def history(
        self,
        points: Sequence[str],
        start: datetime,
        end: Optional[datetime] = None,
    ) -> Dict[str, pd.Series]:
        """Samples in ``[start, end]`` per point (UTC index). Missing points may be omitted."""

    def latest(self, points: Sequence[str]) -> Dict[str, Reading]:
        """Most recent sample per point. Default: last value of the past 24 h of history."""
        out: Dict[str, Reading] = {}
        now = utcnow()
        for point, series in self.history(points, now - timedelta(hours=24), now).items():
            series = series.dropna()
            if len(series):
                out[point] = Reading(point, float(series.iloc[-1]), series.index[-1].to_pydatetime())
        return out

    def start(self) -> "TimeSeriesSource":  # noqa: B027 - optional hook for streaming sources
        return self

    def close(self) -> None:  # noqa: B027  # pragma: no cover - optional hook
        pass


__all__ = ["Reading", "TimeSeriesSource", "to_series", "empty_series", "normalize_unit", "utcnow", "as_utc"]
