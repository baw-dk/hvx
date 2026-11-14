# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Config and options flows: building settings -> areas -> sensors per area."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    BUILDING_TYPES,
    CATEGORIES,
    CONF_AREAS,
    CONF_BUILDING_TYPE,
    CONF_ROOMS,
    CONF_SCAN_INTERVAL,
    CONF_TARGET_CATEGORY,
    CONF_WINDOW_DAYS,
    DEFAULT_BUILDING_TYPE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TARGET_CATEGORY,
    DEFAULT_WINDOW_DAYS,
    DOMAIN,
    PARAMETER_DEVICE_CLASSES,
    PARAMETER_LABELS,
)
from .discovery import area_infos, candidate_sensors, detect_rooms


def _settings_schema(defaults: dict[str, Any]) -> dict:
    return {
        vol.Required(CONF_TARGET_CATEGORY, default=defaults.get(CONF_TARGET_CATEGORY, DEFAULT_TARGET_CATEGORY)): selector.SelectSelector(
            selector.SelectSelectorConfig(options=CATEGORIES, mode=selector.SelectSelectorMode.LIST, translation_key="target_category")
        ),
        vol.Required(CONF_WINDOW_DAYS, default=defaults.get(CONF_WINDOW_DAYS, DEFAULT_WINDOW_DAYS)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=30, step=1, unit_of_measurement="d", mode=selector.NumberSelectorMode.BOX)
        ),
        vol.Required(CONF_SCAN_INTERVAL, default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=5, max=240, step=5, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX)
        ),
    }


def _areas_schema(default: list[str]) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_AREAS, default=default): selector.AreaSelector(selector.AreaSelectorConfig(multiple=True))})


def _sensor_field(area_name: str, parameter: str) -> str:
    return f"{area_name} · {PARAMETER_LABELS[parameter]}"


def _sensors_schema(hass: HomeAssistant, rooms: dict[str, dict[str, Any]]) -> tuple[vol.Schema, dict[str, tuple[str, str]]]:
    """One optional entity picker per (area, parameter), pre-filled; returns schema and key map."""
    infos = area_infos(hass)
    fields: dict = {}
    keys: dict[str, tuple[str, str]] = {}
    for area_id, params in sorted(rooms.items(), key=lambda kv: infos[kv[0]].name if kv[0] in infos else kv[0]):
        name = infos[area_id].name if area_id in infos else area_id
        for parameter, device_class in PARAMETER_DEVICE_CLASSES.items():
            key = _sensor_field(name, parameter)
            keys[key] = (area_id, parameter)
            current = params.get(parameter)
            marker = vol.Optional(key, description={"suggested_value": current}) if current else vol.Optional(key)
            fields[marker] = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class=device_class))
    return vol.Schema(fields), keys


def _rooms_from_input(keys: dict[str, tuple[str, str]], user_input: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rooms: dict[str, dict[str, Any]] = {}
    for key, (area_id, parameter) in keys.items():
        rooms.setdefault(area_id, {p: None for p in PARAMETER_DEVICE_CLASSES})[parameter] = user_input.get(key) or None
    return {a: p for a, p in rooms.items() if any(p.values())}


class HvxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up an HVX building."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._options: dict[str, Any] = {}
        self._keys: dict[str, tuple[str, str]] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not candidate_sensors(self.hass):
            return self.async_abort(reason="no_sensors")
        if user_input is not None:
            self._data = {CONF_NAME: user_input[CONF_NAME], CONF_BUILDING_TYPE: user_input[CONF_BUILDING_TYPE]}
            self._options = {k: user_input[k] for k in (CONF_TARGET_CATEGORY, CONF_WINDOW_DAYS, CONF_SCAN_INTERVAL)}
            return await self.async_step_areas()
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=self.hass.config.location_name or "Home"): selector.TextSelector(),
                vol.Required(CONF_BUILDING_TYPE, default=DEFAULT_BUILDING_TYPE): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=BUILDING_TYPES, translation_key="building_type")
                ),
                **_settings_schema({}),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_areas(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_AREAS]:
                return await self.async_step_sensors(rooms=detect_rooms(self.hass, user_input[CONF_AREAS]))
            errors["base"] = "no_areas"
        return self.async_show_form(step_id="areas", data_schema=_areas_schema(sorted(candidate_sensors(self.hass))), errors=errors)

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None, rooms: dict[str, dict[str, Any]] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            selected = _rooms_from_input(self._keys, user_input)
            if selected:
                return self.async_create_entry(title=self._data[CONF_NAME], data=self._data, options={**self._options, CONF_ROOMS: selected})
            errors["base"] = "no_sensors_selected"
            rooms = _rooms_from_input(self._keys, {}) or {a: {} for a, _ in self._keys.values()}
        schema, self._keys = _sensors_schema(self.hass, rooms or {})
        return self.async_show_form(step_id="sensors", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HvxOptionsFlow()


class HvxOptionsFlow(OptionsFlow):
    """Change targets, window, interval, rooms and sensors."""

    def __init__(self) -> None:
        self._settings: dict[str, Any] = {}
        self._keys: dict[str, tuple[str, str]] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = dict(self.config_entry.options)
        if user_input is not None:
            self._settings = {k: user_input[k] for k in (CONF_TARGET_CATEGORY, CONF_WINDOW_DAYS, CONF_SCAN_INTERVAL)}
            existing = current.get(CONF_ROOMS, {})
            detected = detect_rooms(self.hass, [a for a in user_input[CONF_AREAS] if a not in existing])
            rooms = {a: existing.get(a) or detected.get(a, {}) for a in user_input[CONF_AREAS]}
            schema, self._keys = _sensors_schema(self.hass, rooms)
            return self.async_show_form(step_id="sensors", data_schema=schema)
        schema = vol.Schema({**_settings_schema(current), **_areas_schema(list(current.get(CONF_ROOMS, {}))).schema})
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        rooms = _rooms_from_input(self._keys, user_input or {})
        if not rooms:
            schema, _ = _sensors_schema(self.hass, {a: {} for a, _ in self._keys.values()})
            return self.async_show_form(step_id="sensors", data_schema=schema, errors={"base": "no_sensors_selected"})
        return self.async_create_entry(data={**self._settings, CONF_ROOMS: rooms})
