# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Per-room analysis worker.

:func:`analyze_room` is a pure, top-level function over a picklable
:class:`RoomTask`, so the builder can fan rooms out across processes. It never
mutates the caller's entities: standards run on a private copy of the room.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from hvx.core.data_quality import analyze_dataframe_quality
from hvx.core.entities import Room
from hvx.core.filters.seasonal_filter import SeasonalFilter
from hvx.core.semantics.ieq import PARAMETER_UNITS, ComfortCategory, IEQAssessment

from .config import ReportConfig
from .frames import climate_frame, frame_to_timeseries, room_frame
from .i18n import Translator, describe_schedule
from .model import IEQ_PARAMETERS, ParameterSummary, RoomReport, SeasonResult

logger = logging.getLogger(__name__)

PARAMETER_LABELS = {"temperature": "Temperature", "co2": "CO₂", "humidity": "Humidity"}
_SEASON_PERIOD = {"winter": "heating", "summer": "cooling"}


@dataclass
class RoomTask:
    """Everything needed to analyse one room, detached from the entity graph."""

    room: Room
    building_name: Optional[str] = None
    floor_name: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    building_type: Optional[str] = None
    climate: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    holiday_periods: List[Any] = field(default_factory=list)  # from building/portfolio metadata
    timezone: Optional[str] = None  # IANA zone for timestamps with a UTC offset (building metadata "timezone")


def _round(value: Optional[float], digits: int = 1) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def _weighted(values: List[tuple]) -> Optional[float]:
    """Weighted mean of ``(value, weight)`` pairs ignoring missing values."""
    pairs = [(v, w) for v, w in values if v is not None and w]
    total = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / total if total else None


def season_slice(df: pd.DataFrame, season: str, country: Optional[str]) -> pd.DataFrame:
    if season == "all_year" or not isinstance(df.index, pd.DatetimeIndex):
        return df
    period = _SEASON_PERIOD.get(season, season)
    months = SeasonalFilter(f"{period}:{country}" if country else period).months
    return df[df.index.month.isin(months)]


def ieq_score(compliance: Dict[str, Optional[float]], weights: Dict[str, float]) -> Optional[float]:
    """Composite 0-100 score: weighted mean of parameter compliance at the target category."""
    return _weighted([(compliance.get(p), w) for p, w in weights.items()])


def analyze_room(task: RoomTask, config: ReportConfig) -> RoomReport:
    room = task.room
    report = RoomReport(
        room_id=room.id,
        room_name=room.name,
        building_id=room.building_id,
        building_name=task.building_name,
        floor_id=room.floor_id,
        floor_name=task.floor_name,
        room_type=room.room_type,
        area_m2=room.area_m2,
        brick_class=room.semantic_brick_class(),
        ifc_guid=room.ifc_guid,
        target_category=config.target_category,
    )
    if not room.timeseries_data:
        report.status = "no_data"
        report.message = Translator(config.language)("No sensor data")
        return report
    try:
        _analyze(task, config, report)
    except Exception as exc:  # isolate failures: one bad room must not sink the report
        logger.exception("Room %s failed", room.id)
        report.status = "error"
        report.message = f"{type(exc).__name__}: {exc}"
    return report


