"""Diagnostics (API key and location redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from . import OWM4ConfigEntry

TO_REDACT = {CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE, "unique_id", "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OWM4ConfigEntry
) -> dict[str, Any]:
    """Return redacted entry data and the latest data from each coordinator."""
    data = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "current": data.current.data,
        "hourly_count": len(data.hourly.data or []),
        "daily_count": len(data.daily.data or []),
        "minute_summary": data.minute.summary(),
        "last_success": {
            name: coordinator.last_update_success_time
            for name, coordinator in (
                ("current", data.current),
                ("hourly", data.hourly),
                ("daily", data.daily),
                ("minute", data.minute),
            )
        },
    }
