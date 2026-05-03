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
    _load_overrides, get_overrides,
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
