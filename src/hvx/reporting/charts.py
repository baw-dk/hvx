# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Tiny inline-SVG chart helpers.

Inline SVG keeps the HTML report self-contained (no CDN, works offline, prints
cleanly) and the chosen chart types stay readable at any portfolio size:
distributions and per-building rows, never one bar per room.
"""

from __future__ import annotations

from html import escape
from typing import List, Optional, Sequence, Tuple

CATEGORY_COLORS = {
    "I": "var(--cat-1)",
    "II": "var(--cat-2)",
    "III": "var(--cat-3)",
    "IV": "var(--cat-4)",
    "none": "var(--cat-none)",
}
CATEGORY_LABELS = {"I": "Cat I", "II": "Cat II", "III": "Cat III", "IV": "Cat IV", "none": "Below IV / n.a."}


def stacked_bar(
    segments: Sequence[Tuple[str, float, str]],
    width: int = 600,
    height: int = 22,
    title: Optional[str] = None,
    pct_format=lambda p: f"{p:.0f}%",
) -> str:
    """Horizontal 100 % bar. ``segments`` = [(label, value, css colour)]."""
    total = sum(max(v, 0) for _, v, _ in segments)
    parts: List[str] = []
    x = 0.0
    if total > 0:
        for label, value, color in segments:
            if value <= 0:
                continue
            w = width * value / total
            pct = 100.0 * value / total
            parts.append(
                f'<rect x="{x:.2f}" y="0" width="{w:.2f}" height="{height}" fill="{color}">'
                f"<title>{escape(label)}: {value:g} ({pct:.0f}%)</title></rect>"
            )
            if w > 34 and height >= 18:
                parts.append(
                    f'<text x="{x + w / 2:.2f}" y="{height / 2 + 4:.1f}" text-anchor="middle" '
                    f'class="bar-label">{escape(pct_format(pct))}</text>'
                )
            x += w
    else:
        parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="var(--cat-none)" opacity="0.4"/>')
    aria = escape(title or ", ".join(f"{label} {value:g}" for label, value, _ in segments))
    return (
        f'<svg class="chart stacked" viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'role="img" aria-label="{aria}">{"".join(parts)}</svg>'
    )


def category_bar(counts: dict, width: int = 600, height: int = 22, labels: Optional[dict] = None,
                 title: str = "EN 16798-1", pct_format=None) -> str:
    names = {**CATEGORY_LABELS, **(labels or {})}
    segments = [(names[c], float(counts.get(c, 0)), CATEGORY_COLORS[c]) for c in ("I", "II", "III", "IV", "none")]
    extra = {"pct_format": pct_format} if pct_format else {}
    return stacked_bar(segments, width=width, height=height, title=title, **extra)


def histogram(bins: Sequence[int], width: int = 600, height: int = 180, title: str = "Rooms by IEQ score", unit: str = "room(s)") -> str:
    """Vertical histogram of 10 score bins (0-10 ... 90-100)."""
    pad_l, pad_b, pad_t = 28, 22, 10
    n = len(bins) or 1
    peak = max(bins) if bins and max(bins) > 0 else 1
    plot_w, plot_h = width - pad_l, height - pad_b - pad_t
    bar_w = plot_w / n
    parts = [
        f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{width}" y2="{pad_t + plot_h}" class="axis"/>',
        f'<text x="{pad_l - 6}" y="{pad_t + 8}" text-anchor="end" class="tick">{peak}</text>',
        f'<text x="{pad_l - 6}" y="{pad_t + plot_h}" text-anchor="end" class="tick">0</text>',
    ]
    for i, count in enumerate(bins):
        h = plot_h * count / peak
        x = pad_l + i * bar_w
        color = "var(--cat-4)" if i < 5 else "var(--cat-3)" if i < 8 else "var(--cat-2)" if i < 9 else "var(--cat-1)"
        parts.append(
            f'<rect x="{x + 2:.1f}" y="{pad_t + plot_h - h:.1f}" width="{bar_w - 4:.1f}" height="{h:.1f}" '
            f'fill="{color}" rx="2"><title>{i * 10}–{i * 10 + 10}: {count} {escape(unit)}</title></rect>'
        )
        if count:
            parts.append(
                f'<text x="{x + bar_w / 2:.1f}" y="{pad_t + plot_h - h - 3:.1f}" text-anchor="middle" class="tick">{count}</text>'
            )
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{height - 6}" text-anchor="middle" class="tick">{i * 10}</text>'
        )
    return (
        f'<svg class="chart hist" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(title)}">{"".join(parts)}</svg>'
    )


def meter(value: Optional[float], width: int = 120, height: int = 8) -> str:
    """Small 0-100 bar used in table cells."""
    if value is None:
        return ""
    v = max(0.0, min(100.0, float(value)))
    color = "var(--cat-1)" if v >= 95 else "var(--cat-2)" if v >= 90 else "var(--cat-3)" if v >= 70 else "var(--cat-4)"
    return (
        f'<svg class="chart meter" viewBox="0 0 {width} {height}" aria-hidden="true">'
        f'<rect width="{width}" height="{height}" rx="{height / 2}" class="meter-bg"/>'
        f'<rect width="{width * v / 100:.1f}" height="{height}" rx="{height / 2}" fill="{color}"/></svg>'
    )


# --- TAIL rating diagram -------------------------------------------------------

TAIL_COLORS = {"I": "#5cc489", "II": "#f4c84f", "III": "#f39a4b", "IV": "#e8605b", None: "#e3e6ea"}
TAIL_TEXT = {"I": "#0f3d24", "II": "#4a3700", "III": "#4a2300", "IV": "#ffffff", None: "#5b6472"}
# Layout of the TAIL scheme (clockwise from 12 o'clock): A, L, I, T quadrants.
TAIL_LAYOUT = (
    ("acoustic", "A", 0, ("noise",)),
    ("luminous", "L", 90, ("daylight_factor", "illuminance")),
    ("iaq", "I", 180, ("co2", "relative_humidity", "benzene", "formaldehyde", "pm2_5", "radon", "ventilation", "mold")),
    ("thermal", "T", 270, ("temperature",)),
)
TAIL_PARAMETER_LABELS = {
    "en": {"temperature": "Temperature", "noise": "Noise", "co2": "CO₂", "relative_humidity": "RH", "benzene": "Benzene",
           "formaldehyde": "CH₂O", "pm2_5": "PM2.5", "radon": "Radon", "ventilation": "Vent.", "mold": "Mould",
           "illuminance": "Lux", "daylight_factor": "Daylight"},
    "da": {"temperature": "Temperatur", "noise": "Støj", "co2": "CO₂", "relative_humidity": "RF", "benzene": "Benzen",
           "formaldehyde": "CH₂O", "pm2_5": "PM2.5", "radon": "Radon", "ventilation": "Vent.", "mold": "Skimmel",
           "illuminance": "Lux", "daylight_factor": "Dagslys"},
}
TAIL_DOMAIN_LABELS = {
    "en": {"thermal": "Thermal", "acoustic": "Acoustic", "iaq": "Air quality", "luminous": "Light", "overall": "Overall"},
    "da": {"thermal": "Termisk", "acoustic": "Akustik", "iaq": "Luftkvalitet", "luminous": "Lys", "overall": "Samlet"},
}
_TAIL_ALIASES = {"humidity": "relative_humidity", "rh": "relative_humidity", "lux": "illuminance", "pm25": "pm2_5",
                 "ch2o": "formaldehyde", "hcho": "formaldehyde", "vent": "ventilation", "df": "daylight_factor"}


def _polar(cx: float, cy: float, r: float, deg: float) -> Tuple[float, float]:
    """Point at radius r and clock angle deg (0 = 12 o'clock, clockwise)."""
    import math

    rad = math.radians(deg)
    return cx + r * math.sin(rad), cy - r * math.cos(rad)


def rounded_sector(cx: float, cy: float, r0: float, r1: float, a0: float, a1: float, corner: float) -> str:
    """
    SVG path of an annular sector (radii r0 < r1, clock angles a0 < a1) with
    rounded corners of radius ``corner``: each corner is a circle tangent to the
    radial edge and to the arc, like d3's ``arc().cornerRadius``.
    """
    import math

    span = math.radians(a1 - a0)
    c = max(0.0, min(corner, (r1 - r0) / 2 - 0.01, r0 * span / 2 * 0.95 if r0 > 0 else corner))

    def p(r: float, deg: float) -> str:
        x, y = _polar(cx, cy, r, deg)
        return f"{x:.2f},{y:.2f}"

    if c < 0.2:
        large = 1 if a1 - a0 > 180 else 0
        return (f"M{p(r1, a0)} A{r1:.2f},{r1:.2f} 0 {large} 1 {p(r1, a1)} "
                f"L{p(r0, a1)} A{r0:.2f},{r0:.2f} 0 {large} 0 {p(r0, a0)} Z")
    to = math.degrees(math.asin(c / (r1 - c)))  # angular offset of outer tangent points
    ti = math.degrees(math.asin(c / (r0 + c)))  # inner
    d_out = math.sqrt((r1 - c) ** 2 - c ** 2)  # radial distance of outer corner's tangent on the edge
    d_in = math.sqrt((r0 + c) ** 2 - c ** 2)
    large_o = 1 if (a1 - a0 - 2 * to) > 180 else 0
    large_i = 1 if (a1 - a0 - 2 * ti) > 180 else 0
    return (
        f"M{p(d_out, a0)} A{c:.2f},{c:.2f} 0 0 1 {p(r1, a0 + to)} "
        f"A{r1:.2f},{r1:.2f} 0 {large_o} 1 {p(r1, a1 - to)} "
        f"A{c:.2f},{c:.2f} 0 0 1 {p(d_out, a1)} "
        f"L{p(d_in, a1)} A{c:.2f},{c:.2f} 0 0 1 {p(r0, a1 - ti)} "
        f"A{r0:.2f},{r0:.2f} 0 {large_i} 0 {p(r0, a0 + ti)} "
        f"A{c:.2f},{c:.2f} 0 0 1 {p(d_in, a0)} Z"
    )


def tail_sunburst(tail: dict, size: int = 260, language: str = "en", title: str = "TAIL", na: str = "not assessed") -> str:
    """
    The TAIL rating diagram: overall rating in the centre, the four domains
    (Thermal, Acoustic, Indoor air, Luminous) in the middle ring and their
    parameters outside, coloured by rating (I green … IV red, grey = not
    assessed). Rounded segments separated by white gaps.
    """
    import math
    import uuid

    uid = "tail-" + uuid.uuid4().hex[:8]  # unique ids: several charts share one page
    labels = TAIL_PARAMETER_LABELS.get(language, TAIL_PARAMETER_LABELS["en"])
    domain_labels = TAIL_DOMAIN_LABELS.get(language, TAIL_DOMAIN_LABELS["en"])
    params = {_TAIL_ALIASES.get(k, k): v for k, v in (tail.get("parameters") or {}).items()}
    domains = tail.get("domains") or {}
    cx = cy = size / 2
    outer = size / 2 - 3
    gap = max(2.0, size / 110)  # white space between segments and rings
    r_core = outer * 0.30
    r_dom0, r_dom1 = r_core + gap, outer * 0.62
    r_par0, r_par1 = r_dom1 + gap, outer
    corner = size / 55
    unit = size / 260
    white = 'stroke="#ffffff" stroke-width="{w:.2f}" paint-order="stroke"'.format(w=max(1.0, gap * 0.6))
    parts: List[str] = []
    defs: List[str] = []

    def arc_path(radius: float, a0: float, a1: float) -> str:
        """Arc for text: clockwise on the top half, reversed on the bottom so text stays upright."""
        mid = (a0 + a1) / 2 % 360
        large = 1 if a1 - a0 > 180 else 0
        if 90 < mid < 270:
            x0, y0 = _polar(cx, cy, radius, a1)
            x1, y1 = _polar(cx, cy, radius, a0)
            return f"M{x0:.2f},{y0:.2f} A{radius:.2f},{radius:.2f} 0 {large} 0 {x1:.2f},{y1:.2f}"
        x0, y0 = _polar(cx, cy, radius, a0)
        x1, y1 = _polar(cx, cy, radius, a1)
        return f"M{x0:.2f},{y0:.2f} A{radius:.2f},{radius:.2f} 0 {large} 1 {x1:.2f},{y1:.2f}"

    def pad(radius: float) -> float:
        return math.degrees(gap / radius) / 2  # constant linear gap at that radius

    for domain, letter, start, members in TAIL_LAYOUT:
        span = 90.0 / len(members)
        p_pad = pad((r_par0 + r_par1) / 2)
        for i, name in enumerate(members):
            a0, a1 = start + i * span + p_pad, start + (i + 1) * span - p_pad
            rating = params.get(name)
            text = labels.get(name, name)
            parts.append(
                f'<path d="{rounded_sector(cx, cy, r_par0, r_par1, a0, a1, corner)}" fill="{TAIL_COLORS.get(rating, TAIL_COLORS[None])}" {white}>'
                f"<title>{escape(text)}: {escape(rating or na)}</title></path>"
            )
            mid = (a0 + a1) / 2
            lx, ly = _polar(cx, cy, (r_par0 + r_par1) / 2, mid)
            color = TAIL_TEXT.get(rating, TAIL_TEXT[None])
            if span < 30 and size < 200:
                continue  # too small to read; the segment's <title> still names it
            if span < 30:  # narrow segment: write along the radius
                rot = mid - 270 if mid > 180 else mid - 90
                fs = 9.5 * unit
                parts.append(
                    f'<text x="{lx:.1f}" y="{ly:.1f}" transform="rotate({rot:.1f} {lx:.1f} {ly:.1f})" text-anchor="middle" '
                    f'dominant-baseline="central" font-size="{fs:.1f}" font-weight="500" fill="{color}">{escape(text)}</text>'
                )
            else:  # wide segment: set the label along the arc
                fs = (12 if size >= 200 else 14) * unit
                path_id = f"{uid}-{name}"
                defs.append(f'<path id="{path_id}" d="{arc_path((r_par0 + r_par1) / 2, a0, a1)}" fill="none"/>')
                parts.append(
                    f'<text font-size="{fs:.1f}" font-weight="500" fill="{color}" dominant-baseline="central">'
                    f'<textPath href="#{path_id}" startOffset="50%" text-anchor="middle">{escape(text)}</textPath></text>'
                )
        rating = domains.get(domain)
        d_pad = pad((r_dom0 + r_dom1) / 2)
        name = domain_labels[domain]
        parts.append(
            f'<path d="{rounded_sector(cx, cy, r_dom0, r_dom1, start + d_pad, start + 90 - d_pad, corner)}" '
            f'fill="{TAIL_COLORS.get(rating, TAIL_COLORS[None])}" {white}><title>{escape(name)} ({letter}): {escape(rating or na)}</title></path>'
        )
        # Domain name along the arc, with its rating; written out so it reads in any language.
        path_id = f"{uid}-{domain}"
        defs.append(f'<path id="{path_id}" d="{arc_path((r_dom0 + r_dom1) / 2, start + d_pad, start + 90 - d_pad)}" fill="none"/>')
        label = f"{name} {rating}" if rating else name
        parts.append(
            f'<text font-size="{13 * unit:.1f}" font-weight="700" fill="{TAIL_TEXT.get(rating, TAIL_TEXT[None])}" dominant-baseline="central">'
            f'<textPath href="#{path_id}" startOffset="50%" text-anchor="middle">{escape(label)}</textPath></text>'
        )
    overall = tail.get("overall")
    parts.append(
        f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r_core:.2f}" fill="{TAIL_COLORS.get(overall, TAIL_COLORS[None])}" {white}>'
        f"<title>{escape(title)}: {escape(overall or na)}</title></circle>"
    )
    ink = TAIL_TEXT.get(overall, TAIL_TEXT[None])
    parts.append(f'<text x="{cx:.2f}" y="{cy - r_core * 0.42:.2f}" text-anchor="middle" dominant-baseline="central" '
                 f'font-size="{9 * unit:.1f}" font-weight="600" letter-spacing="0.08em" fill="{ink}" opacity="0.85">'
                 f'{escape(domain_labels["overall"].upper())}</text>')
    parts.append(f'<text x="{cx:.2f}" y="{cy + r_core * 0.12:.2f}" text-anchor="middle" dominant-baseline="central" '
                 f'font-size="{34 * unit:.1f}" font-weight="700" fill="{ink}">{escape(overall or "–")}</text>')
    return (
        f'<svg class="chart tail" viewBox="0 0 {size} {size}" width="{size}" height="{size}" role="img" '
        f'font-family="Inter, system-ui, -apple-system, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif" '
        f'aria-label="{escape(title)} {escape(overall or na)}"><defs>{"".join(defs)}</defs>{"".join(parts)}</svg>'
    )


