"""Tile device communication handler."""
import asyncio
import base64
import logging
import random
from typing import Optional

from bleak import BleakClient
from bleak_retry_connector import establish_connection
from cryptography.hazmat.primitives import hashes, hmac
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .const import TILE_COMMAND_UUID, TILE_RESPONSE_UUID, CMD_RING_BASE, VOLUME_OPTIONS

_LOGGER = logging.getLogger(__name__)


class TileDevice:
    """Handle communication with a Tile device."""

    def __init__(self, hass: HomeAssistant, mac_address: str, auth_key: str, name: str):
        """Initialize the Tile device."""
        self.hass = hass
        self.mac_address = mac_address
        self.auth_key = base64.b64decode(auth_key)
        self.name = name
        self.client: Optional[BleakClient] = None
        self.nonce = 0
        self.auth_key_mac: Optional[bytes] = None
        self.expected_prefix = 0
        self.connected = False
        self.channel: list[int] = []
        self.rand_a: list[int] = []

    async def connect(self) -> bool:
        """Connect to the Tile device using Home Assistant's Bluetooth integration."""
        try:
            # Get the BLE device from Home Assistant's Bluetooth integration
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.mac_address, connectable=True
            )
            
            if not ble_device:
                _LOGGER.error("Could not find Bluetooth device %s", self.mac_address)
                # Try to trigger rediscovery
                await bluetooth.async_rediscover_address(self.hass, self.mac_address)
                return False

            # Use bleak-retry-connector for reliable connection with longer timeout
            self.client = await establish_connection(
                BleakClient,
                ble_device,
                self.mac_address,
                max_attempts=3,
                disconnected_callback=self._on_disconnect,
                timeout=20.0,  # Increased timeout for Tile devices
            )
            
            self.connected = True
            _LOGGER.info("Connected to Tile device %s (%s)", self.name, self.mac_address)
            return True
            
        except Exception as e:
            _LOGGER.error("Failed to connect to %s (%s): %s", self.name, self.mac_address, e)
            return False

    def _on_disconnect(self, client: BleakClient) -> None:
        """Handle disconnect callback."""
        self.connected = False
        _LOGGER.debug("Tile device %s disconnected", self.name)

    async def disconnect(self):
        """Disconnect from the Tile device."""
        if self.client and self.connected:
            try:
                await self.client.disconnect()
            except Exception as e:
                _LOGGER.warning("Error during disconnect: %s", e)
            finally:
                self.connected = False
                _LOGGER.info("Disconnected from Tile device %s", self.name)

    def convert_to_long_buffer(self, n: int) -> list[int]:
        """Convert integer to 8-byte buffer."""
        hex_string = f"{n:x}"
        if len(hex_string) % 2:
            hex_string = "0" + hex_string
        
        result = [0] * 8
        byte_len = len(hex_string) // 2
        for i in range(byte_len):
            result[i] = int(hex_string[2*i:2*(i+1)], 16)
        return result

    def generate_hmac(self, secret: bytes, data: list[int]) -> bytes:
        """Generate HMAC-SHA256."""
        # Pad data to 32 bytes
        data_copy = data.copy()
        while len(data_copy) < 32:
            data_copy.append(0)
        
        h = hmac.HMAC(secret, hashes.SHA256())
        h.update(bytes(data_copy))
        return h.finalize()

    async def authenticated_send(self, prefix: int, payload: list[int]):
        """Send authenticated command."""
        if not self.client or not self.connected or not self.auth_key_mac:
            _LOGGER.error("Cannot send authenticated command - client, connection, or auth_key_mac missing")
            return
            
        self.nonce += 1
        bf_nonce = self.convert_to_long_buffer(self.nonce)
        hmac_data = bf_nonce + [1, len(payload)] + payload
        hmac_result = self.generate_hmac(self.auth_key_mac, hmac_data)
        
        command = [prefix] + payload + list(hmac_result[:4])
        try:
            await self.client.write_gatt_char(TILE_COMMAND_UUID, bytes(command), response=False)
            _LOGGER.debug("Sent authenticated command: prefix=%d, payload=%s", prefix, payload)
        except Exception as e:
            _LOGGER.error("Failed to send authenticated command: %s", e)
            raise

    async def ring(self, duration: int = 30, volume: str = "high") -> bool:
        """Ring the Tile device for specified duration and volume.

        Args:
            duration: Ring duration in seconds (1-60, default 30)
            volume: Volume level (low, medium, high, auto, default high)
        """
        if not await self.connect():
            return False

        # Clamp duration to reasonable bounds
        duration = max(1, min(60, duration))

        # Get volume bytes, default to high if invalid
        volume_data = VOLUME_OPTIONS.get(volume, VOLUME_OPTIONS["high"])
        volume_bytes = volume_data["bytes"]

        try:
            # Reset state for new ring attempt
            self.nonce = 0
            self.auth_key_mac = None
            self.expected_prefix = 0

            # Set up response handler
            response_complete = asyncio.Event()

            async def handle_response(sender, data):
                await self._handle_response(data, response_complete, duration, volume_bytes)

            # Start notifications on the response characteristic
            await self.client.start_notify(TILE_RESPONSE_UUID, handle_response)

            # Generate random channel and randA (matching original implementation)
            rng = random.Random()
            self.channel = [0] + [rng.randint(0, 255) for _ in range(4)]
            self.rand_a = [rng.randint(0, 255) for _ in range(14)]

            # Start authentication sequence
            init_command = self.channel + [20] + self.rand_a
            await self.client.write_gatt_char(TILE_COMMAND_UUID, bytes(init_command), response=False)
            _LOGGER.debug("Sent initial auth command for %s (duration: %ds, volume: %s)",
                         self.name, duration, volume)

            # Wait for authentication and ring to complete
            try:
                await asyncio.wait_for(response_complete.wait(), timeout=15.0)
                _LOGGER.info("Successfully rang Tile device %s for %d seconds at %s volume",
                           self.name, duration, volume)
                return True
            except asyncio.TimeoutError:
                _LOGGER.error("Timeout waiting for response from %s", self.name)
                return False
            finally:
                # Stop notifications
                try:
                    await self.client.stop_notify(TILE_RESPONSE_UUID)
                except Exception as e:
                    _LOGGER.debug("Error stopping notifications: %s", e)

        except Exception as e:
            _LOGGER.error("Failed to ring %s: %s", self.name, e)
            return False
        finally:
            await self.disconnect()

    async def _handle_response(self, data: bytes, response_complete: asyncio.Event, duration: int, volume_bytes: list[int]):
        """Handle response from Tile device."""
        try:
            data_list = list(data)
            if not data_list:
                return
                
            prefix = data_list[0]
            
            # Handle prefix mismatch gracefully
            if prefix != self.expected_prefix and self.expected_prefix != 0:
                _LOGGER.debug("Received prefix %d, expected %d", prefix, self.expected_prefix)
                
            toa_type = data_list[5] if prefix == 0 else data_list[1]
            _LOGGER.debug("Received response: prefix=%d, toa_type=%d, data_len=%d", 
                         prefix, toa_type, len(data_list))
            
            if toa_type == 1:
                # Send ring command with volume and duration
                # Based on node-tile: [5, 2, volume_bytes..., duration]
                ring_command = CMD_RING_BASE + volume_bytes + [duration]
                _LOGGER.debug("Sending ring command with duration %ds, volume_bytes %s",
                             duration, volume_bytes)
                await self.authenticated_send(prefix, ring_command)
                
            elif toa_type == 7:
                # Ring command acknowledged - wait for completion
                _LOGGER.debug("Ring command acknowledged, will ring for %ds", duration)
                response_complete.set()
                
            elif toa_type == 18:
                # Finish auth, open channel
                if len(data_list) < 7:
                    _LOGGER.error("Invalid response length for toa_type 18")
                    response_complete.set()
                    return
                    
                self.expected_prefix = data_list[6]
                channel_data = data_list[7:]
                
                # Generate auth key MAC
                hmac_input = self.rand_a + channel_data + [self.expected_prefix] + self.channel[1:]
                self.auth_key_mac = self.generate_hmac(self.auth_key, hmac_input)[:16]
                _LOGGER.debug("Generated auth_key_mac, opening channel with prefix %d", self.expected_prefix)
                
                await self.authenticated_send(self.expected_prefix, [18, 19])
                
            elif toa_type == 19:
                # Authentication complete, ready for commands
                _LOGGER.debug("Authentication complete")
                
            elif toa_type == 21:
                # Start auth - send channel and randA
                _LOGGER.debug("Starting authentication handshake")
                command = self.channel + [16] + self.rand_a
                await self.client.write_gatt_char(TILE_COMMAND_UUID, bytes(command), response=False)
                
            else:
                _LOGGER.debug("Unknown toa_type: %d", toa_type)
                
        except Exception as e:
            _LOGGER.error("Error handling response: %s", e)
            response_complete.set()  # Set event to prevent hanging