def _analyze(task: RoomTask, config: ReportConfig, report: RoomReport) -> None:
    room = task.room
    t = Translator(config.language)
    target = ComfortCategory(config.target_category)
    country = task.country or config.default_country
    building_type = (task.building_type or room.building_type or config.default_building_type)
    building_type = str(building_type).lower()

    from .frames import COUNTRY_TIMEZONES

    tz = task.timezone or COUNTRY_TIMEZONES.get(str(country).upper())
    df, warnings = room_frame(room.timeseries_data, room.timestamps, climate_frame(task.climate, tz), tz)
    report.warnings.extend(warnings)
    if df is None or df.empty:
        report.status = "no_data"
        report.message = t("No usable sensor data")
        return

    report.data_quality = _data_quality(df)
    ieq_cols = [c for c in IEQ_PARAMETERS if c in df.columns]
    durations = _sample_hours(df)

    # Standards apply "during use": assess occupied samples only.
    full = df
    unoccupied = None
    if isinstance(df.index, pd.DatetimeIndex):
        schedule = config.schedule_for(building_type, task.holiday_periods)
        unoccupied = pd.Series(~schedule.mask(df.index, country).to_numpy(), index=df.index)
    if config.occupied_only and isinstance(df.index, pd.DatetimeIndex):
        occupied = (~unoccupied).to_numpy()
        df = df[occupied]
        durations = durations[occupied]
        report.occupancy = describe_schedule(schedule, t)
        report.data_quality["occupied_hours"] = round(float(durations.sum()), 1)
        if df.empty:
            report.status = "no_data"
            report.message = t("No data during occupied hours ({hours})", hours=report.occupancy)
            return
    else:
        report.occupancy = t("all hours (24/7 occupancy)")
    _exceedance(report, df, durations, config)
    _profiles(report, df, durations, config)

    # --- standards, per season, on private copies ---------------------------
    assessments: List[IEQAssessment] = []
    for season in config.seasons:
        part = season_slice(df, season, country) if config.multi_season else df
        if len(part.dropna(how="all", subset=ieq_cols or None)) < config.min_samples_per_season:
            if config.multi_season:
                report.warnings.append(t("{season}: not enough data in season ({n} samples); skipped.", season=t(season), n=len(part)))
            continue
        series, stamps = frame_to_timeseries(part)
        outdoor = series.pop("outdoor_temperature", None)
        if outdoor is not None and all(v is None for v in outdoor):
            outdoor = None
        work = room.model_copy(
            update={
                "timeseries_data": series,
                "timestamps": stamps,
                "computed_metrics": {},
                "metadata": dict(room.metadata or {}),
                "building_type": room.building_type or building_type,
            }
        )
        results = work.compute_standards(
            country=country,
            region=task.region,
            building_type=building_type,
            season=season,
            outdoor_temperature=outdoor,
            force_recompute=True,
        )
        season_result = SeasonResult(
            season=season,
            samples=int(len(part)),
            period_start=part.index.min().isoformat() if isinstance(part.index, pd.DatetimeIndex) else None,
            period_end=part.index.max().isoformat() if isinstance(part.index, pd.DatetimeIndex) else None,
        )
        en = results.get("en16798_1")
        if isinstance(en, dict) and en:
            assessment = IEQAssessment.from_en16798(
                room.id,
                en,
                target_category=target,
                period_start=part.index.min() if isinstance(part.index, pd.DatetimeIndex) else None,
                period_end=part.index.max() if isinstance(part.index, pd.DatetimeIndex) else None,
                samples=int(len(part)),
            )
            assessment.season = season
            assessments.append(assessment)
            season_result.achieved_category = assessment.achieved_category.value if assessment.achieved_category else None
            season_result.compliance_pct = _round(assessment.compliance_pct)
            season_result.time_in_category_pct = {k: round(v, 1) for k, v in assessment.time_in_category_pct.items()}
        else:
            reason = results.get("en16798_1_error") or (
                f"EN 16798-1 not applicable (building type '{building_type}', country '{country}')"
                if "temperature" in df.columns
                else "EN 16798-1 needs a temperature series"
            )
            report.warnings.append(f"{season}: {reason}")
        tail = results.get("tail")
        if isinstance(tail, dict):
            season_result.tail_rating = tail.get("overall_rating_label")
            season_result.tail = {
                "overall": tail.get("overall_rating_label"),
                "domains": {k: v.get("rating_label") for k, v in (tail.get("domains") or {}).items() if isinstance(v, dict)},
                "parameters": {k: v.get("rating") for k, v in (tail.get("parameters") or {}).items() if isinstance(v, dict)},
            }
        report.seasons.append(season_result)

    _combine(report, assessments, config, df)
    _br18(report, df, room, country, building_type)

    # --- simulations on the full period -------------------------------------
    if config.include_simulations:
        _simulate(report, full, df, room, config, unoccupied, country)

    report.issues = _issues(report, config)


