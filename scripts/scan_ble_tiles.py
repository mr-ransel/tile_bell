#!/usr/bin/env python3
"""Scan for nearby Tile BLE devices and dump their characteristics.

Useful for finding BLE MAC addresses and verifying Tile devices are
advertising and connectable. Does not require Tile cloud credentials.

Usage:
    pip install bleak
    python scan_ble_tiles.py
"""

import asyncio
from bleak import BleakScanner, BleakClient

TILE_ID_CHAR_UUID = "9d410007-35d6-f4dd-ba60-e7bd8dc491c0"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
SCAN_DURATION = 15


async def scan_for_tiles():
    """Scan for BLE devices named 'Tile'."""
    print(f"Scanning for {SCAN_DURATION}s...")
    tiles = []
    devices = await BleakScanner.discover(timeout=SCAN_DURATION, return_adv=True)
    for d, adv in devices.values():
        name = d.name or adv.local_name or ""
        if "tile" in name.lower():
            tiles.append({
                "address": d.address,
                "name": name,
                "rssi": adv.rssi,
                "service_uuids": [str(u) for u in (adv.service_uuids or [])],
                "manufacturer_data": {
                    k: v.hex() for k, v in (adv.manufacturer_data or {}).items()
                },
                "service_data": {
                    str(k): v.hex() for k, v in (adv.service_data or {}).items()
                },
            })
    return tiles


async def inspect_tile(address: str, name: str):
    """Connect to a Tile and dump all services/characteristics."""
    print(f"\n{'='*60}")
    print(f"Connecting to {name} ({address})...")
    try:
        async with BleakClient(address, timeout=20.0) as client:
            print(f"Connected!")
            print(f"\nAll services and characteristics:")
            for service in client.services:
                print(f"\n  Service: {service.uuid}")
                if service.description:
                    print(f"    Description: {service.description}")
                for char in service.characteristics:
                    props = ", ".join(char.properties)
                    print(f"    Char: {char.uuid}  [{props}]")
                    if char.description:
                        print(f"      Description: {char.description}")

                    if "read" in char.properties:
                        try:
                            data = await client.read_gatt_char(char.uuid)
                            print(f"      Value (hex): {data.hex()}")
                            print(f"      Value (raw): {list(data)}")
                            try:
                                text = data.decode("utf-8", errors="ignore")
                                if text.isprintable() and len(text) > 0:
                                    print(f"      Value (str): {text}")
                            except Exception:
                                pass
                        except Exception as e:
                            print(f"      Read failed: {e}")

            # Specifically try TILE_ID_CHAR
            print(f"\n--- TILE_ID_CHAR ({TILE_ID_CHAR_UUID}) ---")
            try:
                data = await client.read_gatt_char(TILE_ID_CHAR_UUID)
                print(f"  Value (hex): {data.hex()}")
                print(f"  This is the Tile's cloud UUID — use it to match BLE to cloud devices")
            except Exception as e:
                print(f"  Not available: {e}")

            # Try battery level (not expected to work on Tiles)
            print(f"\n--- Battery Level ({BATTERY_LEVEL_UUID}) ---")
            try:
                data = await client.read_gatt_char(BATTERY_LEVEL_UUID)
                print(f"  Battery: {data[0]}%")
            except Exception as e:
                print(f"  Not available (expected — Tiles don't expose BLE battery)")

    except Exception as e:
        print(f"Connection failed: {e}")


async def main():
    tiles = await scan_for_tiles()
    print(f"\nFound {len(tiles)} Tile device(s):")
    for t in tiles:
        print(f"  {t['address']}  RSSI={t['rssi']}  Name={t['name']}")
        print(f"    Service UUIDs: {t['service_uuids']}")
        print(f"    Manufacturer Data: {t['manufacturer_data']}")
        print(f"    Service Data: {t['service_data']}")

    for t in tiles:
        await inspect_tile(t["address"], t["name"])

    print(f"\n{'='*60}")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
