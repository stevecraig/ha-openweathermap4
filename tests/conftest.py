"""Fixtures: canned One Call 4.0 responses built around a frozen 'now'."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.openweathermap4.api import API_BASE
from custom_components.openweathermap4.const import DOMAIN

# Made-up location (open sea), not anyone's home.
LAT, LON = 10.0, -30.0
API_KEY = "test-key"
NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
T0 = int(NOW.timestamp())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every test."""
    return


@pytest.fixture(autouse=True)
def frozen_time(freezer) -> Generator[None]:
    """Freeze time at NOW."""
    freezer.move_to(NOW)
    yield


def weather(code: int = 500, desc: str = "light rain") -> list[dict]:
    return [{"id": code, "main": "Rain", "description": desc, "icon": "10d"}]


def current_body() -> dict:
    return {
        "lat": LAT,
        "lon": LON,
        "timezone": "Etc/GMT+2",
        "timezone_offset": -7200,
        "data": [
            {
                "dt": T0,
                "sunrise": T0 - 6 * 3600,
                "sunset": T0 + 6 * 3600,
                "temp": 18.5,
                "feels_like": 17.9,
                "pressure": 1012,
                "humidity": 81,
                "dew_point": 15.1,
                "uvi": 2.4,
                "clouds": 90,
                "visibility": 9000,
                "wind_speed": 5.2,
                "wind_gust": 9.1,
                "wind_deg": 230,
                "rain": {"1h": 0.42},
                "weather": weather(),
                "alerts": [],
            }
        ],
    }


def minute_records(wet_from: int | None = 12, wet_to: int = 30, rate: float = 1.2):
    """60 one-minute records; rain between minutes wet_from..wet_to."""
    return [
        {
            "dt": T0 + i * 60,
            "precipitation": rate
            if wet_from is not None and wet_from <= i < wet_to
            else 0,
        }
        for i in range(60)
    ]


def hourly_page(start: int, count: int, more: bool) -> dict:
    body = {
        "lat": LAT,
        "lon": LON,
        "data": [
            {
                "dt": start + i * 3600,
                "temp": 18 + i % 5,
                "feels_like": 17 + i % 5,
                "pressure": 1010,
                "humidity": 80,
                "dew_point": 14,
                "uvi": 1,
                "clouds": 75,
                "visibility": 10000,
                "wind_speed": 4,
                "wind_deg": 200,
                "pop": 0.65,
                "rain": {"1h": 0.3},
                "weather": weather(),
            }
            for i in range(count)
        ],
    }
    if more:
        nxt = start + count * 3600
        body["next"] = (
            f"{API_BASE}/timeline/1h?lat={LAT}&lon={LON}&start={nxt}&appid={{API key}}"
        )
    return body


def daily_body() -> dict:
    return {
        "lat": LAT,
        "lon": LON,
        "data": [
            {
                "dt": T0 + d * 86400,
                "temp": {
                    "day": 20,
                    "min": 12 + d,
                    "max": 21 + d,
                    "night": 13,
                    "eve": 18,
                    "morn": 13,
                },
                "feels_like": {"day": 19.5, "night": 12, "eve": 17, "morn": 12},
                "pressure": 1015,
                "humidity": 70,
                "dew_point": 12,
                "wind_speed": 6,
                "wind_deg": 250,
                "wind_gust": 11,
                "weather": weather(800, "clear sky") if d % 2 else weather(),
                "clouds": 40,
                "pop": 0.2 * (d % 5),
                "rain": {"1h": 2.5} if not d % 2 else None,
                "uvi": 5,
            }
            for d in range(10)
        ],
        "next": f"{API_BASE}/timeline/1day?lat={LAT}&lon={LON}&start={T0 + 10 * 86400}",
    }


def mock_api(
    aioclient_mock: AiohttpClientMocker,
    *,
    status: int = 200,
    minutes: list[dict] | None = None,
) -> None:
    """Register every One Call 4.0 endpoint."""
    aioclient_mock.clear_requests()
    if status != 200:
        for path in ("current", "timeline/1min", "timeline/1h", "timeline/1day"):
            aioclient_mock.get(
                f"{API_BASE}/{path}",
                status=status,
                json={"cod": status, "message": "nope"},
            )
        return
    aioclient_mock.get(f"{API_BASE}/current", json=current_body())
    aioclient_mock.get(
        f"{API_BASE}/timeline/1min",
        json={"lat": LAT, "lon": LON, "data": minutes or minute_records()},
    )
    # Pages 2 and 3 are matched on their start param, so register them first.
    t2, t3 = T0 + 20 * 3600, T0 + 40 * 3600
    aioclient_mock.get(
        f"{API_BASE}/timeline/1h",
        params={"start": str(t2)},
        json=hourly_page(t2, 20, True),
    )
    aioclient_mock.get(
        f"{API_BASE}/timeline/1h",
        params={"start": str(t3)},
        json=hourly_page(t3, 20, True),
    )
    aioclient_mock.get(f"{API_BASE}/timeline/1h", json=hourly_page(T0, 20, True))
    aioclient_mock.get(f"{API_BASE}/timeline/1day", json=daily_body())


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Sea",
        unique_id=f"{LAT}-{LON}",
        data={"api_key": API_KEY, "latitude": LAT, "longitude": LON},
        options={"language": "en"},
    )
