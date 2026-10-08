"""OpenWeatherMap One Call 4.0 integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LANGUAGE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import OneCall4Client
from .const import DEFAULT_LANGUAGE, DOMAIN, PLATFORMS
from .coordinator import (
    CurrentCoordinator,
    DailyCoordinator,
    HourlyCoordinator,
    MinuteCoordinator,
)
from .services import async_setup_services

type OWM4ConfigEntry = ConfigEntry[OWM4Data]


@dataclass
class OWM4Data:
    """Runtime data for a config entry."""

    current: CurrentCoordinator
    hourly: HourlyCoordinator
    daily: DailyCoordinator
    minute: MinuteCoordinator


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: OWM4ConfigEntry) -> bool:
    """Set up from a config entry."""
    client = OneCall4Client(
        async_get_clientsession(hass),
        entry.data[CONF_API_KEY],
        entry.data[CONF_LATITUDE],
        entry.data[CONF_LONGITUDE],
        entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE),
    )
    data = OWM4Data(
        current=CurrentCoordinator(hass, entry, client),
        hourly=HourlyCoordinator(hass, entry, client),
        daily=DailyCoordinator(hass, entry, client),
        minute=MinuteCoordinator(hass, entry, client),
    )
    # Current conditions must work (this also checks the key); the forecasts
    # are best effort at startup and retry on their own schedule.
    await data.current.async_config_entry_first_refresh()
    await asyncio.gather(
        data.hourly.async_refresh(),
        data.daily.async_refresh(),
        data.minute.async_refresh(),
    )
    entry.runtime_data = data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OWM4ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
