#!/usr/bin/env python3
"""GFM emoji shortcode rendering."""
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

from mpe_core.emoji_map import EMOJI_ALIASES  # noqa: E402
from mpe_core.md_renderer import (  # noqa: E402
    _EMOJI_RE,
    _protect_code_then,
    _replace_emoji,
    render,
)


def _render(text):
    result = render(text, strip_yaml=False, enable_math=False)
    if result.get("errors"):
        raise unittest.SkipTest("markdown unavailable: %s" % result["errors"])
    return result["body_html"]


class EmojiMapTests(unittest.TestCase):
    def test_map_has_common_aliases(self):
        for alias in ("smile", "tada", "+1", "-1", "heart"):
            self.assertIn(alias, EMOJI_ALIASES)

    def test_map_values_are_emoji(self):
        for alias in ("smile", "tada", "+1"):
            ch = EMOJI_ALIASES[alias]
            self.assertGreaterEqual(len(ch), 1)
            self.assertLess(len(ch), 12)

    def test_github_mascots_absent(self):
        self.assertNotIn("octocat", EMOJI_ALIASES)
        self.assertNotIn("shipit", EMOJI_ALIASES)


class EmojiRegexTests(unittest.TestCase):
    def test_simple_shortcode(self):
        m = _EMOJI_RE.search(":smile:")
        self.assertEqual(m.group(1), "smile")

    def test_flag_emoji_with_plus_dash(self):
        self.assertEqual(_EMOJI_RE.search(":+1:").group(1), "+1")

    def test_no_match_between_word_chars(self):
        self.assertIsNone(_EMOJI_RE.search("foo:bar:baz"))
        self.assertIsNone(_EMOJI_RE.search("a:b"))

    def test_match_after_punctuation(self):
        self.assertEqual(_EMOJI_RE.search("(:tada:)").group(1), "tada")
        self.assertEqual(_EMOJI_RE.search(":tada:,").group(1), "tada")

    def test_match_at_line_start(self):
        m = _EMOJI_RE.search(":tada: ship it")
        self.assertEqual(m.group(1), "tada")


class EmojiReplaceTests(unittest.TestCase):
    def test_replace_known(self):
        self.assertEqual(_replace_emoji(":smile:"), EMOJI_ALIASES["smile"])

    def test_unknown_kept(self):
        self.assertEqual(_replace_emoji(":not-an-emoji-944:"), ":not-an-emoji-944:")

    def test_prose_sentence(self):
        out = _replace_emoji("Great work :+1: team!")
        self.assertIn(EMOJI_ALIASES["+1"], out)

    def test_word_boundary_untouched(self):
        self.assertEqual(_replace_emoji("key:value"), "key:value")

    def test_multiple(self):
        out = _replace_emoji(":tada: :smile:")
        self.assertEqual(
            out, EMOJI_ALIASES["tada"] + " " + EMOJI_ALIASES["smile"])


class ProtectCodeThenTests(unittest.TestCase):
    def test_fence_content_untouched(self):
        src = "```python\nx = ':smile:'\n```\n\n:text :tada:\n"
        out = _protect_code_then(src, _replace_emoji)
        self.assertIn("':smile:'", out)
        self.assertNotIn(":tada:", out)

    def test_inline_code_untouched(self):
        src = "run `:smile:` cmd then :tada:\n"
        out = _protect_code_then(src, _replace_emoji)
        self.assertIn("`:smile:`", out)
        self.assertNotIn(":tada:", out)


class EmojiRenderTests(unittest.TestCase):
    def test_renders_in_paragraph(self):
        html = _render("hello :smile: world\n")
        self.assertIn(EMOJI_ALIASES["smile"], html)
        self.assertNotIn(":smile:", html)

    def test_renders_in_heading(self):
        html = _render("# T :tada:\n")
        self.assertIn(EMOJI_ALIASES["tada"], html)

    def test_disabled_keeps_shortcode(self):
        result = render("hi :smile:\n", strip_yaml=False,
                        enable_math=False, enable_emoji=False)
        if result.get("errors"):
            raise unittest.SkipTest("markdown unavailable")
        self.assertIn(":smile:", result["body_html"])

    def test_code_block_not_replaced(self):
        html = _render("```\n:smile:\n```\n")
        self.assertIn(":smile:", html)
        self.assertNotIn(EMOJI_ALIASES["smile"], html)

    def test_inline_code_not_replaced(self):
        html = _render("use `:smile:` ok\n")
        self.assertIn(":smile:", html)

    def test_unknown_stays(self):
        html = _render("a :nope-944: b\n")
        self.assertIn(":nope-944:", html)

    def test_in_table_cell(self):
        html = _render("| a | b |\n| --- | --- |\n | :smile: | x |\n")
        self.assertIn(EMOJI_ALIASES["smile"], html)


if __name__ == "__main__":
    unittest.main()
