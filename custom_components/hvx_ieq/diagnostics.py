"""Diagnostics download (Settings → Devices & services → HVX → ⋮ → Download diagnostics)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import HvxConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: HvxConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "options": dict(entry.options),
        "data": dict(entry.data),
        "bindings": [asdict(b) for b in coordinator.monitor.bindings],
        "snapshot": None
        if data is None
        else {
            "generated_at": data.generated_at,
            "season": data.season,
            "summary": asdict(data.summary),
            "rooms": {
                room_id: {
                    "category_now": s.category_now,
                    "alerts": s.alerts,
                    "current": {k: asdict(v) for k, v in s.current.items()},
                    "window_status": s.window.status if s.window else None,
                    "window_category": s.window.achieved_category if s.window else None,
                    "window_warnings": s.window.warnings if s.window else None,
                }
                for room_id, s in data.rooms.items()
            },
        },
    }
