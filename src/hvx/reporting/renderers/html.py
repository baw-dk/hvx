# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""HTML renderer (Jinja2, autoescaped, self-contained output)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup, escape

from .. import charts
from ..branding import ReportBranding, load_brand
from ..analysis import PARAMETER_LABELS
from ..i18n import Translator
from ..model import PortfolioReport

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


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


def _heat_class(value: Optional[float], kind: str) -> str:
    """Badness bins for heatmap cells: share of time (pct) or hours."""
    if value is None:
        return "heat-na"
    bounds = (10, 25, 50) if kind == "pct" else (0.5, 10, 25)
    if kind == "hours" and value < bounds[0]:
        return "heat-0"
    for i, bound in enumerate(bounds):
        if value < bound:
            return f"heat-{i}"
    return "heat-3"


def _profile_columns(report: PortfolioReport, key: str) -> List[int]:
    cols = set()
    for b in report.buildings:
        cols.update((b.summary.profiles.get(key) or {}).keys())
    for r in report.worst_rooms:
        cols.update((r.profiles.get(key) or {}).keys())
    return sorted(int(c) for c in cols)


def _tail_badge(rating: Optional[str], prefix: str = "", title: str = "") -> Markup:
    bg, fg = charts.tail_colors(rating)
    text = f"{prefix} {rating or '–'}".strip()
    tip = f' title="{escape(title)}"' if title else ""
    return Markup(f'<span class="tail-badge" style="background:{bg};color:{fg}"{tip}>{escape(text)}</span>')


def _tail_spread(counts: Optional[dict], t: Translator) -> Markup:
    """Thin bar of how many rooms are rated I..IV (the badge shows the typical room)."""
    total = sum((counts or {}).values())
    if not total:
        return Markup("")
    segments = []
    for rating in ("I", "II", "III", "IV"):
        n = counts.get(rating, 0)
        if n:
            bg, _ = charts.tail_colors(rating)
            segments.append(f'<i style="flex:{n};background:{bg}" title="{rating}: {n}"></i>')
    tip = " · ".join(f"{r}: {counts.get(r, 0)}" for r in ("I", "II", "III", "IV"))
    return Markup(f'<span class="tail-spread" title="{escape(t("Rooms"))} {tip}">{"".join(segments)}</span>')


CONFIG_BRAND = "config"  # render with the brand named in the report's config


def resolve_brand(report: PortfolioReport, brand=CONFIG_BRAND) -> Optional[ReportBranding]:
    """``brand="config"`` uses ``report.config["branding"]``; ``None`` forces white-label."""
    return load_brand(report.config.get("branding") if brand == CONFIG_BRAND else brand)


def _environment(report: PortfolioReport) -> Environment:
    t = Translator(report.config.get("language", "en"))
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=("html", "j2"), default=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    labels = {c: t(text) if c == "none" else t("Cat {cat}", cat=c) for c, text in charts.CATEGORY_LABELS.items()}
    day_periods = report.config.get("day_periods") or {}
    weights = report.config.get("score_weights") or {}
    env.filters.update(
        pct=lambda v, d=1: t.pct(v, d),
        num=lambda v, d=1, unit="": t.num(v, d, unit),
        level=_level,
        date=t.date,
        translate=lambda v: t(str(v)),
    )
    env.globals.update(
        _=t,
        lang=t.language,
        unit_h="t" if t.language == "da" else "h",
        category_bar=lambda counts, **kw: Markup(charts.category_bar(counts, labels=labels, pct_format=lambda p: t.pct(p, 0), **kw)),
        histogram=lambda bins, **kw: Markup(charts.histogram(bins, title=t("Distribution of room IEQ scores"), unit=t("rooms"), **kw)),
        meter=lambda v, **kw: Markup(charts.meter(v, **kw)),
        tail_chart=lambda tail, size=220: Markup(charts.tail_sunburst(tail, size=size, language=t.language, title="TAIL", na=t("not measured"))),
        tail_tree=lambda tail: Markup(charts.tail_tree(tail, language=t.language, na=t("not measured"))),
        tail_network=lambda portfolio, buildings, title="": Markup(charts.tail_network(
            portfolio, [(b.building_name, b.summary.tail) for b in buildings], language=t.language, title=title,
            rooms_label=t("{n} rooms"))),
        tail_badge=_tail_badge,
        tail_spread=lambda counts: _tail_spread(counts, t),
        tail_domains=[(k, charts.TAIL_DOMAIN_LABELS.get(t.language, charts.TAIL_DOMAIN_LABELS["en"])[k]) for k in charts.TAIL_ORDER],
        param_label=lambda p: t(PARAMETER_LABELS.get(p, p)),
        category_label=lambda c: labels.get(c, c),
        heat_class=_heat_class,
        heat_text=lambda v, kind: "" if v is None else t.num(v, 0),
        profile_columns=lambda rep, key: _profile_columns(rep, key),
        hour_label=lambda h: f"{int(h):02d}",
        month_label=lambda m: t.month(int(m)),
        period_span=lambda name: f" ({day_periods[name][0][:2]}–{day_periods[name][1][:2]})" if name in day_periods else "",
        score_weights=", ".join(f"{t(PARAMETER_LABELS.get(p, p))} {t.pct(w * 100, 0)}" for p, w in weights.items()),
    )
    return env


def render_html(report: PortfolioReport, brand=CONFIG_BRAND) -> str:
    """Self-contained HTML page. ``brand`` overrides the config's branding (``None``: white-label)."""
    template = _environment(report).get_template("report.html.j2")
    return template.render(report=report, cfg=report.config, s=report.summary, brand=resolve_brand(report, brand))


def write_html(report: PortfolioReport, path: Union[str, Path], brand=CONFIG_BRAND) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(report, brand), encoding="utf-8")
    return path


__all__ = ["render_html", "write_html"]
