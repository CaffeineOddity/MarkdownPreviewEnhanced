#!/usr/bin/env python3
"""有序列表起始编号（start 属性）渲染测试 (issue #15)."""
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


class TestOrderedListStart(unittest.TestCase):
    def test_non_one_start_emits_start_attribute(self):
        html = _body("Some paragraph.\n\n5. Fifth item\n6. Sixth item\n")
        self.assertIn('start="5"', html)

    def test_one_start_omits_start_attribute(self):
        html = _body("1. First\n2. Second\n")
        self.assertNotIn('start="', html)

    def test_interrupted_lists_keep_their_starts(self):
        html = _body("3. three\n4. four\n\nbreak\n\n7. seven\n8. eight\n")
        self.assertIn('start="3"', html)
        self.assertIn('start="7"', html)


if __name__ == "__main__":
    unittest.main()