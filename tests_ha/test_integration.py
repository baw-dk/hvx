# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""End-to-end tests of the hvx_ieq integration inside Home Assistant (recorder included)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.components.recorder.common import async_wait_recording_done

from custom_components.hvx_ieq.const import CONF_ROOMS, CONF_TARGET_CATEGORY, DOMAIN

START = datetime(2025, 1, 14, 16, 0, tzinfo=timezone.utc)  # 08:00 on a winter weekday in the test instance (US/Pacific)
STEPS = 48  # 8 hours at 10-minute steps

SENSORS = {
    # entity suffix: (area, device class, unit, value(step))
    "office_temperature": ("office", "temperature", "°C", lambda i: 22.0 + 0.1 * (i % 3)),
    "office_co2": ("office", "carbon_dioxide", "ppm", lambda i: 600.0 + 5 * (i % 4)),
    "office_humidity": ("office", "humidity", "%", lambda i: 40.0),
    "meeting_temperature": ("meeting", "temperature", "°C", lambda i: 23.0),
    "meeting_co2": ("meeting", "carbon_dioxide", "ppm", lambda i: 700.0 + 25 * i),  # climbs to ~1900 ppm
    "garden_temperature": ("garden", "temperature", "°C", lambda i: 2.0),
}


async def _setup_home(hass: HomeAssistant, freezer) -> dict[str, str]:
    floors = fr.async_get(hass)
    ground = floors.async_create("Ground floor", level=0)
    areas = ar.async_get(hass)
    area_ids = {
        "office": areas.async_create("Office", floor_id=ground.floor_id).id,
        "meeting": areas.async_create("Meeting room", floor_id=ground.floor_id).id,
        "garden": areas.async_create("Garden").id,
    }
    entities = er.async_get(hass)
    for suffix, (area, device_class, _unit, _fn) in SENSORS.items():
        entry = entities.async_get_or_create(
            "sensor", "test", suffix, suggested_object_id=suffix, original_device_class=device_class
        )
        entities.async_update_entity(entry.entity_id, area_id=area_ids[area])

    freezer.move_to(START)
    for i in range(STEPS):
        for suffix, (_area, device_class, unit, fn) in SENSORS.items():
            hass.states.async_set(
                f"sensor.{suffix}", str(fn(i)), {"unit_of_measurement": unit, "device_class": device_class}
            )
        await hass.async_block_till_done()
        freezer.tick(timedelta(minutes=10))
    await async_wait_recording_done(hass)
    return area_ids


def _entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id, unique_id
    return entity_id


async def _create_entry(hass: HomeAssistant, area_ids: dict[str, str]):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Test office", "building_type": "office", "target_category": "cat_ii", "window_days": 1, "scan_interval": 15},
    )
    assert result["step_id"] == "areas"
    # all three areas with sensors are suggested
    default = next(k for k in result["data_schema"].schema if k == "areas").default()
    assert set(default) == set(area_ids.values())

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"areas": [area_ids["office"], area_ids["meeting"]]})
    assert result["step_id"] == "sensors"
    fields = {str(k): k for k in result["data_schema"].schema}
    assert "Office · CO₂" in fields and "Garden · temperature" not in fields
    # detected sensors are pre-filled as suggestions
    assert fields["Meeting room · CO₂"].description["suggested_value"] == "sensor.meeting_co2"
    assert "suggested_value" not in (fields["Meeting room · humidity"].description or {})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "Office · temperature": "sensor.office_temperature",
            "Office · CO₂": "sensor.office_co2",
            "Office · humidity": "sensor.office_humidity",
            "Meeting room · temperature": "sensor.meeting_temperature",
            "Meeting room · CO₂": "sensor.meeting_co2",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return result["result"]


