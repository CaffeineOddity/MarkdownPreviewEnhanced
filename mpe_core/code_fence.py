"""Fenced-code metadata: ``title``, ``{highlight lines}`` and line numbers.

Parses a fence info string like ``python title="app.py" {1,3-5}`` into its
three parts, stashes any block that carries a title or highlight out of
python-markdown's reach (the bundled fenced_code/regex chokes on extra info
tokens), and restores each as a ``.mdpp-code`` block containing the Pygments
highlight table plus an optional header with a Copy button.

Blocks without metadata pass through untouched, so the common case keeps the
existing codehilite output byte-for-byte.

Pygments ships inside mdpopups (``mdpopups.pygments``), not as a top-level
package, on Sublime's plugin host. If neither import works the block degrades
to escaped ``<pre>`` text rather than failing.
"""
import re
import sys

_MARKER_TMPL = "\x00MDPP_FENCE_%d\x00"

# Opening fence line: optional 0–3 leading spaces, ``` or ~~~, then info.
_FENCE_OPEN_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})([ \t]*[^\n]*)$")

_TITLE_RE = re.compile(r'title\s*=\s*"([^"]*)"')
_HL_RE = re.compile(r"\{\s*([0-9][0-9,\-\s]*)\s*\}")


def parse_fence_info(info):
    """Return ``(lang, title_or_None, hl_lines_or_None)``.

    ``lang`` is the first whitespace token that remains after ``title="…"``
    and ``{…}`` are removed (order-independent). ``hl_lines`` is a sorted list
    of positive ints, or ``None`` when no highlight brace is present.
    """
    info = (info or "").strip()
    title = None
    m = _TITLE_RE.search(info)
    if m:
        title = m.group(1)
        info = (info[:m.start()] + " " + info[m.end():]).strip()

    hl = None
    m = _HL_RE.search(info)
    if m:
        hl = _parse_hl(m.group(1))
        info = (info[:m.start()] + " " + info[m.end():]).strip()

    lang = info.split()[0] if info.strip() else ""
    return lang, title, hl


def _parse_hl(spec):
    lines = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            lo, hi = lo.strip(), hi.strip()
            if lo.isdigit() and hi.isdigit():
                a, b = int(lo), int(hi)
                if a > b:
                    a, b = b, a
                for n in range(a, b + 1):
                    if n >= 1:
                        lines.add(n)
        elif part.isdigit():
            n = int(part)
            if n >= 1:
                lines.add(n)
    return sorted(lines) or None


def _is_close(line, fence_char, fence_len):
    """True if *line* is a closing fence for the given marker char/length."""
    s = line.rstrip("\r\n").strip()
    return bool(s) and s == fence_char * len(s) and len(s) >= fence_len


def extract_code_fences(text):
    """Stash every closed fenced block.

    Returns ``(text, stash)`` where *stash* is an ordered list of
    ``{"lang", "title", "hl", "code"}`` and stashed blocks are replaced by
    ``\\x00MDPP_FENCE_<i>\\x00`` markers. Unclosed fences pass through as-is.
    """
    stash = []
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        m = _FENCE_OPEN_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        fence_char = m.group(2)[0]
        fence_len = len(m.group(2))
        info = m.group(3)
        lang, title, hl = parse_fence_info(info)

        j = i + 1
        code_lines = []
        while j < len(lines) and not _is_close(lines[j], fence_char, fence_len):
            code_lines.append(lines[j])
            j += 1
        if j >= len(lines):
            # Unclosed fence: leave the rest of the document verbatim.
            out.extend(lines[i:])
            break

        idx = len(stash)
        stash.append({
            "lang": lang,
            "title": title,
            "hl": hl,
            "code": "\n".join(code_lines),
        })
        out.append(_MARKER_TMPL % idx)
        i = j + 1
    return "\n".join(out), stash


def restore_code_fences(html, stash):
    """Replace markers with rendered ``.mdpp-code`` blocks (unwrapping <p>)."""
    for idx, meta in enumerate(stash):
        marker = _MARKER_TMPL % idx
        frag = render_block(meta)
        html = html.replace("<p>%s</p>" % marker, frag)
        html = html.replace("<p>%s</p>\n" % marker, frag + "\n")
        html = html.replace(marker, frag)
    return html


def pygments_modules():
    """Return ``(pygments, lexers, formatters)`` or raise ``ImportError``.

    Sublime's plugin host has no top-level ``pygments``; mdpopups vendors it as
    ``mdpopups.pygments`` and rewrites ``pygments.*`` imports to that name.
    Prefer the real package when a non-Sublime runner has one installed.
    """
    try:
        import pygments
        import pygments.lexers as lexers
        import pygments.formatters as formatters
        return pygments, lexers, formatters
    except ImportError:
        pass
    import mdpopups.pygments as pygments
    import mdpopups.pygments.lexers as lexers
    import mdpopups.pygments.formatters as formatters
    # codehilite does ``from pygments import highlight`` at import time.
    sys.modules.setdefault("pygments", pygments)
    return pygments, lexers, formatters


def render_block(meta):
    """Render one stashed block to a ``.mdpp-code`` fragment."""
    from html import escape

    lang = meta["lang"] or ""
    title = meta["title"]
    hl = meta["hl"]
    code = meta["code"]

    try:
        pygments, lexers, formatters = pygments_modules()
    except ImportError:
        highlighted = "<pre><code>%s</code></pre>" % escape(code)
    else:
        lexer = lexers.TextLexer()
        if lang:
            try:
                lexer = lexers.get_lexer_by_name(lang)
            except Exception:
                lexer = lexers.TextLexer()
        formatter = formatters.HtmlFormatter(
            cssclass="codehilite",
            noclasses=False,
            linenos="table",
            hl_lines=hl or [],
            wrapcode=False,
        )
        highlighted = pygments.highlight(code, lexer, formatter)

    return '<div class="mdpp-code">%s%s</div>' % (
        _build_header(title, lang), highlighted)


def _build_header(title, lang):
    pieces = []
    if title:
        from html import escape
        pieces.append(
            '<span class="mdpp-code-title">%s</span>' % escape(title))
    if lang:
        from html import escape
        pieces.append(
            '<span class="mdpp-code-lang">%s</span>' % escape(lang))
    return (
        '<div class="mdpp-code-header">%s'
        '<button class="mdpp-code-copy" aria-label="Copy code">Copy</button>'
        '</div>' % "".join(pieces)
    )