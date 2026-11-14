# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""JSON and CSV renderers."""

from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Union

from ..model import IEQ_PARAMETERS, PortfolioReport

CSV_COLUMNS = [
    "building_id", "building_name", "floor_id", "floor_name", "room_id", "room_name", "room_type",
    "area_m2", "status", "target_category", "achieved_category", "meets_target", "ieq_score",
    *[f"{p}_compliance_pct" for p in IEQ_PARAMETERS],
    *[f"{p}_mean" for p in IEQ_PARAMETERS],
    "co2_gt1000_h", "co2_gt2000_h", "temperature_gt26_h", "temperature_gt27_h", "occupied_hours", "occupancy",
    "tail_rating", "br18_pass", "br18_failed", "below_category_iv", "completeness_pct", "samples", "period_start", "period_end",
    "issues", "brick_class", "ifc_guid",
]


def _clean(value: Any) -> Any:
    """Make values JSON-safe (NaN/inf -> null)."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def report_to_dict(report: PortfolioReport) -> Dict[str, Any]:
    return _clean(report.to_dict())


def render_json(report: PortfolioReport, indent: int = 2) -> str:
    return json.dumps(report_to_dict(report), indent=indent, ensure_ascii=False, default=str)


def room_rows(report: PortfolioReport) -> List[Dict[str, Any]]:
    rows = []
    for r in report.rooms:
        dq = r.data_quality or {}
        row = {
            "building_id": r.building_id, "building_name": r.building_name,
            "floor_id": r.floor_id, "floor_name": r.floor_name,
            "room_id": r.room_id, "room_name": r.room_name, "room_type": r.room_type,
            "area_m2": r.area_m2, "status": r.status, "target_category": r.target_category,
            "achieved_category": r.achieved_category, "meets_target": r.meets_target, "ieq_score": r.ieq_score,
            "tail_rating": r.tail_rating, "br18_pass": r.br18_pass, "br18_failed": " | ".join(r.br18_failed),
            "below_category_iv": r.below_category_iv, "occupancy": r.occupancy,
            "occupied_hours": dq.get("occupied_hours"),
            **{f"{k.replace('>', '_gt')}_h": v for k, v in r.exceedance_hours.items()},
            "completeness_pct": dq.get("completeness_pct"), "samples": dq.get("samples"),
            "period_start": dq.get("start"), "period_end": dq.get("end"),
            "issues": " | ".join(r.issues), "brick_class": r.brick_class, "ifc_guid": r.ifc_guid,
        }
        for p in IEQ_PARAMETERS:
            summary = r.parameters.get(p)
            row[f"{p}_compliance_pct"] = r.compliance.get(p)
            row[f"{p}_mean"] = summary.mean if summary else None
        rows.append(row)
    return rows


def render_csv(report: PortfolioReport) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in room_rows(report):
        writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
    return buffer.getvalue()


def write_json(report: PortfolioReport, path: Union[str, Path]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_json(report), encoding="utf-8")
    return path


def write_csv(report: PortfolioReport, path: Union[str, Path]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_csv(report), encoding="utf-8", newline="")
    return path


__all__ = ["render_json", "render_csv", "report_to_dict", "room_rows", "write_json", "write_csv", "CSV_COLUMNS"]
