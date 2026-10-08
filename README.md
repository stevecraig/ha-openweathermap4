# OpenWeatherMap 4.0 for Home Assistant

A custom integration for the [OpenWeatherMap One Call API 4.0](https://openweathermap.org/api/one-call-4).

Home Assistant's built-in OpenWeatherMap integration uses One Call API 3.0. OpenWeatherMap no longer accepts new 3.0
subscriptions, so new accounts can only get 4.0. This integration gives you the same entities as the built-in one on
4.0, plus sensors for rain in the next hour that you can use in automations.

## What you get

One device per location, with:

- **Weather entity** with current conditions, a 48-hour hourly forecast and an 8-day daily forecast. It works with
  weather cards and `weather.get_forecasts`.
- **Current-condition sensors**, the same as the built-in integration: temperature, apparent temperature, dew point,
  humidity, pressure, wind speed, gust and direction, cloud coverage, UV index, visibility, rain and snow intensity,
  precipitation kind, condition, weather description and weather code.
- **Precipitation probability**: the chance of rain or snow in the current hour (%).
- **Rain in the next hour**, from the minute-by-minute forecast:
  - `binary_sensor.<name>_precipitation_next_hour` is on when rain or snow (≥ 0.1 mm/h) is expected within the hour.
    Its attributes are `starts_at`, `ends_at`, `minutes_until` and `max_rate`.
  - `sensor.<name>_minutes_until_precipitation` counts down every minute. It is unknown when the hour is dry.
  - `sensor.<name>_next_hour_max_precipitation_intensity` (mm/h) and `sensor.<name>_next_hour_precipitation` (mm).
- **When the rain starts**, from the hourly forecast, sharpened to the minute by the minute forecast within the next
  hour:
  - `sensor.<name>_next_rain`: the time the next rain starts, within the 48-hour forecast (unknown if none). Its
    attributes say whether the time came from the `minute` or `hourly` forecast, plus that hour's chance and amount.
  - `sensor.<name>_dry_hours_left_today`: hours from now until the rain or midnight, whichever comes first.
  - `binary_sensor.<name>_rain_later_today`: on when rain starts before midnight.

  An hour counts as wet when its chance of rain is at least 40 % or at least 0.2 mm is forecast. You can change both
  from the integration's **Configure** button.
- **Action `openweathermap4.get_minute_forecast`**, which returns the minute forecast in the same shape as the
  built-in `openweathermap.get_minute_forecast`. It is answered from the last poll, so calling it uses no API calls.

## API calls and cost

OpenWeatherMap bills One Call 4.0 per call, and the first **1,000 calls a day are free**. Every request counts,
including each page of a forecast. This integration makes about **590 calls a day** per location:

| Data | How often | Calls |
|---|---|---|
| Minute rain (next hour) | every 5 min | 288/day |
| Current conditions | every 10 min | 144/day |
| Hourly forecast (48 h, 3 pages) | every 30 min | 144/day |
| Daily forecast (8 days) | every 3 h, and only while something shows it | ≤ 8/day |

Under **Billing plans** on your OpenWeatherMap account, set the daily call limit to **1,000** so you can never be
charged. With two locations you would go over the free 1,000.

## Install

1. In OpenWeatherMap, subscribe to **One Call API 4.0** ("One Call by Call") and set the daily limit to 1,000. A new
   subscription can take a while to activate.
2. In HACS, open ⋮ → **Custom repositories**, add `https://github.com/stevecraig/ha-openweathermap4` with type
   **Integration**, then download **OpenWeatherMap 4.0** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → OpenWeatherMap 4.0**. Enter a name, the location
   (your home by default) and your API key. The key is stored by Home Assistant like any other integration's.

If OpenWeatherMap later rejects the key, Home Assistant shows a **Reconfigure** prompt asking for a new one. You can
change the language and the rain thresholds later from the integration's **Configure** button.

## Examples

Tell someone before the rain arrives:

```yaml
triggers:
  - trigger: numeric_state
    entity_id: sensor.home_minutes_until_precipitation
    below: 15
actions:
  - action: notify.mobile_app_phone
    data:
      message: >
        Rain in about {{ states('sensor.home_minutes_until_precipitation') }} minutes
        (up to {{ state_attr('binary_sensor.home_precipitation_next_hour', 'max_rate') }} mm/h).
```

Is there time to dry the washing outside?

```yaml
triggers:
  - trigger: time
    at: "08:00:00"
conditions:
  - condition: numeric_state
    entity_id: sensor.home_dry_hours_left_today
    above: 5
actions:
  - action: notify.mobile_app_phone
    data:
      message: >
        Good drying day: dry for {{ states('sensor.home_dry_hours_left_today') }} hours.
```

Read the minute forecast in a template or script:

```yaml
- action: openweathermap4.get_minute_forecast
  target:
    entity_id: weather.home
  response_variable: minutes
- variables:
    wet_minutes: >
      {{ minutes['weather.home'].forecast | selectattr('precipitation', '>', 0) | list | count }}
```

## Development

```bash
python -m venv venv
venv/bin/pip install -r requirements_test.txt
venv/bin/pytest
```

The tests use canned API responses, so they need no API key. CI also runs Home Assistant's `hassfest` and the HACS
validation.

Not affiliated with OpenWeather. Weather data © OpenWeather.
