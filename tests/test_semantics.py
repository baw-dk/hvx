# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from __future__ import annotations

import os
import uuid

import pytest

from hvx.core.enums import RoomType, SpatialEntityType
from hvx.core.semantics import ifc_guid
from hvx.core.semantics.ieq import ComfortCategory, IEQAssessment, IEQRequirements
from hvx.core.semantics.mappings import (
    POINT_MAPPINGS,
    ROOM_TYPE_BRICK_CLASS,
    ROOM_USAGE_ALIASES,
    SPATIAL_MAPPINGS,
    brick_class_for_room_type,
)
from hvx.core.semantics.namespaces import expand

rdflib = pytest.importorskip("rdflib")


def _all_classes():
    classes = {m.brick_class for m in SPATIAL_MAPPINGS.values()}
    classes |= set(ROOM_TYPE_BRICK_CLASS.values()) | set(ROOM_USAGE_ALIASES.values())
    classes |= {m.brick_class for m in POINT_MAPPINGS.values()}
    return classes


@pytest.fixture(scope="module")
def brick_ontology():
    brickschema = pytest.importorskip("brickschema")
    path = os.path.join(os.path.dirname(brickschema.__file__), "ontologies", "1.4", "Brick.ttl")
    if not os.path.exists(path):
        pytest.skip("Brick 1.4 ontology not bundled with this brickschema version")
    g = rdflib.Graph()
    g.parse(path, format="turtle")
    return g


def test_brick_classes_exist_in_brick_1_4(brick_ontology):
    missing = [c for c in _all_classes() | {m.quantity for m in POINT_MAPPINGS.values() if m.quantity and m.quantity.startswith("brick:")}
               if c.startswith("brick:") and (rdflib.URIRef(expand(c)), None, None) not in brick_ontology]
    assert not missing, missing


def test_extension_classes_are_declared_and_subclass_brick():
    from hvx.core.semantics.brick import load_extension_ontology

    ext = load_extension_ontology()
    for curie in (c for c in _all_classes() if c.startswith("ieq:")):
        node = rdflib.URIRef(expand(curie))
        assert (node, rdflib.RDF.type, rdflib.OWL.Class) in ext, curie
        assert list(ext.objects(node, rdflib.RDFS.subClassOf)), f"{curie} must specialise a Brick class"


def test_ifc_names_exist_in_ifc4_schema():
    ifcopenshell = pytest.importorskip("ifcopenshell")
    schema = ifcopenshell.ifcopenshell_wrapper.schema_by_name("IFC4")
    for mapping in SPATIAL_MAPPINGS.values():
        if mapping.ifc_class:
            schema.declaration_by_name(mapping.ifc_class)
    sensor_types = set(schema.declaration_by_name("IfcSensorTypeEnum").enumeration_items())
    for metric, mapping in POINT_MAPPINGS.items():
        if mapping.ifc_sensor_type:
            assert mapping.ifc_sensor_type in sensor_types, metric


def test_entity_semantic_classes(portfolio):
    p, b, f, r = portfolio
    assert p.semantic_brick_class() == "brick:Portfolio" and p.ifc_class is None
    assert b["b0"].ifc_class == "IfcBuilding"
    assert f["b0_f0"].semantic_brick_class() == "brick:Floor"
    room = r["b0_f0_r0"]
    assert room.ifc_class == "IfcSpace"
    assert room.semantic_brick_class() == "brick:Conference_Room"
    room.brick_class = "brick:Break_Room"
    assert room.semantic_brick_class() == "brick:Break_Room"
    assert brick_class_for_room_type("Office") == "brick:Office"
    assert brick_class_for_room_type("classroom") == "ieq:Classroom"
    assert brick_class_for_room_type("unknown thing") == "brick:Room"


