"""Report renderers: one PortfolioReport, many output formats."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Union

from ..model import PortfolioReport
from .html import render_html, write_html
from .tabular import render_csv, render_json, report_to_dict, room_rows, write_csv, write_json

RENDERERS: Dict[str, Callable[[PortfolioReport], str]] = {
    "html": render_html,
    "json": render_json,
    "csv": render_csv,
}

MEDIA_TYPES = {
    "html": "text/html; charset=utf-8",
    "json": "application/json",
    "csv": "text/csv; charset=utf-8",
}


def render(report: PortfolioReport, fmt: str = "html") -> str:
    try:
        return RENDERERS[fmt.lower()](report)
    except KeyError as exc:
        raise ValueError(f"Unknown report format {fmt!r}; expected one of {sorted(RENDERERS)}") from exc


def write(report: PortfolioReport, path: Union[str, Path], fmt: str | None = None) -> Path:
    path = Path(path)
    fmt = (fmt or path.suffix.lstrip(".") or "html").lower()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(report, fmt), encoding="utf-8", newline="" if fmt == "csv" else None)
    return path


__all__ = [
    "render",
    "write",
    "render_html",
    "render_json",
    "render_csv",
    "report_to_dict",
    "room_rows",
    "write_html",
    "write_json",
    "write_csv",
    "RENDERERS",
    "MEDIA_TYPES",
]
