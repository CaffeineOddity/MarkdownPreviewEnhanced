#!/usr/bin/env python3
"""列表嵌套按实际缩进（2 空格起），四空格代码块不变 (issue #23 / #27)。"""
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

    def test_four_space_items_nest(self):
        html = _body("* List 1\n    - nested\n")
        self.assertEqual(len(re.findall(r"<ul\b", html)), 2)
        self.assertRegex(html, r"List 1<ul>\s*<li\b[^>]*>nested</li>")

    def test_loose_four_space_items_nest(self):
        html = _body("- foo\n\n    - bar\n\n        - baz\n")
        self.assertRegex(
            html,
            r"foo<ul>\s*<li\b[^>]*>bar<ul>\s*<li\b[^>]*>baz</li>",
        )

    def test_tab_indented_items_nest(self):
        html = _body("- foo\n\t- bar\n\t\t- baz\n")
        self.assertRegex(
            html,
            r"foo<ul>\s*<li\b[^>]*>bar<ul>\s*<li\b[^>]*>baz</li>",
        )

    def test_two_space_ordered_items_nest(self):
        html = _body("1. a\n  1. b\n    1. c\n")
        self.assertEqual(len(re.findall(r"<ol\b", html)), 3)
        self.assertRegex(html, r"a<ol>\s*<li\b[^>]*>b<ol>")

    def test_ordered_deeper_four_space_levels(self):
        html = _body(
            "1. 第一層\n"
            "2. 第一層\n"
            "    1. 第二層\n"
            "    2. 第二層\n"
            "        1. 第三層\n"
        )
        self.assertEqual(len(re.findall(r"<ol\b", html)), 3)
        self.assertRegex(
            html,
            r"第二層<ol>\s*<li\b[^>]*>第三層</li>",
        )

    def test_top_level_three_space_items(self):
        html = _body("   - foo\n       - bar\n")
        self.assertRegex(
            html,
            r"foo<ul>\s*<li\b[^>]*>bar</li>",
        )

    def test_four_space_code_block_unchanged(self):
        html = _body("paragraph\n\n    code\n")
        self.assertIn("<code>code\n</code>", html)
        self.assertNotIn("<ul", html)

    def test_code_block_inside_list_unchanged(self):
        html = _body("- item\n\n      code\n")
        self.assertIn("<code>code\n</code>", html)
        self.assertNotRegex(html, r"item<ul")

    def test_list_interrupts_paragraph(self):
        html = _body(
            "un-order points\n"
            "- point 1\n"
            "- point 2\n"
            "    - point 2.1\n"
            "- point 3\n"
        )
        self.assertRegex(html, r"<p\b[^>]*>un-order points</p>\s*<ul>")
        self.assertRegex(html, r"point 2<ul>\s*<li\b[^>]*>point 2.1</li>")

    def test_ordered_list_interrupts_paragraph(self):
        html = _body(
            "order points\n"
            "1. point 1\n"
            "2. point 2\n"
            "    1. point 2.1\n"
            "    2. point 2.2\n"
        )
        self.assertRegex(html, r"<p\b[^>]*>order points</p>\s*<ol>")
        self.assertRegex(html, r"point 2<ol>\s*<li\b[^>]*>point 2.1</li>")

    def test_ordered_list_not_starting_at_one_does_not_interrupt(self):
        html = _body("para\n2. item\n")
        self.assertIn("<p", html)
        self.assertNotIn("<ol", html)

    def test_issue_27_sample(self):
        html = _body(
            "Heading1\n"
            "========\n"
            "\n"
            "Some text, some paragraphs..\n"
            "\n"
            "heading2\n"
            "---------\n"
            "\n"
            "un-order points\n"
            "- point 1\n"
            "- point 2\n"
            "    - point 2.1\n"
            "    - point 2.2\n"
            "- point 3\n"
            "\n"
            "order points\n"
            "1. point 1\n"
            "2. point 2\n"
            "    1. point 2.1\n"
            "    2. point 2.2\n"
        )
        self.assertEqual(len(re.findall(r"<ul\b", html)), 2)
        self.assertEqual(len(re.findall(r"<ol\b", html)), 2)
        self.assertRegex(html, r"<p\b[^>]*>un-order points</p>\s*<ul>")
        self.assertRegex(html, r"point 2<ul>\s*<li\b[^>]*>point 2.1</li>")
        self.assertRegex(html, r"<p\b[^>]*>order points</p>\s*<ol>")
        self.assertRegex(html, r"point 2<ol>\s*<li\b[^>]*>point 2.1</li>")

    def test_ordered_and_unordered_stay_separate(self):
        html = _body("* bullet\n\n1. numbered\n")
        self.assertIn("<ul>", html)
        self.assertIn("<ol>", html)
        self.assertNotRegex(html, r"<ul>.*<ol>.*</ul>", re.DOTALL)


if __name__ == "__main__":
    unittest.main()
