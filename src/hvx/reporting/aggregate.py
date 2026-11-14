# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Roll room results up to floors, buildings and the portfolio."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence

from .analysis import PARAMETER_LABELS, _weighted
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
    keys = sorted({k for r in analysed for k in r.exceedance_hours})
    for key in keys:
        values = [r.exceedance_hours[key] for r in analysed if key in r.exceedance_hours]
        s.exceedance_hours[key] = round(sum(values) / len(values), 1)
    return s


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


def group_actions(rooms: Iterable[RoomReport], limit: int) -> List[ActionItem]:
    """Merge per-room recommendations into portfolio/building actions."""
    groups: Dict[tuple, ActionItem] = {}
    severity: Dict[tuple, tuple] = {}
    for r in rooms:
        for rec in r.recommendations:
            title = _generic_title(rec, r.room_name)
            key = (rec.get("type"), title)
            priority = str(rec.get("priority", "low")).lower()
            item = groups.get(key)
            if item is None:
                item = groups[key] = ActionItem(type=str(rec.get("type")), title=title, priority=priority)
            if r.room_id not in item.room_ids:
                item.room_ids.append(r.room_id)
                item.room_names.append(r.room_name)
            rank = (_PRIORITY.get(priority, 3), r.ieq_score if r.ieq_score is not None else 101.0)
            if key not in severity or rank < severity[key]:
                severity[key] = rank
                item.priority = priority
                item.description = rec.get("description")
                item.expected_benefit = rec.get("expected_benefit")
    ordered = sorted(groups.values(), key=lambda a: (_PRIORITY.get(a.priority, 3), -a.room_count, a.title))
    return ordered[:limit]


def highlights(
    portfolio_summary: GroupSummary,
    buildings: Sequence[BuildingReport],
    config: ReportConfig,
) -> List[str]:
    s = portfolio_summary
    out: List[str] = []
    out.append(
        f"{s.rooms_analysed} of {s.rooms_total} rooms analysed ({s.coverage_pct:g}% coverage)"
        + (f", {s.area_analysed_m2:,.0f} m²." if s.area_analysed_m2 else ".")
    )
    if s.meets_target_pct is not None:
        out.append(f"{s.meets_target_pct:g}% of rated rooms meet the Category {config.target_category} target.")
    if s.category:
        share = round(config.group_category_threshold * 100)
        out.append(f"Portfolio category {s.category}: at least {share}% of rooms reach Category {s.category} or better.")
    params = {p: v for p, v in s.compliance.items() if v is not None}
    if len(params) > 1:
        weakest = min(params, key=params.get)
        out.append(
            f"{PARAMETER_LABELS.get(weakest, weakest)} is the weakest parameter: rooms are within "
            f"Category {config.target_category} limits {params[weakest]:g}% of the time on average."
        )
    if "co2>1000" in s.exceedance_hours:
        line = f"Rooms are above 1000 ppm CO₂ for {s.exceedance_hours['co2>1000']:,.0f} occupied hours on average"
        if s.exceedance_hours.get("co2>2000"):
            line += f" and above 2000 ppm for {s.exceedance_hours['co2>2000']:,.0f} hours"
        out.append(line + ".")
    if "temperature>26" in s.exceedance_hours:
        out.append(f"Rooms are above 26 °C for {s.exceedance_hours['temperature>26']:,.0f} occupied hours on average (BR18 allows 100 h).")
    scored = [b for b in buildings if b.summary.ieq_score is not None]
    if len(scored) > 1:
        worst = min(scored, key=lambda b: b.summary.ieq_score)
        out.append(f"Lowest-scoring building: {worst.building_name} (IEQ score {worst.summary.ieq_score:g}).")
    problems = s.rooms_without_data + s.rooms_failed
    if problems:
        out.append(
            f"{problems} room(s) could not be assessed ({s.rooms_without_data} without data, {s.rooms_failed} failed)."
        )
    return out


__all__ = ["group_category", "summarize", "worst_rooms", "group_actions", "highlights"]
