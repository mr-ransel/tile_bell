"""Button platform for Tile Bell integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .tile_device import TileDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the button platform."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    entry_type = entry_data.get("entry_type")

    if entry_type == "hub":
        # Hub entry — create entities from subentries
        for subentry in config_entry.subentries.values():
            if subentry.subentry_type != "device":
                continue
            device_data = entry_data["devices"][subentry.subentry_id]
            config = device_data["config"]
            device = TileDevice(
                hass=hass,
                mac_address=config["mac_address"],
                auth_key=config["auth_key"],
                name=config["name"],
            )
            async_add_entities(
                [TileRingButton(device, device_data)],
                config_subentry_id=subentry.subentry_id,
            )

    elif entry_type == "device":
        # Standalone manual device entry
        config = entry_data["config"]
        device = TileDevice(
            hass=hass,
            mac_address=config["mac_address"],
            auth_key=config["auth_key"],
            name=config["name"],
        )
        async_add_entities([TileRingButton(device, entry_data)])


class TileRingButton(ButtonEntity):
    """Button to ring a Tile device."""

    def __init__(self, device: TileDevice, device_data: dict[str, Any]) -> None:
        """Initialize the ring button."""
        self._device = device
        self._device_data = device_data
        self._attr_name = f"{device.name} Ring"
        self._attr_unique_id = f"{device.mac_address}_ring"
        self._attr_icon = "mdi:bell-ring"

        # Set initial availability based on device discovery
        self._attr_available = device_data.get("available", False)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        identifiers = {(DOMAIN, self._device.mac_address)}
        # Add native Tile integration identifier so devices merge
        tile_id = self._device_data.get("config", {}).get("tile_id")
        if tile_id:
            identifiers.add(("tile", tile_id))
        return DeviceInfo(
            identifiers=identifiers,
            name=self._device.name,
            manufacturer="Tile",
            model="Tile Tracker",
            connections={("bluetooth", self._device.mac_address)},
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
                f"{DOMAIN}_availability_update_{self._device.mac_address}",
                self._handle_coordinator_update,
            )
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        if not self.available:
            raise HomeAssistantError(
                f"Tile device {self._device.name} is not available. "
                "Make sure it's within Bluetooth range and powered on."
            )

        # Get ring duration and volume from device data (set by number/select entities)
        ring_duration = self._device_data.get("ring_duration", 30)
        ring_volume = self._device_data.get("ring_volume", "high")

        _LOGGER.info(
            "Ring button pressed for %s (duration: %ds, volume: %s)",
            self._device.name, ring_duration, ring_volume,
        )

        try:
            success = await self._device.ring(duration=ring_duration, volume=ring_volume)

            if not success:
                raise HomeAssistantError(
                    f"Failed to ring {self._device.name}. "
                    "Check device connectivity and authentication."
                )

            _LOGGER.info(
                "Successfully rang %s for %d seconds",
                self._device.name, ring_duration,
            )

        except HomeAssistantError:
            raise
        except Exception as e:
            _LOGGER.error("Error ringing %s: %s", self._device.name, e)
            raise HomeAssistantError(f"Failed to ring {self._device.name}: {e}") from e
