"""Paste clipboard HTML as markdown into the current view.

读取系统剪贴板的 text/html 格式，用 vendored markdownify 转为 markdown，
插入当前光标处。剪贴板没有 HTML 时降级为普通粘贴。

macOS: osascript `the clipboard as «class HTML»`（返回 «data HTML....» hex）。
Windows: PowerShell Get-Clipboard -TextFormatType Html（CF_HTML，按头部偏移截取）。
Linux: xclip -t text/html -o（X11）/ wl-paste --type text/html（Wayland）。

见 specs/paste-html-as-markdown.md。
"""
import binascii
import re
import subprocess
import threading
import zlib

import sublime
import sublime_plugin

from ..mpe_core import config
from ..mpe_core import log
from ..mpe_core import vendor

_HTML_HEX_RE = re.compile(r"«data HTML([0-9A-Fa-f]+)»")
_CF_HTML_HEADER_RE = re.compile(
    r"Version:[\d.]+\s+StartHTML:(\d+)\s+EndHTML:(\d+)", re.IGNORECASE)
_IMG_URL_RE = re.compile(r"(!\[[^\]]*\]\()(https?://[^)\s]+)(\))")
_IMG_EXT_BY_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}
_IMG_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)
_MAX_IMAGE_BYTES = 20 * 1024 * 1024


def read_clipboard_html():
    """读取剪贴板 text/html。返回 (html or None, detail)。

    detail 用于无 HTML 时的说明（无工具 / 无 HTML 格式）。
    """
    import sys
    if sys.platform == "darwin":
        return _read_macos()
    if sys.platform == "win32":
        return _read_windows()
    return _read_linux()


