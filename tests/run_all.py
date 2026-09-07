#!/usr/bin/env python3
"""Test runner for MarkdownPreviewEnhanced.

Works outside Sublime: injects a `sublime` stub, points md_renderer's
markdown import at the mdpopups dependency installed under ST's Lib/python38,
then discovers tests in tests/.

Usage: python3 tests/run_all.py
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── sublime stub ─────────────────────────────────────────────────────────────
if "sublime" not in sys.modules:
    _sublime = types.ModuleType("sublime")
    _sublime.load_resource = lambda p: ""
    _sublime.load_binary_resource = lambda p: None
    _sublime.cache_path = lambda: "/tmp/mdpp_cache_stub"
    _sublime.version = lambda: 4107
    sys.modules["sublime"] = _sublime

# ── markdown from mdpopups (bypasses mdpopups/__init__ which needs ST) ──────
_MDPOPUPS_DIR = os.path.expanduser(
    "~/Library/Application Support/Sublime Text/Lib/python38/mdpopups")


def _inject_markdown():
    if not os.path.isdir(_MDPOPUPS_DIR):
        print("mdpopups not found at %s; render tests will skip" % _MDPOPUPS_DIR)
        return
    if _MDPOPUPS_DIR not in sys.path:
        sys.path.insert(0, _MDPOPUPS_DIR)
    try:
        import markdown
        import markdown.extensions.attr_list as attr_list
        import markdown.extensions.codehilite as codehilite
        import markdown.extensions.fenced_code as fenced_code
        import markdown.extensions.footnotes as footnotes
        import markdown.extensions.nl2br as nl2br
        import markdown.extensions.tables as tables
        import markdown.extensions.toc as toc
    except Exception as e:
        print("markdown import failed (%s); render tests will skip" % e)
        return
    sys.path.insert(0, ROOT)
    import mpe_core.md_renderer as mdr
    mdr._md = markdown
    mdr.AttrListExtension = attr_list.AttrListExtension
    mdr.CodeHiliteExtension = codehilite.CodeHiliteExtension
    mdr.FencedCodeExtension = fenced_code.FencedCodeExtension
    mdr.FootnoteExtension = footnotes.FootnoteExtension
    mdr.Nl2BrExtension = nl2br.Nl2BrExtension
    mdr.TableExtension = tables.TableExtension
    mdr.TocExtension = toc.TocExtension
    mdr._HAS_MARKDOWN = True
    mdr._IMPORT_ERROR = None


def main():
    _inject_markdown()
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    import unittest
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(ROOT, "tests"),
                            pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