TAIL_ORDER = ("thermal", "acoustic", "iaq", "luminous")  # T, A, I, L


def tail_tree(tail: dict, language: str = "en", na: str = "not measured", width: int = 600) -> str:
    """
    The TAIL rating as a hierarchy, read left to right: overall rating ->
    the four domains (Thermal, Acoustic, Indoor air, Luminous) -> the
    parameters that were measured, each node coloured by its rating
    (I green … IV red). A domain's unmeasured parameters are collapsed into
    one grey node, so missing data neither crowds the picture nor hides.
    """
    import uuid
    from html import escape

    labels = TAIL_PARAMETER_LABELS.get(language, TAIL_PARAMETER_LABELS["en"])
    domain_labels = TAIL_DOMAIN_LABELS.get(language, TAIL_DOMAIN_LABELS["en"])
    params = {_TAIL_ALIASES.get(k, k): v for k, v in (tail.get("parameters") or {}).items()}
    domains = tail.get("domains") or {}
    layout = {key: names for key, _, _, names in TAIL_LAYOUT}
    uid = "tailtree-" + uuid.uuid4().hex[:8]

    leaf_h, leaf_gap, group_gap, pad = 26.0, 6.0, 14.0, 8.0
    x0, r0 = 38.0, 32.0  # overall node centre x and radius
    dom_x, dom_w, dom_h = 118.0, 168.0, 36.0
    leaf_x = 350.0
    leaf_w = width - leaf_x - 4

    groups = []  # (domain key, rating, [(label, rating, tooltip)])
    for key in TAIL_ORDER:
        names = layout[key]
        measured = [(labels.get(n, n), params[n], None) for n in names if params.get(n)]
        missing = [labels.get(n, n) for n in names if not params.get(n)]
        leaves = list(measured)
        if missing:
            shown = list(missing)
            text = f"{na[:1].upper()}{na[1:]}: " + ", ".join(shown)
            while len(text) > 38 and len(shown) > 1:  # keep the pill to one line
                shown.pop()
                text = f"{na[:1].upper()}{na[1:]}: " + ", ".join(shown) + f" +{len(missing) - len(shown)}"
            leaves.append((text, None, ", ".join(missing)))
        rating = domains.get(key) or _worst_rating([r for _, r, _ in measured])
        groups.append((key, rating, leaves))

    y = pad
    placed = []
    for key, rating, leaves in groups:
        ys = []
        for _ in leaves:
            ys.append(y + leaf_h / 2)
            y += leaf_h + leaf_gap
        y += group_gap - leaf_gap
        placed.append((key, rating, leaves, ys, sum(ys) / len(ys)))
    height = y - group_gap + pad
    y0 = sum(p[4] for p in placed) / len(placed)
    overall = tail.get("overall")

    def color(r):
        return TAIL_COLORS.get(r, TAIL_COLORS[None])

    def ink(r):
        return TAIL_TEXT.get(r, TAIL_TEXT[None])

    def link(xa, ya, xb, yb, r):
        mx = (xa + xb) / 2
        return (f'<path d="M{xa:.1f},{ya:.1f} C{mx:.1f},{ya:.1f} {mx:.1f},{yb:.1f} {xb:.1f},{yb:.1f}" fill="none" '
                f'stroke="{color(r)}" stroke-width="2.5" stroke-linecap="round" opacity="{0.9 if r else 0.8}"/>')

    def pill(x, yc, w, h, label, r, size, bold_label=False, tooltip=None, dashed=False):
        tip = f"<title>{escape(tooltip)}</title>" if tooltip else ""
        border = ' stroke="#c4c9d1" stroke-dasharray="3 3"' if dashed else ""
        weight = ' font-weight="600"' if bold_label else ""
        value = "" if dashed else (
            f'<text x="{x + w - 12:.1f}" y="{yc:.1f}" text-anchor="end" dominant-baseline="central" '
            f'font-size="{size + 1:.1f}" font-weight="700" fill="{ink(r)}">{r or "–"}</text>')
        return (f'<g>{tip}<rect x="{x:.1f}" y="{yc - h / 2:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{h / 2:.1f}" '
                f'fill="{color(r)}"{border}/>'
                f'<text x="{x + 13:.1f}" y="{yc:.1f}" dominant-baseline="central" font-size="{size:.1f}"{weight} '
                f'fill="{ink(r)}">{escape(label)}</text>{value}</g>')

    parts = []
    for key, rating, leaves, ys, yc in placed:
        parts.append(link(x0 + r0 - 2, y0, dom_x + 2, yc, rating))
        for (_, r, _), ly in zip(leaves, ys):
            parts.append(link(dom_x + dom_w - 2, yc, leaf_x + 2, ly, r))
    parts.append(f'<circle cx="{x0}" cy="{y0:.1f}" r="{r0 + 3}" fill="#ffffff"/>'
                 f'<circle cx="{x0}" cy="{y0:.1f}" r="{r0}" fill="{color(overall)}"/>'
                 f'<text x="{x0}" y="{y0 - 11:.1f}" text-anchor="middle" font-size="7.5" font-weight="600" letter-spacing=".08em" '
                 f'fill="{ink(overall)}">{escape(domain_labels["overall"].upper())}</text>'
                 f'<text x="{x0}" y="{y0 + 7:.1f}" text-anchor="middle" dominant-baseline="central" font-size="21" font-weight="750" '
                 f'fill="{ink(overall)}">{overall or "–"}</text>')
    for key, rating, leaves, ys, yc in placed:
        letter = {"thermal": "T", "acoustic": "A", "iaq": "I", "luminous": "L"}[key]
        parts.append(pill(dom_x, yc, dom_w, dom_h, f"{letter} · {domain_labels[key]}", rating, 12.5, bold_label=True))
        for (label, r, tip), ly in zip(leaves, ys):
            parts.append(pill(leaf_x, ly, leaf_w, leaf_h, label, r, 11, tooltip=tip, dashed=r is None))
    return (f'<svg class="chart tail-tree" id="{uid}" viewBox="0 0 {width} {height:.0f}" role="img" '
            f'aria-label="TAIL {overall or "–"}" font-family="Inter, system-ui, -apple-system, \'Segoe UI\', Roboto, sans-serif" '
            f'style="max-width:{width}px">{"".join(parts)}</svg>')


def _worst_rating(ratings) -> "str | None":
    order = ("I", "II", "III", "IV")
    ratings = [r for r in ratings if r in order]
    return max(ratings, key=order.index) if ratings else None


def tail_colors(rating) -> Tuple[str, str]:
    """(background, text) colours for a TAIL rating badge."""
    return TAIL_COLORS.get(rating, TAIL_COLORS[None]), TAIL_TEXT.get(rating, TAIL_TEXT[None])


__all__ = ["stacked_bar", "category_bar", "histogram", "meter", "tail_sunburst", "tail_tree", "tail_colors", "TAIL_ORDER", "CATEGORY_COLORS", "CATEGORY_LABELS", "TAIL_COLORS"]
