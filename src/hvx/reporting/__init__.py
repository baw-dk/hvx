"""
Portfolio IEQ reporting.

Pipeline::

    entities ──► ReportBuilder ──► PortfolioReport ──► render(html | json | csv)
                 (per-room, parallel)   (one model)

Quick start::

    from hvx.reporting import ReportConfig, generate_report

    generate_report(portfolio, buildings, floors, rooms, "out/report.html",
                    config=ReportConfig(seasons=("winter", "summer")))
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional, Union

from .builder import ReportBuilder, build_report
from .config import ReportConfig
from .model import (
    SCHEMA_VERSION,
    ActionItem,
    BuildingReport,
    FloorReport,
    GroupSummary,
    ParameterSummary,
    PortfolioReport,
    RoomReport,
    SeasonResult,
)
from .renderers import MEDIA_TYPES, render, write


def generate_report(
    portfolio,
    buildings: Mapping,
    floors: Mapping,
    rooms: Mapping,
    output_path: Union[str, Path],
    config: Optional[ReportConfig] = None,
    fmt: Optional[str] = None,
) -> PortfolioReport:
    """Build a report and write it; the format follows the file extension unless ``fmt`` is given."""
    report = ReportBuilder(config).build(portfolio, buildings, floors, rooms)
    write(report, output_path, fmt)
    return report


__all__ = [
    "ReportBuilder",
    "ReportConfig",
    "PortfolioReport",
    "BuildingReport",
    "FloorReport",
    "RoomReport",
    "GroupSummary",
    "ParameterSummary",
    "SeasonResult",
    "ActionItem",
    "SCHEMA_VERSION",
    "MEDIA_TYPES",
    "build_report",
    "generate_report",
    "render",
    "write",
]
