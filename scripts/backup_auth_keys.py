#!/usr/bin/env python3
"""Back up Tile device auth keys from the cloud API.

Saves device credentials to tile_backup.json so you can configure
Tile Bell in manual mode without cloud dependency.

Usage:
    pip install pytile aiohttp
    python backup_auth_keys.py
"""

import asyncio
import json
import sys
from getpass import getpass

from aiohttp import ClientSession
import pytile


async def main():
    email = input("Tile account email: ").strip()
    if not email:
        print("Error: email is required")
        sys.exit(1)

    password = getpass("Tile account password: ")
    if not password:
        print("Error: password is required")
        sys.exit(1)

    print(f"\nConnecting to Tile API...")

    async with ClientSession() as session:
        api = await pytile.async_login(email, password, session)
        tiles = await api.async_get_tiles()

    if not tiles:
        print("No Tile devices found on your account.")
        sys.exit(1)

    backup = {}
    for tile_id, tile in tiles.items():
        if str(tile.uuid).startswith("p!"):
            continue  # Skip phone entries
        backup[tile.name] = {
            "uuid": tile.uuid,
            "auth_key": tile._tile_data["result"]["auth_key"],
            "firmware": tile.firmware_version,
            "hardware": tile.hardware_version,
        }
        print(f"  {tile.name}: uuid={tile.uuid}")

    with open("tile_backup.json", "w") as f:
        json.dump(backup, f, indent=2)

    print(f"\nSaved {len(backup)} device(s) to tile_backup.json")
    print("Keep this file safe — it contains your auth keys for manual configuration.")


if __name__ == "__main__":
    asyncio.run(main())
