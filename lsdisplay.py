#!/usr/bin/env python3
"""
lsdisplay - List connected displays with details and layout diagram.

Similar to lsusb, lspci, lscpu but for screens/monitors.
Reads EDID from /sys/class/drm for manufacturer, model, serial number.
Uses xrandr (or kscreen-doctor/wlr-randr on Wayland) for resolution and layout.

Usage:
    lsdisplay              List all displays with ASCII layout
    lsdisplay --json       Output as JSON
    lsdisplay --no-layout  Skip the layout diagram
    lsdisplay --short      Compact one-line-per-display output

License: GPL-2.0
"""

import argparse
import json as json_mod
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple

__version__ = "0.1.0"

# PNP manufacturer IDs (subset of the official PNP ID registry)
PNP_MANUFACTURERS = {
    "AAC": "AcerView", "ACR": "Acer", "AOC": "AOC", "AUS": "ASUS",
    "BNQ": "BenQ", "CMN": "Chimei Innolux", "DEL": "Dell",
    "ENC": "Eizo", "FUS": "Fujitsu Siemens", "GSM": "LG (GoldStar)",
    "HPN": "HP", "HWP": "HP", "IVM": "Iiyama", "LEN": "Lenovo",
    "LGD": "LG Display", "MAX": "Maxdata", "MEI": "Panasonic",
    "MEL": "Mitsubishi", "NEC": "NEC", "PHL": "Philips",
    "SAM": "Samsung", "SDC": "Samsung Display", "SNY": "Sony",
    "SHP": "Sharp", "TSB": "Toshiba", "VSC": "ViewSonic",
    "HSD": "HannStar", "BOE": "BOE", "AUO": "AU Optronics",
    "INL": "InnoLux", "MSI": "MSI", "GBT": "Gigabyte",
}


# Color support
_use_color = True

def _init_color(no_color_flag: bool):
    global _use_color
    _use_color = not no_color_flag and sys.stdout.isatty()

def _c(text: str, code: str) -> str:
    """Wrap text in ANSI color if color is enabled."""
    if _use_color:
        return f"\033[{code}m{text}\033[0m"
    return text

def green(text: str) -> str:
    return _c(text, "32")

def red(text: str) -> str:
    return _c(text, "31")

def yellow(text: str) -> str:
    return _c(text, "33")


@dataclass
class Display:
    """Represents a connected display."""
    name: str               # xrandr output name (e.g. HDMI-A-2)
    drm_path: str = ""      # /sys/class/drm entry
    width: int = 0          # resolution width in pixels
    height: int = 0         # resolution height in pixels
    x: int = 0              # position x
    y: int = 0              # position y
    rotation: str = ""      # left, right, inverted, normal
    primary: bool = False
    connector: str = ""     # HDMI, DisplayPort, eDP, VGA
    manufacturer_id: str = ""
    manufacturer: str = ""
    model: str = ""
    serial: str = ""
    width_mm: int = 0
    height_mm: int = 0
    diagonal_inches: float = 0.0
    refresh_rate: float = 0.0

    def __post_init__(self):
        # Determine connector type from name
        if self.name.startswith("HDMI"):
            self.connector = "HDMI"
        elif self.name.startswith("DP") or self.name.startswith("DisplayPort"):
            self.connector = "DisplayPort"
        elif self.name.startswith("eDP"):
            self.connector = "eDP"
        elif self.name.startswith("VGA"):
            self.connector = "VGA"
        elif self.name.startswith("DVI"):
            self.connector = "DVI"
        elif self.name.startswith("USB"):
            self.connector = "USB-C"


def _load_overrides():
    """Load display overrides from ~/.config/lsdisplay/overrides.json."""
    home = os.environ.get("HOME", os.path.expanduser("~"))
    paths = [
        os.path.join(home, ".config/lsdisplay/overrides.json"),
        os.path.expanduser("~/.config/lsdisplay/overrides.json"),
        "/etc/lsdisplay/overrides.json",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p) as f:
                    data = json_mod.load(f)
                return {k: v for k, v in data.items() if not k.startswith("_")}
            except Exception:
                pass
    return {}

