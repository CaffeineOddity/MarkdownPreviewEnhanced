"""Markdown → HTML rendering for MarkdownPreviewEnhanced.

Features:
  - Frontmatter stripping
  - Mermaid → SVG (via mermaid_renderer)
  - Tables, fenced code, codehilite (Pygments), TOC, attr_list, nl2br, footnotes
  - GFM task lists
  - Relative image rewrite (for local server or file://)
  - Heading data-line attributes for scroll sync
  - Math is extracted *before* markdown (so nl2br / escapes cannot break it),
    emitted as ``.mdpp-math`` nodes, and rendered client-side by KaTeX.
"""
import os
import re
import hashlib

# ── debug file logging ──────────────────────────────────────────────────────
_DEBUG_LOG_PATH = os.path.expanduser("~/Downloads/MarkdownPreviewEnhanced/debug.log")


def _mdpp_log(msg):
    import datetime
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    line = "[%s] [md_renderer] %s" % (ts, msg)
    print(line)
    try:
        os.makedirs(os.path.dirname(_DEBUG_LOG_PATH), exist_ok=True)
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


try:
    # 让 mpe_core 内 vendored 的 markdown / pygments 同时以「相对包」和「顶层名」两种身份
    # 可被导入，且两条路径解析到 *同一份* 模块对象。
    #
    # 背景：python-markdown / pygments 内部大量使用绝对导入
    #   - `from markdown.treeprocessors import ...`（legacy_attrs）
    #   - `from pygments import highlight`（codehilite）
    #   - `from pygments.util import ...`（pygments/__init__.py 顶部）
    # 若只做 `from . import markdown` 而不注册顶层名，这些绝对导入会 No module named。
    #
    # 关键陷阱 1（pygments 循环导入）：pygments/__init__.py 在模块体顶部就执行
    #   `from pygments.util import ...`。若直接 `from . import pygments`，import 机制在
    #   __init__.py 执行期间尚未把顶层名 pygments 写入 sys.modules，于是这一行立即报
    #   No module named 'pygments'。解法：先在 sys.modules['pygments'] 放一个占位包，
    #   __path__ 指向真实 pygments 目录，再用 importlib 真正加载 .pygments（加载时就地
    #   填充占位包属性），这样 __init__ 里的 `from pygments.util import ...` 能在
    #   占位包 __path__ 下找到子模块。
    #
    # 关键陷阱 2（Extension 类身份分裂）：markdown.core 顶层 `from .extensions import
    #   Extension` 得到的是 MarkdownPreviewEnhanced.mpe_core.markdown.extensions.Extension；
    #   而 build_extension 把字符串 "markdown.extensions.fenced_code" 交给 importlib，
    #   该模块 `from . import Extension` 解析出的却是 markdown.extensions.Extension。
    #   两个 Extension 来自不同模块对象 → isinstance 判定失败 → TypeError。解法：把
    #   sys.modules['markdown'] 直接指向相对包对象 _md（而非另造占位包），让顶层名与
    #   相对包共享同一份模块树，两条导入路径得到同一个 Extension 类。
    import sys as _sys
    import types as _types
    import importlib as _importlib
    import os as _os

    from . import markdown as _md
    # 让 vendored markdown 包同时以相对名（MarkdownPreviewEnhanced.mpe_core.markdown）
    # 和顶层名（markdown）可被导入，且两条路径复用同一份模块对象。
    #
    # 关键陷阱：markdown.core 顶层 `from .extensions import Extension` 得到的是相对包的
    # Extension 类；而 build_extension 把字符串 "markdown.extensions.fenced_code" 交给
    # importlib，该模块 `from . import Extension` 又解析出顶层名下的 Extension 类。若
    # 两条路径是两份独立模块对象 → Extension 类身份分裂 → isinstance 失败 →
    # TypeError: Extension ... must be of type ...。
    #
    # 解法：把已加载的相对包及其所有子模块，按顶层名（markdown / markdown.extensions /
    # markdown.util …）逐一注册到 sys.modules 指向同一对象；再把顶层 markdown 的
    # __name__ 归一为 "markdown"，使后续 build_extension 的绝对导入命中同一模块树。
    _MPE_PREFIX = __package__ + ".markdown"
    for _k in list(_sys.modules):
        if _k == _MPE_PREFIX or _k.startswith(_MPE_PREFIX + "."):
            _sys.modules["markdown" + _k[len(_MPE_PREFIX):]] = _sys.modules[_k]
    _md = _sys.modules["markdown"]
    _md.__name__ = "markdown"

    _pyg_dir = _os.path.join(_os.path.dirname(__file__), "pygments")
    _pyg = _types.ModuleType("pygments")
    _pyg.__path__ = [_pyg_dir]
    _pyg.__package__ = "pygments"
    _sys.modules["pygments"] = _pyg
    _importlib.import_module(".pygments", __package__)
    _pygments = _sys.modules["pygments"]

    from .markdown.extensions.codehilite import CodeHiliteExtension
    from .markdown.extensions.toc import TocExtension
    _HAS_MARKDOWN = True
    _IMPORT_ERROR = None
