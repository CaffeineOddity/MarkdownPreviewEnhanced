#!/usr/bin/env python3
"""Test runner for MarkdownPreviewEnhanced.

Works outside Sublime: injects a `sublime` stub, points md_renderer's
markdown import at the mdpopups dependency installed under ST's Lib/python3*,
then discovers tests in tests/.

Usage: python3 tests/run_all.py
"""
import importlib.util
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

# commands/ 里的 TextCommand 基类也需要 stub
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

# ── markdown from mdpopups (bypasses mdpopups/__init__ which needs ST) ──────
def _find_mdpopups():
    """探测 ST <data>/Lib/python3*/mdpopups，优先最新解释器版本。"""
    import glob
    import re
    roots = [
        os.path.expanduser("~/Library/Application Support/Sublime Text/Lib"),
        os.path.join(os.environ.get("APPDATA", ""), "Sublime Text", "Lib"),
        os.path.expanduser("~/.config/sublime-text/Lib"),
    ]
    for env_var in ("SUBLIME_PACKAGES", "XDG_DATA_HOME"):
        base = os.environ.get(env_var)
        if base:
            roots.append(os.path.join(base, "..", "Lib"))
    hits = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for sub in glob.glob(os.path.join(root, "python3*")):
            md = os.path.join(sub, "mdpopups")
            if not os.path.isdir(md):
                continue
            m = re.match(r"python(\d+)", os.path.basename(sub))
            hits.append((int(m.group(1)) if m else 0, md))
    hits.sort(reverse=True)
    return hits[0][1] if hits else None


def _inject_markdown():
    mdpopups_dir = _find_mdpopups()
    if not mdpopups_dir:
        print("mdpopups not found under ST Lib/python3*; render tests will skip")
        return
    try:
        mdpopups = types.ModuleType("mdpopups")
        mdpopups.__path__ = [mdpopups_dir]
        sys.modules["mdpopups"] = mdpopups
        markdown_dir = os.path.join(mdpopups_dir, "markdown")
        spec = importlib.util.spec_from_file_location(
            "mdpopups.markdown",
            os.path.join(markdown_dir, "__init__.py"),
            submodule_search_locations=[markdown_dir],
        )
        markdown = importlib.util.module_from_spec(spec)
        sys.modules["mdpopups.markdown"] = markdown
        mdpopups.markdown = markdown
        spec.loader.exec_module(markdown)
        import mdpopups.markdown.extensions.attr_list as attr_list
        import mdpopups.markdown.extensions.codehilite as codehilite
        import mdpopups.markdown.extensions.fenced_code as fenced_code
        import mdpopups.markdown.extensions.footnotes as footnotes
        import mdpopups.markdown.extensions.nl2br as nl2br
        import mdpopups.markdown.extensions.tables as tables
        import mdpopups.markdown.extensions.toc as toc
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