_OVERRIDES = None

def get_overrides():
    global _OVERRIDES
    if _OVERRIDES is None:
        _OVERRIDES = _load_overrides()
    return _OVERRIDES


def parse_edid(data: bytes) -> dict:
    """Parse EDID binary data and extract manufacturer, model, serial."""
    if len(data) < 128:
        return {}

    # Manufacturer ID (bytes 8-9), encoded as 3x5-bit ASCII
    m1, m2 = data[8], data[9]
    c1 = chr(((m1 >> 2) & 0x1F) + 64)
    c2 = chr(((m1 & 0x3) << 3 | (m2 >> 5)) + 64)
    c3 = chr((m2 & 0x1F) + 64)
    mfg_id = c1 + c2 + c3

    # Product code (bytes 10-11)
    product_code = data[10] | (data[11] << 8)

    # Serial number (bytes 12-15)
    serial_num = data[12] | (data[13] << 8) | (data[14] << 16) | (data[15] << 24)

    # Physical size from detailed timing descriptors (mm precision)
    width_mm = 0
    height_mm = 0
    name = ""
    serial_str = ""

    for i in range(4):
        offset = 54 + i * 18
        if offset + 18 > len(data):
            break
        # Detailed timing descriptor (not a display descriptor)
        if data[offset] != 0 or data[offset + 1] != 0:
            # Physical size in mm from detailed timing
            w = data[offset + 12] | ((data[offset + 14] & 0xF0) << 4)
            h = data[offset + 13] | ((data[offset + 14] & 0x0F) << 8)
            if w > 0 and h > 0 and width_mm == 0:
                width_mm = w
                height_mm = h
        else:
            # Display descriptor
            tag = data[offset + 3]
            raw = data[offset + 5:offset + 18]
            text = raw.decode("ascii", errors="replace").strip().rstrip("\n").rstrip("\r")
            if tag == 0xFC:  # Monitor name
                name = text
            elif tag == 0xFF:  # Serial string
                serial_str = text

    # Fallback to bytes 21-22 (cm) if no detailed timing found
    if width_mm == 0:
        width_mm = data[21] * 10
        height_mm = data[22] * 10

    result = {
        "manufacturer_id": mfg_id,
        "manufacturer": PNP_MANUFACTURERS.get(mfg_id, mfg_id),
        "model": name,
        "serial": serial_str if serial_str else str(serial_num) if serial_num else "",
        "product_code": product_code,
        "width_mm": width_mm,
        "height_mm": height_mm,
    }

    # Apply overrides if available
    key = f"{mfg_id}{product_code:04X}"
    overrides = get_overrides()
    if key in overrides:
        ov = overrides[key]
        if "model" in ov:
            result["model"] = ov["model"]
        if "diagonal" in ov:
            result["diagonal_override"] = ov["diagonal"]
        if "serial" in ov:
            result["serial"] = ov["serial"]

    return result


def read_edid_for_output(output_name: str) -> dict:
    """Read EDID data from /sys/class/drm for a given output name."""
    drm_dir = "/sys/class/drm"
    if not os.path.isdir(drm_dir):
        return {}

    for entry in os.listdir(drm_dir):
        if output_name in entry:
            edid_path = os.path.join(drm_dir, entry, "edid")
            if os.path.exists(edid_path):
                try:
                    with open(edid_path, "rb") as f:
                        data = f.read()
                    if len(data) >= 128:
                        return parse_edid(data)
                except (IOError, PermissionError):
                    pass
    return {}


