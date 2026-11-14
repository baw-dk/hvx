# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
PDF renderer: prints the HTML report with headless Chromium (Playwright).

Chromium renders the report's CSS, inline SVG charts and print styles
exactly as a browser does. Needs the ``pdf`` extra and a Chromium build::

    pip install "hvx[pdf]"
    playwright install chromium        # or set HVX_CHROMIUM_PATH to an existing Chromium
"""

from __future__ import annotations

import os
from html import escape
from pathlib import Path
from typing import Optional, Union

from ..i18n import Translator
from ..model import PortfolioReport
from .html import CONFIG_BRAND, render_html, resolve_brand

FOOTER = (
    '<div style="font-size:7.5px;width:100%;margin:0 12mm;color:#6b7280;'
    'font-family:system-ui,sans-serif;display:flex;justify-content:space-between;gap:12px">'
    "<span>{left}</span>{middle}"
    '<span style="white-space:nowrap">{page} <span class="pageNumber"></span> {of} <span class="totalPages"></span></span></div>'
)


def _footer(report: PortfolioReport, t: Translator, brand) -> str:
    """White-label: report title and page. Branded: company and CVR number, title, page."""
    title = escape(report.portfolio_name)
    if brand:
        company = brand.legal_name or brand.name
        if brand.cvr:
            company = f"{company} · {t('CVR no. {cvr}', cvr=brand.cvr)}"
        left, middle = escape(company), f"<span>{title}</span>"
    else:
        left, middle = title, ""
    return FOOTER.format(
        left=left, middle=middle, page="Side" if t.language == "da" else "Page", of="af" if t.language == "da" else "of"
    )


def render_pdf(report: PortfolioReport, executable_path: Optional[str] = None, brand=CONFIG_BRAND) -> bytes:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError('PDF output needs Playwright: pip install "hvx[pdf]" && playwright install chromium') from exc

    t = Translator(report.config.get("language", "en"))
    brand = resolve_brand(report, brand)
    html = render_html(report, brand)
    footer = _footer(report, t, brand)
    executable_path = executable_path or os.environ.get("HVX_CHROMIUM_PATH") or None
    with sync_playwright() as p:
        browser = p.chromium.launch(**({"executable_path": executable_path} if executable_path else {}))
        try:
            page = browser.new_page()
            page.emulate_media(media="print", color_scheme="light")
            page.set_content(html, wait_until="load")
            # Collapsed sections (recommendations, all rooms) belong in the printed report.
            page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
            return page.pdf(
                format="A4",
                print_background=True,
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=footer,
                margin={"top": "14mm", "bottom": "16mm", "left": "12mm", "right": "12mm"},
            )
        finally:
            browser.close()


def write_pdf(report: PortfolioReport, path: Union[str, Path], executable_path: Optional[str] = None, brand=CONFIG_BRAND) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_pdf(report, executable_path, brand))
    return path


__all__ = ["render_pdf", "write_pdf"]
