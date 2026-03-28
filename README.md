# Tile Bell - Home Assistant Custom Component

Ring your Tile Bluetooth trackers directly from Home Assistant via BLE -- no Tile app required.

## Credit

This integration builds upon the reverse engineering work done in [jeretile](https://github.com/jeremad/jeretile) by Jeremy Adam and [node-tile](https://github.com/lesleyxyz/node-tile) by lesleyxyz. The Bluetooth protocol implementation is adapted from their work.

## Features

- **Ring button** -- Ring any Tile device on demand from HA
- **Volume control** -- Select Low, Medium, High, or Auto volume
- **Duration control** -- Set ring duration from 1-60 seconds
- **Battery sensor** (experimental) -- Battery percentage from Tile cloud API (hub mode only, disabled by default)
- **Auto-discovery** -- Scan for nearby Tiles and auto-match them to your cloud account
- **Manual fallback** -- Enter BLE MAC and auth key directly if auto-discovery doesn't work
- **Device merging** -- Tile Bell entities merge with the native HA Tile integration's devices
- **Availability tracking** -- Entities show as unavailable when the Tile is out of Bluetooth range

## Installation

### HACS

1. Open HACS in Home Assistant
2. Click the three-dot menu and select **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Click **Download**
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/tile_bell` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to **Settings > Devices & Services > Add Integration**
4. Search for **Tile Bell**

## Setup

### Option 1: Tile Account Hub (Recommended)

This is the recommended setup. It connects to your Tile cloud account to retrieve device auth keys, enables auto-discovery of nearby Tiles, and provides battery level reporting.

1. Add the integration and choose **Tile Account Hub**
2. Enter your Tile account email and password
3. After the hub is created, click **Add Device** on the integration card
4. Choose **Auto-Discover Nearby Tiles** or **Enter MAC Address Manually**
5. If using auto-discover, select the Tile you want to add from the list

You can repeat steps 3-5 to add more devices. Already-configured devices are automatically excluded from discovery results, so each run gets faster.

### Option 2: Manual Configuration (No Cloud)

For users who don't want to use cloud credentials, or for Tiles whose auth keys are already known.

1. Add the integration and choose **Manual MAC Address & Auth Key**
2. Enter the device name, BLE MAC address, and auth key

This mode does not provide battery level reporting or auto-discovery since those require cloud access.

## Entities

Each configured Tile device gets these entities:

| Entity | Type | Description |
|--------|------|-------------|
| Ring | Button | Press to ring the Tile |
| Ring Volume | Select | Low, Medium, High, or Auto |
| Ring Duration | Number | 1-60 seconds (default 30) |
| Battery | Sensor | Battery percentage (hub mode only, experimental, disabled by default) |

## Tips and Troubleshooting

### Auto-Discovery Not Finding Your Tiles

Auto-discovery works by scanning for BLE devices named "Tile" that Home Assistant can see, connecting to each one, and reading an internal ID to match it to your cloud account. This can take a few minutes.

If your Tiles don't show up:

- Make sure the Tile is powered on and within Bluetooth range of your HA instance
- Check that HA's Bluetooth integration is working (Settings > Devices & Services > Bluetooth)
- Use a BLE scanner app like **nRF Connect** on your phone to verify the Tile is advertising and note its MAC address
- If you can see the Tile in nRF Connect but auto-discovery still fails, use **Enter MAC Address Manually** instead and provide the MAC address from nRF Connect

### Ring Is Slow

Ringing requires establishing a new BLE connection, authenticating, and sending the command. Tiles can be slow to connect -- ring times of up to 15 seconds are not unusual. This is a limitation of the Tile BLE protocol, not the integration.

### Ring Not Working

- The Tile must be within Bluetooth range at the time you press the Ring button
- If the ring is very quiet, the Tile's battery may be nearly dead -- the speaker gets weak before the battery fully dies
- Check HA logs with debug logging enabled (see below)

### Battery Sensor (Experimental)

The battery sensor is disabled by default. You can enable it from the entity's settings in HA. Battery data comes from the Tile cloud API and is only available in hub mode. It refreshes every 24 hours to avoid rate limiting. The accuracy of this data is uncertain -- Tile may estimate battery based on time since replacement rather than actual measurement. The sensor won't appear for manually-configured devices since there's no cloud data source.

### Device Merging with Native Tile Integration

If you also have the native HA Tile integration installed, Tile Bell devices will automatically merge with the corresponding Tile devices in the device registry. Both integrations' entities will appear under a single device. This requires that the Tile was added via the hub flow (so the cloud Tile UUID is known).

### Debug Logging

```yaml
logger:
  default: info
  logs:
    custom_components.tile_bell: debug
```

## Backing Up Auth Keys (Future-Proofing)

If Tile ever discontinues their cloud service, you can still use your Tiles as ringers by providing the auth keys manually. Use this script to extract and save your auth keys while the cloud API is still available:

```python
import asyncio
import json
from aiohttp import ClientSession
from pytile import async_login

async def main():
    async with ClientSession() as session:
        api = await async_login("your_email@example.com", "your_password", session)
        tiles = await api.async_get_tiles()

        backup = {}
        for tile in tiles.values():
            if str(tile.uuid).startswith("p!"):
                continue  # Skip phone entries
            backup[tile.name] = {
                "uuid": tile.uuid,
                "auth_key": tile._tile_data["result"]["auth_key"],
                "firmware": tile.firmware_version,
                "hardware": tile.hardware_version,
            }
            print(f"{tile.name}: uuid={tile.uuid}, auth_key=<saved>")

        with open("tile_backup.json", "w") as f:
            json.dump(backup, f, indent=2)
        print(f"\nSaved {len(backup)} device(s) to tile_backup.json")

asyncio.run(main())
```

Install dependencies with `pip install pytile aiohttp`, then run the script. Store `tile_backup.json` somewhere safe. With the BLE MAC address (from nRF Connect or auto-discovery) and the auth key from the backup, you can configure Tile Bell in manual mode without any cloud dependency.

## How It Works

1. **Discovery** -- Uses the Tile cloud API (via `pytile`) to retrieve device auth keys, then scans nearby BLE devices and reads their Tile ID characteristic to match them
2. **Connection** -- Uses Home Assistant's Bluetooth integration and `bleak-retry-connector` for reliable BLE connections
3. **Authentication** -- HMAC-SHA256 handshake with the Tile device over BLE
4. **Ring** -- Sends the ring command with configurable volume and duration
5. **Battery** -- Periodically fetches battery percentage from the Tile cloud API (every 24 hours)

## Requirements

- Home Assistant 2024.3 or newer (for config subentry support)
- Bluetooth LE adapter accessible to Home Assistant
- Tile devices within Bluetooth range
- Python packages (installed automatically): `bleak-retry-connector`, `cryptography`, `pytile`

## Acknowledgments

- [Jeremy Adam](https://github.com/jeremad) for [jeretile](https://github.com/jeremad/jeretile)
- [lesleyxyz](https://github.com/lesleyxyz) for [node-tile](https://github.com/lesleyxyz/node-tile)
- The `pytile` library maintainers
- The Home Assistant community

## License

MIT License -- see the LICENSE file for details.
