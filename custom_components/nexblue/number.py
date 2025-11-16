from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import NexblueAPIError, NexblueChargerData, NexblueCommandError
from .const import DOMAIN

MIN_CURRENT_LIMIT = 6
MAX_CURRENT_LIMIT = 32


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    tracked: set[str] = set()

    @callback
    def _discover_new_numbers() -> None:
        new_entities: list[NexblueCurrentLimitNumber] = []
        for charger_id, data in coordinator.data.items():
            if charger_id in tracked:
                continue
            if not isinstance(data, NexblueChargerData):
                continue
            tracked.add(charger_id)
            new_entities.append(NexblueCurrentLimitNumber(coordinator, charger_id))

        if new_entities:
            async_add_entities(new_entities)

    _discover_new_numbers()
    entry.async_on_unload(coordinator.async_add_listener(_discover_new_numbers))


class NexblueCurrentLimitNumber(CoordinatorEntity, NumberEntity):
    """Number entity to configure the charger current limit."""

    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_has_entity_name = True
    _attr_name = "Current Limit"
    _attr_translation_key = "current_limit"
    _attr_native_min_value = MIN_CURRENT_LIMIT
    _attr_native_step = 1
    _attr_mode = NumberMode.AUTO

    def __init__(self, coordinator, charger_id: str) -> None:
        super().__init__(coordinator)
        self._charger_id = charger_id
        self._attr_unique_id = f"{charger_id}_current_limit"

        charger_data = self._charger_data
        product_name = charger_data.detail.get("product_name") if charger_data else None
        default_name = f"Charger {charger_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, charger_id)},
            manufacturer="Nexblue",
            model=product_name,
            name=product_name or default_name,
        )
        self._attr_native_max_value = (
            charger_data.max_configurable_current if charger_data else MAX_CURRENT_LIMIT
        )

    @property
    def _charger_data(self) -> NexblueChargerData | None:
        data = self.coordinator.data.get(self._charger_id)
        if isinstance(data, NexblueChargerData):
            return data
        return None

    @property
    def available(self) -> bool:
        charger_data = self._charger_data
        return bool(self.coordinator.last_update_success and charger_data)

    @property
    def native_value(self) -> float | None:
        charger_data = self._charger_data
        if not charger_data:
            return None
        return charger_data.current_limit

    async def async_set_native_value(self, value: float) -> None:
        target = int(round(value))
        min_value = self._attr_native_min_value or MIN_CURRENT_LIMIT
        max_value = self._attr_native_max_value or MAX_CURRENT_LIMIT
        target = max(min_value, min(target, max_value))

        try:
            await self.coordinator.api.set_current_limit(self._charger_id, target)
        except NexblueCommandError as err:
            raise HomeAssistantError(
                f"Nexblue rejected the current limit change (code {err.result})"
            ) from err
        except NexblueAPIError as err:
            raise HomeAssistantError(f"Failed to communicate with Nexblue: {err}") from err

        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        charger_data = self._charger_data
        if not charger_data:
            return None
        attrs: dict[str, Any] = {
            "charger_id": self._charger_id,
            "circuit_fuse": charger_data.circuit_fuse,
        }
        return {key: value for key, value in attrs.items() if value is not None}

    @callback
    def _handle_coordinator_update(self) -> None:
        charger_data = self._charger_data
        if charger_data:
            self._attr_native_max_value = charger_data.max_configurable_current
        super()._handle_coordinator_update()
