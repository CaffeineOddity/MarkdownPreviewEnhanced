"""Markdown → HTML rendering for MarkdownPreviewEnhanced.

Features:
  - Frontmatter stripping
  - Mermaid → SVG (via mermaid_renderer)
  - Tables, fenced code, codehilite (Pygments), TOC, attr_list, nl2br, footnotes
  - GFM task lists
  - Relative image rewrite (for local server or file://)
  - Heading and block-level data-line attributes for scroll sync
  - Math is extracted *before* markdown (so nl2br / escapes cannot break it),
    emitted as ``.mdpp-math`` nodes, and rendered client-side by KaTeX.
"""
import os
import re
import hashlib

from .log import debug, error


def _load_mdpopups():
    """Import markdown + pygments from the mdpopups dependency.

    Primary path: Package Control injects mdpopups into sys.path when this
    package is listed in ``installed_packages`` (declared via
    ``dependencies.json``). That is the supported, regular flow.

    Fallback: when this package is installed manually as a .sublime-package
    (not registered with Package Control), PC does not wire up the dependency
    and ``import mdpopups`` fails. mdpopups is still physically present under
    ``<ST data>/Lib/python38/`` (PC installs it for other packages too), so we
    locate that directory and put it on sys.path ourselves. This keeps a
    manual/development zip install working without PC's dependency machinery.
    """
    try:
        from mdpopups import markdown as _md
        from mdpopups.markdown.extensions.attr_list import AttrListExtension
        from mdpopups.markdown.extensions.codehilite import CodeHiliteExtension
        from mdpopups.markdown.extensions.fenced_code import FencedCodeExtension
        from mdpopups.markdown.extensions.footnotes import FootnoteExtension
        from mdpopups.markdown.extensions.nl2br import Nl2BrExtension
        from mdpopups.markdown.extensions.tables import TableExtension
        from mdpopups.markdown.extensions.toc import TocExtension
        return {
            "md": _md,
            "AttrList": AttrListExtension,
            "CodeHilite": CodeHiliteExtension,
            "FencedCode": FencedCodeExtension,
            "Footnotes": FootnoteExtension,
            "Nl2Br": Nl2BrExtension,
            "Tables": TableExtension,
            "Toc": TocExtension,
        }
    except Exception:
        pass

    # Fallback: locate mdpopups under ST's <data>/Lib without going through
    # Package Control's dependency injection. The plugin-host Python version
    # differs across ST builds (python33 / python38 / python314), so probe
    # Lib/python3*/mdpopups instead of hard-coding one version.
    import sys
    import glob

    def _py_ver(path):
        m = re.match(r"python(\d+)", os.path.basename(path))
        return int(m.group(1)) if m else 0

    lib_roots = []
    # <ST data>/Lib — canonical PC dependency install location.
    for env_var in ("SUBLIME_PACKAGES", "XDG_DATA_HOME"):
        base = os.environ.get(env_var)
        if base:
            lib_roots.append(os.path.join(base, "..", "Lib"))
    # macOS / Windows / Linux default data dirs.
    lib_roots.append(
        os.path.expanduser("~/Library/Application Support/Sublime Text/Lib"))
    lib_roots.append(
        os.path.join(os.environ.get("APPDATA", ""), "Sublime Text", "Lib"))
    lib_roots.append(os.path.expanduser("~/.config/sublime-text/Lib"))

    candidates = []
    for root in lib_roots:
        if not root or not os.path.isdir(root):
            continue
        # 优先新宿主版本(python314 > python38 > python33)。
        for sub in sorted(
            glob.glob(os.path.join(root, "python3*")),
            key=_py_ver, reverse=True,
        ):
            if os.path.isdir(os.path.join(sub, "mdpopups")):
                candidates.append(sub)
    seen = set()
    for c in candidates:
        if not c or c in seen or not os.path.isdir(c):
            continue
        seen.add(c)
        if not os.path.isdir(os.path.join(c, "mdpopups")):
            continue
        if c not in sys.path:
            sys.path.insert(0, c)
        debug("mdpopups fallback: using %s" % c)
        try:
            from mdpopups import markdown as _md
            from mdpopups.markdown.extensions.attr_list import AttrListExtension
            from mdpopups.markdown.extensions.codehilite import CodeHiliteExtension
            from mdpopups.markdown.extensions.fenced_code import FencedCodeExtension
            from mdpopups.markdown.extensions.footnotes import FootnoteExtension
            from mdpopups.markdown.extensions.nl2br import Nl2BrExtension
            from mdpopups.markdown.extensions.tables import TableExtension
            from mdpopups.markdown.extensions.toc import TocExtension
            return {
                "md": _md,
                "AttrList": AttrListExtension,
                "CodeHilite": CodeHiliteExtension,
                "FencedCode": FencedCodeExtension,
                "Footnotes": FootnoteExtension,
                "Nl2Br": Nl2BrExtension,
                "Tables": TableExtension,
                "Toc": TocExtension,
            }
        except Exception as _e:
            debug("mdpopups fallback failed at %s: %s" % (c, _e))
            # Remove so we don't leave a broken path confusing later imports.
            try:
                sys.path.remove(c)
            except ValueError:
                pass
    return None