async def test_full_flow_entities_and_report(hass: HomeAssistant, recorder_mock, freezer) -> None:
    area_ids = await _setup_home(hass, freezer)
    entry = await _create_entry(hass, area_ids)
    assert entry.options[CONF_ROOMS][area_ids["meeting"]] == {
        "temperature": "sensor.meeting_temperature", "co2": "sensor.meeting_co2", "humidity": None,
    }
    assert entry.state is config_entries.ConfigEntryState.LOADED
    office, meeting = area_ids["office"], area_ids["meeting"]

    # Window assessment from recorder history
    office_score = hass.states.get(_entity_id(hass, "sensor", f"{entry.entry_id}_{office}_ieq_score"))
    meeting_score = hass.states.get(_entity_id(hass, "sensor", f"{entry.entry_id}_{meeting}_ieq_score"))
    assert float(office_score.state) == pytest.approx(100.0, abs=0.5)  # constant humidity held, not "missing"
    assert float(meeting_score.state) < float(office_score.state)
    co2_comp = hass.states.get(_entity_id(hass, "sensor", f"{entry.entry_id}_{meeting}_co2_compliance"))
    assert 0 < float(co2_comp.state) < 100
    assert meeting_score.attributes["issues"]

    # Live state: meeting room CO2 is now ~1900 ppm -> problem; office fine
    problem = hass.states.get(_entity_id(hass, "binary_sensor", f"{entry.entry_id}_{meeting}_ieq_problem"))
    assert problem.state == "on" and any("co2" in a for a in problem.attributes["alerts"])
    assert hass.states.get(_entity_id(hass, "binary_sensor", f"{entry.entry_id}_{office}_ieq_problem")).state == "off"
    # A state change is reflected without waiting for the 15-minute window refresh
    hass.states.async_set("sensor.meeting_co2", "650", {"unit_of_measurement": "ppm", "device_class": "carbon_dioxide"})
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=15))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    problem_id = _entity_id(hass, "binary_sensor", f"{entry.entry_id}_{meeting}_ieq_problem")
    assert hass.states.get(problem_id).state == "off"
    # ...and the window assessment from the last full refresh is kept
    assert float(hass.states.get(meeting_score.entity_id).state) == float(meeting_score.state)

    now_cat = hass.states.get(_entity_id(hass, "sensor", f"{entry.entry_id}_{office}_current_category"))
    assert now_cat.state in ("cat_i", "cat_ii")

    building = hass.states.get(_entity_id(hass, "sensor", f"{entry.entry_id}_building_ieq_score"))
    assert building.attributes["rooms_analysed"] == 2
    meeting_target = hass.states.get(_entity_id(hass, "sensor", f"{entry.entry_id}_building_rooms_meeting_target"))
    assert float(meeting_target.state) == pytest.approx(50.0)

    # Devices: room devices sit in their area, under the building device
    from homeassistant.helpers import device_registry as dr

    devices = dr.async_get(hass)
    room_device = devices.async_get_device({(DOMAIN, f"{entry.entry_id}_{meeting}")})
    assert room_device.area_id == meeting and room_device.via_device_id is not None

    # Report service with response
    response = await hass.services.async_call(DOMAIN, "generate_report", {"format": "html", "full_analysis": False}, blocking=True, return_response=True)
    path = Path(response["path"])
    assert path.exists() and "Test office" in path.read_text(encoding="utf-8")
    assert response["url"].startswith("/local/hvx_ieq/")

    # Options: stricter target reloads the entry
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"target_category": "cat_i", "window_days": 1, "scan_interval": 15, "areas": [office]}
    )
    assert result["step_id"] == "sensors"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"Office · temperature": "sensor.office_temperature", "Office · CO₂": "sensor.office_co2"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_TARGET_CATEGORY] == "cat_i" and list(entry.options[CONF_ROOMS]) == [office]
    assert entry.runtime_data.target_category == "I"
    assert er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{office}_ieq_score")

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_abort_without_sensors(hass: HomeAssistant, recorder_mock) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "no_sensors"


async def test_diagnostics(hass: HomeAssistant, recorder_mock, freezer) -> None:
    # Called directly: the frozen clock would invalidate the HTTP test client's auth token.
    from custom_components.hvx_ieq.diagnostics import async_get_config_entry_diagnostics

    area_ids = await _setup_home(hass, freezer)
    entry = await _create_entry(hass, area_ids)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert len(diag["bindings"]) == 5
    assert diag["snapshot"]["summary"]["rooms_analysed"] == 2
    import json

    json.dumps(diag, default=str)  # must be serialisable for the download
