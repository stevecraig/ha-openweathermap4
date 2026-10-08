"""Sensors for OpenWeatherMap One Call 4.0."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UV_INDEX,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumetricFlux,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import OWM4ConfigEntry
from .const import ATTRIBUTION
from .coordinator import HourlyCoordinator, MinuteCoordinator, OWM4Coordinator
from .entity import device_info

# Same sensors as the core OpenWeatherMap integration (current conditions).
CURRENT_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(key="weather", translation_key="weather"),
    SensorEntityDescription(
        key="dew_point",
        translation_key="dew_point",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="feels_like_temperature",
        translation_key="feels_like_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="wind_speed",
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="wind_gust",
        translation_key="wind_gust",
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="wind_bearing",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT_ANGLE,
        device_class=SensorDeviceClass.WIND_DIRECTION,
    ),
    SensorEntityDescription(
        key="humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="pressure",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="clouds",
        translation_key="clouds",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="rain",
        translation_key="rain",
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="snow",
        translation_key="snow",
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="precipitation_kind", translation_key="precipitation_kind"
    ),
    SensorEntityDescription(
        key="uv_index",
        translation_key="uv_index",
        native_unit_of_measurement=UV_INDEX,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="visibility_distance",
        translation_key="visibility_distance",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(key="condition", translation_key="condition"),
    SensorEntityDescription(key="weather_code", translation_key="weather_code"),
)


@dataclass(frozen=True, kw_only=True)
class MinuteSensorDescription(SensorEntityDescription):
    """A sensor computed from the next-hour minute forecast summary."""

    value: Callable[[dict[str, Any]], StateType]
    attributes: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _rain_window(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "starts_at": summary["starts_at"],
        "ends_at": summary["ends_at"],
        "minutes_covered": summary["minutes_covered"],
    }


MINUTE_SENSORS: tuple[MinuteSensorDescription, ...] = (
    MinuteSensorDescription(
        key="minutes_until_precipitation",
        translation_key="minutes_until_precipitation",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        value=lambda s: s["minutes_until"],
        attributes=_rain_window,
    ),
    MinuteSensorDescription(
        key="next_hour_max_precipitation",
        translation_key="next_hour_max_precipitation",
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda s: s["max_rate"],
    ),
    MinuteSensorDescription(
        key="next_hour_precipitation",
        translation_key="next_hour_precipitation",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        suggested_display_precision=1,
        value=lambda s: s["total"],
    ),
)

HOURLY_POP = SensorEntityDescription(
    key="precipitation_probability",
    translation_key="precipitation_probability",
    native_unit_of_measurement=PERCENTAGE,
    state_class=SensorStateClass.MEASUREMENT,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OWM4ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the sensors."""
    data = entry.runtime_data
    entities: list[SensorEntity] = [
        CurrentSensor(entry, data.current, d) for d in CURRENT_SENSORS
    ]
    entities.append(PrecipitationProbabilitySensor(entry, data.hourly, HOURLY_POP))
    entities.extend(MinuteSensor(entry, data.minute, d) for d in MINUTE_SENSORS)
    async_add_entities(entities)


class OWM4Sensor[C: OWM4Coordinator](CoordinatorEntity[C], SensorEntity):
    """Base sensor tied to one coordinator."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: OWM4ConfigEntry,
        coordinator: C,
        description: SensorEntityDescription,
    ) -> None:
        """Initialise."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}-{description.key}"
        self._attr_device_info = device_info(entry)


class CurrentSensor(OWM4Sensor):
    """A current-conditions value."""

    @property
    def native_value(self) -> StateType:
        """Value from the current conditions."""
        return (self.coordinator.data or {}).get(self.entity_description.key)


class PrecipitationProbabilitySensor(OWM4Sensor[HourlyCoordinator]):
    """Chance of precipitation in the current hour."""

    @property
    def native_value(self) -> StateType:
        """The first hourly record's probability (%)."""
        forecast = self.coordinator.upcoming() or []
        return forecast[0].get("precipitation_probability") if forecast else None


class MinuteSensor(OWM4Sensor[MinuteCoordinator]):
    """A next-hour figure from the minute forecast; refreshed every minute."""

    entity_description: MinuteSensorDescription

    async def async_added_to_hass(self) -> None:
        """Re-evaluate every minute so countdowns stay current between polls."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(self.hass, self._tick, timedelta(minutes=1))
        )

    @callback
    def _tick(self, _now: datetime) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> StateType:
        """Computed from the minute summary."""
        return self.entity_description.value(self.coordinator.summary())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Optional attributes (rain start/end)."""
        if self.entity_description.attributes is None:
            return None
        return self.entity_description.attributes(self.coordinator.summary())