def _run(argv, stdin_bytes=None, timeout=10):
    """跑外部命令，返回 CompletedProcess；找不到命令返回 None。"""
    try:
        return subprocess.run(
            argv,
            input=stdin_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        raise RuntimeError("clipboard command timed out: %s" % " ".join(argv))


def _decode(raw):
    """utf-8 解码并剥离 BOM/空字节。"""
    if isinstance(raw, bytes):
        raw = raw.lstrip(b"\xef\xbb\xbf\x00") or raw
        return raw.decode("utf-8", errors="replace")
    return raw


def _read_macos():
    r = _run(["osascript", "-e", "the clipboard as «class HTML»"])
    if r is None:
        return None, "osascript unavailable"
    if r.returncode != 0:
        return None, (r.stderr or b"").decode("utf-8", "replace").strip()[:200]
    out = _decode(r.stdout).strip()
    m = _HTML_HEX_RE.search(out)
    if not m:
        return None, "clipboard has no HTML flavor"
    try:
        return binascii.unhexlify(m.group(1)).decode("utf-8", "replace"), ""
    except (binascii.Error, ValueError) as e:
        return None, "clipboard HTML hex decode failed: %s" % e


def _read_windows():
    script = (
        "$h = Get-Clipboard -TextFormatType Html -Raw; "
        "if ($h) { [Console]::Out.Write($h) }"
    )
    r = _run(["powershell", "-NoProfile", "-Command", script], timeout=15)
    if r is None:
        return None, "powershell unavailable"
    if r.returncode != 0:
        return None, (r.stderr or b"").decode("utf-8", "replace").strip()[:200]
    raw = r.stdout
    if not raw:
        return None, "clipboard has no HTML flavor"
    # CF_HTML: 头部行是 ASCII；偏移是相对全文的字节位置。
    head_text = raw[:512].decode("utf-8", "replace")
    m = _CF_HTML_HEADER_RE.search(head_text)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        if 0 <= start < end <= len(raw):
            return raw[start:end].decode("utf-8", "replace"), ""
    return _decode(raw), ""


def _read_linux():
    for argv in (
        ["xclip", "-selection", "clipboard", "-t", "text/html", "-o"],
        ["wl-paste", "--type", "text/html"],
    ):
        r = _run(argv)
        if r is None:
            continue
        if r.returncode != 0:
            # 有工具但剪贴板里没有 text/html target（如只有纯文本）。
            err = (r.stderr or b"").decode("utf-8", "replace").strip()[:120]
            return None, err or "clipboard has no text/html target"
        return _decode(r.stdout), ""
    return None, "no clipboard tool (install xclip or wl-clipboard)"


def html_fragment_to_markdown(html):
    """清洗剪贴板 HTML 片段并转 markdown。"""
    cleaned = _strip_wrappers(html)
    md = vendor.markdownify(cleaned, heading_style="ATX", bullets="-")
    return md.strip() + "\n"


def _strip_wrappers(html):
    """剥掉浏览器片段包装：meta/style/script 标签与 HTML 注释。"""
    html = re.sub(r"(?is)<\s*(meta|style|script)\b.*?>", "", html)
    html = re.sub(r"(?s)<!--.*?-->", "", html)
    return html


def download_image(url, images_dir, md_dir):
    """下载图片到 images_dir，返回相对路径；失败返回 None。

    命名 crc32(内容)；扩展名按 Content-Type，回退魔数，再回退 URL 后缀。
    """
    import os
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as f:
            ctype = (f.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            data = f.read(_MAX_IMAGE_BYTES + 1)
    except Exception:
        return None
    if not data or len(data) > _MAX_IMAGE_BYTES:
        return None
    ext = _IMG_EXT_BY_TYPE.get(ctype)
    if ext is None:
        for magic, magic_ext in _IMG_MAGIC:
            if data.startswith(magic):
                ext = magic_ext
                break
    if ext is None:
        m = re.search(r"\.(\w{3,5})(?:[?#]|$)", url)
        ext = "." + m.group(1).lower() if m else ".png"
    name = "%x%s" % (zlib.crc32(data), ext)
    try:
        os.makedirs(images_dir, exist_ok=True)
        with open(os.path.join(images_dir, name), "wb") as f:
            f.write(data)
    except OSError:
        return None
    return os.path.relpath(os.path.join(images_dir, name), md_dir)


def localize_images(md_text, md_dir, images_dir):
    """下载 md_text 里的 http(s) 图片，替换为本地相对路径。

    返回 (新文本, 成功数, 失败数)。
    """
    import os
    import urllib.parse

    def _repl(m):
        prefix, url, suffix = m.group(1), m.group(2), m.group(3)
        local = download_image(
            urllib.parse.unquote(url.split("(")[0]), images_dir, md_dir)
        if local is None:
            return None
        # URL 可能带 Title 尾巴（![](...) 里不会再有，但保险起见重拼）
        return "%s%s%s" % (prefix, local.replace(os.sep, "/"), suffix)

    ok = fail = 0
    out_parts = []
    pos = 0
    for m in _IMG_URL_RE.finditer(md_text):
        replaced = _repl(m)
        if replaced is None:
            fail += 1
            continue
        ok += 1
        out_parts.append(md_text[pos:m.start()])
        out_parts.append(replaced)
        pos = m.end()
    out_parts.append(md_text[pos:])
    return "".join(out_parts), ok, fail


class MarkdownPreviewEnhancedPasteAsMarkdownCommand(sublime_plugin.TextCommand):
    """Paste clipboard HTML as markdown (falls back to plain paste)."""

    def is_enabled(self):
        return self.view.match_selector(0, "text.html.markdown")

    def is_visible(self):
        return self.view.match_selector(0, "text.html.markdown")

    def run(self, edit):
        log.info("paste-md: triggered view=%s" % (self.view.file_name() or "<untitled>"))
        view = self.view
        file_path = view.file_name()
        md_dir = (
            file_path and (file_path.rsplit("/", 1)[0] if "/" in file_path else ".")
        ) or ""
        download_images = bool(config.get("paste_download_images", False))
        images_dir_name = config.get("paste_images_dir", "media")

        def _work():
            try:
                html, detail = read_clipboard_html()
            except Exception as e:
                msg = "Paste as markdown: clipboard read crashed: %s" % e
                log.error(msg)
                sublime.set_timeout(
                    lambda: sublime.error_message(msg), 0)
                return
            log.info(
                "paste-md: clipboard read html=%s detail=%s"
                % ("yes len=%d" % len(html) if html else "no", detail or "-"))
            if html is None:
                if "no clipboard tool" in detail or "unavailable" in detail:
                    msg = "Paste as markdown failed: %s" % detail
                    sublime.set_timeout(
                        lambda: sublime.error_message(msg), 0)
                    return
                # 无 HTML 格式 → 降级普通粘贴
                sublime.set_timeout(lambda: view.run_command("paste"), 0)
                fallback_msg = (
                    "no HTML in clipboard; pasted as plain text (%s)" % detail)
                sublime.set_timeout(
                    lambda: sublime.status_message(fallback_msg), 0)
                return

            try:
                md_text = html_fragment_to_markdown(html)
                log.info(
                    "paste-md: converted html=%d -> md=%d chars"
                    % (len(html), len(md_text)))
            except Exception as e:
                msg = "Paste as markdown: HTML conversion failed: %s" % e
                sublime.set_timeout(
                    lambda: sublime.error_message(msg), 0)
                return

            img_msg = ""
            if download_images and md_dir and _IMG_URL_RE.search(md_text):
                images_dir = md_dir.rstrip("/") + "/" + images_dir_name
                md_text, ok, fail = localize_images(md_text, md_dir, images_dir)
                img_msg = ", images %d saved / %d failed" % (ok, fail) if ok or fail else ""

            def _insert():
                log.info(
                    "paste-md: inserting %d chars at %d sel(s)"
                    % (len(md_text), len(view.sel())))
                # edit 对象在 run() 返回后失效——插入须另起 TextCommand 完成。
                try:
                    view.run_command(
                        "markdown_preview_enhanced_insert_text",
                        {"text": md_text, "status": "Pasted as markdown%s" % img_msg},
                    )
                except Exception as e:
                    msg = "Paste as markdown: insert failed: %s" % e
                    log.error(msg)
                    sublime.set_timeout(
                        lambda: sublime.error_message(msg), 0)

            sublime.set_timeout(_insert, 0)

        threading.Thread(target=_work, daemon=True).start()


class MarkdownPreviewEnhancedInsertTextCommand(sublime_plugin.TextCommand):
    """在当前选区插入文本（供后台线程经 run_command 调用，绕开 edit 生命周期）。"""

    def run(self, edit, text, status=""):
        for region in self.view.sel():
            self.view.insert(edit, region.begin(), text)
        log.info(
            "paste-md: insert_text done chars=%d sel=%d"
            % (len(text), len(self.view.sel())))
        if status:
            sublime.status_message(status)
