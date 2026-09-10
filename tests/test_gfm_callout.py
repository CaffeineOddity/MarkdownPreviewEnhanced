"""GFM callout（> [!NOTE] 等）渲染测试。"""
import unittest

from mpe_core.md_renderer import render


def _body(text):
    """渲染并返回 body_html（关掉无关特性）。"""
    return render(
        text,
        strip_yaml=False,
        enable_math=False,
        enable_emoji=False,
        enable_task_lists=False,
        enable_toc=False,
    )["body_html"]


class TestGfmCallout(unittest.TestCase):
    def test_note_callout(self):
        html = _body("> [!NOTE]\n> content")
        self.assertIn('mdpp-callout mdpp-callout-note', html)
        self.assertIn("mdpp-callout-title", html)
        self.assertIn("mdpp-callout-icon", html)
        self.assertNotIn("[!NOTE]", html)

    def test_all_five_types(self):
        for t in ("NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION"):
            html = _body("> [!%s]\n> x" % t)
            self.assertIn("mdpp-callout-%s" % t.lower(), html)

    def test_custom_title(self):
        html = _body("> [!tip] My Title\n> x")
        self.assertIn("My Title", html)
        self.assertNotIn("[!tip]", html)

    def test_default_title(self):
        html = _body("> [!warning]\n> x")
        self.assertIn("Warning", html)

    def test_unknown_type_stays_plain(self):
        html = _body("> [!FOO]\n> x")
        self.assertNotIn("mdpp-callout", html)
        self.assertIn("[!FOO]", html)

    def test_plain_quote_untouched(self):
        html = _body("> plain quote")
        self.assertNotIn("mdpp-callout", html)

    def test_type_not_on_first_line(self):
        html = _body("> some text\n> [!NOTE]")
        self.assertNotIn("mdpp-callout", html)

    def test_body_content_preserved(self):
        html = _body("> [!WARNING]\n> multi line\n>\n> second `para`")
        self.assertIn("multi line", html)
        self.assertIn("second <code>para</code>", html)
        self.assertNotIn("[!WARNING]", html)

    def test_list_after_blank_line_inside_callout(self):
        # 引用内 lazy continuation 会把紧跟首段的列表并入段落（python-markdown
        # 既有行为，非 callout 特有），空行分隔的列表正常解析
        html = _body("> [!IMPORTANT]\n>\n> - a\n> - b")
        self.assertIn("mdpp-callout-important", html)
        self.assertIn("<li>a</li>", html)


if __name__ == "__main__":
    unittest.main()
