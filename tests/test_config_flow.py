"""Config, reauth and options flows."""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.openweathermap4.config_flow import owm_language
from custom_components.openweathermap4.const import DOMAIN

from .conftest import LAT, LON, mock_api

USER_INPUT = {
    "name": "Sea",
    "location": {"latitude": LAT, "longitude": LON},
    "api_key": "new-key",
    "language": "en",
}


async def test_user_flow_creates_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A good key creates the entry; the location is flattened into data."""
    mock_api(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Sea"
    assert result["data"] == {"api_key": "new-key", "latitude": LAT, "longitude": LON}
    assert result["options"] == {"language": "en"}
    assert result["result"].unique_id == f"{LAT}-{LON}"


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, "invalid_api_key"), (429, "rate_limited"), (500, "cannot_connect")],
)
async def test_user_flow_errors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status, error
) -> None:
    """Errors are shown on the form, and the user can retry."""
    mock_api(aioclient_mock, status=status)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_api(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_location_aborts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    """The same coordinates can only be added once."""
    config_entry.add_to_hass(hass)
    mock_api(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    """Reauth stores the new key."""
    mock_api(aioclient_mock)
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "fresh-key"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data["api_key"] == "fresh-key"


async def test_options_flow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry
) -> None:
    """Language and rain thresholds can be changed afterwards."""
    mock_api(aioclient_mock)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"language": "de", "rain_probability": 60, "rain_amount": 0.5},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {
        "language": "de",
        "rain_probability": 60,
        "rain_amount": 0.5,
    }


@pytest.mark.parametrize(
    ("ha", "owm"),
    [
        ("en-GB", "en"),
        ("en", "en"),
        ("pt-BR", "pt_br"),
        ("de-CH", "de"),
        ("cs", "cz"),
        ("ko", "kr"),
        ("sq", "al"),
        ("nb", "no"),
        ("zh-Hans", "zh_cn"),
        ("zh-Hant", "zh_tw"),
        ("xx", "en"),
        (None, "en"),
    ],
)
def test_language_mapping(ha, owm) -> None:
    """HA's regional language codes map to ones OpenWeatherMap accepts."""
    assert owm_language(ha) == owm
