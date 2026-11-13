#!/usr/bin/env python3
"""export_dir suggested export path (docs/specs/export-dir.md)."""
from __future__ import print_function

import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if "sublime" not in sys.modules:
    _sublime = types.ModuleType("sublime")
    _sublime.load_resource = lambda p: ""
    _sublime.load_binary_resource = lambda p: None
    _sublime.cache_path = lambda: "/tmp/mdpp_cache_stub"
    sys.modules["sublime"] = _sublime

from mpe_core import config  # noqa: E402


class ExportDefaultPathTests(unittest.TestCase):
    def test_empty_uses_output_dir(self):
        md = os.path.join("docs", "notes", "guide.md")
        with mock.patch.object(config, "get", return_value=""), \
                mock.patch.object(config, "output_dir", return_value="/cache/mpe"):
            got = config.export_default_path(md, ".pdf")
        self.assertEqual(got, os.path.join("/cache/mpe", "guide.pdf"))

    def test_beside_source(self):
        md = os.path.join("docs", "notes", "guide.md")
        with mock.patch.object(config, "get", return_value="beside_source"):
            got = config.export_default_path(md, ".pdf")
        self.assertEqual(got, os.path.join("docs", "notes", "guide.pdf"))

    def test_custom_dir(self):
        md = os.path.join("docs", "notes", "guide.md")
        with mock.patch.object(config, "get", return_value="/fixed/Exports"):
            got = config.export_default_path(md, ".html")
        self.assertEqual(got, os.path.join("/fixed/Exports", "guide.html"))

    def test_custom_dir_expands_user(self):
        md = os.path.join("docs", "notes", "guide.md")
        with mock.patch.object(config, "get", return_value="~/Exports"), \
                mock.patch(
                    "mpe_core.config.os.path.expanduser",
                    side_effect=lambda p: "/home/u/Exports" if p == "~/Exports" else p,
                ):
            got = config.export_default_path(md, ".html")
        self.assertEqual(got, os.path.join("/home/u/Exports", "guide.html"))

    def test_untitled_falls_back_to_output_dir(self):
        with mock.patch.object(config, "get", return_value="beside_source"), \
                mock.patch.object(config, "output_dir", return_value="/cache/mpe"):
            got = config.export_default_path(None, ".pdf")
        self.assertEqual(got, os.path.join("/cache/mpe", "export.pdf"))

    def test_untitled_with_custom_dir(self):
        with mock.patch.object(config, "get", return_value="/fixed/out"):
            got = config.export_default_path("", ".html")
        self.assertEqual(got, os.path.join("/fixed/out", "export.html"))


if __name__ == "__main__":
    unittest.main()
