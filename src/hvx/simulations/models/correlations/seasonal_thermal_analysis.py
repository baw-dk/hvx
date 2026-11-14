# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from hvx.core.filters.seasonal_filter import SeasonalFilter


@dataclass
class SeasonalThermalResult:
    """Results from seasonal thermal comfort analysis."""

    winter_overheating_hours: Optional[float]
    winter_overheating_percentage: Optional[float]
    winter_avg_temp: Optional[float]
    winter_max_temp: Optional[float]

    summer_undercooling_hours: Optional[float]
    summer_undercooling_percentage: Optional[float]
    summer_avg_temp: Optional[float]
    summer_min_temp: Optional[float]

    sample_count_winter: int
    sample_count_summer: int

    def as_dict(self) -> dict:
        return {
            "winter_overheating_hours": self.winter_overheating_hours,
            "winter_overheating_percentage": self.winter_overheating_percentage,
            "winter_avg_temp": self.winter_avg_temp,
            "winter_max_temp": self.winter_max_temp,
            "summer_undercooling_hours": self.summer_undercooling_hours,
            "summer_undercooling_percentage": self.summer_undercooling_percentage,
            "summer_avg_temp": self.summer_avg_temp,
            "summer_min_temp": self.summer_min_temp,
            "sample_count_winter": self.sample_count_winter,
            "sample_count_summer": self.sample_count_summer,
        }


class SeasonalThermalAnalyzer:
    """
    Analyzes thermal comfort issues specific to seasons.

    Detects:
    - Winter overheating (heating system too aggressive or poor control)
    - Summer undercooling (insufficient cooling or poor ventilation)
    """

    def __init__(
        self,
        temperature_band: tuple[float, float] = (20.0, 24.0),
        winter_overheating_threshold: float = 23.0,
        summer_undercooling_threshold: float = 21.0,
    ) -> None:
        """
        Initialize seasonal thermal analyzer.

        Args:
            temperature_band: Acceptable temperature range (°C)
            winter_overheating_threshold: Temperature above which winter overheating occurs (°C)
            summer_undercooling_threshold: Temperature below which summer undercooling occurs (°C)
        """
        self.temperature_band = temperature_band
        self.winter_overheating_threshold = winter_overheating_threshold
        self.summer_undercooling_threshold = summer_undercooling_threshold

    def analyze(self, df: pd.DataFrame) -> SeasonalThermalResult:
        """
        Analyze seasonal thermal patterns.

        Args:
            df: DataFrame with DatetimeIndex and 'temperature' column

        Returns:
            SeasonalThermalResult with seasonal metrics
        """
        if "temperature" not in df or df.empty:
            return SeasonalThermalResult(
                winter_overheating_hours=None,
                winter_overheating_percentage=None,
                winter_avg_temp=None,
                winter_max_temp=None,
                summer_undercooling_hours=None,
                summer_undercooling_percentage=None,
                summer_avg_temp=None,
                summer_min_temp=None,
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

        # Analyze winter overheating
        winter_results = self._analyze_winter_overheating(winter_df)

        # Analyze summer undercooling
        summer_results = self._analyze_summer_undercooling(summer_df)

        return SeasonalThermalResult(
            winter_overheating_hours=winter_results["overheating_hours"],
            winter_overheating_percentage=winter_results["overheating_percentage"],
            winter_avg_temp=winter_results["avg_temp"],
            winter_max_temp=winter_results["max_temp"],
            summer_undercooling_hours=summer_results["undercooling_hours"],
            summer_undercooling_percentage=summer_results["undercooling_percentage"],
            summer_avg_temp=summer_results["avg_temp"],
            summer_min_temp=summer_results["min_temp"],
            sample_count_winter=winter_results["sample_count"],
            sample_count_summer=summer_results["sample_count"],
        )

    def _analyze_winter_overheating(self, winter_df: pd.DataFrame) -> dict:
        """Analyze winter overheating patterns."""
        if winter_df.empty or "temperature" not in winter_df:
            return {
                "overheating_hours": None,
                "overheating_percentage": None,
                "avg_temp": None,
                "max_temp": None,
                "sample_count": 0,
            }

        temp = winter_df["temperature"]
        overheating_mask = temp > self.winter_overheating_threshold

        # Calculate hours (assuming hourly data, otherwise estimate)
        overheating_count = overheating_mask.sum()
        total_count = len(temp)

        # Estimate granularity for hour calculation
        if len(winter_df) > 1:
            time_diff = (winter_df.index[1] - winter_df.index[0]).total_seconds()
            hours_per_sample = time_diff / 3600.0
        else:
            hours_per_sample = 1.0

        overheating_hours = float(overheating_count * hours_per_sample)
        overheating_percentage = float((overheating_count / total_count) * 100.0) if total_count > 0 else 0.0

        return {
            "overheating_hours": overheating_hours,
            "overheating_percentage": overheating_percentage,
            "avg_temp": float(temp.mean()),
            "max_temp": float(temp.max()),
            "sample_count": total_count,
        }

    def _analyze_summer_undercooling(self, summer_df: pd.DataFrame) -> dict:
        """Analyze summer undercooling patterns."""
        if summer_df.empty or "temperature" not in summer_df:
            return {
                "undercooling_hours": None,
                "undercooling_percentage": None,
                "avg_temp": None,
                "min_temp": None,
                "sample_count": 0,
            }

        temp = summer_df["temperature"]
        undercooling_mask = temp < self.summer_undercooling_threshold

        # Calculate hours
        undercooling_count = undercooling_mask.sum()
        total_count = len(temp)

        # Estimate granularity for hour calculation
        if len(summer_df) > 1:
            time_diff = (summer_df.index[1] - summer_df.index[0]).total_seconds()
            hours_per_sample = time_diff / 3600.0
        else:
            hours_per_sample = 1.0

        undercooling_hours = float(undercooling_count * hours_per_sample)
        undercooling_percentage = float((undercooling_count / total_count) * 100.0) if total_count > 0 else 0.0

        return {
            "undercooling_hours": undercooling_hours,
            "undercooling_percentage": undercooling_percentage,
            "avg_temp": float(temp.mean()),
            "min_temp": float(temp.min()),
            "sample_count": total_count,
        }
