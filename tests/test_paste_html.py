#!/usr/bin/env python3
"""tests for commands/paste_html_as_markdown.py (HTML → Markdown 转换部分)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# sublime / sublime_plugin stub（与 run_all.py 一致，commands 模块级 import 需要）
import types  # noqa: E402
if "sublime" not in sys.modules:
    _sublime = types.ModuleType("sublime")
    _sublime.load_resource = lambda p: ""
    _sublime.load_binary_resource = lambda p: None
    _sublime.cache_path = lambda: "/tmp/mdpp_cache_stub"
    _sublime.version = lambda: 4107
    sys.modules["sublime"] = _sublime
if "sublime_plugin" not in sys.modules:
    _sp = types.ModuleType("sublime_plugin")

    class _TextCommand:  # noqa: D101 - 测试不实例化
        pass

    class _WindowCommand:  # noqa: D101
        pass

    class _EventListener:  # noqa: D101
        pass

    _sp.TextCommand = _TextCommand
    _sp.WindowCommand = _WindowCommand
    _sp.EventListener = _EventListener
    sys.modules["sublime_plugin"] = _sp

from mpe_core import vendor  # noqa: E402,F401
# commands/*.py 用 ..mpe_core 相对导入，须以包身份加载：
# 把仓库根伪装成 MarkdownPreviewEnhanced 包，再按包路径 import
import importlib  # noqa: E402
import types  # noqa: E402
_pkg = types.ModuleType("MarkdownPreviewEnhanced")
_pkg.__path__ = [ROOT]
_pkg.__package__ = "MarkdownPreviewEnhanced"
sys.modules.setdefault("MarkdownPreviewEnhanced", _pkg)
_sub = importlib.import_module("mpe_core")
sys.modules["MarkdownPreviewEnhanced.mpe_core"] = _sub
ph = importlib.import_module("MarkdownPreviewEnhanced.commands.paste_html_as_markdown")


class TestHtmlToMarkdown(unittest.TestCase):
    def test_basic_structure(self):
        html = (
            "<h3>标题</h3><p>段落，<em>斜体</em>与<b>加粗</b>。</p>"
            "<blockquote><p>引用</p></blockquote>"
            "<ol><li>第一</li><li>第二</li></ol>"
            "<img src=\"https://e.com/a.png\" alt=\"图\">"
            "<p><a href=\"https://e.com\">链接</a></p>"
        )
        md = ph.html_fragment_to_markdown(html)
        self.assertIn("### 标题", md)
        self.assertIn("*斜体*", md)
        self.assertIn("**加粗**", md)
        self.assertIn("> 引用", md)
        self.assertIn("1. 第一", md)
        self.assertIn("![图](https://e.com/a.png)", md)
        self.assertIn("[链接](https://e.com)", md)
        self.assertTrue(md.endswith("\n"))

    def test_chrome_meta_wrappers_stripped(self):
        html = '<meta charset="utf-8"><div><h2>T</h2><p>x</p></div>'
        md = ph.html_fragment_to_markdown(html)
        self.assertIn("## T", md)
        self.assertNotIn("meta", md.lower())

    def test_firefox_comment_wrappers_stripped(self):
        html = (
            '<!--StartFragment--><p>content here</p>'
            '<!--EndFragment-->'
        )
        md = ph.html_fragment_to_markdown(html)
        self.assertIn("content here", md)
        self.assertNotIn("StartFragment", md)

    def test_code_block_fenced(self):
        html = "<pre><code>x = 1\ny = 2</code></pre>"
        md = ph.html_fragment_to_markdown(html)
        self.assertIn("```\nx = 1\ny = 2\n```", md)

    def test_table(self):
        html = "<table><tr><th>H</th></tr><tr><td>v</td></tr></table>"
        md = ph.html_fragment_to_markdown(html)
        self.assertIn("| H |", md)
        self.assertIn("| v |", md)


class TestLocalizeImages(unittest.TestCase):
    def _md(self, body, ctype):
        # 本地 HTTP stub：用 file:// 不行（urlopen 支持），改打桩 download_image
        calls = []

        def fake_download(url, images_dir, md_dir):
            calls.append(url)
            return "media/abc.png"

        orig = ph.download_image
        ph.download_image = fake_download
        try:
            out, ok, fail = ph.localize_images(
                "![图](https://e.com/a.png) and ![b](https://e.com/b.jpg)",
                "/tmp/md", "/tmp/md/media")
        finally:
            ph.download_image = orig
        return out, ok, fail, calls

    def test_replace_all(self):
        out, ok, fail, calls = self._md(None, None)
        self.assertEqual(ok, 2)
        self.assertEqual(fail, 0)
        self.assertEqual(len(calls), 2)
        self.assertIn("](media/abc.png)", out)
        self.assertNotIn("https://e.com", out)

    def test_fail_keeps_url(self):
        orig = ph.download_image
        ph.download_image = lambda *a: None
        try:
            out, ok, fail = ph.localize_images(
                "![x](https://e.com/dead.png)", "/tmp/md", "/tmp/md/media")
        finally:
            ph.download_image = orig
        self.assertEqual(fail, 1)
        self.assertEqual(ok, 0)
        self.assertIn("https://e.com/dead.png", out)


class TestCfHtmlParsing(unittest.TestCase):
    def test_cf_html_header_regex(self):
        head = "Version:0.9\r\nStartHTML:0000000171\r\nEndHTML:0000001234\r\n"
        m = ph._CF_HTML_HEADER_RE.search(head)
        self.assertEqual(m.group(1), "0000000171")
        self.assertEqual(int(m.group(2)), 1234)

    def test_macos_hex_regex(self):
        m = ph._HTML_HEX_RE.search("«data HTML3c703e»")
        self.assertEqual(m.group(1), "3c703e")
        import binascii
        self.assertEqual(binascii.unhexlify(m.group(1)), b"<p>")


if __name__ == "__main__":
    unittest.main()
