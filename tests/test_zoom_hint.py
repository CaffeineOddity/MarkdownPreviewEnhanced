"""图片 / Mermaid 放大提示默认英文，并可由 zoom_hint 覆盖 (issue #25)。"""
import os
import unittest

from mpe_core.html_builder import build_preview_shell, normalize_zoom_hint

_DEFAULT = "Drag to pan · Scroll to zoom · Esc to close"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _preview_js():
    path = os.path.join(_ROOT, "assets", "preview.js")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestZoomHint(unittest.TestCase):
    def test_blank_hint_is_unset(self):
        self.assertEqual(normalize_zoom_hint(""), "")
        self.assertEqual(normalize_zoom_hint("  \n\t"), "")
        self.assertEqual(normalize_zoom_hint(None), "")

    def test_hint_collapses_to_one_line(self):
        self.assertEqual(
            normalize_zoom_hint("拖动平移\n滚轮缩放"),
            "拖动平移 滚轮缩放",
        )

    def test_default_shell_has_no_hardcoded_chinese_hint(self):
        html = build_preview_shell("<p>x</p>", enable_katex=False, use_server=True)
        self.assertNotIn("拖动平移", html)
        self.assertNotIn("滚轮缩放", html)
        self.assertNotIn('"zoomHint"', html)
        js = _preview_js()
        self.assertIn(_DEFAULT, js)
        self.assertNotIn("拖动平移 · 滚轮缩放 · Esc 关闭", js)

    def test_custom_hint_is_plain_text_in_config(self):
        html = build_preview_shell(
            "<p>x</p>",
            enable_katex=False,
            use_server=True,
            zoom_hint="拖动平移 · 滚轮缩放 · Esc 关闭",
        )
        self.assertIn(
            '"zoomHint": "拖动平移 · 滚轮缩放 · Esc 关闭"',
            html,
        )

    def test_hint_cannot_close_the_script_tag(self):
        html = build_preview_shell(
            "<p>x</p>",
            enable_katex=False,
            use_server=True,
            zoom_hint='</script><img src=x onerror=alert(1)>',
        )
        self.assertNotIn("</script><img", html)
        self.assertIn("\\u003c/script>", html)


if __name__ == "__main__":
    unittest.main()
