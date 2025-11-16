from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfElectricCurrent, UnitOfEnergy, UnitOfPower
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.typing import StateType

from .api import NexblueChargerData
from .const import CHARGER_STATE_MAP, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _kw_to_w(value: Any) -> float | None:
    try:
        return round(float(value) * 1000, 1)
    except (TypeError, ValueError):
        return None


@dataclass(eq=False, frozen=True)
class NexblueSensorEntityDescription(SensorEntityDescription):
    """Sensor description with value extraction callback."""

    value_fn: Callable[[NexblueChargerData], StateType | None] = lambda data: None


SENSOR_DESCRIPTIONS: tuple[NexblueSensorEntityDescription, ...] = (
    NexblueSensorEntityDescription(
        key="charging_state",
        translation_key="charging_state",
        name="Charging State",
        device_class=SensorDeviceClass.ENUM,
        options=tuple(CHARGER_STATE_MAP.values()),
        value_fn=lambda data: data.charging_state,
    ),
    NexblueSensorEntityDescription(
        key="power",
        translation_key="power",
        name="Charging Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda data: _kw_to_w(data.status.get("power")),
    ),
    NexblueSensorEntityDescription(
        key="session_energy",
        translation_key="session_energy",
        name="Session Energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.status.get("energy"),
    ),
    NexblueSensorEntityDescription(
        key="lifetime_energy",
        translation_key="lifetime_energy",
        name="Lifetime Energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.status.get("lifetime_energy"),
    ),
    NexblueSensorEntityDescription(
        key="current_limit",
        translation_key="current_limit",
        name="Current Limit",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=lambda data: data.status.get("current_limit"),
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    tracked: set[str] = set()

    @callback
    def _discover_new_entities() -> None:
        new_entities: list[NexblueChargerSensor] = []
        for charger_id in coordinator.data:
            if charger_id in tracked:
                continue
            tracked.add(charger_id)

            for description in SENSOR_DESCRIPTIONS:
                new_entities.append(NexblueChargerSensor(coordinator, charger_id, description))

        if new_entities:
            async_add_entities(new_entities)

    _discover_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_discover_new_entities))


class NexblueChargerSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Nexblue charger sensor."""

    entity_description: NexblueSensorEntityDescription

    def __init__(self, coordinator, charger_id: str, description: NexblueSensorEntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._charger_id = charger_id
        self._attr_unique_id = f"{charger_id}_{description.key}"

        charger_data = self._charger_data
        product_name = charger_data.detail.get("product_name") if charger_data else None
        default_name = f"Charger {charger_id}"
        self._attr_name = description.name
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, charger_id)},
            manufacturer="Nexblue",
            model=product_name,
            name=product_name or default_name,
            suggested_area=(
                charger_data.detail.get("place_data", {}).get("address")
                if charger_data
                else None
            ),
            sw_version=(
                charger_data.status.get("protocol_version") if charger_data else None
            ),
        )

    @property
    def _charger_data(self) -> NexblueChargerData | None:
        return self.coordinator.data.get(self._charger_id)

    @property
    def available(self) -> bool:
        charger_data = self._charger_data
        return bool(self.coordinator.last_update_success and charger_data)

    @property
    def native_value(self) -> StateType:
        charger_data = self._charger_data
        if not charger_data:
            return None
        return self.entity_description.value_fn(charger_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        charger_data = self._charger_data
        if not charger_data:
            return None

        status = charger_data.status
        attrs = {
            "charger_id": self._charger_id,
            "online": charger_data.online,
            "raw_charging_state": status.get("charging_state"),
            "voltage": status.get("voltage_list"),
            "current": status.get("current_list"),
        }
        return {key: value for key, value in attrs.items() if value is not None}