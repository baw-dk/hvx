"""
Typed IEQ requirement and assessment models.

These replace the loose ``computed_metrics`` dictionaries at the boundaries of
the system (reporting, IFC write-back, Brick export). They map onto:

* IFC 4 property sets: ``Pset_SpaceThermalRequirements``,
  ``Pset_SpaceLightingRequirements``, ``Pset_SpaceOccupancyRequirements`` and
  two extension sets for what IFC does not cover
  (``HVX_Pset_SpaceIEQRequirements``, ``HVX_Pset_IEQAssessment``). Custom
  sets must not use the reserved ``Pset_`` prefix.
* The ``ieq:`` extension of Brick (see ``ontology/hvx_ieq.ttl``).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

IEQ_REQUIREMENTS_PSET = "HVX_Pset_SpaceIEQRequirements"
IEQ_ASSESSMENT_PSET = "HVX_Pset_IEQAssessment"


class ComfortCategory(str, Enum):
    """EN 16798-1 categories, best (I) to worst (IV)."""

    I = "I"
    II = "II"
    III = "III"
    IV = "IV"

    @property
    def rank(self) -> int:
        return ["I", "II", "III", "IV"].index(self.value)

    @classmethod
    def parse(cls, value: Any) -> Optional["ComfortCategory"]:
        if value is None:
            return None
        if isinstance(value, ComfortCategory):
            return value
        text = str(value).strip().upper().replace("CATEGORY", "").replace("CAT", "").strip(" _-")
        roman = {"1": "I", "2": "II", "3": "III", "4": "IV"}.get(text, text)
        try:
            return cls(roman)
        except ValueError:
            return None

    @classmethod
    def worst(cls, *values: Optional["ComfortCategory"]) -> Optional["ComfortCategory"]:
        present = [v for v in values if v is not None]
        return max(present, key=lambda c: c.rank) if present else None


# Default parameter units used across reports and exports.
PARAMETER_UNITS: Dict[str, str] = {
    "temperature": "°C",
    "co2": "ppm",
    "humidity": "%RH",
    "illuminance": "lx",
    "noise": "dB(A)",
}


class IEQRequirements(BaseModel):
    """Design/target IEQ requirements for a space."""

    target_category: ComfortCategory = ComfortCategory.II
    standard: str = "EN 16798-1"

    temperature_min_c: Optional[float] = None
    temperature_max_c: Optional[float] = None
    temperature_winter_min_c: Optional[float] = None
    temperature_winter_max_c: Optional[float] = None
    temperature_summer_min_c: Optional[float] = None
    temperature_summer_max_c: Optional[float] = None
    humidity_min_pct: Optional[float] = Field(default=None, ge=0, le=100)
    humidity_max_pct: Optional[float] = Field(default=None, ge=0, le=100)
    co2_max_ppm: Optional[float] = Field(default=None, gt=0)
    co2_above_outdoor_max_ppm: Optional[float] = Field(default=None, gt=0)
    illuminance_min_lux: Optional[float] = Field(default=None, ge=0)
    sound_pressure_level_max_dba: Optional[float] = Field(default=None, ge=0)
    occupancy_type: Optional[str] = None
    design_occupancy: Optional[int] = Field(default=None, ge=0)
    area_per_occupant_m2: Optional[float] = Field(default=None, gt=0)

    # IFC stores humidity as IfcRatioMeasure (0..1), the model uses percent.
    def to_ifc_psets(self) -> Dict[str, Dict[str, Any]]:
        """Return ``{pset_name: {property: value}}`` with ``None`` values dropped."""

        def clean(d: Dict[str, Any]) -> Dict[str, Any]:
            return {k: v for k, v in d.items() if v is not None}

        ratio = lambda pct: None if pct is None else round(pct / 100.0, 4)  # noqa: E731
        psets = {
            "Pset_SpaceThermalRequirements": clean(
                {
                    "SpaceTemperatureMin": self.temperature_min_c,
                    "SpaceTemperatureMax": self.temperature_max_c,
                    "SpaceTemperatureWinterMin": self.temperature_winter_min_c,
                    "SpaceTemperatureWinterMax": self.temperature_winter_max_c,
                    "SpaceTemperatureSummerMin": self.temperature_summer_min_c,
                    "SpaceTemperatureSummerMax": self.temperature_summer_max_c,
                    "SpaceHumidityMin": ratio(self.humidity_min_pct),
                    "SpaceHumidityMax": ratio(self.humidity_max_pct),
                }
            ),
            "Pset_SpaceLightingRequirements": clean({"Illuminance": self.illuminance_min_lux}),
            "Pset_SpaceOccupancyRequirements": clean(
                {
                    "OccupancyType": self.occupancy_type,
                    "OccupancyNumber": self.design_occupancy,
                    "AreaPerOccupant": self.area_per_occupant_m2,
                }
            ),
            IEQ_REQUIREMENTS_PSET: clean(
                {
                    "TargetCategory": self.target_category.value,
                    "Standard": self.standard,
                    "CO2ConcentrationMax": self.co2_max_ppm,
                    "CO2AboveOutdoorMax": self.co2_above_outdoor_max_ppm,
                    "SoundPressureLevelMax": self.sound_pressure_level_max_dba,
                }
            ),
        }
        return {name: props for name, props in psets.items() if props}

    @classmethod
    def from_ifc_psets(cls, psets: Dict[str, Dict[str, Any]]) -> Optional["IEQRequirements"]:
        """Build requirements from IFC psets; returns ``None`` if nothing relevant is set."""
        thermal = psets.get("Pset_SpaceThermalRequirements", {}) or {}
        lighting = psets.get("Pset_SpaceLightingRequirements", {}) or {}
        occupancy = psets.get("Pset_SpaceOccupancyRequirements", {}) or {}
        ieq = psets.get(IEQ_REQUIREMENTS_PSET, {}) or {}
        if not (thermal or lighting or occupancy or ieq):
            return None

        def pct(value: Any) -> Optional[float]:
            if value is None:
                return None
            value = float(value)
            # Tolerate models that (incorrectly) store percent instead of ratio.
            return round(value * 100.0, 2) if value <= 1.0 else value

        occupancy_number = occupancy.get("OccupancyNumber")
        return cls(
            target_category=ComfortCategory.parse(ieq.get("TargetCategory")) or ComfortCategory.II,
            standard=ieq.get("Standard") or "EN 16798-1",
            temperature_min_c=thermal.get("SpaceTemperatureMin"),
            temperature_max_c=thermal.get("SpaceTemperatureMax"),
            temperature_winter_min_c=thermal.get("SpaceTemperatureWinterMin"),
            temperature_winter_max_c=thermal.get("SpaceTemperatureWinterMax"),
            temperature_summer_min_c=thermal.get("SpaceTemperatureSummerMin"),
            temperature_summer_max_c=thermal.get("SpaceTemperatureSummerMax"),
            humidity_min_pct=pct(thermal.get("SpaceHumidityMin")),
            humidity_max_pct=pct(thermal.get("SpaceHumidityMax")),
            co2_max_ppm=ieq.get("CO2ConcentrationMax"),
            co2_above_outdoor_max_ppm=ieq.get("CO2AboveOutdoorMax"),
            illuminance_min_lux=lighting.get("Illuminance"),
            sound_pressure_level_max_dba=ieq.get("SoundPressureLevelMax"),
            occupancy_type=occupancy.get("OccupancyType"),
            design_occupancy=int(occupancy_number) if occupancy_number is not None else None,
            area_per_occupant_m2=occupancy.get("AreaPerOccupant"),
        )


class ParameterAssessment(BaseModel):
    """Result for one IEQ parameter (temperature, CO2, ...)."""

    parameter: str
    unit: Optional[str] = None
    compliance_pct: Optional[float] = Field(
        default=None, description="Share of samples meeting the target category"
    )
    category_compliance_pct: Dict[str, float] = Field(default_factory=dict)
    mean: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    time_above_pct: Optional[float] = None
    time_below_pct: Optional[float] = None
    samples: Optional[int] = None


class IEQAssessment(BaseModel):
    """Typed EN 16798-1 style assessment of one space for one period."""

    entity_id: str
    standard: str = "EN 16798-1"
    season: Optional[str] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    target_category: ComfortCategory = ComfortCategory.II
    achieved_category: Optional[ComfortCategory] = None
    compliance_pct: Optional[float] = Field(
        default=None, description="Share of time meeting the target category"
    )
    time_in_category_pct: Dict[str, float] = Field(default_factory=dict)
    parameters: Dict[str, ParameterAssessment] = Field(default_factory=dict)
    samples: Optional[int] = None

    @property
    def meets_target(self) -> Optional[bool]:
        if self.achieved_category is None:
            return None
        return self.achieved_category.rank <= self.target_category.rank

    @classmethod
    def from_en16798(
        cls,
        entity_id: str,
        result: Dict[str, Any],
        target_category: ComfortCategory = ComfortCategory.II,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
        samples: Optional[int] = None,
    ) -> "IEQAssessment":
        """Parse the dictionary returned by ``standards.en16798.analysis.run``."""
        target = target_category.value
        parameters: Dict[str, ParameterAssessment] = {}
        for name, metrics in (result.get("parameter_metrics") or {}).items():
            if not isinstance(metrics, dict):
                continue
            per_cat = {
                cat: float(metrics[f"category_{cat}_compliance_rate"])
                for cat in ("I", "II", "III", "IV")
                if metrics.get(f"category_{cat}_compliance_rate") is not None
            }
            parameters[name] = ParameterAssessment(
                parameter=name,
                unit=PARAMETER_UNITS.get(name),
                compliance_pct=per_cat.get(target),
                category_compliance_pct=per_cat,
                mean=metrics.get("mean_value"),
                minimum=metrics.get("min_value"),
                maximum=metrics.get("max_value"),
                time_above_pct=metrics.get("time_above_threshold_pct"),
                time_below_pct=metrics.get("time_below_threshold_pct"),
            )

        time_in = {
            cat: float(result[f"time_in_category_{cat}_pct"])
            for cat in ("I", "II", "III", "IV")
            if result.get(f"time_in_category_{cat}_pct") is not None
        }
        if result.get("time_out_of_all_categories_pct") is not None:
            time_in["out"] = float(result["time_out_of_all_categories_pct"])

        overall = (result.get("category_compliance_rates") or {}).get(target)
        return cls(
            entity_id=entity_id,
            season=result.get("season"),
            period_start=period_start,
            period_end=period_end,
            target_category=target_category,
            achieved_category=ComfortCategory.parse(result.get("achieved_category")),
            compliance_pct=float(overall) if overall is not None else None,
            time_in_category_pct=time_in,
            parameters=parameters,
            samples=samples or result.get("total_data_points"),
        )

    def to_ifc_pset(self) -> Dict[str, Dict[str, Any]]:
        """Summary as an IFC property set (for write-back onto ``IfcSpace``)."""
        props: Dict[str, Any] = {
            "Standard": self.standard,
            "Season": self.season,
            "TargetCategory": self.target_category.value,
            "AchievedCategory": self.achieved_category.value if self.achieved_category else None,
            "CompliancePercent": self.compliance_pct,
            "MeetsTarget": self.meets_target,
            "PeriodStart": self.period_start.isoformat() if self.period_start else None,
            "PeriodEnd": self.period_end.isoformat() if self.period_end else None,
        }
        for name, param in self.parameters.items():
            if param.compliance_pct is not None:
                props[f"{name.capitalize()}CompliancePercent"] = round(param.compliance_pct, 2)
        return {IEQ_ASSESSMENT_PSET: {k: v for k, v in props.items() if v is not None}}


__all__ = [
    "ComfortCategory",
    "IEQRequirements",
    "ParameterAssessment",
    "IEQAssessment",
    "PARAMETER_UNITS",
    "IEQ_REQUIREMENTS_PSET",
    "IEQ_ASSESSMENT_PSET",
]
