#!/usr/bin/env python3
"""Scan for Tile BLE devices and match them to cloud API data.

This script:
1. Fetches your Tile devices from the cloud API
2. Scans for nearby BLE devices advertising as Tile
3. Connects to each and reads the TILE_ID characteristic
4. Matches BLE devices to cloud devices by Tile ID

This is the same logic the integration's auto-discovery uses,
but as a standalone script for debugging.

Usage:
    pip install pytile aiohttp bleak
    python match_ble_to_cloud.py
"""

import asyncio
import sys
from getpass import getpass

from aiohttp import ClientSession
import pytile
from bleak import BleakScanner, BleakClient

TILE_ID_CHAR_UUID = "9d410007-35d6-f4dd-ba60-e7bd8dc491c0"
SCAN_DURATION = 15


async def get_cloud_tiles(email: str, password: str) -> dict:
    """Fetch tile data from the cloud API."""
    async with ClientSession() as session:
        api = await pytile.async_login(email, password, session)
        tiles = await api.async_get_tiles()

    result = {}
    for tile_id, tile in tiles.items():
        if str(tile.uuid).startswith("p!"):
            continue  # skip phones
        result[tile_id] = {
            "name": tile.name,
            "tile_uuid": str(tile.uuid),
            "auth_key": tile._tile_data["result"]["auth_key"],
        }
    return result


async def scan_for_tiles() -> list[dict]:
    """Scan for BLE devices named 'Tile'."""
    print(f"Scanning for Tile BLE devices for {SCAN_DURATION}s...")
    tiles = []
    devices = await BleakScanner.discover(timeout=SCAN_DURATION, return_adv=True)
    for d, adv in devices.values():
        name = d.name or adv.local_name or ""
        if "tile" in name.lower():
            tiles.append({
                "address": d.address,
                "name": name,
                "rssi": adv.rssi,
            })
    return tiles


async def read_tile_id(ble_address: str) -> str | None:
    """Connect to a Tile and read TILE_ID_CHAR."""
    try:
        print(f"  Connecting to {ble_address}...")
        async with BleakClient(ble_address, timeout=15.0) as client:
            data = await client.read_gatt_char(TILE_ID_CHAR_UUID)
            tile_id = data.hex()
            print(f"  TILE_ID: {tile_id}")
            return tile_id
    except Exception as e:
        print(f"  Failed: {e}")
        return None


async def main():
    email = input("Tile account email: ").strip()
    if not email:
        print("Error: email is required")
        sys.exit(1)

    password = getpass("Tile account password: ")
    if not password:
        print("Error: password is required")
        sys.exit(1)

    # Step 1: Cloud data
    print("\n=== Fetching cloud tile data ===")
    cloud_tiles = await get_cloud_tiles(email, password)
    print(f"Cloud tiles ({len(cloud_tiles)}):")
    for tile_id, data in cloud_tiles.items():
        print(f"  {data['name']:20s}  uuid={data['tile_uuid']}")

    # Step 2: BLE scan
    print(f"\n=== Scanning for BLE Tile devices ===")
    ble_tiles = await scan_for_tiles()
    print(f"Found {len(ble_tiles)} BLE Tile device(s):")
    for t in ble_tiles:
        print(f"  {t['address']}  RSSI={t['rssi']}  Name={t['name']}")

    if not ble_tiles:
        print("\nNo Tile BLE devices found nearby.")
        return

    # Step 3: Connect and match
    print(f"\n=== Matching BLE to cloud ===")
    matches = []
    for tile in ble_tiles:
        ble_addr = tile["address"]
        print(f"\n{ble_addr} ({tile['name']}):")
        tile_id = await read_tile_id(ble_addr)

        if not tile_id:
            continue

        for cloud_id, cloud_data in cloud_tiles.items():
            if cloud_id.lower() == tile_id.lower():
                print(f"  MATCHED: {cloud_data['name']}")
                matches.append({
                    "ble_mac": ble_addr,
                    "cloud_name": cloud_data["name"],
                    "tile_uuid": cloud_data["tile_uuid"],
                    "auth_key": cloud_data["auth_key"],
                    "rssi": tile["rssi"],
                })
                break
        else:
            print(f"  No cloud match for tile_id={tile_id}")

    # Summary
    print(f"\n{'='*60}")
    print(f"Matched {len(matches)} of {len(ble_tiles)} BLE device(s):\n")
    for m in matches:
        print(f"  {m['cloud_name']}")
        print(f"    BLE MAC:   {m['ble_mac']}")
        print(f"    Tile UUID: {m['tile_uuid']}")
        print(f"    Auth Key:  {m['auth_key']}")
        print(f"    RSSI:      {m['rssi']}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
