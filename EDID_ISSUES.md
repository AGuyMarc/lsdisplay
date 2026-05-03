# EDID Issues — Samsung Smart TVs

## Problem

Samsung Smart TVs report incorrect information in their EDID (Extended Display
Identification Data), making automatic identification unreliable:

| Field | Expected | Samsung reports | Impact |
|-------|----------|-----------------|--------|
| **Monitor name** | Model name (e.g. TQ65QN800DTXXC) | Generic "SAMSUNG" | Cannot identify model |
| **Serial number** | Unique per device | Same generic number (e.g. 16780800) across all TVs | Cannot distinguish two Samsung TVs |
| **Physical size** | Panel dimensions | Chassis/bezel dimensions | Incorrect diagonal calculation (65" TV reports 85") |
| **Product code** | — | Hex code (e.g. 0x7513) | No public database to map to model name |

### Example: Samsung Neo QLED 8K 65"

```
EDID bytes 21-22 (physical size):  142cm x 80cm → 85" diagonal (WRONG)
EDID detailed timing descriptor:  1872mm x 1053mm → 85" (WRONG)
Actual panel size:                 1440mm x 810mm → 65" (CORRECT)
EDID monitor name descriptor:     "SAMSUNG" (generic, not model name)
EDID serial number:                16780800 (same on all Samsung TVs tested)
```

The EDID reports the **total chassis dimensions** including bezel and stand
mounting area, not the actual display panel size. This is arguably a violation
of the EDID specification (VESA E-EDID Standard, section 3.10.2) which states
that the image size should reflect the "viewable image area."

### Affected Samsung models tested

- **TQ65QN800DTXXC** (Neo QLED 8K 65") — product code 0x7513, reports 85"
- **QE32Q50A** (Q50AE 32") — product code 0x71A5, reports 55"

### Other manufacturers

Iiyama PL2792Q and PL2793Q (27" monitors) report **correct** EDID data:
correct model name, unique serial numbers, and accurate physical dimensions.

**Note:** We have not been able to test other TV manufacturers (LG, Sony, etc.)
to determine if this is a Samsung-specific issue or an industry-wide problem
with Smart TVs.

## Workaround: `overrides.json`

`lsdisplay` supports a manual override file to correct Samsung EDID data.

### Configuration file locations (first found wins)

1. `~/.config/lsdisplay/overrides.json` (user)
2. `/etc/lsdisplay/overrides.json` (system-wide)

### Format

Key = manufacturer PNP ID (3 chars) + EDID product code (4 hex digits uppercase).

```json
{
  "_comment": "Override incorrect EDID data. Key = MFG_ID + product_code_hex",
  "SAM7513": {
    "model": "TQ65QN800DTXXC",
    "diagonal": 65,
    "serial": "94:e6:ba:dd:9a:7a",
    "note": "Samsung Neo QLED 8K 65\" Salon"
  },
  "SAM71A5": {
    "model": "QE32Q50A",
    "diagonal": 32,
    "serial": "bc:45:5b:e4:e8:13",
    "note": "Samsung Q50AE 32\" Loggia"
  }
}
```

### Automatic scan: `lsdisplay --scan`

Samsung Smart TVs expose an HTTP API on port 8001 that provides accurate
device information (model name, MAC address, resolution, firmware, etc.).

`lsdisplay --scan` exploits this to auto-populate `overrides.json`:

1. Scans the local network for devices with port 8001 open
2. Queries `http://<ip>:8001/api/v2/` on each
3. Matches network TVs with connected EDID displays by closest resolution
4. Extracts real model name, diagonal (from TV name), and MAC address
5. Writes `overrides.json` automatically

```bash
lsdisplay --scan                  # auto-detect local subnet
lsdisplay --scan 192.168.1.0/24  # scan specific subnet
```

### How to find the EDID product code for a new TV

```bash
python3 -c "
import os
for entry in os.listdir('/sys/class/drm'):
    edid_path = f'/sys/class/drm/{entry}/edid'
    if not os.path.exists(edid_path): continue
    with open(edid_path, 'rb') as f: data = f.read()
    if len(data) < 128: continue
    m1, m2 = data[8], data[9]
    mfg = chr(((m1>>2)&0x1F)+64) + chr(((m1&0x3)<<3|(m2>>5))+64) + chr((m2&0x1F)+64)
    prod = data[10] | (data[11] << 8)
    if mfg == 'SAM':
        name = ''
        for i in range(4):
            o = 54 + i*18
            if data[o]==0 and data[o+1]==0 and data[o+3]==0xFC:
                name = data[o+5:o+18].decode('ascii',errors='replace').strip()
        print(f'{entry}: SAM{prod:04X} name={name}')
"
```

## Recommendation to Samsung

Samsung could improve the user and developer experience by:

1. **Reporting the real model name** in EDID descriptor tag 0xFC (e.g.
   "TQ65QN800D" instead of "SAMSUNG")
2. **Using unique serial numbers** in EDID descriptor tag 0xFF or bytes 12-15
   (the MAC address would be a good candidate)
3. **Reporting accurate panel dimensions** in the detailed timing descriptors
   (panel size, not chassis size)
4. **Publishing a product code database** mapping EDID hex codes to model names

These are trivial firmware changes that would benefit all Linux users,
HTPC builders, media centers, and display management tools.
