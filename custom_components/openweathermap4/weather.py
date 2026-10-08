"""Weather entity for OpenWeatherMap One Call 4.0."""

from __future__ import annotations

from typing import Any

from homeassistant.components.weather import (
    CoordinatorWeatherEntity,
    Forecast,
    WeatherEntityFeature,
)
from homeassistant.const import (
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OWM4ConfigEntry
from .const import ATTRIBUTION
from .coordinator import (
    CurrentCoordinator,
    DailyCoordinator,
    HourlyCoordinator,
    MinuteCoordinator,
)
from .entity import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OWM4ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the weather entity."""
    async_add_entities([OWM4Weather(entry)])


class OWM4Weather(
    CoordinatorWeatherEntity[
        CurrentCoordinator, DailyCoordinator, HourlyCoordinator, DailyCoordinator
    ]
):
    """Current conditions plus hourly and daily forecasts."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_visibility_unit = UnitOfLength.METERS

    def __init__(self, entry: OWM4ConfigEntry) -> None:
        """Initialise."""
        data = entry.runtime_data
        super().__init__(
            data.current,
            daily_coordinator=data.daily,
            hourly_coordinator=data.hourly,
        )
        self._minute: MinuteCoordinator = data.minute
        self._attr_unique_id = entry.unique_id
        self._attr_device_info = device_info(entry)

    def _current(self, key: str) -> Any:
        return (self.coordinator.data or {}).get(key)

    @property
    def condition(self) -> str | None:
        """Current condition."""
        return self._current("condition")

    @property
    def native_temperature(self) -> float | None:
        """Temperature."""
        return self._current("temperature")

    @property
    def native_apparent_temperature(self) -> float | None:
        """Feels-like temperature."""
        return self._current("feels_like_temperature")

    @property
    def native_pressure(self) -> float | None:
        """Pressure."""
        return self._current("pressure")

    @property
    def humidity(self) -> float | None:
        """Humidity."""
        return self._current("humidity")

    @property
    def native_dew_point(self) -> float | None:
        """Dew point."""
        return self._current("dew_point")

    @property
    def cloud_coverage(self) -> float | None:
        """Cloud cover."""
        return self._current("clouds")

    @property
    def native_wind_speed(self) -> float | None:
        """Wind speed."""
        return self._current("wind_speed")

    @property
    def native_wind_gust_speed(self) -> float | None:
        """Wind gust."""
        return self._current("wind_gust")

    @property
    def wind_bearing(self) -> float | str | None:
        """Wind bearing."""
        return self._current("wind_bearing")

    @property
    def uv_index(self) -> float | None:
        """UV index."""
        return self._current("uv_index")

    @property
    def native_visibility(self) -> float | None:
        """Visibility."""
        return self._current("visibility_distance")

    @callback
    def _async_forecast_hourly(self) -> list[Forecast] | None:
        return self.forecast_coordinators["hourly"].upcoming()

    @callback
    def _async_forecast_daily(self) -> list[Forecast] | None:
        return self.forecast_coordinators["daily"].data

    async def async_get_minute_forecast(self) -> dict[str, Any]:
        """Return the minute-by-minute precipitation forecast (next hour).

        Same shape as the core OpenWeatherMap action:
        {"forecast": [{"datetime": ..., "precipitation": mm/h}, ...]}.
        Served from the last poll (every 5 minutes), so calling it costs no
        API calls; minutes already gone are left out.
        """
        return {"forecast": self._minute.upcoming()}