try:
    _mods = _load_mdpopups()
    if _mods is None:
        raise ImportError("mdpopups not found via PC or fallback paths")
    _md = _mods["md"]
    AttrListExtension = _mods["AttrList"]
    CodeHiliteExtension = _mods["CodeHilite"]
    FencedCodeExtension = _mods["FencedCode"]
    FootnoteExtension = _mods["Footnotes"]
    Nl2BrExtension = _mods["Nl2Br"]
    TableExtension = _mods["Tables"]
    TocExtension = _mods["Toc"]
    _HAS_MARKDOWN = True
    _IMPORT_ERROR = None
except Exception as _e:
    _HAS_MARKDOWN = False
    _IMPORT_ERROR = "%s: %s" % (type(_e).__name__, _e)
    import traceback as _tb
    _IMPORT_TRACEBACK = _tb.format_exc()
    error("markdown import failed: %s" % _IMPORT_ERROR)

from .emoji_map import EMOJI_ALIASES
from .katex_renderer import render_tex_batch  # noqa: E402
from .mdpp_inline import MdppInlineExtension  # noqa: E402

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

# GFM emoji shortcode :alias: — alias chars and non-word delimiters both sides.
# Word boundaries keep `foo:bar:`/`a:b` intact while matching prose and the
# punctuation-delimited cases GitHub renders (start of line, "(:smile:)"...).
_EMOJI_ALIAS_RE = r"[A-Za-z0-9_+-]+"
_EMOJI_RE = re.compile(
    r"(?<![A-Za-z0-9_+-]):(" + _EMOJI_ALIAS_RE + r"):(?![A-Za-z0-9_+-])"
)

# ATX headings for line mapping
_ATX_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")

# HTML img src rewriter
_IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=["\'])([^"\']+)(["\'])', re.IGNORECASE)

# HTML a href rewriter
_A_HREF_RE = re.compile(r'(<a\b[^>]*?\bhref=["\'])([^"\']+)(["\'])', re.IGNORECASE)
_A_TAG_RE = re.compile(r"<a\b[^>]*>", re.IGNORECASE)

# Task list items produced by markdown as plain text inside <li>
_TASK_OPEN_RE = re.compile(
    r"(<li>)(\s*)\[ \]\s+",
    re.IGNORECASE,
)
_TASK_DONE_RE = re.compile(
    r"(<li>)(\s*)\[x\]\s+",
    re.IGNORECASE,
)


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
    in_fence = False
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
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


# ── 块级元素 data-line 注入 ──────────────────────────────────────────────────

