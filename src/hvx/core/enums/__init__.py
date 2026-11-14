# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Enum package

Provides grouped enum definitions for spatial, sensor, rules, analysis, and access domains.
"""

from .spatial import (
    SpatialEntityType,
    VentilationType,
    BuildingType,
    RoomType,
    OpeningHoursProfile,
)
from .sensors import MetricType, TimeSeriesType, SensorSourceType, PointType
from .rules import RuleOperator, Season, StandardType, DynamicFunctionType
from .analysis import AggregatorType, AnalysisStatus, AnalysisType, ModelType
from .access import PermissionScope, UserRole
from .energy import EnergyCarrier, FuelUnit, PrimaryEnergyScope
from .country import CountryCode
from .timeseries import TimeResolution, AggregationMethod, DataCategory

__all__ = [
    "SpatialEntityType",
    "VentilationType",
    "BuildingType",
    "RoomType",
    "OpeningHoursProfile",
    "MetricType",
    "TimeSeriesType",
    "SensorSourceType",
    "PointType",
    "RuleOperator",
    "Season",
    "StandardType",
    "DynamicFunctionType",
    "AggregatorType",
    "AnalysisStatus",
    "AnalysisType",
    "ModelType",
    "PermissionScope",
    "UserRole",
    "EnergyCarrier",
    "FuelUnit",
    "PrimaryEnergyScope",
    "CountryCode",
    "TimeResolution",
    "AggregationMethod",
    "DataCategory",
]
