# lsdisplay

List connected displays with details and ASCII layout diagram.

Like `lsusb`, `lspci`, `lscpu` — but for displays.

A useful CLI tool for Linux users and admins. Zero-dependency — just Python 3.7+ and `/sys/class/drm`.

## Features

- **EDID parsing** from `/sys/class/drm/*/edid`: manufacturer, model, serial number
- **Resolution, position, rotation** via xrandr (fallback: kscreen-doctor, wlr-randr)
- **ASCII art layout diagram** with correct proportions
- **JSON output** for scripting
- Works on X11 and Wayland (KDE, Sway, etc.)
- No external dependencies, Python 3.7+

## Installation

### Debian / Ubuntu (.deb)

Download the `.deb` from the [Releases page](https://github.com/AGuyMarc/lsdisplay/releases/latest), then:

```bash
sudo dpkg -i lsdisplay_X.Y.Z-1_all.deb
```

The package installs `/usr/bin/lsdisplay`, the man page `lsdisplay(1)`, and documentation.

### Arch Linux / Manjaro (AUR)

Available in the AUR thanks to [@seraf1](https://aur.archlinux.org/account/seraf1):

```bash
yay -S lsdisplay-git
```

Package page: https://aur.archlinux.org/packages/lsdisplay-git

### From source

```bash
git clone https://github.com/AGuyMarc/lsdisplay
cd lsdisplay

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

- Python 3.7+
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
