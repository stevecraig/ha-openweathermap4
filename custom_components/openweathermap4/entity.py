"""Shared entity helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN, MANUFACTURER

if TYPE_CHECKING:
    from . import OWM4ConfigEntry


def device_info(entry: OWM4ConfigEntry) -> DeviceInfo:
    """One service device per configured location."""
    return DeviceInfo(
        entry_type=DeviceEntryType.SERVICE,
        identifiers={(DOMAIN, str(entry.unique_id))},
        manufacturer=MANUFACTURER,
        model="One Call API 4.0",
        name=entry.title,
    )
