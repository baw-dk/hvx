"""
Backwards-compatible facade over :mod:`reporting`.

``HTMLReportService`` keeps its historical constructor and ``generate_report``
signature but delegates to :class:`reporting.ReportBuilder`, which:

* no longer mutates the rooms passed in (timeseries used to be truncated);
* analyses each season separately when ``analyze_full_year=True`` (previously
  the summer pass silently reused the cached winter result);
* reports compliance against EN 16798-1 category limits during the same
  samples used for the category, instead of fixed 20–24 °C / 1200 ppm bands;
* renders a self-contained, autoescaped HTML page.

New code should use :func:`reporting.generate_report` directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from hvx.core.entities import Building, Floor, Portfolio, Room
from hvx.reporting import PortfolioReport, ReportBuilder, ReportConfig, RoomReport
from hvx.reporting.renderers import write_html

# Old name for the per-room row; the new RoomReport carries a superset of the data.
RoomReportRow = RoomReport


class HTMLReportService:
    """Generate the facility-manager HTML report (legacy entry point)."""

    def __init__(
        self,
        season: str = "winter",
        temperature_band: Tuple[float, float] = (20.0, 24.0),
        co2_threshold: float = 1200.0,
        analyze_full_year: bool = False,
        **config_overrides: Any,
    ) -> None:
        self.season = season
        self.analyze_full_year = analyze_full_year
        self.temperature_band = temperature_band
        self.co2_threshold = co2_threshold
        self.config = ReportConfig.from_legacy(
            season=season,
            analyze_full_year=analyze_full_year,
            temperature_band=temperature_band,
            co2_threshold=co2_threshold,
            **config_overrides,
        )
        self.last_report: Optional[PortfolioReport] = None

    @property
    def seasons(self):
        return list(self.config.seasons)

    def build(
        self,
        portfolio: Portfolio,
        buildings: Dict[str, Building],
        floors: Dict[str, Floor],
        rooms: Dict[str, Room],
    ) -> PortfolioReport:
        self.last_report = ReportBuilder(self.config).build(portfolio, buildings, floors, rooms)
        return self.last_report

    def generate_report(
        self,
        portfolio: Portfolio,
        buildings: Dict[str, Building],
        floors: Dict[str, Floor],
        rooms: Dict[str, Room],
        output_path: Path,
        entity_lookup: Optional[Callable[[str], Any]] = None,  # kept for signature compatibility
    ) -> Path:
        report = self.build(portfolio, buildings, floors, rooms)
        return write_html(report, Path(output_path))


__all__ = ["HTMLReportService", "RoomReportRow"]
