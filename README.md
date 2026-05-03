# lsdisplay

List connected displays with details and ASCII layout diagram.

Like `lsusb`, `lspci`, `lscpu` — but for displays.

## Features

- **EDID parsing** from `/sys/class/drm/*/edid`: manufacturer, model, serial number
- **Resolution, position, rotation** via xrandr (fallback: kscreen-doctor, wlr-randr)
- **ASCII art layout diagram** with correct proportions
- **JSON output** for scripting
- Works on X11 and Wayland (KDE, Sway, etc.)
- No external dependencies, Python 3.6+

## Installation

```bash
# System-wide
sudo cp lsdisplay.py /usr/local/bin/lsdisplay
sudo chmod +x /usr/local/bin/lsdisplay

# Or user-local
cp lsdisplay.py ~/.local/bin/lsdisplay
chmod +x ~/.local/bin/lsdisplay
```

## Usage

```bash
lsdisplay              # Full output with layout diagram
lsdisplay --short      # Compact one-line-per-display
lsdisplay --json       # JSON output for scripting
lsdisplay --no-layout  # Skip the ASCII art diagram
lsdisplay --version    # Show version
```

## Example output

```
CONNECTED DISPLAYS
==================

  HDMI-A-2     1440x2560+1441+0        27"  75Hz  Iiyama PL2792Q   HDMI         S/N:1152032422031   rot=left
  DP-4         1440x2560+0+0           27"  75Hz  Iiyama PL2792Q   DisplayPort  S/N:1152031921274   rot=left [PRIMARY]
  HDMI-A-5     5376x3024+0+2561        65"  60Hz  Samsung QN800D   HDMI         S/N:16780800

Total: 3 display(s) connected

LAYOUT
======

  +--------------+ +--------------+
  |              | |              |
  |     DP-4*    | |   HDMI-A-2   |
  |              | |              |
  +--------------+ +--------------+

  +------------------------------+
  |                              |
  |          HDMI-A-5            |
  |                              |
  +------------------------------+
```

## Requirements

- Python 3.6+
- Linux with `/sys/class/drm` (any modern kernel)
- `xrandr` (X11) or `kscreen-doctor` (KDE Wayland) or `wlr-randr` (wlroots Wayland)

## How it works

1. Scans `/sys/class/drm/card*/edid` for raw EDID data
2. Parses EDID to extract PNP manufacturer ID, monitor name, serial number
3. Maps PNP IDs to human-readable names (Samsung, Dell, Iiyama, etc.)
4. Uses `xrandr` output for resolution, position, rotation
5. Draws ASCII art layout proportional to actual pixel dimensions

## License

GPL-2.0. See [LICENSE](LICENSE) for the full text.
