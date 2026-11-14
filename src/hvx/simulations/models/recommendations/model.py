# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from hvx.simulations.models.correlations import ClimateCorrelationResult
from hvx.simulations.models.scenario import ScenarioImpactSummary
from hvx.simulations.models.ventilation import VentilationRateResult


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
    key: Optional[str] = None  # stable id, e.g. "ventilation"; selects the text template
    action: Optional[str] = None  # room-independent title, used to group rooms

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "type": self.type.value,
            "priority": self.priority,
            "description": self.description,
            "expected_benefit": self.expected_benefit,
            "evidence": self.evidence or {},
            "key": self.key,
            "action": self.action,
        }


# Texts per language. Placeholders receive numbers already formatted for the language.
RECOMMENDATION_TEXTS: Dict[str, Dict[str, Dict[str, str]]] = {
    "en": {
        "ventilation": {
            "action": "Increase ventilation",
            "title": "Increase ventilation in {room}",
            "description": "Measured CO₂ levels indicate insufficient air exchange. Consider balancing supply fans, "
            "extending schedules, or installing demand-controlled ventilation.",
            "benefit": "+{gain} pp CO₂ compliance by reaching {ach} ACH",
        },
        "solar_shading": {
            "action": "Deploy solar shading",
            "title": "Deploy solar shading in {room}",
            "description": "Indoor temperatures move strongly with solar radiation. Use automated blinds, "
            "electrochromic glazing, or fins to cut peak gains.",
            "benefit": "+{gain} pp temperature compliance",
        },
        "envelope": {
            "action": "Improve envelope tightness",
            "title": "Improve envelope tightness in {room}",
            "description": "Indoor temperature tracks the outdoor profile, pointing to conduction or infiltration "
            "losses. Inspect window seals, check insulation continuity, and correct uncontrolled infiltration paths.",
        },
        "humidity": {
            "action": "Review humidity control",
            "title": "Review humidification schedule in {room}",
            "description": "Humidity drifts outside the recommended band. Verify set-points and maintenance of "
            "humidifiers/dehumidifiers.",
        },
        "winter_overheating": {
            "action": "Reduce winter overheating",
            "title": "Reduce winter overheating in {room}",
            "description": "During winter months, the room experiences overheating for {pct} of the time ({hours} hours). "
            "This indicates excessive heating or poor temperature control. Consider adjusting heating curves, "
            "implementing weather compensation, or upgrading to smart thermostatic controls with occupancy detection.",
            "benefit": "Reduce overheating by ~{pct0} of winter hours",
        },
        "summer_undercooling": {
            "action": "Address summer undercooling",
            "title": "Address summer undercooling in {room}",
            "description": "During summer months, the room is too cold for {pct} of the time ({hours} hours). "
            "This suggests overcooling, wasting energy and reducing comfort. Review cooling setpoints, consider "
            "raising temperature targets, or implement adaptive comfort strategies that allow higher temperatures during summer.",
            "benefit": "Eliminate {pct0} of overcooling hours, reducing cooling energy",
        },
        "winter_solar_gain": {
            "action": "Improve winter solar heat gain",
            "title": "Improve winter solar heat gain in {room}",
            "description": "In winter, high solar radiation is available for {pct} of the time ({hours} hours) when the "
            "room is cold. This represents missed passive heating opportunities. Consider removing or automating window "
            "coverings to allow solar gains during sunny winter days, or reviewing shading schedules to maximize natural heating.",
            "benefit": "Potential heating energy offset: ~{kwh} kWh/winter",
        },
        "summer_solar_excess": {
            "action": "Reduce excessive solar heat gains",
            "title": "Reduce excessive solar heat gains in {room}",
            "description": "During summer, excessive solar radiation contributes to overheating for {pct} of the time "
            "({hours} hours). This increases cooling demand and reduces comfort. Implement external shading (automated "
            "blinds, louvers, or films), increase vegetation shading, or consider electrochromic glazing to block solar "
            "gains during peak hours.",
            "benefit": "Potential cooling load reduction: ~{kwh} kWh/summer",
        },
    },
    "da": {
        "ventilation": {
            "action": "Øg ventilationen",
            "title": "Øg ventilationen i {room}",
            "description": "De målte CO₂-niveauer viser, at luftskiftet i brugstiden er utilstrækkeligt. Overvej at "
            "indregulere ventilationsanlægget, forlænge driftstiderne eller etablere behovsstyret ventilation.",
            "benefit": "+{gain} procentpoint CO₂-overholdelse ved {ach} luftskifter i timen",
        },
        "solar_shading": {
            "action": "Etabler solafskærmning",
            "title": "Etabler solafskærmning i {room}",
            "description": "Indetemperaturen følger solindstrålingen tæt. Automatisk styrede persienner, udvendige "
            "lameller eller solafskærmende glas kan begrænse varmetilskuddet, når solen står højest.",
            "benefit": "+{gain} procentpoint temperaturoverholdelse",
        },
        "envelope": {
            "action": "Forbedr klimaskærmens tæthed",
            "title": "Forbedr klimaskærmens tæthed i {room}",
            "description": "Indetemperaturen følger udetemperaturen, hvilket peger på varmetab gennem klimaskærmen "
            "eller utætheder. Efterse vinduernes tætningslister, kontroller isoleringen og udbedr utætheder.",
        },
        "humidity": {
            "action": "Gennemgå fugtforholdene",
            "title": "Gennemgå fugtforholdene i {room}",
            "description": "Luftfugtigheden ligger ofte uden for det anbefalede interval. Kontroller ventilationens "
            "driftstider og indstillinger samt eventuelle befugtere eller affugtere.",
        },
        "winter_overheating": {
            "action": "Reducer overtemperatur i fyringssæsonen",
            "title": "Reducer overtemperatur i fyringssæsonen i {room}",
            "description": "I fyringssæsonen er lokalet for varmt {pct} af tiden ({hours} timer). Det tyder på for høj "
            "varmetilførsel eller utilstrækkelig temperaturregulering. Overvej at justere varmekurven, indføre "
            "udetemperaturkompensering eller termostatstyring med tilstedeværelsesregistrering.",
            "benefit": "Overtemperaturen kan reduceres med op til ca. {pct0} af timerne i fyringssæsonen",
        },
        "summer_undercooling": {
            "action": "Undgå for lave temperaturer om sommeren",
            "title": "Undgå for lave temperaturer om sommeren i {room}",
            "description": "I sommerhalvåret er lokalet for koldt {pct} af tiden ({hours} timer). Det kan skyldes "
            "overkøling eller for kraftig ventilation med kold udeluft. Gennemgå setpunkterne for køling og ventilation.",
            "benefit": "Fjerner op til {pct0} af timerne med for lav temperatur",
        },
        "winter_solar_gain": {
            "action": "Udnyt solvarmen bedre om vinteren",
            "title": "Udnyt solvarmen bedre om vinteren i {room}",
            "description": "Om vinteren er der kraftig solindstråling {pct} af tiden ({hours} timer), mens lokalet er "
            "koldt. Det er et uudnyttet passivt varmetilskud. Overvej automatisk styret solafskærmning, så solen kan "
            "varme lokalet på solrige vinterdage.",
            "benefit": "Mulig besparelse på opvarmning: ca. {kwh} kWh pr. vinter",
        },
        "summer_solar_excess": {
            "action": "Begræns solvarmen om sommeren",
            "title": "Begræns solvarmen om sommeren i {room}",
            "description": "Om sommeren bidrager kraftig solindstråling til overtemperatur {pct} af tiden ({hours} "
            "timer), hvilket forringer komforten. Etabler udvendig solafskærmning (automatiske persienner, lameller "
            "eller solfilm), skygge fra beplantning, eller overvej solafskærmende glas.",
            "benefit": "Mulig reduktion af varmebelastningen: ca. {kwh} kWh pr. sommer",
        },
    },
}