def _data_quality(df: pd.DataFrame) -> Dict[str, Any]:
    cols = [c for c in IEQ_PARAMETERS if c in df.columns] or list(df.columns)
    try:
        per_param = {k: v.to_dict() for k, v in analyze_dataframe_quality(df[cols]).items()}
    except Exception as exc:  # quality is informative only
        logger.debug("Data quality failed: %s", exc)
        per_param = {}
    completeness = [m.get("completeness_percentage") for m in per_param.values() if m.get("completeness_percentage") is not None]
    interval = None
    if isinstance(df.index, pd.DatetimeIndex) and len(df) > 1:
        interval = df.index.to_series().diff().median().total_seconds() / 60.0
    return {
        "samples": int(len(df)),
        "start": df.index.min().isoformat() if isinstance(df.index, pd.DatetimeIndex) else None,
        "end": df.index.max().isoformat() if isinstance(df.index, pd.DatetimeIndex) else None,
        "interval_minutes": _round(interval),
        "completeness_pct": _round(sum(completeness) / len(completeness)) if completeness else None,
        "gaps": int(sum(m.get("num_gaps") or 0 for m in per_param.values())),
        "parameters": {
            k: {
                "completeness_pct": v.get("completeness_percentage"),
                "gaps": v.get("num_gaps"),
                "outliers": ((v.get("outliers") or {}).get("iqr") or {}).get("count"),
            }
            for k, v in per_param.items()
        },
    }


def _combine(report: RoomReport, assessments: List[IEQAssessment], config: ReportConfig, df: pd.DataFrame) -> None:
    report.assessments = [a.model_dump(mode="json") for a in assessments]
    # EN 16798-1 Category IV is everything outside Category III, so every assessed season has
    # a category; the room takes its worst season.
    categories = [a.achieved_category for a in assessments if a.achieved_category is not None]
    worst = ComfortCategory.worst(*categories)
    report.achieved_category = worst.value if worst else None
    if worst is not None:
        report.meets_target = worst.rank <= ComfortCategory(config.target_category).rank

    for name in IEQ_PARAMETERS:
        entries = [(a.parameters[name], a.samples or 1) for a in assessments if name in a.parameters]
        if not entries:
            continue
        summary = ParameterSummary(
            parameter=name,
            unit=PARAMETER_UNITS.get(name),
            compliance_pct=_round(_weighted([(p.compliance_pct, w) for p, w in entries])),
            mean=_round(_weighted([(p.mean, w) for p, w in entries]), 2),
            minimum=_round(min((p.minimum for p, _ in entries if p.minimum is not None), default=None), 2),
            maximum=_round(max((p.maximum for p, _ in entries if p.maximum is not None), default=None), 2),
        )
        report.parameters[name] = summary
        report.compliance[name] = summary.compliance_pct

    report.ieq_score = _round(ieq_score(report.compliance, config.score_weights))
    tails = [ComfortCategory.parse(s.tail_rating) for s in report.seasons if s.tail_rating]
    tail_worst = ComfortCategory.worst(*tails)
    report.tail_rating = tail_worst.value if tail_worst else None
    report.tail = combine_tail([s.tail for s in report.seasons if s.tail])