except Exception as _e:
    _HAS_MARKDOWN = False
    _IMPORT_ERROR = "%s: %s" % (type(_e).__name__, _e)
    import traceback as _tb
    _IMPORT_TRACEBACK = _tb.format_exc()
    _mdpp_log("markdown import failed: %s" % _IMPORT_ERROR)

from .katex_renderer import render_tex_batch  # noqa: E402

_ECHARTS_FENCE_RE = re.compile(
    r"(?m)^(`{3,}|~{3,})echarts[ \t]*\n(.*?)^\1[ \t]*$",
    re.DOTALL,
)
_ECHARTS_MARKER_TMPL = "\x00MDPP_ECHARTS_%d\x00"

_MERMAID_FENCE_RE = re.compile(
    r"(?m)^(`{3,}|~{3,})mermaid[ \t]*\n(.*?)^\1[ \t]*$",
    re.DOTALL,
)
_MERMAID_MARKER_TMPL = "\x00MDPP_MERMAID_%d\x00"

# Fenced code (any language) — protect before math extraction.
_FENCE_RE = re.compile(
    r"(?m)^(`{3,}|~{3,}).*?\n.*?\1[ \t]*$",
    re.DOTALL,
)
# Inline code spans
_INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")

# Math delimiters (processed after code is stashed). Order matters.
_MATH_DISPLAY_DOLLAR_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_MATH_DISPLAY_BRACKET_RE = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)
_MATH_INLINE_PAREN_RE = re.compile(r"\\\((.+?)\\\)", re.DOTALL)
# Single $ … $ : not $$ , not escaped, no leading/trailing space inside.
_MATH_INLINE_DOLLAR_RE = re.compile(
    r"(?<![\\$])\$(?!\$)(?!\s)((?:[^$\n\\]|\\.)+?)(?<!\s)\$(?!\$)"
)

_MATH_MARKER_TMPL = "@@MDPPMATH%d@@"
_CODE_MARKER_TMPL = "@@MDPPCODE%d@@"

# YAML frontmatter at document start
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n.*?\r?\n---[ \t]*\r?\n", re.DOTALL)

# ATX headings for line mapping
_ATX_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")

# HTML img src rewriter
_IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=["\'])([^"\']+)(["\'])', re.IGNORECASE)

# Task list items produced by markdown as plain text inside <li>
_TASK_OPEN_RE = re.compile(
    r"(<li>)(\s*)\[ \]\s+",
    re.IGNORECASE,
)
_TASK_DONE_RE = re.compile(
    r"(<li>)(\s*)\[x\]\s+",
    re.IGNORECASE,
)


def set_debug_log_path(path):
    global _DEBUG_LOG_PATH
    _DEBUG_LOG_PATH = path


def _escape(s, quote=False):
    import html as _html
    return _html.escape(s, quote=quote)


def strip_frontmatter(text):
    """Remove leading YAML frontmatter.

    Returns (body, frontmatter_or_None, line_offset) where *line_offset* is the
    number of lines removed so heading data-line values still match the editor.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return text, None, 0
    fm = m.group(0)
    # Count newlines removed so 1-based line numbers stay buffer-accurate.
    offset = fm.count("\n")
    return text[m.end():], fm, offset


def _collect_heading_lines(text):
    """Return list of (line_no 1-based, level, title) for ATX headings."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        m = _ATX_HEADING_RE.match(line)
        if m:
            title = m.group(2).strip()
            # strip inline code/emphasis markers for rough match
            out.append((i, len(m.group(1)), title))
    return out