def test_ifc_guid_roundtrip_and_compat():
    for _ in range(50):
        u = uuid.uuid4().hex
        g = ifc_guid.compress(u)
        assert len(g) == 22 and ifc_guid.is_valid(g)
        assert ifc_guid.expand(g) == u
    assert ifc_guid.from_entity_id("room-1") == ifc_guid.from_entity_id("room-1")
    try:
        import ifcopenshell.guid
    except ImportError:
        return
    u = uuid.uuid4().hex
    assert ifc_guid.compress(u) == ifcopenshell.guid.compress(u)
    g = ifcopenshell.guid.new()
    assert ifc_guid.expand(g) == ifcopenshell.guid.expand(g).replace("-", "")


def test_requirements_ifc_pset_roundtrip():
    req = IEQRequirements(
        target_category="I", temperature_min_c=21, temperature_max_c=23, humidity_min_pct=30,
        humidity_max_pct=50, co2_max_ppm=950, illuminance_min_lux=500, sound_pressure_level_max_dba=35,
        occupancy_type="meeting_room", design_occupancy=8,
    )
    psets = req.to_ifc_psets()
    assert psets["Pset_SpaceThermalRequirements"]["SpaceHumidityMin"] == pytest.approx(0.30)  # IfcRatioMeasure
    assert psets["Pset_SpaceLightingRequirements"]["Illuminance"] == 500
    assert all(not name.startswith("Pset_") or name in {
        "Pset_SpaceThermalRequirements", "Pset_SpaceLightingRequirements", "Pset_SpaceOccupancyRequirements"} for name in psets)
    back = IEQRequirements.from_ifc_psets(psets)
    assert back == req


def test_assessment_from_en16798_dict():
    raw = {
        "achieved_category": "III", "season": "winter", "category_compliance_rates": {"I": 40.0, "II": 75.5, "III": 96.0, "IV": 100.0},
        "time_in_category_I_pct": 40.0, "time_in_category_II_pct": 35.5, "time_in_category_III_pct": 20.5, "time_in_category_IV_pct": 4.0,
        "parameter_metrics": {"co2": {"mean_value": 700, "min_value": 400, "max_value": 1300, "category_II_compliance_rate": 88.0, "category_I_compliance_rate": 60.0}},
    }
    a = IEQAssessment.from_en16798("r1", raw, target_category=ComfortCategory.II)
    assert a.achieved_category == ComfortCategory.III and a.meets_target is False
    assert a.compliance_pct == 75.5
    assert a.parameters["co2"].compliance_pct == 88.0 and a.parameters["co2"].unit == "ppm"
    pset = a.to_ifc_pset()["HVX_Pset_IEQAssessment"]
    assert pset["AchievedCategory"] == "III" and pset["Co2CompliancePercent"] == 88.0
    assert ComfortCategory.worst(ComfortCategory.I, None, ComfortCategory.III) == ComfortCategory.III


def test_brick_export_import_roundtrip(portfolio):
    from hvx.core.semantics.brick import BrickExporter, BrickImporter

    p, b, f, r = portfolio
    r["b0_f0_r1"].ieq_requirements = IEQRequirements(target_category="I", co2_max_ppm=950)
    r["b0_f0_r1"].ifc_guid = ifc_guid.from_entity_id("b0_f0_r1")
    p.metadata.update(ifc_project_id="0abcdefghijklmnopqrstu", ifc_file="model.ifc")
    assessment = IEQAssessment(entity_id="b0_f0_r1", achieved_category="II", compliance_pct=91.2, season="winter")

    graph = BrickExporter().build_graph(p, b, f, r, assessments={"b0_f0_r1": [assessment]}, ieq_scores={"b0_f0_r1": 93.1})
    B = rdflib.Namespace("https://brickschema.org/schema/Brick#")
    REF = rdflib.Namespace("https://brickschema.org/schema/Brick/ref#")
    room_node = rdflib.URIRef("urn:hvx:b0_f0_r1")
    assert (room_node, rdflib.RDF.type, B.Open_Office) in graph
    assert (rdflib.URIRef("urn:hvx:b0_f0"), B.hasPart, room_node) in graph
    points = list(graph.objects(room_node, B.hasPoint))
    assert len(points) == 3
    assert any((pt, rdflib.RDF.type, B.CO2_Level_Sensor) in graph for pt in points)
    assert list(graph.subjects(rdflib.RDF.type, REF.TimeseriesReference))
    assert list(graph.objects(None, REF.ifcGlobalID)) == [rdflib.Literal(r["b0_f0_r1"].ifc_guid)]

    # Reload from Turtle text, as a consumer would.
    reloaded = rdflib.Graph().parse(data=graph.serialize(format="turtle"), format="turtle")
    result = BrickImporter().load(reloaded)
    assert (len(result.buildings), len(result.floors), len(result.rooms)) == (2, 2, 6)
    room = result.rooms["b0_f0_r1"]
    assert room.floor_id == "b0_f0" and room.building_id == "b0"
    assert room.area_m2 == 25.0 and room.room_type == RoomType.OPEN_OFFICE.value
    assert room.ifc_guid == r["b0_f0_r1"].ifc_guid
    assert room.ieq_requirements.target_category == ComfortCategory.I and room.ieq_requirements.co2_max_ppm == 950
    assert {g for g in room.sensor_groups} == {"temperature", "co2", "humidity"}
    assert result.portfolio.type == SpatialEntityType.PORTFOLIO and not result.warnings


