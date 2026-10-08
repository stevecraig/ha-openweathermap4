"""Binary sensor: is precipitation expected in the next hour?"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import OWM4ConfigEntry
from .const import ATTRIBUTION
from .coordinator import MinuteCoordinator
from .entity import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OWM4ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the binary sensor."""
    async_add_entities([PrecipitationNextHour(entry, entry.runtime_data.minute)])


class PrecipitationNextHour(CoordinatorEntity[MinuteCoordinator], BinarySensorEntity):
    """On when the minute forecast has precipitation in the coming hour."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_translation_key = "precipitation_next_hour"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE

    def __init__(self, entry: OWM4ConfigEntry, coordinator: MinuteCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}-precipitation_next_hour"
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Re-evaluate every minute (rain that has passed drops off)."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(self.hass, self._tick, timedelta(minutes=1))
        )

    @callback
    def _tick(self, _now: datetime) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """True when any minute ahead reaches the rain threshold."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.summary()["expected"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """When it starts and stops, and how heavy it gets."""
        s = self.coordinator.summary()
        return {
            "starts_at": s["starts_at"],
            "ends_at": s["ends_at"],
            "minutes_until": s["minutes_until"],
            "max_rate": s["max_rate"],
        }