def _simulate(report: RoomReport, full: pd.DataFrame, df: pd.DataFrame, room: Room, config: ReportConfig,
              unoccupied: Optional[pd.Series] = None, country: Optional[str] = None) -> None:
    """``full``: all hours (CO₂ decay happens when rooms empty). ``df``: assessed (occupied) hours,
    used for overheating, correlations and scenarios so they match the standards' numbers."""
    from hvx.simulations.models.correlations import ClimateCorrelationModel
    from hvx.simulations.models.recommendations import SmartRecommendationsModel
    from hvx.simulations.models.scenario import ScenarioImpactModel
    from hvx.simulations.models.ventilation import VentilationCalculator

    ventilation = correlations = scenarios = None
    try:
        if "co2" in full.columns:
            # Decays in unoccupied time only (no CO₂ source during the decay). They describe the
            # empty room, when mechanical ventilation may be reduced or off, not use.
            ventilation = VentilationCalculator().estimate_from_co2_decay(
                full["co2"].dropna(), volume_m3=room.volume_m3, unoccupied=unoccupied
            )
            if ventilation is not None:
                report.ventilation = {
                    "basis": "after_hours_co2_decay",
                    "ach": _round(ventilation.ach, 2),
                    "ach_iqr": list(ventilation.confidence_interval),
                    "decays": ventilation.decays,
                    "background_co2": _round(ventilation.outdoor_co2, 0),
                    "r_squared": _round(ventilation.r_squared, 3),
                    "ventilation_l_s": _round(ventilation.ventilation_l_s, 1),
                    "resolvable_max_ach": ventilation.resolvable_max_ach,
                    "description": ventilation.description,
                }
    except Exception as exc:
        report.warnings.append(f"Ventilation estimate failed: {exc}")
    try:
        correlations = ClimateCorrelationModel(
            temperature_band=config.temperature_band, co2_threshold=config.co2_threshold
        ).compute(df, window_area_m2=config.window_area_m2)
        raw = correlations.as_dict()
        report.correlations = {
            k: (_round(raw.get(k), 2) if raw.get(k) is not None else None)
            for k in ("temperature_vs_outdoor", "temperature_vs_solar", "co2_vs_outdoor", "humidity_vs_outdoor")
        }
    except Exception as exc:
        report.warnings.append(f"Climate correlation failed: {exc}")
    # Target-category limits per season (EN 16798-1), and which samples fall in the heating season.
    from hvx.simulations.models.recommendations import RoomEvidence
    from hvx.standards.en16798.analysis import EN16798Calculator, EN16798Category

    category = EN16798Category(config.target_category)
    limits = EN16798Calculator.get_thresholds(category, "heating")
    heat_band = (limits.temperature_heating["lower"], limits.temperature_heating["upper"])
    cool_band = (limits.temperature_cooling["lower"], limits.temperature_cooling["upper"])
    heating = pd.Series(False, index=df.index)
    if isinstance(df.index, pd.DatetimeIndex):
        heating = pd.Series(df.index.isin(season_slice(df, "winter", country).index), index=df.index)
    try:
        scenarios = ScenarioImpactModel(co2_limit=limits.co2_ppm, temp_band=heat_band).estimate_impacts(
            df, ventilation, heating=heating
        )
        report.scenarios = [s for s in (scenarios.as_dict().get(k) for k in ("ventilation", "solar_shading")) if s]
    except Exception as exc:
        report.warnings.append(f"Scenario estimate failed: {exc}")
    try:
        evidence = RoomEvidence.from_frame(df, _sample_hours(df), heating, limits.co2_ppm, heat_band, cool_band)
        if scenarios is not None:
            if scenarios.ventilation is not None:
                evidence.airflow_factor = scenarios.ventilation.metrics.get("airflow_factor")
            if scenarios.solar_shading is not None:
                metrics = scenarios.solar_shading.metrics
                if (metrics.get("t_statistic") or 0) >= 3 and (metrics.get("solar_k_per_100_w_m2") or 0) > 0:
                    evidence.solar_k_per_100 = metrics.get("solar_k_per_100_w_m2")
                    evidence.solar_hours_avoided = metrics.get("hours_avoided")
        recs = SmartRecommendationsModel(config.language).generate(room.name, evidence)
        report.recommendations = [r.as_dict() for r in recs]
    except Exception as exc:
        report.warnings.append(f"Recommendations failed: {exc}")


