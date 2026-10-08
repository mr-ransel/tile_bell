#!/usr/bin/env python3
"""Raw BLE scan — dump ALL devices seen, no filtering.

Use this to check if a device is visible to your Mac's BLE stack at all.
Look for your device by RSSI (closest = strongest signal) or service UUIDs.
"""

import asyncio
from bleak import BleakScanner

SCAN_DURATION = 30


async def main():
    print(f"Raw scanning for {SCAN_DURATION}s (no filters)...")
    devices = await BleakScanner.discover(timeout=SCAN_DURATION, return_adv=True)

    # Sort by RSSI (strongest first)
    entries = []
    for d, adv in devices.values():
        name = d.name or adv.local_name or ""
        uuids = [str(u) for u in (adv.service_uuids or [])]
        svc_data = {str(k): v.hex() for k, v in (adv.service_data or {}).items()}
        mfr_data = {k: v.hex() for k, v in (adv.manufacturer_data or {}).items()}
        entries.append((adv.rssi, d.address, name, uuids, svc_data, mfr_data))

    entries.sort(key=lambda x: x[0], reverse=True)

    print(f"\n{len(entries)} devices found (sorted by signal strength):\n")

    # Highlight anything with "feed" or "feec" in service UUIDs
    for rssi, addr, name, uuids, svc_data, mfr_data in entries:
        is_tile = any("feed" in u or "feec" in u for u in uuids)
        marker = " <-- TILE" if is_tile else ""
        print(f"  RSSI={rssi:4d}  {addr}  Name={name or '(none)'}{marker}")
        if uuids:
            print(f"           Service UUIDs: {uuids}")
        if svc_data:
            print(f"           Service Data: {svc_data}")
        if mfr_data:
            print(f"           Manufacturer Data: {mfr_data}")


if __name__ == "__main__":
    asyncio.run(main())
