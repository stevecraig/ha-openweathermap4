"""Data update coordinators for OpenWeatherMap One Call 4.0.

Each part of the forecast has its own coordinator so it can be polled at its
own pace (see the interval constants for the call budget).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_SUNNY,
    Forecast,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import sun
from homeassistant.helpers.update_coordinator import (
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import OneCall4Client, OWMAuthError, OWMError, OWMRateLimitError
from .const import (
    CONDITION_MAP,
    CURRENT_INTERVAL,
    DAILY_DAYS,
    DAILY_INTERVAL,
    DOMAIN,
    HOURLY_HOURS,
    HOURLY_INTERVAL,
    MINUTE_INTERVAL,
    RAIN_THRESHOLD,
    WEATHER_CODE_SUNNY_OR_CLEAR_NIGHT,
)

if TYPE_CHECKING:
    from . import OWM4ConfigEntry

_LOGGER = logging.getLogger(__name__)


class OWM4Coordinator[T](TimestampDataUpdateCoordinator[T]):
    """Base coordinator: one fetch, errors mapped to HA's expectations."""

    config_entry: OWM4ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: OWM4ConfigEntry,
        client: OneCall4Client,
        part: str,
        interval: timedelta,
    ) -> None:
        """Initialise the coordinator."""
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN} {part}",
            update_interval=interval,
        )

    async def _fetch(self, call: Callable[[], Awaitable[Any]]) -> Any:
        try:
            return await call()
        except OWMAuthError as err:
            raise ConfigEntryAuthFailed(
                f"OpenWeatherMap rejected the API key: {err}"
            ) from err
        except OWMRateLimitError as err:
            raise UpdateFailed(
                f"OpenWeatherMap daily call limit reached: {err}"
            ) from err
        except OWMError as err:
            raise UpdateFailed(f"OpenWeatherMap request failed: {err}") from err

    def condition(
        self, weather: list[dict] | None, timestamp: int | None, daily: bool = False
    ) -> str | None:
        """Map an OWM weather code to an HA condition (sunny vs clear night)."""
        if not weather:
            return None
        code = weather[0].get("id")
        if code == WEATHER_CODE_SUNNY_OR_CLEAR_NIGHT:
            if daily:  # a day's summary: clear means sunny
                return ATTR_CONDITION_SUNNY
            when = dt_util.utc_from_timestamp(timestamp) if timestamp else None
            if sun.is_up(self.hass, when):
                return ATTR_CONDITION_SUNNY
            return ATTR_CONDITION_CLEAR_NIGHT
        return CONDITION_MAP.get(code)


