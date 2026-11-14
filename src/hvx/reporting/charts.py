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
                    f'class="bar-label">{pct:.0f}%</text>'
                )
            x += w
    else:
        parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="var(--cat-none)" opacity="0.4"/>')
    aria = escape(title or ", ".join(f"{label} {value:g}" for label, value, _ in segments))
    return (
        f'<svg class="chart stacked" viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'role="img" aria-label="{aria}">{"".join(parts)}</svg>'
    )


def category_bar(counts: dict, width: int = 600, height: int = 22) -> str:
    segments = [(CATEGORY_LABELS[c], float(counts.get(c, 0)), CATEGORY_COLORS[c]) for c in ("I", "II", "III", "IV", "none")]
    return stacked_bar(segments, width=width, height=height, title="Rooms by EN 16798-1 category")


def histogram(bins: Sequence[int], width: int = 600, height: int = 180, title: str = "Rooms by IEQ score") -> str:
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
            f'fill="{color}" rx="2"><title>{i * 10}–{i * 10 + 10}: {count} room(s)</title></rect>'
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


__all__ = ["stacked_bar", "category_bar", "histogram", "meter", "CATEGORY_COLORS", "CATEGORY_LABELS"]
