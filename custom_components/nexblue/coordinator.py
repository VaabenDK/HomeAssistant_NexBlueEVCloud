from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant
from datetime import timedelta
import logging
from .const import DOMAIN, DEFAULT_SCAN_INTERVAL
from .api import NexblueAPI

_LOGGER = logging.getLogger(__name__)

class NexblueDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, config_entry):
        self.hass = hass
        self.config_entry = config_entry
        self.api = NexblueAPI(
            config_entry.data["email"],
            config_entry.data["password"]
        )

        update_interval = timedelta(seconds=config_entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL))

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval
        )

    async def _async_update_data(self):
        try:
            data = await self.api.get_charger_data()
            return data
        except Exception as e:
            raise UpdateFailed(f"Error fetching data: {e}")