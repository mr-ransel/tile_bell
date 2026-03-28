"""Config flow for Tile Bell integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow as HAConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, TILE_ID_CHAR_UUID

_LOGGER = logging.getLogger(__name__)

# Main config flow schemas
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("config_method", default="hub"): vol.In(
            {
                "hub": "Tile Account Hub (recommended)",
                "manual": "Manual MAC Address & Auth Key"
            }
        ),
    }
)

STEP_HUB_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("email"): str,
        vol.Required("password"): str,
    }
)

STEP_MANUAL_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("name"): str,
        vol.Required("mac_address"): str,
        vol.Required("auth_key"): str,
    }
)

# Subentry flow schemas (manual path — MAC only, name comes from cloud tile selection)
STEP_DEVICE_MAC_SCHEMA = vol.Schema(
    {
        vol.Required("ble_mac_address"): str,
    }
)


async def validate_tile_credentials(hass: HomeAssistant, email: str, password: str) -> dict[str, Any]:
    """Validate Tile credentials and retrieve device list."""
    try:
        import pytile
        from aiohttp import ClientSession
        
        async with ClientSession() as session:
            api = await pytile.async_login(email, password, session)
            tiles = await api.async_get_tiles()
            
            if not tiles:
                raise NoDevicesFound
                
            # Store physical tiles only (exclude phones)
            tile_data = {}
            for tile_id, tile in tiles.items():
                if not str(tile.uuid).startswith('p!'):
                    tile_data[tile_id] = {
                        "name": tile.name,
                        "api_mac": str(tile.uuid).upper(),
                        "auth_key": tile._tile_data["result"]["auth_key"]
                    }
            
            if not tile_data:
                raise NoDevicesFound("No physical Tile devices found (phones excluded)")
            
            return {"tiles": tile_data}
            
    except ImportError:
        raise CannotConnect("pytile library not available")
    except Exception as e:
        _LOGGER.error("Failed to authenticate with Tile: %s", e)
        raise InvalidAuth


async def validate_manual_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate manual input."""
    if not all([data.get("name"), data.get("mac_address"), data.get("auth_key")]):
        raise InvalidAuth("All fields are required")
    
    # Validate MAC address format
    mac = data["mac_address"].replace(":", "").replace("-", "")
    if len(mac) != 12 or not all(c in "0123456789ABCDEFabcdef" for c in mac):
        raise InvalidAuth("Invalid MAC address format")
    
    return {"title": data["name"]}


class ConfigFlow(HAConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tile Bell."""

    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Get supported subentry types."""
        # Only hub entries support subentries
        if config_entry.data.get("entry_type") == "hub":
            return {"device": DeviceSubentryFlowHandler}
        return {}

    def __init__(self):
        """Initialize."""
        self.tile_data = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - choose config method."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        if user_input["config_method"] == "hub":
            return await self.async_step_hub()
        else:
            return await self.async_step_manual()

    async def async_step_hub(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle hub configuration - store Tile credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                result = await validate_tile_credentials(
                    self.hass, user_input["email"], user_input["password"]
                )
                self.tile_data = result["tiles"]
                
                # Create hub config entry
                await self.async_set_unique_id(f"tile_hub_{user_input['email']}")
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=f"Tile Account ({user_input['email']})",
                    data={
                        "entry_type": "hub",
                        "email": user_input["email"],
                        "password": user_input["password"],
                        "tiles": self.tile_data,
                    }
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except NoDevicesFound:
                errors["base"] = "no_devices"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="hub", 
            data_schema=STEP_HUB_DATA_SCHEMA, 
            errors=errors,
            description_placeholders={
                "instructions": (
                    "Enter your Tile account credentials. This will create a hub "
                    "that you can then add individual devices to."
                )
            }
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual configuration - standalone device."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_manual_input(self.hass, user_input)
                
                await self.async_set_unique_id(user_input["mac_address"])
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=info["title"], 
                    data={
                        "entry_type": "device",
                        "name": user_input["name"],
                        "mac_address": user_input["mac_address"],
                        "auth_key": user_input["auth_key"],
                        "config_method": "manual"
                    }
                )
            except InvalidAuth as e:
                errors["base"] = "invalid_auth"
                _LOGGER.error("Manual config validation failed: %s", e)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="manual", 
            data_schema=STEP_MANUAL_DATA_SCHEMA, 
            errors=errors,
            description_placeholders={
                "instructions": (
                    "Manually configure a single Tile device. "
                    "You'll need the actual BLE MAC address and auth key."
                )
            }
        )


async def _async_discover_tiles(
    hass: HomeAssistant,
    cloud_tiles: dict[str, Any],
    existing_macs: set[str],
) -> list[dict[str, Any]]:
    """Scan for nearby Tile BLE devices and match them to cloud accounts.

    Filters out devices whose BLE MAC is already configured.
    Returns a list of dicts with keys: ble_mac, tile_id, tile_name, api_mac, auth_key, rssi.
    """
    from bleak_retry_connector import establish_connection
    from bleak import BleakClient

    # Get all currently discovered BLE devices from HA
    discovered = bluetooth.async_discovered_service_info(hass)

    # Filter to devices with "Tile" in their name, excluding already-configured MACs
    tile_candidates = []
    for service_info in discovered:
        name = service_info.name or ""
        if "tile" in name.lower() and service_info.address.upper() not in existing_macs:
            tile_candidates.append(service_info)

    if not tile_candidates:
        return []

    matched = []
    for service_info in tile_candidates:
        ble_mac = service_info.address.upper()
        try:
            # Connect and read the TILE_ID characteristic
            client = await establish_connection(
                BleakClient, service_info.device, service_info.name, timeout=15.0
            )
            try:
                data = await client.read_gatt_char(TILE_ID_CHAR_UUID)
                ble_tile_id = data.hex()
            finally:
                await client.disconnect()
        except Exception as e:
            _LOGGER.debug("Could not read TILE_ID from %s: %s", ble_mac, e)
            continue

        # Match against cloud Tile UUIDs
        for cloud_id, cloud_data in cloud_tiles.items():
            if cloud_id.lower() == ble_tile_id.lower():
                matched.append({
                    "ble_mac": ble_mac,
                    "tile_id": cloud_id,
                    "tile_name": cloud_data["name"],
                    "api_mac": cloud_data["api_mac"],
                    "auth_key": cloud_data["auth_key"],
                    "rssi": service_info.rssi,
                })
                break

    return matched


