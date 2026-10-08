"""Setup, entities, call budget and the minute forecast action."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.openweathermap4.api import API_BASE
from custom_components.openweathermap4.const import DOMAIN

from .conftest import API_KEY, NOW, current_body, minute_records, mock_api


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _calls(aioclient_mock: AiohttpClientMocker, path: str) -> int:
    return sum(
        1 for _m, url, *_ in aioclient_mock.mock_calls if url.path.endswith(path)
    )


async def test_setup_creates_entities(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    """All platforms load and read the canned data."""
    mock_api(aioclient_mock)
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    weather = hass.states.get("weather.sea")
    assert weather.state == "rainy"
    assert weather.attributes["temperature"] == 18.5
    assert weather.attributes["humidity"] == 81

    assert hass.states.get("sensor.sea_temperature").state == "18.5"
    assert hass.states.get("sensor.sea_rain_intensity").state == "0.42"
    assert hass.states.get("sensor.sea_precipitation_kind").state == "Rain"
    assert hass.states.get("sensor.sea_weather").state == "light rain"
    assert hass.states.get("sensor.sea_precipitation_probability").state == "65"

    # Rain from minute 12 to 30 at 1.2 mm/h.
    assert hass.states.get("sensor.sea_minutes_until_precipitation").state == "12"
    assert (
        hass.states.get("sensor.sea_next_hour_max_precipitation_intensity").state
        == "1.2"
    )
    assert hass.states.get("sensor.sea_next_hour_precipitation").state == "0.36"
    rain_soon = hass.states.get("binary_sensor.sea_precipitation_next_hour")
    assert rain_soon.state == "on"
    assert rain_soon.attributes["minutes_until"] == 12

    # Every entity sits on one device for the location.
    ent_reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(ent_reg, config_entry.entry_id)
    assert len({e.device_id for e in entries}) == 1


async def test_key_and_units_sent(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    """Requests carry our key, metric units and language, including next pages."""
    mock_api(aioclient_mock)
    await _setup(hass, config_entry)
    for _method, url, *_ in aioclient_mock.mock_calls:
        assert url.query["appid"] == API_KEY
        assert url.query["units"] == "metric"
        assert url.query["lang"] == "en"
    # 48 h of hourly forecast = 3 pages of 20.
    assert _calls(aioclient_mock, "timeline/1h") == 3
    assert _calls(aioclient_mock, "timeline/1day") == 1


async def test_hourly_and_daily_forecasts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    """weather.get_forecasts returns 48 hours and 8 days."""
    mock_api(aioclient_mock)
    await _setup(hass, config_entry)

    hourly = await hass.services.async_call(
        "weather",
        "get_forecasts",
        {"entity_id": "weather.sea", "type": "hourly"},
        blocking=True,
        return_response=True,
    )
    hours = hourly["weather.sea"]["forecast"]
    assert len(hours) == 48
    assert hours[0]["precipitation_probability"] == 65
    assert hours[0]["precipitation"] == 0.3
    assert hours[0]["condition"] == "rainy"

    daily = await hass.services.async_call(
        "weather",
        "get_forecasts",
        {"entity_id": "weather.sea", "type": "daily"},
        blocking=True,
        return_response=True,
    )
    days = daily["weather.sea"]["forecast"]
    assert len(days) == 8
    assert days[0]["temperature"] == 21
    assert days[0]["templow"] == 12
    assert days[0]["precipitation"] == 2.5
    assert days[1]["condition"] == "sunny"
    assert days[1]["precipitation"] == 0


async def test_minute_forecast_action(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    """openweathermap4.get_minute_forecast answers from cache, no extra call."""
    mock_api(aioclient_mock)
    await _setup(hass, config_entry)
    before = _calls(aioclient_mock, "timeline/1min")

    response = await hass.services.async_call(
        DOMAIN,
        "get_minute_forecast",
        {"entity_id": "weather.sea"},
        blocking=True,
        return_response=True,
    )
    forecast = response["weather.sea"]["forecast"]
    assert len(forecast) == 60
    assert forecast[0]["datetime"] == NOW
    assert forecast[12]["precipitation"] == 1.2
    assert _calls(aioclient_mock, "timeline/1min") == before


async def test_countdown_and_dry_hour(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Minutes-until counts down between polls; a dry hour reads off/unknown."""
    mock_api(aioclient_mock)
    await _setup(hass, config_entry)

    freezer.tick(timedelta(minutes=3))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sea_minutes_until_precipitation").state == "9"

    # Next poll (5 min) says the rain has gone.
    mock_api(aioclient_mock, minutes=minute_records(wet_from=None))
    freezer.tick(timedelta(minutes=3))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.sea_precipitation_next_hour").state == "off"
    assert hass.states.get("sensor.sea_minutes_until_precipitation").state == "unknown"
    assert hass.states.get("sensor.sea_next_hour_precipitation").state == "0.0"


async def test_daily_call_budget(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A full day with every entity listening stays under 1,000 calls."""
    mock_api(aioclient_mock)
    await _setup(hass, config_entry)
    for _ in range(24 * 60):
        freezer.tick(timedelta(minutes=1))
        async_fire_time_changed(hass)
    await hass.async_block_till_done()
    calls = len(aioclient_mock.mock_calls)
    assert calls < 1000, calls


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    """A 401 at setup fails the entry and asks for a new key."""
    mock_api(aioclient_mock, status=401)
    config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flows and flows[0]["context"]["source"] == "reauth"


async def test_server_error_retries(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    """Server errors leave the entry to retry later."""
    mock_api(aioclient_mock, status=500)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    """The entry unloads cleanly."""
    mock_api(aioclient_mock)
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_forecast_failure_does_not_block_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    """Only current conditions are required; a failing timeline just retries."""
    mock_api(aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API_BASE}/current", json=current_body())
    aioclient_mock.get(f"{API_BASE}/timeline/1min", status=500, json={})
    aioclient_mock.get(f"{API_BASE}/timeline/1h", status=500, json={})
    aioclient_mock.get(f"{API_BASE}/timeline/1day", status=500, json={})
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("weather.sea").state == "rainy"
    assert (
        hass.states.get("binary_sensor.sea_precipitation_next_hour").state
        == "unavailable"
    )


async def test_stale_hours_and_minutes_dropped(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Between polls, hours and minutes already over are left out."""
    mock_api(aioclient_mock)
    await _setup(hass, config_entry)
    freezer.tick(timedelta(hours=1, minutes=4))

    data = config_entry.runtime_data
    hours = data.hourly.upcoming()
    assert len(hours) == 47
    assert hours[0]["datetime"] == (NOW + timedelta(hours=1)).isoformat()
    assert (
        hass.states.get("sensor.sea_precipitation_probability").state == "65"
    )  # still from the hour under way

    minutes = data.minute.upcoming(NOW + timedelta(minutes=4, seconds=30))
    assert len(minutes) == 56
    assert minutes[0]["datetime"] == NOW + timedelta(minutes=4)
