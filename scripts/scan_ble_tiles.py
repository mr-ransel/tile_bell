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
# Tile advertised service UUIDs (see node-tile AbstractTileService.ts)
TILE_SERVICE_UUIDS = {"0000feed-0000-1000-8000-00805f9b34fb", "0000feec-0000-1000-8000-00805f9b34fb"}
SCAN_DURATION = 30


def is_tile(name: str, service_uuids: list[str]) -> bool:
    """Check if a BLE device is a Tile by service UUID or name."""
    if set(str(u).lower() for u in service_uuids) & TILE_SERVICE_UUIDS:
        return True
    return "tile" in name.lower()


async def scan_for_tiles():
    """Scan for Tile BLE devices by service UUID.

    Uses a long scan window (60s) because Tiles advertise infrequently (~30s intervals).
    Identifies Tiles by their advertised service UUIDs (feed/feec), not just by name.
    """
    print(f"Scanning for {SCAN_DURATION}s (Tiles advertise infrequently, be patient)...")
    tiles = {}
    devices = await BleakScanner.discover(timeout=SCAN_DURATION, return_adv=True)
    for d, adv in devices.values():
        name = d.name or adv.local_name or ""
        if is_tile(name, adv.service_uuids or []):
            tiles[d.address] = {
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
            }
    return list(tiles.values())


async def inspect_tile(address: str, name: str) -> bool:
    """Connect to a Tile and dump all services/characteristics.

    Retries connection up to 3 times since Tiles are only briefly connectable
    around their advertisement windows. Returns True if connected successfully.
    """
    print(f"\n{'='*60}")
    print(f"Connecting to {name or '(no name)'} ({address})...")
    for attempt in range(1, 4):
        try:
            await _inspect_tile_inner(address)
            return True
        except Exception as e:
            print(f"  Attempt {attempt}/3 failed: {e}")
            if attempt < 3:
                print(f"  Retrying in 5s...")
                await asyncio.sleep(5)
    print(f"  Gave up connecting to {name or '(no name)'}")
    return False


async def _inspect_tile_inner(address: str):
    """Inner connection logic for inspect_tile."""
    try:
        async with BleakClient(address, timeout=30.0) as client:
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
        raise


async def main():
    all_tiles = {}
    failed = {}

    while True:
        tiles = await scan_for_tiles()

        # Merge new results with previous scans
        for t in tiles:
            all_tiles[t["address"]] = t

        print(f"\nFound {len(all_tiles)} Tile device(s) total:")
        for t in all_tiles.values():
            print(f"  {t['address']}  RSSI={t['rssi']}  Name={t['name'] or '(no name)'}")
            print(f"    Service UUIDs: {t['service_uuids']}")
            print(f"    Manufacturer Data: {t['manufacturer_data']}")
            print(f"    Service Data: {t['service_data']}")

        # Connect to tiles that haven't been successfully inspected yet
        to_inspect = [t for t in all_tiles.values() if t["address"] not in failed or failed[t["address"]]]
        for t in to_inspect:
            success = await inspect_tile(t["address"], t["name"])
            failed[t["address"]] = not success

        # Summary
        failed_tiles = [all_tiles[addr] for addr, did_fail in failed.items() if did_fail]
        succeeded = len(all_tiles) - len(failed_tiles)

        print(f"\n{'='*60}")
        print(f"Results: {succeeded} connected, {len(failed_tiles)} failed, {len(all_tiles)} total found")
        if failed_tiles:
            print(f"\nFailed to connect:")
            for t in failed_tiles:
                print(f"  {t['address']}  Name={t['name'] or '(no name)'}")

        options = []
        options.append("[r] Rescan for devices (finds new tiles + retries failed)")
        if failed_tiles:
            options.append("[c] Retry failed connections only (no rescan)")
        options.append("[q] Quit")

        try:
            choice = input("\nWhat would you like to do?\n"
                           + "".join(f"  {o}\n" for o in options)
                           + "> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice == "r":
            continue
        elif choice == "c" and failed_tiles:
            for t in failed_tiles:
                success = await inspect_tile(t["address"], t["name"])
                failed[t["address"]] = not success
            continue
        else:
            break

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
