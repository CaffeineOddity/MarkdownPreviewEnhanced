#!/usr/bin/env python3
"""跨文件标题链接保留 #fragment (issue #22, docs/specs/link-fragment-anchor.md)."""
from __future__ import print_function

import os
import sys
import tempfile
import types
import unittest
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if "sublime" not in sys.modules:
    _sublime = types.ModuleType("sublime")
    _sublime.load_resource = lambda p: ""
    _sublime.load_binary_resource = lambda p: None
    sys.modules["sublime"] = _sublime

from mpe_core.md_renderer import render, rewrite_link_hrefs  # noqa: E402


def _a(href):
    return '<a href="%s">x</a>' % href


def _file_url(path):
    return "/?file=%s" % quote(path, safe="")


class LinkFragmentTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.doc_dir = os.path.join(self.root, "sub")
        os.makedirs(self.doc_dir)
        self.other = os.path.join(self.root, "other.md")
        open(self.other, "w", encoding="utf-8").write("# Target\n")
        self.same = os.path.join(self.doc_dir, "main.md")
        open(self.same, "w", encoding="utf-8").write("# Main\n")
        open(os.path.join(self.root, "notes.txt"), "w").write("txt\n")

    def tearDown(self):
        self._tmp.cleanup()

    def rewrite(self, href):
        return rewrite_link_hrefs(_a(href), self.doc_dir, mode="server")

    def test_md_link_keeps_unicode_fragment(self):
        html = self.rewrite("../other.md#字色")
        self.assertIn(_file_url(self.other) + "#字色", html)
        self.assertNotIn("/doc/", html)

    def test_md_link_keeps_ascii_fragment(self):
        html = self.rewrite("../other.md#hello-world")
        self.assertIn(_file_url(self.other) + "#hello-world", html)

    def test_md_link_without_fragment_unchanged(self):
        html = self.rewrite("../other.md")
        self.assertIn(_file_url(self.other) + '"', html)

    def test_same_document_link_keeps_fragment(self):
        html = self.rewrite("main.md#字色")
        self.assertIn(_file_url(self.same) + "#字色", html)

    def test_non_md_link_keeps_fragment_under_doc(self):
        html = self.rewrite("../notes.txt#L10")
        self.assertIn('href="/doc/notes.txt#L10"', html)

    def test_dict_link_with_fragment_uses_entry_doc(self):
        pkg = os.path.join(self.doc_dir, "pkg")
        os.makedirs(pkg)
        entry = os.path.join(pkg, "README.md")
        open(entry, "w", encoding="utf-8").write("# Dir\n")
        html = self.rewrite("pkg#part")
        self.assertIn(_file_url(entry) + "#part", html)

    def test_in_page_anchor_untouched(self):
        html = self.rewrite("#字色")
        self.assertEqual(html, _a("#字色"))

    def test_http_link_with_fragment_untouched(self):
        html = self.rewrite("https://example.com/a#b")
        self.assertIn('href="https://example.com/a#b"', html)

    def test_md_link_with_fragment_gets_no_target_blank(self):
        self.assertNotIn("target=", self.rewrite("../other.md#字色"))

    def test_file_mode_keeps_html(self):
        html = rewrite_link_hrefs(_a("../other.md#字色"), self.doc_dir, mode="file")
        self.assertEqual(html, '<a href="../other.md#字色">x</a>')


class RenderedAnchorTests(unittest.TestCase):
    """markdown 链接 → HTML 的整链路：目标文档的标题 id 与链接 fragment 一致。"""

    def test_rendered_link_matches_heading_id(self):
        with tempfile.TemporaryDirectory() as d:
            other = os.path.join(d, "other.md")
            with open(other, "w", encoding="utf-8") as f:
                f.write("## 字色\n")
            body_html = render(
                "[字色](other.md#字色)\n",
                base_dir=d,
                strip_yaml=False,
                enable_math=False,
                enable_emoji=False,
                enable_task_lists=False,
                enable_toc=False,
            )["body_html"]
            self.assertIn(_file_url(other) + "#字色", body_html)

    def test_target_heading_keeps_unicode_id(self):
        html = render(
            "## 字色\n",
            strip_yaml=False,
            enable_math=False,
            enable_emoji=False,
            enable_task_lists=False,
            enable_toc=False,
        )["body_html"]
        self.assertIn('id="字色"', html)


if __name__ == "__main__":
    unittest.main()
