#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Guy-Marc APRIN <2026@gm.casa>
# NB: contact email rotates yearly — 2027@gm.casa in 2027, etc.
"""
lsdisplay - List connected displays with details and layout diagram.

Similar to lsusb, lspci, lscpu but for screens/monitors.
Reads EDID from /sys/class/drm for manufacturer, model, serial number.
Uses xrandr (or kscreen-doctor/wlr-randr on Wayland) for resolution and layout.

Author: Guy-Marc APRIN <2026@gm.casa>
        NB: contact email rotates yearly — 2027@gm.casa in 2027, etc.

  « La perfection est atteinte non quand il n'y a plus rien à ajouter,
    mais quand il n'y a plus rien à retirer. »
  « L'essentiel est invisible pour les yeux. »
    — Antoine de Saint-Exupéry

  "Perfection is achieved not when there is nothing more to add,
   but when there is nothing left to take away."
  "What is essential is invisible to the eye."

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
try:
    from dataclasses import dataclass, field, asdict
except ImportError:
    print("Error: Python 3.7+ is required (dataclasses module missing).", file=sys.stderr)
    print("On AlmaLinux/RHEL 8: dnf install python39 && python3.9 lsdisplay.py", file=sys.stderr)
    sys.exit(1)
from typing import List, Optional, Tuple

__version__ = "0.1.3"

def _get_version_string() -> str:
    """Build version string with build date from git or file modification time.

    Format: 0.1.0 (2026-05-07 jeu 01h15m00s)
    """
    import locale
    try:
        locale.setlocale(locale.LC_TIME, "fr_FR.UTF-8")
    except locale.Error:
        pass

    # Try git commit date first
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ts = subprocess.check_output(
            ["git", "log", "-1", "--format=%ct"], text=True,
            stderr=subprocess.DEVNULL, cwd=script_dir
        ).strip()
        from datetime import datetime
        dt = datetime.fromtimestamp(int(ts))
    except Exception:
        # Fallback: file modification time
        try:
            from datetime import datetime
            mtime = os.path.getmtime(__file__)
            dt = datetime.fromtimestamp(mtime)
        except Exception:
            return __version__

    day_name = dt.strftime("%a").lower().rstrip(".")
    date_str = dt.strftime(f"%Y-%m-%d {day_name} %Hh%Mm%Ss")
    return f"{__version__} ({date_str})"

# PNP manufacturer IDs (subset of the official PNP ID registry)
# Source: https://uefi.org/PNP_ID_List
# History: https://github.com/onkoe/pnpid/blob/main/list.csv
# See also: /usr/share/hwdata/pnp.ids (hwdata package)
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
    """Disable ANSI colors when --no-color is set or stdout is not a terminal."""
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
        # Infer connector type from the DRM output name prefix (e.g. "HDMI-A-2" → "HDMI")
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
    """Load display overrides from ~/.config/lsdisplay/overrides.json.

    Searches user config dir then /etc; first file found wins.
    Keys starting with "_" (e.g. _comment) are stripped from the result.
    """
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

_OVERRIDES = None  # lazy-loaded singleton

def get_overrides():
    """Return cached overrides dict (loaded once on first call)."""
    global _OVERRIDES
    if _OVERRIDES is None:
        _OVERRIDES = _load_overrides()
    return _OVERRIDES


def parse_edid(data: bytes) -> dict:
    """Parse EDID binary data and extract manufacturer, model, serial."""
    if len(data) < 128:
        return {}

    # EDID bytes 8-9: manufacturer ID encoded as three 5-bit chars (A=1 .. Z=26)
    # packed into 16 bits: [0AAAAA BBBBB CCCCC]. Add 64 to get ASCII uppercase.
    m1, m2 = data[8], data[9]
    c1 = chr(((m1 >> 2) & 0x1F) + 64)          # bits 14..10 of the 16-bit word
    c2 = chr(((m1 & 0x3) << 3 | (m2 >> 5)) + 64)  # bits 9..5
    c3 = chr((m2 & 0x1F) + 64)                 # bits 4..0
    mfg_id = c1 + c2 + c3

    # EDID bytes 10-11: product code (little-endian 16-bit)
    product_code = data[10] | (data[11] << 8)

    # EDID bytes 12-15: serial number (little-endian 32-bit)
    serial_num = data[12] | (data[13] << 8) | (data[14] << 16) | (data[15] << 24)

    # Parse the four 18-byte descriptor blocks starting at byte 54
    width_mm = 0
    height_mm = 0
    name = ""
    serial_str = ""

    for i in range(4):
        offset = 54 + i * 18
        if offset + 18 > len(data):
            break
        # Non-zero first two bytes = detailed timing descriptor (pixel clock present)
        if data[offset] != 0 or data[offset + 1] != 0:
            # Extract physical size: byte+12 = low 8 bits of width_mm,
            # byte+14 upper nibble = high 4 bits; same pattern for height
            w = data[offset + 12] | ((data[offset + 14] & 0xF0) << 4)
            h = data[offset + 13] | ((data[offset + 14] & 0x0F) << 8)
            if w > 0 and h > 0 and width_mm == 0:
                width_mm = w
                height_mm = h
        else:
            # Display descriptor: byte+3 is the tag type
            tag = data[offset + 3]
            raw = data[offset + 5:offset + 18]  # 13-byte ASCII payload
            text = raw.decode("ascii", errors="replace").strip().rstrip("\n").rstrip("\r")
            if tag == 0xFC:  # Monitor name descriptor
                name = text
            elif tag == 0xFF:  # Monitor serial string descriptor
                serial_str = text

    # Sanity check: some cheap displays put pixel dimensions in the DTD mm fields
    # (e.g. 800x1280 pixels reported as 800x1280 mm = 59" instead of 8").
    # Also catch unreasonably large values (> 2000mm = ~80").
    # In these cases, prefer the coarse size from bytes 21-22.
    coarse_w = data[21] * 10  # cm -> mm
    coarse_h = data[22] * 10
    if width_mm > 0 and coarse_w > 0 and coarse_h > 0:
        import math
        dtd_diag = math.sqrt(width_mm**2 + height_mm**2) / 25.4
        coarse_diag = math.sqrt(coarse_w**2 + coarse_h**2) / 25.4
        # If DTD diagonal is more than 2x the coarse diagonal, DTD is bogus
        if dtd_diag > 2 * coarse_diag and coarse_diag > 0:
            width_mm = coarse_w
            height_mm = coarse_h

    # Fallback: bytes 21-22 give coarse physical size in centimeters
    if width_mm == 0:
        width_mm = coarse_w
        height_mm = coarse_h

    result = {
        "manufacturer_id": mfg_id,
        "manufacturer": PNP_MANUFACTURERS.get(mfg_id, mfg_id),
        "model": name,
        "serial": serial_str if serial_str else str(serial_num) if serial_num else "",
        "product_code": product_code,
        "width_mm": width_mm,
        "height_mm": height_mm,
    }

    # Apply overrides keyed by "MFG_ID + product_code_hex" (e.g. "SAM0A3E")
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


def _build_connector_id_map() -> dict:
    """Build a mapping of connector_id -> sysfs EDID path.

    Each /sys/class/drm/card*-*/connector_id file contains an integer that
    matches the CONNECTOR_ID property exposed by xrandr (modesetting/i915/amdgpu).
    This allows us to link xrandr output names (e.g. DP-1-3) to the correct
    sysfs entry (e.g. card0-DP-5) even when names differ (MST hubs, evdi/DisplayLink).
    """
    drm_dir = "/sys/class/drm"
    cid_map = {}
    if not os.path.isdir(drm_dir):
        return cid_map
    for entry in os.listdir(drm_dir):
        cid_path = os.path.join(drm_dir, entry, "connector_id")
        if os.path.exists(cid_path):
            try:
                with open(cid_path) as f:
                    cid = f.read().strip()
                edid_path = os.path.join(drm_dir, entry, "edid")
                if os.path.exists(edid_path):
                    cid_map[cid] = edid_path
            except (IOError, PermissionError):
                pass
    return cid_map

_CONNECTOR_ID_MAP = None  # lazy singleton

def _get_connector_id_map() -> dict:
    global _CONNECTOR_ID_MAP
    if _CONNECTOR_ID_MAP is None:
        _CONNECTOR_ID_MAP = _build_connector_id_map()
    return _CONNECTOR_ID_MAP


def _get_xrandr_connector_ids() -> dict:
    """Parse xrandr --properties to extract CONNECTOR_ID per output.

    Returns a dict: {"DP-1-3": "42", "eDP-1": "51", ...}
    Only available with modesetting/i915/amdgpu DDX; NVIDIA proprietary
    driver does not expose this property.
    """
    try:
        output = subprocess.check_output(
            ["xrandr", "--properties"], text=True, stderr=subprocess.DEVNULL
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}

    result = {}
    current_output = None
    for line in output.split("\n"):
        # Output header: "DP-1-3 connected primary 1920x1080+0+0 ..."
        m = re.match(r"^(\S+)\s+(?:connected|disconnected)", line)
        if m:
            current_output = m.group(1)
        # Property line: "\tCONNECTOR_ID: 42"
        elif current_output and "CONNECTOR_ID" in line:
            cm = re.search(r"CONNECTOR_ID:\s*(\d+)", line)
            if cm:
                result[current_output] = cm.group(1)
    return result

_XRANDR_CONNECTOR_IDS = None  # lazy singleton

def _get_xrandr_connector_ids_cached() -> dict:
    global _XRANDR_CONNECTOR_IDS
    if _XRANDR_CONNECTOR_IDS is None:
        _XRANDR_CONNECTOR_IDS = _get_xrandr_connector_ids()
    return _XRANDR_CONNECTOR_IDS


def _parse_xrandr_edid_blocks() -> dict:
    """Parse EDID hex blocks from xrandr --verbose as a last-resort fallback.

    Returns a dict: {"DP-1-3": bytes, "eDP-1": bytes, ...}
    Some drivers (Intel/AMD) expose EDID through xrandr properties.
    """
    try:
        output = subprocess.check_output(
            ["xrandr", "--verbose"], text=True, stderr=subprocess.DEVNULL
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}

    result = {}
    current_output = None
    edid_lines = []
    in_edid = False

    for line in output.split("\n"):
        m = re.match(r"^(\S+)\s+(?:connected|disconnected)", line)
        if m:
            # Save previous EDID block if any
            if current_output and edid_lines:
                hex_str = "".join(edid_lines)
                try:
                    result[current_output] = bytes.fromhex(hex_str)
                except ValueError:
                    pass
            current_output = m.group(1)
            edid_lines = []
            in_edid = False
        elif "EDID:" in line:
            in_edid = True
            edid_lines = []
        elif in_edid:
            stripped = line.strip()
            if re.match(r"^[0-9a-fA-F]+$", stripped) and len(stripped) == 32:
                edid_lines.append(stripped)
            else:
                in_edid = False

    # Don't forget the last output
    if current_output and edid_lines:
        hex_str = "".join(edid_lines)
        try:
            result[current_output] = bytes.fromhex(hex_str)
        except ValueError:
            pass

    return result

_XRANDR_EDID_BLOCKS = None  # lazy singleton

def _get_xrandr_edid_blocks() -> dict:
    global _XRANDR_EDID_BLOCKS
    if _XRANDR_EDID_BLOCKS is None:
        _XRANDR_EDID_BLOCKS = _parse_xrandr_edid_blocks()
    return _XRANDR_EDID_BLOCKS


def read_edid_for_output(output_name: str) -> dict:
    """Read and parse EDID for a display output, trying multiple strategies:

    1. CONNECTOR_ID: match xrandr CONNECTOR_ID property to sysfs connector_id
    2. Exact name match: look for /sys/class/drm/card*-<output_name>/edid
    3. xrandr --verbose: parse EDID hex blocks from xrandr properties
    """
    drm_dir = "/sys/class/drm"

    # Strategy 1: CONNECTOR_ID mapping (works for MST hubs, evdi/DisplayLink)
    xrandr_cids = _get_xrandr_connector_ids_cached()
    if output_name in xrandr_cids:
        cid_map = _get_connector_id_map()
        cid = xrandr_cids[output_name]
        if cid in cid_map:
            try:
                with open(cid_map[cid], "rb") as f:
                    data = f.read()
                if len(data) >= 128:
                    return parse_edid(data)
            except (IOError, PermissionError):
                pass

    # Strategy 2: exact sysfs name match (e.g. "card0-HDMI-A-2" ends with "-HDMI-A-2")
    if os.path.isdir(drm_dir):
        suffix = "-" + output_name
        for entry in os.listdir(drm_dir):
            if entry.endswith(suffix):
                edid_path = os.path.join(drm_dir, entry, "edid")
                if os.path.exists(edid_path):
                    try:
                        with open(edid_path, "rb") as f:
                            data = f.read()
                        if len(data) >= 128:
                            return parse_edid(data)
                    except (IOError, PermissionError):
                        pass

    # Strategy 3: EDID from xrandr --verbose (last resort)
    edid_blocks = _get_xrandr_edid_blocks()
    if output_name in edid_blocks:
        data = edid_blocks[output_name]
        if len(data) >= 128:
            return parse_edid(data)

    return {}


def get_displays_xrandr() -> List[Display]:
    """Get display information using xrandr."""
    try:
        output = subprocess.check_output(["xrandr"], text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    displays = []
    # Parse xrandr "connected" lines, e.g.:
    #   HDMI-A-2 connected primary 2560x1440+0+0 normal (…) 597mm x 336mm
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

            # Scan indented mode lines below this output for the active refresh rate
            # (marked with * by xrandr, e.g. "59.95*+")
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

            # Enrich with EDID data (manufacturer, model, serial, precise dimensions)
            edid = read_edid_for_output(name)
            if edid:
                d.manufacturer_id = edid.get("manufacturer_id", "")
                d.manufacturer = edid.get("manufacturer", "")
                d.model = edid.get("model", "")
                d.serial = edid.get("serial", "")
                # Prefer override diagonal (from --scan), then EDID mm, then xrandr mm
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


def get_displays_wlr() -> List[Display]:
    """Get display info using wlr-randr (wlroots-based compositors: Sway, Hyprland, etc.)."""
    try:
        output = subprocess.check_output(["wlr-randr"], text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    displays = []
    current = None
    for line in output.split("\n"):
        # Non-indented line starts a new output block: e.g. 'DP-1 "Manufacturer Model"'
        m = re.match(r"^(\S+)\s+", line)
        if m and not line.startswith(" "):
            if current:
                displays.append(current)
            current = Display(name=m.group(1))
        if current and line.startswith("  "):
            stripped = line.strip()
            # Position: 1880,0
            pm = re.match(r"Position:\s*(\d+),(\d+)", stripped)
            if pm:
                current.x = int(pm.group(1))
                current.y = int(pm.group(2))
            # Physical size: 597x336 mm
            sm = re.match(r"Physical size:\s*(\d+)x(\d+)\s*mm", stripped)
            if sm:
                current.width_mm = int(sm.group(1))
                current.height_mm = int(sm.group(2))
                import math
                current.diagonal_inches = round(
                    math.sqrt(current.width_mm**2 + current.height_mm**2) / 25.4
                )
            # wlr-randr uses degrees; map to xrandr-style rotation names
            tm = re.match(r"Transform:\s*(\S+)", stripped)
            if tm:
                t = tm.group(1)
                rot_map = {"normal": "normal", "90": "left", "180": "inverted", "270": "right"}
                current.rotation = rot_map.get(t, "normal")
            # Mode line with "(current)" suffix is the active mode
            mm = re.match(r"(\d+)x(\d+)\s+px,\s*([\d.]+)\s*Hz\s*\(.*current", stripped)
            if mm:
                current.width = int(mm.group(1))
                current.height = int(mm.group(2))
                current.refresh_rate = float(mm.group(3))
            # Drop disabled outputs entirely
            em = re.match(r"Enabled:\s*no", stripped)
            if em:
                current = None

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
                # kscreen-doctor uses bitmask values: 1=normal, 2=left, 4=inverted, 8=right
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
    """Detect displays via the best available backend.

    Strategy: if WAYLAND_DISPLAY is set, try wlr-randr (wlroots) then
    kscreen-doctor (KDE Plasma). Fall back to xrandr (works on X11 and XWayland).
    """
    wayland = os.environ.get("WAYLAND_DISPLAY")
    if wayland:
        displays = get_displays_wlr()
        if displays:
            return displays
        displays = get_displays_kscreen()
        if displays:
            return displays
    displays = get_displays_xrandr()
    return displays


def get_gpu_mapping() -> dict:
    """Map each DRM card to its GPU name (via lspci) and list of output ports.

    Returns: {"card0": {"name": "NVIDIA ...", "outputs": [{"port": "HDMI-A-2", "connected": True}, ...]}}
    """
    gpus = {}
    drm_dir = "/sys/class/drm"
    if not os.path.isdir(drm_dir):
        return gpus

    for entry in sorted(os.listdir(drm_dir)):
        m = re.match(r"^(card\d+)$", entry)
        if m:
            card = m.group(1)
            card_path = os.path.join(drm_dir, card)
            device_link = os.path.join(card_path, "device")

            # Resolve the PCI address from the device symlink, then query lspci
            gpu_name = ""
            try:
                pci_addr = os.path.basename(os.readlink(device_link))
                lspci_out = subprocess.check_output(
                    ["lspci", "-s", pci_addr], text=True, stderr=subprocess.DEVNULL
                ).strip()
                gpu_name = re.sub(r"^[0-9a-f:.]+\s+\S+\s+\S+\s+controller:\s*", "", lspci_out, flags=re.IGNORECASE)
            except (OSError, subprocess.CalledProcessError):
                pass

            # Enumerate connector entries for this card (e.g. "card0-HDMI-A-2")
            outputs = []
            for sub in sorted(os.listdir(drm_dir)):
                if sub.startswith(card + "-"):
                    port = sub[len(card) + 1:]  # strip "card0-" prefix
                    status_path = os.path.join(drm_dir, sub, "status")
                    edid_path = os.path.join(drm_dir, sub, "edid")
                    # Check connection via status file, fall back to non-empty EDID
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
        # Avoid "Samsung SAMSUNG" redundancy: suppress model if it matches manufacturer
        model = d.model if d.model.upper() != d.manufacturer.upper() else ""
        mfg_model = f"{d.manufacturer} {model}".strip()
        serial = d.serial if d.serial else ""

        pos = f"{d.width}x{d.height}+{d.x}+{d.y}"
        padded_name = d.name.ljust(12)
        name_col = green(padded_name) if d.primary else padded_name
        printf_fmt = f"  {name_col} {pos:<22s} {diag:>4s} {hz:>5s}  {mfg_model:<20s} {d.connector:<12s} S/N:{serial:<15s}{rot}{primary}"
        print(printf_fmt)

    print()
    n = len(displays)
    print(f"Total: {n} display{'s' if n != 1 else ''} connected")


def render_layout(displays: List[Display], term_cols: int = None) -> List[str]:
    """Render the layout diagram as a list of lines (no header, no trailing blank).

    Each display is painted onto a 2D character canvas at its scaled (x, y)
    position. This correctly handles partial vertical overlaps — e.g. a
    portrait monitor on the left whose y-range straddles two stacked landscape
    monitors on the right — which a row-banding approach cannot represent.

    Larger displays are drawn first so smaller boxes paint on top: their
    corners stay visible at shared edges instead of being erased by a
    neighbour's continuous edge.
    """
    if not displays:
        return []

    char_aspect = 2.0  # terminal chars are ~2x taller than wide

    min_x = min(d.x for d in displays)
    min_y = min(d.y for d in displays)
    max_x = max(d.x + d.width for d in displays)
    max_y = max(d.y + d.height for d in displays)
    span_x = max(1, max_x - min_x)
    span_y = max(1, max_y - min_y)

    if term_cols is None:
        term_cols = shutil.get_terminal_size().columns
    target_cols = min(70, max(10, term_cols - 4))
    px_per_col = span_x / target_cols
    px_per_row = px_per_col * char_aspect

    total_cols = target_cols + 1  # +1 for the rightmost box's right edge
    total_rows = max(3, int(round(span_y / px_per_row)) + 1)

    canvas = [[" "] * total_cols for _ in range(total_rows)]

    def place(r, c, ch):
        if 0 <= r < total_rows and 0 <= c < total_cols:
            canvas[r][c] = ch

    # Largest first so smaller boxes overwrite at shared edges (keeps their
    # corners visible). Primary as tie-breaker so its label wins on identical
    # geometries.
    def order_key(d):
        return (-(d.width * d.height), 0 if d.primary else 1)

    for d in sorted(displays, key=order_key):
        label = d.name
        if d.primary and d.manufacturer_id != "SAM":
            label = d.name + "*"

        # Compute box edges from absolute coordinates so adjacent displays
        # always share a column / row (avoids 1-cell gaps from independent
        # rounding of width/height).
        col_x = int(round((d.x - min_x) / px_per_col))
        col_xr = int(round((d.x + d.width - min_x) / px_per_col))
        row_y = int(round((d.y - min_y) / px_per_row))
        row_yb = int(round((d.y + d.height - min_y) / px_per_row))
        box_w = max(len(label) + 2, col_xr - col_x)
        box_h = max(3, row_yb - row_y)

        # Clamp to canvas
        if col_x + box_w >= total_cols:
            box_w = max(3, total_cols - col_x - 1)
        if row_y + box_h >= total_rows:
            box_h = max(3, total_rows - row_y - 1)

        # Top and bottom edges
        for c in range(col_x, col_x + box_w + 1):
            corner = (c == col_x) or (c == col_x + box_w)
            place(row_y, c, "+" if corner else "-")
            place(row_y + box_h, c, "+" if corner else "-")
        # Left and right edges
        for r in range(row_y + 1, row_y + box_h):
            place(r, col_x, "|")
            place(r, col_x + box_w, "|")
        # Centred label on the middle interior row
        if box_h >= 3 and box_w >= 3:
            mid_r = row_y + box_h // 2
            label_text = label[: box_w - 1]
            start_c = col_x + 1 + (box_w - 1 - len(label_text)) // 2
            for i, ch in enumerate(label_text):
                place(mid_r, start_c + i, ch)

    return ["".join(row).rstrip() for row in canvas]


def draw_layout(displays: List[Display]):
    """Print the LAYOUT section to stdout."""
    if not displays:
        return
    print()
    print("LAYOUT")
    print("=" * 6)
    print()
    for line in render_layout(displays):
        print("  " + line)
    print()


def list_priority(displays, connected_only=False):
    """List displays sorted by priority: primary first, then left-to-right, top-to-bottom."""
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
    """Scan the local /24 network for Samsung SmartTVs on port 8001.

    For each TV found, queries the Samsung REST API for model/resolution/MAC,
    then matches it to a connected Samsung EDID display by closest resolution.
    Results are saved to overrides.json so future runs show TV model names.
    """
    import socket
    import urllib.request
    import ipaddress

    # Auto-detect subnet from the default route interface's IP
    if not subnet:
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

    # Probe each host on port 8001 (Samsung SmartTV WebSocket/REST API port)
    network = ipaddress.IPv4Network(subnet, strict=False)
    found_tvs = []

    for ip in network.hosts():
        ip_str = str(ip)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)  # fast fail for non-responsive hosts
        result = sock.connect_ex((ip_str, 8001))
        sock.close()
        if result == 0:
            # Port open -- query Samsung REST API at /api/v2/
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

    # Match discovered TVs to connected Samsung EDID displays by resolution proximity
    import re
    overrides = get_overrides()
    updated = False
    matched_displays = set()

    # Build lookup of connected Samsung displays with their EDID product codes
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

        # Extract diagonal size from the TV's friendly name (e.g. '65" Neo QLED 8K' -> 65)
        diag = 0
        dm = re.search(r'(\d{2,3})"?\s', tv["name"])
        if dm:
            diag = int(dm.group(1))

        # Greedy match: pick the Samsung display with the closest max dimension
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
        # Persist overrides to user config dir; also copy to /etc if writable
        overrides["_comment"] = "Auto-generated by lsdisplay --scan. Key = MFG_ID + product_code_hex"
        home = os.environ.get("HOME", os.path.expanduser("~"))
        config_dir = os.path.join(home, ".config", "lsdisplay")
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "overrides.json")
        with open(config_path, "w") as f:
            json_mod.dump(overrides, f, indent=2, ensure_ascii=False)
        print(f"Overrides saved to {config_path}")
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
        "--version", "-V", action="version", version=f"%(prog)s {_get_version_string()}"
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
