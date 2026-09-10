"""GFM 内联语法（删除线/高亮/上标/下标）渲染测试。"""
import unittest

from mpe_core.md_renderer import render


def _body(text):
    """渲染并返回 body_html（关掉无关特性，聚焦内联语法）。"""
    return render(
        text,
        strip_yaml=False,
        enable_math=False,
        enable_emoji=False,
        enable_task_lists=False,
        enable_toc=False,
    )["body_html"]


class TestGfmInline(unittest.TestCase):
    def test_strikethrough(self):
        html = _body("~~deleted~~")
        self.assertIn("<del>deleted</del>", html)

    def test_highlight(self):
        html = _body("==highlighted==")
        self.assertIn("<mark>highlighted</mark>", html)

    def test_superscript(self):
        html = _body("x^2^")
        self.assertIn("x<sup>2</sup>", html)

    def test_subscript(self):
        html = _body("H~2~O")
        self.assertIn("H<sub>2</sub>O", html)

    def test_nested_bold_in_del(self):
        html = _body("**bold ~~del~~ more**")
        self.assertIn("bold <del>del</del> more", html)

    def test_inline_code_untouched(self):
        html = _body("`~~code~~`")
        self.assertIn("<code>~~code~~</code>", html)
        self.assertNotIn("<del>", html)

    def test_code_fence_untouched(self):
        html = _body("```\n~~x~~\n```")
        self.assertNotIn("<del>", html)

    def test_lone_tilde_untouched(self):
        html = _body("~ lone tilde")
        self.assertNotIn("<sub>", html)

    def test_comparison_not_highlight(self):
        html = _body("2 == 2")
        self.assertNotIn("<mark>", html)

    def test_unclosed_sup_untouched(self):
        html = _body("a^b no close")
        self.assertNotIn("<sup>", html)


if __name__ == "__main__":
    unittest.main()
