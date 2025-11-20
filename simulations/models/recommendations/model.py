from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from simulations.models.correlations import ClimateCorrelationResult
from simulations.models.scenario import ScenarioImpactSummary
from simulations.models.ventilation import VentilationRateResult


class RecommendationType(str, Enum):
    """Categories for recommendations shown in the HTML report."""

    VENTILATION = "ventilation"
    SOLAR_SHADING = "solar_shading"
    ENVELOPE = "envelope"
    OPERATIONAL = "operational"
    SEASONAL_CONTROL = "seasonal_control"
    SOLAR_MANAGEMENT = "solar_management"


@dataclass
class SmartRecommendation:
    """Structured recommendation that the report can render."""

    title: str
    type: RecommendationType
    priority: str
    description: str
    expected_benefit: Optional[str] = None
    evidence: Optional[Dict[str, float]] = None

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "type": self.type.value,
            "priority": self.priority,
            "description": self.description,
            "expected_benefit": self.expected_benefit,
            "evidence": self.evidence or {},
        }


class SmartRecommendationsModel:
    """
    Lightweight recommendation engine tailored for the HTML report workflow.
    """

    def __init__(self) -> None:
        pass

    def _ventilation_recommendation(
        self,
        room_name: str,
        co2_compliance: Optional[float],
        ventilation_result: Optional[VentilationRateResult],
        scenarios: ScenarioImpactSummary,
    ) -> Optional[SmartRecommendation]:
        if ventilation_result is None:
            return None

        need_upgrade = (co2_compliance is not None and co2_compliance < 90.0) or ventilation_result.ach < 2.0
        if not need_upgrade:
            return None

        scenario = scenarios.ventilation
        benefit = None
        if scenario and scenario.metrics.get("co2_compliance_gain"):
            benefit = (
                f"+{scenario.metrics['co2_compliance_gain']:.1f} pp CO₂ compliance "
                f"by reaching {scenario.metrics['target_ach']:.2f} ACH"
            )

        return SmartRecommendation(
            title=f"Increase ventilation in {room_name}",
            type=RecommendationType.VENTILATION,
            priority="high" if (co2_compliance or 100.0) < 80.0 else "medium",
            description=(
                "Measured CO₂ levels indicate insufficient air exchange. "
                "Consider balancing supply fans, extending schedules, or installing "
                "demand-controlled ventilation."
            ),
            expected_benefit=benefit,
            evidence={
                "ach": ventilation_result.ach,
                "co2_compliance": co2_compliance or 0.0,
            },
        )

    def _solar_shading_recommendation(
        self,
        room_name: str,
        temp_compliance: Optional[float],
        correlations: ClimateCorrelationResult,
        scenarios: ScenarioImpactSummary,
    ) -> Optional[SmartRecommendation]:
        if temp_compliance is None or temp_compliance > 85.0:
            return None

        if correlations.temperature_vs_solar is None or correlations.temperature_vs_solar < 0.35:
            return None

        scenario = scenarios.solar_shading
        benefit = None
        if scenario and scenario.metrics.get("temp_compliance_gain"):
            benefit = f"+{scenario.metrics['temp_compliance_gain']:.1f} pp temperature compliance"

        return SmartRecommendation(
            title=f"Deploy solar shading in {room_name}",
            type=RecommendationType.SOLAR_SHADING,
            priority="medium",
            description=(
                "Indoor temperatures move strongly with solar radiation. "
                "Use automated blinds, electrochromic glazing, or fins to cut peak gains."
            ),
            expected_benefit=benefit,
            evidence={
                "temp_vs_solar_corr": correlations.temperature_vs_solar or 0.0,
                "temp_compliance": temp_compliance,
            },
        )

    def _envelope_recommendation(
        self,
        room_name: str,
        temp_compliance: Optional[float],
        correlations: ClimateCorrelationResult,
    ) -> Optional[SmartRecommendation]:
        if temp_compliance is None or temp_compliance > 75.0:
            return None

        if correlations.temperature_vs_outdoor is None or correlations.temperature_vs_outdoor > -0.2:
            return None

        return SmartRecommendation(
            title=f"Improve envelope tightness in {room_name}",
            type=RecommendationType.ENVELOPE,
            priority="medium",
            description=(
                "Indoor temperature tracks the outdoor profile, pointing to conduction or infiltration losses. "
                "Inspect window seals, check insulation continuity, and correct uncontrolled infiltration paths."
            ),
            evidence={
                "temp_vs_outdoor_corr": correlations.temperature_vs_outdoor or 0.0,
                "temp_compliance": temp_compliance,
            },
        )

    def _operational_recommendation(
        self,
        room_name: str,
        humidity_compliance: Optional[float],
    ) -> Optional[SmartRecommendation]:
        if humidity_compliance is None or humidity_compliance > 90.0:
            return None
        return SmartRecommendation(
            title=f"Review humidification schedule in {room_name}",
            type=RecommendationType.OPERATIONAL,
            priority="low",
            description="Humidity drifts outside the recommended band. Verify set-points and maintenance of humidifiers/dehumidifiers.",
            evidence={"humidity_compliance": humidity_compliance},
        )

    def _winter_overheating_recommendation(
        self,
        room_name: str,
        correlations: ClimateCorrelationResult,
    ) -> Optional[SmartRecommendation]:
        """Generate recommendation for winter overheating issues."""
        if correlations.seasonal_thermal is None:
            return None

        seasonal = correlations.seasonal_thermal
        if seasonal.winter_overheating_percentage is None:
            return None

        # Threshold: significant overheating if >10% of winter hours are too hot
        if seasonal.winter_overheating_percentage < 10.0:
            return None

        priority = "high" if seasonal.winter_overheating_percentage > 25.0 else "medium"

        return SmartRecommendation(
            title=f"Reduce winter overheating in {room_name}",
            type=RecommendationType.SEASONAL_CONTROL,
            priority=priority,
            description=(
                f"During winter months, the room experiences overheating for {seasonal.winter_overheating_percentage:.1f}% "
                f"of the time ({seasonal.winter_overheating_hours:.0f} hours). This indicates excessive heating or poor "
                "temperature control. Consider adjusting heating curves, implementing weather compensation, or "
                "upgrading to smart thermostatic controls with occupancy detection."
            ),
            expected_benefit=f"Reduce overheating by ~{seasonal.winter_overheating_percentage:.0f}% of winter hours",
            evidence={
                "winter_overheating_pct": seasonal.winter_overheating_percentage,
                "winter_overheating_hours": seasonal.winter_overheating_hours,
                "winter_avg_temp": seasonal.winter_avg_temp,
                "winter_max_temp": seasonal.winter_max_temp,
            },
        )

    def _summer_undercooling_recommendation(
        self,
        room_name: str,
        correlations: ClimateCorrelationResult,
    ) -> Optional[SmartRecommendation]:
        """Generate recommendation for summer undercooling issues."""
        if correlations.seasonal_thermal is None:
            return None

        seasonal = correlations.seasonal_thermal
        if seasonal.summer_undercooling_percentage is None:
            return None

        # Threshold: significant undercooling if >10% of summer hours are too cold
        if seasonal.summer_undercooling_percentage < 10.0:
            return None

        priority = "medium" if seasonal.summer_undercooling_percentage > 20.0 else "low"

        return SmartRecommendation(
            title=f"Address summer undercooling in {room_name}",
            type=RecommendationType.SEASONAL_CONTROL,
            priority=priority,
            description=(
                f"During summer months, the room is too cold for {seasonal.summer_undercooling_percentage:.1f}% "
                f"of the time ({seasonal.summer_undercooling_hours:.0f} hours). This suggests overcooling, "
                "wasting energy and reducing comfort. Review cooling setpoints, consider raising temperature "
                "targets, or implement adaptive comfort strategies that allow higher temperatures during summer."
            ),
            expected_benefit=f"Eliminate {seasonal.summer_undercooling_percentage:.0f}% of overcooling hours, reducing cooling energy",
            evidence={
                "summer_undercooling_pct": seasonal.summer_undercooling_percentage,
                "summer_undercooling_hours": seasonal.summer_undercooling_hours,
                "summer_avg_temp": seasonal.summer_avg_temp,
                "summer_min_temp": seasonal.summer_min_temp,
            },
        )

    def _solar_gain_opportunity_recommendation(
        self,
        room_name: str,
        correlations: ClimateCorrelationResult,
    ) -> Optional[SmartRecommendation]:
        """Generate recommendation for missed solar gain opportunities in winter."""
        if correlations.solar_gain_utilization is None:
            return None

        solar = correlations.solar_gain_utilization
        if solar.winter_solar_gain_opportunity_percentage is None:
            return None

        # Threshold: significant missed opportunity if >15% of winter hours
        if solar.winter_solar_gain_opportunity_percentage < 15.0:
            return None

        priority = "medium" if solar.winter_solar_gain_opportunity_percentage > 30.0 else "low"

        benefit = None
        if solar.winter_missed_heating_offset_kwh is not None and solar.winter_missed_heating_offset_kwh > 0:
            benefit = f"Potential heating energy offset: ~{solar.winter_missed_heating_offset_kwh:.0f} kWh/winter"

        return SmartRecommendation(
            title=f"Improve winter solar heat gain in {room_name}",
            type=RecommendationType.SOLAR_MANAGEMENT,
            priority=priority,
            description=(
                f"In winter, high solar radiation is available for {solar.winter_solar_gain_opportunity_percentage:.1f}% "
                f"of the time ({solar.winter_solar_gain_opportunity_hours:.0f} hours) when the room is cold. "
                "This represents missed passive heating opportunities. Consider removing or automating window "
                "coverings to allow solar gains during sunny winter days, or reviewing shading schedules to "
                "maximize natural heating."
            ),
            expected_benefit=benefit,
            evidence={
                "winter_solar_opportunity_pct": solar.winter_solar_gain_opportunity_percentage,
                "winter_solar_opportunity_hours": solar.winter_solar_gain_opportunity_hours,
                "winter_missed_heating_kwh": solar.winter_missed_heating_offset_kwh,
                "winter_avg_solar": solar.winter_avg_solar_radiation,
            },
        )

    def _solar_excess_recommendation(
        self,
        room_name: str,
        correlations: ClimateCorrelationResult,
    ) -> Optional[SmartRecommendation]:
        """Generate recommendation for excess solar gains in summer."""
        if correlations.solar_gain_utilization is None:
            return None

        solar = correlations.solar_gain_utilization
        if solar.summer_excess_solar_percentage is None:
            return None

        # Threshold: significant excess if >15% of summer hours
        if solar.summer_excess_solar_percentage < 15.0:
            return None

        priority = "high" if solar.summer_excess_solar_percentage > 30.0 else "medium"

        benefit = None
        if solar.summer_excess_cooling_load_kwh is not None and solar.summer_excess_cooling_load_kwh > 0:
            benefit = f"Potential cooling load reduction: ~{solar.summer_excess_cooling_load_kwh:.0f} kWh/summer"

        return SmartRecommendation(
            title=f"Reduce excessive solar heat gains in {room_name}",
            type=RecommendationType.SOLAR_MANAGEMENT,
            priority=priority,
            description=(
                f"During summer, excessive solar radiation contributes to overheating for {solar.summer_excess_solar_percentage:.1f}% "
                f"of the time ({solar.summer_excess_solar_hours:.0f} hours). This increases cooling demand and "
                "reduces comfort. Implement external shading (automated blinds, louvers, or films), increase "
                "vegetation shading, or consider electrochromic glazing to block solar gains during peak hours."
            ),
            expected_benefit=benefit,
            evidence={
                "summer_excess_solar_pct": solar.summer_excess_solar_percentage,
                "summer_excess_solar_hours": solar.summer_excess_solar_hours,
                "summer_excess_cooling_kwh": solar.summer_excess_cooling_load_kwh,
                "summer_avg_solar": solar.summer_avg_solar_radiation,
            },
        )

    def generate(
        self,
        room_name: str,
        compliance: Dict[str, Optional[float]],
        correlations: ClimateCorrelationResult,
        ventilation_result: Optional[VentilationRateResult],
        scenarios: ScenarioImpactSummary,
    ) -> List[SmartRecommendation]:
        recommendations: List[SmartRecommendation] = []

        # Existing recommendations
        rec = self._ventilation_recommendation(
            room_name,
            compliance.get("co2"),
            ventilation_result,
            scenarios,
        )
        if rec:
            recommendations.append(rec)

        rec = self._solar_shading_recommendation(
            room_name,
            compliance.get("temperature"),
            correlations,
            scenarios,
        )
        if rec:
            recommendations.append(rec)

        rec = self._envelope_recommendation(
            room_name,
            compliance.get("temperature"),
            correlations,
        )
        if rec:
            recommendations.append(rec)

        rec = self._operational_recommendation(
            room_name,
            compliance.get("humidity"),
        )
        if rec:
            recommendations.append(rec)

        # New seasonal and solar recommendations
        rec = self._winter_overheating_recommendation(
            room_name,
            correlations,
        )
        if rec:
            recommendations.append(rec)

        rec = self._summer_undercooling_recommendation(
            room_name,
            correlations,
        )
        if rec:
            recommendations.append(rec)

        rec = self._solar_gain_opportunity_recommendation(
            room_name,
            correlations,
        )
        if rec:
            recommendations.append(rec)

        rec = self._solar_excess_recommendation(
            room_name,
            correlations,
        )
        if rec:
            recommendations.append(rec)

        # Sort by priority (high -> medium -> low)
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda r: priority_order.get(r.priority, 3))

        return recommendations
