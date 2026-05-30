# Changelog

All notable changes to **lsdisplay**. This is the canonical upstream changelog;
`debian/changelog` tracks Debian packaging only.

## Unreleased

* tests: add a version-consistency guard that fails if the version sources
  (`setup.py`, `__version__`, man `.TH`, `debian/changelog`, this file) diverge.
* docs(man): use an ISO date (`YYYY-MM-DD`) in the `.TH` line.

## 0.2.2 — 2026-05-29

* Pass `xrandr --current` to both the `--properties` and `--verbose` queries so
  xrandr returns the current configuration without polling for hardware
  changes — this avoids lsdisplay altering the display configuration as a side
  effect, and speeds up execution ~2–3×. (Thanks to Vincent Danjean, PR #4.)
  A `--currrent` typo (three r's) in the `--verbose` call was fixed in a
  follow-up so the EDID-block parser keeps working.
* Declare the license as the SPDX expression `GPL-2.0-or-later` and drop the
  deprecated `License :: OSI Approved ::` classifier. (Thanks to Vincent
  Danjean, PR #5.)

## 0.2.1 — 2026-05-18

* `debian/control`: bump minimum Python from 3.6 to 3.7 to match `setup.py`'s
  `python_requires=">=3.7"` (the code uses f-strings and dataclasses; the 3.6
  entry was a stale leftover).
* README: installation example uses the exact `.deb` filename instead of an
  `X.Y.Z` placeholder. Refresh the docstring example date.
* Cleanup: move `RELEASING.md`, old `.deb`/`.bak`/`debian_backup` and other
  internal notes to a local `.info/` directory (not shipped).

## 0.2.0 — 2026-05-17

* Add CLI override management (CRUD): `--override-list`, `--override-add`
  (interactive wizard), `--override-set` (with `--override-model` /
  `--override-diagonal` / `--override-note`), and `--override-remove`. The
  wizard reads detected displays, derives the `MFG_ID+product_code_hex` key,
  and prompts for new values with sensible defaults from the current EDID.
* Refactor: extract a `_save_overrides()` helper so all write paths share the
  same persistence logic. Document the new commands in the argparse epilog.

## 0.1.4 — 2026-05-15

* Packaging regression fix (introduced in 0.1.3): install the man page
  (`debian/lsdisplay.manpages`) and `README.md` (`debian/lsdisplay.docs`), add
  a Debian-format `debian/copyright`, and move the `/usr/bin/lsdisplay` symlink
  from a postinst hack to `debian/lsdisplay.links`. Fix the maintainer name
  `Aprin` → `APRIN`.

## 0.1.3 — 2026-05-15

* Replace the row-banding layout renderer with a 2D character canvas: portrait
  monitors whose y-range straddles two stacked landscape monitors are now drawn
  correctly (previously three disjoint horizontal bands). Box edges are
  computed from absolute coordinates, eliminating spurious `||` artifacts
  between perfectly-adjacent displays. (Reported by bigbob.)
* Lower `debhelper-compat` from 13 to 11 so the source package builds out of
  the box on Ubuntu 22.04 LTS. (Reported by bigbob, issue #2.)

## 0.1.2 — 2026-05-14

* Add the SPDX license header (`GPL-2.0-or-later`).
* EDID DTD sanity check: prefer the coarse size (bytes 21-22) when the DTD
  diagonal exceeds 2× the coarse diagonal — fixes ~8" displays appearing as 59"
  when the DTD field contains pixels instead of millimetres (e.g. SGN L01N8A,
  BOE panels). (Reported by Blaise on LinuxFr.org.)

## 0.1.1 — 2026-05-03

* Initial release: EDID parsing (manufacturer, model, serial); ASCII layout
  diagram with correct proportions; Smart-TV network scan (`--scan`); override
  file for incorrect EDID data; refresh-rate display; colour output with
  `--no-color`; `--list-priority` with GPU mapping; `--connected-only`.
