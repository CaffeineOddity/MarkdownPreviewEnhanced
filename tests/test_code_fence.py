#!/usr/bin/env python3
"""代码块 filename/行号/高亮 元信息解析与组装测试 (docs/specs/code-fence-meta.md)."""
import unittest

from mpe_core.code_fence import (
    extract_code_fences,
    parse_fence_info,
    render_block,
    restore_code_fences,
)


class TestParseFenceInfo(unittest.TestCase):
    def test_lang_title_hl(self):
        self.assertEqual(
            parse_fence_info('python title="app.py" {1,3-5}'),
            ("python", "app.py", [1, 3, 4, 5]))

    def test_order_independent(self):
        self.assertEqual(
            parse_fence_info('{2,4} title="x.py" js'),
            ("js", "x.py", [2, 4]))

    def test_no_meta(self):
        self.assertEqual(parse_fence_info("python"), ("python", None, None))

    def test_title_with_space(self):
        self.assertEqual(
            parse_fence_info('title="my file.py"'), ("", "my file.py", None))


class TestExtractFences(unittest.TestCase):
    def test_plain_fence_also_stashed(self):
        text = '```python title="a.py" {1}\nx\n```\n\n```\nplain\n```'
        newtext, stash = extract_code_fences(text)
        self.assertEqual(len(stash), 2)
        self.assertEqual(stash[0]["title"], "a.py")
        self.assertEqual(stash[1]["code"], "plain")
        self.assertNotIn("```\nplain\n```", newtext)

    def test_restore_wraps(self):
        text = '```python title="a.py" {1}\nx\n```'
        newtext, stash = extract_code_fences(text)
        html = restore_code_fences("<p>\x00MDPP_FENCE_0\x00</p>", stash)
        self.assertIn('class="mdpp-code"', html)
        self.assertIn("a.py", html)
        self.assertIn("linenos", html)


class TestRenderBlock(unittest.TestCase):
    def test_plain_fence_header_has_copy(self):
        meta = {"lang": "shell", "title": None, "hl": None, "code": "ruby x.rb\n"}
        html = render_block(meta)
        self.assertIn("mdpp-code-header", html)
        self.assertLess(html.index("mdpp-code-copy"), html.index("codehilitetable"))


if __name__ == "__main__":
    unittest.main()