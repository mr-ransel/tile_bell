# Future Work - Tile Bell Integration

## 1. Stop Ring via BLE Disconnect

**Status**: Not started

The node-tile implementation shows that Tiles don't have a native "stop ring" command. They ring for a specified duration (default 30 seconds). However, we could potentially interrupt ringing by disconnecting the BLE connection.

**Implementation ideas**:
- Test if disconnecting mid-ring actually stops the Tile from ringing
- If it works, expose a "Stop Ring" button entity
- May need to handle reconnection gracefully for subsequent rings

**Files to modify**: `tile_device.py`

---

## 2. Button Press Detection (Tile to HA)

**Status**: Researched, not implemented

The node-tile reference implementation shows that Tiles support "TDT" (Tile Double Tab) events. When the physical button is pressed, the Tile sends a BLE notification:
- `data[0] == 0x00` = single press
- `data[0] == 0x02` = double press

**Constraints**:
- Requires a **persistent BLE connection** (drains Tile battery, limited range)
- Needs `expected_tdt_cmd_config` from the cloud API (`firmware.expected_tdt_cmd_config` field)
- Must send a TDT configuration packet after authentication (ToA message type 4)
- Feature-gated: Tile must support `ToaFeature.TDT` and firmware must not be expired
- Hub (cloud) mode only

**Potential use cases**:
- Fire HA events/automations when Tile button is pressed
- "Find my phone" equivalent — press Tile button to trigger HA notification

**Reference**: `node-tile/src/services/AbstractTileService.ts` lines 339-348

---

## 3. Extract Tile Protocol to Separate Python Library

**Status**: Not started

The Tile BLE protocol could be useful to other projects. Consider extracting into a standalone library.

**Components to extract**:
- Bluetooth connection management
- HMAC-SHA256 authentication handshake
- Command serialization (ring, volume, duration)
- Protocol constants and UUIDs

**Benefits**:
- Reusable outside Home Assistant
- Easier to test independently
- Tile Bell integration becomes a thin HA wrapper

---

## 4. Improve Battery Sensor Accuracy

**Status**: Experimental sensor implemented, accuracy unknown

The battery sensor reads `metadata.battery_state` from the Tile cloud API. It's unclear whether this is an actual measurement or an estimate based on time since battery replacement. The sensor is disabled by default.

**Things to investigate**:
- Monitor the value over time to see if it changes meaningfully
- Check if `metadata.battery_replaced_at` is used to compute battery_state
- Compare with `battery_status` field (coarse: NONE/LEVEL1/LEVEL2)
- Consider removing if the data proves unreliable

---

## 5. Older Tile Models Without TILE_ID Characteristic

**Status**: MAC-based fallback implemented, untested on older hardware

The comment at https://github.com/bachya/pytile/issues/49#issuecomment-2717862142 describes three generations of Tile MAC handling. Auto-discovery now tries MAC-based matching first (covers older tiles and PrivateID v1), then falls back to connecting and reading TILE_ID_CHAR (covers PrivateID v2). However, the MAC-based matching hasn't been tested on actual older Tile hardware. If older tiles also lack the "Tile" name in BLE advertisements, they won't be found at all.

---

## 6. macOS BLE MAC Masking

**Status**: Known limitation, no workaround

macOS replaces real BLE MAC addresses with CoreBluetooth UUIDs. This means:
- Auto-discovery on macOS-based HA instances will show CB UUIDs instead of real MACs
- The TILE_ID matching still works (it reads from BLE characteristic, not the MAC)
- Manual entry requires the user to know the real MAC (e.g., from a Linux device or nRF Connect on Android)

No action needed unless users report issues.

---

## Implementation Priority

1. **Stop Ring Experiment** (Low effort, immediate user value)
2. **Button Press Detection** (Medium effort, unique capability)
3. **Battery Accuracy** (Observation over time)
4. **Library Extraction** (High effort, long-term)
