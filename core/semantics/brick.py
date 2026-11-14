"""
Brick Schema (1.4) export and import.

Export produces a Brick model of the portfolio:

* spatial hierarchy (``brick:Portfolio`` / ``Building`` / ``Floor`` / room
  classes) linked with ``brick:hasPart`` / ``brick:isPartOf``;
* ``brick:area`` / ``brick:volume`` value shapes with QUDT units;
* one Brick point per measured parameter, linked with ``brick:isPointOf`` and
  carrying a ``ref:TimeseriesReference`` (Brick's own mechanism);
* ``ref:IFCReference`` links to the source IFC model when GUIDs are known;
* IEQ requirements and assessments using the ``ieq:`` extension.

Import reads a Brick model back into Portfolio/Building/Floor/Room entities
with ``SensorDefinition`` objects for every point found.

``rdflib`` is imported lazily so the rest of the data model does not need it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union
from urllib.parse import quote

from ..enums import MetricType, SpatialEntityType
from .ieq import IEQAssessment, IEQRequirements
from .mappings import (
    BRICK_CLASS_TO_METRIC,
    BRICK_CLASS_TO_ROOM_TYPE,
    ROOM_TYPE_BRICK_CLASS,
    normalize_metric_name,
    point_mapping,
)
from .namespaces import BRICK, BRICK_REF, DEFAULT_INSTANCE_BASE, HVX_IEQ, PREFIXES, expand
from .types import SemanticImportResult

if TYPE_CHECKING:  # pragma: no cover
    from rdflib import Graph

    from ..entities import Building, Floor, Portfolio, Room
    from ..spacial_entity import SpatialEntity

ONTOLOGY_PATH = Path(__file__).parent / "ontology" / "hvx_ieq.ttl"


def _rdflib():
    try:
        import rdflib  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised only without rdflib
        raise ImportError("Brick export/import requires 'rdflib' (pip install rdflib)") from exc
    return rdflib


def load_extension_ontology() -> "Graph":
    """Load the ``ieq:`` extension ontology as an rdflib Graph."""
    rdflib = _rdflib()
    graph = rdflib.Graph()
    graph.parse(ONTOLOGY_PATH, format="turtle")
    return graph


def brick_class_for(entity: "SpatialEntity") -> str:
    """Brick class CURIE for an entity, honouring an explicit override."""
    if getattr(entity, "brick_class", None):
        return entity.brick_class  # type: ignore[return-value]
    return entity.semantic_brick_class()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class BrickExporter:
    """Serialize a portfolio to a Brick 1.4 graph."""

    def __init__(
        self,
        base_uri: str = DEFAULT_INSTANCE_BASE,
        include_points: bool = True,
        include_assessments: bool = True,
        timeseries_store: str = "hvx",
    ) -> None:
        self.base_uri = base_uri
        self.include_points = include_points
        self.include_assessments = include_assessments
        self.timeseries_store = timeseries_store

    def uri(self, *parts: str):
        rdflib = _rdflib()
        return rdflib.URIRef(self.base_uri + "/".join(quote(p, safe="-_.~") for p in parts))

    def build_graph(
        self,
        portfolio: "Portfolio",
        buildings: Mapping[str, "Building"],
        floors: Mapping[str, "Floor"],
        rooms: Mapping[str, "Room"],
        assessments: Optional[Mapping[str, Sequence[IEQAssessment]]] = None,
        ieq_scores: Optional[Mapping[str, float]] = None,
    ) -> "Graph":
        rdflib = _rdflib()
        from rdflib import BNode, Literal
        from rdflib.namespace import RDF, RDFS, XSD

        g = rdflib.Graph()
        for prefix, iri in PREFIXES.items():
            g.bind(prefix, rdflib.Namespace(iri))
        g.bind("inst", rdflib.Namespace(self.base_uri))
        B = rdflib.Namespace(BRICK)
        REF = rdflib.Namespace(BRICK_REF)
        IEQ = rdflib.Namespace(HVX_IEQ)
        C = lambda curie: rdflib.URIRef(expand(curie))  # noqa: E731

        ifc_project = self._ifc_project_node(g, portfolio)

        def add_entity(entity: "SpatialEntity", parent=None):
            node = self.uri(entity.id)
            g.add((node, RDF.type, C(brick_class_for(entity))))
            g.add((node, RDFS.label, Literal(entity.name)))
            if parent is not None:
                g.add((parent, B.hasPart, node))
                g.add((node, B.isPartOf, parent))
            for prop, value, unit in (("area", entity.area_m2, "unit:M2"), ("volume", entity.volume_m3, "unit:M3")):
                if value is not None:
                    shape = BNode()
                    g.add((node, B[prop], shape))
                    g.add((shape, B.value, Literal(float(value), datatype=XSD.decimal)))
                    g.add((shape, B.hasUnit, C(unit)))
            if entity.ifc_guid and ifc_project is not None:
                ref = BNode()
                g.add((node, REF.hasExternalReference, ref))
                g.add((ref, RDF.type, REF.IFCReference))
                g.add((ref, REF.ifcGlobalID, Literal(entity.ifc_guid)))
                g.add((ref, REF.ifcName, Literal(entity.name)))
                g.add((ref, REF.hasIfcProjectReference, ifc_project))
            if entity.design_occupancy is not None:
                g.add((node, IEQ.designOccupancy, Literal(int(entity.design_occupancy), datatype=XSD.integer)))
            if entity.ieq_requirements is not None:
                self._add_requirements(g, node, entity.ieq_requirements)
            return node

        p_node = add_entity(portfolio)
        building_nodes = {}
        for building in buildings.values():
            building_nodes[building.id] = add_entity(building, p_node)
            if building.year_built:
                shape = BNode()
                g.add((building_nodes[building.id], B.yearBuilt, shape))
                g.add((shape, B.value, Literal(int(building.year_built), datatype=XSD.integer)))

        floor_nodes = {}
        for floor in floors.values():
            parent = building_nodes.get(floor.building_id or "") or self._first_parent(floor, building_nodes)
            floor_nodes[floor.id] = add_entity(floor, parent)

        for room in rooms.values():
            parent = (
                floor_nodes.get(room.floor_id or "")
                or building_nodes.get(room.building_id or "")
                or self._first_parent(room, {**floor_nodes, **building_nodes})
            )
            room_node = add_entity(room, parent)
            point_nodes = self._add_points(g, room, room_node) if self.include_points else {}
            if self.include_assessments and assessments:
                for assessment in assessments.get(room.id, []):
                    self._add_assessment(g, room_node, assessment, point_nodes, (ieq_scores or {}).get(room.id))
        return g

    def serialize(self, *args: Any, destination: Optional[Union[str, Path]] = None, fmt: str = "turtle", **kwargs: Any) -> str:
        graph = self.build_graph(*args, **kwargs)
        data = graph.serialize(format=fmt)
        if destination is not None:
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            Path(destination).write_text(data, encoding="utf-8")
        return data

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _first_parent(entity: "SpatialEntity", candidates: Mapping[str, Any]):
        for pid in entity.parent_ids:
            if pid in candidates:
                return candidates[pid]
        return None

    def _ifc_project_node(self, g: "Graph", portfolio: "Portfolio"):
        from rdflib import Literal
        from rdflib.namespace import RDF

        rdflib = _rdflib()
        REF = rdflib.Namespace(BRICK_REF)
        meta = portfolio.metadata or {}
        project_id = meta.get("ifc_project_id")
        if not project_id:
            return None
        node = self.uri("ifc-project", str(project_id))
        g.add((node, RDF.type, REF.ifcProject))
        g.add((node, REF.ifcProjectID, Literal(str(project_id))))
        g.add((node, REF.ifcFileLocation, Literal(str(meta.get("ifc_file", "")))))
        return node

    def _add_points(self, g: "Graph", room: "Room", room_node) -> Dict[str, Any]:
        rdflib = _rdflib()
        from rdflib import BNode, Literal
        from rdflib.namespace import RDF, RDFS

        B = rdflib.Namespace(BRICK)
        REF = rdflib.Namespace(BRICK_REF)
        IEQ = rdflib.Namespace(HVX_IEQ)
        C = lambda curie: rdflib.URIRef(expand(curie))  # noqa: E731

        parameters: Dict[str, Optional[str]] = {name: None for name in room.timeseries_data}
        for group in room.sensor_groups.values():
            for sensor in group.sensors:
                parameters.setdefault(sensor.parameter, sensor.brick_point_uri)
                if sensor.brick_point_uri:
                    parameters[sensor.parameter] = sensor.brick_point_uri

        nodes: Dict[str, Any] = {}
        for parameter, explicit_uri in parameters.items():
            metric = normalize_metric_name(parameter)
            mapping = point_mapping(metric) if metric else None
            if mapping is None:
                continue
            node = rdflib.URIRef(explicit_uri) if explicit_uri else self.uri(room.id, "point", parameter)
            g.add((node, RDF.type, C(mapping.brick_class)))
            g.add((node, RDFS.label, Literal(f"{room.name} {parameter}")))
            g.add((node, B.isPointOf, room_node))
            g.add((room_node, B.hasPoint, node))
            g.add((node, B.hasUnit, C(mapping.unit)))
            if mapping.brick_class == "ieq:Sound_Pressure_Level_Sensor":
                g.add((node, IEQ.frequencyWeighting, Literal("A")))
            if parameter in room.timeseries_data:
                ref = BNode()
                g.add((node, REF.hasExternalReference, ref))
                g.add((ref, RDF.type, REF.TimeseriesReference))
                g.add((ref, REF.hasTimeseriesId, Literal(f"{room.id}:{parameter}")))
                g.add((ref, REF.storedAt, Literal(self.timeseries_store)))
            nodes[metric.value if metric else parameter] = node
        return nodes

    @staticmethod
    def _add_requirements(g: "Graph", node, req: IEQRequirements) -> None:
        rdflib = _rdflib()
        from rdflib import BNode, Literal
        from rdflib.namespace import RDF, XSD

        IEQ = rdflib.Namespace(HVX_IEQ)
        r = BNode()
        g.add((node, IEQ.hasRequirement, r))
        g.add((r, RDF.type, IEQ.IEQRequirement))
        g.add((r, IEQ.targetCategory, IEQ[f"Category_{req.target_category.value}"]))
        for prop, value in (
            ("temperatureMin", req.temperature_min_c),
            ("temperatureMax", req.temperature_max_c),
            ("humidityMin", req.humidity_min_pct),
            ("humidityMax", req.humidity_max_pct),
            ("co2Max", req.co2_max_ppm),
            ("illuminanceMin", req.illuminance_min_lux),
            ("soundPressureLevelMax", req.sound_pressure_level_max_dba),
        ):
            if value is not None:
                g.add((r, IEQ[prop], Literal(float(value), datatype=XSD.decimal)))

    @staticmethod
    def _add_assessment(g: "Graph", node, a: IEQAssessment, point_nodes: Mapping[str, Any], score: Optional[float]) -> None:
        rdflib = _rdflib()
        from rdflib import BNode, Literal
        from rdflib.namespace import RDF, XSD

        IEQ = rdflib.Namespace(HVX_IEQ)
        C = lambda curie: rdflib.URIRef(expand(curie))  # noqa: E731
        n = BNode()
        g.add((node, IEQ.hasAssessment, n))
        g.add((n, RDF.type, IEQ.IEQAssessment))
        g.add((n, IEQ.assesses, node))
        g.add((n, IEQ.accordingTo, IEQ["EN16798-1"]))
        g.add((n, IEQ.targetCategory, IEQ[f"Category_{a.target_category.value}"]))
        if a.achieved_category:
            g.add((n, IEQ.achievedCategory, IEQ[f"Category_{a.achieved_category.value}"]))
        if a.season:
            g.add((n, IEQ.season, Literal(a.season)))
        if a.period_start:
            g.add((n, IEQ.periodStart, Literal(a.period_start, datatype=XSD.dateTime)))
        if a.period_end:
            g.add((n, IEQ.periodEnd, Literal(a.period_end, datatype=XSD.dateTime)))
        if a.compliance_pct is not None:
            g.add((n, IEQ.compliancePercent, Literal(round(a.compliance_pct, 2), datatype=XSD.decimal)))
        if score is not None:
            g.add((n, IEQ.ieqScore, Literal(round(score, 1), datatype=XSD.decimal)))
        for name, param in a.parameters.items():
            pr = BNode()
            g.add((n, IEQ.hasParameterResult, pr))
            g.add((pr, RDF.type, IEQ.ParameterResult))
            mapping = point_mapping(name)
            if mapping and mapping.quantity:
                g.add((pr, IEQ.quantity, C(mapping.quantity)))
            metric = normalize_metric_name(name)
            if metric and metric.value in point_nodes:
                g.add((pr, IEQ.basedOnPoint, point_nodes[metric.value]))
            for prop, value in (
                ("compliancePercent", param.compliance_pct),
                ("meanValue", param.mean),
                ("minValue", param.minimum),
                ("maxValue", param.maximum),
            ):
                if value is not None:
                    g.add((pr, IEQ[prop], Literal(round(float(value), 3), datatype=XSD.decimal)))


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

_ROOM_LIKE_SUFFIXES = ("_Room", "Office", "_Space", "Lobby", "Hallway", "Auditorium", "Cafeteria", "Laboratory", "Restroom")


class BrickImporter:
    """Read a Brick model into HVX entities."""

    def __init__(self, base_uri: str = DEFAULT_INSTANCE_BASE, ontology: Optional["Graph"] = None) -> None:
        self.base_uri = base_uri
        self.ontology = ontology

    def load(self, source: Union[str, Path, "Graph"], fmt: Optional[str] = None) -> SemanticImportResult:
        rdflib = _rdflib()
        from rdflib.namespace import RDF, RDFS

        from ..entities import Building, Floor, Portfolio, Room
        from ..metering import SensorDefinition

        if isinstance(source, rdflib.Graph):
            g, label = source, "graph"
        else:
            g = rdflib.Graph()
            g.parse(str(source), format=fmt or rdflib.util.guess_format(str(source)) or "turtle")
            label = str(source)

        B = rdflib.Namespace(BRICK)
        REF = rdflib.Namespace(BRICK_REF)
        IEQ = rdflib.Namespace(HVX_IEQ)
        superclasses = self._superclass_index(g)
        result_warnings: List[str] = []

        def kind_of(node) -> Optional[str]:
            kinds = set()
            for cls in g.objects(node, RDF.type):
                for c in {str(cls)} | superclasses.get(str(cls), set()):
                    kinds.add(c)
            for k in kinds:
                if k == BRICK + "Portfolio":
                    return "portfolio"
                if k == BRICK + "Building":
                    return "building"
                if k == BRICK + "Floor":
                    return "floor"
            for k in kinds:
                if k in (BRICK + "Room", BRICK + "Space") or self._is_room_class(k):
                    return "room"
            for k in kinds:
                if k.startswith(BRICK) and (k.endswith("_Sensor") or k.endswith("_Setpoint")) or k == HVX_IEQ + "Sound_Pressure_Level_Sensor":
                    return "point"
            return None

        def local_id(node) -> str:
            text = str(node)
            if text.startswith(self.base_uri):
                return text[len(self.base_uri) :]
            for sep in ("#", "/", ":"):
                if sep in text:
                    text = text.rsplit(sep, 1)[-1]
                    break
            return text

        def label_of(node) -> str:
            value = g.value(node, RDFS.label)
            return str(value) if value is not None else local_id(node)

        def quantity(node, prop) -> Optional[float]:
            shape = g.value(node, B[prop])
            if shape is None:
                return None
            value = g.value(shape, B.value)
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        def parent_of(node):
            parent = g.value(node, B.isPartOf)
            if parent is None:
                parent = g.value(None, B.hasPart, node)
            return parent

        def ifc_guid_of(node) -> Optional[str]:
            for ref in g.objects(node, REF.hasExternalReference):
                guid = g.value(ref, REF.ifcGlobalID)
                if guid is not None:
                    return str(guid)
            return None

        def brick_curie(node) -> Optional[str]:
            for cls in g.objects(node, RDF.type):
                text = str(cls)
                for prefix, base in PREFIXES.items():
                    if text.startswith(base):
                        return f"{prefix}:{text[len(base):]}"
            return None

        nodes: Dict[str, List[Any]] = {"portfolio": [], "building": [], "floor": [], "room": [], "point": []}
        for node in set(g.subjects(RDF.type, None)):
            kind = kind_of(node)
            if kind:
                nodes[kind].append(node)

        if nodes["portfolio"]:
            pnode = sorted(nodes["portfolio"], key=str)[0]
            portfolio = Portfolio(id=local_id(pnode), name=label_of(pnode), type=SpatialEntityType.PORTFOLIO)
            if len(nodes["portfolio"]) > 1:
                result_warnings.append("Multiple brick:Portfolio nodes found; using the first.")
        else:
            portfolio = Portfolio(id="brick_portfolio", name="Imported Brick model", type=SpatialEntityType.PORTFOLIO)

        def common(node) -> Dict[str, Any]:
            return {
                "id": local_id(node),
                "name": label_of(node),
                "area_m2": quantity(node, "area"),
                "volume_m3": quantity(node, "volume"),
                "ifc_guid": ifc_guid_of(node),
                "ieq_requirements": self._requirements(g, node),
            }

        buildings: Dict[str, Building] = {}
        for node in sorted(nodes["building"], key=str):
            b = Building(**common(node), parent_ids=[portfolio.id])
            year = g.value(g.value(node, B.yearBuilt), B.value) if g.value(node, B.yearBuilt) is not None else None
            if year is not None:
                b.year_built = int(year)
            buildings[b.id] = b
            portfolio.add_building(b.id)

        floors: Dict[str, Floor] = {}
        for node in sorted(nodes["floor"], key=str):
            parent = parent_of(node)
            bid = local_id(parent) if parent is not None else None
            f = Floor(**common(node), building_id=bid, parent_ids=[bid] if bid else [])
            floors[f.id] = f
            if bid in buildings:
                buildings[bid].add_floor(f.id)
            elif bid is None:
                result_warnings.append(f"Floor {f.id} has no parent building.")

        rooms: Dict[str, Room] = {}
        room_node_by_id: Dict[str, Any] = {}
        for node in sorted(nodes["room"], key=str):
            parent = parent_of(node)
            pid = local_id(parent) if parent is not None else None
            floor_id = pid if pid in floors else None
            building_id = floors[pid].building_id if floor_id else (pid if pid in buildings else None)
            curie = brick_curie(node)
            room_type = BRICK_CLASS_TO_ROOM_TYPE.get(curie or "")
            occupancy = g.value(node, IEQ.designOccupancy)
            room = Room(
                **common(node),
                floor_id=floor_id,
                building_id=building_id,
                parent_ids=[pid] if pid else [],
                room_type=room_type.value if room_type else None,
                brick_class=curie if curie and curie != ROOM_TYPE_BRICK_CLASS.get(room_type) else None,
                design_occupancy=int(occupancy) if occupancy is not None else None,
            )
            rooms[room.id] = room
            room_node_by_id[room.id] = node
            if floor_id:
                floors[floor_id].add_room(room.id)
            if building_id in buildings:
                buildings[building_id].add_room(room.id)
            if pid is None:
                result_warnings.append(f"Room {room.id} has no parent floor or building.")

        node_to_room = {str(n): rid for rid, n in room_node_by_id.items()}
        for node in sorted(nodes["point"], key=str):
            owner = g.value(node, B.isPointOf) or g.value(None, B.hasPoint, node) or g.value(node, B.hasLocation)
            room_id = node_to_room.get(str(owner)) if owner is not None else None
            if room_id is None:
                continue
            curie = brick_curie(node) or ""
            metric = BRICK_CLASS_TO_METRIC.get(curie, MetricType.OTHER)
            unit_node = g.value(node, B.hasUnit)
            ts_ids = [str(g.value(ref, REF.hasTimeseriesId)) for ref in g.objects(node, REF.hasExternalReference) if g.value(ref, REF.hasTimeseriesId) is not None]
            sensor = SensorDefinition(
                id=local_id(node),
                spatial_entity_id=room_id,
                metric=metric,
                parameter=metric.value,
                unit=str(unit_node).rsplit("/", 1)[-1] if unit_node is not None else "",
                name=label_of(node),
                brick_point_uri=str(node),
                metadata={"brick_class": curie, "timeseries_ids": ts_ids},
            )
            rooms[room_id].load_sensor(sensor)

        return SemanticImportResult(
            portfolio=portfolio,
            buildings=buildings,
            floors=floors,
            rooms=rooms,
            warnings=result_warnings,
            source=label,
        )

    # -- helpers ------------------------------------------------------------

    def _superclass_index(self, g: "Graph") -> Dict[str, set]:
        from rdflib.namespace import RDFS

        direct: Dict[str, set] = {}
        graphs: Iterable[Any] = [g, load_extension_ontology()]
        if self.ontology is not None:
            graphs = [*graphs, self.ontology]
        for graph in graphs:
            for sub, sup in graph.subject_objects(RDFS.subClassOf):
                direct.setdefault(str(sub), set()).add(str(sup))
        closure: Dict[str, set] = {}
        for cls in direct:
            seen, stack = set(), list(direct[cls])
            while stack:
                c = stack.pop()
                if c not in seen:
                    seen.add(c)
                    stack.extend(direct.get(c, ()))
            closure[cls] = seen
        return closure

    @staticmethod
    def _is_room_class(iri: str) -> bool:
        if not iri.startswith(BRICK):
            return False
        local = iri[len(BRICK) :]
        return local.endswith(_ROOM_LIKE_SUFFIXES) and not local.endswith(("_Sensor", "_Setpoint"))

    @staticmethod
    def _requirements(g: "Graph", node) -> Optional[IEQRequirements]:
        rdflib = _rdflib()
        IEQ = rdflib.Namespace(HVX_IEQ)
        r = g.value(node, IEQ.hasRequirement)
        if r is None:
            return None

        def num(prop: str) -> Optional[float]:
            v = g.value(r, IEQ[prop])
            return float(v) if v is not None else None

        target = g.value(r, IEQ.targetCategory)
        from .ieq import ComfortCategory

        return IEQRequirements(
            target_category=ComfortCategory.parse(str(target).rsplit("_", 1)[-1]) if target is not None else ComfortCategory.II,
            temperature_min_c=num("temperatureMin"),
            temperature_max_c=num("temperatureMax"),
            humidity_min_pct=num("humidityMin"),
            humidity_max_pct=num("humidityMax"),
            co2_max_ppm=num("co2Max"),
            illuminance_min_lux=num("illuminanceMin"),
            sound_pressure_level_max_dba=num("soundPressureLevelMax"),
        )


def export_brick(
    portfolio: "Portfolio",
    buildings: Mapping[str, "Building"],
    floors: Mapping[str, "Floor"],
    rooms: Mapping[str, "Room"],
    destination: Optional[Union[str, Path]] = None,
    assessments: Optional[Mapping[str, Sequence[IEQAssessment]]] = None,
    ieq_scores: Optional[Mapping[str, float]] = None,
    base_uri: str = DEFAULT_INSTANCE_BASE,
    fmt: str = "turtle",
) -> str:
    """Convenience wrapper returning the serialized Brick model."""
    return BrickExporter(base_uri=base_uri).serialize(
        portfolio, buildings, floors, rooms,
        destination=destination, fmt=fmt, assessments=assessments, ieq_scores=ieq_scores,
    )


def import_brick(source: Union[str, Path, "Graph"], base_uri: str = DEFAULT_INSTANCE_BASE) -> SemanticImportResult:
    return BrickImporter(base_uri=base_uri).load(source)


__all__ = [
    "BrickExporter",
    "BrickImporter",
    "export_brick",
    "import_brick",
    "load_extension_ontology",
    "brick_class_for",
    "ONTOLOGY_PATH",
]