class DeviceSubentryFlowHandler(ConfigSubentryFlow):
    """Handle subentry flow for adding individual Tile devices."""

    def __init__(self) -> None:
        """Initialize."""
        self.ble_mac_address: str | None = None
        self.discovered_tiles: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Choose between auto-discover and manual entry."""
        if user_input is not None:
            if user_input["add_method"] == "discover":
                return await self.async_step_discover()
            else:
                return await self.async_step_manual()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("add_method", default="discover"): vol.In({
                    "discover": "Auto-Discover Nearby Tiles (may take a few minutes)",
                    "manual": "Enter MAC Address Manually",
                }),
            }),
        )

    def _get_existing_macs(self) -> set[str]:
        """Get BLE MACs already configured as subentries."""
        hub_entry = self._get_entry()
        macs = set()
        for subentry in hub_entry.subentries.values():
            if subentry.subentry_type == "device":
                mac = subentry.data.get("mac_address", "").upper()
                if mac:
                    macs.add(mac)
        return macs

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Scan for nearby Tiles and match to cloud account."""
        if user_input is not None:
            selected_mac = user_input["discovered_device"]
            match = next(
                (t for t in self.discovered_tiles if t["ble_mac"] == selected_mac),
                None,
            )
            if match is None:
                return self.async_abort(reason="device_not_found")

            return self.async_create_entry(
                title=match["tile_name"],
                data={
                    "entry_type": "device",
                    "name": match["tile_name"],
                    "mac_address": match["ble_mac"],
                    "auth_key": match["auth_key"],
                    "api_mac": match["api_mac"],
                    "tile_id": match["tile_id"],
                    "config_method": "discover",
                },
                unique_id=match["ble_mac"],
            )

        # Perform the scan
        hub_entry = self._get_entry()
        cloud_tiles = hub_entry.data.get("tiles", {})

        if not cloud_tiles:
            return self.async_abort(reason="no_devices")

        existing_macs = self._get_existing_macs()
        self.discovered_tiles = await _async_discover_tiles(
            self.hass, cloud_tiles, existing_macs
        )

        if not self.discovered_tiles:
            return self.async_abort(reason="no_tiles_discovered")

        # Build selection options
        device_options = {}
        for tile in self.discovered_tiles:
            label = f"{tile['tile_name']} ({tile['ble_mac']}, RSSI: {tile['rssi']})"
            device_options[tile["ble_mac"]] = label

        return self.async_show_form(
            step_id="discover",
            data_schema=vol.Schema({
                vol.Required("discovered_device"): vol.In(device_options),
            }),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Manual entry — type in BLE MAC address."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                ble_mac = user_input["ble_mac_address"].replace(":", "").replace("-", "")
                if len(ble_mac) != 12 or not all(c in "0123456789ABCDEFabcdef" for c in ble_mac):
                    raise InvalidAuth("Invalid BLE MAC address format")

                hub_entry = self._get_entry()
                tiles = hub_entry.data.get("tiles", {})

                if not tiles:
                    raise NoDevicesFound("No Tile devices available from hub")

                self.ble_mac_address = user_input["ble_mac_address"].upper()

                return await self.async_step_select_tile()

            except InvalidAuth:
                errors["ble_mac_address"] = "invalid_mac"
            except NoDevicesFound:
                errors["base"] = "no_devices"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception in device subentry")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="manual",
            data_schema=STEP_DEVICE_MAC_SCHEMA,
            errors=errors,
        )

    async def async_step_select_tile(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Select which Tile device this MAC corresponds to."""
        if user_input is None:
            hub_entry = self._get_entry()
            tiles = hub_entry.data.get("tiles", {})

            device_options = {}
            for tile_id, tile_data in tiles.items():
                display_name = f"{tile_data['name']} (API: {tile_data['api_mac']})"
                device_options[tile_id] = display_name

            if not device_options:
                return self.async_abort(reason="no_devices")

            return self.async_show_form(
                step_id="select_tile",
                data_schema=vol.Schema({
                    vol.Required("tile_id"): vol.In(device_options)
                }),
            )

        # Create the subentry
        tile_id = user_input["tile_id"]
        hub_entry = self._get_entry()
        tile_data = hub_entry.data["tiles"][tile_id]

        device_name = tile_data["name"]

        return self.async_create_entry(
            title=device_name,
            data={
                "entry_type": "device",
                "name": device_name,
                "mac_address": self.ble_mac_address,
                "auth_key": tile_data["auth_key"],
                "api_mac": tile_data["api_mac"],
                "tile_id": tile_id,
                "config_method": "subentry",
            },
            unique_id=self.ble_mac_address,
        )



class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class NoDevicesFound(HomeAssistantError):
    """Error to indicate no devices were found."""