# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Per-room 'IEQ problem' binary sensor: on while a live value breaks the target limits."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import HvxConfigEntry, HvxCoordinator
from .entity import HvxRoomEntity


async def async_setup_entry(hass: HomeAssistant, entry: HvxConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator: HvxCoordinator = entry.runtime_data
    async_add_entities(HvxProblemSensor(coordinator, room_id) for room_id in coordinator.site.rooms)


class HvxProblemSensor(HvxRoomEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: HvxCoordinator, room_id: str) -> None:
        super().__init__(coordinator, room_id, "ieq_problem")

    @property
    def is_on(self) -> bool | None:
        state = self.room_state
        if state is None:
            return None
        return any(p.status in ("high", "low") for p in state.current.values())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        state = self.room_state
        if state is None:
            return None
        return {
            "alerts": list(state.alerts),
            "target_category": self.coordinator.target_category,
            **{f"{param}_status": p.status for param, p in state.current.items()},
        }
