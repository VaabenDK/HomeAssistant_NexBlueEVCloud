from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import NexblueAPIError, NexblueChargerData, NexblueCommandError
from .const import CHARGER_STATE_MAP, DOMAIN

_LOGGER = logging.getLogger(__name__)


ACTIVE_STATES = {CHARGER_STATE_MAP[2]}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    tracked: set[str] = set()

    @callback
    def _discover_new_switches() -> None:
        new_entities: list[NexblueChargerSwitch] = []
        for charger_id in coordinator.data:
            if charger_id in tracked:
                continue
            tracked.add(charger_id)
            new_entities.append(NexblueChargerSwitch(coordinator, charger_id))

        if new_entities:
            async_add_entities(new_entities)

    _discover_new_switches()
    entry.async_on_unload(coordinator.async_add_listener(_discover_new_switches))


class NexblueChargerSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a Nexblue charger start/stop switch."""

    def __init__(self, coordinator, charger_id: str) -> None:
        super().__init__(coordinator)
        self._charger_id = charger_id
        self._attr_unique_id = f"{charger_id}_charging_switch"

        charger_data = self._charger_data
        product_name = charger_data.detail.get("product_name") if charger_data else None
        default_name = f"Charger {charger_id}"
        self._attr_name = "Charging"
        self._attr_has_entity_name = True
        self._attr_device_class = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, charger_id)},
            manufacturer="Nexblue",
            model=product_name,
            name=product_name or default_name,
        )

    @property
    def _charger_data(self) -> NexblueChargerData | None:
        return self.coordinator.data.get(self._charger_id)

    @property
    def available(self) -> bool:
        charger_data = self._charger_data
        return bool(self.coordinator.last_update_success and charger_data and charger_data.online)

    @property
    def is_on(self) -> bool:
        charger_data = self._charger_data
        if not charger_data:
            return False
        return charger_data.charging_state in ACTIVE_STATES

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send_command(self.coordinator.api.start_charging)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send_command(self.coordinator.api.stop_charging)

    async def _send_command(self, command: Callable[[str], Awaitable[None]]) -> None:
        try:
            await command(self._charger_id)
        except NexblueCommandError as err:
            raise HomeAssistantError(f"Nexblue rejected the command (code {err.result})") from err
        except NexblueAPIError as err:
            raise HomeAssistantError(f"Failed to communicate with Nexblue: {err}") from err

        await self.coordinator.async_request_refresh()