# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
TAIL label from one CSV file of measurements (ideally one year, 365 days).

Kept light on purpose (pandas, numpy, pydantic, pyyaml; no scipy) so it also runs in
the browser with Pyodide: the TAIL label web app (``web/``) calls :func:`label_from_csv`.

The CSV needs a time column and at least one TAIL parameter. Column names are matched
loosely (English and Danish): ``timestamp``/``time``/``tid``, ``temperature``/``temperatur``,
``co2``, ``humidity``/``rh``/``fugtighed``, ``noise``/``støj``, ``illuminance``/``lux``/``lys``,
``pm2.5``, ``formaldehyde``, ``benzene``, ``radon``. Separators ``,`` ``;`` or tab and decimal
commas are detected.
"""

from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Sequence, Union

import pandas as pd

from hvx.core.schedules import OccupancySchedule
from hvx.standards.tail.calculator import TAILCalculator

TIME_NAMES = ("timestamp", "datetime", "date_time", "time", "date", "tid", "tidspunkt", "dato", "local_time", "datetime_local")
# extra names on top of TAILCalculator.PARAMETER_ALIASES (Danish exports, units in headers)
EXTRA_ALIASES = {
    "temperatur": "temperature", "temp_c": "temperature", "temperature_c": "temperature",
    "fugtighed": "relative_humidity", "luftfugtighed": "relative_humidity", "rf": "relative_humidity",
    "humidity_pct": "relative_humidity", "co2_ppm": "co2", "kuldioxid": "co2",
    "stoej": "noise", "støj": "noise", "noise_db": "noise", "lyd": "noise",
    "lys": "illuminance", "lux": "illuminance", "illuminance_lux": "illuminance",
    "pm2_5": "pm25", "pm_2_5": "pm25", "formaldehyd": "formaldehyde", "benzen": "benzene",
    "outdoor_temperature": "outdoor_temperature", "outdoor_temp": "outdoor_temperature", "t_out": "outdoor_temperature",
    "outside_temperature": "outdoor_temperature", "udetemperatur": "outdoor_temperature", "ude_temperatur": "outdoor_temperature",
    "no2": "no2", "nitrogen_dioxide": "no2", "kvælstofdioxid": "no2",
}
CONTEXT_COLUMNS = ("outdoor_temperature",)  # used by the rating, not rated themselves
PARAMETER_UNITS = {"temperature": "°C", "relative_humidity": "%", "co2": "ppm", "noise": "dB(A)", "illuminance": "lx",
                   "pm25": "µg/m³", "formaldehyde": "µg/m³", "benzene": "µg/m³", "radon": "Bq/m³", "no2": "µg/m³",
                   "reverberation_time": "s"}
BUILDING_TYPES = ("office", "hotel", "school")
ROOM_TYPES = {"office": ("small_office", "open_office"), "hotel": ("hotel_room",), "school": ("classroom",)}


def _key(name: str) -> str:
    text = str(name).strip().lower()
    text = re.sub(r"\[.*?\]|\(.*?\)", "", text)  # "Temperature [°C]" -> "temperature"
    return re.sub(r"[\s\-./]+", "_", text).strip("_")


def parameter_for(column: str) -> Optional[str]:
    """TAIL parameter a column name stands for, or None."""
    key = _key(column)
    if key in EXTRA_ALIASES:
        return EXTRA_ALIASES[key]
    compact = key.replace("_", "")
    for alias, parameter in TAILCalculator.PARAMETER_ALIASES.items():
        if compact == alias.replace(" ", "").replace("_", ""):
            return parameter
    for alias, parameter in EXTRA_ALIASES.items():
        if compact == alias.replace("_", ""):
            return parameter
    return None


def read_measurements(source: Union[str, bytes, io.IOBase], columns: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """
    CSV text/bytes/file -> DataFrame indexed by local time, one column per TAIL parameter.
    ``columns`` overrides the detection: ``{"Column in file": "co2", "Other": "ignore"}``.
    """
    if isinstance(source, bytes):
        source = source.decode("utf-8-sig", errors="replace")
    text = source.read() if hasattr(source, "read") else source
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig", errors="replace")
    text = text.lstrip("﻿")
    first = text.splitlines()[0] if text else ""
    sep = max((";", ",", "\t"), key=first.count) if first else ","
    decimal = "," if sep != "," and re.search(r"\d,\d", text[:5000]) else "."
    raw = pd.read_csv(io.StringIO(text), sep=sep, decimal=decimal, dtype=str, keep_default_na=True)
    raw.columns = [str(c).strip() for c in raw.columns]
    if raw.empty:
        raise ValueError("The file has no rows.")

    overrides = {k: v for k, v in (columns or {}).items()}
    time_col = next((c for c, v in overrides.items() if v == "time"), None)
    if time_col is None:
        time_col = next((c for c in raw.columns if _key(c) in TIME_NAMES), None)
    if time_col is None:  # first column that parses as dates
        for c in raw.columns:
            parsed = pd.to_datetime(raw[c].head(50), errors="coerce", format="mixed")
            if parsed.notna().mean() > 0.9:
                time_col = c
                break
    if time_col is None:
        raise ValueError("No time column found (expected e.g. 'timestamp', 'time' or 'tid').")

    stamps = pd.to_datetime(raw[time_col], errors="coerce", format="mixed", utc=False)
    if getattr(stamps.dt, "tz", None) is not None:
        stamps = stamps.dt.tz_convert("Europe/Copenhagen").dt.tz_localize(None)
    data: Dict[str, pd.Series] = {}
    for column in raw.columns:
        if column == time_col:
            continue
        parameter = overrides.get(column) or parameter_for(column)
        if not parameter or parameter in ("ignore", "time") or parameter in data:
            continue
        values = raw[column].str.replace(",", ".", regex=False) if decimal == "," else raw[column]
        data[parameter] = pd.to_numeric(values, errors="coerce")
    if not data:
        raise ValueError("No TAIL parameter found. Name columns e.g. 'temperature', 'co2', 'humidity', 'noise', 'lux'.")
    frame = pd.DataFrame(data)
    frame.index = pd.DatetimeIndex(stamps)
    frame = frame[frame.index.notna()].sort_index()
    frame = frame[~frame.index.duplicated(keep="first")]
    return frame.dropna(how="all")


def detected_columns(source: Union[str, bytes]) -> Dict[str, Optional[str]]:
    """Column name -> detected parameter ('time' for the time column, None if unused)."""
    text = source.decode("utf-8-sig", errors="replace") if isinstance(source, bytes) else source
    first = text.lstrip("﻿").splitlines()[0] if text else ""
    sep = max((";", ",", "\t"), key=first.count) if first else ","
    names = [c.strip().strip('"') for c in first.split(sep)]
    out: Dict[str, Optional[str]] = {}
    time_seen = False
    for name in names:
        if not time_seen and _key(name) in TIME_NAMES:
            out[name], time_seen = "time", True
        else:
            out[name] = parameter_for(name)
    return out


def coverage(frame: pd.DataFrame) -> Dict[str, Any]:
    """Period, days and completeness per parameter (share of expected samples)."""
    index = frame.index
    step = index.to_series().diff().median() if len(index) > 1 else pd.Timedelta(hours=1)
    step = step if pd.notna(step) and step > pd.Timedelta(0) else pd.Timedelta(hours=1)
    span = (index.max() - index.min()) + step if len(index) else pd.Timedelta(0)
    expected = max(int(round(span / step)), 1)
    return {
        "start": index.min().isoformat() if len(index) else None,
        "end": index.max().isoformat() if len(index) else None,
        "days": round(span / pd.Timedelta(days=1), 1),
        "step_minutes": round(step / pd.Timedelta(minutes=1), 1),
        "samples": int(len(index)),
        "completeness_pct": {c: round(100.0 * frame[c].notna().sum() / expected, 1) for c in frame.columns},
    }


def default_hours(building_type: str) -> Dict[str, Any]:
    """Assessed hours of the building type's TAIL profile (offices 09-17, hotels 22-06, schools 08-17)."""
    name, profile = TAILCalculator.profile_for(building_type)
    hours = profile.get("hours") or {"start": "09:00", "end": "17:00", "weekdays": [0, 1, 2, 3, 4]}
    return {"profile": name, **hours}


def assess(
    frame: pd.DataFrame,
    building_type: str = "office",
    room_type: Optional[str] = None,
    occupied_from: Optional[str] = None,
    occupied_to: Optional[str] = None,
    weekdays: Optional[Sequence[int]] = None,
    all_hours: bool = False,
    country: str = "DK",
    holiday_periods: Sequence[Sequence[str]] = (),
    outdoor_co2_ppm: float = 420.0,
    mechanical_cooling: Optional[bool] = None,
    volume_m3: Optional[float] = None,
    area_m2: Optional[float] = None,
    persons: Optional[float] = None,
    spot_values: Optional[Dict[str, float]] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    TAIL rating of a measurement frame over its occupied hours; JSON-ready dict.

    building_type: "office", "hotel" or "school" (TAIL profile). mechanical_cooling=False uses
    the adaptive temperature bands outside the heating season (needs an outdoor temperature
    column). spot_values: single measurements such as {"reverberation_time": 0.6,
    "daylight_factor": 2.4, "radon": 80}.
    """
    building_type = (building_type or "office").lower()
    hours = default_hours(building_type)
    if all_hours:
        schedule = OccupancySchedule(always=True, public_holidays=False)
    else:
        schedule = OccupancySchedule(
            start=occupied_from or hours["start"], end=occupied_to or hours["end"],
            weekdays=tuple(weekdays) if weekdays else tuple(hours["weekdays"]),
            public_holidays=hours["profile"] != "hotel",
        ).with_holidays(holiday_periods)
    context = {c: frame.pop(c) for c in CONTEXT_COLUMNS if c in frame.columns}
    cov = coverage(frame)
    mask = schedule.mask(frame.index, country).to_numpy()
    occupied = frame[mask]
    outdoor_daily = None
    if "outdoor_temperature" in context:
        daily = context["outdoor_temperature"].dropna().resample("D").mean().dropna()
        outdoor_daily = {d.strftime("%Y-%m-%d"): float(v) for d, v in daily.items()}
    warnings: List[str] = []
    if cov["days"] < 360:
        warnings.append(f"The data covers {cov['days']:g} days; a TAIL label should cover a full year (365 days).")
    if occupied.empty:
        raise ValueError(f"No measurements during the occupied hours ({schedule.describe()}).")
    for parameter, pct in cov["completeness_pct"].items():
        if pct < 80:
            warnings.append(f"{parameter}: only {pct:g} % of the expected samples are present.")

    if mechanical_cooling is False and outdoor_daily is None:
        warnings.append("No outdoor temperature column: the fixed temperature bands were used instead of the "
                        "adaptive ones for buildings without mechanical cooling.")
    series = {c: occupied[c] for c in occupied.columns}
    for key, value in (spot_values or {}).items():
        if value is not None and str(value) != "":
            series[key] = pd.Series([float(value)])
    result = TAILCalculator.assess_timeseries(
        series,
        metadata={"building_type": building_type, "room_type": room_type, "outdoor_co2_ppm": outdoor_co2_ppm,
                  "mechanical_cooling": mechanical_cooling, "outdoor_daily_mean_temperature": outdoor_daily,
                  "volume_m3": volume_m3, "area_m2": area_m2, "design_occupancy": persons},
        occupancy_filtered=True,
    )
    parameters = {}
    for p in result.parameter_results:
        parameters[p.parameter] = {
            "rating": p.rating_label,
            "domain": p.category.value,
            "distribution": p.distribution,
            "summary_value": p.summary_value,
            "samples": p.sample_count,
            "unit": PARAMETER_UNITS.get(p.parameter),
            "mean": round(float(occupied[_column_for(occupied, p.parameter)].mean()), 2) if _column_for(occupied, p.parameter) else None,
            "rule": p.metadata.get("rule"),
            "adaptive": p.metadata.get("adaptive"),
        }
    domains = {c.value: r.rating_label for c, r in result.categories.items()}
    return {
        "name": name,
        "profile": result.profile,
        "standard": ("TAIL for schools (Tran 2024)" if result.profile == "school"
                     else "TAIL (Wargocki et al. 2021), reference implementation tail.R"),
        "overall": result.overall_rating_label,
        "domains": domains,
        "parameters": parameters,
        "not_rated": dict(result.not_rated),
        "extensions": {p.parameter: p.rating_label for p in result.extensions},
        "coverage": cov,
        "occupied": {"description": schedule.describe(), "start": schedule.start, "end": schedule.end,
                     "weekdays": list(schedule.weekdays), "all_hours": bool(schedule.always),
                     "hours": round(float(_durations(frame.index)[mask].sum()), 0),
                     "samples": int(len(occupied)), "building_type": building_type, "country": country},
        "warnings": warnings,
    }


def _column_for(frame: pd.DataFrame, parameter: str) -> Optional[str]:
    if parameter in frame.columns:
        return parameter
    return next((c for c in frame.columns if TAILCalculator._normalize_parameter_name(c) == parameter), None)


def _durations(index: pd.DatetimeIndex) -> pd.Series:
    """Hours each sample stands for, from the full timeline (gap to the next sample,
    capped at max(3x median step, 1 h) so data gaps don't count)."""
    if len(index) < 2:
        return pd.Series(1.0, index=index)
    gaps = index.to_series().diff().shift(-1).dt.total_seconds() / 3600.0
    median = float(gaps[gaps > 0].median()) if (gaps > 0).any() else 1.0
    return gaps.fillna(median).clip(lower=0, upper=max(3 * median, 1.0))


def label_from_csv(source: Union[str, bytes], columns: Optional[Dict[str, str]] = None, **options: Any) -> Dict[str, Any]:
    """CSV -> TAIL label data (see :func:`assess` for options)."""
    return assess(read_measurements(source, columns), **options)


__all__ = ["read_measurements", "detected_columns", "coverage", "assess", "label_from_csv", "parameter_for",
           "default_hours", "BUILDING_TYPES", "ROOM_TYPES"]
