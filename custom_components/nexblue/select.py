from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import NexblueAPIError, NexblueChargerData, NexblueCommandError
from .const import (
    DOMAIN,
    SCHEDULE_MODE_LABELS,
    SCHEDULE_MODE_MAP,
    SCHEDULE_MODE_REVERSE_MAP,
    SELECTABLE_SCHEDULE_MODES,
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    tracked: set[str] = set()

    @callback
    def _discover_new_selects() -> None:
        new_entities: list[NexblueScheduleModeSelect] = []
        for charger_id, data in coordinator.data.items():
            if charger_id in tracked:
                continue
            if not isinstance(data, NexblueChargerData):
                continue
            if data.schedule is None or data.schedule_mode is None:
                continue
            tracked.add(charger_id)
            new_entities.append(NexblueScheduleModeSelect(coordinator, charger_id))

        if new_entities:
            async_add_entities(new_entities)

    _discover_new_selects()
    entry.async_on_unload(coordinator.async_add_listener(_discover_new_selects))


def _label_for_slug(slug: str) -> str:
    return SCHEDULE_MODE_LABELS.get(slug, slug.replace("_", " ").title())


class NexblueScheduleModeSelect(CoordinatorEntity, SelectEntity):
    """Select entity to switch charger schedule mode."""

    _attr_has_entity_name = True
    _attr_name = "Schedule Mode"
    _attr_translation_key = "schedule_mode"

    def __init__(self, coordinator, charger_id: str) -> None:
        super().__init__(coordinator)
        self._charger_id = charger_id
        self._attr_unique_id = f"{charger_id}_schedule_mode"
        self._option_to_slug: dict[str, str] = {}
        self._selectable_labels: set[str] = set()

        charger_data = self._charger_data
        product_name = charger_data.detail.get("product_name") if charger_data else None
        default_name = f"Charger {charger_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, charger_id)},
            manufacturer="Nexblue",
            model=product_name,
            name=product_name or default_name,
        )

        self._refresh_options()

    @property
    def _charger_data(self) -> NexblueChargerData | None:
        data = self.coordinator.data.get(self._charger_id)
        if isinstance(data, NexblueChargerData):
            return data
        return None

    @property
    def available(self) -> bool:
        charger_data = self._charger_data
        return bool(self.coordinator.last_update_success and charger_data and charger_data.schedule is not None)

    @property
    def current_option(self) -> str | None:
        charger_data = self._charger_data
        if not charger_data:
            return None
        slug = charger_data.schedule_mode
        if not slug:
            return None
        label = _label_for_slug(slug)
        if label not in self._option_to_slug:
            self._option_to_slug[label] = slug
            self._attr_options = list(self._option_to_slug.keys())
        return label

    async def async_select_option(self, option: str) -> None:
        slug = self._option_to_slug.get(option)
        if not slug:
            raise HomeAssistantError(f"Unsupported schedule option: {option}")

        charger_data = self._charger_data
        if not charger_data:
            raise HomeAssistantError("Charger data unavailable")

        current_slug = charger_data.schedule_mode
        if slug == current_slug:
            return

        if option not in self._selectable_labels:
            raise HomeAssistantError("This schedule mode cannot be selected via the Nexblue API")

        mode_id = SCHEDULE_MODE_REVERSE_MAP.get(slug)
        if mode_id is None:
            raise HomeAssistantError("Failed to resolve schedule mode")

        try:
            await self.coordinator.api.set_schedule_mode(self._charger_id, mode_id)
        except NexblueCommandError as err:
            raise HomeAssistantError(
                f"Nexblue rejected the schedule mode change (code {err.result})"
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
            "uk_reg": charger_data.uk_reg,
        }
        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        self._refresh_options()
        super()._handle_coordinator_update()

    def _refresh_options(self) -> None:
        option_map: dict[str, str] = {}
        selectable_labels: set[str] = set()
        charger_data = self._charger_data

        if charger_data:
            uk_reg = charger_data.uk_reg
            for mode_id in sorted(SELECTABLE_SCHEDULE_MODES):
                if mode_id == 0 and not uk_reg:
                    continue
                slug = SCHEDULE_MODE_MAP.get(mode_id)
                if not slug:
                    continue
                label = _label_for_slug(slug)
                option_map[label] = slug
                selectable_labels.add(label)

            current_slug = charger_data.schedule_mode
            if current_slug:
                label = _label_for_slug(current_slug)
                option_map.setdefault(label, current_slug)

        self._option_to_slug = option_map
        self._selectable_labels = selectable_labels
        self._attr_options = list(option_map.keys())
