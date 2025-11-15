from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry):
    from .coordinator import NexblueDataUpdateCoordinator
    coordinator = NexblueDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    hass.async_create_task(hass.config_entries.async_forward_entry_setup(entry, "sensor"))
    hass.async_create_task(hass.config_entries.async_forward_entry_setup(entry, "switch"))
    return True

async def async_unload_entry(hass, entry):
    unload_ok = all(await asyncio.gather(
        hass.config_entries.async_forward_entry_unload(entry, "sensor"),
        hass.config_entries.async_forward_entry_unload(entry, "switch"),
    ))
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok