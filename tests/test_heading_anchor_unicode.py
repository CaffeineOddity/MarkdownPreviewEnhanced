#!/usr/bin/env python3
"""中文标题 anchor id 渲染测试 (issue #16)."""
import unittest

from mpe_core.md_renderer import render


def _body(text):
    return render(
        text,
        strip_yaml=False,
        enable_math=False,
        enable_emoji=False,
        enable_task_lists=False,
        enable_toc=False,
    )["body_html"]


class TestChineseHeadingAnchor(unittest.TestCase):
    def test_chinese_heading_keeps_unicode_id(self):
        html = _body("### 句型")
        self.assertIn('id="句型"', html)

    def test_duplicate_chinese_headings_get_suffix(self):
        html = _body("## 重复\n\n## 重复")
        self.assertIn('id="重复"', html)
        self.assertIn('id="重复_1"', html)

    def test_ascii_heading_id_unchanged(self):
        html = _body("## Hello World")
        self.assertIn('id="hello-world"', html)


if __name__ == "__main__":
    unittest.main()