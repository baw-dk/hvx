# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
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
