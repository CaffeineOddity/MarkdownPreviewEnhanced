#!/usr/bin/env python3
"""导出 HTML 本地图片 base64 内嵌 (specs/export-base64-images.md)."""
from __future__ import print_function

import base64
import os
import sys
import tempfile
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

from mpe_core.html_builder import build_export_html, embed_local_images  # noqa: E402


def _write_png(path):
    """1x1 红色 PNG."""
    raw = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4"
        "z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    )
    with open(path, "wb") as f:
        f.write(raw)


class EmbedLocalImagesTests(unittest.TestCase):
    def test_relative_file_embedded(self):
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "a.png")
            _write_png(img)
            html = '<img src="file://%s" alt="a">' % img
            out, n, failed = embed_local_images(html)
            self.assertEqual((n, failed), (1, []))
            self.assertIn("data:image/png;base64,", out)
            self.assertNotIn("file://", out)

    def test_missing_file_kept_and_reported(self):
        html = '<img src="file:///nonexistent/nope.png">'
        out, n, failed = embed_local_images(html)
        self.assertEqual(n, 0)
        self.assertEqual(failed, ["file:///nonexistent/nope.png"])
        self.assertIn("file:///nonexistent/nope.png", out)

    def test_remote_and_data_uri_untouched(self):
        html = (
            '<img src="https://example.com/x.png">'
            '<img src="data:image/gif;base64,AAAA">'
        )
        out, n, failed = embed_local_images(html)
        self.assertEqual((n, failed), (0, []))
        self.assertEqual(out, html)

    def test_url_encoded_path(self):
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "图片 a.png")
            _write_png(img)
            from urllib.parse import quote

            html = '<img src="file://%s">' % quote(img)
            out, n, failed = embed_local_images(html)
            self.assertEqual((n, failed), (1, []))
            self.assertIn("data:image/png;base64,", out)


class BuildExportHtmlTests(unittest.TestCase):
    def test_export_embeds_images_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "b.png")
            _write_png(img)
            body = '<p>x</p><img src="file://%s">' % img
            html = build_export_html(body, enable_katex=False)
            self.assertIn("data:image/png;base64,", html)
            self.assertNotIn("file://", html)

    def test_export_disabled_keeps_file_paths(self):
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "c.png")
            _write_png(img)
            body = '<img src="file://%s">' % img
            html = build_export_html(body, enable_katex=False, embed_images=False)
            self.assertIn("file://", html)
            self.assertNotIn("data:image/png;base64,", html)

    def test_export_missing_image_warns(self):
        body = '<img src="file:///nonexistent/nope.png">'
        warnings = []
        html = build_export_html(body, enable_katex=False, embed_warnings=warnings)
        self.assertEqual(len(warnings), 1)
        self.assertIn("file:///nonexistent/nope.png", html)


if __name__ == "__main__":
    unittest.main()