# 源码块级结构识别正则
_LIST_ITEM_RE = re.compile(r"^([-*+]|[0-9]+\.)\s+")
_TABLE_ROW_RE = re.compile(r"^\|.*\|\s*$")
_TABLE_SEP_RE = re.compile(r"^[\s|:-]+$")
_HR_RE = re.compile(r"^(-{3,}|\*{3,}|_{3,})\s*$")
_FENCE_LANG_RE = re.compile(r"^(`{3,}|~{3,})(\w+)", re.IGNORECASE)


def _collect_block_lines(text):
    """逐行扫描源码，返回 [(line_no 1-based, tag)] 块级元素列表。

    heading 已由 _collect_heading_lines 处理，这里跳过。
    tag 取值: p, li, blockquote, pre, table, tr
    不标 ul/ol（容器）；blockquote 只标自身不标内部 p；
    table 标首个 | 行（表头），tr 标每个数据行。
    mermaid fence 标 <pre class="mermaid"> 的起止行；echarts 渲染成 div，跳过。
    $$...$$ 数学块渲染后是 <div>，跳过。
    连续非空行 markdown 合并为一个 <p>，只标首行；
    连续 > 行合并为一个 <blockquote>，只标首行。
    """
    out = []
    in_fence = False
    in_table = False
    in_paragraph = False
    in_blockquote = False
    in_math = False
    fence_start = 0
    fence_lang = ""
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        # 数学块 $$...$$
        if stripped == "$$" or stripped.startswith("$$"):
            if not in_math:
                in_math = True
            else:
                in_math = False
            in_paragraph = False
            in_blockquote = False
            continue
        if in_math:
            continue
        # fenced code / mermaid. Record on close so we have an end line.
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_paragraph = False
            in_blockquote = False
            in_table = False
            if not in_fence:
                in_fence = True
                fence_start = i
                m = _FENCE_LANG_RE.match(stripped)
                fence_lang = m.group(2).lower() if m else ""
            else:
                in_fence = False
                if fence_lang != "echarts":
                    out.append((fence_start, "pre", i))
                fence_lang = ""
            continue
        if in_fence:
            continue
        # heading: 跳过，heading_lines 已处理
        if _ATX_HEADING_RE.match(stripped):
            in_paragraph = False
            in_blockquote = False
            in_table = False
            continue
        # table row
        if _TABLE_ROW_RE.match(stripped):
            in_paragraph = False
            in_blockquote = False
            if not in_table:
                out.append((i, "table"))
                in_table = True
            elif not _TABLE_SEP_RE.match(stripped):
                out.append((i, "tr"))
            continue
        else:
            in_table = False
        # list item
        if _LIST_ITEM_RE.match(stripped):
            in_paragraph = False
            in_blockquote = False
            out.append((i, "li"))
            continue
        # blockquote: 连续 > 行合并为一个 <blockquote>，只标首行
        if stripped.startswith(">"):
            in_paragraph = False
            if not in_blockquote:
                out.append((i, "blockquote"))
                in_blockquote = True
            continue
        else:
            in_blockquote = False
        # horizontal rule (渲染为 <hr>,不标 data-line)
        if _HR_RE.match(stripped):
            in_paragraph = False
            continue
        # paragraph: 连续非空行合并为一个 <p>，只标首行
        if stripped:
            if not in_paragraph:
                out.append((i, "p"))
                in_paragraph = True
        else:
            in_paragraph = False
    if in_fence and fence_lang != "echarts":
        out.append((fence_start, "pre", i))
    return out


