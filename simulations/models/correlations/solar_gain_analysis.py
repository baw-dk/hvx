from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
import numpy as np

from core.filters.seasonal_filter import SeasonalFilter


@dataclass
class SolarGainUtilizationResult:
    """Results from solar gain utilization analysis."""

    winter_solar_gain_opportunity_hours: Optional[float]
    winter_solar_gain_opportunity_percentage: Optional[float]
    winter_avg_solar_radiation: Optional[float]
    winter_missed_heating_offset_kwh: Optional[float]

    summer_excess_solar_hours: Optional[float]
    summer_excess_solar_percentage: Optional[float]
    summer_avg_solar_radiation: Optional[float]
    summer_excess_cooling_load_kwh: Optional[float]

    annual_solar_utilization_efficiency: Optional[float]
    sample_count_winter: int
    sample_count_summer: int

    def as_dict(self) -> dict:
        return {
            "winter_solar_gain_opportunity_hours": self.winter_solar_gain_opportunity_hours,
            "winter_solar_gain_opportunity_percentage": self.winter_solar_gain_opportunity_percentage,
            "winter_avg_solar_radiation": self.winter_avg_solar_radiation,
            "winter_missed_heating_offset_kwh": self.winter_missed_heating_offset_kwh,
            "summer_excess_solar_hours": self.summer_excess_solar_hours,
            "summer_excess_solar_percentage": self.summer_excess_solar_percentage,
            "summer_avg_solar_radiation": self.summer_avg_solar_radiation,
            "summer_excess_cooling_load_kwh": self.summer_excess_cooling_load_kwh,
            "annual_solar_utilization_efficiency": self.annual_solar_utilization_efficiency,
            "sample_count_winter": self.sample_count_winter,
            "sample_count_summer": self.sample_count_summer,
        }


