#!/usr/bin/env python3
"""KaTeX 服务端渲染在 Windows 区域编码下仍按 UTF-8 收发 (issue #26).

本机区域编码是 UTF-8，subprocess 的 "locale" 编解码器也不走
locale.getpreferredencoding。测试在未显式传入 encoding 时，按 cp1252
模拟 Windows 文本模式：stdin 编码失败、stdout 被解成乱码。
"""
import os
import shutil
import subprocess
import unittest

from mpe_core import katex_renderer as kr

_REAL_RUN = subprocess.run

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KATEX_DIR = os.path.join(_ROOT, "assets", "katex")
_WORKER = os.path.join(_KATEX_DIR, "_render_worker.js")
_KATEX_JS = os.path.join(_KATEX_DIR, "katex.min.js")


def _run_like_windows_cp1252(*args, **kwargs):
    """未指定 encoding 的文本模式按 cp1252 收发，已指定的编码保持原样。"""
    text_mode = (
        kwargs.get("universal_newlines")
        or kwargs.get("text")
        or kwargs.get("encoding")
        or kwargs.get("errors")
    )
    if not text_mode or kwargs.get("encoding"):
        return _REAL_RUN(*args, **kwargs)

    payload = kwargs.get("input")
    if isinstance(payload, str):
        kwargs["input"] = payload.encode("cp1252")
    for key in ("universal_newlines", "text", "encoding", "errors"):
        kwargs.pop(key, None)
    result = _REAL_RUN(*args, **kwargs)
    stdout = result.stdout.decode("cp1252") if isinstance(result.stdout, bytes) else result.stdout
    stderr = result.stderr.decode("cp1252") if isinstance(result.stderr, bytes) else result.stderr
    return subprocess.CompletedProcess(result.args, result.returncode, stdout, stderr)


class TestKatexUtf8Pipe(unittest.TestCase):
    def setUp(self):
        kr._CACHE.clear()

    def tearDown(self):
        kr._CACHE.clear()

    def test_math_glyphs_survive_cp1252_locale(self):
        node = shutil.which("node")
        if not node or not os.path.isfile(_WORKER) or not os.path.isfile(_KATEX_JS):
            self.skipTest("node or katex worker unavailable")

        old_find = kr._find_node
        old_paths = kr._ensure_katex_paths
        old_run = kr.subprocess.run
        kr._find_node = lambda: node
        kr._ensure_katex_paths = lambda: (_KATEX_JS, _WORKER)
        kr.subprocess.run = _run_like_windows_cp1252
        try:
            html = kr.render_tex(
                r"L(\alpha, \theta) = \sum_{i=1}^{n} \Pi_i + \lambda",
                display=True,
            )
            # α 不在 cp1252 里。文本模式未固定 UTF-8 时，写入 stdin 会失败。
            text_html = kr.render_tex(r"\text{α}", display=False)
        finally:
            kr._find_node = old_find
            kr._ensure_katex_paths = old_paths
            kr.subprocess.run = old_run

        self.assertIsInstance(html, str)
        self.assertIn("\u03b1", html)
        self.assertIn("\u03b8", html)
        self.assertIn("\u2211", html)
        self.assertIn("\u03a0", html)
        self.assertIn("\u03bb", html)
        self.assertNotIn("Î±", html)
        self.assertNotIn("âˆ‘", html)
        self.assertIsInstance(text_html, str)
        self.assertIn("\u03b1", text_html)


if __name__ == "__main__":
    unittest.main()
