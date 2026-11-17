"""实时预览正文宽度比例 content_width，范围 0.5–1。"""
import unittest

from mpe_core.html_builder import (
    build_preview_shell,
    format_content_width,
    normalize_content_width,
)


class TestContentWidth(unittest.TestCase):
    def test_default_and_invalid_become_0_9(self):
        self.assertEqual(normalize_content_width(None), 0.8)
        self.assertEqual(normalize_content_width("wide"), 0.8)
        self.assertEqual(normalize_content_width(True), 0.8)
        self.assertEqual(normalize_content_width(float("nan")), 0.8)

    def test_clamps_to_half_and_full(self):
        self.assertEqual(normalize_content_width(0.1), 0.5)
        self.assertEqual(normalize_content_width(0.5), 0.5)
        self.assertEqual(normalize_content_width(1), 1.0)
        self.assertEqual(normalize_content_width(1.4), 1.0)
        self.assertEqual(normalize_content_width("0.75"), 0.75)

    def test_format_strips_trailing_zeros(self):
        self.assertEqual(format_content_width(0.9), "0.9")
        self.assertEqual(format_content_width(1), "1")
        self.assertEqual(format_content_width(0.5), "0.5")

    def test_shell_writes_clamped_css_variable(self):
        html = build_preview_shell("<p>x</p>", enable_katex=False, use_server=True)
        self.assertIn('style="--mdpp-content-width: 0.8"', html)
        wide = build_preview_shell(
            "<p>x</p>", enable_katex=False, use_server=True, content_width=2)
        self.assertIn('style="--mdpp-content-width: 1"', wide)
        narrow = build_preview_shell(
            "<p>x</p>", enable_katex=False, use_server=True, content_width=0.2)
        self.assertIn('style="--mdpp-content-width: 0.5"', narrow)


if __name__ == "__main__":
    unittest.main()
