"""TrikHub integration for Home Assistant."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .client import TrikHubClient, TrikHubClientError
from .const import (
    ATTR_INPUT,
    ATTR_NAME,
    ATTR_PACKAGE,
    ATTR_TOOL,
    CONF_AUTH_TOKEN,
    CONF_LLM_API_KEY,
    CONF_LLM_MODEL,
    CONF_LLM_PROVIDER,
    CONF_SERVER_URL,
    DOMAIN,
    SERVICE_EXECUTE_TRIK,
    SERVICE_INSTALL_TRIK,
    SERVICE_UNINSTALL_TRIK,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CONVERSATION]

SERVICE_EXECUTE_TRIK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TOOL): cv.string,
        vol.Optional(ATTR_INPUT, default={}): dict,
    }
)

SERVICE_INSTALL_TRIK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PACKAGE): cv.string,
    }
)

SERVICE_UNINSTALL_TRIK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_NAME): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TrikHub from a config entry."""
    server_url = entry.data[CONF_SERVER_URL]
    auth_token = entry.data.get(CONF_AUTH_TOKEN)

    # Create the client
    client = TrikHubClient(server_url, auth_token)

    # Verify connection
    try:
        await client.health_check()
    except TrikHubClientError as err:
        _LOGGER.error("Failed to connect to TrikHub server: %s", err)
        await client.close()
        return False

    # Store client and config in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "config": {
            CONF_SERVER_URL: server_url,
            CONF_AUTH_TOKEN: auth_token,
            CONF_LLM_PROVIDER: entry.data.get(CONF_LLM_PROVIDER),
            CONF_LLM_API_KEY: entry.data.get(CONF_LLM_API_KEY),
            CONF_LLM_MODEL: entry.data.get(CONF_LLM_MODEL),
        },
    }

    # Register services
    await _async_register_services(hass, client)

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        client: TrikHubClient = data["client"]
        await client.close()

    return unload_ok


async def _async_register_services(hass: HomeAssistant, client: TrikHubClient) -> None:
    """Register TrikHub services."""

    async def handle_execute_trik(call: ServiceCall) -> dict[str, Any]:
        """Handle the execute_trik service call."""
        tool = call.data[ATTR_TOOL]
        input_data = call.data.get(ATTR_INPUT, {})

        _LOGGER.debug("Executing trik tool: %s with input: %s", tool, input_data)

        try:
            result = await client.execute(tool, input_data)
            _LOGGER.debug("Trik execution result: %s", result)
            return result
        except TrikHubClientError as err:
            _LOGGER.error("Failed to execute trik: %s", err)
            raise

    async def handle_install_trik(call: ServiceCall) -> dict[str, Any]:
        """Handle the install_trik service call."""
        package = call.data[ATTR_PACKAGE]

        _LOGGER.info("Installing trik: %s", package)

        try:
            result = await client.install_trik(package)
            _LOGGER.info("Trik installed: %s", result)
            return result
        except TrikHubClientError as err:
            _LOGGER.error("Failed to install trik: %s", err)
            raise

    async def handle_uninstall_trik(call: ServiceCall) -> dict[str, Any]:
        """Handle the uninstall_trik service call."""
        name = call.data[ATTR_NAME]

        _LOGGER.info("Uninstalling trik: %s", name)

        try:
            result = await client.uninstall_trik(name)
            _LOGGER.info("Trik uninstalled: %s", result)
            return result
        except TrikHubClientError as err:
            _LOGGER.error("Failed to uninstall trik: %s", err)
            raise

    # Only register if not already registered
    if not hass.services.has_service(DOMAIN, SERVICE_EXECUTE_TRIK):
        hass.services.async_register(
            DOMAIN,
            SERVICE_EXECUTE_TRIK,
            handle_execute_trik,
            schema=SERVICE_EXECUTE_TRIK_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_INSTALL_TRIK):
        hass.services.async_register(
            DOMAIN,
            SERVICE_INSTALL_TRIK,
            handle_install_trik,
            schema=SERVICE_INSTALL_TRIK_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_UNINSTALL_TRIK):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UNINSTALL_TRIK,
            handle_uninstall_trik,
            schema=SERVICE_UNINSTALL_TRIK_SCHEMA,
        )
