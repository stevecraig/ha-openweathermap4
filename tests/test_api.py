"""Client edge cases: key never leaks, bad bodies, pagination stops."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.openweathermap4.api import (
    API_BASE,
    OneCall4Client,
    OWMConnectionError,
)

from .conftest import LAT, LON, T0, hourly_page

KEY = "secret-key-123"


def _client(hass: HomeAssistant) -> OneCall4Client:
    return OneCall4Client(async_get_clientsession(hass), KEY, LAT, LON)


async def test_client_error_message_hides_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """aiohttp errors that quote the URL don't expose the key."""
    aioclient_mock.get(
        f"{API_BASE}/current",
        exc=aiohttp.ClientError(f"boom at {API_BASE}/current?appid={KEY}"),
    )
    with pytest.raises(OWMConnectionError) as err:
        await _client(hass).current()
    assert KEY not in str(err.value)
    assert err.value.__cause__ is None


async def test_bad_json_is_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A non-JSON or non-object body maps to OWMConnectionError."""
    aioclient_mock.get(f"{API_BASE}/current", text="<html>maintenance</html>")
    with pytest.raises(OWMConnectionError):
        await _client(hass).current()
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API_BASE}/current", json=[1, 2, 3])
    with pytest.raises(OWMConnectionError):
        await _client(hass).current()


async def test_empty_page_stops_pagination(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An empty page with a `next` link ends the walk (no runaway calls)."""
    t2 = T0 + 20 * 3600
    empty = {"data": [], "next": f"{API_BASE}/timeline/1h?start={t2 + 1}"}
    aioclient_mock.get(f"{API_BASE}/timeline/1h", params={"start": str(t2)}, json=empty)
    aioclient_mock.get(f"{API_BASE}/timeline/1h", json=hourly_page(T0, 20, True))
    records = await _client(hass).hourly(48)
    assert len(records) == 20
    assert aioclient_mock.call_count == 2


async def test_page_cap(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Never more pages than the records asked for need."""
    aioclient_mock.get(f"{API_BASE}/timeline/1h", json=hourly_page(T0, 5, True))
    records = await _client(hass).hourly(48)
    # 48 hours = 3 pages of 20, even if each page is short.
    assert aioclient_mock.call_count == 3
    assert len(records) == 15
