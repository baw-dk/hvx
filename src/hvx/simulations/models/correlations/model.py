# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import pandas as pd

from .seasonal_thermal_analysis import SeasonalThermalAnalyzer, SeasonalThermalResult
from .solar_gain_analysis import SolarGainUtilizationAnalyzer, SolarGainUtilizationResult


@dataclass
class ClimateCorrelationResult:
    """Summaries describing how indoor conditions react to weather inputs."""

    temperature_vs_outdoor: Optional[float]
    temperature_vs_solar: Optional[float]
    co2_vs_outdoor: Optional[float]
    humidity_vs_outdoor: Optional[float]
    violation_vs_solar: Optional[float]
    sample_count: int

    # New seasonal and solar analyses
    seasonal_thermal: Optional[SeasonalThermalResult] = None
    solar_gain_utilization: Optional[SolarGainUtilizationResult] = None

    def as_dict(self) -> dict:
        result = {
            "temperature_vs_outdoor": self.temperature_vs_outdoor,
            "temperature_vs_solar": self.temperature_vs_solar,
            "co2_vs_outdoor": self.co2_vs_outdoor,
            "humidity_vs_outdoor": self.humidity_vs_outdoor,
            "violation_vs_solar": self.violation_vs_solar,
            "samples": self.sample_count,
        }

        if self.seasonal_thermal is not None:
            result["seasonal_thermal"] = self.seasonal_thermal.as_dict()

        if self.solar_gain_utilization is not None:
            result["solar_gain_utilization"] = self.solar_gain_utilization.as_dict()

        return result


class ClimateCorrelationModel:
    """
    Compute quick correlations between indoor sensors and outdoor references.

    The model operates purely on pandas dataframes and does not depend on the
    rest of the simulation registry, which means it can run offline on cached
    room data inside the report pipeline.
    """

    def __init__(
        self,
        temperature_band: Tuple[float, float] = (20.0, 24.0),
        co2_threshold: float = 1200.0,
        enable_seasonal_analysis: bool = True,
        enable_solar_analysis: bool = True,
        window_area_m2: Optional[float] = None,
    ) -> None:
        self.temperature_band = temperature_band
        self.co2_threshold = co2_threshold
        self.enable_seasonal_analysis = enable_seasonal_analysis
        self.enable_solar_analysis = enable_solar_analysis

        # Initialize analyzers
        self.seasonal_analyzer = SeasonalThermalAnalyzer(
            temperature_band=temperature_band
        ) if enable_seasonal_analysis else None

        self.solar_analyzer = SolarGainUtilizationAnalyzer(
            temperature_band=temperature_band,
            window_area_m2=window_area_m2 or 10.0,
        ) if enable_solar_analysis else None

    @staticmethod
    def _corr(series_a: pd.Series, series_b: pd.Series) -> Optional[float]:
        if series_a is None or series_b is None:
            return None
        aligned = pd.concat([series_a, series_b], axis=1).dropna()
        if aligned.empty:
            return None
        coeff = aligned.corr().iloc[0, 1]
        return float(coeff) if pd.notna(coeff) else None

    def compute(self, df: pd.DataFrame, window_area_m2: Optional[float] = None) -> ClimateCorrelationResult:
        """
        Compute correlations for the given room dataframe.

        Args:
            df: Time-indexed dataframe containing columns such as
                temperature, co2, outdoor_temperature, solar_radiation, humidity.
            window_area_m2: Optional window area for solar gain calculations

        Returns:
            ClimateCorrelationResult with optional float correlations.
        """
        temp = df.get("temperature")
        co2 = df.get("co2")
        humidity = df.get("humidity")
        outdoor = df.get("outdoor_temperature")
        solar = df.get("solar_radiation") if df.get("solar_radiation") is not None else df.get("solar_irradiance")

        temp_vs_outdoor = self._corr(temp, outdoor)
        temp_vs_solar = self._corr(temp, solar)
        co2_vs_outdoor = self._corr(co2, outdoor)
        humidity_vs_outdoor = self._corr(humidity, outdoor)

        violation_mask = None
        if temp is not None:
            lower, upper = self.temperature_band
            violation_mask = ((temp < lower) | (temp > upper)).astype(float)

        if violation_mask is None and co2 is not None:
            violation_mask = (co2 > self.co2_threshold).astype(float)

        violation_vs_solar = None
        if violation_mask is not None and solar is not None:
            violation_vs_solar = self._corr(violation_mask, solar)

        # Run seasonal thermal analysis
        seasonal_result = None
        if self.seasonal_analyzer is not None:
            seasonal_result = self.seasonal_analyzer.analyze(df)

        # Run solar gain utilization analysis
        solar_gain_result = None
        if self.solar_analyzer is not None:
            solar_gain_result = self.solar_analyzer.analyze(df, window_area_m2)

        return ClimateCorrelationResult(
            temperature_vs_outdoor=temp_vs_outdoor,
            temperature_vs_solar=temp_vs_solar,
            co2_vs_outdoor=co2_vs_outdoor,
            humidity_vs_outdoor=humidity_vs_outdoor,
            violation_vs_solar=violation_vs_solar,
            sample_count=int(len(df)),
            seasonal_thermal=seasonal_result,
            solar_gain_utilization=solar_gain_result,
        )
