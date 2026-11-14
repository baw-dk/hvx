# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
What-if estimates behind the report's recommendations. Each one states its
assumption; none uses a fixed effect that ignores the room's own data.

Airflow during use
    In a room whose CO2 comes from its occupants, the steady-state excess over the
    background is inversely proportional to the outdoor-air supply. The factor by
    which the supply during use would have to grow so that the 95th percentile of
    occupied CO2 stays at the target limit is
    ``(P95 - background) / (limit - background)``. Steady state is an assumption:
    in short lessons CO2 is still rising, so the factor is an upper estimate for
    long lessons and an order of magnitude otherwise. It needs no air change rate,
    so the after-hours decay rate (which says nothing about use) is not involved.

Solar shading
    Occupied temperatures outside the heating season are regressed on global solar
    irradiance *and* outdoor temperature (so the season does not masquerade as a
    solar effect). If the solar coefficient is clearly positive, the estimate
    removes ``shading_reduction`` (default 70 %, typical of external shading
    compared with unshaded glazing) of the measured solar response and counts the
    hours above 26 °C that remain. Without outdoor temperature no estimate is made.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
import pandas as pd

from hvx.simulations.models.ventilation import VentilationRateResult


@dataclass
class ScenarioResult:
    """Container for a what-if scenario."""

    name: str
    description: str
    metrics: Dict[str, Optional[float]] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"name": self.name, "description": self.description, "metrics": self.metrics}


@dataclass
class ScenarioImpactSummary:
    """Summary of all simulated scenarios."""

    base_temperature_compliance: Optional[float]
    base_co2_compliance: Optional[float]
    ventilation: Optional[ScenarioResult]
    solar_shading: Optional[ScenarioResult]

    def as_dict(self) -> dict:
        return {
            "base_temperature_compliance": self.base_temperature_compliance,
            "base_co2_compliance": self.base_co2_compliance,
            "ventilation": self.ventilation.as_dict() if self.ventilation else None,
            "solar_shading": self.solar_shading.as_dict() if self.solar_shading else None,
        }


def _hours(index: pd.Index) -> pd.Series:
    from hvx.standards.br18.analysis import _sample_hours

    return _sample_hours(index)


class ScenarioImpactModel:
    """Airflow-during-use and solar-shading estimates from a room's occupied data."""

    def __init__(
        self,
        co2_limit: float = 1200.0,
        temp_band: tuple = (20.0, 24.0),
        overheating_limit: float = 26.0,
        shading_reduction: float = 0.7,
        min_samples: int = 100,
        co2_threshold: Optional[float] = None,  # deprecated alias of co2_limit
    ) -> None:
        self.co2_limit = float(co2_threshold if co2_threshold is not None else co2_limit)
        self.temp_band = temp_band
        self.overheating_limit = overheating_limit
        self.shading_reduction = shading_reduction
        self.min_samples = min_samples

    def _co2_compliance(self, df: pd.DataFrame) -> Optional[float]:
        if "co2" not in df or df["co2"].dropna().empty:
            return None
        co2 = df["co2"].dropna()
        return float((co2 <= self.co2_limit).mean() * 100.0)

    def _temperature_compliance(self, df: pd.DataFrame) -> Optional[float]:
        if "temperature" not in df or df["temperature"].dropna().empty:
            return None
        t = df["temperature"].dropna()
        lower, upper = self.temp_band
        return float(((t >= lower) & (t <= upper)).mean() * 100.0)

    def airflow_scenario(self, df: pd.DataFrame, background: float) -> Optional[ScenarioResult]:
        if "co2" not in df:
            return None
        co2 = df["co2"].dropna()
        if len(co2) < 24 or self.co2_limit <= background:
            return None
        p95 = float(np.percentile(co2, 95))
        factor = (p95 - background) / (self.co2_limit - background)
        return ScenarioResult(
            name="Outdoor air during use",
            description="Steady-state estimate: excess CO₂ falls in proportion to the outdoor-air supply.",
            metrics={
                "co2_p95": round(p95, 0),
                "background_co2": round(background, 0),
                "co2_limit": self.co2_limit,
                "airflow_factor": round(factor, 2) if factor > 1.0 else None,
            },
        )

    def solar_shading_scenario(self, df: pd.DataFrame, heating: Optional[pd.Series] = None) -> Optional[ScenarioResult]:
        solar_col = next((c for c in ("solar_irradiance", "solar_radiation") if c in df), None)
        if "temperature" not in df or solar_col is None or "outdoor_temperature" not in df:
            return None
        part = df if heating is None else df[~heating.reindex(df.index).fillna(False).astype(bool)]
        data = part[["temperature", solar_col, "outdoor_temperature"]].dropna()
        if len(data) < self.min_samples:
            return None
        x = np.column_stack([np.ones(len(data)), data[solar_col].to_numpy(), data["outdoor_temperature"].to_numpy()])
        y = data["temperature"].to_numpy()
        coef, *_ = np.linalg.lstsq(x, y, rcond=None)
        residual = y - x @ coef
        dof = max(len(y) - 3, 1)
        sigma2 = float(residual @ residual) / dof
        try:
            se = np.sqrt(np.diag(sigma2 * np.linalg.inv(x.T @ x)))
        except np.linalg.LinAlgError:
            return None
        solar_k, t_stat = float(coef[1]), float(coef[1] / se[1]) if se[1] > 0 else 0.0
        hours = _hours(data.index)
        before = float(hours[data["temperature"] > self.overheating_limit].sum())
        if solar_k <= 0 or t_stat < 3.0:
            after = before
        else:
            shaded = data["temperature"] - self.shading_reduction * solar_k * data[solar_col]
            after = float(hours[shaded > self.overheating_limit].sum())
        return ScenarioResult(
            name="External solar shading",
            description=(
                "Regression of occupied temperature on solar irradiance and outdoor temperature outside the heating "
                f"season; shading assumed to remove {self.shading_reduction:.0%} of the measured solar response."
            ),
            metrics={
                "solar_k_per_100_w_m2": round(solar_k * 100.0, 2),
                "t_statistic": round(t_stat, 1),
                "samples": float(len(data)),
                "hours_above_limit_before": round(before, 0),
                "hours_above_limit_after": round(after, 0),
                "hours_avoided": round(before - after, 0),
                "shading_reduction": self.shading_reduction,
            },
        )

    def estimate_impacts(
        self,
        df: pd.DataFrame,
        ventilation_result: Optional[VentilationRateResult] = None,
        heating: Optional[pd.Series] = None,
        background_co2: Optional[float] = None,
    ) -> ScenarioImpactSummary:
        """``df``: occupied samples (incl. climate columns). ``heating``: True in heating-season
        samples. ``background_co2``: from the CO₂ decay analysis if available."""
        background = background_co2
        if background is None and ventilation_result is not None:
            background = ventilation_result.outdoor_co2
        return ScenarioImpactSummary(
            base_temperature_compliance=self._temperature_compliance(df),
            base_co2_compliance=self._co2_compliance(df),
            ventilation=self.airflow_scenario(df, float(background) if background else 420.0),
            solar_shading=self.solar_shading_scenario(df, heating),
        )


__all__ = ["ScenarioImpactModel", "ScenarioImpactSummary", "ScenarioResult"]