def _br18(report: RoomReport, df: pd.DataFrame, room: Room, country: str, building_type: str) -> None:
    """BR18 once over all assessed (occupied) hours of the period: its hour limits are per
    year of use, so splitting by season would give each season its own allowance."""
    from hvx.standards.br18.analysis import load_config as br18_config, run as br18_run

    applicability = br18_config().get("applicability") or {}
    if str(country).upper() not in (applicability.get("countries") or []):
        return
    if building_type not in (applicability.get("building_types") or [building_type]):
        return
    series, stamps = frame_to_timeseries(df[[c for c in ("temperature", "co2") if c in df.columns]])
    if not series:
        return
    work = room.model_copy(update={"timeseries_data": series, "timestamps": stamps, "computed_metrics": {},
                                   "building_type": room.building_type or building_type})
    try:
        result = br18_run(work, series, stamps, season="all_year").summary_results
    except Exception as exc:  # BR18 is an add-on: never fail the room for it
        report.warnings.append(f"BR18 check failed: {exc}")
        return
    if result.get("overall_pass") is None:
        return
    report.br18_pass = bool(result["overall_pass"])
    report.br18_failed = sorted(
        str(rule.get("name") or rule_id)
        for rule_id, rule in (result.get("rules") or {}).items()
        if isinstance(rule, dict) and rule.get("passed") is False
    )


def _sample_hours(df: pd.DataFrame) -> pd.Series:
    """Hours each sample stands for: the gap to the next one, capped at max(3x the median
    step, 1 h) so data gaps don't count but an hourly sample always counts as its hour."""
    from hvx.standards.br18.analysis import _sample_hours as sample_hours

    return sample_hours(df.index)


def _exceedance(report: RoomReport, df: pd.DataFrame, hours: pd.Series, config: ReportConfig) -> None:
    for parameter, limits in config.exceedance_thresholds.items():
        if parameter not in df.columns:
            continue
        values = df[parameter]
        for limit in limits:
            report.exceedance_hours[f"{parameter}>{limit:g}"] = round(float(hours[values > limit].sum()), 1)
    if not isinstance(df.index, pd.DatetimeIndex):
        return
    minutes = df.index.hour * 60 + df.index.minute
    for name, (start, end) in config.day_periods.items():
        a, b = (int(x.split(":")[0]) * 60 + int(x.split(":")[1]) for x in (start, end))
        in_period = (minutes >= a) & (minutes < b)
        sub, sub_hours = df[in_period], hours[in_period]
        total = float(sub_hours[sub.notna().any(axis=1)].sum()) if len(sub) else 0.0
        if not total:
            continue
        stats: Dict[str, Optional[float]] = {"hours": round(total, 1)}
        for parameter, limits in config.exceedance_thresholds.items():
            if parameter in sub.columns and limits:
                valid = float(sub_hours[sub[parameter].notna()].sum())
                over = float(sub_hours[sub[parameter] > limits[0]].sum())
                stats[f"{parameter}_mean"] = _round(sub[parameter].mean(), 1)
                stats[f"{parameter}>{limits[0]:g}_pct"] = round(100.0 * over / valid, 1) if valid else None
        report.period_breakdown[name] = stats


def _worst_label(labels) -> Optional[str]:
    worst = ComfortCategory.worst(*(ComfortCategory.parse(x) for x in labels if x))
    return worst.value if worst else None