def _inject_heading_lines(html, heading_lines):
    """Add data-line attributes to h1–h6 in document order."""
    if not heading_lines:
        return html
    idx = [0]

    def repl(m):
        tag = m.group(1)
        rest = m.group(2)
        if idx[0] < len(heading_lines):
            line = heading_lines[idx[0]][0]
            idx[0] += 1
            return '<%s data-line="%d"%s' % (tag, line, rest)
        return m.group(0)

    return re.sub(r"<(h[1-6])(\b[^>]*>)", repl, html, flags=re.IGNORECASE)


def _apply_task_lists(html):
    html = _TASK_OPEN_RE.sub(
        r'\1\2<input type="checkbox" class="task-list-item-checkbox" disabled> ',
        html,
    )
    html = _TASK_DONE_RE.sub(
        r'\1\2<input type="checkbox" class="task-list-item-checkbox" checked disabled> ',
        html,
    )
    # mark parent lists
    if "task-list-item-checkbox" in html:
        html = html.replace("<ul>", '<ul class="contains-task-list">', 1)
        # crude: add class to all ul that contain checkboxes via second pass
        parts = html.split("<ul>")
        rebuilt = [parts[0]]
        for part in parts[1:]:
            if "task-list-item-checkbox" in part.split("</ul>")[0]:
                rebuilt.append('<ul class="contains-task-list">' + part)
            else:
                rebuilt.append("<ul>" + part)
        html = "".join(rebuilt)
        html = re.sub(
            r"<li>(\s*<input type=\"checkbox\" class=\"task-list-item-checkbox\")",
            r'<li class="task-list-item">\1',
            html,
        )
    return html


def rewrite_image_srcs(html, base_dir, mode="server"):
    """Rewrite relative image src attributes.

    mode:
      - "server": prefix with /doc/
      - "file": convert to absolute file:// URLs
      - "export": convert to absolute file:// (or leave http)
    """
    if not base_dir:
        return html

    def repl(m):
        prefix, src, suffix = m.group(1), m.group(2), m.group(3)
        s = src.strip()
        if not s or s.startswith(("http://", "https://", "data:", "file://", "/doc/")):
            return m.group(0)
        # absolute filesystem path
        if os.path.isabs(s):
            path = s
        else:
            path = os.path.normpath(os.path.join(base_dir, s))
        if mode == "server":
            # encode path relative to base_dir for /doc/ serving
            try:
                rel = os.path.relpath(path, base_dir)
            except ValueError:
                rel = os.path.basename(path)
            rel = rel.replace("\\", "/")
            if rel.startswith("../"):
                # outside doc dir — fall back to file URL for export-ish safety
                return '%sfile://%s%s' % (prefix, path, suffix)
            return "%s/doc/%s%s" % (prefix, rel, suffix)
        # file / export
        return "%sfile://%s%s" % (prefix, path, suffix)

    return _IMG_SRC_RE.sub(repl, html)


def content_hash(html):
    return hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]


def _math_placeholder_html(tex, display, rendered=None):
    """Emit math HTML.

    If *rendered* (server-side KaTeX HTML) is provided, wrap it so CSS still
    applies. Otherwise emit a client-side ``.mdpp-math`` marker.
    """
    tex = (tex or "").strip()
    attr = _escape(tex, quote=True)
    if rendered:
        # Already painted by Node/KaTeX — mark rendered so client skips it.
        if display:
            return (
                '<div class="mdpp-math mdpp-math-display mdpp-math-ssr" '
                'data-display="true" data-tex="%s" data-mdpp-rendered="ssr">%s</div>'
                % (attr, rendered)
            )
        return (
            '<span class="mdpp-math mdpp-math-inline mdpp-math-ssr" '
            'data-display="false" data-tex="%s" data-mdpp-rendered="ssr">%s</span>'
            % (attr, rendered)
        )
    body = _escape(tex)
    if display:
        return (
            '<div class="mdpp-math mdpp-math-display" data-display="true" '
            'data-tex="%s">%s</div>' % (attr, body)
        )
    return (
        '<span class="mdpp-math mdpp-math-inline" data-display="false" '
        'data-tex="%s">%s</span>' % (attr, body)
    )


