"""
IFC GlobalId helpers (22-character compressed GUIDs).

Pure-Python implementation of the IFC base-64 GUID encoding so entity
identifiers can be produced without IfcOpenShell. Output is identical to
``ifcopenshell.guid.compress``.
"""

from __future__ import annotations

import re
import uuid

_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"
_IFC_GUID_RE = re.compile(r"^[0-3][0-9A-Za-z_$]{21}$")

# Namespace for deterministic GUIDs derived from HVX entity ids.
HVX_GUID_NAMESPACE = uuid.UUID("6b1f3c1e-2f0a-5e8e-9a57-4f1c0f7d5a10")


def _b64(value: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(_CHARS[value % 64])
        value //= 64
    return "".join(reversed(out))


def compress(uuid_hex: str) -> str:
    """Compress a 32-hex-digit UUID into a 22-character IFC GlobalId."""
    hex_digits = uuid_hex.replace("-", "")
    if len(hex_digits) != 32:
        raise ValueError(f"Expected 32 hex digits, got {uuid_hex!r}")
    bs = [int(hex_digits[i : i + 2], 16) for i in range(0, 32, 2)]
    parts = [_b64(bs[0], 2)]
    for i in range(1, 16, 3):
        parts.append(_b64((bs[i] << 16) + (bs[i + 1] << 8) + bs[i + 2], 4))
    return "".join(parts)


def expand(global_id: str) -> str:
    """Expand a 22-character IFC GlobalId into 32 lowercase hex digits."""
    if not is_valid(global_id):
        raise ValueError(f"Not a valid IFC GlobalId: {global_id!r}")
    nums = [_CHARS.index(c) for c in global_id]
    value = 0
    for n in nums:
        value = value * 64 + n
    return f"{value:032x}"


def is_valid(global_id: str) -> bool:
    return bool(global_id) and bool(_IFC_GUID_RE.match(global_id))


def new() -> str:
    """Random IFC GlobalId."""
    return compress(uuid.uuid4().hex)


def from_entity_id(entity_id: str) -> str:
    """Deterministic GlobalId for an HVX entity id (stable across exports)."""
    return compress(uuid.uuid5(HVX_GUID_NAMESPACE, entity_id).hex)


__all__ = ["compress", "expand", "is_valid", "new", "from_entity_id"]
