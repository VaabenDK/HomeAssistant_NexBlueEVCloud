from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    switches = []

    for charger in coordinator.data:
        switches.append(NexblueChargerSwitch(coordinator, charger["id"]))
    async_add_entities(switches)

class NexblueChargerSwitch(SwitchEntity):
    def __init__(self, coordinator, charger_id):
        self._coordinator = coordinator
        self._attr_name = f"Nexblue Charger {charger_id}"
        self._state = False

    @property
    def is_on(self):
        return self._state

    async def async_turn_on(self):
        self._state = True
        _LOGGER.debug("Starting charge session (simulated)")

    async def async_turn_off(self):
        self._state = False
        _LOGGER.debug("Stopping charge session (simulated)")