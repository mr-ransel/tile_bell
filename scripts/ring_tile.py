#!/usr/bin/env python3
"""Ring a Tile device directly via BLE using bleak.

Standalone script — no Home Assistant required.
Useful for testing ring functionality outside of HA.

Usage:
    python ring_tile.py --mac AA:BB:CC:DD:EE:FF --auth-key <base64_auth_key>
    python ring_tile.py --mac AA:BB:CC:DD:EE:FF --auth-key <base64_auth_key> --duration 10 --volume low
"""

import argparse
import asyncio
import base64
import logging
import random
import sys

from bleak import BleakClient, BleakScanner
from cryptography.hazmat.primitives import hashes, hmac

# Tile BLE UUIDs
TILE_COMMAND_UUID = "9d410018-35d6-f4dd-ba60-e7bd8dc491c0"
TILE_RESPONSE_UUID = "9d410019-35d6-f4dd-ba60-e7bd8dc491c0"

CMD_RING_BASE = [5, 2]

VOLUME_OPTIONS = {
    "low": [1, 1],
    "medium": [1, 2],
    "high": [1, 3],
    "auto": [22, 3, 3],
}

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")
_LOGGER = logging.getLogger(__name__)


def convert_to_long_buffer(n: int) -> list[int]:
    hex_string = f"{n:x}"
    if len(hex_string) % 2:
        hex_string = "0" + hex_string
    result = [0] * 8
    byte_len = len(hex_string) // 2
    for i in range(byte_len):
        result[i] = int(hex_string[2 * i : 2 * (i + 1)], 16)
    return result


def generate_hmac(secret: bytes, data: list[int]) -> bytes:
    data_copy = data.copy()
    while len(data_copy) < 32:
        data_copy.append(0)
    h = hmac.HMAC(secret, hashes.SHA256())
    h.update(bytes(data_copy))
    return h.finalize()


async def _try_ring(client: BleakClient, auth_key: bytes, duration: int, volume: str, volume_bytes: list[int]) -> bool:
    """Perform the auth handshake and ring command on an already-connected client."""
    nonce = 0
    auth_key_mac = None
    expected_prefix = 0
    response_complete = asyncio.Event()

    rng = random.Random()
    channel = [0] + [rng.randint(0, 255) for _ in range(4)]
    rand_a = [rng.randint(0, 255) for _ in range(14)]

    async def handle_response(sender, data):
        nonlocal nonce, auth_key_mac, expected_prefix

        data_list = list(data)
        if not data_list:
            return

        prefix = data_list[0]
        toa_type = data_list[5] if prefix == 0 else data_list[1]
        _LOGGER.debug("Response: prefix=%d, toa_type=%d, data=%s", prefix, toa_type, data_list)

        if toa_type == 1:
            ring_command = CMD_RING_BASE + volume_bytes + [duration]
            nonce += 1
            bf_nonce = convert_to_long_buffer(nonce)
            hmac_data = bf_nonce + [1, len(ring_command)] + ring_command
            hmac_result = generate_hmac(auth_key_mac, hmac_data)
            command = [prefix] + ring_command + list(hmac_result[:4])
            _LOGGER.info("Sending ring command (duration=%ds, volume=%s)", duration, volume)
            await client.write_gatt_char(TILE_COMMAND_UUID, bytes(command), response=False)

        elif toa_type == 7:
            _LOGGER.info("Ring acknowledged! Tile should be ringing for %ds", duration)
            response_complete.set()

        elif toa_type == 18:
            expected_prefix = data_list[6]
            channel_data = data_list[7:]
            hmac_input = rand_a + channel_data + [expected_prefix] + channel[1:]
            auth_key_mac = generate_hmac(auth_key, hmac_input)[:16]
            _LOGGER.debug("Auth key MAC generated, opening channel (prefix=%d)", expected_prefix)

            nonce += 1
            bf_nonce = convert_to_long_buffer(nonce)
            payload = [18, 19]
            hmac_data = bf_nonce + [1, len(payload)] + payload
            hmac_result = generate_hmac(auth_key_mac, hmac_data)
            command = [expected_prefix] + payload + list(hmac_result[:4])
            await client.write_gatt_char(TILE_COMMAND_UUID, bytes(command), response=False)

        elif toa_type == 19:
            _LOGGER.debug("Authentication complete")

        elif toa_type == 21:
            _LOGGER.debug("Starting auth handshake")
            command = channel + [16] + rand_a
            await client.write_gatt_char(TILE_COMMAND_UUID, bytes(command), response=False)

        else:
            _LOGGER.debug("Unknown toa_type: %d", toa_type)

    await client.start_notify(TILE_RESPONSE_UUID, handle_response)

    init_command = channel + [20] + rand_a
    await client.write_gatt_char(TILE_COMMAND_UUID, bytes(init_command), response=False)

    try:
        await asyncio.wait_for(response_complete.wait(), timeout=15.0)
        _LOGGER.info("Done!")
        return True
    except asyncio.TimeoutError:
        _LOGGER.error("Timeout waiting for ring acknowledgement")
        return False
    finally:
        try:
            await client.stop_notify(TILE_RESPONSE_UUID)
        except Exception:
            pass


async def ring_tile(mac: str, auth_key_b64: str, duration: int = 30, volume: str = "high"):
    auth_key = base64.b64decode(auth_key_b64)
    volume_bytes = VOLUME_OPTIONS.get(volume, VOLUME_OPTIONS["high"])

    _LOGGER.info("Scanning for %s (up to 30s, Tiles advertise infrequently)...", mac)
    device = await BleakScanner.find_device_by_address(mac, timeout=30.0)
    if not device:
        _LOGGER.error("Device %s not found! Is it nearby and powered on?", mac)
        return False

    _LOGGER.info("Found %s (%s), connecting (up to 3 attempts)...", device.name, device.address)
    for attempt in range(1, 4):
        try:
            async with BleakClient(device, timeout=30.0) as client:
                _LOGGER.info("Connected (attempt %d/3), starting auth...", attempt)
                return await _try_ring(client, auth_key, duration, volume, volume_bytes)
        except Exception as e:
            _LOGGER.error("Attempt %d/3 failed: %s", attempt, e)
            if attempt < 3:
                _LOGGER.info("Retrying in 5s...")
                await asyncio.sleep(5)

    _LOGGER.error("All connection attempts failed")
    return False


def main():
    parser = argparse.ArgumentParser(description="Ring a Tile device via BLE")
    parser.add_argument("--mac", required=True, help="BLE MAC address (e.g. AA:BB:CC:DD:EE:FF)")
    parser.add_argument("--auth-key", required=True, help="Base64-encoded auth key from Tile cloud")
    parser.add_argument("--duration", type=int, default=30, help="Ring duration in seconds (1-60, default 30)")
    parser.add_argument("--volume", choices=["low", "medium", "high", "auto"], default="high", help="Volume level (default high)")
    args = parser.parse_args()

    duration = max(1, min(60, args.duration))
    success = asyncio.run(ring_tile(args.mac, args.auth_key, duration, args.volume))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
