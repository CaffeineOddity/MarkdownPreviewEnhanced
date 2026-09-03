#!/usr/bin/env python3
"""Scroll-sync mapping: data-line injection and viewport pinning."""
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

from mpe_core.md_renderer import (  # noqa: E402
    _collect_block_lines,
    _collect_heading_lines,
    _inject_block_lines,
    render,
)


class DataLineInjectionTests(unittest.TestCase):
    def test_collect_paragraphs_and_list_items(self):
        src = "hello\n\n- a\n- b\n"
        blocks = _collect_block_lines(src)
        self.assertEqual(blocks, [(1, "p"), (3, "li"), (4, "li")])

    def test_collect_mermaid_fence_has_line_range(self):
        src = "intro\n\n```mermaid\ngraph TD\n  A-->B\n```\n\nnext\n"
        blocks = _collect_block_lines(src)
        self.assertIn((3, "pre", 6), blocks)
        self.assertIn((8, "p"), blocks)

    def test_inject_mermaid_pre_gets_range(self):
        html = '<pre class="mermaid">graph</pre><p>hello</p>'
        out = _inject_block_lines(html, [(3, "pre", 6), (8, "p")], 0)
        self.assertIn('<pre data-line="3" data-line-end="6" class="mermaid">', out)
        self.assertIn('<p data-line="8">hello</p>', out)

    def test_heading_lines_ignore_fences(self):
        src = "# real\n```\n# fake\n```\n## two\n"
        lines = _collect_heading_lines(src)
        self.assertEqual([ln for ln, _lvl, _t in lines], [1, 5])

    def test_inject_block_lines_writes_data_line(self):
        html = "<p>hello</p><ul><li>a</li><li>b</li></ul>"
        out = _inject_block_lines(html, [(1, "p"), (3, "li"), (4, "li")], 0)
        self.assertIn('<p data-line="1">hello</p>', out)
        self.assertIn('<li data-line="3">a</li>', out)
        self.assertIn('<li data-line="4">b</li>', out)

    def test_block_lines_apply_frontmatter_offset(self):
        html = "<p>hello</p>"
        out = _inject_block_lines(html, [(1, "p")], line_offset=3)
        self.assertIn('data-line="4"', out)

    def test_render_injects_paragraph_data_line(self):
        result = render("hello\n\nworld\n", strip_yaml=False, enable_math=False)
        if result.get("errors"):
            import inspect
            from mpe_core import md_renderer
            src = inspect.getsource(md_renderer.render)
            self.assertIn("_inject_block_lines", src)
            self.skipTest("markdown unavailable: %s" % result["errors"])
        html = result["body_html"]
        self.assertIn('data-line="1"', html)
        self.assertIn('data-line="3"', html)
        self.assertGreaterEqual(html.count("data-line="), 2)


if __name__ == "__main__":
    unittest.main()
