"""Config flow for TrikHub integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .client import TrikHubClient, TrikHubClientError, TrikHubConnectionError
from .const import (
    CONF_AUTH_TOKEN,
    CONF_LLM_API_KEY,
    CONF_LLM_MODEL,
    CONF_LLM_PROVIDER,
    CONF_SERVER_URL,
    DEFAULT_LLM_MODEL,
    DEFAULT_SERVER_URL,
    DOMAIN,
    LLM_PROVIDER_ANTHROPIC,
    LLM_PROVIDER_OLLAMA,
    LLM_PROVIDER_OPENAI,
    LLM_PROVIDERS,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SERVER_URL, default=DEFAULT_SERVER_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        vol.Optional(CONF_AUTH_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)

STEP_LLM_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LLM_PROVIDER, default=LLM_PROVIDER_OPENAI): SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"value": LLM_PROVIDER_OPENAI, "label": "OpenAI"},
                    {"value": LLM_PROVIDER_ANTHROPIC, "label": "Anthropic"},
                    {"value": LLM_PROVIDER_OLLAMA, "label": "Ollama (Local)"},
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(CONF_LLM_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_LLM_MODEL, default=DEFAULT_LLM_MODEL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
    }
)


class TrikHubConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TrikHub."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._server_url: str | None = None
        self._auth_token: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - server configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._server_url = user_input[CONF_SERVER_URL]
            self._auth_token = user_input.get(CONF_AUTH_TOKEN)

            # Validate connection to TrikHub server
            client = TrikHubClient(self._server_url, self._auth_token)
            try:
                await client.health_check()
                # Connection successful, proceed to LLM configuration
                return await self.async_step_llm()
            except TrikHubConnectionError:
                errors["base"] = "cannot_connect"
            except TrikHubClientError as err:
                _LOGGER.error("TrikHub server error: %s", err)
                errors["base"] = "unknown"
            finally:
                await client.close()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "default_url": DEFAULT_SERVER_URL,
            },
        )

    async def async_step_llm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the LLM configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            llm_provider = user_input[CONF_LLM_PROVIDER]
            llm_api_key = user_input[CONF_LLM_API_KEY]
            llm_model = user_input[CONF_LLM_MODEL]

            # For Ollama, API key might be empty or a URL
            if llm_provider != LLM_PROVIDER_OLLAMA and not llm_api_key:
                errors[CONF_LLM_API_KEY] = "api_key_required"
            else:
                # Create the config entry
                await self.async_set_unique_id(f"trikhub_{self._server_url}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="TrikHub",
                    data={
                        CONF_SERVER_URL: self._server_url,
                        CONF_AUTH_TOKEN: self._auth_token,
                        CONF_LLM_PROVIDER: llm_provider,
                        CONF_LLM_API_KEY: llm_api_key,
                        CONF_LLM_MODEL: llm_model,
                    },
                )

        # Adjust schema based on provider
        return self.async_show_form(
            step_id="llm",
            data_schema=STEP_LLM_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return TrikHubOptionsFlowHandler(config_entry)


class TrikHubOptionsFlowHandler:
    """Handle options flow for TrikHub."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LLM_MODEL,
                        default=self.config_entry.data.get(
                            CONF_LLM_MODEL, DEFAULT_LLM_MODEL
                        ),
                    ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
                }
            ),
        )
