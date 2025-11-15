from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    sensors = []

    for charger in coordinator.data:
        sensors.append(NexblueSensor(coordinator, charger["id"], "Power", charger.get("power", 0), "power", "W"))
    async_add_entities(sensors)

class NexblueSensor(SensorEntity):
    def __init__(self, coordinator, charger_id, name, value, device_class, unit):
        self._coordinator = coordinator
        self._attr_name = f"Nexblue {name}"
        self._attr_native_value = value
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit

    @property
    def should_poll(self):
        return False

    async def async_update(self):
        await self._coordinator.async_request_refresh()