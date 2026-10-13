#!/usr/bin/env python3
"""frontmatter title/date/tags 解析测试 (docs/specs/frontmatter-banner.md)."""
import unittest

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


if __name__ == "__main__":
    unittest.main()