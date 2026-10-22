#!/usr/bin/env python3
"""frontmatter title/date/tags 解析测试 (docs/specs/frontmatter-banner.md)."""
import unittest

from mpe_core.html_builder import build_export_html, build_preview_shell
from mpe_core.md_renderer import parse_frontmatter


class TestParseFrontmatter(unittest.TestCase):
    def test_inline_tags(self):
        fm = "---\ntitle: My Doc\ndate: 2026-07-07\ntags: [a, b, c]\n---"
        meta = parse_frontmatter(fm)
        self.assertEqual(meta["title"], "My Doc")
        self.assertEqual(meta["date"], "2026-07-07")
        self.assertEqual(meta["tags"], ["a", "b", "c"])

    def test_block_tags(self):
        fm = "---\ntitle: 'Quoted'\ntags:\n  - x\n  - y\n---"
        meta = parse_frontmatter(fm)
        self.assertEqual(meta["title"], "Quoted")
        self.assertEqual(meta["tags"], ["x", "y"])

    def test_no_recognized_keys(self):
        self.assertIsNone(parse_frontmatter(None))
        self.assertIsNone(parse_frontmatter("---\nfoo: bar\n---"))


class TestFrontmatterLayout(unittest.TestCase):
    """frontmatter 顶栏不能作为 mdpp-wrap 的第三个 grid 子元素（回归）。

    有 TOC 时 ``.mdpp-wrap`` 是两列 grid（sidebar + 正文）；banner 若作为
    第三个直接子元素会抢占正文列，把 ``main`` 挤到 sidebar 正下方。
    """

    _FM = {"title": "T", "date": "D", "tags": ["a"]}

    def _assert_banner_in_main_col(self, html, main_open):
        wrap = html.index('<div class="mdpp-wrap">')
        main_col = html.index('<div class="mdpp-main">')
        banner = html.index('class="mdpp-frontmatter"')
        main = html.index(main_open)
        self.assertLess(wrap, main_col)
        self.assertLess(main_col, banner)
        self.assertLess(banner, main)

    def test_preview_banner_not_grid_third_item(self):
        html = build_preview_shell(
            "<p>x</p>", toc_html="<ul><li>s1</li></ul>", frontmatter=self._FM)
        self._assert_banner_in_main_col(html, '<main id="mdpp-content"')

    def test_export_banner_not_grid_third_item(self):
        html = build_export_html(
            "<p>x</p>", toc_html="<ul><li>s1</li></ul>", frontmatter=self._FM)
        self._assert_banner_in_main_col(html, '<main class="markdown-body">')


if __name__ == "__main__":
    unittest.main()