"""
IFC (IFC2X3 / IFC4 / IFC4X3) import and IEQ write-back via IfcOpenShell.

Import maps::

    IfcProject         -> Portfolio (metadata: ifc_project_id, ifc_file, schema)
    IfcBuilding        -> Building  (Pset_BuildingCommon.YearOfConstruction / OccupancyType)
    IfcBuildingStorey  -> Floor     (ordered by Elevation)
    IfcSpace           -> Room      (Qto_SpaceBaseQuantities, requirement Psets)
    IfcSensor          -> SensorDefinition on the containing space

Every entity keeps its ``GlobalId`` in ``ifc_guid`` and uses it as its id, so
results can be written back onto the same objects later
(:func:`write_ieq_to_ifc`).

IfcOpenShell is an optional dependency (``pip install hvx[ifc]``).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional, Union

from ..enums import BuildingType, MetricType, RoomType, SpatialEntityType
from .ieq import IEQAssessment, IEQRequirements
from .mappings import IFC_SENSOR_TO_METRIC, point_mapping
from .types import SemanticImportResult

if TYPE_CHECKING:  # pragma: no cover
    from ..entities import Room


def _ifcopenshell():
    try:
        import ifcopenshell
        import ifcopenshell.util.element  # noqa: F401
        import ifcopenshell.util.unit  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "IFC support requires IfcOpenShell (pip install 'ifcopenshell>=0.8')"
        ) from exc
    return ifcopenshell


def _slug(text: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").strip().lower()).strip("_")


def _match_enum(enum_cls, *candidates: Optional[str]):
    values = {e.value: e for e in enum_cls}
    for candidate in candidates:
        slug = _slug(candidate)
        if slug in values:
            return values[slug]
    return None


def _first(psets: Mapping[str, Mapping[str, Any]], pset: str, *props: str) -> Optional[Any]:
    data = psets.get(pset) or {}
    for prop in props:
        if data.get(prop) is not None:
            return data[prop]
    return None


def load_ifc(path: Union[str, Path], portfolio_name: Optional[str] = None) -> SemanticImportResult:
    """Load the spatial structure and sensors of an IFC file."""
    ifcopenshell = _ifcopenshell()
    from ifcopenshell.util import element as uel
    from ifcopenshell.util import unit as uunit

    from ..entities import Building, Floor, Portfolio, Room
    from ..metering import SensorDefinition

    model = ifcopenshell.open(str(path))
    warnings: list[str] = []
    # IFC assigns length, area and volume units independently (e.g. mm + m²).
    unit_scale = {
        1: uunit.calculate_unit_scale(model, "LENGTHUNIT"),
        2: uunit.calculate_unit_scale(model, "AREAUNIT"),
        3: uunit.calculate_unit_scale(model, "VOLUMEUNIT"),
    }

    def psets_of(entity) -> Dict[str, Dict[str, Any]]:
        return uel.get_psets(entity) or {}

    def scaled(value: Optional[float], power: int) -> Optional[float]:
        return None if value is None else round(float(value) * unit_scale[power], 4)

    def first_present(*values: Optional[float]) -> Optional[float]:
        return next((v for v in values if v is not None), None)

    projects = model.by_type("IfcProject")
    project = projects[0] if projects else None
    portfolio = Portfolio(
        id=project.GlobalId if project else "ifc_portfolio",
        name=portfolio_name or (project.LongName or project.Name if project else None) or Path(path).stem,
        type=SpatialEntityType.PORTFOLIO,
        ifc_guid=project.GlobalId if project else None,
        metadata={
            "ifc_project_id": project.GlobalId if project else None,
            "ifc_file": str(path),
            "ifc_schema": model.schema,
        },
    )

    buildings: Dict[str, Building] = {}
    for ifc_building in model.by_type("IfcBuilding"):
        psets = psets_of(ifc_building)
        year = _first(psets, "Pset_BuildingCommon", "YearOfConstruction")
        building_type = _match_enum(BuildingType, _first(psets, "Pset_BuildingCommon", "OccupancyType"), ifc_building.ObjectType)
        address = getattr(ifc_building, "BuildingAddress", None)
        try:
            year_int = int(str(year)[:4]) if year else None
        except ValueError:
            year_int = None
        b = Building(
            id=ifc_building.GlobalId,
            name=ifc_building.LongName or ifc_building.Name or ifc_building.GlobalId,
            ifc_guid=ifc_building.GlobalId,
            parent_ids=[portfolio.id],
            building_type=building_type.value if building_type else None,
            year_built=year_int,
            city=getattr(address, "Town", None) if address else None,
            area_m2=scaled(_first(psets, "Qto_BuildingBaseQuantities", "NetFloorArea", "GrossFloorArea"), 2),
        )
        buildings[b.id] = b
        portfolio.add_building(b.id)

    floors: Dict[str, Floor] = {}
    storeys_by_building: Dict[str, list] = {}
    for storey in model.by_type("IfcBuildingStorey"):
        parent = uel.get_aggregate(storey)
        bid = parent.GlobalId if parent is not None and parent.is_a("IfcBuilding") else None
        if bid is None:
            warnings.append(f"Storey {storey.GlobalId} is not aggregated into a building.")
        storeys_by_building.setdefault(bid or "", []).append(storey)

    for bid, storeys in storeys_by_building.items():
        storeys.sort(key=lambda s: (s.Elevation is None, s.Elevation or 0.0))
        below = sum(1 for s in storeys if (s.Elevation or 0.0) < 0)
        for index, storey in enumerate(storeys):
            f = Floor(
                id=storey.GlobalId,
                name=storey.LongName or storey.Name or storey.GlobalId,
                ifc_guid=storey.GlobalId,
                building_id=bid or None,
                parent_ids=[bid] if bid else [],
                floor_number=index - below,
            )
            floors[f.id] = f
            if bid in buildings:
                buildings[bid].add_floor(f.id)

    rooms: Dict[str, Room] = {}
    for space in model.by_type("IfcSpace"):
        psets = psets_of(space)
        parent = uel.get_aggregate(space) or uel.get_container(space)
        floor_id = building_id = None
        if parent is not None and parent.is_a("IfcBuildingStorey"):
            floor_id = parent.GlobalId
            building_id = floors[floor_id].building_id if floor_id in floors else None
        elif parent is not None and parent.is_a("IfcBuilding"):
            building_id = parent.GlobalId
        else:
            warnings.append(f"Space {space.GlobalId} has no storey or building parent.")

        requirements = IEQRequirements.from_ifc_psets(psets)
        occupancy_type = _first(psets, "Pset_SpaceOccupancyRequirements", "OccupancyType")
        room_type = _match_enum(RoomType, occupancy_type, space.ObjectType, space.LongName, space.Name)
        occupancy = _first(psets, "Pset_SpaceOccupancyRequirements", "OccupancyNumber")
        room = Room(
            id=space.GlobalId,
            name=space.LongName or space.Name or space.GlobalId,
            ifc_guid=space.GlobalId,
            floor_id=floor_id,
            building_id=building_id,
            parent_ids=[floor_id or building_id] if (floor_id or building_id) else [],
            room_type=room_type.value if room_type else None,
            area_m2=first_present(
                scaled(_first(psets, "Qto_SpaceBaseQuantities", "NetFloorArea", "GrossFloorArea"), 2),
                scaled(_first(psets, "Pset_SpaceCommon", "NetPlannedArea", "GrossPlannedArea"), 2),
            ),
            volume_m3=scaled(_first(psets, "Qto_SpaceBaseQuantities", "NetVolume", "GrossVolume"), 3),
            design_occupancy=int(occupancy) if occupancy is not None else None,
            ieq_requirements=requirements,
            metadata={"ifc_name": space.Name, "ifc_long_name": space.LongName},
        )
        rooms[room.id] = room
        if floor_id in floors:
            floors[floor_id].add_room(room.id)
        if building_id in buildings:
            buildings[building_id].add_room(room.id)

    for sensor in model.by_type("IfcSensor"):
        container = uel.get_container(sensor)
        if container is None or container.GlobalId not in rooms:
            continue
        predefined = uel.get_predefined_type(sensor) or "NOTDEFINED"
        metric = IFC_SENSOR_TO_METRIC.get(predefined, MetricType.OTHER)
        mapping = point_mapping(metric)
        rooms[container.GlobalId].load_sensor(
            SensorDefinition(
                id=sensor.GlobalId,
                spatial_entity_id=container.GlobalId,
                metric=metric,
                parameter=metric.value,
                unit=mapping.unit.split(":", 1)[1] if mapping else "",
                name=sensor.Name,
                ifc_guid=sensor.GlobalId,
                metadata={"ifc_predefined_type": predefined},
            )
        )

    return SemanticImportResult(
        portfolio=portfolio,
        buildings=buildings,
        floors=floors,
        rooms=rooms,
        warnings=warnings,
        source=str(path),
    )


def write_ieq_to_ifc(
    source: Union[str, Path, Any],
    rooms: Mapping[str, "Room"],
    assessments: Optional[Mapping[str, IEQAssessment]] = None,
    output_path: Optional[Union[str, Path]] = None,
    write_requirements: bool = True,
    ieq_scores: Optional[Mapping[str, float]] = None,
) -> Any:
    """
    Write IEQ requirements and assessment results onto ``IfcSpace`` objects.

    Rooms are matched by ``ifc_guid``. Results go to ``HVX_Pset_IEQAssessment``;
    requirements to the standard ``Pset_Space*Requirements`` sets plus
    ``HVX_Pset_SpaceIEQRequirements``. Returns the IfcOpenShell file object.
    """
    ifcopenshell = _ifcopenshell()
    import ifcopenshell.api.pset as api_pset
    from ifcopenshell.util import element as uel

    model = source if hasattr(source, "by_type") else ifcopenshell.open(str(source))
    written = 0
    for room in rooms.values():
        if not room.ifc_guid:
            continue
        try:
            space = model.by_guid(room.ifc_guid)
        except RuntimeError:
            continue
        psets: Dict[str, Dict[str, Any]] = {}
        if write_requirements and room.ieq_requirements is not None:
            psets.update(room.ieq_requirements.to_ifc_psets())
        assessment = (assessments or {}).get(room.id)
        if assessment is not None:
            for name, props in assessment.to_ifc_pset().items():
                if ieq_scores and room.id in ieq_scores and ieq_scores[room.id] is not None:
                    props = {**props, "IEQScore": round(float(ieq_scores[room.id]), 1)}
                psets[name] = props
        existing = uel.get_psets(space)
        for name, props in psets.items():
            if name in existing and "id" in existing[name]:
                pset = model.by_id(existing[name]["id"])
            else:
                pset = api_pset.add_pset(model, product=space, name=name)
            api_pset.edit_pset(model, pset=pset, properties=props)
        written += 1

    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        model.write(str(output_path))
    return model


__all__ = ["load_ifc", "write_ieq_to_ifc"]