class SolarGainUtilizationAnalyzer:
    """
    Analyzes how effectively a building utilizes solar radiation.

    In winter:
    - Detects missed opportunities for passive solar heating (cold rooms + high solar radiation)

    In summer:
    - Detects excessive solar gains causing overheating (hot rooms + high solar radiation)

    Calculates estimated energy impacts of poor solar management.
    """

    def __init__(
        self,
        temperature_band: tuple[float, float] = (20.0, 24.0),
        solar_high_threshold: float = 300.0,  # W/m²
        solar_medium_threshold: float = 150.0,  # W/m²
        window_area_m2: float = 10.0,  # Default window area for energy calculations
        solar_heat_gain_coefficient: float = 0.6,  # SHGC for typical windows
    ) -> None:
        """
        Initialize solar gain utilization analyzer.

        Args:
            temperature_band: Acceptable temperature range (°C)
            solar_high_threshold: High solar radiation threshold (W/m²)
            solar_medium_threshold: Medium solar radiation threshold (W/m²)
            window_area_m2: Approximate window area for energy calculations
            solar_heat_gain_coefficient: SHGC for energy calculations
        """
        self.temperature_band = temperature_band
        self.solar_high_threshold = solar_high_threshold
        self.solar_medium_threshold = solar_medium_threshold
        self.window_area_m2 = window_area_m2
        self.shgc = solar_heat_gain_coefficient

    def analyze(self, df: pd.DataFrame, window_area_m2: Optional[float] = None) -> SolarGainUtilizationResult:
        """
        Analyze solar gain utilization patterns.

        Args:
            df: DataFrame with DatetimeIndex, 'temperature', and solar radiation column
            window_area_m2: Optional window area override for energy calculations

        Returns:
            SolarGainUtilizationResult with utilization metrics
        """
        if window_area_m2 is not None:
            self.window_area_m2 = window_area_m2

        # Check for required columns
        solar_col = None
        for col in ["solar_radiation", "solar_irradiance"]:
            if col in df.columns:
                solar_col = col
                break

        if "temperature" not in df or solar_col is None or df.empty:
            return SolarGainUtilizationResult(
                winter_solar_gain_opportunity_hours=None,
                winter_solar_gain_opportunity_percentage=None,
                winter_avg_solar_radiation=None,
                winter_missed_heating_offset_kwh=None,
                summer_excess_solar_hours=None,
                summer_excess_solar_percentage=None,
                summer_avg_solar_radiation=None,
                summer_excess_cooling_load_kwh=None,
                annual_solar_utilization_efficiency=None,
                sample_count_winter=0,
                sample_count_summer=0,
            )

        # Ensure DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            df = df.copy()
            df.index = pd.to_datetime(df.index)

        # Filter winter and summer data
        winter_filter = SeasonalFilter("winter")
        summer_filter = SeasonalFilter("summer")

        winter_df = winter_filter.apply(df)
        summer_df = summer_filter.apply(df)

        # Analyze winter solar opportunities
        winter_results = self._analyze_winter_solar_opportunity(winter_df, solar_col)

        # Analyze summer excess solar
        summer_results = self._analyze_summer_excess_solar(summer_df, solar_col)

        # Calculate annual utilization efficiency
        efficiency = self._calculate_utilization_efficiency(winter_results, summer_results)

        return SolarGainUtilizationResult(
            winter_solar_gain_opportunity_hours=winter_results["opportunity_hours"],
            winter_solar_gain_opportunity_percentage=winter_results["opportunity_percentage"],
            winter_avg_solar_radiation=winter_results["avg_solar"],
            winter_missed_heating_offset_kwh=winter_results["missed_energy_kwh"],
            summer_excess_solar_hours=summer_results["excess_hours"],
            summer_excess_solar_percentage=summer_results["excess_percentage"],
            summer_avg_solar_radiation=summer_results["avg_solar"],
            summer_excess_cooling_load_kwh=summer_results["excess_energy_kwh"],
            annual_solar_utilization_efficiency=efficiency,
            sample_count_winter=winter_results["sample_count"],
            sample_count_summer=summer_results["sample_count"],
        )

    def _analyze_winter_solar_opportunity(self, winter_df: pd.DataFrame, solar_col: str) -> dict:
        """
        Analyze missed solar heating opportunities in winter.

        Detects: High solar radiation when room is below temperature band.
        """
        if winter_df.empty or "temperature" not in winter_df or solar_col not in winter_df:
            return {
                "opportunity_hours": None,
                "opportunity_percentage": None,
                "avg_solar": None,
                "missed_energy_kwh": None,
                "sample_count": 0,
            }

        temp = winter_df["temperature"]
        solar = winter_df[solar_col]

        lower_temp, _ = self.temperature_band

        # Opportunity: Room is cold AND solar radiation is available
        cold_mask = temp < lower_temp
        high_solar_mask = solar > self.solar_medium_threshold
        opportunity_mask = cold_mask & high_solar_mask

        opportunity_count = opportunity_mask.sum()
        total_count = len(temp)

        # Calculate hours
        if len(winter_df) > 1:
            time_diff = (winter_df.index[1] - winter_df.index[0]).total_seconds()
            hours_per_sample = time_diff / 3600.0
        else:
            hours_per_sample = 1.0

        opportunity_hours = float(opportunity_count * hours_per_sample)
        opportunity_percentage = float((opportunity_count / total_count) * 100.0) if total_count > 0 else 0.0

        # Calculate missed heating energy offset
        # Energy = Solar radiation * Window area * SHGC * Time
        missed_energy_kwh = None
        if opportunity_count > 0:
            missed_solar_energy = solar[opportunity_mask].sum() * self.window_area_m2 * self.shgc * hours_per_sample
            missed_energy_kwh = float(missed_solar_energy / 1000.0)  # Convert W*h to kWh

        return {
            "opportunity_hours": opportunity_hours,
            "opportunity_percentage": opportunity_percentage,
            "avg_solar": float(solar.mean()) if len(solar) > 0 else None,
            "missed_energy_kwh": missed_energy_kwh,
            "sample_count": total_count,
        }

    def _analyze_summer_excess_solar(self, summer_df: pd.DataFrame, solar_col: str) -> dict:
        """
        Analyze excess solar gains in summer.

        Detects: High solar radiation when room is above temperature band.
        """
        if summer_df.empty or "temperature" not in summer_df or solar_col not in summer_df:
            return {
                "excess_hours": None,
                "excess_percentage": None,
                "avg_solar": None,
                "excess_energy_kwh": None,
                "sample_count": 0,
            }

        temp = summer_df["temperature"]
        solar = summer_df[solar_col]

        _, upper_temp = self.temperature_band

        # Excess: Room is hot AND solar radiation is high
        hot_mask = temp > upper_temp
        high_solar_mask = solar > self.solar_medium_threshold
        excess_mask = hot_mask & high_solar_mask

        excess_count = excess_mask.sum()
        total_count = len(temp)

        # Calculate hours
        if len(summer_df) > 1:
            time_diff = (summer_df.index[1] - summer_df.index[0]).total_seconds()
            hours_per_sample = time_diff / 3600.0
        else:
            hours_per_sample = 1.0

        excess_hours = float(excess_count * hours_per_sample)
        excess_percentage = float((excess_count / total_count) * 100.0) if total_count > 0 else 0.0

        # Calculate excess cooling load
        excess_energy_kwh = None
        if excess_count > 0:
            excess_solar_energy = solar[excess_mask].sum() * self.window_area_m2 * self.shgc * hours_per_sample
            excess_energy_kwh = float(excess_solar_energy / 1000.0)  # Convert W*h to kWh

        return {
            "excess_hours": excess_hours,
            "excess_percentage": excess_percentage,
            "avg_solar": float(solar.mean()) if len(solar) > 0 else None,
            "excess_energy_kwh": excess_energy_kwh,
            "sample_count": total_count,
        }

    def _calculate_utilization_efficiency(self, winter_results: dict, summer_results: dict) -> Optional[float]:
        """
        Calculate overall solar utilization efficiency score (0-100).

        Higher score = better solar management
        - In winter: capturing solar gains when cold
        - In summer: blocking solar gains when hot
        """
        winter_opp_pct = winter_results.get("opportunity_percentage")
        summer_excess_pct = summer_results.get("excess_percentage")

        if winter_opp_pct is None and summer_excess_pct is None:
            return None

        # Efficiency = 100 - average of problems
        winter_problem = winter_opp_pct if winter_opp_pct is not None else 0.0
        summer_problem = summer_excess_pct if summer_excess_pct is not None else 0.0

        # Weight by sample count
        winter_count = winter_results.get("sample_count", 0)
        summer_count = summer_results.get("sample_count", 0)
        total_count = winter_count + summer_count

        if total_count == 0:
            return None

        weighted_problem = (winter_problem * winter_count + summer_problem * summer_count) / total_count
        efficiency = max(0.0, 100.0 - weighted_problem)

        return float(efficiency)
