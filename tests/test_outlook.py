"""Next rain / dry hours left today / rain later today."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.openweathermap4.outlook import rain_outlook

from .conftest import NOW, minute_records, mock_api

TZ = "Europe/London"  # NOW = 13:00 BST, so 11 hours to midnight


def hours(pops: dict[int, int], mm: dict[int, float] | None = None) -> list[dict]:
    """48 hours from NOW; pop/mm by hour offset, otherwise dry."""
    mm = mm or {}
    return [
        {
            "datetime": (NOW + timedelta(hours=i)).isoformat(),
            "precipitation_probability": pops.get(i, 0),
            "native_precipitation": mm.get(i, 0.0),
        }
        for i in range(48)
    ]


def minutes(
    *, expected: bool, starts_in: int | None = None, covered: int = 60
) -> dict:
    return {
        "minutes_covered": covered,
        "expected": expected,
        "starts_at": NOW + timedelta(minutes=starts_in) if expected else None,
    }


def outlook(hours_, minutes_=None, now=NOW):
    return rain_outlook(
        hours_, minutes_, now, min_probability=40, min_precipitation=0.2
    )


async def test_minute_forecast_wins_within_the_hour(hass: HomeAssistant) -> None:
    """Rain in the minute data gives an exact time, even if the hour looks dry."""
    await hass.config.async_set_time_zone(TZ)
    o = outlook(hours({}), minutes(expected=True, starts_in=12))
    assert o["next_rain"] == NOW + timedelta(minutes=12)
    assert o["source"] == "minute"
    assert o["rain_today"] is True
    assert o["dry_hours_today"] == 0.2


async def test_first_wet_hour_after_the_minute_data(hass: HomeAssistant) -> None:
    """A dry next hour skips the hourly wet hour it covers."""
    await hass.config.async_set_time_zone(TZ)
    o = outlook(hours({0: 70, 4: 55}), minutes(expected=False))
    assert o["next_rain"] == NOW + timedelta(hours=4)
    assert o["source"] == "hourly"
    assert o["probability"] == 55
    assert o["dry_hours_today"] == 4.0
    assert o["rain_today"] is True


async def test_wet_hour_part_covered_starts_when_minutes_end(
    hass: HomeAssistant,
) -> None:
    """A wet hour half covered by dry minutes starts when the minutes run out."""
    await hass.config.async_set_time_zone(TZ)
    later = NOW + timedelta(minutes=30)
    o = outlook(hours({1: 60}), minutes(expected=False), now=later)
    assert o["next_rain"] == later + timedelta(minutes=60)


async def test_amount_alone_makes_an_hour_wet(hass: HomeAssistant) -> None:
    """Heavy but unlikely-looking rain still counts."""
    await hass.config.async_set_time_zone(TZ)
    o = outlook(hours({3: 20}, {3: 0.5}))
    assert o["next_rain"] == NOW + timedelta(hours=3)
    assert o["precipitation"] == 0.5


async def test_dry_today_rain_tomorrow(hass: HomeAssistant) -> None:
    """Rain after midnight: dry for the rest of today, next rain tomorrow."""
    await hass.config.async_set_time_zone(TZ)
    o = outlook(hours({14: 80}), minutes(expected=False))
    assert o["next_rain"] == NOW + timedelta(hours=14)
    assert o["rain_today"] is False
    assert o["dry_hours_today"] == 11.0


async def test_dry_all_forecast(hass: HomeAssistant) -> None:
    """No wet hour at all: no next rain, dry until midnight."""
    await hass.config.async_set_time_zone(TZ)
    o = outlook(hours({}))
    assert o["next_rain"] is None
    assert o["source"] is None
    assert o["rain_today"] is False
    assert o["dry_hours_today"] == 11.0
    assert o["end_of_today"] == datetime(2026, 6, 1, 23, 0, tzinfo=UTC)


async def test_no_hourly_data(hass: HomeAssistant) -> None:
    """Without the hourly forecast there is no outlook."""
    assert outlook(None, minutes(expected=True, starts_in=5)) is None


async def test_entities(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The three entities read the outlook and follow the minute data."""
    await hass.config.async_set_time_zone(TZ)
    mock_api(aioclient_mock)  # every hour 65 %, minute rain from minute 12
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    next_rain = hass.states.get("sensor.sea_next_rain")
    assert dt_util.parse_datetime(next_rain.state) == NOW + timedelta(minutes=12)
    assert next_rain.attributes["source"] == "minute"
    assert hass.states.get("sensor.sea_dry_hours_left_today").state == "0.2"
    rain_today = hass.states.get("binary_sensor.sea_rain_later_today")
    assert rain_today.state == "on"

    # Next minute poll is dry: the hourly forecast says rain from the next hour.
    mock_api(aioclient_mock, minutes=minute_records(wet_from=None))
    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    next_rain = hass.states.get("sensor.sea_next_rain")
    assert next_rain.attributes["source"] == "hourly"
    assert dt_util.parse_datetime(next_rain.state) == NOW + timedelta(hours=1)


async def test_thresholds_from_options(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Raising the chance needed above the forecast's 65 % leaves only amounts."""
    await hass.config.async_set_time_zone(TZ)
    mock_api(aioclient_mock, minutes=minute_records(wet_from=None))
    entry = MockConfigEntry(
        domain="openweathermap4",
        title="Sea",
        unique_id="10.0--30.0",
        data={"api_key": "test-key", "latitude": 10.0, "longitude": -30.0},
        options={"language": "en", "rain_probability": 70, "rain_amount": 0.5},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # Canned hours are 65 % and 0.3 mm: below both thresholds.
    assert hass.states.get("sensor.sea_next_rain").state == "unknown"
    assert hass.states.get("binary_sensor.sea_rain_later_today").state == "off"
    assert hass.states.get("sensor.sea_dry_hours_left_today").state == "11.0"
