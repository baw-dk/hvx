# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Coordinator: recorder history -> hvx LiveMonitor -> snapshot for the entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance, history
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from hvx.core.entities import Building, Floor, Portfolio, Room
from hvx.core.enums import SpatialEntityType
from hvx.live import InMemorySource, LiveMonitor, LiveSnapshot, bind
from hvx.reporting import ReportConfig

from .const import (
    CONF_BUILDING_TYPE,
    CONF_ROOMS,
    CONF_SCAN_INTERVAL,
    CONF_TARGET_CATEGORY,
    CONF_WINDOW_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TARGET_CATEGORY,
    DEFAULT_WINDOW_DAYS,
    DOMAIN,
    LOGGER,
    SOURCE_NAME,
)
from .discovery import area_infos

HvxConfigEntry = ConfigEntry["HvxCoordinator"]


@dataclass
class HvxSite:
    portfolio: Portfolio
    buildings: dict[str, Building]
    floors: dict[str, Floor]
    rooms: dict[str, Room]

    @property
    def building(self) -> Building:
        return next(iter(self.buildings.values()))


def build_site(hass: HomeAssistant, entry: ConfigEntry) -> HvxSite:
    """hvx entities from the entry: one building, HA floors as floors, HA areas as rooms."""
    country = hass.config.country or "DK"
    portfolio = Portfolio(id=f"ha-{entry.entry_id}", name=entry.data[CONF_NAME], type=SpatialEntityType.PORTFOLIO, country=country)
    building = Building(
        id=entry.entry_id,
        name=entry.data[CONF_NAME],
        parent_ids=[portfolio.id],
        building_type=entry.data.get(CONF_BUILDING_TYPE),
        country=country,
    )
    portfolio.add_building(building.id)
    floors: dict[str, Floor] = {}
    rooms: dict[str, Room] = {}
    infos = area_infos(hass)
    for area_id, sensors in entry.options.get(CONF_ROOMS, {}).items():
        info = infos.get(area_id)
        floor = None
        if info and info.floor_id:
            floor = floors.get(info.floor_id)
            if floor is None:
                floor = Floor(id=info.floor_id, name=info.floor_name or info.floor_id, building_id=building.id,
                              parent_ids=[building.id], floor_number=info.floor_level)
                floors[floor.id] = floor
                building.add_floor(floor.id)
        room = Room(
            id=area_id,
            name=info.name if info else area_id,
            building_id=building.id,
            floor_id=floor.id if floor else None,
            parent_ids=[floor.id if floor else building.id],
        )
        for parameter, entity_id in sensors.items():
            if entity_id:
                bind(room, parameter, entity_id, SOURCE_NAME)
        rooms[room.id] = room
        building.add_room(room.id)
        if floor:
            floor.add_room(room.id)
    return HvxSite(portfolio, {building.id: building}, floors, rooms)


class HvxCoordinator(DataUpdateCoordinator[LiveSnapshot]):
    """Fetch recorder history incrementally and assess the rolling window."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        options = entry.options
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(minutes=float(options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))),
        )
        self.window = timedelta(days=float(options.get(CONF_WINDOW_DAYS, DEFAULT_WINDOW_DAYS)))
        self.target_category = str(options.get(CONF_TARGET_CATEGORY, DEFAULT_TARGET_CATEGORY))
        self.site = build_site(hass, entry)
        # Recorder history is change-driven: values hold until the next state.
        self.source = InMemorySource(hold_values=True)
        self.report_config = ReportConfig(
            target_category=self.target_category,
            include_simulations=False,
            parallel_backend="serial",
            min_samples_per_season=8,
            default_building_type=entry.data.get(CONF_BUILDING_TYPE) or "office",
        )
        self.monitor = LiveMonitor(
            self.site.portfolio,
            self.site.buildings,
            self.site.floors,
            self.site.rooms,
            sources={SOURCE_NAME: self.source},
            window=self.window,
            interval="15min",
            timezone=str(hass.config.time_zone),
            config=self.report_config,
        )
        self._fetched_until: datetime | None = None
        self._unsub_states: CALLBACK_TYPE | None = None
        self._live_debouncer = Debouncer(hass, LOGGER, cooldown=10, immediate=False, function=self._async_refresh_live)

    @staticmethod
    def _value(state: State) -> float:
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return float("nan")  # unavailable / unknown ends the previous value

    @callback
    def async_start_live_updates(self) -> None:
        """Push state changes straight into the monitor so live checks react within seconds."""

        @callback
        def _on_change(event: Event[EventStateChangedData]) -> None:
            new = event.data["new_state"]
            if new is None:
                return
            self.source.push(new.entity_id, self._value(new), new.last_changed, new.attributes.get("unit_of_measurement"))
            self._live_debouncer.async_schedule_call()

        self._unsub_states = async_track_state_change_event(self.hass, self.entity_ids, _on_change)

    async def async_shutdown(self) -> None:
        if self._unsub_states:
            self._unsub_states()
            self._unsub_states = None
        self._live_debouncer.async_shutdown()
        await super().async_shutdown()

    async def _async_refresh_live(self) -> None:
        """Re-evaluate current values only; keep the last window assessment."""
        if self.data is None:
            return
        now = dt_util.utcnow()
        live = await self.hass.async_add_executor_job(self._live, now)
        for room_id, state in live.rooms.items():
            previous = self.data.rooms.get(room_id)
            state.window = previous.window if previous else None
        live.summary = self.data.summary
        live.window_start = self.data.window_start
        # Update listeners without rescheduling the periodic window refresh.
        self.data = live
        self.async_update_listeners()

    def _live(self, now: datetime) -> LiveSnapshot:
        self.monitor.refresh(now)
        return self.monitor.snapshot(now, assess_window=False)

    @property
    def entity_ids(self) -> list[str]:
        return sorted({b.point for b in self.monitor.bindings})

    async def _async_update_data(self) -> LiveSnapshot:
        now = dt_util.utcnow()
        first = self._fetched_until is None
        start = now - self.window if first else self._fetched_until
        try:
            states = await get_instance(self.hass).async_add_executor_job(
                self._history, start, now, first
            )
        except Exception as exc:  # recorder not ready, database error...
            raise UpdateFailed(f"Could not read history: {exc}") from exc
        pushed = 0
        for entity_id, rows in states.items():
            for state in rows:
                if not isinstance(state, State):
                    continue
                # The state at window start keeps its original last_changed; clamp it into the window.
                ts = max(state.last_changed, start)
                self.source.push(entity_id, self._value(state), ts, state.attributes.get("unit_of_measurement"))
                pushed += 1
        self._fetched_until = now
        self.source.prune(now - self.window)
        LOGGER.debug("%s: %d new samples for %d entities", self.name, pushed, len(states))
        return await self.hass.async_add_executor_job(self._assess, now)

    def _history(self, start: datetime, end: datetime, include_start: bool) -> dict[str, list[Any]]:
        return history.get_significant_states(
            self.hass,
            start,
            end,
            self.entity_ids,
            include_start_time_state=include_start,
            significant_changes_only=False,
        )

    def _assess(self, now: datetime) -> LiveSnapshot:
        self.monitor.refresh(now)
        return self.monitor.snapshot(now)
