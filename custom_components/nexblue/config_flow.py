from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .api import NexblueAPI, NexblueAPIError, NexblueAuthError
from .const import (
    ACCOUNT_TYPE_INSTALLER,
    CONF_ACCOUNT_TYPE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_ACCOUNT_TYPE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

ACCOUNT_TYPE_OPTIONS = {
    DEFAULT_ACCOUNT_TYPE: "End user",
    ACCOUNT_TYPE_INSTALLER: "Installer",
}


class NexblueConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Nexblue."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        user_input = user_input or {}

        if user_input:
            result = await self._async_validate_input(user_input)
            if not isinstance(result, dict):
                errors["base"] = result
            else:
                await self.async_set_unique_id(result[CONF_EMAIL].lower())
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=result[CONF_EMAIL],
                    data={
                        CONF_EMAIL: result[CONF_EMAIL],
                        CONF_PASSWORD: result[CONF_PASSWORD],
                        CONF_ACCOUNT_TYPE: result[CONF_ACCOUNT_TYPE],
                    },
                    options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL, default=user_input.get(CONF_EMAIL, "")): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(
                    CONF_ACCOUNT_TYPE,
                    default=user_input.get(CONF_ACCOUNT_TYPE, DEFAULT_ACCOUNT_TYPE),
                ): vol.In(list(ACCOUNT_TYPE_OPTIONS)),
            }
        )

        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        user_input = user_input or {}

        assert self._reauth_entry is not None

        if user_input:
            result = await self._async_validate_input(user_input)
            if isinstance(result, dict):
                data = {
                    CONF_EMAIL: result[CONF_EMAIL],
                    CONF_PASSWORD: result[CONF_PASSWORD],
                    CONF_ACCOUNT_TYPE: result[CONF_ACCOUNT_TYPE],
                }
                self.hass.config_entries.async_update_entry(self._reauth_entry, data=data)
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_create_entry(title="", data={})

            errors["base"] = result

        data_schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL, default=self._reauth_entry.data[CONF_EMAIL]): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(
                    CONF_ACCOUNT_TYPE,
                    default=self._reauth_entry.data.get(CONF_ACCOUNT_TYPE, DEFAULT_ACCOUNT_TYPE),
                ): vol.In(list(ACCOUNT_TYPE_OPTIONS)),
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=data_schema,
            errors=errors,
        )

    async def _async_validate_input(self, user_input: dict[str, Any]) -> dict[str, Any] | str:
        email = user_input[CONF_EMAIL]
        password = user_input[CONF_PASSWORD]
        account_type = user_input.get(CONF_ACCOUNT_TYPE, DEFAULT_ACCOUNT_TYPE)

        api = NexblueAPI(self.hass, email, password, account_type)
        try:
            await api.get_chargers()
        except NexblueAuthError:
            return "invalid_auth"
        except NexblueAPIError:
            return "cannot_connect"

        return {
            CONF_EMAIL: email,
            CONF_PASSWORD: password,
            CONF_ACCOUNT_TYPE: account_type,
        }

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return NexblueOptionsFlowHandler(config_entry)


class NexblueOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Nexblue options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input:
            return self.async_create_entry(
                title="",
                data={CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL]},
            )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(int, vol.Range(min=30, max=600)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema, errors=errors)
