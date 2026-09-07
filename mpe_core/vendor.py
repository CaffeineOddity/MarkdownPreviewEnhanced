"""Vendored library loader.

把 `_vendor` 目录加入 sys.path，使 markdownify / bs4 可直接 import。
幂等：重复调用无害。供 paste_html_as_markdown 使用。
"""
import os
import sys

_VENDOR_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_vendor")


def ensure_vendor_path():
    """将 _vendor 目录插入 sys.path（幂等）。"""
    if _VENDOR_DIR not in sys.path:
        sys.path.insert(0, _VENDOR_DIR)


def markdownify(html, **options):
    """HTML → Markdown。首次调用时加载 vendored markdownify。"""
    ensure_vendor_path()
    from markdownify import markdownify as _md
    return _md(html, **options)
