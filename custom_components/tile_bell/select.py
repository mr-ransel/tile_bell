"""Select platform for Tile Bell integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, VOLUME_OPTIONS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the select platform."""
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
                [TileRingVolumeSelect(config, device_data)],
                config_subentry_id=subentry.subentry_id,
            )

    elif entry_type == "device":
        # Standalone manual device entry
        config = entry_data["config"]
        async_add_entities([TileRingVolumeSelect(config, entry_data)])


class TileRingVolumeSelect(SelectEntity):
    """Select entity to control ring volume."""

    entity_description = SelectEntityDescription(
        key="ring_volume",
        name="Ring Volume",
        icon="mdi:volume-high",
        entity_category=EntityCategory.CONFIG,
        options=list(VOLUME_OPTIONS.keys()),
    )

    def __init__(self, config: dict[str, Any], device_data: dict[str, Any]) -> None:
        """Initialize the select entity."""
        self._config = config
        self._device_data = device_data
        self._attr_name = f"{config['name']} Ring Volume"
        self._attr_unique_id = f"{config['mac_address']}_ring_volume"
        self._attr_options = [VOLUME_OPTIONS[key]["name"] for key in VOLUME_OPTIONS.keys()]

        # Default to high volume (matching node-tile default)
        self._attr_current_option = VOLUME_OPTIONS["high"]["name"]

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

    async def async_select_option(self, option: str) -> None:
        """Change the selected volume option."""
        # Find the volume key by display name
        volume_key = None
        for key, data in VOLUME_OPTIONS.items():
            if data["name"] == option:
                volume_key = key
                break

        if volume_key:
            self._attr_current_option = option
            # Store the volume key in device data for button to use
            self._device_data["ring_volume"] = volume_key
            self.async_write_ha_state()
            _LOGGER.info("Set ring volume for %s to %s", self._config["name"], option)
        else:
            _LOGGER.error("Unknown volume option: %s", option)
