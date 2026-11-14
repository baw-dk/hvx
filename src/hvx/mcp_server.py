# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
MCP server: lets an AI assistant (Claude Desktop, Claude Code, …) build IEQ reports with hvx.

Workflow the tools follow::

    load_csv_folder / load_climify_export / load_site   ->  data held in this server
    describe_data                                       ->  what was loaded, gaps
    build_report(...)                                   ->  report id + key figures
    report_details(report_id, section)                  ->  buildings, actions, rooms
    export_report(report_id, path, format, brand)       ->  .html / .pdf / .json / .csv

Run with ``hvx mcp`` (stdio) and register it in the client, e.g. Claude Code::

    claude mcp add hvx -- hvx mcp

File access: tools read data files and write report files with the user's
permissions. Set ``HVX_MCP_ROOT`` to a folder to confine every path to it.
"""

from __future__ import annotations

import os
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # MCP Python SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # pragma: no cover - SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError

INSTRUCTIONS = """\
hvx builds indoor environmental quality (IEQ) reports for buildings: EN 16798-1 categories,
TAIL ratings, Danish BR18 checks, hours above CO2/temperature limits and recommendations.

1. Load data: load_csv_folder (hvx CSV layout), load_climify_export (Climify room exports,
   optional DMI weather files) or load_site (site YAML with live sources). Loading replaces
   what was loaded before.
2. Call describe_data and tell the user what was loaded: buildings, rooms, parameters, period,
   and anything missing (e.g. no outdoor climate data -> fewer recommendations).
3. Ask the user what the report needs before building it, if not given: language (en/da),
   seasons (winter, summer), target category (II is normal), occupied hours (e.g. schools
   08:00-16:00 Mon-Fri) and holiday periods, title, branding (white-label unless asked).
4. build_report returns key figures; report_details gives buildings, priority actions and rooms.
   Summarise faithfully: say which numbers rest on assumptions (recommendation effects use
   default window areas; air change rates come from CO2 decays, mostly after hours).
