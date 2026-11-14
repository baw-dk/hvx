# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
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
    metrics: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "metrics": self.metrics,
        }


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


class ScenarioImpactModel:
    """
    Simple scenario calculator that estimates the benefit of common retrofits.

    The current version implements two universal scenarios:
      1. Increasing ventilation rate by +1 ACH and estimating CO2 compliance.
      2. Applying dynamic solar shading (up to -1.5 °C when solar > 300 W/m²).
    """

    def __init__(
        self,
        temp_band: tuple[float, float] = (20.0, 24.0),
        co2_threshold: float = 1200.0,
        solar_medium: float = 150.0,
        solar_high: float = 300.0,
        max_temp_drop: float = 1.5,
    ) -> None:
        self.temp_band = temp_band
        self.co2_threshold = co2_threshold
        self.solar_medium = solar_medium
        self.solar_high = solar_high
        self.max_temp_drop = max_temp_drop

    @staticmethod
    def _compliance_percentage(mask: pd.Series) -> Optional[float]:
        if mask is None or len(mask) == 0:
            return None
        return float((~mask).mean() * 100.0)

    def _temperature_compliance(self, df: pd.DataFrame) -> Optional[float]:
        if "temperature" not in df:
            return None
        lower, upper = self.temp_band
        mask = (df["temperature"] < lower) | (df["temperature"] > upper)
        return self._compliance_percentage(mask)

    def _co2_compliance(self, df: pd.DataFrame) -> Optional[float]:
        if "co2" not in df:
            return None
        mask = df["co2"] > self.co2_threshold
        return self._compliance_percentage(mask)

    def _ventilation_scenario(
        self,
        df: pd.DataFrame,
        ventilation_result: Optional[VentilationRateResult],
    ) -> Optional[ScenarioResult]:
        if ventilation_result is None or "co2" not in df:
            return None

        current = max(ventilation_result.ach, 0.1)
        target = current + 1.0
        scale = current / target
        outdoor = ventilation_result.outdoor_co2

        adjusted = outdoor + (df["co2"] - outdoor) * scale
        mask = adjusted > self.co2_threshold
        compliance = self._compliance_percentage(mask)

        baseline = self._co2_compliance(df)
        improvement = None
        if compliance is not None and baseline is not None:
            improvement = compliance - baseline

        return ScenarioResult(
            name="Ventilation Boost",
            description="Increase supply airflow (+1 ACH).",
            metrics={
                "target_ach": round(target, 2),
                "co2_compliance_after": round(compliance, 2) if compliance is not None else None,
                "co2_compliance_gain": round(improvement, 2) if improvement is not None else None,
            },
        )

    def _solar_shading_scenario(self, df: pd.DataFrame) -> Optional[ScenarioResult]:
        if "temperature" not in df or ("solar_radiation" not in df and "solar_irradiance" not in df):
            return None

        solar = df.get("solar_radiation") if df.get("solar_radiation") is not None else df.get("solar_irradiance")
        reduction = np.where(
            solar > self.solar_high,
            self.max_temp_drop,
            np.where(solar > self.solar_medium, self.max_temp_drop / 2, 0.0),
        )
        shaded_temp = df["temperature"] - reduction
        lower, upper = self.temp_band
        mask = (shaded_temp < lower) | (shaded_temp > upper)
        compliance = self._compliance_percentage(pd.Series(mask, index=df.index))

        baseline = self._temperature_compliance(df)
        improvement = None
        if compliance is not None and baseline is not None:
            improvement = compliance - baseline

        return ScenarioResult(
            name="Dynamic Solar Shading",
            description="Apply automated external shading when radiation spikes.",
            metrics={
                "temp_compliance_after": round(compliance, 2) if compliance is not None else None,
                "temp_compliance_gain": round(improvement, 2) if improvement is not None else None,
                "max_temp_drop_c": self.max_temp_drop,
            },
        )

    def estimate_impacts(
        self,
        df: pd.DataFrame,
        ventilation_result: Optional[VentilationRateResult],
    ) -> ScenarioImpactSummary:
        return ScenarioImpactSummary(
            base_temperature_compliance=self._temperature_compliance(df),
            base_co2_compliance=self._co2_compliance(df),
            ventilation=self._ventilation_scenario(df, ventilation_result),
            solar_shading=self._solar_shading_scenario(df),
        )
