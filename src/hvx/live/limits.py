"""
Instantaneous EN 16798-1 limits for live checks.

Read from the same ``standards/en16798/config.yaml`` the batch assessment uses,
so a live "CO₂ above Category II" alert and the report can never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Optional, Tuple

from hvx.core.semantics.ieq import IEQRequirements

CATEGORIES = ("I", "II", "III", "IV")
Bounds = Tuple[Optional[float], Optional[float]]


@dataclass(frozen=True)
class CategoryLimits:
    """``limits[category][parameter] = (lower, upper)`` for one season."""

    season: str
    limits: Dict[str, Dict[str, Bounds]]

    def bounds(self, category: str, parameter: str) -> Optional[Bounds]:
        return self.limits.get(category, {}).get(parameter)


@lru_cache(maxsize=4)
def en16798_limits(season: str = "winter") -> CategoryLimits:
    from hvx.standards.en16798.analysis import load_config

    season = {"heating": "winter", "cooling": "summer"}.get(season, season)
    out: Dict[str, Dict[str, Bounds]] = {}
    for ruleset in load_config().get("rulesets", []):
        cat = str(ruleset.get("category"))
        for rule in ruleset.get("rules", []):
            rule_season = rule.get("season")
            if rule_season and rule_season != season:
                continue
            metric = rule.get("metric")
            op = rule.get("operator")
            if op == "between":
                bounds: Bounds = (rule.get("lower_bound"), rule.get("upper_bound"))
            elif op in ("<=", "<"):
                bounds = (None, rule.get("target_value"))
            elif op in (">=", ">"):
                bounds = (rule.get("target_value"), None)
            else:
                continue
            out.setdefault(cat, {})[metric] = bounds
    return CategoryLimits(season=season, limits=out)


def with_requirements(limits: CategoryLimits, target: str, req: Optional[IEQRequirements]) -> CategoryLimits:
    """Override the target category's bounds with a room's own design requirements."""
    if req is None:
        return limits
    target_limits = dict(limits.limits.get(target, {}))
    season_min = req.temperature_winter_min_c if limits.season == "winter" else req.temperature_summer_min_c
    season_max = req.temperature_winter_max_c if limits.season == "winter" else req.temperature_summer_max_c
    t_lo = season_min if season_min is not None else req.temperature_min_c
    t_hi = season_max if season_max is not None else req.temperature_max_c
    if t_lo is not None or t_hi is not None:
        base = target_limits.get("temperature", (None, None))
        target_limits["temperature"] = (t_lo if t_lo is not None else base[0], t_hi if t_hi is not None else base[1])
    if req.co2_max_ppm is not None:
        target_limits["co2"] = (None, req.co2_max_ppm)
    if req.humidity_min_pct is not None or req.humidity_max_pct is not None:
        base = target_limits.get("humidity", (None, None))
        target_limits["humidity"] = (
            req.humidity_min_pct if req.humidity_min_pct is not None else base[0],
            req.humidity_max_pct if req.humidity_max_pct is not None else base[1],
        )
    return CategoryLimits(season=limits.season, limits={**limits.limits, target: target_limits})


def classify(value: float, bounds: Optional[Bounds]) -> str:
    """'ok', 'low' or 'high' against (lower, upper); 'ok' if no bounds."""
    if bounds is None:
        return "ok"
    lower, upper = bounds
    if lower is not None and value < lower:
        return "low"
    if upper is not None and value > upper:
        return "high"
    return "ok"


def category_now(values: Dict[str, float], limits: CategoryLimits) -> Optional[str]:
    """Best category whose limits all current values satisfy (None = below IV)."""
    if not values:
        return None
    for cat in CATEGORIES:
        if all(classify(v, limits.bounds(cat, p)) == "ok" for p, v in values.items() if limits.bounds(cat, p)):
            return cat
    return None


__all__ = ["CategoryLimits", "en16798_limits", "with_requirements", "classify", "category_now", "CATEGORIES"]
