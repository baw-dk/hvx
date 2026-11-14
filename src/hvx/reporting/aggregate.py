# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Roll room results up to floors, buildings and the portfolio."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence

from .analysis import PARAMETER_LABELS, _weighted
from .i18n import Translator
from .config import ReportConfig
from .model import CATEGORIES, IEQ_PARAMETERS, ActionItem, BuildingReport, GroupSummary, RoomReport

_PRIORITY = {"high": 0, "medium": 1, "low": 2}


def group_category(counts: Dict[str, int], threshold: float, below_iv: int = 0) -> Optional[str]:
    """Best category reached by at least ``threshold`` of rated rooms (cumulative I→IV).

    ``below_iv`` rooms were assessed but missed Category IV; they count in the
    denominator (as failing every category), unlike rooms that could not be rated.
    """
    total = sum(counts.get(c, 0) for c in CATEGORIES) + below_iv
    if not total:
        return None
    cumulative = 0
    for cat in CATEGORIES:
        cumulative += counts.get(cat, 0)
        if cumulative / total >= threshold - 1e-9:
            return cat
    return None


def summarize(rooms: Sequence[RoomReport], config: ReportConfig) -> GroupSummary:
    s = GroupSummary(rooms_total=len(rooms))
    analysed = [r for r in rooms if r.analysed]
    s.rooms_analysed = len(analysed)
    s.rooms_without_data = sum(1 for r in rooms if r.status == "no_data")
    s.rooms_failed = sum(1 for r in rooms if r.status == "error")
    s.coverage_pct = round(100.0 * len(analysed) / len(rooms), 1) if rooms else 0.0
    s.area_analysed_m2 = round(sum(r.area_m2 or 0.0 for r in analysed), 1)

    for r in analysed:
        s.category_counts[r.achieved_category if r.achieved_category in CATEGORIES else "none"] += 1
    if analysed:
        s.category_pct = {k: round(100.0 * v / len(analysed), 1) for k, v in s.category_counts.items()}
    below_iv = sum(1 for r in analysed if r.below_category_iv)
    s.category = group_category(s.category_counts, config.group_category_threshold, below_iv)

    rated = [r for r in analysed if r.meets_target is not None]
    if rated:
        s.meets_target_pct = round(100.0 * sum(1 for r in rated if r.meets_target) / len(rated), 1)

    # Area-weighted when every analysed room has a floor area, else equal weights.
    use_area = bool(analysed) and all(r.area_m2 for r in analysed)
    weight = (lambda r: r.area_m2) if use_area else (lambda r: 1.0)
    score = _weighted([(r.ieq_score, weight(r)) for r in analysed])
    s.ieq_score = round(score, 1) if score is not None else None
    for p in IEQ_PARAMETERS:
        value = _weighted([(r.compliance.get(p), weight(r)) for r in analysed])
        if value is not None:
            s.compliance[p] = round(value, 1)

    for r in analysed:
        if r.ieq_score is not None:
            s.score_histogram[min(int(r.ieq_score // 10), 9)] += 1
    for name in sorted({k for r in analysed for k in r.profiles}):
        buckets: Dict[int, List[float]] = {}
        for r in analysed:
            for k, v in (r.profiles.get(name) or {}).items():
                if v is not None:
                    buckets.setdefault(int(k), []).append(v)
        s.profiles[name] = {k: round(sum(v) / len(v), 1) for k, v in sorted(buckets.items())}
    s.tail = typical_tail([r.tail for r in analysed if r.tail])
    keys = sorted({k for r in analysed for k in r.exceedance_hours})
    for key in keys:
        values = [r.exceedance_hours[key] for r in analysed if key in r.exceedance_hours]
        s.exceedance_hours[key] = round(sum(values) / len(values), 1)
    return s


TAIL_DOMAIN_OF = {
    "temperature": "thermal", "noise": "acoustic", "illuminance": "luminous", "lux": "luminous", "daylight_factor": "luminous",
}


def typical_tail(rooms: Sequence[Dict]) -> Dict:
    """
    TAIL for a group of rooms: each parameter gets the rounded mean of the rooms'
    ratings (the typical room); domains and overall then follow the TAIL rule
    (worst parameter, worst domain). Using the worst room instead would make
    almost every building IV and hide where most rooms stand.
    """
    if not rooms:
        return {}
    values: Dict[str, List[int]] = {}
    for tail in rooms:
        for p, label in (tail.get("parameters") or {}).items():
            if label in CATEGORIES:
                values.setdefault(p, []).append(CATEGORIES.index(label) + 1)
    params = {p: CATEGORIES[min(3, max(0, int(sum(v) / len(v) + 0.5) - 1))] for p, v in values.items()}
    domains: Dict[str, str] = {}
    for p, label in params.items():
        d = TAIL_DOMAIN_OF.get(p, "iaq")
        if d not in domains or CATEGORIES.index(label) > CATEGORIES.index(domains[d]):
            domains[d] = label
    overall = max(domains.values(), key=CATEGORIES.index) if domains else None
    # How the rooms themselves are rated, per domain and overall: {"thermal": {"I": 3, "IV": 9}, ...}
    distribution: Dict[str, Dict[str, int]] = {}
    for tail in rooms:
        for key, label in [*(tail.get("domains") or {}).items(), ("overall", tail.get("overall"))]:
            if label in CATEGORIES:
                counts = distribution.setdefault(key, {})
                counts[label] = counts.get(label, 0) + 1
    return {"overall": overall, "domains": domains, "parameters": params, "rooms": len(rooms), "distribution": distribution}


def worst_rooms(rooms: Iterable[RoomReport], limit: int) -> List[str]:
    """Rooms most in need of attention: missing the target first, then lowest score."""
    candidates = [
        r for r in rooms
        if r.analysed and (r.meets_target is False or (r.ieq_score is not None and r.ieq_score < 100.0) or r.issues)
    ]
    candidates.sort(key=lambda r: (r.meets_target is not False, r.ieq_score if r.ieq_score is not None else 101.0, r.room_name))
    return [r.room_id for r in candidates[:limit]]


def _generic_title(rec: dict, room_name: str) -> str:
    title = rec.get("title") or rec.get("type", "Action")
    return re.sub(rf"\s+(in|for)\s+{re.escape(room_name)}\s*$", "", title).strip() or title


def _effect_range(kind: Optional[str], values: List[float], t: Translator) -> Optional[str]:
    """Effect estimates of the rooms in one action, as a range (not one room's number)."""
    values = sorted(v for v in values if v is not None)
    if not values or kind is None:
        return None
    lo, hi, mid = values[0], values[-1], values[len(values) // 2]
    if kind == "airflow_factor":
        return t("×{lo}–×{hi} outdoor air during use (median ×{mid}; steady-state estimate)",
                 lo=t.num(lo, 1), hi=t.num(hi, 1), mid=t.num(mid, 1))
    if kind == "hours_avoided":
        return t("{lo}–{hi} fewer hours above 26 °C per room (estimate)", lo=t.num(lo, 0), hi=t.num(hi, 0))
    return None


def group_actions(rooms: Iterable[RoomReport], limit: int, qualify: bool = False, language: str = "en") -> List[ActionItem]:
    """Merge per-room recommendations into portfolio/building actions.

    The description is the action's room-independent summary and the expected effect
    the range over the rooms. ``qualify`` prefixes room names with their building
    (portfolio level, where room names like "11" are ambiguous across buildings).
    """
    t = Translator(language)
    groups: Dict[tuple, ActionItem] = {}
    severity: Dict[tuple, tuple] = {}
    effects: Dict[tuple, tuple] = {}
    for r in rooms:
        for rec in r.recommendations:
            title = rec.get("action") or _generic_title(rec, r.room_name)
            key = (rec.get("type"), title)
            priority = str(rec.get("priority", "low")).lower()
            item = groups.get(key)
            if item is None:
                item = groups[key] = ActionItem(type=str(rec.get("type")), title=title, priority=priority)
            if r.room_id not in item.room_ids:
                item.room_ids.append(r.room_id)
                item.room_names.append(f"{r.building_name} {r.room_name}" if qualify and r.building_name else r.room_name)
            rank = (_PRIORITY.get(priority, 3), r.ieq_score if r.ieq_score is not None else 101.0)
            if key not in severity or rank < severity[key]:
                severity[key] = rank
                item.priority = priority
                item.description = rec.get("summary") or rec.get("description")
            kind, values = effects.get(key, (rec.get("metric_kind"), []))
            if rec.get("metric") is not None:
                values.append(float(rec["metric"]))
            effects[key] = (kind or rec.get("metric_kind"), values)
    for key, item in groups.items():
        kind, values = effects.get(key, (None, []))
        item.expected_benefit = _effect_range(kind, values, t)
    ordered = sorted(groups.values(), key=lambda a: (_PRIORITY.get(a.priority, 3), -a.room_count, a.title))
    return ordered[:limit]


def highlights(
    portfolio_summary: GroupSummary,
    buildings: Sequence[BuildingReport],
    config: ReportConfig,
) -> List[str]:
    t = Translator(config.language)
    s = portfolio_summary
    out: List[str] = []
    line = t("{n} of {total} rooms analysed ({pct} coverage)", n=s.rooms_analysed, total=s.rooms_total, pct=t.pct(s.coverage_pct, 0))
    if s.area_analysed_m2:
        line += t(", {area} m²", area=t.num(s.area_analysed_m2, 0))
    out.append(line + ".")
    if s.meets_target_pct is not None:
        out.append(t("{pct} of rated rooms meet the Category {cat} target.", pct=t.pct(s.meets_target_pct, 0), cat=config.target_category))
    if s.category:
        out.append(t("Portfolio category {cat}: at least {pct} of rooms reach Category {cat} or better.",
                     cat=s.category, pct=t.pct(config.group_category_threshold * 100, 0)))
    params = {p: v for p, v in s.compliance.items() if v is not None}
    if len(params) > 1:
        weakest = min(params, key=params.get)
        out.append(t("{label} is the weakest parameter: rooms are within Category {cat} limits {pct} of the time on average.",
                     label=t(PARAMETER_LABELS.get(weakest, weakest)), cat=config.target_category, pct=t.pct(params[weakest])))
    if "co2>1000" in s.exceedance_hours:
        line = t("Rooms are above 1000 ppm CO₂ for {hours} occupied hours on average", hours=t.num(s.exceedance_hours["co2>1000"], 0))
        if s.exceedance_hours.get("co2>2000"):
            line += t(" and above 2000 ppm for {hours} hours", hours=t.num(s.exceedance_hours["co2>2000"], 0))
        out.append(line + ".")
    if "temperature>26" in s.exceedance_hours:
        out.append(t("Rooms are above 26 °C for {hours} occupied hours on average (BR18 guidance value: 100 h).",
                     hours=t.num(s.exceedance_hours["temperature>26"], 0)))
    scored = [b for b in buildings if b.summary.ieq_score is not None]
    if len(scored) > 1:
        worst = min(scored, key=lambda b: b.summary.ieq_score)
        out.append(t("Lowest-scoring building: {name} (IEQ score {score}).", name=worst.building_name, score=t.num(worst.summary.ieq_score)))
    problems = s.rooms_without_data + s.rooms_failed
    if problems:
        out.append(t("{n} room(s) could not be assessed ({no_data} without data, {failed} failed).",
                     n=problems, no_data=s.rooms_without_data, failed=s.rooms_failed))
    return out


__all__ = ["group_category", "summarize", "worst_rooms", "group_actions", "highlights"]
