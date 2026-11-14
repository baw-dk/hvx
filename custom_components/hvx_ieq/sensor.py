# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""IEQ sensors per room and per building."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from hvx.live import LiveSnapshot, RoomLiveState

from .const import CATEGORY_STATES
from .coordinator import HvxConfigEntry, HvxCoordinator
from .entity import HvxBuildingEntity, HvxRoomEntity

CATEGORY_OPTIONS = list(CATEGORY_STATES.values())


@dataclass(frozen=True, kw_only=True)
class RoomSensorDescription(SensorEntityDescription):
    value_fn: Callable[[RoomLiveState], Any]


@dataclass(frozen=True, kw_only=True)
class BuildingSensorDescription(SensorEntityDescription):
    value_fn: Callable[[LiveSnapshot], Any]


def _window(state: RoomLiveState, attr: str):
    report = state.window
    return getattr(report, attr) if report is not None and report.status == "ok" else None


def _compliance(parameter: str) -> Callable[[RoomLiveState], Any]:
    def fn(state: RoomLiveState):
        report = state.window
        return report.compliance.get(parameter) if report is not None and report.status == "ok" else None

    return fn


def _category(value: str | None, analysed: bool) -> str | None:
    return CATEGORY_STATES.get(value) if analysed else None


PCT = dict(native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=0)

ROOM_SENSORS: tuple[RoomSensorDescription, ...] = (
    RoomSensorDescription(key="ieq_score", **PCT, value_fn=lambda s: _window(s, "ieq_score")),
    RoomSensorDescription(
        key="comfort_category",
        device_class=SensorDeviceClass.ENUM,
        options=CATEGORY_OPTIONS,
        value_fn=lambda s: _category(_window(s, "achieved_category"), s.window is not None and s.window.status == "ok"),
    ),
    RoomSensorDescription(
        key="current_category",
        device_class=SensorDeviceClass.ENUM,
        options=CATEGORY_OPTIONS,
        value_fn=lambda s: _category(s.category_now, any(p.status not in ("stale", "missing") for p in s.current.values())),
    ),
    RoomSensorDescription(key="temperature_compliance", **PCT, value_fn=_compliance("temperature")),
    RoomSensorDescription(key="co2_compliance", **PCT, value_fn=_compliance("co2")),
    RoomSensorDescription(key="humidity_compliance", **PCT, value_fn=_compliance("humidity")),
)

BUILDING_SENSORS: tuple[BuildingSensorDescription, ...] = (
    BuildingSensorDescription(key="ieq_score", **PCT, value_fn=lambda d: d.summary.ieq_score),
    BuildingSensorDescription(key="rooms_meeting_target", **PCT, value_fn=lambda d: d.summary.meets_target_pct),
    BuildingSensorDescription(
        key="comfort_category",
        device_class=SensorDeviceClass.ENUM,
        options=CATEGORY_OPTIONS,
        value_fn=lambda d: CATEGORY_STATES.get(d.summary.category) if d.summary.rooms_analysed else None,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: HvxConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator: HvxCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [HvxBuildingSensor(coordinator, d) for d in BUILDING_SENSORS]
    for room_id in coordinator.site.rooms:
        entities.extend(HvxRoomSensor(coordinator, room_id, d) for d in ROOM_SENSORS)
    async_add_entities(entities)


class HvxRoomSensor(HvxRoomEntity, SensorEntity):
    entity_description: RoomSensorDescription

    def __init__(self, coordinator: HvxCoordinator, room_id: str, description: RoomSensorDescription) -> None:
        super().__init__(coordinator, room_id, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        state = self.room_state
        return self.entity_description.value_fn(state) if state else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        state = self.room_state
        if state is None or self.entity_description.key not in ("ieq_score", "comfort_category"):
            return None
        report = state.window
        return {
            "target_category": self.coordinator.target_category,
            "issues": list(report.issues) if report else [],
            "window_days": self.coordinator.window.days,
            "samples": (report.data_quality or {}).get("samples") if report else None,
        }


class HvxBuildingSensor(HvxBuildingEntity, SensorEntity):
    entity_description: BuildingSensorDescription

    def __init__(self, coordinator: HvxCoordinator, description: BuildingSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data) if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if data is None or self.entity_description.key != "ieq_score":
            return None
        s = data.summary
        return {
            "rooms_total": s.rooms_total,
            "rooms_analysed": s.rooms_analysed,
            "category_counts": s.category_counts,
            "compliance": s.compliance,
            "season": data.season,
        }
