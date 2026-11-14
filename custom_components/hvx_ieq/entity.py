"""Base entities: one device per building and per room (area)."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HvxCoordinator


class HvxBuildingEntity(CoordinatorEntity[HvxCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: HvxCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_building_{key}"
        self._attr_translation_key = f"building_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="HVX",
            model="IEQ building",
            entry_type=DeviceEntryType.SERVICE,
        )


class HvxRoomEntity(CoordinatorEntity[HvxCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: HvxCoordinator, room_id: str, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        room = coordinator.site.rooms[room_id]
        self.room_id = room_id
        self._attr_unique_id = f"{entry.entry_id}_{room_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{room_id}")},
            name=f"{room.name} IEQ",
            manufacturer="HVX",
            model="IEQ room",
            suggested_area=room.name,
            via_device=(DOMAIN, entry.entry_id),
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def room_state(self):
        data = self.coordinator.data
        return data.rooms.get(self.room_id) if data else None

    @property
    def available(self) -> bool:
        return super().available and self.room_state is not None
