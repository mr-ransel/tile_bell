"""Sensor platform for Tile Bell integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    entry_type = entry_data.get("entry_type")

    if entry_type == "hub":
        # Battery data comes from cloud API, only available for hub entries
        for subentry in config_entry.subentries.values():
            if subentry.subentry_type != "device":
                continue
            device_data = entry_data["devices"][subentry.subentry_id]
            config = device_data["config"]
            async_add_entities(
                [TileBatteryLevelSensor(config, device_data)],
                config_subentry_id=subentry.subentry_id,
            )

    # No battery sensor for manual device entries — no cloud data source


class TileBatteryLevelSensor(SensorEntity):
    """Sensor showing Tile device battery level."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:battery-bluetooth"
    _attr_entity_registry_enabled_default = False

    def __init__(self, config: dict[str, Any], device_data: dict[str, Any]) -> None:
        """Initialize the battery sensor."""
        self._config = config
        self._device_data = device_data
        self._attr_name = f"{config['name']} Battery"
        self._attr_unique_id = f"{config['mac_address']}_battery"
        self._attr_native_value = device_data.get("battery_level")

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

    @callback
    def _handle_battery_update(self) -> None:
        """Handle updated battery data."""
        self._attr_native_value = self._device_data.get("battery_level")
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_battery_update_{self._config['mac_address']}",
                self._handle_battery_update,
            )
        )
