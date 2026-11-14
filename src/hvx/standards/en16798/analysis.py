"""
EN 16798-1 Standard Analysis Module

This module implements EN 16798-1 compliance assessment using the
refactored service architecture with RuleSet and TestRule models.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import timezone

import numpy as np
import pandas as pd
import yaml

try:
    from pythermalcomfort.models import adaptive_en
    PYTHERMALCOMFORT_AVAILABLE = True
except ImportError:
    PYTHERMALCOMFORT_AVAILABLE = False
    adaptive_en = None

from hvx.core.rules import RuleSet, TestRule, ApplicabilityCondition
from hvx.core.analysis import (
    TestResult,
    ComplianceAnalysis,
    AnalysisStatus,
    AnalysisType,
)
from hvx.core.spacial_entity import SpatialEntity
from hvx.core.enums import (
    MetricType,
    RuleOperator,
    StandardType,
    VentilationType as EntityVentilationType,
    CountryCode,
)


class EN16798Category(str, Enum):
    """EN 16798-1 indoor environment categories."""

    CATEGORY_I = "I"
    CATEGORY_II = "II"
    CATEGORY_III = "III"
    CATEGORY_IV = "IV"


DEFAULT_CATEGORY_COMPLIANCE_THRESHOLDS: Dict[EN16798Category, float] = {
    EN16798Category.CATEGORY_I: 95.0,
    EN16798Category.CATEGORY_II: 95.0,
    EN16798Category.CATEGORY_III: 90.0,
    EN16798Category.CATEGORY_IV: 85.0,
}


def get_category_threshold_from_config(
    category: EN16798Category, config_data: Dict[str, Any]
) -> float:
    """
    Derive the compliance threshold for a category based on config tolerances.

    The tolerance_percentage indicates the maximum share of time points that may
    violate the rule while still being acceptable. We convert it to a compliance
    threshold by subtracting the maximum tolerance from 100%.
    """
    max_tolerance = 0.0
    for ruleset in config_data.get("rulesets", []):
        if ruleset.get("category") != category.value:
            continue
        for rule in ruleset.get("rules", []):
            tolerance = rule.get("tolerance_percentage")
            if tolerance is None:
                continue
            max_tolerance = max(max_tolerance, float(tolerance))

    if max_tolerance > 0:
        threshold = 100.0 - max_tolerance
        # Clamp to sensible bounds to avoid invalid config from breaking analysis
        return max(0.0, min(100.0, threshold))

    return DEFAULT_CATEGORY_COMPLIANCE_THRESHOLDS.get(category, 95.0)


def build_category_threshold_map(
    categories: List[EN16798Category], config_data: Dict[str, Any]
) -> Dict[EN16798Category, float]:
    """Build a lookup of compliance thresholds for the provided categories."""
    return {cat: get_category_threshold_from_config(cat, config_data) for cat in categories}


class VentilationType(str, Enum):
    """Building ventilation types for the EN 16798 calculator."""

    MECHANICAL = "mechanical"
    NATURAL = "natural"
    MIXED_MODE = "mixed_mode"


EU_MEMBER_COUNTRY_CODES: tuple[str, ...] = (
    CountryCode.AT.value,
    CountryCode.BE.value,
    CountryCode.BG.value,
    CountryCode.HR.value,
    CountryCode.CY.value,
    CountryCode.CZ.value,
    CountryCode.DK.value,
    CountryCode.EE.value,
    CountryCode.FI.value,
    CountryCode.FR.value,
    CountryCode.DE.value,
    CountryCode.GR.value,
    CountryCode.HU.value,
    CountryCode.IE.value,
    CountryCode.IT.value,
    CountryCode.LV.value,
    CountryCode.LT.value,
    CountryCode.LU.value,
    CountryCode.MT.value,
    CountryCode.NL.value,
    CountryCode.PL.value,
    CountryCode.PT.value,
    CountryCode.RO.value,
    CountryCode.SK.value,
    CountryCode.SI.value,
    CountryCode.ES.value,
    CountryCode.SE.value,
)


def _expand_country_groups(countries: Optional[List[str]]) -> Optional[List[str]]:
    """
    Expand special tokens in the applicability country list.
    Currently supports the "EU-members" shortcut.
    """
    if not countries:
        return countries

    expanded: List[str] = []
    seen: set[str] = set()
    for entry in countries:
        if isinstance(entry, str) and entry.strip().lower() == "eu-members":
            for eu_code in EU_MEMBER_COUNTRY_CODES:
                if eu_code not in seen:
                    expanded.append(eu_code)
                    seen.add(eu_code)
            continue

        normalized = entry.value if isinstance(entry, CountryCode) else str(entry).strip()
        if not normalized or normalized in seen:
            continue
        expanded.append(normalized)
        seen.add(normalized)

    return expanded


class PollutionLevel(str, Enum):
    """Building pollution level for ventilation calculations."""

    VERY_LOW = "very_low"
    LOW = "low"
    NON_LOW = "non_low"

    @property
    def emission_factor(self) -> float:
        """Get building emission factor in L/(s·m²)."""
        factors = {
            "very_low": 0.0,
            "low": 0.5,
            "non_low": 1.0,
        }
        return factors[self.value]


@dataclass
class EN16798Thresholds:
    """Complete thresholds for a specific EN 16798-1 category."""

    category: EN16798Category
    temperature_heating: Dict[str, float]
    temperature_cooling: Dict[str, float]
    co2_ppm: float
    humidity_lower: float
    humidity_upper: float
    ventilation_per_person_l_s: float
    ventilation_per_area_l_s_m2: float


@dataclass
class EN16798ComplianceResult:
    """Results of EN 16798-1 compliance assessment."""

    achieved_category: Optional[EN16798Category]
    all_compliant_categories: List[EN16798Category]
    compliance_by_category: Dict[EN16798Category, Dict[str, Any]]
    thresholds_used: Dict[EN16798Category, EN16798Thresholds]
    season: str
    adaptive_model_used: bool


@dataclass
class EN16798DetailedResult:
    """
    Detailed EN 16798-1 analysis results with comprehensive metrics.

    Includes time-in-category breakdown, violation details, and
    parameter-by-parameter analysis.
    """

    achieved_category: Optional[EN16798Category]
    all_compliant_categories: List[EN16798Category]
    overall_compliance_rate: float

    time_in_category_I_pct: float
    time_in_category_II_pct: float
    time_in_category_III_pct: float
    time_in_category_IV_pct: float
    time_out_of_all_categories_pct: float

    total_data_points: int
    valid_data_points: int

    temperature_metrics: Optional[Dict[str, Any]] = None
    co2_metrics: Optional[Dict[str, Any]] = None
    humidity_metrics: Optional[Dict[str, Any]] = None

    violations: Optional[List[Dict[str, Any]]] = None
    total_violations: int = 0

    season: str = "heating"
    adaptive_model_used: bool = False
    outdoor_running_mean_temp: Optional[float] = None
    ventilation_type: str = "mechanical"

    analysis_timestamp: Optional[str] = None

    def __post_init__(self) -> None:
        """Initialize default values for mutable fields."""
        if self.violations is None:
            self.violations = []
        if self.temperature_metrics is None:
            self.temperature_metrics = {}
        if self.co2_metrics is None:
            self.co2_metrics = {}
        if self.humidity_metrics is None:
            self.humidity_metrics = {}


@dataclass
class EN16798ParameterMetrics:
    """Detailed metrics for a single parameter."""

    parameter_name: str
    mean_value: float
    min_value: float
    max_value: float
    std_dev: float

    category_I_compliance_rate: float
    category_II_compliance_rate: float
    category_III_compliance_rate: float
    category_IV_compliance_rate: float

    time_above_threshold_pct: float
    time_below_threshold_pct: float
    max_exceedance: float

    thresholds_by_category: Optional[Dict[str, Dict[str, Any]]] = None

    def __post_init__(self) -> None:
        """Initialize default values."""
        if self.thresholds_by_category is None:
            self.thresholds_by_category = {}


@dataclass
class VentilationRequirement:
    """Calculated ventilation requirements."""

    total_ventilation_l_s: float
    ventilation_per_person_l_s: float
    ventilation_per_area_l_s_m2: float
    occupant_contribution_l_s: float
    building_contribution_l_s: float
    air_change_rate_ach: Optional[float]
    category: EN16798Category


class EN16798Calculator:
    """
    Complete EN 16798-1 calculator for indoor environmental assessment.

    Provides temperature thresholds, CO2 limits, humidity thresholds,
    ventilation requirements, and category compliance logic.
    """

    TEMP_HEATING = {
        EN16798Category.CATEGORY_I: {"lower": 21.0, "upper": 23.0, "design": 22.0},
        EN16798Category.CATEGORY_II: {"lower": 20.0, "upper": 24.0, "design": 22.0},
        EN16798Category.CATEGORY_III: {"lower": 19.0, "upper": 25.0, "design": 22.0},
        EN16798Category.CATEGORY_IV: {"lower": 17.0, "upper": 27.0, "design": 22.0},
    }

    TEMP_COOLING = {
        EN16798Category.CATEGORY_I: {"lower": 23.5, "upper": 25.5, "design": 24.5},
        EN16798Category.CATEGORY_II: {"lower": 23.0, "upper": 26.0, "design": 24.5},
        EN16798Category.CATEGORY_III: {"lower": 22.0, "upper": 27.0, "design": 24.5},
        EN16798Category.CATEGORY_IV: {"lower": 20.0, "upper": 29.0, "design": 24.5},
    }

    ADAPTIVE_TEMP_DEVIATION = {
        EN16798Category.CATEGORY_I: 2.0,
        EN16798Category.CATEGORY_II: 3.0,
        EN16798Category.CATEGORY_III: 4.0,
        EN16798Category.CATEGORY_IV: 5.0,
    }

    CO2_ABOVE_OUTDOOR = {
        EN16798Category.CATEGORY_I: 550,
        EN16798Category.CATEGORY_II: 800,
        EN16798Category.CATEGORY_III: 1350,
        EN16798Category.CATEGORY_IV: 1350,
    }

    HUMIDITY = {
        EN16798Category.CATEGORY_I: {"lower": 30, "upper": 50},
        EN16798Category.CATEGORY_II: {"lower": 25, "upper": 60},
        EN16798Category.CATEGORY_III: {"lower": 20, "upper": 70},
        EN16798Category.CATEGORY_IV: {"lower": 15, "upper": 80},
    }

    VENTILATION_PER_PERSON = {
        EN16798Category.CATEGORY_I: 10,
        EN16798Category.CATEGORY_II: 7,
        EN16798Category.CATEGORY_III: 4,
        EN16798Category.CATEGORY_IV: 4,
    }

    OUTDOOR_CO2 = 400.0

    @classmethod
    def get_temperature_thresholds(
        cls,
        category: EN16798Category,
        season: str = "heating",
        outdoor_running_mean_temp: Optional[float] = None,
        ventilation_type: VentilationType = VentilationType.MECHANICAL,
    ) -> Dict[str, float]:
        """Get temperature thresholds for a category."""
        if (
            ventilation_type in [VentilationType.NATURAL, VentilationType.MIXED_MODE]
            and outdoor_running_mean_temp is not None
            and 10.0 <= outdoor_running_mean_temp <= 30.0
        ):
            return cls._get_adaptive_temperature_thresholds(category, outdoor_running_mean_temp)

        if season.lower() == "cooling":
            return cls.TEMP_COOLING[category].copy()
        return cls.TEMP_HEATING[category].copy()

    @classmethod
    def _get_adaptive_temperature_thresholds(
        cls,
        category: EN16798Category,
        outdoor_running_mean_temp: float,
    ) -> Dict[str, Any]:
        """Calculate adaptive comfort thresholds."""
        t_comf = 0.33 * outdoor_running_mean_temp + 18.8

        if PYTHERMALCOMFORT_AVAILABLE and adaptive_en is not None:
            try:
                result = adaptive_en(
                    tdb=t_comf,
                    tr=t_comf,
                    t_running_mean=outdoor_running_mean_temp,
                    v=0.1,
                )

                def to_scalar(val: Any) -> float:
                    if isinstance(val, (list, np.ndarray)):
                        return float(val[0]) if len(val) > 0 else 0.0
                    return float(val)

                if category == EN16798Category.CATEGORY_I:
                    lower = to_scalar(result.tmp_cmf_cat_i_low)
                    upper = to_scalar(result.tmp_cmf_cat_i_up)
                elif category == EN16798Category.CATEGORY_II:
                    lower = to_scalar(result.tmp_cmf_cat_ii_low)
                    upper = to_scalar(result.tmp_cmf_cat_ii_up)
                elif category == EN16798Category.CATEGORY_III:
                    lower = to_scalar(result.tmp_cmf_cat_iii_low)
                    upper = to_scalar(result.tmp_cmf_cat_iii_up)
                else:
                    deviation = cls.ADAPTIVE_TEMP_DEVIATION[category]
                    lower = t_comf - deviation
                    upper = t_comf + deviation

                return {
                    "lower": round(lower, 1),
                    "upper": round(upper, 1),
                    "design": round(to_scalar(result.tmp_cmf), 1),
                    "outdoor_running_mean": round(outdoor_running_mean_temp, 1),
                    "adaptive_model": True,
                }
            except Exception:
                pass

        deviation = cls.ADAPTIVE_TEMP_DEVIATION[category]
        return {
            "lower": round(t_comf - deviation, 1),
            "upper": round(t_comf + deviation, 1),
            "design": round(t_comf, 1),
            "outdoor_running_mean": round(outdoor_running_mean_temp, 1),
            "adaptive_model": True,
        }

    @classmethod
    def calculate_running_mean_outdoor_temp(
        cls,
        daily_outdoor_temps: List[float],
        alpha: float = 0.8,
    ) -> Optional[float]:
        """
        Calculate exponentially-weighted running mean outdoor temperature for a single point.

        This is kept for backward compatibility but returns a single value.
        Use calculate_running_mean_timeseries for time-varying calculations.
        """
        if not daily_outdoor_temps or len(daily_outdoor_temps) < 7:
            return sum(daily_outdoor_temps) / len(daily_outdoor_temps) if daily_outdoor_temps else None

        t_rm = 0.0
        weight_sum = 0.0

        for i, temp in enumerate(daily_outdoor_temps[:30]):
            weight = alpha ** i
            t_rm += (1 - alpha) * weight * temp
            weight_sum += (1 - alpha) * weight

        return t_rm / weight_sum if weight_sum > 0 else None

    @classmethod
    def calculate_running_mean_timeseries(
        cls,
        outdoor_temp_series: pd.Series,
        alpha: float = 0.8,
    ) -> pd.Series:
        """
        Calculate running mean outdoor temperature as a time series using pythermalcomfort approach.

        According to EN 16798-1 and pythermalcomfort.utilities.running_mean_outdoor_temperature():
        T_rm = (α^0 * T_ed-1 + α^1 * T_ed-2 + α^2 * T_ed-3 + ...) / Σ(α^i)

        Where:
        - T_ed-1 is the daily mean outdoor temperature of the previous day
        - T_ed-2 is from 2 days ago, etc.
        - α is the constant between 0 and 1 (default 0.8 for EN16798)
        - The weights are α^0=1.0, α^1=0.8, α^2=0.64, etc. (decreasing exponentially)

        Implementation matches pythermalcomfort where temp_array = [T_ed-1, T_ed-2, ..., T_ed-n]

        Args:
            outdoor_temp_series: Pandas Series of outdoor temperatures with DatetimeIndex
            alpha: Exponential weighting factor (default 0.8)

        Returns:
            Pandas Series of daily running mean temperatures, forward-filled to match input frequency
        """
        if outdoor_temp_series is None or len(outdoor_temp_series) == 0:
            return pd.Series(dtype=float)

        # Resample to daily mean temperatures
        daily_temps = outdoor_temp_series.resample('D').mean().dropna()

        # Calculate running mean for each day using exponential weights
        running_means = []

        for i in range(len(daily_temps)):
            if i == 0:
                # For first day, use the current day's temperature
                running_means.append(daily_temps.iloc[i])
            else:
                # Build temp_array in format [T_ed-1, T_ed-2, T_ed-3, ...]
                # This matches pythermalcomfort.utilities.running_mean_outdoor_temperature()
                lookback = min(i, 30)  # Look back up to 30 days
                temp_array = [daily_temps.iloc[i - j - 1] for j in range(lookback)]

                # Calculate weights: [α^0, α^1, α^2, ...]
                weights = [alpha ** j for j in range(len(temp_array))]

                # Calculate weighted mean
                t_rm = sum(w * t for w, t in zip(weights, temp_array)) / sum(weights)
                running_means.append(t_rm)

        # Create series with daily running means
        running_mean_daily = pd.Series(running_means, index=daily_temps.index)

        # Forward-fill to match original frequency (so hourly indoor temps use the daily threshold)
        running_mean_series = running_mean_daily.reindex(
            outdoor_temp_series.index,
            method='ffill'
        )

        return running_mean_series

    @classmethod
    def get_thresholds(
        cls,
        category: EN16798Category,
        season: str = "heating",
        outdoor_running_mean_temp: Optional[float] = None,
        ventilation_type: VentilationType = VentilationType.MECHANICAL,
        outdoor_co2: float = OUTDOOR_CO2,
        pollution_level: PollutionLevel = PollutionLevel.NON_LOW,
    ) -> EN16798Thresholds:
        """Get complete thresholds for a category."""
        return EN16798Thresholds(
            category=category,
            temperature_heating=cls.get_temperature_thresholds(
                category, "heating", outdoor_running_mean_temp, ventilation_type
            ),
            temperature_cooling=cls.get_temperature_thresholds(
                category, "cooling", outdoor_running_mean_temp, ventilation_type
            ),
            co2_ppm=outdoor_co2 + cls.CO2_ABOVE_OUTDOOR[category],
            humidity_lower=cls.HUMIDITY[category]["lower"],
            humidity_upper=cls.HUMIDITY[category]["upper"],
            ventilation_per_person_l_s=cls.VENTILATION_PER_PERSON[category],
            ventilation_per_area_l_s_m2=pollution_level.emission_factor,
        )

    @classmethod
    def calculate_ventilation_requirement(
        cls,
        category: EN16798Category,
        floor_area_m2: float,
        occupancy_count: int,
        pollution_level: PollutionLevel = PollutionLevel.NON_LOW,
        volume_m3: Optional[float] = None,
    ) -> VentilationRequirement:
        """Calculate required ventilation rate."""
        q_p = cls.VENTILATION_PER_PERSON[category]
        q_b = pollution_level.emission_factor

        occupant_contribution = occupancy_count * q_p
        building_contribution = floor_area_m2 * q_b
        total_ventilation = occupant_contribution + building_contribution

        ach = None
        if volume_m3 and volume_m3 > 0:
            q_tot_m3_h = total_ventilation * 3.6
            ach = q_tot_m3_h / volume_m3

        return VentilationRequirement(
            total_ventilation_l_s=round(total_ventilation, 2),
            ventilation_per_person_l_s=q_p,
            ventilation_per_area_l_s_m2=q_b,
            occupant_contribution_l_s=round(occupant_contribution, 2),
            building_contribution_l_s=round(building_contribution, 2),
            air_change_rate_ach=round(ach, 2) if ach else None,
            category=category,
        )

    @classmethod
    def assess_compliance(
        cls,
        measured_values: Dict[str, float],
        season: str = "heating",
        outdoor_running_mean_temp: Optional[float] = None,
        ventilation_type: VentilationType = VentilationType.MECHANICAL,
        outdoor_co2: float = OUTDOOR_CO2,
        categories_to_check: Optional[List[EN16798Category]] = None,
    ) -> EN16798ComplianceResult:
        """Assess which EN 16798-1 category is achieved based on point measurements."""
        if categories_to_check is None:
            categories_to_check = list(EN16798Category)
        if category_thresholds is None:
            config_data = load_config()
            category_thresholds = build_category_threshold_map(categories_to_check, config_data)

        achieved_categories: List[EN16798Category] = []
        compliance_details: Dict[EN16798Category, Dict[str, Any]] = {}
        thresholds_used: Dict[EN16798Category, EN16798Thresholds] = {}
        adaptive_used = False

        for category in categories_to_check:
            compliant = True
            details: Dict[str, Any] = {}

            thresholds = cls.get_thresholds(
                category, season, outdoor_running_mean_temp, ventilation_type, outdoor_co2
            )
            thresholds_used[category] = thresholds

            if "temperature" in measured_values:
                temp = measured_values["temperature"]
                temp_thresholds = thresholds.temperature_heating if season.lower() == "heating" else thresholds.temperature_cooling
                temp_ok = temp_thresholds["lower"] <= temp <= temp_thresholds["upper"]
                details["temperature"] = {
                    "value": temp,
                    "thresholds": temp_thresholds,
                    "compliant": temp_ok,
                }
                compliant = compliant and temp_ok
                adaptive_used = bool(temp_thresholds.get("adaptive_model", False))

            if "co2" in measured_values:
                co2 = measured_values["co2"]
                co2_ok = co2 <= thresholds.co2_ppm
                details["co2"] = {
                    "value": co2,
                    "threshold": thresholds.co2_ppm,
                    "compliant": co2_ok,
                }
                compliant = compliant and co2_ok

            if "humidity" in measured_values:
                rh = measured_values["humidity"]
                rh_ok = thresholds.humidity_lower <= rh <= thresholds.humidity_upper
                details["humidity"] = {
                    "value": rh,
                    "lower": thresholds.humidity_lower,
                    "upper": thresholds.humidity_upper,
                    "compliant": rh_ok,
                }
                compliant = compliant and rh_ok

            compliance_details[category] = {
                "compliant": compliant,
                "details": details,
            }

            if compliant:
                achieved_categories.append(category)

        best_category = achieved_categories[0] if achieved_categories else None

        return EN16798ComplianceResult(
            achieved_category=best_category,
            all_compliant_categories=achieved_categories,
            compliance_by_category=compliance_details,
            thresholds_used=thresholds_used,
            season=season,
            adaptive_model_used=bool(adaptive_used),
        )

    @classmethod
    def assess_timeseries_compliance(
        cls,
        temperature: Optional[pd.Series] = None,
        co2: Optional[pd.Series] = None,
        humidity: Optional[pd.Series] = None,
        outdoor_temperature: Optional[pd.Series] = None,
        season: str = "heating",
        ventilation_type: VentilationType = VentilationType.MECHANICAL,
        outdoor_co2: float = OUTDOOR_CO2,
        categories_to_check: Optional[List[EN16798Category]] = None,
        category_thresholds: Optional[Dict[EN16798Category, float]] = None,
    ) -> Dict[str, Any]:
        """Assess compliance over time series data."""
        if categories_to_check is None:
            categories_to_check = list(EN16798Category)
        if category_thresholds is None:
            config_data = load_config()
            category_thresholds = build_category_threshold_map(categories_to_check, config_data)

        outdoor_running_mean = None
        if outdoor_temperature is not None and len(outdoor_temperature) > 0:
            daily_temps = outdoor_temperature.resample("D").mean().dropna().tolist()
            outdoor_running_mean = cls.calculate_running_mean_outdoor_temp(daily_temps)

        results: Dict[str, Any] = {}
        for category in categories_to_check:
            thresholds = cls.get_thresholds(
                category, season, outdoor_running_mean, ventilation_type, outdoor_co2
            )

            compliances = []

            measured = []
            if temperature is not None:
                temp_thresh = thresholds.temperature_heating if season.lower() == "heating" else thresholds.temperature_cooling
                temp_compliant = ((temperature >= temp_thresh["lower"]) & (temperature <= temp_thresh["upper"])) | temperature.isna()
                compliances.append(temp_compliant)
                measured.append(temperature.notna())

            if co2 is not None:
                co2_compliant = (co2 <= thresholds.co2_ppm) | co2.isna()
                compliances.append(co2_compliant)
                measured.append(co2.notna())

            if humidity is not None:
                rh_compliant = ((humidity >= thresholds.humidity_lower) & (humidity <= thresholds.humidity_upper)) | humidity.isna()
                compliances.append(rh_compliant)
                measured.append(humidity.notna())

            if compliances:
                any_measured = pd.concat(measured, axis=1).fillna(False).any(axis=1)
                overall_compliant = pd.concat(compliances, axis=1).fillna(True).all(axis=1)[any_measured]
                compliance_rate = (overall_compliant.sum() / len(overall_compliant)) * 100 if len(overall_compliant) else 0.0
            else:
                compliance_rate = 0.0

            results[category.value] = {
                "compliance_rate": round(compliance_rate, 2),
                "thresholds": thresholds,
            }

        return results

    @classmethod
    def _calculate_adaptive_compliance(
        cls,
        temperature: pd.Series,
        running_mean_series: pd.Series,
        category: EN16798Category,
        season: str = "heating",
    ) -> pd.Series:
        """
        Calculate temperature compliance using adaptive model with time-varying thresholds.

        Each hourly indoor temperature is evaluated against the adaptive thresholds
        calculated from that day's outdoor running mean temperature.

        Args:
            temperature: Indoor temperature series
            running_mean_series: Outdoor running mean temperature series (daily values forward-filled)
            category: EN16798 category to evaluate
            season: Season for non-adaptive fallback

        Returns:
            Boolean series indicating compliance at each timestamp
        """
        compliant = pd.Series([True] * len(temperature), index=temperature.index)

        for idx in temperature.index:
            if idx not in running_mean_series.index:
                compliant[idx] = False
                continue

            t_rm = running_mean_series[idx]
            t_indoor = temperature[idx]

            # Check if adaptive model is applicable (10-30°C range)
            if pd.isna(t_rm) or t_rm < 10.0 or t_rm > 30.0:
                # Fallback to non-adaptive thresholds
                if season.lower() == "heating":
                    thresholds = cls.TEMP_HEATING[category]
                else:
                    thresholds = cls.TEMP_COOLING[category]
            else:
                # Use adaptive thresholds based on this timestamp's running mean
                thresholds = cls._get_adaptive_temperature_thresholds(category, t_rm)

            # Check compliance
            if pd.isna(t_indoor):
                compliant[idx] = False
            else:
                compliant[idx] = (t_indoor >= thresholds["lower"]) and (t_indoor <= thresholds["upper"])

        return compliant

    @classmethod
    def assess_detailed_timeseries(
        cls,
        temperature: Optional[pd.Series] = None,
        co2: Optional[pd.Series] = None,
        humidity: Optional[pd.Series] = None,
        outdoor_temperature: Optional[pd.Series] = None,
        season: str = "heating",
        ventilation_type: VentilationType = VentilationType.MECHANICAL,
        outdoor_co2: float = OUTDOOR_CO2,
        occupancy_mask: Optional[pd.Series] = None,
        categories_to_check: Optional[List[EN16798Category]] = None,
        category_thresholds: Optional[Dict[EN16798Category, float]] = None,
    ) -> EN16798DetailedResult:
        """
        Perform comprehensive EN 16798-1 analysis with detailed metrics.

        Calculates both adaptive and non-adaptive results when outdoor temperature is available.
        Uses pythermalcomfort approach: daily running mean thresholds applied to hourly indoor temperatures.
        """
        from datetime import datetime

        if categories_to_check is None:
            categories_to_check = list(EN16798Category)
        if category_thresholds is None:
            config_data = load_config()
            category_thresholds = build_category_threshold_map(categories_to_check, config_data)

        # Calculate running mean time series using pythermalcomfort approach
        running_mean_series = None
        outdoor_running_mean_single = None
        can_use_adaptive = False

        if outdoor_temperature is not None and len(outdoor_temperature) > 0:
            running_mean_series = cls.calculate_running_mean_timeseries(outdoor_temperature)
            # Also calculate single value for backward compatibility and metadata
            daily_temps = outdoor_temperature.resample("D").mean().dropna().tolist()
            outdoor_running_mean_single = cls.calculate_running_mean_outdoor_temp(daily_temps)

            # Check if adaptive model can be used
            can_use_adaptive = (
                ventilation_type in [VentilationType.NATURAL, VentilationType.MIXED_MODE]
                and running_mean_series is not None
                and len(running_mean_series) > 0
            )

        if occupancy_mask is not None:
            if temperature is not None:
                temperature = temperature[occupancy_mask]
            if co2 is not None:
                co2 = co2[occupancy_mask]
            if humidity is not None:
                humidity = humidity[occupancy_mask]

        # Align the parameters on one index. Rows where nothing was measured are not
        # assessed, and a missing value for one parameter is not a violation. (Previously
        # absent parameters defaulted to a RangeIndex series whose union with the
        # datetime index doubled the row count, and NaN compared as non-compliant.)
        present = {
            name: series
            for name, series in (("temperature", temperature), ("co2", co2), ("humidity", humidity))
            if series is not None and len(series) > 0
        }
        if present:
            frame = pd.concat(present, axis=1).dropna(how="all")
            temperature = frame["temperature"] if "temperature" in present else None
            co2 = frame["co2"] if "co2" in present else None
            humidity = frame["humidity"] if "humidity" in present else None
            assess_index = frame.index
        else:
            assess_index = pd.RangeIndex(0)
        total_points = len(assess_index)

        # Calculate compliance for NON-ADAPTIVE model (always calculated)
        category_compliance_nonadaptive: Dict[EN16798Category, pd.Series] = {}

        for category in categories_to_check:
            # Non-adaptive thresholds (fixed by season)
            thresholds = cls.get_thresholds(
                category, season, None, VentilationType.MECHANICAL, outdoor_co2
            )

            temp_compliant = pd.Series(True, index=assess_index)
            if temperature is not None and len(temperature) > 0:
                temp_thresh = thresholds.temperature_heating if season.lower() == "heating" else thresholds.temperature_cooling
                temp_compliant = ((temperature >= temp_thresh["lower"]) & (temperature <= temp_thresh["upper"])) | temperature.isna()

            co2_compliant = pd.Series(True, index=assess_index)
            if co2 is not None and len(co2) > 0:
                co2_compliant = (co2 <= thresholds.co2_ppm) | co2.isna()

            rh_compliant = pd.Series(True, index=assess_index)
            if humidity is not None and len(humidity) > 0:
                rh_compliant = ((humidity >= thresholds.humidity_lower) & (humidity <= thresholds.humidity_upper)) | humidity.isna()

            overall_compliant = temp_compliant & co2_compliant & rh_compliant
            category_compliance_nonadaptive[category] = overall_compliant

        # Calculate compliance for ADAPTIVE model (if applicable)
        category_compliance_adaptive: Dict[EN16798Category, pd.Series] = {}
        adaptive_used = False

        if can_use_adaptive and temperature is not None and len(temperature) > 0:
            adaptive_used = True
            for category in categories_to_check:
                # Use time-varying adaptive thresholds for temperature
                temp_compliant_adaptive = cls._calculate_adaptive_compliance(
                    temperature, running_mean_series, category, season
                ) | temperature.isna()

                # CO2 and humidity use same thresholds as non-adaptive
                co2_compliant = pd.Series(True, index=assess_index)
                if co2 is not None and len(co2) > 0:
                    thresholds = cls.get_thresholds(category, season, None, ventilation_type, outdoor_co2)
                    co2_compliant = (co2 <= thresholds.co2_ppm) | co2.isna()

                rh_compliant = pd.Series(True, index=assess_index)
                if humidity is not None and len(humidity) > 0:
                    thresholds = cls.get_thresholds(category, season, None, ventilation_type, outdoor_co2)
                    rh_compliant = ((humidity >= thresholds.humidity_lower) & (humidity <= thresholds.humidity_upper)) | humidity.isna()

                overall_compliant_adaptive = temp_compliant_adaptive & co2_compliant & rh_compliant
                category_compliance_adaptive[category] = overall_compliant_adaptive

        # Use adaptive results as primary if available, otherwise use non-adaptive
        category_compliance_arrays = category_compliance_adaptive if adaptive_used else category_compliance_nonadaptive
        violations: List[Dict[str, Any]] = []

        time_in_cat_I = 0
        time_in_cat_II = 0
        time_in_cat_III = 0
        time_in_cat_IV = 0
        time_out_of_all = 0

        if total_points > 0:
            cat_I_compliant = category_compliance_arrays.get(EN16798Category.CATEGORY_I, pd.Series(False, index=assess_index))
            cat_II_compliant = category_compliance_arrays.get(EN16798Category.CATEGORY_II, pd.Series(False, index=assess_index))
            cat_III_compliant = category_compliance_arrays.get(EN16798Category.CATEGORY_III, pd.Series(False, index=assess_index))
            cat_IV_compliant = category_compliance_arrays.get(EN16798Category.CATEGORY_IV, pd.Series(False, index=assess_index))

            time_in_cat_I = cat_I_compliant.sum()
            time_in_cat_II = (cat_II_compliant & ~cat_I_compliant).sum()
            time_in_cat_III = (cat_III_compliant & ~cat_II_compliant).sum()
            time_in_cat_IV = (cat_IV_compliant & ~cat_III_compliant).sum()
            time_out_of_all = (~cat_IV_compliant).sum()

        time_in_cat_I_pct = (time_in_cat_I / total_points * 100) if total_points > 0 else 0.0
        time_in_cat_II_pct = (time_in_cat_II / total_points * 100) if total_points > 0 else 0.0
        time_in_cat_III_pct = (time_in_cat_III / total_points * 100) if total_points > 0 else 0.0
        time_in_cat_IV_pct = (time_in_cat_IV / total_points * 100) if total_points > 0 else 0.0
        time_out_of_all_pct = (time_out_of_all / total_points * 100) if total_points > 0 else 0.0

        achieved_category = None
        all_compliant_categories = []
        overall_compliance_rate = 0.0

        for category in categories_to_check:
            compliance_array = category_compliance_arrays.get(category)
            compliance_rate = (compliance_array.sum() / total_points * 100) if total_points > 0 and compliance_array is not None else 0.0
            threshold = category_thresholds.get(
                category,
                DEFAULT_CATEGORY_COMPLIANCE_THRESHOLDS.get(category, 95.0),
            )
            if compliance_rate >= threshold:
                all_compliant_categories.append(category)

        if all_compliant_categories:
            achieved_category = all_compliant_categories[0]
            compliance_array = category_compliance_arrays[achieved_category]
            overall_compliance_rate = (compliance_array.sum() / total_points * 100) if total_points > 0 else 0.0

        temperature_metrics = None
        if temperature is not None and len(temperature) > 0:
            temperature_metrics = cls._calculate_parameter_metrics(
                "temperature",
                temperature,
                season,
                categories_to_check,
                outdoor_running_mean_single,
                ventilation_type,
                outdoor_co2,
            )

        co2_metrics = None
        if co2 is not None and len(co2) > 0:
            co2_metrics = cls._calculate_parameter_metrics(
                "co2",
                co2,
                season,
                categories_to_check,
                outdoor_running_mean_single,
                ventilation_type,
                outdoor_co2,
            )

        humidity_metrics = None
        if humidity is not None and len(humidity) > 0:
            humidity_metrics = cls._calculate_parameter_metrics(
                "humidity",
                humidity,
                season,
                categories_to_check,
                outdoor_running_mean_single,
                ventilation_type,
                outdoor_co2,
            )

        if EN16798Category.CATEGORY_IV in category_compliance_arrays:
            cat_IV_compliant = category_compliance_arrays[EN16798Category.CATEGORY_IV]
            violation_mask = ~cat_IV_compliant

            if violation_mask.sum() > 0:
                violation_indices = violation_mask[violation_mask].index
                for idx in violation_indices[:100]:
                    violation_detail: Dict[str, Any] = {"timestamp": str(idx)}
                    if temperature is not None and idx in temperature.index:
                        violation_detail["temperature"] = float(temperature.loc[idx])
                    if co2 is not None and idx in co2.index:
                        violation_detail["co2"] = float(co2.loc[idx])
                    if humidity is not None and idx in humidity.index:
                        violation_detail["humidity"] = float(humidity.loc[idx])
                    violations.append(violation_detail)

        return EN16798DetailedResult(
            achieved_category=achieved_category,
            all_compliant_categories=all_compliant_categories,
            overall_compliance_rate=round(overall_compliance_rate, 2),
            time_in_category_I_pct=round(time_in_cat_I_pct, 2),
            time_in_category_II_pct=round(time_in_cat_II_pct, 2),
            time_in_category_III_pct=round(time_in_cat_III_pct, 2),
            time_in_category_IV_pct=round(time_in_cat_IV_pct, 2),
            time_out_of_all_categories_pct=round(time_out_of_all_pct, 2),
            total_data_points=total_points,
            valid_data_points=total_points,
            temperature_metrics=temperature_metrics,
            co2_metrics=co2_metrics,
            humidity_metrics=humidity_metrics,
            violations=violations,
            total_violations=len(violations),
            season=season,
            adaptive_model_used=adaptive_used,
            outdoor_running_mean_temp=outdoor_running_mean_single,
            ventilation_type=ventilation_type.value,
            analysis_timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def _calculate_parameter_metrics(
        cls,
        parameter_name: str,
        data: pd.Series,
        season: str,
        categories_to_check: List[EN16798Category],
        outdoor_running_mean: Optional[float],
        ventilation_type: VentilationType,
        outdoor_co2: float,
    ) -> Dict[str, Any]:
        """Calculate detailed metrics for a single parameter (over measured samples only)."""
        data = data.dropna()
        if data.empty:
            return {"parameter_name": parameter_name, "sample_count": 0}
        metrics: Dict[str, Any] = {
            "parameter_name": parameter_name,
            "mean_value": round(float(data.mean()), 2),
            "min_value": round(float(data.min()), 2),
            "max_value": round(float(data.max()), 2),
            "std_dev": round(float(data.std()), 2),
            "median_value": round(float(data.median()), 2),
        }

        compliance_rates: Dict[str, float] = {}
        thresholds_by_category: Dict[str, Dict[str, Any]] = {}

        for category in categories_to_check:
            thresholds = cls.get_thresholds(
                category, season, outdoor_running_mean, ventilation_type, outdoor_co2
            )
            thresholds_by_category[category.value] = {}

            if parameter_name == "temperature":
                temp_thresh = thresholds.temperature_heating if season.lower() == "heating" else thresholds.temperature_cooling
                compliant = (data >= temp_thresh["lower"]) & (data <= temp_thresh["upper"])
                thresholds_by_category[category.value] = temp_thresh
            elif parameter_name == "co2":
                compliant = data <= thresholds.co2_ppm
                thresholds_by_category[category.value] = {"threshold": thresholds.co2_ppm}
            elif parameter_name == "humidity":
                compliant = (data >= thresholds.humidity_lower) & (data <= thresholds.humidity_upper)
                thresholds_by_category[category.value] = {
                    "lower": thresholds.humidity_lower,
                    "upper": thresholds.humidity_upper,
                }
            else:
                compliant = pd.Series([True] * len(data))

            compliance_rate = (compliant.sum() / len(data) * 100) if len(data) > 0 else 0.0
            compliance_rates[f"category_{category.value}_compliance_rate"] = round(compliance_rate, 2)

        metrics.update(compliance_rates)
        metrics["thresholds_by_category"] = thresholds_by_category

        if EN16798Category.CATEGORY_II in categories_to_check:
            cat_II_thresholds = cls.get_thresholds(
                EN16798Category.CATEGORY_II, season, outdoor_running_mean, ventilation_type, outdoor_co2
            )

            if parameter_name == "temperature":
                temp_thresh = cat_II_thresholds.temperature_heating if season.lower() == "heating" else cat_II_thresholds.temperature_cooling
                above_threshold = data > temp_thresh["upper"]
                below_threshold = data < temp_thresh["lower"]
                time_above_pct = (above_threshold.sum() / len(data) * 100) if len(data) > 0 else 0.0
                time_below_pct = (below_threshold.sum() / len(data) * 100) if len(data) > 0 else 0.0
                max_exceedance = max(
                    float(data.max() - temp_thresh["upper"]),
                    float(temp_thresh["lower"] - data.min()),
                )
            elif parameter_name == "co2":
                above_threshold = data > cat_II_thresholds.co2_ppm
                time_above_pct = (above_threshold.sum() / len(data) * 100) if len(data) > 0 else 0.0
                time_below_pct = 0.0
                max_exceedance = float(data.max() - cat_II_thresholds.co2_ppm)
            elif parameter_name == "humidity":
                above_threshold = data > cat_II_thresholds.humidity_upper
                below_threshold = data < cat_II_thresholds.humidity_lower
                time_above_pct = (above_threshold.sum() / len(data) * 100) if len(data) > 0 else 0.0
                time_below_pct = (below_threshold.sum() / len(data) * 100) if len(data) > 0 else 0.0
                max_exceedance = max(
                    float(data.max() - cat_II_thresholds.humidity_upper),
                    float(cat_II_thresholds.humidity_lower - data.min()),
                )
            else:
                time_above_pct = 0.0
                time_below_pct = 0.0
                max_exceedance = 0.0

            metrics["time_above_threshold_pct"] = round(time_above_pct, 2)
            metrics["time_below_threshold_pct"] = round(time_below_pct, 2)
            metrics["max_exceedance"] = round(max(0, max_exceedance), 2)

        return metrics

def load_config() -> Dict[str, Any]:
    """Load the en16798_1 configuration file."""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f) or {}

    applicability = config.get('applicability')
    if isinstance(applicability, dict):
        expanded_countries = _expand_country_groups(applicability.get('countries'))
        if expanded_countries is not None:
            applicability['countries'] = expanded_countries

    return config


def create_rulesets_from_config(config: Dict[str, Any]) -> List[RuleSet]:
    """
    Create RuleSet objects from config file.

    Returns:
        List of RuleSet objects for each category
    """
    rulesets = []

    for ruleset_config in config.get('rulesets', []):
        category = ruleset_config['category']

        # Create test rules
        rules = []
        for rule_config in ruleset_config.get('rules', []):
            # Map metric string to MetricType enum
            metric_map = {
                'temperature': MetricType.TEMPERATURE,
                'co2': MetricType.CO2,
                'humidity': MetricType.HUMIDITY,
            }
            metric = metric_map.get(rule_config['metric'], MetricType.OTHER)

            # Map operator string to RuleOperator enum
            operator_map = {
                'between': RuleOperator.BETWEEN,
                '<=': RuleOperator.LE,
                '<': RuleOperator.LT,
                '>=': RuleOperator.GE,
                '>': RuleOperator.GT,
                '==': RuleOperator.EQ,
            }
            operator = operator_map.get(rule_config['operator'], RuleOperator.LE)

            rule = TestRule(
                id=rule_config['id'],
                name=rule_config['name'],
                metric=metric,
                operator=operator,
                target_value=rule_config.get('target_value'),
                lower_bound=rule_config.get('lower_bound'),
                upper_bound=rule_config.get('upper_bound'),
                tolerance_hours=rule_config.get('tolerance_hours'),
                tolerance_percentage=rule_config.get('tolerance_percentage'),
                applies_during=rule_config.get('applies_during'),
                metadata={
                    'unit': rule_config.get('unit', ''),
                    'season': rule_config.get('season', 'all_year'),
                }
            )
            rules.append(rule)

        # Create applicability conditions
        applicability = config.get('applicability', {})
        conditions = [
            ApplicabilityCondition(
                id=f"en16798_{category}_applicability",
                countries=applicability.get('countries'),
                regions=applicability.get('regions'),
                building_types=applicability.get('building_types'),
                ventilation_types=[
                    EntityVentilationType(vt) for vt in applicability.get('ventilation_types', [])
                ] if applicability.get('ventilation_types') else None,
            )
        ]

        # Create ruleset
        ruleset = RuleSet(
            id=f"en16798_cat_{category}",
            name=f"EN 16798-1 Category {category}",
            standard=StandardType.EN16798,
            category=category,
            rules=rules,
            applicability_conditions=conditions,
            metadata={
                'version': config.get('version', '2024.1'),
                'ventilation_rate': config.get('ventilation_rates', {}).get(category),
            }
        )
        rulesets.append(ruleset)

    return rulesets


def run(
    spatial_entity: SpatialEntity,
    timeseries_dict: Dict[str, List[float]],
    timestamps: List[str],
    season: str = "winter",
    categories: Optional[List[str]] = None,
    **kwargs
) -> ComplianceAnalysis:
    """
    Run EN 16798-1 compliance analysis for a spatial entity.

    Args:
        spatial_entity: The spatial entity to analyze
        timeseries_dict: Dict mapping metric names to value lists
        timestamps: List of timestamp strings
        season: "winter" or "summer"
        categories: List of categories to check (default: all)
        **kwargs: Additional configuration

    Returns:
        ComplianceAnalysis object with results
    """
    from datetime import datetime

    # Load configuration
    config = load_config()

    # Create rulesets
    rulesets = create_rulesets_from_config(config)

    # Filter categories if specified
    if categories:
        rulesets = [rs for rs in rulesets if rs.category in categories]

    # Use EN16798Calculator for actual computation
    calculator = EN16798Calculator()

    # Extract outdoor_temperature from kwargs if provided
    outdoor_temperature = kwargs.get('outdoor_temperature')
    if outdoor_temperature and 'outdoor_temperature' not in timeseries_dict:
        timeseries_dict['outdoor_temperature'] = outdoor_temperature

    # Convert timeseries to pandas Series
    ts_data = {}
    ts_index = pd.to_datetime(timestamps) if timestamps else None

    for metric, values in timeseries_dict.items():
        if metric in ['temperature', 'co2', 'humidity', 'outdoor_temperature']:
            # Handle case where values length doesn't match timestamps length
            # This can happen when data has missing values that were filtered out
            if ts_index is not None:
                # If lengths match, use the index directly
                if len(values) == len(ts_index):
                    ts_data[metric] = pd.Series(values, index=ts_index)
                else:
                    # If lengths don't match, we need a datetime index for outdoor_temperature
                    # since it's used for resampling
                    if metric == 'outdoor_temperature':
                        # For outdoor temperature from climate data, it likely has its own timestamps
                        # Create a datetime index from the values' natural order
                        # Assuming it's the same period as the room data
                        try:
                            # Try to infer datetime index from the data length
                            if len(values) > 0:
                                # Use the timestamps length as reference, create a compatible index
                                temp_index = pd.date_range(
                                    start=ts_index[0] if len(ts_index) > 0 else '2024-01-01',
                                    periods=len(values),
                                    freq='h'
                                )
                                ts_data[metric] = pd.Series(values, index=temp_index)
                            else:
                                ts_data[metric] = None
                        except Exception:
                            # Fall back to None if we can't create proper index
                            ts_data[metric] = None
                    else:
                        # For other metrics, create series without index
                        ts_data[metric] = pd.Series(values)
            else:
                ts_data[metric] = pd.Series(values)

    # Determine ventilation type
    vent_type_map = {
        EntityVentilationType.NATURAL: VentilationType.NATURAL,
        EntityVentilationType.MECHANICAL: VentilationType.MECHANICAL,
        EntityVentilationType.MIXED: VentilationType.MIXED_MODE,
    }
    vent_type = VentilationType.MECHANICAL
    if spatial_entity.ventilation_type and spatial_entity.ventilation_type != EntityVentilationType.UNKNOWN:
        vent_type = vent_type_map.get(spatial_entity.ventilation_type, VentilationType.MECHANICAL)

    cat_map = {
        'I': EN16798Category.CATEGORY_I,
        'II': EN16798Category.CATEGORY_II,
        'III': EN16798Category.CATEGORY_III,
        'IV': EN16798Category.CATEGORY_IV,
    }
    categories_to_check = [cat_map[rs.category] for rs in rulesets if rs.category in cat_map]
    category_thresholds = build_category_threshold_map(categories_to_check, config)

    # Map season to heating/cooling for calculator
    season_map = {
        'winter': 'heating',
        'summer': 'cooling',
        'heating': 'heating',
        'cooling': 'cooling',
    }
    calc_season = season_map.get(season.lower(), 'heating')

    # Use detailed timeseries assessment for comprehensive metrics
    detailed_result = calculator.assess_detailed_timeseries(
        temperature=ts_data.get('temperature'),
        co2=ts_data.get('co2'),
        humidity=ts_data.get('humidity'),
        outdoor_temperature=ts_data.get('outdoor_temperature'),
        season=calc_season,
        ventilation_type=vent_type,
        categories_to_check=categories_to_check,
        category_thresholds=category_thresholds,
    )

    # Calculate compliance rates per category for test results
    category_compliance_rates = {}
    for category in categories_to_check:
        # Get thresholds for this category
        thresholds = calculator.get_thresholds(
            category, calc_season, detailed_result.outdoor_running_mean_temp, vent_type
        )

        # Calculate compliance for each parameter
        temp_data = ts_data.get('temperature')
        co2_data = ts_data.get('co2')
        humidity_data = ts_data.get('humidity')

        compliances = []
        if temp_data is not None and len(temp_data) > 0:
            temp_thresh = thresholds.temperature_heating if calc_season == "heating" else thresholds.temperature_cooling
            temp_compliant = (temp_data >= temp_thresh["lower"]) & (temp_data <= temp_thresh["upper"])
            compliances.append(temp_compliant)

        if co2_data is not None and len(co2_data) > 0:
            co2_compliant = co2_data <= thresholds.co2_ppm
            compliances.append(co2_compliant)

        if humidity_data is not None and len(humidity_data) > 0:
            rh_compliant = (humidity_data >= thresholds.humidity_lower) & (humidity_data <= thresholds.humidity_upper)
            compliances.append(rh_compliant)

        if compliances:
            overall_compliant = pd.concat(compliances, axis=1).all(axis=1)
            compliance_rate = (overall_compliant.sum() / len(overall_compliant)) * 100
        else:
            compliance_rate = 0.0

        category_compliance_rates[category.value] = compliance_rate

    # Convert detailed results to TestResult objects
    test_results = []
    for category in categories_to_check:
        compliance_rate = category_compliance_rates[category.value]
        threshold = category_thresholds.get(
            category,
            DEFAULT_CATEGORY_COMPLIANCE_THRESHOLDS.get(category, 95.0),
        )
        passed = compliance_rate >= threshold

        # Get thresholds for export
        thresholds = calculator.get_thresholds(
            category, calc_season, detailed_result.outdoor_running_mean_temp, vent_type
        )
        thresh_dict = {
            'temperature_heating': thresholds.temperature_heating,
            'temperature_cooling': thresholds.temperature_cooling,
            'co2_ppm': thresholds.co2_ppm,
            'humidity_lower': thresholds.humidity_lower,
            'humidity_upper': thresholds.humidity_upper,
        }

        test_result = TestResult(
            id=f"test_{spatial_entity.id}_{category.value}",
            name=f"EN16798 Category {category.value} Test",
            type=AnalysisType.TEST_RESULT,
            spatial_entity_id=spatial_entity.id,
            rule_id=f"en16798_cat_{category.value}",
            successful=passed,
            out_of_range_percentage=100.0 - compliance_rate,
            status=AnalysisStatus.COMPLETED,
            details={
                'compliance_rate': round(compliance_rate, 2),
                'category': category.value,
                'thresholds': thresh_dict,
            }
        )
        test_results.append(test_result)

    # Determine overall compliance (best achieved category)
    overall_pass = any(tr.successful for tr in test_results)
    best_category = detailed_result.achieved_category.value if detailed_result.achieved_category else None
    best_compliance = detailed_result.overall_compliance_rate

    # Create ComplianceAnalysis with detailed metrics
    analysis = ComplianceAnalysis(
        id=f"compliance_{spatial_entity.id}_en16798",
        name=f"EN 16798-1 Compliance for {spatial_entity.name}",
        type=AnalysisType.COMPLIANCE,
        spatial_entity_id=spatial_entity.id,
        rule_set_id=f"en16798_multi_category",
        test_result_ids=[tr.id for tr in test_results],
        overall_pass=overall_pass,
        status=AnalysisStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        summary_results={
            'achieved_category': best_category,
            'season': season,
            'standard': 'en16798_1',
            'version': config.get('version', '2024.1'),

            # Detailed category breakdown
            'category_compliance_rates': {
                cat.value: round(category_compliance_rates[cat.value], 2)
                for cat in categories_to_check
            },
            'category_thresholds': {
                cat.value: category_thresholds.get(
                    cat,
                    DEFAULT_CATEGORY_COMPLIANCE_THRESHOLDS.get(cat, 95.0),
                )
                for cat in categories_to_check
            },
            'time_in_category_I_pct': detailed_result.time_in_category_I_pct,
            'time_in_category_II_pct': detailed_result.time_in_category_II_pct,
            'time_in_category_III_pct': detailed_result.time_in_category_III_pct,
            'time_in_category_IV_pct': detailed_result.time_in_category_IV_pct,
            'time_out_of_all_categories_pct': detailed_result.time_out_of_all_categories_pct,

            # Parameter-specific metrics
            'parameter_metrics': {
                'temperature': detailed_result.temperature_metrics if detailed_result.temperature_metrics else None,
                'co2': detailed_result.co2_metrics if detailed_result.co2_metrics else None,
                'humidity': detailed_result.humidity_metrics if detailed_result.humidity_metrics else None,
            },

            # Data quality and metadata
            'total_data_points': detailed_result.total_data_points,
            'valid_data_points': detailed_result.valid_data_points,
            'adaptive_model_used': detailed_result.adaptive_model_used,
            'outdoor_running_mean_temp': detailed_result.outdoor_running_mean_temp,
            'ventilation_type': detailed_result.ventilation_type,

            # Aggregation method
            'aggregation_method': 'time_weighted_percentage',
            'aggregation_description': 'Compliance calculated as percentage of time points meeting all parameter thresholds simultaneously',
        }
    )

    return analysis


# Convenience function for backward compatibility
def analyze(
    spatial_entity: SpatialEntity,
    temperature: Optional[List[float]] = None,
    co2: Optional[List[float]] = None,
    humidity: Optional[List[float]] = None,
    outdoor_temperature: Optional[List[float]] = None,
    timestamps: Optional[List[str]] = None,
    season: str = "winter",
    categories: Optional[List[str]] = None,
) -> ComplianceAnalysis:
    """
    Convenience function for EN 16798-1 analysis.

    Args:
        spatial_entity: Entity to analyze
        temperature: Temperature values (°C)
        co2: CO2 values (ppm)
        humidity: Relative humidity values (%)
        outdoor_temperature: Outdoor temperature values (°C)
        timestamps: Timestamp strings
        season: "winter" or "summer"
        categories: Categories to check

    Returns:
        ComplianceAnalysis with results
    """
    timeseries_dict = {}
    if temperature:
        timeseries_dict['temperature'] = temperature
    if co2:
        timeseries_dict['co2'] = co2
    if humidity:
        timeseries_dict['humidity'] = humidity
    if outdoor_temperature:
        timeseries_dict['outdoor_temperature'] = outdoor_temperature

    return run(
        spatial_entity=spatial_entity,
        timeseries_dict=timeseries_dict,
        timestamps=timestamps or [],
        season=season,
        categories=categories,
    )


if __name__ == "__main__":
    # Test the configuration loading
    config = load_config()
    print(f"Loaded EN 16798-1 config: {config['name']}")
    print(f"Version: {config['version']}")
    print(f"Categories: {[c['id'] for c in config['categories']]}")

    # Create rulesets
    rulesets = create_rulesets_from_config(config)
    print(f"\nCreated {len(rulesets)} rulesets:")
    for rs in rulesets:
        print(f"  - {rs.name}: {len(rs.rules)} rules")