def precip_value(value: Any) -> float:
    """Rain/snow can be a number or an object like {"1h": 0.3}."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    if isinstance(value, dict):
        for key in ("1h", "3h", "all"):
            if isinstance(value.get(key), (int, float)):
                return round(float(value[key]), 2)
    return 0.0


def precip_kind(rain: float, snow: float) -> str:
    """Describe the precipitation kind the way the core integration does."""
    if rain and snow:
        return "Snow and Rain"
    if rain:
        return "Rain"
    if snow:
        return "Snow"
    return "None"


def iso(timestamp: int) -> str:
    """Unix seconds to an ISO string in UTC."""
    return dt_util.utc_from_timestamp(timestamp).isoformat()


class CurrentCoordinator(OWM4Coordinator[dict[str, Any]]):
    """Current conditions."""

    def __init__(self, hass, config_entry, client) -> None:
        """Initialise."""
        super().__init__(hass, config_entry, client, "current", CURRENT_INTERVAL)

    async def _async_update_data(self) -> dict[str, Any]:
        record = await self._fetch(self.client.current)
        weather = record.get("weather") or []
        rain = precip_value(record.get("rain"))
        snow = precip_value(record.get("snow"))
        return {
            "condition": self.condition(weather, record.get("dt")),
            "temperature": record.get("temp"),
            "feels_like_temperature": record.get("feels_like"),
            "pressure": record.get("pressure"),
            "humidity": record.get("humidity"),
            "dew_point": record.get("dew_point"),
            "clouds": record.get("clouds"),
            "wind_speed": record.get("wind_speed"),
            "wind_gust": record.get("wind_gust"),
            "wind_bearing": record.get("wind_deg"),
            "weather": weather[0].get("description") if weather else None,
            "weather_code": weather[0].get("id") if weather else None,
            "uv_index": record.get("uvi"),
            "visibility_distance": record.get("visibility"),
            "rain": rain,
            "snow": snow,
            "precipitation_kind": precip_kind(rain, snow),
            "alerts": list(record.get("alerts") or []),
        }


class HourlyCoordinator(OWM4Coordinator[list[Forecast]]):
    """Hourly forecast (48 h = 3 calls)."""

    def __init__(self, hass, config_entry, client) -> None:
        """Initialise."""
        super().__init__(hass, config_entry, client, "hourly", HOURLY_INTERVAL)

    async def _async_update_data(self) -> list[Forecast]:
        records = await self._fetch(lambda: self.client.hourly(HOURLY_HOURS))
        return [self._forecast(r) for r in records if "dt" in r]

    def upcoming(self) -> list[Forecast] | None:
        """Hours from the one under way onwards (the poll is every 30 min,
        so the first stored hour may already be over)."""
        if self.data is None:
            return None
        cutoff = dt_util.utcnow() - timedelta(hours=1)
        return [
            f
            for f in self.data
            if (when := dt_util.parse_datetime(f["datetime"])) is None or when > cutoff
        ]

    def _forecast(self, r: dict) -> Forecast:
        rain = precip_value(r.get("rain"))
        snow = precip_value(r.get("snow"))
        return Forecast(
            datetime=iso(r["dt"]),
            condition=self.condition(r.get("weather"), r.get("dt")),
            native_temperature=r.get("temp"),
            native_apparent_temperature=r.get("feels_like"),
            native_pressure=r.get("pressure"),
            humidity=r.get("humidity"),
            native_dew_point=r.get("dew_point"),
            cloud_coverage=r.get("clouds"),
            native_wind_speed=r.get("wind_speed"),
            native_wind_gust_speed=r.get("wind_gust"),
            wind_bearing=r.get("wind_deg"),
            uv_index=_float(r.get("uvi")),
            precipitation_probability=_pop(r.get("pop")),
            native_precipitation=round(rain + snow, 2),
        )


class DailyCoordinator(OWM4Coordinator[list[Forecast]]):
    """Daily forecast (8 days = 1 call)."""

    def __init__(self, hass, config_entry, client) -> None:
        """Initialise."""
        super().__init__(hass, config_entry, client, "daily", DAILY_INTERVAL)

    async def _async_update_data(self) -> list[Forecast]:
        records = await self._fetch(lambda: self.client.daily(DAILY_DAYS))
        return [self._forecast(r) for r in records if "dt" in r]

    def _forecast(self, r: dict) -> Forecast:
        temp = r.get("temp") or {}
        feels = r.get("feels_like") or {}
        rain = precip_value(r.get("rain"))
        snow = precip_value(r.get("snow"))
        return Forecast(
            datetime=iso(r["dt"]),
            condition=self.condition(r.get("weather"), r.get("dt"), daily=True),
            native_temperature=temp.get("max"),
            native_templow=temp.get("min"),
            native_apparent_temperature=feels.get("day"),
            native_pressure=r.get("pressure"),
            humidity=r.get("humidity"),
            native_dew_point=r.get("dew_point"),
            cloud_coverage=r.get("clouds"),
            native_wind_speed=r.get("wind_speed"),
            native_wind_gust_speed=r.get("wind_gust"),
            wind_bearing=r.get("wind_deg"),
            uv_index=_float(r.get("uvi")),
            precipitation_probability=_pop(r.get("pop")),
            native_precipitation=round(rain + snow, 2),
        )


class MinuteCoordinator(OWM4Coordinator[dict[str, Any]]):
    """Minute-by-minute precipitation for the next hour."""

    def __init__(self, hass, config_entry, client) -> None:
        """Initialise."""
        super().__init__(hass, config_entry, client, "minute", MINUTE_INTERVAL)

    async def _async_update_data(self) -> dict[str, Any]:
        records = await self._fetch(self.client.minutely)
        forecast = [
            {
                "datetime": dt_util.utc_from_timestamp(r["dt"]),
                "precipitation": round(float(r.get("precipitation") or 0), 2),
            }
            for r in records
            if "dt" in r
        ]
        return {"forecast": forecast}

    def upcoming(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """Minutes from the one under way onwards (drops elapsed minutes)."""
        now = now or dt_util.utcnow()
        return [
            m
            for m in (self.data or {}).get("forecast", [])
            if m["datetime"] > now - timedelta(minutes=1)
        ]

    def summary(self, now: datetime | None = None) -> dict[str, Any]:
        """Work out the next-hour figures from the stored minute forecast.

        Recomputed on read so "minutes until" counts down between polls.
        """
        now = now or dt_util.utcnow()
        upcoming = self.upcoming(now)
        rates = [m["precipitation"] for m in upcoming]
        first_wet = next(
            (m for m in upcoming if m["precipitation"] >= RAIN_THRESHOLD), None
        )
        first_dry_after = None
        if first_wet is not None:
            first_dry_after = next(
                (
                    m
                    for m in upcoming
                    if m["datetime"] > first_wet["datetime"]
                    and m["precipitation"] < RAIN_THRESHOLD
                ),
                None,
            )
        minutes_until = None
        if first_wet is not None:
            minutes_until = max(
                0, int((first_wet["datetime"] - now).total_seconds() // 60)
            )
        return {
            "minutes_covered": len(upcoming),
            "expected": first_wet is not None,
            "minutes_until": minutes_until,
            "starts_at": first_wet["datetime"] if first_wet else None,
            "ends_at": first_dry_after["datetime"] if first_dry_after else None,
            "max_rate": round(max(rates), 2) if rates else None,
            # mm/h per minute → mm over the hour.
            "total": round(sum(rates) / 60, 2) if rates else None,
        }


def _float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _pop(value: Any) -> int | None:
    return round(float(value) * 100) if value is not None else None
