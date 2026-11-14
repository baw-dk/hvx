# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""HTML renderer (Jinja2, autoescaped, self-contained output)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from .. import charts
from ..analysis import PARAMETER_LABELS
from ..model import PortfolioReport

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def _pct(value: Optional[float], digits: int = 1) -> str:
    return "–" if value is None else f"{value:.{digits}f}%"


def _num(value: Optional[float], digits: int = 1, unit: str = "") -> str:
    if value is None:
        return "–"
    text = f"{value:,.{digits}f}"
    return f"{text} {unit}".strip()


def _level(value: Optional[float]) -> str:
    """CSS class for a 0-100 value (compliance or score)."""
    if value is None:
        return "lvl-na"
    if value >= 95:
        return "lvl-1"
    if value >= 90:
        return "lvl-2"
    if value >= 70:
        return "lvl-3"
    return "lvl-4"


def _date(value: Optional[str]) -> str:
    if not value:
        return "–"
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d")
    except ValueError:
        return value


def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=("html", "j2"), default=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(pct=_pct, num=_num, level=_level, date=_date)
    env.globals.update(
        category_bar=lambda counts, **kw: Markup(charts.category_bar(counts, **kw)),
        histogram=lambda bins, **kw: Markup(charts.histogram(bins, **kw)),
        meter=lambda v, **kw: Markup(charts.meter(v, **kw)),
        param_label=lambda p: PARAMETER_LABELS.get(p, p),
        CATEGORY_LABELS=charts.CATEGORY_LABELS,
    )
    return env


def render_html(report: PortfolioReport) -> str:
    template = _environment().get_template("report.html.j2")
    return template.render(report=report, cfg=report.config, s=report.summary)


def write_html(report: PortfolioReport, path: Union[str, Path]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(report), encoding="utf-8")
    return path


__all__ = ["render_html", "write_html"]