def test_brick_export_is_valid_against_brick_shapes(portfolio, brick_ontology):
    """Every rdf:type used by the export resolves to Brick 1.4, ref:, or the ieq: extension."""
    from hvx.core.semantics.brick import BrickExporter, load_extension_ontology

    graph = BrickExporter().build_graph(*portfolio)
    known = brick_ontology + load_extension_ontology()
    for cls in set(graph.objects(None, rdflib.RDF.type)):
        assert (cls, None, None) in known, cls


def test_ifc_import(ifc_file):
    from hvx.core.semantics.ifc import load_ifc

    path, space_guid = ifc_file
    result = load_ifc(path)
    assert (len(result.buildings), len(result.floors), len(result.rooms)) == (1, 3, 1)
    assert sorted(f.floor_number for f in result.floors.values()) == [-1, 0, 1]
    room = result.rooms[space_guid]
    assert room.ifc_guid == space_guid and room.name == "Meeting room 1.01"
    assert room.room_type == "meeting_room" and room.semantic_brick_class() == "brick:Conference_Room"
    assert room.area_m2 == pytest.approx(24.5) and room.volume_m3 == pytest.approx(66.0)
    assert room.design_occupancy == 6
    assert room.ieq_requirements.target_category == ComfortCategory.I
    assert room.ieq_requirements.humidity_max_pct == pytest.approx(50.0)
    assert result.floors[room.floor_id].name == "Ground"
    assert "co2" in room.sensor_groups
    assert result.portfolio.metadata["ifc_project_id"]


def test_ifc_write_back(ifc_file, tmp_path):
    import ifcopenshell
    import ifcopenshell.util.element as uel

    from hvx.core.semantics.ifc import load_ifc, write_ieq_to_ifc

    path, space_guid = ifc_file
    result = load_ifc(path)
    assessment = IEQAssessment(entity_id=space_guid, achieved_category="II", target_category="I", compliance_pct=81.0, season="winter")
    out = tmp_path / "out.ifc"
    write_ieq_to_ifc(path, result.rooms, {space_guid: assessment}, output_path=out, ieq_scores={space_guid: 88.4})
    written = ifcopenshell.open(str(out))  # keep the file alive while reading its entities
    psets = uel.get_psets(written.by_guid(space_guid))
    assert psets["HVX_Pset_IEQAssessment"]["AchievedCategory"] == "II"
    assert psets["HVX_Pset_IEQAssessment"]["MeetsTarget"] is False
    assert psets["HVX_Pset_IEQAssessment"]["IEQScore"] == pytest.approx(88.4)
    assert psets["HVX_Pset_SpaceIEQRequirements"]["CO2ConcentrationMax"] == 950
