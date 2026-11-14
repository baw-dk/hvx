# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Report renderers: one PortfolioReport, many output formats."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Union

from ..model import PortfolioReport
from .html import CONFIG_BRAND, render_html, write_html
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
    "pdf": "application/pdf",
}


def render(report: PortfolioReport, fmt: str = "html", brand=CONFIG_BRAND):
    """Text for html/json/csv; bytes for pdf. ``brand`` overrides the config's branding (html/pdf)."""
    if fmt.lower() == "pdf":
        from .pdf import render_pdf

        return render_pdf(report, brand=brand)
    if fmt.lower() == "html":
        return render_html(report, brand)
    try:
        return RENDERERS[fmt.lower()](report)
    except KeyError as exc:
        raise ValueError(f"Unknown report format {fmt!r}; expected one of {sorted(RENDERERS)}") from exc


def write(report: PortfolioReport, path: Union[str, Path], fmt: str | None = None, brand=CONFIG_BRAND) -> Path:
    path = Path(path)
    fmt = (fmt or path.suffix.lstrip(".") or "html").lower()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = render(report, fmt, brand)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8", newline="" if fmt == "csv" else None)
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
