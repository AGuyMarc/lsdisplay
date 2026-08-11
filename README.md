# lsdisplay

List connected displays with details and ASCII layout diagram.

Like `lsusb`, `lspci`, `lscpu`, `lsblk`, `lsmem` — but for displays.

A useful CLI tool for Linux users and admins. Zero-dependency — just Python 3.7+ and `/sys/class/drm`. (Config-path handling follows the XDG spec more closely when the optional `pyxdg` module — Debian `python3-xdg` — is installed.)

**Companion tool:** [`lsgpu`](https://github.com/AGuyMarc/lsgpu) — list the GPUs that drive those displays (with NVIDIA/AMD stats).

## Why this exists

I built `lsdisplay` and its companion [`lsgpu`](https://github.com/AGuyMarc/lsgpu) in parallel, both for the same reason: setting up my sysadmin workstation — six monitors driven by three GPUs (two NVIDIA cards plus the Arrow Lake iGPU), one of them a 65" overview TV — and finding that no single Linux command could tell me which physical screen was driven by which output, on which card, doing what.

Try answering this concretely: *which* GPU is driving the 32" Samsung sitting in the bottom-right corner of my desk right now, and what is that card actually doing?

`lsdisplay` answers the screen-and-cable side. It identifies each physical panel and shows where it sits:

```
CONNECTED DISPLAYS
==================

  HDMI-A-2     1440x2560+1441+0        27"  75Hz  Iiyama PL2792Q       HDMI         S/N:1152032422031   rot=left [PRIMARY]
  HDMI-A-3     1440x2560+2881+0        27"  75Hz  Iiyama PL2792Q       HDMI         S/N:1152032422030   rot=left
  HDMI-A-5     5376x3024+0+2561        65"  60Hz  Samsung TQ65QN800DTXXC HDMI       S/N:94:e6:ba:dd:9a:7a
  DP-4         1440x2560+0+0           27"  75Hz  Iiyama PL2792Q       DisplayPort  S/N:1152031921274   rot=left
  HDMI-A-4     1440x2560+4322+0        27"  75Hz  Iiyama PL2793Q       HDMI         S/N:12464540C1808   rot=left
  HDMI-A-1     1920x1080+5376+2561     32"  60Hz  Samsung QE32Q50A     HDMI         S/N:bc:45:5b:e4:e8:13

Total: 6 displays connected

LAYOUT
======

  +-------------+-------------+------------+-------------+
  |             |             |            |             |
  |             |             |            |             |
  |             |             |            |             |
  |             |             |            |             |
  |             |             |            |             |
  |    DP-4     |  HDMI-A-2*  |  HDMI-A-3  |  HDMI-A-4   |
  |             |             |            |             |
  |             |             |            |             |
  |             |             |            |             |
  |             |             |            |             |
  |             |             |            |             |
  +-------------+-------------+------------+----------+-----------------+
  |                                                   |                 |
  |                                                   |    HDMI-A-1     |
  |                                                   |                 |
  |                                                   |                 |
  |                                                   +-----------------+
  |                                                   |
  |                     HDMI-A-5                      |
  |                                                   |
  |                                                   |
  |                                                   |
  |                                                   |
  |                                                   |
  |                                                   |
  |                                                   |
  +---------------------------------------------------+
```

→ the 32" Samsung in the bottom-right corner is `HDMI-A-1`.

`lsgpu` answers the silicon side. It identifies each card and shows what it is currently running:

```
GRAPHICS CARDS
==============

  card0: NVIDIA Corporation GA107 [GeForce RTX 3050 6GB] (rev a1)
         Driver: nvidia | GPU:26% MEM:4422/6144MB 48°C 27.3W
    ├─ DP-4: connected ← Iiyama PL2792Q 27"
    ├─ HDMI-A-2: connected ← Iiyama PL2792Q 27"
    ├─ HDMI-A-3: connected ← Iiyama PL2792Q 27"

  card1: NVIDIA Corporation AD106 [GeForce RTX 4060 Ti] (rev a1)
         Driver: nvidia | GPU:0% MEM:12794/16380MB 48°C 15.1W
    ├─ HDMI-A-1: connected ← Samsung QE32Q50A 32"
    Processes:
      PID 9728  ollama  12744MB

  card2: Intel Corporation Arrow Lake-S [Intel Graphics] (rev 06)
         Driver: i915
    ├─ HDMI-A-4: connected ← Iiyama PL2793Q 27"
    ├─ HDMI-A-5: connected ← Samsung TQ65QN800DTXXC 65"

Total: 3 GPUs, 6 outputs connected
```

→ `HDMI-A-1` lives on `card1`, the RTX 4060 Ti, currently pinned by Ollama with 12.7 GB of VRAM. The three Iiyama 27" on the top row are all driven by `card0` (RTX 3050 6 GB); the fourth 27" and the 65" overview TV come straight out of the Intel Arrow Lake iGPU (`card2`).

Together they tell the whole story: the screen in front of me, the cable behind it, the card driving it, and what that card is doing right now. That's the workflow `lsdisplay` exists for — and zero-dependency Python is what makes it work on the locked-down sysadmin boxes where I actually need it.

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
sudo dpkg -i lsdisplay_0.2.1-1_all.deb
```

The package installs `/usr/bin/lsdisplay`, the man page `lsdisplay(1)`, and documentation.

### Arch Linux / Manjaro (AUR)

Available in the AUR thanks to [@seraf1](https://aur.archlinux.org/account/seraf1):

```bash
yay -S lsdisplay-git
```

Package page: https://aur.archlinux.org/packages/lsdisplay-git

### Fedora (COPR)

Available from the [`ls-tools` COPR repository](https://copr.fedorainfracloud.org/coprs/guy-marc-aprin/ls-tools/):

```bash
sudo dnf copr enable guy-marc-aprin/ls-tools
sudo dnf install lsdisplay
```

Builds are provided for Fedora 43, 44 and rawhide (x86_64). Enabling the COPR also
gives you `lsgpus` (the companion GPU-listing tool).

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
lsdisplay                  # Full output with layout diagram
lsdisplay --short          # Compact one-line-per-display
lsdisplay --json           # JSON output for scripting
lsdisplay --no-layout      # Skip the ASCII art diagram
lsdisplay --connected-only # Hide disconnected outputs
lsdisplay --list-priority  # Display priority order with GPU mapping
lsdisplay --no-color       # Disable coloured output
lsdisplay --version        # Show version
```

### Smart TV network scan

```bash
lsdisplay --scan                 # Auto-detect the local subnet
lsdisplay --scan 192.168.1.0/24  # Scan a specific subnet
```

### Display overrides (for wrong or missing EDID)

```bash
lsdisplay --override-list        # List current overrides
lsdisplay --override-add         # Interactive wizard for a detected display
lsdisplay --override-set SAM7513 --override-model QN65QN900B --override-diagonal 65 --override-note Salon
lsdisplay --override-remove SAM7513
```

### Save or restore the config

```bash
lsdisplay --write-config           # Save overrides to your user config
lsdisplay --write-config=system    # Install overrides machine-wide (needs sudo)
lsdisplay --restore-config=system  # Copy machine config into your user config
```

### Scripting

```bash
lsdisplay --json | jq '.[].manufacturer'
```

## Configuration

Display overrides live in `overrides.json`, searched in XDG order (first match wins per key):

| Scope  | Path |
|--------|------|
| User   | `$XDG_CONFIG_HOME/lsdisplay/` (default `~/.config/lsdisplay/`) |
| System | `$XDG_CONFIG_DIRS` entries, then `/etc/xdg/lsdisplay/` — canonical system path |
| Legacy | `/etc/lsdisplay/` — **deprecated**, still read as a last-resort fallback |

Full XDG semantics need the optional `pyxdg` module; without it the fallback paths
above are used. If `/etc/lsdisplay/overrides.json` is found, a one-line deprecation
note is printed to **stderr** (stdout and `--json` stay clean). lsdisplay never moves
or writes it for you.

### Saving & restoring overrides

```bash
lsdisplay --write-config            # save current overrides to your user config
lsdisplay --write-config=system     # install them machine-wide (needs sudo)
sudo lsdisplay --write-config=system

lsdisplay --restore-config=system          # pull the machine config into your user config
lsdisplay --restore-config=~/backup.json   # import an overrides.json (e.g. a *.bak)
```

`--write-config` **pushes** your active overrides to a scope; `--restore-config`
**pulls** a config into your user scope. Both back up any existing target to
`*.bak` first. `--write-config=system` replaces the old silent `/etc` auto-copy
with an explicit, visible action.

## Example output

Compact one-line-per-display view (`lsdisplay --short`) of a six-screen
workstation — `*` marks the primary. The full table with serials plus the ASCII
layout diagram is shown in [Why this exists](#why-this-exists) above.

```
  HDMI-A-1     1920x1080@60Hz  32" Samsung QE32Q50A [HDMI]
* HDMI-A-2     1440x2560@75Hz  27" Iiyama PL2792Q [HDMI]
  HDMI-A-3     1440x2560@75Hz  27" Iiyama PL2792Q [HDMI]
  HDMI-A-5     5376x3024@60Hz  65" Samsung TQ65QN800DTXXC [HDMI]
  DP-4         1440x2560@75Hz  27" Iiyama PL2792Q [DisplayPort]
  HDMI-A-4     1440x2560@75Hz  27" Iiyama PL2793Q [HDMI]
```

## Requirements

**Required:**
- Python 3.7+
- Linux with `/sys/class/drm` (any modern kernel)

**Optional** (lsdisplay still lists every display with EDID details without them):
- `xrandr` (X11), `kscreen-doctor` (KDE Wayland) or `wlr-randr` (wlroots Wayland) — for live resolution, position and rotation
- `pyxdg` (Debian `python3-xdg`) — full `$XDG_CONFIG_HOME`/`$XDG_CONFIG_DIRS` config-path semantics

## How it works

1. Scans `/sys/class/drm/card*/edid` for raw EDID data
2. Parses EDID to extract PNP manufacturer ID, monitor name, serial number
3. Maps PNP IDs to human-readable names (Samsung, Dell, Iiyama, etc.)
4. Uses `xrandr` output for resolution, position, rotation
5. Draws ASCII art layout proportional to actual pixel dimensions

## See also

Hardware enumeration `ls*` family on Linux:

- [`lsgpu`](https://github.com/AGuyMarc/lsgpu) — GPUs (NVIDIA/AMD/Intel) with stats and output mapping (companion to this tool)
- `lscpu` — CPU architecture info
- `lspci` — PCI devices
- `lsusb` — USB devices
- `lsblk` — block devices (disks, partitions)
- `lsmem` — memory ranges
- `lsmod` — kernel modules
- `lsipc` — IPC facilities
- `lsns` — namespaces

## License

GPL-2.0. See [LICENSE](LICENSE) for the full text.
