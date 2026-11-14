"""
Building simulation model implementations.
"""

from .occupancy import OccupancyCalculator, OccupancyPattern
from .ventilation import VentilationCalculator, VentilationRateResult
from .rc_thermal import RCThermalModel, RCModelParameters, RCModelResult, RCModelType
from .real_epc import calculate_epc_rating
from .correlations import ClimateCorrelationModel, ClimateCorrelationResult
from .scenario import ScenarioImpactModel, ScenarioImpactSummary, ScenarioResult
from .recommendations import (
    SmartRecommendationsModel,
    SmartRecommendation,
    RecommendationType,
)
__all__ = [
    "OccupancyCalculator",
    "OccupancyPattern",
    "VentilationCalculator",
    "VentilationRateResult",
    "RCThermalModel",
    "RCModelParameters",
    "RCModelResult",
    "RCModelType",
    "calculate_epc_rating",
    "ClimateCorrelationModel",
    "ClimateCorrelationResult",
    "ScenarioImpactModel",
    "ScenarioImpactSummary",
    "ScenarioResult",
    "SmartRecommendationsModel",
    "SmartRecommendation",
    "RecommendationType",
]
