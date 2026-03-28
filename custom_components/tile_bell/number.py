"""Number platform for Tile Bell integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number platform."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    entry_type = entry_data.get("entry_type")

    if entry_type == "hub":
        # Hub entry — create entities from subentries
        for subentry in config_entry.subentries.values():
            if subentry.subentry_type != "device":
                continue
            device_data = entry_data["devices"][subentry.subentry_id]
            config = device_data["config"]
            async_add_entities(
                [TileRingDurationNumber(config, device_data)],
                config_subentry_id=subentry.subentry_id,
            )

    elif entry_type == "device":
        # Standalone manual device entry
        config = entry_data["config"]
        async_add_entities([TileRingDurationNumber(config, entry_data)])


class TileRingDurationNumber(NumberEntity):
    """Number entity to control ring duration."""

    entity_description = NumberEntityDescription(
        key="ring_duration",
        name="Ring Duration",
        icon="mdi:timer-outline",
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_min_value=1,
        native_max_value=60,
        native_step=1,
        native_unit_of_measurement="s",
    )

    def __init__(self, config: dict[str, Any], device_data: dict[str, Any]) -> None:
        """Initialize the number entity."""
        self._config = config
        self._device_data = device_data
        self._attr_name = f"{config['name']} Ring Duration"
        self._attr_unique_id = f"{config['mac_address']}_ring_duration"

        # Default ring duration
        self._attr_native_value = 30.0

        # Set initial availability based on device discovery
        self._attr_available = device_data.get("available", False)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        identifiers = {(DOMAIN, self._config["mac_address"])}
        tile_id = self._config.get("tile_id")
        if tile_id:
            identifiers.add(("tile", tile_id))
        return DeviceInfo(
            identifiers=identifiers,
            name=self._config["name"],
            manufacturer="Tile",
            model="Tile Tracker",
            connections={("bluetooth", self._config["mac_address"])},
        )

    @property
    def available(self) -> bool:
        """Return if the device is available."""
        return self._device_data.get("available", False)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_available = self._device_data.get("available", False)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        # Listen for availability changes
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_availability_update_{self._config['mac_address']}",
                self._handle_coordinator_update,
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set new ring duration."""
        self._attr_native_value = value
        # Store the duration in device data for button to use
        self._device_data["ring_duration"] = int(value)
        self.async_write_ha_state()
        _LOGGER.info("Set ring duration for %s to %d seconds", self._config["name"], int(value))
