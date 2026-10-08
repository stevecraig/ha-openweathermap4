"""Config flow for OpenWeatherMap One Call 4.0."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LANGUAGE,
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    LanguageSelector,
    LanguageSelectorConfig,
    LocationSelector,
    LocationSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import OneCall4Client, OWMAuthError, OWMError, OWMRateLimitError
from .const import (
    CONF_RAIN_AMOUNT,
    CONF_RAIN_PROBABILITY,
    DEFAULT_LANGUAGE,
    DEFAULT_NAME,
    DEFAULT_RAIN_AMOUNT,
    DEFAULT_RAIN_PROBABILITY,
    DOMAIN,
    LANGUAGES,
)

# Use whichever schema library this Home Assistant's flow manager uses:
# probatio from 2026.11, voluptuous before that.
try:
    from homeassistant.data_entry_flow import probatio as vol
except ImportError:  # pragma: no cover - depends on the HA version
    from homeassistant.data_entry_flow import vol

API_KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
LANGUAGE_SELECTOR = LanguageSelector(
    LanguageSelectorConfig(languages=LANGUAGES, native_name=True)
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Required(CONF_LOCATION): LocationSelector(
            LocationSelectorConfig(radius=False)
        ),
        vol.Required(CONF_API_KEY): API_KEY_SELECTOR,
        vol.Optional(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): LANGUAGE_SELECTOR,
    }
)
REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): API_KEY_SELECTOR})
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): LANGUAGE_SELECTOR,
        vol.Optional(
            CONF_RAIN_PROBABILITY, default=DEFAULT_RAIN_PROBABILITY
        ): NumberSelector(
            NumberSelectorConfig(
                min=5,
                max=100,
                step=5,
                unit_of_measurement="%",
                mode=NumberSelectorMode.SLIDER,
            )
        ),
        vol.Optional(CONF_RAIN_AMOUNT, default=DEFAULT_RAIN_AMOUNT): NumberSelector(
            NumberSelectorConfig(
                min=0.1,
                max=5,
                step=0.1,
                unit_of_measurement="mm",
                mode=NumberSelectorMode.BOX,
            )
        ),
    }
)


# HA (BCP 47) codes that OpenWeatherMap spells differently.
OWM_LANGUAGE_ALIASES = {
    "cs": "cz",
    "ko": "kr",
    "sq": "al",
    "nb": "no",
    "nn": "no",
    "zh": "zh_cn",
    "zh_hans": "zh_cn",
    "zh_hant": "zh_tw",
}


def owm_language(language: str | None) -> str:
    """Map HA's language (e.g. en-GB, pt-BR) to one OpenWeatherMap accepts."""
    if not language:
        return DEFAULT_LANGUAGE
    code = language.lower().replace("-", "_")
    for candidate in (code, code.split("_")[0]):
        candidate = OWM_LANGUAGE_ALIASES.get(candidate, candidate)
        if candidate in LANGUAGES:
            return candidate
    return DEFAULT_LANGUAGE


async def validate_key(
    hass: HomeAssistant, api_key: str, latitude: float, longitude: float
) -> tuple[dict[str, str], dict[str, str]]:
    """Make one call; return (errors, description placeholders)."""
    client = OneCall4Client(async_get_clientsession(hass), api_key, latitude, longitude)
    try:
        await client.validate()
    except OWMAuthError:
        return {"base": "invalid_api_key"}, {}
    except OWMRateLimitError:
        return {"base": "rate_limited"}, {}
    except OWMError as err:
        return {"base": "cannot_connect"}, {"error": str(err)}
    return {}, {}


class OWM4ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a location with an API key."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OWM4OptionsFlow:
        """Options: language and rain thresholds."""
        return OWM4OptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The setup form."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            latitude = user_input[CONF_LOCATION][CONF_LATITUDE]
            longitude = user_input[CONF_LOCATION][CONF_LONGITUDE]
            await self.async_set_unique_id(f"{latitude}-{longitude}")
            self._abort_if_unique_id_configured()
            errors, placeholders = await validate_key(
                self.hass, user_input[CONF_API_KEY], latitude, longitude
            )
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_LATITUDE: latitude,
                        CONF_LONGITUDE: longitude,
                    },
                    options={CONF_LANGUAGE: user_input[CONF_LANGUAGE]},
                )
            suggested = user_input
        else:
            suggested = {
                CONF_LOCATION: {
                    CONF_LATITUDE: self.hass.config.latitude,
                    CONF_LONGITUDE: self.hass.config.longitude,
                },
                CONF_LANGUAGE: owm_language(self.hass.config.language),
            }
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, suggested),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """The key stopped working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new key."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            errors, placeholders = await validate_key(
                self.hass,
                user_input[CONF_API_KEY],
                entry.data[CONF_LATITUDE],
                entry.data[CONF_LONGITUDE],
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: user_input[CONF_API_KEY]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
            description_placeholders=placeholders,
        )


class OWM4OptionsFlow(OptionsFlowWithReload):
    """Change the language and what counts as a wet hour."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The options form."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
