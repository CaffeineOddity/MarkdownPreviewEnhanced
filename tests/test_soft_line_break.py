#!/usr/bin/env python3
"""段内单个换行是软换行 (issue #21)。"""
import re
import unittest

from mpe_core.md_renderer import render


def _body(text, break_on_single_newline=False):
    return render(
        text,
        strip_yaml=False,
        enable_math=False,
        enable_emoji=False,
        enable_task_lists=False,
        enable_toc=False,
        break_on_single_newline=break_on_single_newline,
    )["body_html"]


class TestSoftLineBreak(unittest.TestCase):
    def test_single_newline_stays_one_paragraph(self):
        html = _body(
            "This is a single sentence\nthat is written across two lines.\n"
        )
        self.assertNotIn("<br", html)
        self.assertEqual(len(re.findall(r"<p[\s>]", html)), 1)
        self.assertIn("This is a single sentence", html)
        self.assertIn("that is written across two lines.", html)

    def test_blank_line_starts_a_new_paragraph(self):
        html = _body("one paragraph\n\nanother paragraph\n")
        self.assertEqual(len(re.findall(r"<p[\s>]", html)), 2)
        self.assertNotIn("<br", html)

    def test_two_trailing_spaces_stay_a_hard_break(self):
        html = _body("first line  \nsecond line\n")
        self.assertIn("<br", html)
        self.assertIn("first line", html)
        self.assertIn("second line", html)

    def test_setting_turns_single_newlines_into_breaks(self):
        html = _body("alpha\nbeta\n", break_on_single_newline=True)
        self.assertIn("<br", html)
        self.assertIn("alpha", html)
        self.assertIn("beta", html)


if __name__ == "__main__":
    unittest.main()
