# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Report data model.

Everything the renderers need, as plain dataclasses (cheap to pickle across
worker processes, trivially serialisable to JSON). The HTML, JSON and CSV
outputs are all views of one :class:`PortfolioReport`, so they can never
disagree.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "hvx.ieq-report/2.0"
CATEGORIES = ("I", "II", "III", "IV")
IEQ_PARAMETERS = ("temperature", "co2", "humidity")


@dataclass
class ParameterSummary:
    parameter: str
    unit: Optional[str] = None
    compliance_pct: Optional[float] = None  # share of time meeting the target category
    mean: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None


@dataclass
class SeasonResult:
    season: str
    achieved_category: Optional[str] = None
    compliance_pct: Optional[float] = None
    time_in_category_pct: Dict[str, float] = field(default_factory=dict)
    samples: int = 0
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    adaptive: bool = False  # EN 16798-1 adaptive temperature limits used (free-running building)
    tail_rating: Optional[str] = None
    tail: Dict[str, Any] = field(default_factory=dict)  # {"domains": {...}, "parameters": {...}} labels I–IV
    br18_pass: Optional[bool] = None
    br18_failed: List[str] = field(default_factory=list)


@dataclass
class RoomReport:
    room_id: str
    room_name: str
    building_id: Optional[str] = None
    building_name: Optional[str] = None
    floor_id: Optional[str] = None
    floor_name: Optional[str] = None
    room_type: Optional[str] = None
    area_m2: Optional[float] = None
    brick_class: Optional[str] = None
    ifc_guid: Optional[str] = None

    status: str = "ok"  # ok | no_data | error
    message: Optional[str] = None

    target_category: str = "II"
    achieved_category: Optional[str] = None
    meets_target: Optional[bool] = None
    ieq_score: Optional[float] = None
    compliance: Dict[str, Optional[float]] = field(default_factory=dict)
    parameters: Dict[str, ParameterSummary] = field(default_factory=dict)
    seasons: List[SeasonResult] = field(default_factory=list)
    tail_rating: Optional[str] = None
    tail: Dict[str, Any] = field(default_factory=dict)  # TAIL overall/domains/parameters (+ hvx extensions), worst across seasons
    br18_pass: Optional[bool] = None
    br18_failed: List[str] = field(default_factory=list)  # names of BR18 rules not met
    below_category_iv: bool = False  # deprecated, always False: EN 16798-1 Category IV is everything outside III

    data_quality: Dict[str, Any] = field(default_factory=dict)
    ventilation: Optional[Dict[str, Any]] = None
    correlations: Dict[str, Optional[float]] = field(default_factory=dict)
    scenarios: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    occupancy: Optional[str] = None  # description of the hours assessed
    exceedance_hours: Dict[str, float] = field(default_factory=dict)  # e.g. {"co2>1000": 586.0}
    period_breakdown: Dict[str, Dict[str, Optional[float]]] = field(default_factory=dict)
    profiles: Dict[str, Dict[int, Optional[float]]] = field(default_factory=dict)  # by hour of day / month
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    assessments: List[Dict[str, Any]] = field(default_factory=list)  # IEQAssessment dumps

    @property
    def analysed(self) -> bool:
        return self.status == "ok"

    # Backwards-compatible aliases for the old RoomReportRow
    @property
    def best_compliance_rate(self) -> Optional[float]:
        return self.ieq_score

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GroupSummary:
    rooms_total: int = 0
    rooms_analysed: int = 0
    rooms_without_data: int = 0
    rooms_failed: int = 0
    coverage_pct: float = 0.0
    area_analysed_m2: float = 0.0
    category: Optional[str] = None
    category_counts: Dict[str, int] = field(default_factory=lambda: {c: 0 for c in (*CATEGORIES, "none")})
    category_pct: Dict[str, float] = field(default_factory=lambda: {c: 0.0 for c in (*CATEGORIES, "none")})
    meets_target_pct: Optional[float] = None
    ieq_score: Optional[float] = None
    compliance: Dict[str, Optional[float]] = field(default_factory=dict)
    exceedance_hours: Dict[str, float] = field(default_factory=dict)  # mean per analysed room
    tail: Dict[str, Any] = field(default_factory=dict)  # hvx "typical room" summary of the rooms' TAIL ratings, not a TAIL building rating (see aggregate.typical_tail)
    profiles: Dict[str, Dict[int, float]] = field(default_factory=dict)  # mean of room profiles
    score_histogram: List[int] = field(default_factory=lambda: [0] * 10)


@dataclass
class ActionItem:
    type: str
    title: str
    priority: str
    room_ids: List[str] = field(default_factory=list)
    room_names: List[str] = field(default_factory=list)
    description: Optional[str] = None
    expected_benefit: Optional[str] = None

    @property
    def room_count(self) -> int:
        return len(self.room_ids)


@dataclass
class FloorReport:
    floor_id: str
    floor_name: str
    floor_number: Optional[int]
    summary: GroupSummary


@dataclass
class BuildingReport:
    building_id: str
    building_name: str
    building_type: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    area_m2: Optional[float] = None
    year_built: Optional[int] = None
    ifc_guid: Optional[str] = None
    summary: GroupSummary = field(default_factory=GroupSummary)
    floors: List[FloorReport] = field(default_factory=list)
    actions: List[ActionItem] = field(default_factory=list)
    worst_room_ids: List[str] = field(default_factory=list)


@dataclass
class PortfolioReport:
    portfolio_id: str
    portfolio_name: str
    generated_at: str
    config: Dict[str, Any]
    summary: GroupSummary
    buildings: List[BuildingReport]
    rooms: List[RoomReport]
    actions: List[ActionItem] = field(default_factory=list)
    worst_room_ids: List[str] = field(default_factory=list)
    highlights: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    duration_s: Optional[float] = None
    schema_version: str = SCHEMA_VERSION

    def room(self, room_id: str) -> Optional[RoomReport]:
        return self._room_index().get(room_id)

    def _room_index(self) -> Dict[str, RoomReport]:
        index = getattr(self, "_index", None)
        if index is None or len(index) != len(self.rooms):
            index = {r.room_id: r for r in self.rooms}
            object.__setattr__(self, "_index", index)
        return index

    @property
    def worst_rooms(self) -> List[RoomReport]:
        index = self._room_index()
        return [index[rid] for rid in self.worst_room_ids if rid in index]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for action, src in zip(data["actions"], self.actions):
            action["room_count"] = src.room_count
        for b_data, b in zip(data["buildings"], self.buildings):
            for action, src in zip(b_data["actions"], b.actions):
                action["room_count"] = src.room_count
        return data


__all__ = [
    "SCHEMA_VERSION",
    "CATEGORIES",
    "IEQ_PARAMETERS",
    "ParameterSummary",
    "SeasonResult",
    "RoomReport",
    "GroupSummary",
    "ActionItem",
    "FloorReport",
    "BuildingReport",
    "PortfolioReport",
]
