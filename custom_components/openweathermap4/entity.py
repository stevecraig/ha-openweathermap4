"""Shared entity helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CONF_RAIN_AMOUNT,
    CONF_RAIN_PROBABILITY,
    DEFAULT_RAIN_AMOUNT,
    DEFAULT_RAIN_PROBABILITY,
    DOMAIN,
    MANUFACTURER,
)
from .outlook import rain_outlook

if TYPE_CHECKING:
    from homeassistant.helpers.update_coordinator import CoordinatorEntity

    from . import OWM4ConfigEntry
    from .coordinator import HourlyCoordinator

    _Base = CoordinatorEntity[HourlyCoordinator]
else:
    _Base = object


def device_info(entry: OWM4ConfigEntry) -> DeviceInfo:
    """One service device per configured location."""
    return DeviceInfo(
        entry_type=DeviceEntryType.SERVICE,
        identifiers={(DOMAIN, str(entry.unique_id))},
        manufacturer=MANUFACTURER,
        model="One Call API 4.0",
        name=entry.title,
    )


class RainOutlookMixin(_Base):
    """For entities on the hourly coordinator that also follow the minute
    forecast and re-evaluate every minute (the outlook depends on the time)."""

    async def async_added_to_hass(self) -> None:
        """Follow the minute forecast too, and tick every minute."""
        await super().async_added_to_hass()
        entry = self.coordinator.config_entry
        self.async_on_remove(
            entry.runtime_data.minute.async_add_listener(self.async_write_ha_state)
        )
        self.async_on_remove(
            async_track_time_interval(self.hass, self._tick, timedelta(minutes=1))
        )

    @callback
    def _tick(self, _now: datetime) -> None:
        self.async_write_ha_state()

    def outlook(self) -> dict[str, Any] | None:
        """The rain outlook right now, with the entry's thresholds."""
        entry = self.coordinator.config_entry
        minute = entry.runtime_data.minute
        return rain_outlook(
            self.coordinator.upcoming(),
            minute.summary() if minute.data is not None else None,
            dt_util.utcnow(),
            min_probability=entry.options.get(
                CONF_RAIN_PROBABILITY, DEFAULT_RAIN_PROBABILITY
            ),
            min_precipitation=entry.options.get(CONF_RAIN_AMOUNT, DEFAULT_RAIN_AMOUNT),
        )