5. export_report writes HTML/PDF/JSON/CSV. Never invent company details for a brand.
"""

FORMATS = ("html", "pdf", "json", "csv")
MAX_REPORTS = 10


@dataclass
class _Session:
    entities: Optional[tuple] = None  # (portfolio, buildings, floors, rooms)
    source: str = ""
    notes: List[str] = field(default_factory=list)
    reports: "OrderedDict[str, Any]" = field(default_factory=OrderedDict)


_session = _Session()


# --- helpers ---------------------------------------------------------------------------------

def _root() -> Optional[Path]:
    root = os.environ.get("HVX_MCP_ROOT")
    return Path(root).expanduser().resolve() if root else None


def _path(value: str, *, must_exist: bool = True) -> Path:
    """Resolve a user path; refuse anything outside HVX_MCP_ROOT when it is set."""
    path = Path(value).expanduser()
    root = _root()
    if root is not None and not path.is_absolute():
        path = root / path
    path = path.resolve()
    if root is not None and path != root and root not in path.parents:
        raise ValueError(f"{value} is outside HVX_MCP_ROOT ({root})")
    if must_exist and not path.exists():
        raise ValueError(f"{path} does not exist")
    return path


def _set_data(portfolio, buildings, floors, rooms, source: str, notes: Optional[List[str]] = None) -> Dict[str, Any]:
    if portfolio is None or not rooms:
        raise ValueError("No portfolio or rooms found in the data")
    _session.entities = (portfolio, buildings, floors, rooms)
    _session.source = source
    _session.notes = list(notes or [])
    return describe_data()


def _require_data() -> tuple:
    if _session.entities is None:
        raise ValueError("No data loaded: call load_csv_folder, load_climify_export or load_site first")
    return _session.entities


def _report(report_id: str):
    try:
        return _session.reports[report_id]
    except KeyError:
        raise ValueError(f"Unknown report {report_id!r}; built reports: {list(_session.reports)}") from None


def _room_summary(r) -> Dict[str, Any]:
    return {
        "room_id": r.room_id,
        "room": r.room_name,
        "building": r.building_name,
        "status": r.status,
        "category": r.achieved_category,
        "ieq_score": r.ieq_score,
        "tail": (r.tail or {}).get("overall"),
        "br18_pass": r.br18_pass,
        "hours_above": r.exceedance_hours,
        "issues": r.issues[:6],
    }


# --- tools -------------------------------------------------------------------------------------

def load_csv_folder(path: str) -> Dict[str, Any]:
    """Load a portfolio from a folder in the hvx CSV layout (portfolio/buildings/rooms files and
    room time series). Returns a description of what was loaded."""
    from hvx.connectors.csv import load_portfolio

    loaded = load_portfolio(str(_path(path)))
    return _set_data(loaded.portfolio, loaded.buildings, loaded.floors, loaded.rooms, f"CSV folder {path}")


def load_climify_export(
    rooms_folder: str,
    buildings: List[Dict[str, str]],
    portfolio_name: str = "Portfolio",
    parameters: Optional[List[str]] = None,
    country: str = "DK",
    timezone: str = "Europe/Copenhagen",
) -> Dict[str, Any]:
    """Load Climify room exports (one CSV per room, file names start with a building prefix).

    buildings: one entry per building, e.g. {"prefix": "North_School", "name": "North School",
    "climate_file": "/data/dmi_north.csv", "building_type": "school", "room_type": "classroom"};
    climate_file (DMI weather export) is optional but needed for weather-related recommendations.
    parameters: limit what is loaded, e.g. ["temperature", "co2", "humidity"] to leave out light
    readings that do not represent the work plane."""
    from hvx.connectors.climify import BuildingSpec, load_climify_folder

    specs = []
    for b in buildings:
        if not b.get("prefix") or not b.get("name"):
            raise ValueError("each building needs 'prefix' and 'name'")
        extra = {k: b[k] for k in ("building_type", "room_type", "id") if b.get(k)}
        climate = str(_path(b["climate_file"])) if b.get("climate_file") else None
        specs.append(BuildingSpec(b["prefix"], b["name"], climate_file=climate, **extra))
    result = load_climify_folder(
        _path(rooms_folder), specs, portfolio_name=portfolio_name, country=country, timezone=timezone,
        parameters=tuple(parameters) if parameters else None,
    )
    notes = [f"{len(result.skipped)} file(s) matched no building prefix: {result.skipped[:10]}"] if result.skipped else []
    return _set_data(*result.entities, source=f"Climify export {rooms_folder}", notes=notes)


def load_site(site_file: str, days: float = 14.0, interval: str = "15min") -> Dict[str, Any]:
    """Fetch recent data from the live sources in a site YAML file (Home Assistant, ChirpStack, …)
    for the last `days` days, resampled to `interval`."""
    from datetime import timedelta

    from hvx.live import LiveMonitor, load_site as read_site

    site = read_site(str(_path(site_file)))
    sources = site.build_sources()
    for source in sources.values():
        source.start()
    monitor = LiveMonitor(*site.entities, sources=sources, window=timedelta(days=days), interval=interval, timezone=site.timezone)
    samples = monitor.refresh()
    return _set_data(monitor.portfolio, monitor.buildings, monitor.floors, monitor.window_rooms(),
                     f"site {site_file} ({days:g} days)", [f"{samples} samples received"])


def describe_data() -> Dict[str, Any]:
    """Describe the loaded data: buildings, rooms, measured parameters, period and gaps."""
    import pandas as pd

    portfolio, buildings, floors, rooms = _require_data()
    out_buildings = []
    for b in buildings.values():
        b_rooms = [r for r in rooms.values() if r.building_id == b.id]
        params: Dict[str, int] = {}
        starts, ends, samples = [], [], 0
        for r in b_rooms:
            for p, values in (r.timeseries_data or {}).items():
                params[p] = params.get(p, 0) + 1
            if r.timestamps:
                ts = pd.to_datetime(r.timestamps)
                starts.append(ts.min())
                ends.append(ts.max())
                samples += len(ts)
        climate = sorted((b.metadata or {}).get("climate_data", {}) or {})
        out_buildings.append({
            "id": b.id,
            "name": b.name,
            "building_type": getattr(b, "building_type", None),
            "rooms": len(b_rooms),
            "rooms_per_parameter": params,
            "period": [str(min(starts).date()), str(max(ends).date())] if starts else None,
            "samples": samples,
            "outdoor_climate": climate or "none (weather-related analysis and recommendations limited)",
        })
    return {
        "source": _session.source,
        "portfolio": portfolio.name,
        "buildings": out_buildings,
        "rooms": len(rooms),
        "notes": _session.notes,
    }


def build_report(
    title: Optional[str] = None,
    language: str = "en",
    seasons: Optional[List[str]] = None,
    target_category: str = "II",
    occupied_from: Optional[str] = None,
    occupied_to: Optional[str] = None,
    weekdays: Optional[List[int]] = None,
    holiday_periods: Optional[List[List[str]]] = None,
    occupied_only: bool = True,
    introduction: Optional[str] = None,
    notes: Optional[List[str]] = None,
    branding: Optional[str] = None,
    building_ids: Optional[List[str]] = None,
    top_n_rooms: int = 15,
    include_simulations: bool = True,
) -> Dict[str, Any]:
    """Build an IEQ report for the loaded data and return its key figures and a report_id.

    language: "en" or "da". seasons: ["winter"], ["summer"] or ["winter", "summer"] (full year,
    each season with its own criteria). target_category: EN 16798-1 "I".."IV".
    occupied_from/occupied_to ("08:00"/"16:00") and weekdays (0=Mon..6=Sun) set assessed hours;
    if omitted, each building type's default opening hours are used. holiday_periods:
    [["2024-07-01", "2024-08-09"], ...] are left out, as are public holidays.
    branding: None for white-label, or a built-in brand name (see list_brands)."""
    from hvx.core.schedules import OccupancySchedule
    from hvx.reporting import ReportBuilder, ReportConfig

    portfolio, buildings, floors, rooms = _require_data()
    occupancy = None
    if occupied_from or occupied_to or weekdays:
        occupancy = OccupancySchedule(
            start=occupied_from or "08:00", end=occupied_to or "16:00",
            weekdays=tuple(weekdays) if weekdays else (0, 1, 2, 3, 4),
        )
    config = ReportConfig(
        title=title,
        language=language,
        seasons=tuple(seasons or ("winter",)),
        target_category=target_category,
        occupancy=occupancy,
        holiday_periods=tuple(tuple(p) for p in (holiday_periods or ())),
        occupied_only=occupied_only,
        introduction=introduction,
        notes=tuple(notes or ()),
        branding=branding,
        top_n_rooms=top_n_rooms,
        include_simulations=include_simulations,
    )
    report = ReportBuilder(config).build(portfolio, buildings, floors, rooms, building_ids=building_ids)
    report_id = uuid.uuid4().hex[:8]  # several reports (e.g. per language) can be kept side by side
    _session.reports[report_id] = report
    while len(_session.reports) > MAX_REPORTS:
        _session.reports.popitem(last=False)
    s = report.summary
    return {
        "report_id": report_id,
        "title": report.portfolio_name,
        "rooms_analysed": s.rooms_analysed,
        "rooms_total": s.rooms_total,
        "ieq_score": s.ieq_score,
        "portfolio_category": s.category,
        "rooms_meeting_target_pct": s.meets_target_pct,
        "tail": {k: v for k, v in (s.tail or {}).items() if k in ("overall", "domains")},
        "key_findings": report.highlights,
        "warnings": report.warnings[:10],
        "duration_s": report.duration_s,
    }


def report_details(report_id: str, section: str = "buildings", room: Optional[str] = None, limit: int = 15) -> Any:
    """Details of a built report. section: "buildings" (per-building figures), "actions"
    (priority actions), "rooms" (rooms needing attention, worst first), "room" (one room by id or
    name, incl. recommendations), "config" (settings used)."""
    report = _report(report_id)
    if section == "buildings":
        return [{
            "building_id": b.building_id, "building": b.building_name, "rooms_analysed": b.summary.rooms_analysed,
            "ieq_score": b.summary.ieq_score, "category": b.summary.category, "meets_target_pct": b.summary.meets_target_pct,
            "tail": (b.summary.tail or {}).get("overall"), "hours_above": b.summary.exceedance_hours,
        } for b in report.buildings]
    if section == "actions":
        return [{
            "title": a.title, "type": a.type, "priority": a.priority, "rooms": len(a.room_ids),
            "room_names": a.room_names[:10], "description": a.description, "expected_benefit": a.expected_benefit,
        } for a in report.actions[:limit]]
    if section == "rooms":
        return [_room_summary(r) for r in report.worst_rooms[:limit]]
    if section == "room":
        if not room:
            raise ValueError("give room (id or name)")
        matches = [r for r in report.rooms if room in (r.room_id, r.room_name)]
        if not matches:
            raise ValueError(f"No room {room!r}")
        out = []
        for r in matches:
            item = _room_summary(r)
            item.update(compliance=r.compliance, seasons=[{"season": s.season, "category": s.achieved_category} for s in r.seasons],
                        ventilation=r.ventilation, recommendations=r.recommendations, data_quality=r.data_quality)
            out.append(item)
        return out
    if section == "config":
        return report.config
    raise ValueError("section must be buildings, actions, rooms, room or config")


def export_report(report_id: str, path: str, format: Optional[str] = None, brand: Optional[str] = "config",
                  overwrite: bool = False) -> Dict[str, Any]:
    """Write a built report to a file. format: html, pdf, json or csv (default: from the file
    extension). brand: "config" keeps the report's branding, None/"white_label" removes it, or a
    built-in brand name. PDF needs the pdf extra and Chromium."""
    from hvx.reporting import write

    report = _report(report_id)
    target = _path(path, must_exist=False)
    fmt = (format or target.suffix.lstrip(".")).lower()
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {FORMATS}")
    if target.suffix.lower() != f".{fmt}":
        target = target.with_suffix(f".{fmt}")
    if target.exists() and not overwrite:
        raise ValueError(f"{target} exists; pass overwrite=true to replace it")
    written = write(report, target, fmt, brand=brand)
    return {"path": str(written), "format": fmt, "bytes": written.stat().st_size}


def list_brands() -> Dict[str, Any]:
    """Built-in report brands. Without a brand, reports are white-label."""
    from hvx.reporting import available_brands, load_brand

    brands = {}
    for name in available_brands():
        try:
            b = load_brand(name)
            brands[name] = {"ready": True, "company": b.legal_name or b.name, "cvr": b.cvr}
        except ValueError as exc:
            brands[name] = {"ready": False, "problem": str(exc)}
    return {"white_label": "default (no branding)", "brands": brands}


TOOLS = (load_csv_folder, load_climify_export, load_site, describe_data, build_report, report_details, export_report, list_brands)
READ_ONLY = {"describe_data", "report_details", "list_brands"}

REPORT_PROMPT = """\
Create an indoor climate report with hvx for: {subject}

