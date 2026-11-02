#!/usr/bin/env python3
"""标题 id 与 mermaid 全局名冲突 (issue #18)。

浏览器会把 id/name="mermaid" 的元素暴露成 window.mermaid。库脚本赋值之前
它是真值但没有 run，旧的存在性判断会调用 initialize 并就此停止重试。
"""
import os
import re
import unittest

from mpe_core.html_builder import build_export_html, build_preview_shell
from mpe_core.md_renderer import render
from mpe_core.presentation_builder import build_presentation


def _body(text):
    return render(
        text,
        strip_yaml=False,
        enable_math=False,
        enable_emoji=False,
        enable_task_lists=False,
        enable_toc=False,
    )["body_html"]


def _asset(name):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "assets", name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _preview_js():
    return _asset("preview.js")


class TestMermaidHeadingId(unittest.TestCase):
    def test_exact_heading_still_uses_mermaid_id(self):
        html = _body("#### Mermaid")
        self.assertIn('id="mermaid"', html)

    def test_cjk_suffix_is_not_stripped_to_mermaid(self):
        html = _body("## Mermaid 正解")
        self.assertNotIn('id="mermaid"', html)
        self.assertIn('id="mermaid-正解"', html)


class TestMermaidGlobalGuard(unittest.TestCase):
    def test_preview_js_requires_run(self):
        js = _preview_js()
        self.assertIn('typeof mm.run !== "function"', js)
        self.assertNotIn("typeof window.mermaid === \"undefined\"", js)

    def test_preview_shell_waits_for_run(self):
        html = build_preview_shell('<h1 id="mermaid">Mermaid</h1>')
        self.assertIn("typeof o.run==='function'", html)
        self.assertNotIn("mermaid.initialize(", html)
        self.assertIn("typeof mm.run!=='function'", html)

    def test_export_waits_for_run(self):
        html = build_export_html('<h1 id="mermaid">Mermaid</h1>')
        self.assertIn("typeof mm.run==='function'", html)
        self.assertNotIn("if(window.mermaid){mermaid.initialize", html)

    def test_presentation_does_not_latch_on_element(self):
        html = build_presentation(
            '<h1 id="mermaid">Mermaid</h1><pre class="mermaid">graph TD\nA-->B</pre>'
        )
        self.assertIn('typeof window.mermaid.run==="function"', html)
        self.assertNotIn("if(window.mermaid&&!window.__mdppMm)", html)
        self.assertIn("needMm=", html)


class TestBundledMermaidSubgraphEdges(unittest.TestCase):
    def test_version_keeps_external_edge_on_the_node(self):
        # issue #19：11.16.0 合入 #7672 后，子图里的节点连到外面时，
        # direction 会被单独排版，外连边从子图边框出发。11.17.0 撤回了
        # 这个改动，11.17.2 把 edgePaths 类名补了回来。不要退回 11.16。
        text = _asset("mermaid.min.js")
        match = re.search(r'\{version:"(\d+)\.(\d+)\.(\d+)"\}', text)
        self.assertIsNotNone(match)
        version = tuple(int(part) for part in match.groups())
        self.assertGreaterEqual(version, (11, 17, 2))
        self.assertLess(version, (12, 0, 0))


if __name__ == "__main__":
    unittest.main()
