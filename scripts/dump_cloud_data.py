#!/usr/bin/env python3
"""Dump all Tile cloud API data for debugging.

Shows all fields returned by the API including battery info,
firmware versions, and metadata. Useful for understanding what
data the cloud provides for each device.

Usage:
    pip install pytile aiohttp
    python dump_cloud_data.py
"""

import asyncio
import sys

from aiohttp import ClientSession
import pytile

from tile_env import get_credentials


async def main():
    email, password = get_credentials()

    print(f"\nConnecting to Tile API...")

    async with ClientSession() as session:
        api = await pytile.async_login(email, password, session)
        tiles = await api.async_get_tiles()

    if not tiles:
        print("No Tile devices found.")
        sys.exit(1)

    for tile_id, tile in tiles.items():
        if str(tile.uuid).startswith("p!"):
            continue

        print(f"\n{'='*60}")
        print(f"{tile.name} (uuid={tile.uuid})")
        print(f"{'='*60}")

        result = tile._tile_data.get("result", {})
        for key in sorted(result.keys()):
            val = result[key]
            # Highlight battery-related fields
            if "batt" in key.lower() or "power" in key.lower():
                print(f"  ** {key}: {val}")
            else:
                print(f"  {key}: {val}")

        # Show pytile's computed attributes
        print(f"\n  --- pytile attributes ---")
        for attr in ("battery_level", "firmware_version", "hardware_version",
                      "kind", "dead", "lost", "visible", "ring_state"):
            try:
                print(f"  {attr}: {getattr(tile, attr)}")
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
