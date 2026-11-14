"""
Semantic layer: alignment of the HVX data model with IFC and Brick Schema,
plus the IEQ extension both standards lack.

* :mod:`.mappings` - lookup tables (spatial levels, room usages, sensors)
* :mod:`.ieq` - typed IEQ requirements / assessments (IFC Pset aware)
* :mod:`.brick` - Brick 1.4 RDF export/import (needs ``rdflib``)
* :mod:`.ifc` - IFC import and result write-back (needs ``ifcopenshell``)
* :mod:`.ifc_guid` - IFC GlobalId encoding without IfcOpenShell
* ``ontology/hvx_ieq.ttl`` - the ``ieq:`` extension vocabulary
"""

from . import ifc_guid
from .ieq import (
    IEQ_ASSESSMENT_PSET,
    IEQ_REQUIREMENTS_PSET,
    ComfortCategory,
    IEQAssessment,
    IEQRequirements,
    ParameterAssessment,
)
from .mappings import (
    POINT_MAPPINGS,
    ROOM_TYPE_BRICK_CLASS,
    SPATIAL_MAPPINGS,
    brick_class_for_room_type,
    normalize_metric_name,
    point_mapping,
    spatial_mapping,
)
from .namespaces import BRICK, BRICK_REF, HVX_IEQ, PREFIXES
from .types import SemanticImportResult

__all__ = [
    "ifc_guid",
    "ComfortCategory",
    "IEQRequirements",
    "IEQAssessment",
    "ParameterAssessment",
    "IEQ_ASSESSMENT_PSET",
    "IEQ_REQUIREMENTS_PSET",
    "POINT_MAPPINGS",
    "ROOM_TYPE_BRICK_CLASS",
    "SPATIAL_MAPPINGS",
    "brick_class_for_room_type",
    "normalize_metric_name",
    "point_mapping",
    "spatial_mapping",
    "BRICK",
    "BRICK_REF",
    "HVX_IEQ",
    "PREFIXES",
    "SemanticImportResult",
]
