"""HVX Indoor Environment: EN 16798-1 IEQ monitoring for Home Assistant areas."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_FORMAT,
    ATTR_FULL_ANALYSIS,
    DOMAIN,
    REPORT_DIR,
    SERVICE_GENERATE_REPORT,
)
from .coordinator import HvxConfigEntry, HvxCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

REPORT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_FORMAT, default="html"): vol.In(["html", "json", "csv"]),
        vol.Optional(ATTR_FULL_ANALYSIS, default=True): cv.boolean,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def generate_report(call: ServiceCall) -> ServiceResponse:
        entries: list[HvxConfigEntry] = hass.config_entries.async_loaded_entries(DOMAIN)
        entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
        if entry_id:
            entries = [e for e in entries if e.entry_id == entry_id]
        if not entries:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_entry")
        entry = entries[0]
        coordinator: HvxCoordinator = entry.runtime_data
        fmt = call.data[ATTR_FORMAT]
        full = call.data[ATTR_FULL_ANALYSIS]

        def build() -> str:
            from dataclasses import replace

            from hvx.reporting import write

            snapshot_season = coordinator.data.season if coordinator.data else "winter"
            config = replace(
                coordinator.report_config,
                title=entry.title,
                seasons=(snapshot_season,),
                include_simulations=full,
            )
            report = coordinator.monitor.report(config)
            target = Path(hass.config.path("www", REPORT_DIR, f"{entry.entry_id}.{fmt}"))
            write(report, target, fmt)
            return str(target)

        path = await hass.async_add_executor_job(build)
        url = f"/local/{REPORT_DIR}/{entry.entry_id}.{fmt}"
        persistent_notification.async_create(
            hass,
            f"IEQ report for **{entry.title}** is ready: [{url}]({url})",
            title="HVX IEQ report",
            notification_id=f"{DOMAIN}_{entry.entry_id}_report",
        )
        return {"path": path, "url": url}

    hass.services.async_register(
        DOMAIN, SERVICE_GENERATE_REPORT, generate_report, schema=REPORT_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HvxConfigEntry) -> bool:
    coordinator = HvxCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    coordinator.async_start_live_updates()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: HvxConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HvxConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
