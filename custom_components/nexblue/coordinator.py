from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NexblueAPI, NexblueAPIError, NexblueChargerData
from .const import (
    CONF_ACCOUNT_TYPE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_ACCOUNT_TYPE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class NexblueDataUpdateCoordinator(DataUpdateCoordinator[dict[str, NexblueChargerData]]):
    """Coordinator to poll Nexblue for charger data."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self.hass = hass
        self.config_entry = config_entry

        email = config_entry.data[CONF_EMAIL]
        password = config_entry.data[CONF_PASSWORD]
        account_type = config_entry.data.get(CONF_ACCOUNT_TYPE, DEFAULT_ACCOUNT_TYPE)

        self.api = NexblueAPI(hass, email, password, account_type)

        update_interval = timedelta(
            seconds=config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, NexblueChargerData]:
        try:
            return await self.api.get_chargers()
        except NexblueAPIError as err:
            raise UpdateFailed(f"Error fetching Nexblue data: {err}") from err