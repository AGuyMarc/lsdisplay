#!/usr/bin/env python3
"""Tests unitaires pour lsdisplay."""
import json
import os
import subprocess
import sys
import unittest

# Ajouter le dossier parent au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lsdisplay import (
    parse_edid, PNP_MANUFACTURERS, Display,
    _load_overrides, get_overrides, render_layout,
)


class TestPNPManufacturers(unittest.TestCase):
    def test_known_manufacturers(self):
        self.assertEqual(PNP_MANUFACTURERS["SAM"], "Samsung")
        self.assertEqual(PNP_MANUFACTURERS["IVM"], "Iiyama")
        self.assertEqual(PNP_MANUFACTURERS["DEL"], "Dell")

    def test_manufacturer_count(self):
        self.assertGreater(len(PNP_MANUFACTURERS), 20)


class TestParseEdid(unittest.TestCase):
    def test_empty_data(self):
        self.assertEqual(parse_edid(b""), {})

    def test_short_data(self):
        self.assertEqual(parse_edid(b"\x00" * 50), {})

    def test_minimal_edid(self):
        # Build a minimal 128-byte EDID
        edid = bytearray(128)
        # Header
        edid[0:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
        # Manufacturer "SAM" = S=19, A=1, M=13
        # S=19: bits 6-2 of byte 8 = 10011
        # A=1:  bits 1-0 of byte 8 + bits 7-5 of byte 9 = 00 001
        # M=13: bits 4-0 of byte 9 = 01101
        edid[8] = 0b01001100  # SAM
        edid[9] = 0b00101101
        # Product code
        edid[10] = 0x13
        edid[11] = 0x75
        # Physical size 142cm x 80cm
        edid[21] = 142
        edid[22] = 80
        result = parse_edid(bytes(edid))
        self.assertEqual(result["manufacturer_id"], "SAM")
        self.assertEqual(result["manufacturer"], "Samsung")
        self.assertEqual(result["product_code"], 0x7513)


class TestDisplay(unittest.TestCase):
    def test_connector_detection_hdmi(self):
        d = Display(name="HDMI-A-2")
        self.assertEqual(d.connector, "HDMI")

    def test_connector_detection_dp(self):
        d = Display(name="DP-4")
        self.assertEqual(d.connector, "DisplayPort")

    def test_connector_detection_edp(self):
        d = Display(name="eDP-1")
        self.assertEqual(d.connector, "eDP")

    def test_connector_detection_vga(self):
        d = Display(name="VGA-1")
        self.assertEqual(d.connector, "VGA")


class TestOverrides(unittest.TestCase):
    def test_load_nonexistent(self):
        result = _load_overrides()
        # May or may not find a file, but should not crash
        self.assertIsInstance(result, dict)

    def test_comment_filtered(self):
        overrides = get_overrides()
        for key in overrides:
            self.assertFalse(key.startswith("_"), f"Key {key} should be filtered")


class TestRenderLayout(unittest.TestCase):
    """Tests for the 2D-canvas layout renderer (regression for v0.1.3)."""

    def _label_row(self, lines, label):
        for i, ln in enumerate(lines):
            if label in ln:
                return i
        raise AssertionError(f"label {label!r} not found in:\n" + "\n".join(lines))

    def _next_horiz_edge(self, lines, start_row):
        """First row at index >= start_row that looks like a horizontal box
        edge: contains '+' corners and many '-' segments."""
        for i in range(start_row, len(lines)):
            if "+" in lines[i] and lines[i].count("-") > 10:
                return i
        return None

    def test_empty_returns_empty(self):
        self.assertEqual(render_layout([]), [])

    def test_single_display_renders_box(self):
        d = Display(name="DP-1", width=2560, height=1440, x=0, y=0, primary=True)
        lines = render_layout([d], term_cols=80)
        self.assertTrue(any("DP-1" in ln for ln in lines))
        self.assertTrue(lines[0].startswith("+") and lines[0].endswith("+"))
        self.assertTrue(lines[-1].startswith("+") and lines[-1].endswith("+"))

    def test_portrait_straddles_two_stacked_landscapes(self):
        """Bigbob case: HDMI-A-1 portrait on the left must vertically overlap
        BOTH stacked Samsung monitors (DP-2 top, DP-1 bottom). Regression for
        the row-banding bug fixed in v0.1.3 — the old algo rendered three
        disjoint horizontal bands with HDMI alone in the middle."""
        ds = [
            Display(name="HDMI-A-1", width=1080, height=1920, x=0, y=733),
            Display(name="DP-1", width=5120, height=1440, x=1080, y=1440,
                    primary=True, manufacturer_id="SAM"),
            Display(name="DP-2", width=5120, height=1440, x=1080, y=0,
                    manufacturer_id="SAM"),
        ]
        lines = render_layout(ds, term_cols=80)
        r_d2 = self._label_row(lines, "DP-2")
        r_h = self._label_row(lines, "HDMI-A-1")
        r_d1 = self._label_row(lines, "DP-1")
        # HDMI's label is vertically between DP-2 and DP-1 labels
        self.assertLess(r_d2, r_h)
        self.assertLess(r_h, r_d1)
        # DP-2 and DP-1 must share their horizontal edge: there must be a
        # single horizontal edge row between their labels (NOT two with a
        # blank gap, which is what the old banding algo produced).
        edge_row = self._next_horiz_edge(lines, r_d2 + 1)
        self.assertIsNotNone(edge_row, "no shared edge row found between DP-2 and DP-1")
        self.assertLess(edge_row, r_d1)
        # Row right after edge_row must be interior of DP-1 (few dashes),
        # not another horizontal edge — proves there's no gap band.
        interior = lines[edge_row + 1] if edge_row + 1 < len(lines) else ""
        self.assertLess(interior.count("-"), 5,
                        f"expected DP-1 interior right after shared edge at row "
                        f"{edge_row}, got another edge: {interior!r}")

    def test_dual_stacked_share_boundary(self):
        ds = [
            Display(name="DP-1", width=5120, height=1440, x=0, y=0,
                    primary=True, manufacturer_id="SAM"),
            Display(name="DP-2", width=5120, height=1440, x=0, y=1440,
                    manufacturer_id="SAM"),
        ]
        lines = render_layout(ds, term_cols=80)
        r_d1 = self._label_row(lines, "DP-1")
        r_d2 = self._label_row(lines, "DP-2")
        self.assertLess(r_d1, r_d2)
        edge_row = self._next_horiz_edge(lines, r_d1 + 1)
        self.assertIsNotNone(edge_row)
        self.assertLess(edge_row, r_d2)
        interior = lines[edge_row + 1] if edge_row + 1 < len(lines) else ""
        self.assertLess(interior.count("-"), 5,
                        "two horizontal edges in a row means there's a gap band")

    def test_horizontal_row_no_double_pipe(self):
        """Adjacent displays with touching x-coords must not render '||'
        between them (regression for cumulative rounding error)."""
        ds = [
            Display(name="DP-1", width=1920, height=1080, x=0, y=0),
            Display(name="DP-2", width=1920, height=1080, x=1920, y=0, primary=True),
            Display(name="DP-3", width=1920, height=1080, x=3840, y=0),
        ]
        lines = render_layout(ds, term_cols=80)
        for ln in lines:
            self.assertNotIn("||", ln,
                             f"adjacent boxes should share an edge, got: {ln!r}")


class TestCLI(unittest.TestCase):
    """Test CLI invocations."""

    def _run(self, *args):
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lsdisplay.py")
        return subprocess.run(
            [sys.executable, script] + list(args),
            capture_output=True, text=True, timeout=10
        )

    def test_help(self):
        r = self._run("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("lsdisplay", r.stdout)

    def test_version(self):
        r = self._run("--version")
        self.assertEqual(r.returncode, 0)
        self.assertIn("1.", r.stdout)

    def test_json_output(self):
        r = self._run("--json")
        if r.returncode == 0:
            data = json.loads(r.stdout)
            self.assertIsInstance(data, list)

    def test_short_output(self):
        r = self._run("--short")
        if r.returncode == 0:
            self.assertGreater(len(r.stdout), 0)

    def test_no_layout(self):
        r = self._run("--no-layout")
        if r.returncode == 0:
            self.assertNotIn("LAYOUT", r.stdout)

    def test_no_color(self):
        r = self._run("--no-layout", "--no-color")
        if r.returncode == 0:
            self.assertNotIn("\033[", r.stdout)


if __name__ == "__main__":
    unittest.main()