def get_displays_xrandr() -> List[Display]:
    """Get display information using xrandr."""
    try:
        output = subprocess.check_output(["xrandr"], text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    displays = []
    pattern = re.compile(
        r"^(\S+) connected\s*(primary)?\s*(\d+)x(\d+)\+(\d+)\+(\d+)\s*"
        r"(left|right|inverted|normal)?\s*"
        r"(?:\(.*?\))?\s*"
        r"(?:.*?(\d+)mm x (\d+)mm)?"
    )

    lines = output.split("\n")
    for idx, line in enumerate(lines):
        m = pattern.match(line)
        if m:
            name = m.group(1)
            d = Display(name=name)
            d.primary = m.group(2) is not None
            d.width = int(m.group(3))
            d.height = int(m.group(4))
            d.x = int(m.group(5))
            d.y = int(m.group(6))
            d.rotation = m.group(7) or "normal"

            # Parse refresh rate from mode lines following the connected line
            # Look for a line with the current resolution and a rate marked with *
            for mode_idx in range(idx + 1, len(lines)):
                mode_line = lines[mode_idx]
                # Stop at the next output line
                if mode_line and not mode_line.startswith(" "):
                    break
                # Look for refresh rate with * (current mode)
                rate_match = re.search(r'(\d+\.\d+)\*', mode_line)
                if rate_match:
                    d.refresh_rate = float(rate_match.group(1))
                    break

            if m.group(8) and m.group(9):
                d.width_mm = int(m.group(8))
                d.height_mm = int(m.group(9))
                import math
                diag_mm = math.sqrt(d.width_mm ** 2 + d.height_mm ** 2)
                d.diagonal_inches = round(diag_mm / 25.4)

            # Read EDID for better info
            edid = read_edid_for_output(name)
            if edid:
                d.manufacturer_id = edid.get("manufacturer_id", "")
                d.manufacturer = edid.get("manufacturer", "")
                d.model = edid.get("model", "")
                d.serial = edid.get("serial", "")
                # Use EDID dimensions if more precise
                # Override diagonal if available, otherwise use EDID dimensions
                if "diagonal_override" in edid:
                    d.diagonal_inches = edid["diagonal_override"]
                else:
                    edid_w = edid.get("width_mm", 0)
                    edid_h = edid.get("height_mm", 0)
                    if edid_w > 0 and edid_h > 0:
                        d.width_mm = edid_w
                        d.height_mm = edid_h
                        import math
                        d.diagonal_inches = round(math.sqrt(edid_w**2 + edid_h**2) / 25.4)

            displays.append(d)

    return displays


def get_displays_kscreen() -> List[Display]:
    """Fallback: get display info using kscreen-doctor (KDE Wayland)."""
    try:
        output = subprocess.check_output(
            ["kscreen-doctor", "--outputs"], text=True, stderr=subprocess.DEVNULL
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    displays = []
    current = None
    for line in output.split("\n"):
        m = re.match(r"Output:\s*\d+\s+(\S+)", line)
        if m:
            if current:
                displays.append(current)
            current = Display(name=m.group(1))
        if current:
            if "enabled" in line:
                pass  # connected and enabled
            if "Geometry:" in line:
                gm = re.search(r"(\d+),(\d+)\s+(\d+)x(\d+)", line)
                if gm:
                    current.x = int(gm.group(1))
                    current.y = int(gm.group(2))
                    current.width = int(gm.group(3))
                    current.height = int(gm.group(4))
            if "Rotation:" in line:
                rm = re.search(r"Rotation:\s*(\d+)", line)
                if rm:
                    rot_map = {0: "normal", 1: "normal", 2: "left", 4: "inverted", 8: "right"}
                    current.rotation = rot_map.get(int(rm.group(1)), "normal")
            if "primary" in line.lower():
                current.primary = True

    if current:
        displays.append(current)

    # Enrich with EDID
    for d in displays:
        edid = read_edid_for_output(d.name)
        if edid:
            d.manufacturer_id = edid.get("manufacturer_id", "")
            d.manufacturer = edid.get("manufacturer", "")
            d.model = edid.get("model", "")
            d.serial = edid.get("serial", "")

    return displays


def get_displays() -> List[Display]:
    """Get displays using the best available method."""
    displays = get_displays_xrandr()
    if not displays:
        displays = get_displays_kscreen()
    return displays


def get_gpu_mapping() -> dict:
    """Map DRM card outputs to GPU info."""
    gpus = {}
    drm_dir = "/sys/class/drm"
    if not os.path.isdir(drm_dir):
        return gpus

    for entry in sorted(os.listdir(drm_dir)):
        # Match card0, card1, card2
        m = re.match(r"^(card\d+)$", entry)
        if m:
            card = m.group(1)
            card_path = os.path.join(drm_dir, card)
            device_link = os.path.join(card_path, "device")

            # Get GPU name via lspci
            gpu_name = ""
            try:
                pci_addr = os.path.basename(os.readlink(device_link))
                lspci_out = subprocess.check_output(
                    ["lspci", "-s", pci_addr], text=True, stderr=subprocess.DEVNULL
                ).strip()
                gpu_name = re.sub(r"^[0-9a-f:.]+\s+\S+\s+\S+\s+controller:\s*", "", lspci_out, flags=re.IGNORECASE)
            except (OSError, subprocess.CalledProcessError):
                pass

            # Find connected outputs for this card
            outputs = []
            for sub in sorted(os.listdir(drm_dir)):
                if sub.startswith(card + "-"):
                    port = sub[len(card) + 1:]
                    status_path = os.path.join(drm_dir, sub, "status")
                    edid_path = os.path.join(drm_dir, sub, "edid")
                    connected = False
                    try:
                        with open(status_path) as f:
                            connected = f.read().strip() == "connected"
                    except (IOError, PermissionError):
                        pass
                    if not connected:
                        try:
                            connected = os.path.getsize(edid_path) > 0
                        except OSError:
                            pass
                    outputs.append({"port": port, "connected": connected})

            gpus[card] = {"name": gpu_name, "outputs": outputs}

    return gpus


def print_gpus(gpus: dict, displays: List[Display]):
    """Print GPU information with output mapping."""
    print("GRAPHICS CARDS")
    print("=" * 14)
    print()

    for card in sorted(gpus.keys()):
        info = gpus[card]
        print(f"  {card}: {yellow(info['name'])}")
        for out in info["outputs"]:
            port = out["port"]
            if out["connected"]:
                # Find matching display
                match = ""
                for d in displays:
                    if d.name == port:
                        mfg = d.manufacturer or d.manufacturer_id
                        diag = f' {d.diagonal_inches:.0f}"' if d.diagonal_inches else ""
                        match = f" ← {mfg} {d.model}{diag}"
                        break
                print(f"    └─ {port}: {green('connected')}{match}")
            else:
                print(f"    └─ {port}: {red('-')}")
        print()


def print_table(displays: List[Display]):
    """Print displays in a formatted table."""
    print("CONNECTED DISPLAYS")
    print("=" * 18)
    print()
    for d in displays:
        primary = green(" [PRIMARY]") if d.primary else ""
        rot = f" rot={d.rotation}" if d.rotation and d.rotation != "normal" else ""
        diag = f'{d.diagonal_inches:.0f}"' if d.diagonal_inches else ""
        hz = f"{d.refresh_rate:.0f}Hz" if d.refresh_rate else ""
        # Éviter "Samsung SAMSUNG" → juste "Samsung"
        model = d.model if d.model.upper() != d.manufacturer.upper() else ""
        mfg_model = f"{d.manufacturer} {model}".strip()
        serial = d.serial if d.serial else ""

        pos = f"{d.width}x{d.height}+{d.x}+{d.y}"
        padded_name = d.name.ljust(12)
        name_col = green(padded_name) if d.primary else padded_name
        printf_fmt = f"  {name_col} {pos:<22s} {diag:>4s} {hz:>5s}  {mfg_model:<20s} {d.connector:<12s} S/N:{serial:<15s}{rot}{primary}"
        print(printf_fmt)

    print()
    print(f"Total: {len(displays)} display(s) connected")


def draw_layout(displays: List[Display]):
    """Draw ASCII art layout diagram with correct proportions."""
    if not displays:
        return

    print()
    print("LAYOUT")
    print("=" * 6)
    print()

    char_aspect = 2.0  # terminal character height/width ratio

    # Group by row (similar y coordinate)
    rows_groups = {}
    for d in displays:
        found = False
        for ry in rows_groups:
            if abs(d.y - ry) < 200:
                rows_groups[ry].append(d)
                found = True
                break
        if not found:
            rows_groups[d.y] = [d]

    # Global scale based on widest row
    global_min_x = min(d.x for d in displays)
    global_max_px = 0
    for group in rows_groups.values():
        row_px = max(d.x + d.width for d in group) - min(d.x for d in group)
        if row_px > global_max_px:
            global_max_px = row_px

    target_cols = min(70, shutil.get_terminal_size().columns - 4)
    px_per_col = global_max_px / target_cols if target_cols > 0 else 1

    for ry in sorted(rows_groups.keys()):
        group = sorted(rows_groups[ry], key=lambda d: d.x)

        # Build boxes
        boxes = []
        for d in group:
            label = d.name
            if d.primary and d.manufacturer_id != "SAM":
                label = d.name + "*"

            box_w = max(len(label) + 2, round(d.width / px_per_col))
            ratio_hw = d.height / d.width if d.width > 0 else 1
            box_h = max(3, round(box_w * ratio_hw / char_aspect))

            top = "+" + "-" * box_w + "+"
            empty = "|" + " " * box_w + "|"
            mid = "|" + label.center(box_w) + "|"

            box = [top]
            for r in range(box_h):
                box.append(mid if r == box_h // 2 else empty)
            box.append(top)
            boxes.append(box)

        # Render with correct x positions
        max_lines = max(len(b) for b in boxes)
        for i in range(max_lines):
            line = ""
            cursor = 0
            for d, b in zip(group, boxes):
                col_x = round((d.x - global_min_x) / px_per_col)
                if col_x > cursor:
                    line += " " * (col_x - cursor)
                    cursor = col_x
                if i < len(b):
                    line += b[i]
                    cursor += len(b[i])
                else:
                    w = len(b[0])
                    line += " " * w
                    cursor += w
            print("  " + line)
        print()


def list_priority(displays, connected_only=False):
    """List displays sorted by priority order, with all GPU outputs."""
    # Primary first, then by x position (left to right), then by y
    primary = [d for d in displays if d.primary]
    others = sorted([d for d in displays if not d.primary], key=lambda d: (d.y, d.x))
    ordered = primary + others
    connected_names = {d.name for d in displays}

    print("DISPLAY PRIORITY ORDER")
    print("=" * 21)
    print()
    for i, d in enumerate(ordered, 1):
        mfg = d.manufacturer or d.manufacturer_id
        model = d.model if d.model.upper() != mfg.upper() else ""
        diag = f'{d.diagonal_inches:.0f}"' if d.diagonal_inches else ""
        primary_tag = green(" <- PRIMARY") if d.primary else ""
        connector = d.connector
        gpu = ""
        # Find which GPU this output belongs to
        for entry in sorted(os.listdir("/sys/class/drm")):
            if d.name in entry and entry.startswith("card"):
                gpu = entry.split("-")[0]
                break
        padded_name = d.name.ljust(12)
        name_col = green(padded_name) if d.primary else padded_name
        print(f"  {i}. {name_col} {d.width}x{d.height:<6} {diag:>4s}  {mfg} {model}  [{connector}/{gpu}]{primary_tag}")

    # Show disconnected outputs if not filtered
    if not connected_only:
        gpus = get_gpu_mapping()
        disconnected = []
        for card, info in gpus.items():
            for out in info["outputs"]:
                if not out["connected"] and out["port"] not in connected_names:
                    disconnected.append((out["port"], card))
        if disconnected:
            print()
            for port, card in disconnected:
                print(f"  -  {red(port.ljust(12))} {red('disconnected'):20s} [{card}]")

    print()
    print()


def scan_network(subnet=None):
    """Scan network for Samsung SmartTVs and update overrides.json."""
    import socket
    import urllib.request
    import ipaddress

    # Determine subnet
    if not subnet:
        # Auto-detect from local IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            parts = local_ip.rsplit(".", 1)
            subnet = parts[0] + ".0/24"
        except Exception:
            subnet = "192.168.1.0/24"

    print(f"Scanning {subnet} for Smart TVs (port 8001)...")
    print()

    # Get current EDID displays for matching
    displays = get_displays()
    samsung_displays = [d for d in displays if d.manufacturer_id == "SAM"]

    # Scan each IP
    network = ipaddress.IPv4Network(subnet, strict=False)
    found_tvs = []

    for ip in network.hosts():
        ip_str = str(ip)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        result = sock.connect_ex((ip_str, 8001))
        sock.close()
        if result == 0:
            # Port 8001 open — try Samsung API
            try:
                url = f"http://{ip_str}:8001/api/v2/"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=2) as resp:
                    data = json_mod.loads(resp.read().decode("utf-8"))
                dev = data.get("device", {})
                if dev.get("type") == "Samsung SmartTV":
                    tv_info = {
                        "ip": ip_str,
                        "model": dev.get("modelName", ""),
                        "name": dev.get("name", "").replace("&quot;", '"'),
                        "resolution": dev.get("resolution", ""),
                        "mac": dev.get("wifiMac", dev.get("networkMac", "")),
                        "uuid": dev.get("id", ""),
                        "os": dev.get("OS", ""),
                        "firmware": dev.get("firmwareVersion", ""),
                    }
                    found_tvs.append(tv_info)
                    print(f"  Found: {tv_info['name']} ({tv_info['model']})")
                    print(f"         IP: {ip_str}  MAC: {tv_info['mac']}")
                    print(f"         Resolution: {tv_info['resolution']}")
                    print()
            except Exception:
                pass

    if not found_tvs:
        print("No Samsung Smart TVs found on the network.")
        return

    # Match TVs with connected EDID Samsung displays by resolution
    import re
    overrides = get_overrides()
    updated = False
    matched_displays = set()

    # Build lookup: for each Samsung display, get its EDID product code and resolution
    sam_edid_info = []
    for d in samsung_displays:
        edid = read_edid_for_output(d.name)
        if edid and edid.get("manufacturer_id") == "SAM":
            sam_edid_info.append({
                "display": d,
                "key": f"SAM{edid['product_code']:04X}",
                "res": f"{d.width}x{d.height}",
                "edid": edid,
            })

    for tv in found_tvs:
        tv_res = tv["resolution"]  # e.g. "7680x4320"
        tv_w, tv_h = 0, 0
        rm = re.match(r"(\d+)x(\d+)", tv_res)
        if rm:
            tv_w, tv_h = int(rm.group(1)), int(rm.group(2))

        # Extract diagonal from TV name (e.g. '65" Neo QLED 8K' → 65)
        diag = 0
        dm = re.search(r'(\d{2,3})"?\s', tv["name"])
        if dm:
            diag = int(dm.group(1))

        # Find best matching Samsung display by closest resolution
        best_match = None
        best_distance = float("inf")
        for info in sam_edid_info:
            if info["key"] in matched_displays:
                continue
            d = info["display"]
            d_max = max(d.width, d.height)
            tv_max = max(tv_w, tv_h)
            distance = abs(d_max - tv_max)
            if distance < best_distance:
                best_distance = distance
                best_match = info

        if best_match:
            key = best_match["key"]
            matched_displays.add(key)
            d = best_match["display"]

            overrides[key] = {
                "model": tv["model"],
                "serial": tv["mac"],
                "note": tv["name"],
            }
            if diag:
                overrides[key]["diagonal"] = diag

            updated = True
            match_type = "exact" if best_distance == 0 else f"closest (Δ{best_distance}px)"
            print(f"  Matched ({match_type}): {d.name} ({d.width}x{d.height}) ↔ {tv['name']} ({tv_res})")
            print(f"  Override: {key} → {tv['model']} diag={diag}\" MAC={tv['mac']}")
            print()
        else:
            print(f"  No matching display for: {tv['name']} ({tv_res})")
            print()

    if updated:
        overrides["_comment"] = "Auto-generated by lsdisplay --scan. Key = MFG_ID + product_code_hex"
        home = os.environ.get("HOME", os.path.expanduser("~"))
        config_dir = os.path.join(home, ".config", "lsdisplay")
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "overrides.json")
        with open(config_path, "w") as f:
            json_mod.dump(overrides, f, indent=2, ensure_ascii=False)
        print(f"Overrides saved to {config_path}")
        # Also copy to /etc if writable
        try:
            etc_dir = "/etc/lsdisplay"
            os.makedirs(etc_dir, exist_ok=True)
            import shutil as sh
            sh.copy2(config_path, os.path.join(etc_dir, "overrides.json"))
            print(f"Also copied to {etc_dir}/overrides.json")
        except PermissionError:
            pass
    else:
        print("No new overrides to save (all TVs already configured).")

    print(f"\nSummary: {len(found_tvs)} TV(s) found, {len(samsung_displays)} Samsung display(s) connected")


def main():
    parser = argparse.ArgumentParser(
        prog="lsdisplay",
        description="List connected displays with manufacturer, model, serial number, and ASCII layout diagram.",
        epilog="""examples:
  lsdisplay              list all displays with layout diagram
  lsdisplay --short      compact one-line-per-display output
  lsdisplay --json       JSON output for scripting
  lsdisplay --no-layout  skip the ASCII art diagram
  lsdisplay --scan       scan network for Smart TVs and auto-configure
  lsdisplay --list-priority  show display priority order
  lsdisplay --json | jq '.[].manufacturer'

source: https://github.com/AGuyMarc/lsdisplay
license: GPL-2.0""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json", action="store_true", help="output as JSON (for scripting)"
    )
    parser.add_argument(
        "--no-layout", action="store_true", help="skip the ASCII art layout diagram"
    )
    parser.add_argument(
        "--short", "-s", action="store_true", help="compact one-line-per-display output"
    )
    parser.add_argument(
        "--scan", nargs="?", const="auto", default=None,
        metavar="SUBNET", help="scan network for Smart TVs (default: auto-detect subnet)"
    )
    parser.add_argument(
        "--list-priority", action="store_true", help="show display priority order with GPU mapping"
    )
    parser.add_argument(
        "--connected-only", action="store_true",
        help="only show connected displays (hide disconnected outputs)"
    )
    parser.add_argument(
        "--no-color", action="store_true",
        help="disable colored output"
    )
    parser.add_argument(
        "--version", "-V", action="version", version=f"%(prog)s {__version__}"
    )
    args = parser.parse_args()

    _init_color(args.no_color)

    if args.scan:
        subnet = None if args.scan == "auto" else args.scan
        scan_network(subnet)
        return


    displays = get_displays()

    if not displays:
        print("No displays found.", file=sys.stderr)
        print("Ensure xrandr, kscreen-doctor, or wlr-randr is available.", file=sys.stderr)
        sys.exit(1)

    if args.list_priority:
        list_priority(displays, connected_only=args.connected_only)
        return

    if args.json:
        data = [asdict(d) for d in displays]
        print(json_mod.dumps(data, indent=2, ensure_ascii=False))
        return

    if args.short:
        for d in displays:
            mfg = d.manufacturer or d.manufacturer_id
            diag = f'{d.diagonal_inches:.0f}"' if d.diagonal_inches else ""
            p = "*" if d.primary else " "
            model = d.model if d.model.upper() != mfg.upper() else ""
            hz = f"@{d.refresh_rate:.0f}Hz" if d.refresh_rate else ""
            print(f"{p} {d.name:<12s} {d.width}x{d.height}{hz} {diag:>4s} {mfg} {model} [{d.connector}]")
        return

    print_table(displays)

    if not args.no_layout:
        draw_layout(displays)


if __name__ == "__main__":
    main()