def _extract_math(text):
    """Pull LaTeX out of *text* so markdown cannot mangle delimiters.

    Returns (text_with_markers, list_of_html_fragments).
    Code fences and inline code are temporarily protected first.
    """
    code_stash = []
    # (tex, display) pending server-side render
    math_jobs = []

    def _stash_code(m):
        code_stash.append(m.group(0))
        return _CODE_MARKER_TMPL % (len(code_stash) - 1)

    # Protect fenced then inline code
    text = _FENCE_RE.sub(_stash_code, text)
    text = _INLINE_CODE_RE.sub(_stash_code, text)

    def _stash_math(tex, display):
        idx = len(math_jobs)
        math_jobs.append({"tex": (tex or "").strip(), "display": bool(display)})
        marker = _MATH_MARKER_TMPL % idx
        # Display math as its own block so markdown won't wrap a <div> in <p>.
        if display:
            return "\n\n%s\n\n" % marker
        return marker

    def _disp_dollar(m):
        return _stash_math(m.group(1), True)

    def _disp_bracket(m):
        return _stash_math(m.group(1), True)

    def _inl_paren(m):
        return _stash_math(m.group(1), False)

    def _inl_dollar(m):
        return _stash_math(m.group(1), False)

    text = _MATH_DISPLAY_DOLLAR_RE.sub(_disp_dollar, text)
    text = _MATH_DISPLAY_BRACKET_RE.sub(_disp_bracket, text)
    text = _MATH_INLINE_PAREN_RE.sub(_inl_paren, text)
    text = _MATH_INLINE_DOLLAR_RE.sub(_inl_dollar, text)

    # Restore code so markdown can process it normally
    for i, block in enumerate(code_stash):
        text = text.replace(_CODE_MARKER_TMPL % i, block)

    # Server-side KaTeX (Node). Batch once for speed.
    math_html = []
    if math_jobs:
        batch = None
        try:
            batch = render_tex_batch(math_jobs)
        except Exception as e:
            _mdpp_log("katex batch failed: %s" % e)
            batch = None
        if batch is None:
            batch = [None] * len(math_jobs)
        ssr_ok = sum(1 for h in batch if h)
        if ssr_ok:
            _mdpp_log("katex SSR %d/%d formula(s)" % (ssr_ok, len(math_jobs)))
        elif math_jobs:
            _mdpp_log("katex SSR unavailable; client fallback for %d formula(s)" % len(math_jobs))
        for job, rendered in zip(math_jobs, batch):
            math_html.append(
                _math_placeholder_html(job["tex"], job["display"], rendered=rendered)
            )

    return text, math_html


def _restore_math(html, math_html):
    for i, frag in enumerate(math_html):
        marker = _MATH_MARKER_TMPL % i
        # Markdown may wrap a lone marker in <p>…</p>
        html = html.replace("<p>%s</p>" % marker, frag)
        html = html.replace("<p>%s</p>\n" % marker, frag + "\n")
        html = html.replace(marker, frag)
    return html


