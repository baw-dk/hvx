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

from core.data_quality import analyze_dataframe_quality
from core.entities import Room
from core.filters.seasonal_filter import SeasonalFilter
from core.semantics.ieq import PARAMETER_UNITS, ComfortCategory, IEQAssessment

from .config import ReportConfig
from .frames import climate_frame, frame_to_timeseries, room_frame
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
        report.message = "No sensor data"
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
    target = ComfortCategory(config.target_category)
    country = task.country or config.default_country
    building_type = (task.building_type or room.building_type or config.default_building_type)
    building_type = str(building_type).lower()

    df, warnings = room_frame(room.timeseries_data, room.timestamps, climate_frame(task.climate))
    report.warnings.extend(warnings)
    if df is None or df.empty:
        report.status = "no_data"
        report.message = "No usable sensor data"
        return

    report.data_quality = _data_quality(df)
    ieq_cols = [c for c in IEQ_PARAMETERS if c in df.columns]

    # --- standards, per season, on private copies ---------------------------
    assessments: List[IEQAssessment] = []
    for season in config.seasons:
        part = season_slice(df, season, country) if config.multi_season else df
        if len(part.dropna(how="all", subset=ieq_cols or None)) < config.min_samples_per_season:
            if config.multi_season:
                report.warnings.append(f"{season}: not enough data in season ({len(part)} samples); skipped.")
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
        br18 = results.get("br18")
        if isinstance(br18, dict) and br18.get("overall_pass") is not None:
            season_result.br18_pass = bool(br18["overall_pass"])
        report.seasons.append(season_result)

    _combine(report, assessments, config, df)

    # --- simulations on the full period -------------------------------------
    if config.include_simulations:
        _simulate(report, df, room, config)

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
    categories = [a.achieved_category for a in assessments]
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
    passes = [s.br18_pass for s in report.seasons if s.br18_pass is not None]
    report.br18_pass = all(passes) if passes else None


def _simulate(report: RoomReport, df: pd.DataFrame, room: Room, config: ReportConfig) -> None:
    from simulations.models.correlations import ClimateCorrelationModel
    from simulations.models.recommendations import SmartRecommendationsModel
    from simulations.models.scenario import ScenarioImpactModel
    from simulations.models.ventilation import VentilationCalculator

    ventilation = correlations = scenarios = None
    try:
        if "co2" in df.columns:
            ventilation = VentilationCalculator().estimate_from_co2_decay(df["co2"].dropna(), volume_m3=room.volume_m3)
            if ventilation is not None:
                report.ventilation = {
                    "ach": _round(ventilation.ach, 2),
                    "category": ventilation.category,
                    "r_squared": _round(ventilation.r_squared, 3),
                    "ventilation_l_s": _round(ventilation.ventilation_l_s, 1),
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
    try:
        scenarios = ScenarioImpactModel(temp_band=config.temperature_band, co2_threshold=config.co2_threshold).estimate_impacts(df, ventilation)
        report.scenarios = [s for s in (scenarios.as_dict().get(k) for k in ("ventilation", "solar_shading")) if s]
    except Exception as exc:
        report.warnings.append(f"Scenario estimate failed: {exc}")
    if correlations is not None and scenarios is not None:
        try:
            recs = SmartRecommendationsModel().generate(room.name, dict(report.compliance), correlations, ventilation, scenarios)
            report.recommendations = [r.as_dict() for r in recs]
        except Exception as exc:
            report.warnings.append(f"Recommendations failed: {exc}")


def _issues(report: RoomReport, config: ReportConfig) -> List[str]:
    issues: List[str] = []
    target = config.target_category
    if report.achieved_category and report.meets_target is False:
        issues.append(f"Achieves Category {report.achieved_category}; target is Category {target}.")
    elif report.achieved_category is None and report.seasons and report.status == "ok":
        if any(s.time_in_category_pct for s in report.seasons):
            issues.append("Below Category IV for a significant share of the time.")
    for name, summary in report.parameters.items():
        if summary.compliance_pct is None or summary.compliance_pct >= config.issue_threshold_pct:
            continue
        label = PARAMETER_LABELS.get(name, name)
        detail = []
        if summary.mean is not None:
            detail.append(f"mean {summary.mean:g} {summary.unit or ''}".strip())
        if summary.maximum is not None and name == "co2":
            detail.append(f"peak {summary.maximum:g} ppm")
        if summary.minimum is not None and summary.maximum is not None and name != "co2":
            detail.append(f"range {summary.minimum:g}–{summary.maximum:g} {summary.unit or ''}".strip())
        suffix = f" ({', '.join(detail)})" if detail else ""
        issues.append(f"{label} within Category {target} limits only {summary.compliance_pct:g}% of the time{suffix}.")
    return issues


__all__ = ["RoomTask", "analyze_room", "ieq_score", "season_slice"]
