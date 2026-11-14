# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
TAIL ratings of a group of rooms (a building, or a portfolio) from the rooms' own ratings.

Plain Python with no pandas, so it also runs in the browser (``hvx.tail_label``).
"""
from __future__ import annotations

from typing import Dict, List, Sequence

CATEGORIES = ("I", "II", "III", "IV")

TAIL_DOMAIN_OF = {
    "temperature": "thermal", "noise": "acoustic", "reverberation_time": "acoustic",
    "illuminance": "luminous", "lux": "luminous", "daylight_factor": "luminous",
}
# hvx extensions: rated alongside TAIL but not TAIL parameters, so never part of a domain
TAIL_EXTENSIONS = frozenset({"pm10", "voc", "tvoc"})


def interim_label(ranks: Sequence[int]) -> str:
    """TAIL paper Eq. 1: mean rank of the rooms (I = 1 ... IV = 4), one decimal; 1-1.4 I,
    1.5-2.4 II, 2.5-3.4 III, 3.5-4 IV."""
    from decimal import ROUND_HALF_UP, Decimal

    mean = Decimal(sum(ranks)) / Decimal(len(ranks))
    value = float(mean.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    return "I" if value <= 1.4 else "II" if value <= 2.4 else "III" if value <= 3.4 else "IV"


def typical_tail(rooms: Sequence[Dict]) -> Dict:
    """
    TAIL rating of a group of rooms (a building, or a portfolio), by profile:

    * offices and hotels, TAIL paper (Wargocki et al. 2021) Eq. 1: per parameter the
      interim rating (mean of the rooms' ratings, binned); domain = worst parameter;
      overall = worst domain.
    * schools, TAIL for schools (Tran 2024, Fig. 10): each classroom is rated fully; per
      domain the mean of the classrooms' domain ratings (binned the same way); overall =
      worst domain. Parameter values shown are the interim ratings, for information.

    ``distribution`` counts how the rooms themselves are rated.
    """
    if not rooms:
        return {}
    profiles = [t.get("profile") for t in rooms if t.get("profile")]
    profile = max(set(profiles), key=profiles.count) if profiles else "office"
    if len(set(profiles)) > 1:
        profile = "mixed"

    def collect(key: str) -> Dict[str, List[int]]:
        values: Dict[str, List[int]] = {}
        for tail in rooms:
            for name, label in (tail.get(key) or {}).items():
                if name in TAIL_EXTENSIONS:
                    continue
                if label in CATEGORIES:
                    values.setdefault(name, []).append(CATEGORIES.index(label) + 1)
        return values

    params = {p: interim_label(v) for p, v in collect("parameters").items()}
    if profile == "school":
        domains = {d: interim_label(v) for d, v in collect("domains").items()}
        basis = "TAIL for schools (Tran 2024): mean of the classrooms' domain ratings"
    else:
        domains = {}
        for p, label in params.items():
            d = TAIL_DOMAIN_OF.get(p, "iaq")
            if d not in domains or CATEGORIES.index(label) > CATEGORIES.index(domains[d]):
                domains[d] = label
        basis = "TAIL (Wargocki et al. 2021, Eq. 1): mean of the rooms' parameter ratings"
    overall = max(domains.values(), key=CATEGORIES.index) if domains else None
    # How the rooms themselves are rated, per domain and overall: {"thermal": {"I": 3, "IV": 9}, ...}
    distribution: Dict[str, Dict[str, int]] = {}
    for tail in rooms:
        for key, label in [*(tail.get("domains") or {}).items(), ("overall", tail.get("overall"))]:
            if label in CATEGORIES:
                counts = distribution.setdefault(key, {})
                counts[label] = counts.get(label, 0) + 1
    return {"overall": overall, "domains": domains, "parameters": params, "rooms": len(rooms),
            "distribution": distribution, "profile": profile, "basis": basis}
