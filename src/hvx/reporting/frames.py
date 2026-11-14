# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Build analysis DataFrames from entities without mutating them.

Rooms store ``timeseries_data`` as ``{name: [values]}`` plus one shared
``timestamps`` list. In practice the series are not always the same length:
loaders copy hourly climate data into rooms with 15-minute indoor data. Those
series are aligned on their *own* timestamps (from the building's climate
payload); positional truncation is only used for trivial length differences.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

import numpy as np
import pandas as pd

from hvx.core.semantics.mappings import normalize_metric_name

# A series whose length differs from the timestamps by at most this share is
# assumed to be positionally aligned (e.g. one trailing sample missing).
POSITIONAL_TOLERANCE = 0.01
CLIMATE_ALIGN_TOLERANCE = pd.Timedelta("90min")


def canonical_name(name: str) -> str:
    metric = normalize_metric_name(name)
    return metric.value if metric is not None else str(name).strip().lower()


# Local time zone per country, for timestamps that carry a UTC offset.
COUNTRY_TIMEZONES = {
    "DK": "Europe/Copenhagen", "SE": "Europe/Stockholm", "NO": "Europe/Oslo", "FI": "Europe/Helsinki",
    "DE": "Europe/Berlin", "NL": "Europe/Amsterdam", "BE": "Europe/Brussels", "FR": "Europe/Paris",
    "GB": "Europe/London", "IE": "Europe/Dublin", "ES": "Europe/Madrid", "IT": "Europe/Rome",
    "AT": "Europe/Vienna", "CH": "Europe/Zurich", "PL": "Europe/Warsaw", "IS": "Atlantic/Reykjavik",
}
_TZ_SUFFIX = r"(?:Z|[+-]\d{2}:?\d{2})$"


def to_datetime_index(values: List[Any], timezone: Optional[str] = None) -> pd.DatetimeIndex:
    """
    Parse timestamps to a tz-naive DatetimeIndex in local time (NaT for bad values).

    Naive timestamps are taken as local time already. Timestamps with a UTC offset are
    converted to ``timezone`` (local wall-clock time) so occupied hours such as 08–16 and
    month/season boundaries refer to local time; without a timezone they become UTC.
    """
    raw = pd.Series(list(values), dtype="object")
    text = raw.astype(str).str.strip()
    aware = text.str.contains(_TZ_SUFFIX, regex=True, na=False) | raw.map(
        lambda v: getattr(v, "tzinfo", None) is not None
    )
    out = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns]")
    if (~aware).any():
        naive = pd.to_datetime(raw[~aware], errors="coerce", format="mixed")
        out[~aware] = pd.DatetimeIndex(naive).tz_localize(None) if getattr(naive.dt, "tz", None) else naive
    if aware.any():
        parsed = pd.to_datetime(raw[aware], errors="coerce", utc=True, format="mixed")
        out[aware] = parsed.dt.tz_convert(timezone or "UTC").dt.tz_localize(None)
    return pd.DatetimeIndex(out)


def _numeric(values: List[Any]) -> np.ndarray:
    return pd.to_numeric(pd.Series(values, dtype="object"), errors="coerce").to_numpy(dtype=float)


def climate_frame(payloads: Mapping[str, Mapping[str, Any]], timezone: Optional[str] = None) -> Optional[pd.DataFrame]:
    """Combine ``{param: {"timestamps": [...], "values": [...]}}`` payloads."""
    frames = []
    for name, payload in (payloads or {}).items():
        stamps, values = payload.get("timestamps") or [], payload.get("values") or []
        n = min(len(stamps), len(values))
        if n == 0:
            continue
        series = pd.Series(_numeric(values[:n]), index=to_datetime_index(stamps[:n], timezone), name=canonical_name(name))
        series = series[~series.index.isna()]
        series = series[~series.index.duplicated(keep="first")].sort_index()
        frames.append(series)
    if not frames:
        return None
    df = pd.concat(frames, axis=1, sort=True)  # nearest-time alignment needs a sorted index
    return df.loc[:, ~df.columns.duplicated()]


def room_frame(
    timeseries: Mapping[str, List[Any]],
    timestamps: List[Any],
    climate: Optional[pd.DataFrame] = None,
    timezone: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], List[str]]:
    """
    Return ``(df, warnings)`` with canonical column names and a DatetimeIndex.

    ``climate`` (from :func:`climate_frame`) is joined by nearest timestamp for
    any climate column the room does not already carry in aligned form.
    """
    warnings: List[str] = []
    if not timeseries:
        return None, warnings

    n_ts = len(timestamps or [])
    columns: Dict[str, np.ndarray] = {}
    if n_ts:
        for name, values in timeseries.items():
            if not isinstance(values, (list, tuple, np.ndarray, pd.Series)):
                continue
            key = canonical_name(name)
            if key == "timestamp" or key in columns:
                continue
            values = list(values)
            if len(values) == n_ts:
                columns[key] = _numeric(values)
            elif abs(len(values) - n_ts) <= max(1, int(n_ts * POSITIONAL_TOLERANCE)):
                padded = (values + [np.nan] * n_ts)[:n_ts]
                columns[key] = _numeric(padded)
                warnings.append(f"{name}: {len(values)} values for {n_ts} timestamps; aligned positionally.")
            elif climate is not None and key in climate.columns:
                continue  # re-aligned from the climate payload below
            else:
                warnings.append(
                    f"{name}: {len(values)} values for {n_ts} timestamps and no own timestamps; ignored."
                )
        if not columns:
            return None, warnings
        df = pd.DataFrame(columns, index=to_datetime_index(timestamps, timezone))
        bad = int(df.index.isna().sum())
        if bad:
            warnings.append(f"{bad} unparseable timestamps dropped.")
            df = df[~df.index.isna()]
        if df.index.has_duplicates:
            warnings.append(f"{int(df.index.duplicated().sum())} duplicate timestamps dropped.")
            df = df[~df.index.duplicated(keep="first")]
        df = df.sort_index()
    else:
        lengths = {len(v) for v in timeseries.values() if isinstance(v, (list, tuple))}
        if len(lengths) != 1:
            warnings.append("No timestamps and series of different lengths; room skipped.")
            return None, warnings
        df = pd.DataFrame({canonical_name(k): _numeric(list(v)) for k, v in timeseries.items()})
        warnings.append("No timestamps; seasonal split and time-based checks unavailable.")

    if climate is not None and isinstance(df.index, pd.DatetimeIndex) and len(df):
        missing = [c for c in climate.columns if c not in df.columns or df[c].isna().all()]
        if missing:
            aligned = climate[missing].reindex(df.index, method="nearest", tolerance=CLIMATE_ALIGN_TOLERANCE)
            for column in missing:
                df[column] = aligned[column].to_numpy()

    df = df.dropna(how="all")
    return (df if len(df) else None), warnings


def frame_to_timeseries(df: pd.DataFrame) -> Tuple[Dict[str, List[float]], List[str]]:
    """Inverse of :func:`room_frame`, for feeding entity-based standard modules."""
    data = {
        column: [None if pd.isna(v) else float(v) for v in df[column].to_numpy()]
        for column in df.columns
    }
    if isinstance(df.index, pd.DatetimeIndex):
        stamps = [ts.isoformat() for ts in df.index]
    else:
        stamps = []
    return data, stamps


__all__ = ["canonical_name", "climate_frame", "room_frame", "frame_to_timeseries", "to_datetime_index"]
