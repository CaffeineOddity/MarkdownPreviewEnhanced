"""Copy the rendered markdown as rich text (text/html) to the clipboard.

macOS: osascript reading an HTML file into the clipboard.
Windows: PowerShell Set-Clipboard with a CF_HTML wrapper.
Linux: xclip / wl-copy with text/html target.
"""
import os
import subprocess
import tempfile
import threading
import traceback

import sublime
import sublime_plugin

from ..mpe_core import config
from ..mpe_core import log
from ..mpe_core.html_builder import build_clipboard_html
from ..mpe_core.md_renderer import render as render_markdown
from ..mpe_core.render import render_settings, view_base_dir, view_title


def _cf_html_wrap(html):
    """Wrap full HTML in the CF_HTML clipboard format Windows expects."""
    # Byte offsets must be calculated on the utf-8 encoded payload.
    header_tpl = (
        "Version:0.9\r\nStartHTML:{start:010d}\r\nEndHTML:{end:010d}\r\n"
        "StartFragment:0000000000\r\nEndFragment:0000000000\r\n"
    )
    payload = html.encode("utf-8")
    # Two passes: header length shifts the offsets.
    start = len(header_tpl.format(start=0, end=0).encode("utf-8"))
    header = header_tpl.format(start=start, end=start + len(payload))
    head_bytes = header.encode("utf-8")
    return head_bytes + payload


def _clipboard_command(html_path):
    """Return (argv, stdin_bytes) for the platform clipboard writer."""
    import sys
    if sys.platform == "darwin":
        script = (
            'set the clipboard to (read (POSIX file "%s") as «class HTML»)'
            % html_path
        )
        return ["osascript", "-e", script], None
    if sys.platform == "win32":
        with open(html_path, "r", encoding="utf-8") as f:
            cf_html = _cf_html_wrap(f.read())
        script = "$input | Set-Clipboard -TextFormatType Html"
        return ["powershell", "-NoProfile", "-Command", script], cf_html
    # Linux / other: try X11 then Wayland tools; stdin gets the HTML.
    for argv in (
        ["xclip", "-selection", "clipboard", "-t", "text/html"],
        ["wl-copy", "--type", "text/html"],
    ):
        try:
            subprocess.run(["which", argv[0]], stdout=subprocess.DEVNULL)
            return argv, None
        except OSError:
            continue
    return None, None


class MarkdownPreviewEnhancedCopyRichTextCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        if view is None or not view.match_selector(0, "text.html.markdown"):
            sublime.status_message("Not a markdown file")
            return

        text = view.substr(sublime.Region(0, view.size()))
        rs = render_settings()
        base_dir = view_base_dir(view)
        mermaid_theme = view.settings().get(
            "markdown_preview_enhanced.mermaid_theme", rs["mermaid_theme"])
        title = view_title(view)

        def _work():
            try:
                result = render_markdown(
                    text,
                    mermaid_theme=mermaid_theme,
                    base_dir=base_dir,
                    image_mode="file",
                    enable_footnotes=rs["enable_footnotes"],
                    enable_task_lists=rs["enable_task_lists"],
                    enable_toc=False,
                    strip_yaml=rs["strip_yaml"],
                    enable_math=rs["enable_math"],
                    enable_emoji=rs["enable_emoji"],
                )
                html = build_clipboard_html(
                    result["body_html"], title=title)
                errors = result.get("errors") or []
            except Exception as e:
                log.error("copy rich text render failed:\n%s"
                          % traceback.format_exc())
                sublime.set_timeout(
                    lambda: sublime.error_message(
                        "Copy as rich text failed:\n%s" % e), 0)
                return

            fd, tmp = tempfile.mkstemp(suffix=".html", prefix="mdpp_clip_")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(html)
                argv, stdin_bytes = _clipboard_command(tmp)
                ok = False
                detail = ""
                if argv is None:
                    detail = "no clipboard tool (install xclip or wl-copy)"
                else:
                    try:
                        r = subprocess.run(
                            argv,
                            input=stdin_bytes,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            timeout=15,
                        )
                        ok = r.returncode == 0
                        if not ok:
                            detail = (r.stderr or b"").decode(
                                "utf-8", errors="replace")[:200]
                    except Exception as e:
                        detail = str(e)
            finally:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass

            def _done():
                if ok:
                    msg = "Copied as rich text"
                    if errors:
                        msg += " (with warnings)"
                    sublime.status_message(msg)
                else:
                    sublime.error_message(
                        "Copy as rich text failed: %s" % (detail or "unknown"))

            sublime.set_timeout(_done, 0)

        threading.Thread(target=_work, daemon=True).start()