def _inject_block_lines(html, block_lines, line_offset):
    """按顺序给 HTML 块级元素注入 data-line。

    跳过容器标签 ul/ol/tbody/thead；跳过 blockquote 内的 <p>；
    跳过 thead 内的 <tr>。heading 已由 _inject_heading_lines 处理。
    """
    if not block_lines:
        return html
    idx = [0]
    in_blockquote = [False]
    in_thead = [False]

    def repl(m):
        full = m.group(0)
        slash = m.group(1)
        tag = m.group(2).lower()
        rest = m.group(3)
        # 闭合标签
        if slash == "/":
            if tag == "thead":
                in_thead[0] = False
            elif tag == "blockquote":
                in_blockquote[0] = False
            return full
        # 开标签
        if tag == "thead":
            in_thead[0] = True
            return full
        # 跳过容器
        if tag in ("ul", "ol", "tbody"):
            return full
        if tag == "pre" and "mdpp-echarts" in rest:
            return full
        # blockquote: 标自身，跳过内部 p
        if tag == "blockquote":
            in_blockquote[0] = True
        if tag == "p" and in_blockquote[0]:
            return full
        if tag == "tr" and in_thead[0]:
            return full
        if idx[0] >= len(block_lines):
            return full
        item = block_lines[idx[0]]
        ln, expected = item[0], item[1]
        end_ln = item[2] if len(item) > 2 else ln
        if tag != expected:
            return full
        idx[0] += 1
        actual_line = ln + line_offset
        attrs = ' data-line="%d"' % actual_line
        if end_ln > ln:
            attrs += ' data-line-end="%d"' % (end_ln + line_offset)
        return "<%s%s%s" % (m.group(2), attrs, rest)

    pattern = re.compile(
        r"<(/?)(p|li|blockquote|thead|tbody|tr|pre|table)(\b[^>]*>)",
        re.IGNORECASE,
    )
    return pattern.sub(repl, html)


