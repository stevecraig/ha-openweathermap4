"""Constants for OpenWeatherMap One Call 4.0."""

from datetime import timedelta

from homeassistant.components.weather import (
    ATTR_CONDITION_CLOUDY,
    ATTR_CONDITION_EXCEPTIONAL,
    ATTR_CONDITION_FOG,
    ATTR_CONDITION_HAIL,
    ATTR_CONDITION_LIGHTNING,
    ATTR_CONDITION_LIGHTNING_RAINY,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_POURING,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SNOWY_RAINY,
    ATTR_CONDITION_SUNNY,
    ATTR_CONDITION_WINDY,
    ATTR_CONDITION_WINDY_VARIANT,
)
from homeassistant.const import Platform

DOMAIN = "openweathermap4"
DEFAULT_NAME = "OpenWeatherMap 4.0"
DEFAULT_LANGUAGE = "en"
ATTRIBUTION = "Data provided by OpenWeatherMap"
MANUFACTURER = "OpenWeather"

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.WEATHER]

# Polling. Each request is one billed call; One Call by Call is free up to
# 1,000 calls/day. Defaults below come to roughly 590 calls/day:
#   minute rain   every 5 min   1 call       288/day
#   current       every 10 min  1 call       144/day
#   hourly (48 h) every 30 min  3 calls      144/day
#   daily (8 d)   every 3 h     1 call         8/day
MINUTE_INTERVAL = timedelta(minutes=5)
CURRENT_INTERVAL = timedelta(minutes=10)
HOURLY_INTERVAL = timedelta(minutes=30)
DAILY_INTERVAL = timedelta(hours=3)
HOURLY_HOURS = 48
DAILY_DAYS = 8

# Minute rain at or above this rate (mm/h) counts as "rain" for the
# minutes-until / binary sensors. Below it is drizzle noise.
RAIN_THRESHOLD = 0.1

# Options: an hour of the hourly forecast counts as wet for "next rain" when
# either its chance of rain or its amount reaches these.
CONF_RAIN_PROBABILITY = "rain_probability"
CONF_RAIN_AMOUNT = "rain_amount"
DEFAULT_RAIN_PROBABILITY = 40  # %
DEFAULT_RAIN_AMOUNT = 0.2  # mm in the hour

LANGUAGES = [
    "af", "al", "ar", "az", "bg", "ca", "cz", "da", "de", "el", "en", "es",
    "eu", "fa", "fi", "fr", "gl", "he", "hi", "hr", "hu", "id", "it", "ja",
    "kr", "la", "lt", "mk", "nl", "no", "pl", "pt", "pt_br", "ro", "ru", "se",
    "sk", "sl", "sp", "sr", "sv", "th", "tr", "ua", "uk", "vi", "zh_cn",
    "zh_tw", "zu",
]  # fmt: skip

WEATHER_CODE_SUNNY_OR_CLEAR_NIGHT = 800
CONDITION_CLASSES = {
    ATTR_CONDITION_CLOUDY: [803, 804],
    ATTR_CONDITION_FOG: [701, 721, 741],
    ATTR_CONDITION_HAIL: [906],
    ATTR_CONDITION_LIGHTNING: [210, 211, 212, 221],
    ATTR_CONDITION_LIGHTNING_RAINY: [200, 201, 202, 230, 231, 232],
    ATTR_CONDITION_PARTLYCLOUDY: [801, 802],
    ATTR_CONDITION_POURING: [504, 314, 502, 503, 522],
    ATTR_CONDITION_RAINY: [300, 301, 302, 310, 311, 312, 313, 500, 501, 520, 521],
    ATTR_CONDITION_SNOWY: [600, 601, 602, 611, 612, 620, 621, 622],
    ATTR_CONDITION_SNOWY_RAINY: [511, 615, 616],
    ATTR_CONDITION_SUNNY: [WEATHER_CODE_SUNNY_OR_CLEAR_NIGHT],
    ATTR_CONDITION_WINDY: [905, 951, 952, 953, 954, 955, 956, 957],
    ATTR_CONDITION_WINDY_VARIANT: [958, 959, 960, 961],
    ATTR_CONDITION_EXCEPTIONAL: [
        711, 731, 751, 761, 762, 771, 900, 901, 962, 903, 904,
    ],
}  # fmt: skip
CONDITION_MAP = {
    code: condition for condition, codes in CONDITION_CLASSES.items() for code in codes
}
