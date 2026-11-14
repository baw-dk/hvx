"""
Bindings between live points and room parameters.

The binding lives on the data model: a room's :class:`SensorDefinition`
carries a :class:`SensorSource` of type ``api``/``stream`` whose config holds
``{"source": <source name>, "point": <point id>}``. So a Brick or IFC import,
a site YAML file or the Home Assistant integration all bind the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional

from hvx.core.entities import Room
from hvx.core.enums import MetricType, SensorSourceType
from hvx.core.metering import SensorDefinition, SensorSource
from hvx.core.semantics.mappings import normalize_metric_name, point_mapping

DEFAULT_SOURCE = "default"


@dataclass(frozen=True)
class PointBinding:
    room_id: str
    parameter: str  # canonical metric name, e.g. "co2"
    point: str  # id in the source, e.g. "sensor.meeting_co2"
    source: str = DEFAULT_SOURCE


def bind(room: Room, parameter: str, point: str, source: str = DEFAULT_SOURCE, unit: Optional[str] = None) -> SensorDefinition:
    """Attach a live point to ``room`` for ``parameter``."""
    metric = normalize_metric_name(parameter) or MetricType.OTHER
    mapping = point_mapping(metric)
    sensor = SensorDefinition(
        id=f"{room.id}:{metric.value}:{point}",
        spatial_entity_id=room.id,
        metric=metric,
        parameter=metric.value,
        unit=unit or (mapping.unit.split(":", 1)[1] if mapping else ""),
        name=point,
        sources=[SensorSource(id=f"{source}:{point}", type=SensorSourceType.API, config={"source": source, "point": point})],
    )
    room.load_sensor(sensor)
    return sensor


def discover_bindings(rooms: Iterable[Room]) -> List[PointBinding]:
    out: List[PointBinding] = []
    for room in rooms:
        for group in room.sensor_groups.values():
            for sensor in group.sensors:
                for src in sensor.sources:
                    point = src.config.get("point") or src.config.get("entity_id")
                    if src.type in (SensorSourceType.API, SensorSourceType.STREAM) and point:
                        out.append(PointBinding(room.id, sensor.parameter, str(point), str(src.config.get("source", DEFAULT_SOURCE))))
    return out


def by_source(bindings: Iterable[PointBinding]) -> Dict[str, List[PointBinding]]:
    grouped: Dict[str, List[PointBinding]] = {}
    for b in bindings:
        grouped.setdefault(b.source, []).append(b)
    return grouped


def bind_from_mapping(rooms: Mapping[str, Room], mapping: Mapping[str, Mapping[str, str]], source: str = DEFAULT_SOURCE) -> List[PointBinding]:
    """``mapping = {room_id: {parameter: point}}`` -> bindings attached to the rooms."""
    for room_id, params in mapping.items():
        for parameter, point in params.items():
            if point:
                bind(rooms[room_id], parameter, point, source)
    return discover_bindings(rooms[r] for r in mapping)


__all__ = ["PointBinding", "bind", "discover_bindings", "by_source", "bind_from_mapping", "DEFAULT_SOURCE"]
