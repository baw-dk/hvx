"""
Namespace IRIs used by the semantic layer.

Kept as plain strings so that importing the data model never requires
``rdflib``; the RDF exporters wrap them in ``rdflib.Namespace`` lazily.
"""

from __future__ import annotations

BRICK = "https://brickschema.org/schema/Brick#"
BRICK_REF = "https://brickschema.org/schema/Brick/ref#"
QUDT_UNIT = "http://qudt.org/vocab/unit/"
QUDT_QUANTITY_KIND = "http://qudt.org/vocab/quantitykind/"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
XSD = "http://www.w3.org/2001/XMLSchema#"

# IEQ extension vocabulary (classes and properties Brick does not provide).
# Change this in one place if the ontology is published under another IRI.
HVX_IEQ = "https://brunoadam.eu/ns/hvx/ieq#"

# Default base for instance IRIs produced by the exporters.
DEFAULT_INSTANCE_BASE = "urn:hvx:"

PREFIXES = {
    "brick": BRICK,
    "ref": BRICK_REF,
    "unit": QUDT_UNIT,
    "qudtqk": QUDT_QUANTITY_KIND,
    "ieq": HVX_IEQ,
}


def expand(curie: str) -> str:
    """Expand a ``prefix:Local`` CURIE into a full IRI."""
    prefix, sep, local = curie.partition(":")
    if not sep or prefix not in PREFIXES:
        raise ValueError(f"Unknown or malformed CURIE: {curie!r}")
    return PREFIXES[prefix] + local


def compact(iri: str) -> str:
    """Compact a full IRI into a CURIE if a known prefix matches."""
    for prefix, base in PREFIXES.items():
        if iri.startswith(base):
            return f"{prefix}:{iri[len(base):]}"
    return iri


__all__ = [
    "BRICK",
    "BRICK_REF",
    "QUDT_UNIT",
    "QUDT_QUANTITY_KIND",
    "HVX_IEQ",
    "DEFAULT_INSTANCE_BASE",
    "PREFIXES",
    "expand",
    "compact",
]
