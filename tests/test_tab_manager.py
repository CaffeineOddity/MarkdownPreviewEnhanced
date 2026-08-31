#!/usr/bin/env python3
"""file_path ↔ view_id ↔ browser-tab generation (1:1:1 registry)."""
from __future__ import print_function

import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if "sublime" not in sys.modules:
    _sublime = types.ModuleType("sublime")
    _sublime.load_resource = lambda p: ""
    _sublime.load_binary_resource = lambda p: None
    sys.modules["sublime"] = _sublime

from mpe_core import tab_manager  # noqa: E402


class TabManagerLifecycleTests(unittest.TestCase):
    def setUp(self):
        tab_manager.reset()

    def tearDown(self):
        tab_manager.reset()

    def test_register_is_not_alive_until_tab_open(self):
        tab_manager.register("/tmp/a.md", view_id=11)
        self.assertFalse(tab_manager.is_alive("/tmp/a.md"))
        self.assertEqual(tab_manager.live_count(), 0)
        self.assertEqual(tab_manager.get_view_id_for_file("/tmp/a.md"), 11)
        self.assertEqual(tab_manager.session_count(), 1)

    def test_tab_open_marks_alive_and_assigns_gen(self):
        tab_manager.register("/tmp/a.md", view_id=11)
        result = tab_manager.tab_open("/tmp/a.md")
        self.assertTrue(tab_manager.is_alive("/tmp/a.md"))
        self.assertEqual(tab_manager.live_count(), 1)
        self.assertEqual(result["gen"], 1)
        self.assertFalse(result["replaced"])
        self.assertIsNone(result["old_gen"])
        self.assertEqual(result["files"], ["/tmp/a.md"])

    def test_second_tab_open_bumps_gen_and_reports_replaced(self):
        tab_manager.tab_open("/tmp/a.md")
        result = tab_manager.tab_open("/tmp/a.md")
        self.assertEqual(result["gen"], 2)
        self.assertTrue(result["replaced"])
        self.assertEqual(result["old_gen"], 1)
        self.assertEqual(tab_manager.live_count(), 1)

    def test_stale_tab_close_does_not_remove_new_generation(self):
        tab_manager.tab_open("/tmp/a.md")
        tab_manager.tab_open("/tmp/a.md")  # gen=2
        removed = tab_manager.tab_close("/tmp/a.md", gen=1)
        self.assertFalse(removed)
        self.assertTrue(tab_manager.is_alive("/tmp/a.md"))
        self.assertEqual(tab_manager.live_count(), 1)

    def test_matching_tab_close_removes_row(self):
        result = tab_manager.tab_open("/tmp/a.md")
        removed = tab_manager.tab_close("/tmp/a.md", gen=result["gen"])
        self.assertTrue(removed)
        self.assertFalse(tab_manager.is_alive("/tmp/a.md"))
        self.assertEqual(tab_manager.live_count(), 0)
        self.assertEqual(tab_manager.session_count(), 0)

    def test_tab_close_is_idempotent(self):
        tab_manager.tab_open("/tmp/a.md")
        self.assertTrue(tab_manager.tab_close("/tmp/a.md", gen=1))
        self.assertFalse(tab_manager.tab_close("/tmp/a.md", gen=1))
        self.assertEqual(tab_manager.live_count(), 0)

    def test_two_files_are_independent(self):
        tab_manager.tab_open("/tmp/a.md")
        tab_manager.tab_open("/tmp/b.md")
        self.assertEqual(tab_manager.live_count(), 2)
        tab_manager.tab_close("/tmp/a.md", gen=1)
        self.assertTrue(tab_manager.is_alive("/tmp/b.md"))
        self.assertEqual(tab_manager.live_count(), 1)
        self.assertEqual(tab_manager.live_files(), ["/tmp/b.md"])

    def test_empty_path_is_ignored(self):
        tab_manager.register("", view_id=1)
        self.assertEqual(tab_manager.session_count(), 0)
        result = tab_manager.tab_open("")
        self.assertIsNone(result)
        self.assertFalse(tab_manager.tab_close("", gen=1))


if __name__ == "__main__":
    unittest.main()
