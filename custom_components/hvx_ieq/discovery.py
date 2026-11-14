# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Find rooms (areas) and their IEQ sensors in Home Assistant's registries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr

from .const import PARAMETER_DEVICE_CLASSES

_DEVICE_CLASS_TO_PARAMETER = {v: k for k, v in PARAMETER_DEVICE_CLASSES.items()}


@dataclass
class AreaInfo:
    area_id: str
    name: str
    floor_id: str | None
    floor_name: str | None
    floor_level: int | None


def area_infos(hass: HomeAssistant) -> dict[str, AreaInfo]:
    areas = ar.async_get(hass)
    floors = fr.async_get(hass)
    out: dict[str, AreaInfo] = {}
    for area in areas.async_list_areas():
        floor = floors.async_get_floor(area.floor_id) if area.floor_id else None
        out[area.id] = AreaInfo(
            area_id=area.id,
            name=area.name,
            floor_id=area.floor_id,
            floor_name=floor.name if floor else None,
            floor_level=floor.level if floor else None,
        )
    return out


def candidate_sensors(hass: HomeAssistant) -> dict[str, dict[str, list[str]]]:
    """``{area_id: {parameter: [entity_id, ...]}}`` for sensors with a matching device class."""
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
    out: dict[str, dict[str, list[str]]] = {}
    for entry in entities.entities.values():
        if entry.domain != "sensor" or entry.disabled_by is not None:
            continue
        area_id = entry.area_id
        if area_id is None and entry.device_id:
            device = devices.async_get(entry.device_id)
            area_id = device.area_id if device else None
        if area_id is None:
            continue
        device_class = entry.device_class or entry.original_device_class
        if device_class is None:
            state = hass.states.get(entry.entity_id)
            device_class = state.attributes.get("device_class") if state else None
        parameter = _DEVICE_CLASS_TO_PARAMETER.get(str(device_class) if device_class else "")
        if parameter:
            out.setdefault(area_id, {}).setdefault(parameter, []).append(entry.entity_id)
    for params in out.values():
        for ids in params.values():
            ids.sort()
    return out


def detect_rooms(hass: HomeAssistant, area_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Default sensor choice per area (first candidate per parameter)."""
    candidates = candidate_sensors(hass)
    wanted = area_ids if area_ids is not None else sorted(candidates)
    return {
        area_id: {param: (candidates.get(area_id, {}).get(param) or [None])[0] for param in PARAMETER_DEVICE_CLASSES}
        for area_id in wanted
    }
