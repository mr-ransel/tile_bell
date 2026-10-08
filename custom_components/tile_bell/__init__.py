"""The Tile Bell integration."""
from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.NUMBER, Platform.SELECT]


def _setup_ble_tracking(
    hass: HomeAssistant, mac_address: str, device_data: dict
) -> None:
    """Register Bluetooth callbacks for a single device."""

    def _device_discovered(service_info, change):
        if service_info.address.upper() == mac_address.upper():
            _LOGGER.debug("Tile device %s discovered: %s", mac_address, change)
            device_data["available"] = True
            device_data["service_info"] = service_info
            async_dispatcher_send(
                hass, f"{DOMAIN}_availability_update_{mac_address}"
            )

    def _device_unavailable(service_info):
        if service_info.address.upper() == mac_address.upper():
            _LOGGER.debug("Tile device %s became unavailable", mac_address)
            device_data["available"] = False
            async_dispatcher_send(
                hass, f"{DOMAIN}_availability_update_{mac_address}"
            )

    cancel_callback = bluetooth.async_register_callback(
        hass,
        _device_discovered,
        {"address": mac_address},
        bluetooth.BluetoothScanningMode.ACTIVE,
    )
    cancel_unavailable = bluetooth.async_track_unavailable(
        hass, _device_unavailable, mac_address
    )

    device_data["cancel_callback"] = cancel_callback
    device_data["cancel_unavailable"] = cancel_unavailable

    # Check if already discovered
    existing = bluetooth.async_last_service_info(hass, mac_address, connectable=True)
    if existing:
        _LOGGER.debug("Found existing service info for %s", mac_address)
        device_data["available"] = True
        device_data["service_info"] = existing


async def _async_hub_entry_updated(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload hub entry when subentries change so new devices get set up."""
    _LOGGER.debug("Hub entry updated, reloading to pick up subentry changes")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tile Bell from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    entry_type = entry.data.get("entry_type", "device")

    if entry_type == "hub":
        # Hub entry — store credentials and set up BLE tracking for each subentry device
        hub_data = {
            "entry_type": "hub",
            "email": entry.data["email"],
            "password": entry.data["password"],
            "tiles": entry.data["tiles"],
            "devices": {},  # keyed by subentry_id
        }
        hass.data[DOMAIN][entry.entry_id] = hub_data

        # Set up BLE tracking for each existing subentry
        for subentry in entry.subentries.values():
            if subentry.subentry_type != "device":
                continue
            mac_address = subentry.data["mac_address"]
            device_data = {
                "entry_type": "device",
                "config": dict(subentry.data),
                "mac_address": mac_address,
                "available": False,
            }
            hub_data["devices"][subentry.subentry_id] = device_data
            _setup_ble_tracking(hass, mac_address, device_data)

        # Forward platforms so entities get created from subentries
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Reload when subentries are added/removed so entities get created
        entry.async_on_unload(
            entry.add_update_listener(_async_hub_entry_updated)
        )

        _LOGGER.info("Set up Tile hub for %s", entry.data["email"])
        return True

    elif entry_type == "device":
        # Standalone manual device entry — no subentries involved
        mac_address = entry.data["mac_address"]
        device_data = {
            "entry_type": "device",
            "config": dict(entry.data),
            "mac_address": mac_address,
            "available": False,
        }
        hass.data[DOMAIN][entry.entry_id] = device_data
        _setup_ble_tracking(hass, mac_address, device_data)

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _LOGGER.info("Set up Tile device %s (%s)", entry.data["name"], mac_address)
        return True

    else:
        _LOGGER.error("Unknown entry type: %s", entry_type)
        return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    entry_type = entry.data.get("entry_type", "device")

    if entry_type == "hub":
        hub_data = hass.data[DOMAIN].get(entry.entry_id, {})
        # Cancel BLE callbacks for all subentry devices
        for device_data in hub_data.get("devices", {}).values():
            if "cancel_callback" in device_data:
                device_data["cancel_callback"]()
            if "cancel_unavailable" in device_data:
                device_data["cancel_unavailable"]()

        if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
            hass.data[DOMAIN].pop(entry.entry_id, None)
        return unload_ok

    elif entry_type == "device":
        device_data = hass.data[DOMAIN].get(entry.entry_id, {})
        if "cancel_callback" in device_data:
            device_data["cancel_callback"]()
        if "cancel_unavailable" in device_data:
            device_data["cancel_unavailable"]()

        if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
            hass.data[DOMAIN].pop(entry.entry_id, None)
        return unload_ok

    return False