1. Load the data I point you to and call describe_data; tell me what is there and what is missing.
2. Ask me for anything you need that I have not said: language, seasons, occupied hours and holiday
   periods, target category, title, introduction, branding.
3. Build the report, then summarise: key figures, worst buildings and rooms, top actions, and the
   assumptions behind estimated numbers.
4. Export HTML and, if I want, PDF.
"""


def _client_errors(fn):
    """Expected problems (no data, bad path or format, missing extra) reach the assistant as a
    readable tool error; the SDK hides the message of any other exception."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ValueError, FileNotFoundError, ImportError, KeyError) as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


def create_server():
    server = _Server("hvx", instructions=INSTRUCTIONS)
    try:
        from mcp.types import ToolAnnotations
    except ImportError:  # pragma: no cover
        ToolAnnotations = None
    for fn in TOOLS:
        annotations = None
        if ToolAnnotations is not None:
            annotations = ToolAnnotations(readOnlyHint=fn.__name__ in READ_ONLY, openWorldHint=fn.__name__ == "load_site")
        server.tool(annotations=annotations)(_client_errors(fn))

    @server.prompt(name="ieq_report", description="Step-by-step: load data, build and export an IEQ report.")
    def ieq_report(subject: str = "the loaded buildings") -> str:
        return REPORT_PROMPT.format(subject=subject)

    return server


def main(transport: str = "stdio") -> None:
    create_server().run(transport)


__all__ = ["create_server", "main", *(fn.__name__ for fn in TOOLS)]
