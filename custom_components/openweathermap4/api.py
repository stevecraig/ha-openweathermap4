"""Minimal async client for the OpenWeatherMap One Call API 4.0."""

from __future__ import annotations

from typing import Any

import aiohttp
from yarl import URL

API_BASE = "https://api.openweathermap.org/data/4.0/onecall"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)

# Maximum records the API returns per page (fixed by OpenWeatherMap).
PAGE_SIZE = {"1min": 60, "15min": 50, "1h": 20, "1day": 10}


class OWMError(Exception):
    """Base error for the One Call 4.0 client."""


class OWMAuthError(OWMError):
    """The API key is missing, invalid or has no One Call 4.0 subscription."""


class OWMRateLimitError(OWMError):
    """The daily call limit has been reached."""


class OWMConnectionError(OWMError):
    """The API could not be reached or returned an unexpected error."""


class OneCall4Client:
    """Talks to the One Call 4.0 endpoints.

    Every request (including each page of a timeline) counts as one API call.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        latitude: float,
        longitude: float,
        language: str = "en",
    ) -> None:
        """Initialise the client."""
        self._session = session
        self._api_key = api_key
        self._latitude = latitude
        self._longitude = longitude
        self._language = language

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        query = {
            "lat": self._latitude,
            "lon": self._longitude,
            "units": "metric",
            "lang": self._language,
            "appid": self._api_key,
            **(params or {}),
        }
        return await self._request(f"{API_BASE}/{path}", query)

    async def _request(self, url: str, params: dict[str, Any] | None) -> dict:
        try:
            async with self._session.get(
                url, params=params, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status == 401:
                    raise OWMAuthError(self._redact(await _message(resp)))
                if resp.status == 429:
                    raise OWMRateLimitError(self._redact(await _message(resp)))
                if resp.status != 200:
                    raise OWMConnectionError(
                        f"HTTP {resp.status}: {self._redact(await _message(resp))}"
                    )
                body = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            # aiohttp messages can include the request URL, which has the key.
            raise OWMConnectionError(
                self._redact(str(err)) or type(err).__name__
            ) from None
        if not isinstance(body, dict):
            raise OWMConnectionError("Unexpected response from OpenWeatherMap")
        return body

    def _redact(self, text: str) -> str:
        return text.replace(self._api_key, "**REDACTED**") if self._api_key else text

    async def _timeline(self, step: str, max_records: int) -> list[dict]:
        """Fetch a timeline, following `next` pages until max_records."""
        body = await self._get(f"timeline/{step}")
        records: list[dict] = list(body.get("data") or [])
        # Never fetch more pages than max_records needs (each page is billed).
        pages_left = -(-max_records // PAGE_SIZE[step]) - 1
        while len(records) < max_records and body.get("next") and pages_left > 0:
            pages_left -= 1
            # The `next` link carries lat/lon/start; make sure our own
            # units/lang/key are on it (replacing any it echoes back).
            next_url = URL(body["next"]).update_query(
                units="metric", lang=self._language, appid=self._api_key
            )
            body = await self._request(str(next_url), None)
            page = body.get("data") or []
            if not page:
                break
            records.extend(page)
        return records[:max_records]

    async def current(self) -> dict:
        """Return the current conditions record."""
        data = (await self._get("current")).get("data") or []
        return data[0] if data else {}

    async def minutely(self) -> list[dict]:
        """Return up to 60 one-minute precipitation records."""
        return await self._timeline("1min", PAGE_SIZE["1min"])

    async def hourly(self, hours: int) -> list[dict]:
        """Return up to `hours` hourly records (20 per call)."""
        return await self._timeline("1h", hours)

    async def daily(self, days: int) -> list[dict]:
        """Return up to `days` daily records (10 per call)."""
        return await self._timeline("1day", days)

    async def validate(self) -> None:
        """Make one cheap call; raises OWMAuthError for a bad key."""
        await self._get("current")


async def _message(resp: aiohttp.ClientResponse) -> str:
    try:
        body = await resp.json(content_type=None)
        if isinstance(body, dict) and body.get("message"):
            return str(body["message"])
    except (ValueError, aiohttp.ClientError):
        pass
    return resp.reason or ""
