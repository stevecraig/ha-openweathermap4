"""When does the rain start? Combines the hourly and minute forecasts."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.weather import Forecast
from homeassistant.util import dt as dt_util

HOUR = timedelta(hours=1)


def is_wet(hour: Forecast, min_probability: int, min_precipitation: float) -> bool:
    """An hour counts as wet when rain is likely enough or heavy enough."""
    pop = hour.get("precipitation_probability")
    amount = hour.get("native_precipitation")
    return (pop is not None and pop >= min_probability) or (
        amount is not None and amount >= min_precipitation
    )


def rain_outlook(
    hours: list[Forecast] | None,
    minutes: dict[str, Any] | None,
    now: datetime,
    *,
    min_probability: int,
    min_precipitation: float,
) -> dict[str, Any] | None:
    """Next rain, dry time left today, and whether it rains later today.

    The minute forecast is exact but only covers the next hour, so it wins
    within that hour; beyond it the first wet hour of the hourly forecast is
    used. ``minutes`` is MinuteCoordinator.summary() (or None without data).
    Returns None when there is no hourly forecast.
    """
    if hours is None:
        return None
    end_of_today = dt_util.start_of_local_day(dt_util.as_local(now) + timedelta(days=1))

    next_rain: datetime | None = None
    source: str | None = None
    hour: Forecast | None = None
    # Minute data covers [now, dry_until); within it trust only the minutes.
    dry_until = now
    if minutes and minutes.get("minutes_covered"):
        if minutes["expected"]:
            next_rain, source = minutes["starts_at"], "minute"
        else:
            dry_until = now + timedelta(minutes=minutes["minutes_covered"])

    if next_rain is None:
        for h in hours:
            start = dt_util.parse_datetime(h["datetime"])
            if start is None or start + HOUR <= dry_until:
                continue
            if is_wet(h, min_probability, min_precipitation):
                next_rain, source, hour = max(start, dry_until), "hourly", h
                break

    dry_end = min(next_rain or end_of_today, end_of_today)
    return {
        "next_rain": next_rain,
        "source": source,
        "probability": hour.get("precipitation_probability") if hour else None,
        "precipitation": hour.get("native_precipitation") if hour else None,
        "rain_today": next_rain is not None and next_rain < end_of_today,
        "dry_hours_today": round(max(0.0, (dry_end - now).total_seconds()) / 3600, 1),
        "end_of_today": end_of_today,
    }
