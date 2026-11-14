# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Report configuration."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

from hvx.core.schedules import OccupancySchedule

VALID_SEASONS = ("winter", "summer", "all_year")
VALID_CATEGORIES = ("I", "II", "III", "IV")

# Weights of the composite IEQ score (renormalised over available parameters).
DEFAULT_SCORE_WEIGHTS: Dict[str, float] = {"temperature": 0.4, "co2": 0.4, "humidity": 0.2}
# Hours above these limits are reported per room (occupied hours). CO2 1000 ppm is
# the Danish Working Environment Authority guideline; 26/27 °C are the BR18 limits.
DEFAULT_EXCEEDANCE: Dict[str, List[float]] = {"co2": [1000.0, 2000.0], "temperature": [26.0, 27.0]}
DEFAULT_DAY_PERIODS: Dict[str, Tuple[str, str]] = {"morning": ("08:00", "12:00"), "afternoon": ("12:00", "16:00")}


@dataclass
class ReportConfig:
    """
    Settings for :class:`reporting.ReportBuilder`.

    Seasons
        ``("winter",)`` assesses all data with heating-season criteria (the
        historical behaviour). With more than one season, data is split by the
        country's heating/cooling months (``core.filters.SeasonalFilter``)
        and each part is assessed with its own criteria; the room's overall
        category is the worst seasonal category.
    Target category
        Compliance percentages and the IEQ score are measured against this
        EN 16798-1 category (Category II = "normal expectation", the usual
        target for new and renovated buildings).
    Occupancy
        With ``occupied_only`` (default) the standards assess only occupied hours:
        ``occupancy`` if given, otherwise the building type's opening hours
        (``hvx.core.schedules``), minus public holidays and any
        ``holiday_periods`` here or in building/portfolio ``metadata["holiday_periods"]``.
        Simulations still see all data (CO₂ decay happens after people leave).
    Parallelism
        ``max_workers=None`` picks automatically: serial for small portfolios,
        a process pool otherwise. Rooms are independent so throughput scales
        with cores.
    """

    title: Optional[str] = None
    language: str = "en"  # "en" or "da": report texts, numbers and dates
    introduction: Optional[str] = None  # shown under the title; blank lines separate paragraphs
    notes: Tuple[str, ...] = ()  # extra method/data notes shown in the method section
    # None: white-label (no company details). A built-in brand name ("baw") or a brand YAML path:
    # logo, accent colour and company details incl. CVR number (see reporting.branding).
    branding: Optional[str] = None
    seasons: Tuple[str, ...] = ("winter",)
    target_category: str = "II"
    default_country: str = "DK"
    default_building_type: str = "office"
    # Buildings without mechanical cooling are assessed with the EN 16798-1 adaptive model
    # outside the heating season (needs outdoor temperature). None: per building
    # (metadata "mechanical_cooling"), else fixed cooling-season ranges.
    mechanical_cooling: Optional[bool] = None

    include_simulations: bool = True
    temperature_band: Tuple[float, float] = (20.0, 24.0)  # used by what-if scenarios
    co2_threshold: float = 1200.0  # used by what-if scenarios
    window_area_m2: float = 15.0
    score_weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SCORE_WEIGHTS))
    group_category_threshold: float = 0.70  # share of rooms needed for a building/portfolio category

    issue_threshold_pct: float = 90.0  # parameter compliance below this is flagged as an issue
    min_samples_per_season: int = 24

    occupied_only: bool = True
    occupancy: Optional[OccupancySchedule] = None  # None: from building type
    holiday_periods: Tuple[Tuple[str, str], ...] = ()
    exceedance_thresholds: Dict[str, List[float]] = field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_EXCEEDANCE.items()})
    day_periods: Dict[str, Tuple[str, str]] = field(default_factory=lambda: dict(DEFAULT_DAY_PERIODS))
    top_n_rooms: int = 15  # rooms given a detailed card in the HTML report
    max_actions: int = 8

    max_workers: Optional[int] = None
    parallel_backend: str = "auto"  # auto | serial | thread | process
    parallel_threshold: int = 24  # auto mode goes parallel above this many rooms

    def __post_init__(self) -> None:
        self.seasons = tuple(s.lower() for s in self.seasons) or ("winter",)
        for season in self.seasons:
            if season not in VALID_SEASONS:
                raise ValueError(f"Unknown season {season!r}; expected one of {VALID_SEASONS}")
        self.target_category = str(self.target_category).upper()
        if self.target_category not in VALID_CATEGORIES:
            raise ValueError(f"target_category must be one of {VALID_CATEGORIES}")
        from .i18n import LANGUAGES

        if self.language not in LANGUAGES:
            raise ValueError(f"language must be one of {LANGUAGES}")
        if self.branding is not None:
            from .branding import load_brand

            self.branding = str(self.branding)
            load_brand(self.branding)  # fail early on unknown brands or missing company details
        if self.parallel_backend not in ("auto", "serial", "thread", "process"):
            raise ValueError("parallel_backend must be auto, serial, thread or process")
        if not 0 < self.group_category_threshold <= 1:
            raise ValueError("group_category_threshold must be in (0, 1]")

    @property
    def multi_season(self) -> bool:
        return len(self.seasons) > 1

    @property
    def season_label(self) -> str:
        if self.multi_season:
            return "Full year (" + " + ".join(s.capitalize() for s in self.seasons) + ")"
        return self.seasons[0].replace("_", " ").capitalize()

    def resolve_workers(self, n_rooms: int) -> Tuple[str, int]:
        """Return ``(backend, workers)`` for a run over ``n_rooms`` rooms."""
        cpu = os.cpu_count() or 1
        workers = self.max_workers if self.max_workers else min(cpu, 8)
        backend = self.parallel_backend
        if backend == "auto":
            backend = "process" if n_rooms > self.parallel_threshold and workers > 1 else "serial"
        if backend == "serial":
            workers = 1
        return backend, max(1, min(workers, max(n_rooms, 1)))

    def schedule_for(self, building_type: Optional[str], extra_holidays=()) -> OccupancySchedule:
        base = self.occupancy or OccupancySchedule.for_building_type(building_type or self.default_building_type)
        return base.with_holidays(tuple(self.holiday_periods) + tuple(tuple(p) for p in extra_holidays))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["seasons"] = list(self.seasons)
        data["temperature_band"] = list(self.temperature_band)
        return data

    @classmethod
    def from_legacy(
        cls,
        season: str = "winter",
        analyze_full_year: bool = False,
        temperature_band: Tuple[float, float] = (20.0, 24.0),
        co2_threshold: float = 1200.0,
        **kwargs,
    ) -> "ReportConfig":
        """Map the old ``HTMLReportService`` arguments onto a config."""
        season = {"heating": "winter", "cooling": "summer"}.get(season, season)
        seasons = ("winter", "summer") if analyze_full_year else (season,)
        return cls(seasons=seasons, temperature_band=tuple(temperature_band), co2_threshold=co2_threshold, **kwargs)


__all__ = ["ReportConfig", "DEFAULT_SCORE_WEIGHTS", "VALID_SEASONS", "VALID_CATEGORIES"]
