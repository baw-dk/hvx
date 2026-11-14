# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Report branding.

Without branding (the default) reports are white-label: no company name, logo
or registration number anywhere. A brand adds a logo or wordmark in the header,
the company block (incl. Danish CVR number) at the end of the report and in the
PDF footer, and an accent colour.

Brands are YAML files: the built-in ones live in ``hvx/reporting/brands/``
(use them by name, e.g. ``"baw"``); any other file can be given by path.
Fields listed under ``required`` must be filled before a report renders, so a
template cannot ship with a blank CVR.
"""

from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

import yaml

BRANDS_DIR = Path(__file__).resolve().parent / "brands"
WHITE_LABEL = ("", "none", "white_label", "white-label", "whitelabel")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass
class ReportBranding:
    name: str
    legal_name: Optional[str] = None
    cvr: Optional[str] = None  # Danish company registration number (8 digits)
    address: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    logo: Optional[str] = None  # data URI (resolved from a file path when loading)
    accent: Optional[str] = None  # hex colour, e.g. "#0b5c4a"
    required: List[str] = field(default_factory=list)

    def validate(self) -> "ReportBranding":
        missing = [f for f in self.required if not str(getattr(self, f, "") or "").strip()]
        if missing:
            raise ValueError(f"Brand '{self.name}' is missing required field(s): {', '.join(missing)}")
        if self.cvr:
            digits = re.sub(r"\s", "", str(self.cvr))
            if not re.fullmatch(r"\d{8}", digits):
                raise ValueError(f"CVR number must be 8 digits, got {self.cvr!r}")
            self.cvr = digits
        if self.accent and not _HEX.match(self.accent):
            raise ValueError(f"accent must be a #rrggbb colour, got {self.accent!r}")
        return self

    @property
    def company_line(self) -> List[str]:
        """Company details in display order, empty fields left out."""
        return [x for x in (self.legal_name or self.name, self.address, self.email, self.phone, self.website) if x]


def _logo_data_uri(value: Optional[str], base: Path) -> Optional[str]:
    if not value:
        return None
    if value.startswith("data:"):
        return value
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def available_brands() -> List[str]:
    """Names of the built-in brands (usable as ``ReportConfig(branding=name)``)."""
    return sorted(p.stem for p in BRANDS_DIR.glob("*.yaml"))


def load_brand(brand: Union[None, str, Path, ReportBranding]) -> Optional[ReportBranding]:
    """``None``/"white_label" -> no branding; a built-in name or a YAML path -> validated brand."""
    if brand is None or isinstance(brand, ReportBranding):
        return brand.validate() if isinstance(brand, ReportBranding) else None
    text = str(brand).strip()
    if text.lower() in WHITE_LABEL:
        return None
    path = Path(text)
    if not path.suffix:
        path = BRANDS_DIR / f"{text.lower()}.yaml"
    if not path.exists():
        raise ValueError(f"Unknown brand {text!r}; built-in brands: {available_brands()}, or give a YAML file path")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data = {k: (v.strip() if isinstance(v, str) else v) or None for k, v in data.items() if k in ReportBranding.__dataclass_fields__}
    data["required"] = list(data.get("required") or [])
    data["logo"] = _logo_data_uri(data.get("logo"), path.parent)
    return ReportBranding(**data).validate()


__all__ = ["ReportBranding", "load_brand", "available_brands", "BRANDS_DIR", "WHITE_LABEL"]
