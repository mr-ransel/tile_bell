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

## 4. Battery Level Reporting

**Status**: Removed — cloud data is ambiguous and unreliable

Battery sensor entities were implemented using the Tile cloud API but removed because the data was not trustworthy. All devices reported 50% at all times regardless of actual state.

**Known cloud API fields related to battery**:
- `battery_status` — Coarse enum: `NONE`, `LEVEL1`, `LEVEL2`. Meaning unclear.
- `metadata.battery_state` — String containing a percentage (e.g. `"50"`). Suspected to be a static estimate rather than a real measurement. All observed values were 50.
- `metadata.battery_replaced_at` — Timestamp. May be used to compute `battery_state` based on expected battery life rather than actual measurement.
- `last_tile_state.battery_level` — Always `0.0` in observed data. Appears unused by the Tile API.

**Standard BLE Battery Level** (characteristic `0x2A19`) is **not exposed** by Tile devices.

**To revisit**:
- Monitor `battery_status` and `metadata.battery_state` over months to see if they change
- Check whether replacing a Tile battery resets `battery_replaced_at` and changes the reported level
- Investigate whether newer firmware versions expose more accurate data
- If reliable data is found, re-add as a sensor entity (use `SensorDeviceClass.BATTERY`, disabled by default)

---

## 5. Newer Tile Hardware (ROYAL_ST1 / PrivateID v2) Ring Support

**Status**: Unsupported — blocked by deliberate anti-reverse-engineering in firmware

Newer Tile models (identified as ROYAL_ST1, hardware version 24.00, firmware 48.x) cannot be rung via BLE from Home Assistant. Older models (DIABLO, hardware 08.03, firmware 05.x) work fine.

### Test results

1. **BLE discovery works** — HA sees these tiles via `0xFEED` service UUID advertisements. Auto-discover matches them to cloud accounts correctly.
2. **BLE connection works** — `establish_connection` and plain `BleakClient` both connect successfully. Connection takes 8-15 seconds (vs ~3s for older tiles).
3. **GATT service discovery works** — Three services found:
   - `0x1801` (Generic Attribute) — no characteristics
   - `0x1800` (Generic Access) — Device Name, Appearance, Preferred Connection Parameters
   - `0xFEED` (Tile service) — contains `9d410018` (command, write-without-response) and `9d410019` (response, notify)
4. **`start_notify` fails** — Enabling notifications on the response characteristic (`9d410019`) fails with a BlueZ GATT error every time. The CCCD descriptor (`0x2902`) reports a **different random garbage handle on every connection** (observed: 46042, 10042, 3573, 23672). The actual characteristic handle is stable at 13.
5. **Pairing doesn't help** — `client.pair()` either returns None or fails; `start_notify` still fails after pairing.
6. **nRF Connect (phone) works fine** — The same tile connects, shows correct services, and allows enabling notifications from an iOS/Android phone. No bonding required.

### Suppositions

- **The randomized CCCD handle is almost certainly deliberate anti-reverse-engineering.** A real firmware bug would produce a consistent wrong handle, not random garbage on every connection. Tile appears to be intentionally returning malformed ATT `Find Information Response` data for the CCCD descriptor.
- **This targets generic BLE stacks (BlueZ, etc.) while preserving compatibility with official apps.** The official Tile app likely either hardcodes the CCCD handle or uses OS-level notification APIs that bypass descriptor discovery. BlueZ's `StartNotify` D-Bus method internally relies on the discovered descriptor handle and fails.
- **nRF Connect works because iOS/Android handle `StartNotify` at the OS BLE driver level** without relying on the reported descriptor handle from the ATT layer.
- **The older tiles (DIABLO) do not have this protection**, which is why they work fine — their CCCD handle is correctly reported.
- **MAC address randomization (PrivateID v2) on the same newer tiles is part of the same anti-third-party strategy** — it prevents MAC-based matching and forces a BLE connection to identify the device.

### Possible workarounds (not yet attempted)

- **Raw ATT socket**: Bypass BlueZ entirely, open an L2CAP socket, and write `0x0100` to handle 14 (char_handle + 1, which is where the CCCD must be per GATT spec) using raw ATT protocol. This avoids BlueZ's descriptor handle lookup.
- **`gatttool` / `bluetoothctl`**: Use command-line BLE tools from the HA host to manually write the CCCD and test if the tile accepts it at the correct handle.
- **BlueZ patch**: Modify BlueZ to ignore discovered descriptor handles and always write CCCD at char_handle + 1. Unlikely to be practical for HA users.
- **Proxy via phone**: Use a companion app on the user's phone to relay ring commands. Adds complexity but bypasses the BlueZ issue entirely.

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

1. **Newer Tile Ring Support** (High impact, blocked on BlueZ CCCD workaround — raw ATT socket most promising)
2. **Stop Ring Experiment** (Low effort, immediate user value)
3. **Button Press Detection** (Medium effort, unique capability)
4. **Battery Level Reporting** (Needs observation over time, blocked on reliable data)
5. **Library Extraction** (High effort, long-term)