def _number(value: Optional[float], digits: int, language: str) -> str:
    if value is None:
        return "–"
    text = f"{value:,.{digits}f}"
    if language == "da":
        text = text.replace(",", "\u00a0").replace(".", ",").replace("\u00a0", ".")
    return text


def _percent(value: Optional[float], digits: int, language: str) -> str:
    return f"{_number(value, digits, language)}\u00a0%" if language == "da" else f"{_number(value, digits, language)}%"


class SmartRecommendationsModel:
    """
    Rule-based recommendations for the report. Texts come from
    :data:`RECOMMENDATION_TEXTS` in the requested language ("en" or "da").
    """

    def __init__(self, language: str = "en") -> None:
        self.language = language if language in RECOMMENDATION_TEXTS else "en"

    def _make(
        self,
        key: str,
        rec_type: RecommendationType,
        priority: str,
        room_name: str,
        params: Optional[Dict[str, Optional[float]]] = None,
        evidence: Optional[Dict[str, float]] = None,
        with_benefit: bool = True,
    ) -> SmartRecommendation:
        lang = self.language
        texts = RECOMMENDATION_TEXTS[lang][key]
        p = params or {}
        fmt = {
            "room": room_name,
            "gain": _number(p.get("gain"), 1, lang),
            "ach": _number(p.get("ach"), 2, lang),
            "pct": _percent(p.get("pct"), 1, lang),
            "pct0": _percent(p.get("pct"), 0, lang),
            "hours": _number(p.get("hours"), 0, lang),
            "kwh": _number(p.get("kwh"), 0, lang),
        }
        benefit = texts["benefit"].format(**fmt) if with_benefit and "benefit" in texts else None
        return SmartRecommendation(
            title=texts["title"].format(**fmt),
            type=rec_type,
            priority=priority,
            description=texts["description"].format(**fmt),
            expected_benefit=benefit,
            evidence=evidence,
            key=key,
            action=texts["action"],
        )

    def _ventilation_recommendation(
        self,
        room_name: str,
        co2_compliance: Optional[float],
        ventilation_result: Optional[VentilationRateResult],
        scenarios: ScenarioImpactSummary,
    ) -> Optional[SmartRecommendation]:
        if ventilation_result is None:
            return None

        # Measured CO2 during use decides. The decay-based air change rate is only a
        # fallback: decays mostly happen after hours, when mechanical ventilation is
        # often off, so a low value alone does not show a problem during lessons.
        if co2_compliance is not None:
            need_upgrade = co2_compliance < 90.0
        else:
            need_upgrade = ventilation_result.ach < 2.0
        if not need_upgrade:
            return None

        scenario = scenarios.ventilation
        gain = scenario.metrics.get("co2_compliance_gain") if scenario else None
        return self._make(
            "ventilation",
            RecommendationType.VENTILATION,
            "high" if (co2_compliance or 100.0) < 80.0 else "medium",
            room_name,
            {"gain": gain, "ach": scenario.metrics.get("target_ach") if scenario else None},
            {"ach": ventilation_result.ach, "co2_compliance": co2_compliance or 0.0},
            with_benefit=bool(gain),
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
        gain = scenario.metrics.get("temp_compliance_gain") if scenario else None
        return self._make(
            "solar_shading",
            RecommendationType.SOLAR_SHADING,
            "medium",
            room_name,
            {"gain": gain},
            {"temp_vs_solar_corr": correlations.temperature_vs_solar or 0.0, "temp_compliance": temp_compliance},
            with_benefit=bool(gain),
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
        return self._make(
            "envelope",
            RecommendationType.ENVELOPE,
            "medium",
            room_name,
            evidence={"temp_vs_outdoor_corr": correlations.temperature_vs_outdoor or 0.0, "temp_compliance": temp_compliance},
        )

    def _operational_recommendation(
        self,
        room_name: str,
        humidity_compliance: Optional[float],
    ) -> Optional[SmartRecommendation]:
        if humidity_compliance is None or humidity_compliance > 90.0:
            return None
        return self._make(
            "humidity", RecommendationType.OPERATIONAL, "low", room_name,
            evidence={"humidity_compliance": humidity_compliance},
        )

    def _winter_overheating_recommendation(
        self,
        room_name: str,
        correlations: ClimateCorrelationResult,
    ) -> Optional[SmartRecommendation]:
        """Generate recommendation for winter overheating issues."""
        seasonal = correlations.seasonal_thermal
        if seasonal is None or seasonal.winter_overheating_percentage is None:
            return None
        # Threshold: significant overheating if >10% of winter hours are too hot
        if seasonal.winter_overheating_percentage < 10.0:
            return None
        return self._make(
            "winter_overheating",
            RecommendationType.SEASONAL_CONTROL,
            "high" if seasonal.winter_overheating_percentage > 25.0 else "medium",
            room_name,
            {"pct": seasonal.winter_overheating_percentage, "hours": seasonal.winter_overheating_hours},
            {
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
        seasonal = correlations.seasonal_thermal
        if seasonal is None or seasonal.summer_undercooling_percentage is None:
            return None
        # Threshold: significant undercooling if >10% of summer hours are too cold
        if seasonal.summer_undercooling_percentage < 10.0:
            return None
        return self._make(
            "summer_undercooling",
            RecommendationType.SEASONAL_CONTROL,
            "medium" if seasonal.summer_undercooling_percentage > 20.0 else "low",
            room_name,
            {"pct": seasonal.summer_undercooling_percentage, "hours": seasonal.summer_undercooling_hours},
            {
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
        solar = correlations.solar_gain_utilization
        if solar is None or solar.winter_solar_gain_opportunity_percentage is None:
            return None
        # Threshold: significant missed opportunity if >15% of winter hours
        if solar.winter_solar_gain_opportunity_percentage < 15.0:
            return None
        kwh = solar.winter_missed_heating_offset_kwh
        return self._make(
            "winter_solar_gain",
            RecommendationType.SOLAR_MANAGEMENT,
            "medium" if solar.winter_solar_gain_opportunity_percentage > 30.0 else "low",
            room_name,
            {"pct": solar.winter_solar_gain_opportunity_percentage, "hours": solar.winter_solar_gain_opportunity_hours, "kwh": kwh},
            {
                "winter_solar_opportunity_pct": solar.winter_solar_gain_opportunity_percentage,
                "winter_solar_opportunity_hours": solar.winter_solar_gain_opportunity_hours,
                "winter_missed_heating_kwh": kwh,
                "winter_avg_solar": solar.winter_avg_solar_radiation,
            },
            with_benefit=bool(kwh and kwh > 0),
        )

    def _solar_excess_recommendation(
        self,
        room_name: str,
        correlations: ClimateCorrelationResult,
    ) -> Optional[SmartRecommendation]:
        """Generate recommendation for excess solar gains in summer."""
        solar = correlations.solar_gain_utilization
        if solar is None or solar.summer_excess_solar_percentage is None:
            return None
        # Threshold: significant excess if >15% of summer hours
        if solar.summer_excess_solar_percentage < 15.0:
            return None
        kwh = solar.summer_excess_cooling_load_kwh
        return self._make(
            "summer_solar_excess",
            RecommendationType.SOLAR_MANAGEMENT,
            "high" if solar.summer_excess_solar_percentage > 30.0 else "medium",
            room_name,
            {"pct": solar.summer_excess_solar_percentage, "hours": solar.summer_excess_solar_hours, "kwh": kwh},
            {
                "summer_excess_solar_pct": solar.summer_excess_solar_percentage,
                "summer_excess_solar_hours": solar.summer_excess_solar_hours,
                "summer_excess_cooling_kwh": kwh,
                "summer_avg_solar": solar.summer_avg_solar_radiation,
            },
            with_benefit=bool(kwh and kwh > 0),
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
