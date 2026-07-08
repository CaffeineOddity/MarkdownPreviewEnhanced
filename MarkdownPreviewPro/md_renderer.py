"""Markdown → HTML rendering for MarkdownPreviewPro.

Uses python-markdown with extensions. Replaces mermaid fenced code blocks with
pre-rendered SVG before running Pygments on the rest.

python-markdown and Pygments are vendored under ``lib/`` so the plugin works
without depending on Package Control dependency installation.
"""
import os
import re
import sys

# ── debug file logging (shared with MarkdownPreviewPro.py) ──────────────
_DEBUG_LOG_PATH = os.path.expanduser("~/Downloads/MarkdownPreviewPro/debug.log")
os.makedirs(os.path.dirname(_DEBUG_LOG_PATH), exist_ok=True)


def _mdpp_log(msg):
    """Append a timestamped line to the debug log AND print to console."""
    import datetime
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    line = "[%s] [md_renderer] %s" % (ts, msg)
    print(line)
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# Make the vendored markdown/pygments importable. Use an absolute path so the
# import is unambiguous regardless of Sublime's working directory or sys.path
# ordering.
_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

try:
    import markdown as _md
    from markdown.extensions.codehilite import CodeHiliteExtension
    _HAS_MARKDOWN = True
    _IMPORT_ERROR = None
except Exception as _e:
    _HAS_MARKDOWN = False
    _IMPORT_ERROR = "%s: %s" % (type(_e).__name__, _e)
    import traceback as _tb
    _IMPORT_TRACEBACK = _tb.format_exc()
    # Log where markdown was actually found (or not) to help diagnose shadowing.
    try:
        import importlib.util as _ilu
        _spec = _ilu.find_spec("markdown")
        _WHERE = str(_spec.origin if _spec else "NOT FOUND")
    except Exception as _we:
        _WHERE = "find_spec failed: %s" % _we
    _mdpp_log("markdown import failed; resolved to: %s; lib=%s" % (_WHERE, _LIB))

from .mermaid_renderer import render_mermaid  # noqa: E402


# Match fenced mermaid code blocks at the source level (before markdown runs),
# so we can pull them out and render them to SVG independently of codehilite.
_MERMAID_FENCE_RE = re.compile(
    r"(?m)^(`{3,}|~{3,})mermaid[ \t]*\n(.*?)^\1[ \t]*$",
    re.DOTALL,
)

# Unique token used to splice pre-rendered mermaid SVG back in. We render the
# SVG *before* running markdown and insert a plain marker string, then swap the
# marker for the SVG afterward. This keeps mermaid output entirely outside
# codehilite's reach.
_MERMAID_MARKER_TMPL = "\x00MDPP_MERMAID_%d\x00"


def _has_markdown():
    return _HAS_MARKDOWN


def render(text, mermaid_theme="default"):
    """Render markdown text to an HTML fragment (string).

    Mermaid fenced code blocks are converted to inline SVG. Other fenced code
    blocks are syntax-highlighted via Pygments (codehilite).
    Returns (html_fragment, had_errors_list).
    """
    errors = []
    if not _HAS_MARKDOWN:
        # Fallback: escape and wrap in <pre>.
        import html as _html
        _dbg = _IMPORT_TRACEBACK if "_IMPORT_TRACEBACK" in globals() else _IMPORT_ERROR
        _mdpp_log("markdown import FAILED:\n%s" % _dbg)
        return "<pre>%s</pre>" % _html.escape(text), ["python-markdown not available: " + (_IMPORT_ERROR or "?")]

    _mdpp_log("md_renderer module=%s _HAS_MARKDOWN=%s md=%s" % (
        __file__, _HAS_MARKDOWN, getattr(_md, "__file__", "?")))

    # Pull mermaid blocks out of the source, render each to SVG now, and splice
    # in a NUL-delimited marker. After markdown runs we replace markers with
    # the pre-rendered SVG. This keeps mermaid output out of codehilite.
    rendered_svgs = []

    def _stash(m):
        code = m.group(2)
        svg, err = render_mermaid(code, theme=mermaid_theme)
        if err:
            errors.append(err)
            svg = '<pre class="mermaid-error"><code>%s</code></pre>' % _escape(code)
        else:
            svg = '<div class="mermaid-svg">%s</div>' % svg
        idx = len(rendered_svgs)
        rendered_svgs.append(svg)
        return _MERMAID_MARKER_TMPL % idx

    text = _MERMAID_FENCE_RE.sub(_stash, text)

    extensions = [
        "markdown.extensions.fenced_code",
        "markdown.extensions.tables",
        "markdown.extensions.attr_list",
        "markdown.extensions.toc",
        "markdown.extensions.nl2br",
        CodeHiliteExtension(guess_lang=False, linenums=False),
    ]
    try:
        html = _md.markdown(text, extensions=extensions, output_format="html5")
        _mdpp_log("markdown() OK; html len=%d; has_table=%s; has_codehilite=%s" % (
            len(html), "<table>" in html, "codehilite" in html))
    except Exception as e:
        _mdpp_log("markdown() with codehilite FAILED: %s" % e)
        # Retry without codehilite if Pygments misbehaves.
        try:
            html = _md.markdown(
                text,
                extensions=[
                    "markdown.extensions.fenced_code",
                    "markdown.extensions.tables",
                    "markdown.extensions.attr_list",
                    "markdown.extensions.toc",
                    "markdown.extensions.nl2br",
                ],
                output_format="html5",
            )
        except Exception as e2:
            import html as _html
            return "<pre>%s</pre>" % _html.escape(text), [str(e2)]

    # Swap mermaid markers back in for their SVG.
    for idx, svg in enumerate(rendered_svgs):
        html = html.replace(_MERMAID_MARKER_TMPL % idx, svg)

    # Full browser rendering — <table> works natively, no conversion needed.

    return html, errors


def _escape(s):
    import html as _html
    return _html.escape(s)