def _apply_task_lists(html):
    # checkbox 不带 disabled：预览中可点击，点击事件由 preview.js 上报
    # /api/task_toggle 回写编辑器（见 specs/task-list-checkbox-sync.md）
    html = _TASK_OPEN_RE.sub(
        r'\1\2<input type="checkbox" class="task-list-item-checkbox"> ',
        html,
    )
    html = _TASK_DONE_RE.sub(
        r'\1\2<input type="checkbox" class="task-list-item-checkbox" checked> ',
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


# GitHub 风格 callout 类型表：class 后缀 → (默认标题, SVG 图标 path)。
# 图标为 octicon（MIT），currentColor 继承 CSS 配色。
_CALLOUT_TYPES = {
    "note": (
        "Note",
        '<path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.5 7.75A.75.75 0 0 1 7.25 7h1a.75.75 0 0 1 .75.75v2.75h.25a.75.75 0 0 1 0 1.5h-2a.75.75 0 0 1 0-1.5h.25v-2h-.25a.75.75 0 0 1-.75-.75ZM8 6a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z"/>',
    ),
    "tip": (
        "Tip",
        '<path d="M8 1.5c-2.363 0-4 1.69-4 3.75 0 .984.424 1.625.984 2.304l.214.253c.223.264.47.556.673.848.284.411.537.896.621 1.49a.75.75 0 0 1-1.484.211c-.04-.282-.163-.547-.37-.847a8.456 8.456 0 0 0-.542-.68c-.084-.1-.173-.205-.268-.32C3.201 7.75 2.5 6.766 2.5 5.25 2.5 2.31 4.863 0 8 0s5.5 2.31 5.5 5.25c0 1.516-.701 2.5-1.328 3.259-.095.115-.184.22-.268.319-.207.245-.383.453-.541.681-.208.3-.33.565-.37.847a.751.751 0 0 1-1.485-.212c.084-.593.337-1.078.621-1.489.203-.292.45-.584.673-.848.075-.088.147-.173.213-.253.561-.679.985-1.32.985-2.304 0-2.06-1.637-3.75-4-3.75ZM5.75 12h4.5a.75.75 0 0 1 0 1.5h-4.5a.75.75 0 0 1 0-1.5ZM6 15.25a.75.75 0 0 1 .75-.75h2.5a.75.75 0 0 1 0 1.5h-2.5a.75.75 0 0 1-.75-.75Z"/>',
    ),
    "important": (
        "Important",
        '<path d="M0 1.75C0 .784.784 0 1.75 0h12.5C15.216 0 16 .784 16 1.75v9.5A1.75 1.75 0 0 1 14.25 13H8.06l-2.573 2.573A1.458 1.458 0 0 1 3 14.543V13H1.75A1.75 1.75 0 0 1 0 11.25Zm1.75-.25a.25.25 0 0 0-.25.25v9.5c0 .138.112.25.25.25h2a.75.75 0 0 1 .75.75v2.19l2.72-2.72a.749.749 0 0 1 .53-.22h6.5a.25.25 0 0 0 .25-.25v-9.5a.25.25 0 0 0-.25-.25Zm7 2.25v2.5a.75.75 0 0 1-1.5 0v-2.5a.75.75 0 0 1 1.5 0ZM9 9a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z"/>',
    ),
    "warning": (
        "Warning",
        '<path d="M6.457 1.047c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0 1 14.083 15H1.917a1.75 1.75 0 0 1-1.542-2.575Zm1.763.707a.25.25 0 0 0-.44 0L1.698 13.132a.25.25 0 0 0 .22.368h12.164a.25.25 0 0 0 .22-.368Zm.53 3.996v2.5a.75.75 0 0 1-1.5 0v-2.5a.75.75 0 0 1 1.5 0ZM9 11a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z"/>',
    ),
    "caution": (
        "Caution",
        '<path d="M4.47.22A.749.749 0 0 1 5 0h6c.199 0 .389.079.53.22l4.25 4.25c.141.14.22.331.22.53v6a.749.749 0 0 1-.22.53l-4.25 4.25a.749.749 0 0 1-.53.22H5a.749.749 0 0 1-.53-.22L.22 11.53A.749.749 0 0 1 0 11V5c0-.199.079-.389.22-.53Zm.84 1.28L1.5 5.31v5.38l3.81 3.81h5.38l3.81-3.81V5.31L10.69 1.5ZM8 4a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 8 4Zm0 8a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z"/>',
    ),
}

# blockquote 开标签后紧跟的第一个 <p> 整段（允许中间空白）；
# 不跨嵌套元素——callout 语法要求首行就是 [!TYPE]。
# nl2br 会把首行后续内容变成 <br>，因此必须消费整个 <p>…</p> 再重写。
_CALLOUT_P_RE = re.compile(
    r"<blockquote(\s[^>]*)?>[ \t]*\n?<p>(?P<inner>.*?)</p>",
    re.DOTALL,
)
_CALLOUT_HEAD_RE = re.compile(
    r"^[ \t]*\[!(?P<type>[A-Za-z]+)\](?P<title>[^\n<]*)(?P<rest>.*)$",
    re.DOTALL,
)


def _apply_callouts(html):
    """GitHub 风格 callout：blockquote 首段 [!TYPE] → 带图标提示块。

    匹配则改写 blockquote class，把首段拆成「标题 p + 内容 p」；
    不匹配保持原文。
    """

    def repl(m):
        head = _CALLOUT_HEAD_RE.match(m.group("inner"))
        if not head:
            return m.group(0)
        type_name = head.group("type").lower()
        if type_name not in _CALLOUT_TYPES:
            # 未知类型按 GitHub 规则保持普通引用
            return m.group(0)
        label, icon = _CALLOUT_TYPES[type_name]
        custom = (head.group("title") or "").strip()
        title = _escape(custom or label)
        rest = head.group("rest").lstrip(" \t")
        # rest 是首行剩余（可能以 <br> 开头接后续行），去掉行首 <br>
        rest = re.sub(r"^(<br\s*/?>)+[ \t]*\n?", "", rest)
        body_p = "<p>%s</p>" % rest if rest.strip() else ""
        open_tag = "<blockquote%s" % (m.group(1) or "")
        return (
            '%s class="mdpp-callout mdpp-callout-%s">'
            '<p class="mdpp-callout-title">'
            '<svg class="mdpp-callout-icon" viewBox="0 0 16 16" '
            'width="16" height="16" aria-hidden="true" fill="currentColor">%s</svg>'
            "%s</p>%s"
            % (open_tag, type_name, icon, title, body_p)
        )

    # 只在引用起点处匹配一次；多个 callout 时重复 sub 全量扫描即可
    return _CALLOUT_P_RE.sub(repl, html)


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


def rewrite_link_hrefs(html, base_dir, mode="server"):
    """Rewrite relative <a href> links for the local preview server.

    The preview page lives at the server root, so the browser resolves
    relative hrefs against doc_dir (leading "../" is clamped to root) - e.g.
    "../superpowers/x.md" reaches "/doc/superpowers/x.md". Compute the same
    resolution here and emit an explicit URL.

    .md links become "/?file=<abs path>" so the browser tab URL reflects the
    document and the server queues it for the standard preview flow. Other
    relative links become /doc/ paths.

    Also make every non-anchor link open in a new tab.
    """
    import posixpath
    from urllib.parse import quote as _quote

    if not base_dir or mode != "server":
        return html

    def repl(m):
        prefix, href, suffix = m.group(1), m.group(2), m.group(3)
        s = href.strip()
        # 页内锚点与特殊协议不改写
        if s.startswith(("#", "mailto:", "javascript:", "http://", "https://",
                         "data:", "file://", "/doc/", "/?file=")):
            return m.group(0)
        if s.startswith("?") or s.startswith("//"):
            return m.group(0)
        # 候选一:markdown 惯例,相对 md 文件目录解析(支持 ../..)
        cand_file = None
        if not s.startswith("/"):
            cand_file = os.path.normpath(os.path.join(base_dir, s))
        # 候选二:相对服务器根解析,".." 被钳制在根(页面位于根的旧行为)
        rel = posixpath.normpath("/" + s).lstrip("/")
        cand_root = os.path.normpath(os.path.join(base_dir, rel)) if rel else None
        # 优先取真实存在的目标
        target = None
        for cand in (cand_file, cand_root):
            if cand and os.path.exists(cand):
                target = cand
                break
        is_md_link = s.lower().endswith(".md")
        if target is not None and os.path.isdir(target):
            # 目录链接:定位其中的入口文档(SKILL/README/index)
            for entry_name in ("SKILL.md", "README.md", "index.md"):
                entry = os.path.join(target, entry_name)
                if os.path.isfile(entry):
                    target = entry
                    is_md_link = True
                    break
        if is_md_link or (target is not None and os.path.isdir(target)):
            path = target or cand_file or cand_root
            return "%s/?file=%s%s" % (prefix, _quote(path, safe=""), suffix)
        if not rel:
            return m.group(0)
        return "%s/doc/%s%s" % (prefix, rel, suffix)

    html = _A_HREF_RE.sub(repl, html)

    # 外链新标签打开;.md 预览链接由客户端复用已有 tab,不加 target=_blank
    def add_target(m):
        tag = m.group(0)
        if 'href="#' in tag or "target=" in tag or "/?file=" in tag:
            return tag
        return tag[:2] + ' target="_blank"' + tag[2:]

    return _A_TAG_RE.sub(add_target, html)


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


def _replace_emoji(text):
    """Replace GFM emoji shortcodes (:smile:) with unicode characters.

    Call with code fences/inline code already stashed (as in _extract_math) so
    code content is never rewritten. Unknown aliases are left untouched.
    """
    def repl(m):
        return EMOJI_ALIASES.get(m.group(1), m.group(0))

    return _EMOJI_RE.sub(repl, text)


def _protect_code_then(text, fn):
    """Stash fenced/inline code, run *fn* on the text, restore the code."""
    stash = []

    def _stash(m):
        stash.append(m.group(0))
        return _CODE_MARKER_TMPL % (len(stash) - 1)

    text = _FENCE_RE.sub(_stash, text)
    text = _INLINE_CODE_RE.sub(_stash, text)
    text = fn(text)
    for i, block in enumerate(stash):
        text = text.replace(_CODE_MARKER_TMPL % i, block)
    return text


def _extract_math(text, replace_emoji=False):
    """Pull LaTeX out of *text* so markdown cannot mangle delimiters.

    Returns (text_with_markers, list_of_html_fragments).
    Code fences and inline code are temporarily protected first; emoji
    replacement runs on the same stash so shortcodes inside code survive.
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

    if replace_emoji:
        text = _replace_emoji(text)

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
            debug("katex batch failed: %s" % e)
            batch = None
        if batch is None:
            batch = [None] * len(math_jobs)
        ssr_ok = sum(1 for h in batch if h)
        if ssr_ok:
            debug("katex SSR %d/%d formula(s)" % (ssr_ok, len(math_jobs)))
        elif math_jobs:
            debug("katex SSR unavailable; client fallback for %d formula(s)" % len(math_jobs))
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
    enable_emoji=True,
):
    """Render markdown text to HTML.

    Returns dict:
      body_html, toc_html, errors, hash, heading_lines
    """
    errors = []
    if not _HAS_MARKDOWN:
        _dbg = _IMPORT_TRACEBACK if "_IMPORT_TRACEBACK" in globals() else _IMPORT_ERROR
        error("markdown import FAILED:\n%s" % _dbg)
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

    # 在 stash 之前收集块级行号，此时 text 行号与源码一致
    block_lines = _collect_block_lines(text)

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

    # Math extraction (must be after mermaid, before markdown convert).
    # Emoji shortcodes ride the same stash pass so code content is protected.
    math_html = []
    if enable_math:
        text, math_html = _extract_math(text, replace_emoji=enable_emoji)
    elif enable_emoji:
        # No math: still protect code fences before substituting.
        text = _protect_code_then(text, _replace_emoji)
    if math_html:
        debug("protected %d math region(s)" % len(math_html))

    # Pass extension *instances* (not string names like
    # "markdown.extensions.fenced_code") so python-markdown does not need to
    # resolve extensions via absolute importlib paths at convert time.
    extensions = [
        FencedCodeExtension(),
        TableExtension(),
        AttrListExtension(),
        Nl2BrExtension(),
        TocExtension(permalink=False, toc_depth=6, title="Contents"),
        CodeHiliteExtension(guess_lang=False, linenums=False),
        MdppInlineExtension(),
    ]
    if enable_footnotes:
        extensions.append(FootnoteExtension())

    toc_html = ""
    try:
        md = _md.Markdown(extensions=extensions, output_format="html5")
        html = md.convert(text)
        toc_html = getattr(md, "toc", "") or ""
        debug("markdown() OK; html len=%d; has_table=%s" % (
            len(html), "<table>" in html))
    except Exception as e:
        error("markdown() FAILED: %s" % e)
        try:
            fallback_ext = [
                FencedCodeExtension(),
                TableExtension(),
                AttrListExtension(),
                Nl2BrExtension(),
                MdppInlineExtension(),
            ]
            if enable_footnotes:
                fallback_ext.append(FootnoteExtension())
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

    html = _apply_callouts(html)

    if enable_task_lists:
        html = _apply_task_lists(html)

    html = _inject_heading_lines(html, heading_lines)
    html = _inject_block_lines(html, block_lines, line_offset)
    html = rewrite_image_srcs(html, base_dir, mode=image_mode)
    html = rewrite_link_hrefs(html, base_dir, mode=image_mode)

    if not enable_toc:
        toc_html = ""

    return {
        "body_html": html,
        "toc_html": toc_html,
        "errors": errors,
        "hash": content_hash(html + toc_html),
        "heading_lines": heading_lines,
    }