def combine_tail(parts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Worst TAIL label per parameter, domain and overall across several assessments (seasons)."""
    if not parts:
        return {}
    params = sorted({k for p in parts for k in (p.get("parameters") or {})})
    domains = sorted({k for p in parts for k in (p.get("domains") or {})})
    return {
        "overall": _worst_label(p.get("overall") for p in parts),
        "domains": {d: _worst_label((p.get("domains") or {}).get(d) for p in parts) for d in domains},
        "parameters": {k: _worst_label((p.get("parameters") or {}).get(k) for p in parts) for k in params},
    }


def _profiles(report: RoomReport, df: pd.DataFrame, hours: pd.Series, config: ReportConfig) -> None:
    """Share of assessed time above the first CO2 limit and hours above 26 °C, by hour of day and by month."""
    if not isinstance(df.index, pd.DatetimeIndex) or df.empty:
        return
    co2_limit = (config.exceedance_thresholds.get("co2") or [None])[0]
    t_limit = (config.exceedance_thresholds.get("temperature") or [None])[0]

    def share_above(column: str, limit: float, keys) -> Dict[int, Optional[float]]:
        valid = df[column].notna()
        over = (df[column] > limit).to_numpy()
        frame = pd.DataFrame({"k": keys, "h": hours.to_numpy(), "valid": valid.to_numpy(), "over": over})
        total = frame[frame["valid"]].groupby("k")["h"].sum()
        above = frame[frame["over"]].groupby("k")["h"].sum()
        return {int(k): round(100.0 * float(above.get(k, 0.0)) / float(v), 1) for k, v in total.items() if v}

    def hours_above(column: str, limit: float, keys) -> Dict[int, float]:
        frame = pd.DataFrame({"k": keys, "h": hours.to_numpy(), "over": (df[column] > limit).to_numpy()})
        sums = frame[frame["over"]].groupby("k")["h"].sum()
        present = sorted(set(int(k) for k in keys))
        return {k: round(float(sums.get(k, 0.0)), 1) for k in present}

    profile: Dict[str, Dict[int, Optional[float]]] = {}
    if co2_limit is not None and "co2" in df.columns:
        profile[f"co2>{co2_limit:g}_pct_by_hour"] = share_above("co2", co2_limit, df.index.hour)
        profile[f"co2>{co2_limit:g}_pct_by_month"] = share_above("co2", co2_limit, df.index.month)
    if t_limit is not None and "temperature" in df.columns:
        profile[f"temperature>{t_limit:g}_h_by_month"] = hours_above("temperature", t_limit, df.index.month)
    report.profiles = profile


def _issues(report: RoomReport, config: ReportConfig) -> List[str]:
    t = Translator(config.language)
    issues: List[str] = []
    target = config.target_category
    if report.achieved_category and report.meets_target is False:
        issues.append(t("Achieves Category {cat}; target is Category {target}.", cat=report.achieved_category, target=target))
    if report.br18_failed:
        issues.append(t("BR18 indicators not met: {rules}.", rules="; ".join(t(name) for name in report.br18_failed)))
    for name, summary in report.parameters.items():
        if summary.compliance_pct is None or summary.compliance_pct >= config.issue_threshold_pct:
            continue
        label = t(PARAMETER_LABELS.get(name, name))
        unit = summary.unit or ""
        detail = []
        if summary.mean is not None:
            detail.append(t("mean {value}", value=t.num(summary.mean, 1, unit)))
        if summary.maximum is not None and name == "co2":
            detail.append(t("peak {value}", value=t.num(summary.maximum, 0, "ppm")))
        if summary.minimum is not None and summary.maximum is not None and name != "co2":
            detail.append(t("range {low}–{high}", low=t.num(summary.minimum, 1), high=t.num(summary.maximum, 1, unit)))
        suffix = f" ({', '.join(detail)})" if detail else ""
        issues.append(t("{label} within Category {target} limits only {pct} of the time{suffix}.",
                        label=label, target=target, pct=t.pct(summary.compliance_pct), suffix=suffix))
    occupied = (report.data_quality or {}).get("occupied_hours") or 0
    for key, hours in report.exceedance_hours.items():
        parameter, _, limit = key.partition(">")
        if not hours:
            continue
        share = t(" ({pct} of occupied time)", pct=t.pct(100 * hours / occupied, 0)) if occupied else ""
        if parameter == "co2" and (not occupied or hours / occupied >= 0.05):
            issues.append(t("CO₂ above {limit} ppm for {hours} h{share}.", limit=limit, hours=t.num(hours, 0), share=share))
        elif parameter == "temperature" and float(limit) == 26 and hours > 100:
            issues.append(t("Above 26 °C for {hours} h in use (BR18 guidance value: 100 h).", hours=t.num(hours, 0)))
        elif parameter == "temperature" and float(limit) == 27 and hours > 25:
            issues.append(t("Above 27 °C for {hours} h in use (BR18 guidance value: 25 h).", hours=t.num(hours, 0)))
    return issues


__all__ = ["RoomTask", "analyze_room", "ieq_score", "season_slice"]
