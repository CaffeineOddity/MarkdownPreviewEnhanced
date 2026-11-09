#!/usr/bin/env python3
"""两空格子列表嵌套，四空格代码块不变 (issue #23)。"""
import re
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


class TestNestedListIndent(unittest.TestCase):
    def test_two_space_items_nest(self):
        html = _body(
            "* List 1\n"
            "  - nested list 1a\n"
            "  - nested list 1b\n"
            "* List 2\n"
            "  - nested list 2a\n"
            "  - nested list 2b\n"
        )
        self.assertEqual(len(re.findall(r"<ul\b", html)), 3)
        self.assertRegex(
            html,
            r"List 1<ul>\s*<li\b[^>]*>nested list 1a</li>\s*"
            r"<li\b[^>]*>nested list 1b</li>\s*</ul>",
        )
        self.assertRegex(
            html,
            r"List 2<ul>\s*<li\b[^>]*>nested list 2a</li>\s*"
            r"<li\b[^>]*>nested list 2b</li>\s*</ul>",
        )

    def test_three_space_items_nest_one_level(self):
        html = _body("* List 1\n   - nested list 1a\n")
        self.assertRegex(html, r"List 1<ul>\s*<li\b[^>]*>nested list 1a</li>")

    def test_deeper_two_space_levels(self):
        html = _body("- foo\n  - bar\n    - baz\n")
        self.assertRegex(
            html,
            r"foo<ul>\s*<li\b[^>]*>bar<ul>\s*<li\b[^>]*>baz</li>",
        )

    def test_four_space_code_block_unchanged(self):
        html = _body("paragraph\n\n    code\n")
        self.assertIn("<code>code\n</code>", html)
        self.assertNotIn("<ul", html)

    def test_four_space_marker_is_not_one_nested_level(self):
        # 方式 2 只认 2 或 3 个空格为一层。4 个空格不再单独嵌套。
        html = _body("* List 1\n    - nested\n")
        self.assertEqual(len(re.findall(r"<ul\b", html)), 1)
        self.assertIn("- nested", html)

    def test_ordered_and_unordered_stay_separate(self):
        html = _body("* bullet\n\n1. numbered\n")
        self.assertIn("<ul>", html)
        self.assertIn("<ol>", html)
        self.assertNotRegex(html, r"<ul>.*<ol>.*</ul>", re.DOTALL)