def render(
    text,
    mermaid_theme="default",
    base_dir=None,
    image_mode="server",
    enable_footnotes=True,
    enable_task_lists=True,
    enable_toc=True,
    strip_yaml=True,
    enable_math=True,
):
    """Render markdown text to HTML.

    Returns dict:
      body_html, toc_html, errors, hash, heading_lines
    """
    errors = []
    if not _HAS_MARKDOWN:
        _dbg = _IMPORT_TRACEBACK if "_IMPORT_TRACEBACK" in globals() else _IMPORT_ERROR
        _mdpp_log("markdown import FAILED:\n%s" % _dbg)
        body = "<pre>%s</pre>" % _escape(text)
        return {
            "body_html": body,
            "toc_html": "",
            "errors": ["python-markdown not available: " + (_IMPORT_ERROR or "?")],
            "hash": content_hash(body),
            "heading_lines": [],
        }

    line_offset = 0
    if strip_yaml:
        text, _fm, line_offset = strip_frontmatter(text)

    heading_lines = _collect_heading_lines(text)
    if line_offset:
        heading_lines = [
            (ln + line_offset, level, title)
            for ln, level, title in heading_lines
        ]

    # ECharts extraction
    echarts_html_parts = {}

    def _stash_echart(m):
        json_code = m.group(2).strip()
        cid = "mdpp-echart-%d" % len(echarts_html_parts)
        # Container div + embedded config script
        echarts_html_parts[cid] = (
            '<div class="mdpp-echarts-wrap" style="max-width:780px;margin:1.2em auto">\n'
            '<div class="mdpp-echarts" id="%s" style="width:100%%;height:420px"></div>\n'
            '</div>\n'
            '<script type="application/json" class="mdpp-echarts-config">%s</script>'
        ) % (cid, json_code)
        return "\x00MDPP_ECHART_%s\x00" % cid

    text = _ECHARTS_FENCE_RE.sub(_stash_echart, text)

    # Mermaid extraction — keep raw code for client-side rendering (no Node.js).
    rendered_svgs = []

    def _stash(m):
        code = m.group(2)
        idx = len(rendered_svgs)
        rendered_svgs.append(
            '<pre class="mermaid">%s</pre>' % code
        )
        return _MERMAID_MARKER_TMPL % idx

    text = _MERMAID_FENCE_RE.sub(_stash, text)

    # Math extraction (must be after mermaid, before markdown convert)
    math_html = []
    if enable_math:
        text, math_html = _extract_math(text)
        if math_html:
            _mdpp_log("protected %d math region(s)" % len(math_html))

    extensions = [
        "markdown.extensions.fenced_code",
        "markdown.extensions.tables",
        "markdown.extensions.attr_list",
        "markdown.extensions.nl2br",
        TocExtension(permalink=False, toc_depth=6),
        CodeHiliteExtension(guess_lang=False, linenums=False),
    ]
    if enable_footnotes:
        extensions.append("markdown.extensions.footnotes")

    toc_html = ""
    try:
        md = _md.Markdown(extensions=extensions, output_format="html5")
        html = md.convert(text)
        toc_html = getattr(md, "toc", "") or ""
        _mdpp_log("markdown() OK; html len=%d; has_table=%s" % (
            len(html), "<table>" in html))
    except Exception as e:
        _mdpp_log("markdown() FAILED: %s" % e)
        try:
            fallback_ext = [
                "markdown.extensions.fenced_code",
                "markdown.extensions.tables",
                "markdown.extensions.attr_list",
                "markdown.extensions.nl2br",
            ]
            if enable_footnotes:
                fallback_ext.append("markdown.extensions.footnotes")
            md = _md.Markdown(extensions=fallback_ext, output_format="html5")
            html = md.convert(text)
            toc_html = getattr(md, "toc", "") or ""
        except Exception as e2:
            body = "<pre>%s</pre>" % _escape(text)
            return {
                "body_html": body,
                "toc_html": "",
                "errors": [str(e2)],
                "hash": content_hash(body),
                "heading_lines": heading_lines,
            }

    for idx, svg in enumerate(rendered_svgs):
        html = html.replace(_MERMAID_MARKER_TMPL % idx, svg)

    for cid, frag in echarts_html_parts.items():
        marker = "\x00MDPP_ECHART_%s\x00" % cid
        # Unwrap <p> tags that markdown may have added around the block marker.
        html = html.replace("<p>%s</p>" % marker, frag)
        html = html.replace(marker, frag)

    if math_html:
        html = _restore_math(html, math_html)

    if enable_task_lists:
        html = _apply_task_lists(html)

    html = _inject_heading_lines(html, heading_lines)
    html = rewrite_image_srcs(html, base_dir, mode=image_mode)

    if not enable_toc:
        toc_html = ""

    return {
        "body_html": html,
        "toc_html": toc_html,
        "errors": errors,
        "hash": content_hash(html + toc_html),
        "heading_lines": heading_lines,
    }
