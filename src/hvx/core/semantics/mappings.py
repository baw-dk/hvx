"""
Mappings between the HVX data model and IFC 4 / Brick 1.4.

Every Brick class referenced here is checked against the official Brick 1.4
ontology in ``tests/test_semantics.py``; every ``ieq:`` class must be declared
in ``ontology/hvx_ieq.ttl``. IFC names are checked against the IFC4 schema
shipped with IfcOpenShell. Edit the tables, not the exporters, to change how
the model maps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from ..enums import MetricType, RoomType, SpatialEntityType


@dataclass(frozen=True)
class SpatialMapping:
    """How a spatial level maps onto IFC and Brick."""

    ifc_class: Optional[str]
    brick_class: str


@dataclass(frozen=True)
class PointMapping:
    """How a measured parameter maps onto a Brick point and an IFC sensor."""

    brick_class: str
    ifc_sensor_type: Optional[str]  # IfcSensorTypeEnum (IFC4)
    unit: str  # QUDT unit CURIE
    quantity: Optional[str] = None  # Brick/QUDT quantity CURIE, informative


# ---------------------------------------------------------------------------
# Spatial hierarchy
# ---------------------------------------------------------------------------
# IFC has no portfolio concept (an IfcProject is one design context, not a
# collection of operated assets), so a Portfolio maps to Brick only.
SPATIAL_MAPPINGS: Dict[SpatialEntityType, SpatialMapping] = {
    SpatialEntityType.PORTFOLIO: SpatialMapping(None, "brick:Portfolio"),
    SpatialEntityType.BUILDING: SpatialMapping("IfcBuilding", "brick:Building"),
    SpatialEntityType.FLOOR: SpatialMapping("IfcBuildingStorey", "brick:Floor"),
    SpatialEntityType.ROOM: SpatialMapping("IfcSpace", "brick:Room"),
    SpatialEntityType.ZONE: SpatialMapping("IfcZone", "brick:Zone"),
}

# ---------------------------------------------------------------------------
# Room usage -> Brick class
# ---------------------------------------------------------------------------
# Brick 1.4 lacks several space types that matter for IEQ (classrooms, patient
# rooms, dwellings...). Those are provided by the ieq: extension ontology as
# subclasses of the nearest Brick class.
ROOM_TYPE_BRICK_CLASS: Dict[RoomType, str] = {
    RoomType.CLASSROOM: "ieq:Classroom",
    RoomType.LECTURE_HALL: "ieq:Lecture_Hall",
    RoomType.MEETING_ROOM: "brick:Conference_Room",
    RoomType.CONFERENCE_ROOM: "brick:Conference_Room",
    RoomType.OPEN_OFFICE: "brick:Open_Office",
    RoomType.PRIVATE_OFFICE: "brick:Enclosed_Office",
    RoomType.HOT_DESK: "brick:Open_Office",
    RoomType.LOBBY: "brick:Lobby",
    RoomType.CORRIDOR: "brick:Hallway",
    RoomType.LABORATORY: "brick:Laboratory",
    RoomType.CLEANROOM: "ieq:Cleanroom",
    RoomType.OPERATING_ROOM: "ieq:Operating_Room",
    RoomType.PATIENT_ROOM: "ieq:Patient_Room",
    RoomType.HOTEL_ROOM: "ieq:Guest_Room",
    RoomType.APARTMENT: "ieq:Dwelling",
    RoomType.KITCHEN: "brick:Food_Service_Room",
    RoomType.CAFETERIA: "brick:Cafeteria",
    RoomType.CANTEEN: "brick:Cafeteria",
    RoomType.SERVER_ROOM: "brick:Server_Room",
    RoomType.DATA_HALL: "brick:Server_Room",
    RoomType.STORAGE: "brick:Storage_Room",
    RoomType.WAREHOUSE_BAY: "brick:Storage_Room",
    RoomType.PARKING_ZONE: "brick:Parking_Space",
    RoomType.RESTROOM: "brick:Restroom",
    RoomType.SHOWER: "brick:Ablutions_Room",
    RoomType.GYM: "brick:Exercise_Room",
    RoomType.AUDITORIUM: "brick:Auditorium",
    RoomType.RETAIL_ZONE: "brick:Retail_Room",
    RoomType.OTHER: "brick:Room",
}

# ---------------------------------------------------------------------------
# Measured parameters -> Brick point / IFC sensor
# ---------------------------------------------------------------------------
_TEMP = PointMapping("brick:Zone_Air_Temperature_Sensor", "TEMPERATURESENSOR", "unit:DEG_C", "qudtqk:Temperature")
_CO2 = PointMapping("brick:CO2_Level_Sensor", "CO2SENSOR", "unit:PPM", "brick:CO2_Concentration")
_RH = PointMapping("brick:Zone_Air_Humidity_Sensor", "HUMIDITYSENSOR", "unit:PERCENT_RH", "qudtqk:RelativeHumidity")
_LUX = PointMapping("brick:Illuminance_Sensor", "LIGHTSENSOR", "unit:LUX", "qudtqk:Illuminance")
_SPL = PointMapping("ieq:Sound_Pressure_Level_Sensor", "SOUNDSENSOR", "unit:DeciB", "ieq:Sound_Pressure_Level")

POINT_MAPPINGS: Dict[MetricType, PointMapping] = {
    MetricType.TEMPERATURE: _TEMP,
    MetricType.CO2: _CO2,
    MetricType.HUMIDITY: _RH,
    MetricType.ILLUMINANCE: _LUX,
    MetricType.LUX: _LUX,
    MetricType.LIGHT_LEVEL: _LUX,
    MetricType.NOISE: _SPL,
    MetricType.SOUND_PRESSURE: _SPL,
    MetricType.VOC: PointMapping("brick:TVOC_Level_Sensor", "GASSENSOR", "unit:MicroGM-PER-M3", "brick:TVOC_Concentration"),
    MetricType.PM25: PointMapping("brick:PM2.5_Sensor", "GASSENSOR", "unit:MicroGM-PER-M3", "brick:PM2.5_Concentration"),
    MetricType.PM10: PointMapping("brick:PM10_Sensor", "GASSENSOR", "unit:MicroGM-PER-M3", "brick:PM10_Concentration"),
    MetricType.OCCUPANCY: PointMapping("brick:Occupancy_Count_Sensor", "MOVEMENTSENSOR", "unit:NUM", "brick:Occupancy_Count"),
    MetricType.MOTION: PointMapping("brick:Occupancy_Sensor", "MOVEMENTSENSOR", "unit:UNITLESS", "brick:Occupancy"),
    MetricType.OUTDOOR_TEMPERATURE: PointMapping("brick:Outside_Air_Temperature_Sensor", "TEMPERATURESENSOR", "unit:DEG_C", "qudtqk:Temperature"),
    MetricType.OUTDOOR_HUMIDITY: PointMapping("brick:Outside_Air_Humidity_Sensor", "HUMIDITYSENSOR", "unit:PERCENT_RH", "qudtqk:RelativeHumidity"),
    MetricType.SOLAR_IRRADIANCE: PointMapping("brick:Solar_Irradiance_Sensor", "RADIATIONSENSOR", "unit:W-PER-M2", "brick:Solar_Irradiance"),
    MetricType.TEMPERATURE_SETPOINT: PointMapping("brick:Zone_Air_Temperature_Setpoint", None, "unit:DEG_C", "qudtqk:Temperature"),
    MetricType.HUMIDITY_SETPOINT: PointMapping("brick:Zone_Air_Humidity_Setpoint", None, "unit:PERCENT_RH", "qudtqk:RelativeHumidity"),
    MetricType.CO2_SETPOINT: PointMapping("brick:CO2_Setpoint", None, "unit:PPM", "brick:CO2_Concentration"),
    MetricType.AIRFLOW: PointMapping("brick:Air_Flow_Sensor", "FLOWSENSOR", "unit:M3-PER-HR"),
    MetricType.AIRFLOW_SUPPLY: PointMapping("brick:Supply_Air_Flow_Sensor", "FLOWSENSOR", "unit:M3-PER-HR"),
    MetricType.AIRFLOW_RETURN: PointMapping("brick:Return_Air_Flow_Sensor", "FLOWSENSOR", "unit:M3-PER-HR"),
    MetricType.AIR_TEMPERATURE_SUPPLY: PointMapping("brick:Supply_Air_Temperature_Sensor", "TEMPERATURESENSOR", "unit:DEG_C"),
    MetricType.AIR_TEMPERATURE_RETURN: PointMapping("brick:Return_Air_Temperature_Sensor", "TEMPERATURESENSOR", "unit:DEG_C"),
    MetricType.DAMPER_POSITION: PointMapping("brick:Damper_Position_Sensor", None, "unit:PERCENT"),
    MetricType.VALVE_POSITION: PointMapping("brick:Valve_Position_Sensor", None, "unit:PERCENT"),
    MetricType.DIFFERENTIAL_PRESSURE: PointMapping("brick:Differential_Pressure_Sensor", "PRESSURESENSOR", "unit:PA"),
    MetricType.PRESSURE: PointMapping("brick:Pressure_Sensor", "PRESSURESENSOR", "unit:PA"),
    MetricType.ELECTRICITY: PointMapping("brick:Electric_Energy_Sensor", None, "unit:KiloW-HR"),
    MetricType.POWER: PointMapping("brick:Electric_Power_Sensor", None, "unit:KiloW"),
    MetricType.WATER_FLOW: PointMapping("brick:Water_Flow_Sensor", "FLOWSENSOR", "unit:M3-PER-HR"),
}

# Free-text column names seen in CSV exports (incl. Danish) -> canonical metric.
METRIC_ALIASES: Dict[str, MetricType] = {
    "temperature": MetricType.TEMPERATURE,
    "temp": MetricType.TEMPERATURE,
    "temperatur": MetricType.TEMPERATURE,
    "co2": MetricType.CO2,
    "co₂": MetricType.CO2,
    "humidity": MetricType.HUMIDITY,
    "relative_humidity": MetricType.HUMIDITY,
    "fugtighed": MetricType.HUMIDITY,
    "relativ fugt": MetricType.HUMIDITY,
    "illuminance": MetricType.ILLUMINANCE,
    "lux": MetricType.ILLUMINANCE,
    "lys": MetricType.ILLUMINANCE,
    "noise": MetricType.NOISE,
    "sound_pressure": MetricType.NOISE,
    "occupancy": MetricType.OCCUPANCY,
    "tilstedeværelse": MetricType.OCCUPANCY,
    "voc": MetricType.VOC,
    "tvoc": MetricType.VOC,
    "pm2_5": MetricType.PM25,
    "pm25": MetricType.PM25,
    "pm10": MetricType.PM10,
    "outdoor_temperature": MetricType.OUTDOOR_TEMPERATURE,
    "outdoor temperature": MetricType.OUTDOOR_TEMPERATURE,
    "udendørs temperatur": MetricType.OUTDOOR_TEMPERATURE,
    "outdoor_humidity": MetricType.OUTDOOR_HUMIDITY,
    "outdoor humidity": MetricType.OUTDOOR_HUMIDITY,
    "udendørs fugt": MetricType.OUTDOOR_HUMIDITY,
    "solar_radiation": MetricType.SOLAR_IRRADIANCE,
    "solar_irradiance": MetricType.SOLAR_IRRADIANCE,
    "solar irradiance": MetricType.SOLAR_IRRADIANCE,
    "solstråling": MetricType.SOLAR_IRRADIANCE,
    "global_stråling": MetricType.SOLAR_IRRADIANCE,
}


def normalize_metric_name(name: str) -> Optional[MetricType]:
    """Resolve a column/parameter name to a canonical MetricType."""
    key = str(name).strip().lower()
    if key in METRIC_ALIASES:
        return METRIC_ALIASES[key]
    try:
        return MetricType(key)
    except ValueError:
        return None


def spatial_mapping(entity_type: SpatialEntityType) -> SpatialMapping:
    return SPATIAL_MAPPINGS[entity_type]


# Free-text usages found in loaders/CSV metadata that are not RoomType values.
ROOM_USAGE_ALIASES: Dict[str, str] = {
    "office": "brick:Office",
    "meeting": "brick:Conference_Room",
    "school": "ieq:Classroom",
    "teaching": "ieq:Classroom",
    "residential": "ieq:Dwelling",
    "bedroom": "ieq:Dwelling",
    "living_room": "ieq:Dwelling",
    "toilet": "brick:Restroom",
    "wc": "brick:Restroom",
    "hallway": "brick:Hallway",
}


def brick_class_for_room_type(room_type: Optional[str]) -> str:
    """Brick (or ieq:) class for a room usage string; falls back to brick:Room."""
    if not room_type:
        return "brick:Room"
    key = str(room_type).strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return ROOM_TYPE_BRICK_CLASS[RoomType(key)]
    except (ValueError, KeyError):
        return ROOM_USAGE_ALIASES.get(key, "brick:Room")


def point_mapping(metric: str | MetricType) -> Optional[PointMapping]:
    metric_type = metric if isinstance(metric, MetricType) else normalize_metric_name(metric)
    if metric_type is None:
        return None
    return POINT_MAPPINGS.get(metric_type)


# Reverse lookups used by the importers.
BRICK_CLASS_TO_ROOM_TYPE: Dict[str, RoomType] = {}
for _room_type, _cls in ROOM_TYPE_BRICK_CLASS.items():
    BRICK_CLASS_TO_ROOM_TYPE.setdefault(_cls, _room_type)
BRICK_CLASS_TO_ROOM_TYPE.setdefault("brick:Office", RoomType.OPEN_OFFICE)

BRICK_CLASS_TO_METRIC: Dict[str, MetricType] = {}
for _metric, _pm in POINT_MAPPINGS.items():
    BRICK_CLASS_TO_METRIC.setdefault(_pm.brick_class, _metric)

IFC_SENSOR_TO_METRIC: Dict[str, MetricType] = {
    "TEMPERATURESENSOR": MetricType.TEMPERATURE,
    "CO2SENSOR": MetricType.CO2,
    "HUMIDITYSENSOR": MetricType.HUMIDITY,
    "LIGHTSENSOR": MetricType.ILLUMINANCE,
    "SOUNDSENSOR": MetricType.NOISE,
    "MOVEMENTSENSOR": MetricType.OCCUPANCY,
    "RADIATIONSENSOR": MetricType.SOLAR_IRRADIANCE,
}

__all__ = [
    "SpatialMapping",
    "PointMapping",
    "SPATIAL_MAPPINGS",
    "ROOM_TYPE_BRICK_CLASS",
    "POINT_MAPPINGS",
    "METRIC_ALIASES",
    "ROOM_USAGE_ALIASES",
    "BRICK_CLASS_TO_ROOM_TYPE",
    "BRICK_CLASS_TO_METRIC",
    "IFC_SENSOR_TO_METRIC",
    "normalize_metric_name",
    "spatial_mapping",
    "brick_class_for_room_type",
    "point_mapping",
]
