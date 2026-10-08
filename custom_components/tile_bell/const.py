"""Constants for the Tile Bell integration."""

DOMAIN = "tile_bell"

# Tile Bluetooth service UUIDs used for advertisement identification
# See: node-tile/src/services/AbstractTileService.ts
TILE_FEED_SERVICE_UUID = "0000feed-0000-1000-8000-00805f9b34fb"
TILE_FEEC_SERVICE_UUID = "0000feec-0000-1000-8000-00805f9b34fb"
TILE_ADVERTISED_UUIDS = {TILE_FEED_SERVICE_UUID, TILE_FEEC_SERVICE_UUID}

# Tile Bluetooth characteristic UUIDs
TILE_COMMAND_UUID = "9d410018-35d6-f4dd-ba60-e7bd8dc491c0"
TILE_RESPONSE_UUID = "9d410019-35d6-f4dd-ba60-e7bd8dc491c0"
TILE_ID_CHAR_UUID = "9d410007-35d6-f4dd-ba60-e7bd8dc491c0"

# Command constants
# Based on node-tile: sendRinger uses SongTransaction(2, volume_bytes + duration)
CMD_RING_BASE = [5, 2]  # Base ring command, volume and duration will be appended

# Volume constants (based on node-tile TileVolume.ts)
VOLUME_LOW = [1, 1]      # TileVolume.LOW
VOLUME_MEDIUM = [1, 2]   # TileVolume.MED
VOLUME_HIGH = [1, 3]     # TileVolume.HIGH
VOLUME_AUTO = [22, 3, 3] # TileVolume.AUTO

VOLUME_OPTIONS = {
    "low": {"name": "Low", "bytes": VOLUME_LOW},
    "medium": {"name": "Medium", "bytes": VOLUME_MEDIUM},
    "high": {"name": "High", "bytes": VOLUME_HIGH},
    "auto": {"name": "Auto", "bytes": VOLUME_AUTO}
}

# NOTE: CMD_STOP_RING removed - protocol doesn't support stop, only duration-based ringing
# NOTE: Standard BLE Battery Level (00002a19) is NOT exposed by Tile devices.
# Cloud API has battery fields but they appear unreliable. See FUTURE_WORK.md.
