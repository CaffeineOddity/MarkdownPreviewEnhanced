r"""MarkdownPreviewEnhanced — browser live preview.

Features: smart refresh (scroll preserve), relative images, KaTeX, task lists,
footnotes, frontmatter, TOC sidebar, export HTML/PDF, local server, scroll sync.
"""
import os
import threading
import time
import traceback

import sublime
import sublime_plugin

from . import config
from .browser import BrowserSession
from .export_util import export_html, export_pdf
from .html_builder import build_preview_shell
from .md_renderer import render as render_markdown, set_debug_log_path
from .preview_server import (
    SERVER,
    pop_browser_line,
    seconds_since_activity,
    set_editor_line,
    set_output_dir,
    update_content,
)

PLUGIN_NAME = "MarkdownPreviewEnhanced"
_MARKDOWN_SCOPE = "text.html.markdown"

_preview_open = False
_browser = BrowserSession()
_bound_view_id = None
_last_browser_seq = 0
_scroll_timer = None


# ── logging ─────────────────────────────────────────────────────────────────

def _file_log(msg):
    import datetime
    try:
        path = config.debug_log_path()
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        with open(path, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (ts, msg))
    except Exception:
        pass


def _log(msg):
    print("[MarkdownPreviewEnhanced] %s" % msg)
    _file_log(msg)


def _escape(s):
    import html as _html
    return _html.escape(s)


def _view_base_dir(view):
    path = view.file_name() if view else None
    if path:
        return os.path.dirname(path)
    return None


def _view_title(view):
    name = view.file_name() if view else None
    if name:
        return os.path.basename(name)
    return "Markdown Preview"


def _ensure_server():
    if not config.get("use_local_server", True):
        return None
    set_output_dir(config.output_dir())
    port = int(config.get("server_port", 8765) or 8765)
    url = SERVER.start(port=port, log=_log)
    if not url:
        _log("failed to start preview server on port %s+" % port)
    return url


def _preview_url():
    if config.get("use_local_server", True):
        if not SERVER.running:
            _ensure_server()
        if SERVER.running:
            return SERVER.base_url + "/"
    return "file://" + config.preview_path()


def _preview_alive():
    """True if we believe the live preview session is still usable."""
    global _preview_open
    if not _preview_open:
        return False
    if config.get("use_local_server", True) and not SERVER.running:
        _log("preview flag was set but server is down; treating as closed")
        _preview_open = False
        return False
    return True


def _stop_scroll_poller():
    global _scroll_timer
    if _scroll_timer is not None:
        try:
            _scroll_timer.cancel()
        except Exception:
            pass
        _scroll_timer = None


def _stop_server():
    """Release the local HTTP port when preview is no longer needed."""
    if SERVER.running:
        try:
            SERVER.stop(log=_log)
        except Exception as e:
            _log("server stop failed: %s" % e)


def _close_preview_ui(stop_server=True):
    """Close browser window and optionally stop the local server.

    stop_server=True (default): free the port — used on Close / Toggle-off /
    idle timeout / plugin unload. Pass False only if you need a brief restart.
    """
    global _preview_open
    hint = None
    if SERVER.running and SERVER.port:
        hint = ":%d" % SERVER.port
    else:
        hint = config.preview_path()
    _browser.close(preview_file_hint=hint, log=_log)
    _preview_open = False
    _stop_scroll_poller()
    if stop_server:
        _stop_server()
    _log("preview closed (server %s)" % ("stopped" if stop_server else "kept"))


def _write_files(shell_html, body_html):
    preview = config.preview_path()
    last = config.last_html_path()
    try:
        with open(preview, "w", encoding="utf-8") as f:
            f.write(shell_html)
    except Exception as e:
        _log("write preview.html failed: %s" % e)
    try:
        with open(last, "w", encoding="utf-8") as f:
            f.write(shell_html)
    except Exception:
        pass
    # Also write body fragment for debugging / file mode consumers
    try:
        body_path = os.path.join(config.output_dir(), "body.html")
        with open(body_path, "w", encoding="utf-8") as f:
            f.write(body_html)
    except Exception:
        pass


def _publish(result, view, force_open=False):
    """Push rendered result to disk + server and optionally open browser."""
    global _preview_open, _bound_view_id

    show_toc = bool(config.get("show_toc", True))
    enable_katex = bool(config.get("enable_katex", True))
    scroll_sync = bool(config.get("scroll_sync", True))
    use_server = bool(config.get("use_local_server", True))
    custom_css = config.get("custom_css", "") or ""
    title = _view_title(view)

    body = result["body_html"]
    toc = result["toc_html"] if show_toc else ""
    content_hash = result["hash"]

    shell = build_preview_shell(
        body,
        toc_html=toc,
        show_toc=show_toc,
        enable_katex=enable_katex,
        scroll_sync=scroll_sync and use_server,
        use_server=use_server,
        custom_css=custom_css,
        title=title,
    )

    base_dir = _view_base_dir(view)
    set_debug_log_path(config.debug_log_path())
    set_output_dir(config.output_dir())

    # Capture raw markdown and settings for server-side PDF/PNG export
    raw_md = ""
    try:
        if view is not None:
            raw_md = view.substr(sublime.Region(0, view.size()))
    except Exception:
        pass

    if use_server:
        _ensure_server()
        update_content(
            body_html=body,
            toc_html=toc,
            full_html=shell,
            content_hash=content_hash,
            doc_dir=base_dir,
            shell_html=shell,
            raw_markdown=raw_md,
            export_base_dir=base_dir,
            export_settings={
                "mermaid_theme": config.get("mermaid_theme", "default") or "default",
                "show_toc": False,  # TOC hidden in exports for cleaner output
                "enable_katex": enable_katex,
                "custom_css": custom_css,
                "title": title,
            },
        )

    _write_files(shell, body)

    if force_open or not _preview_open:
        url = _preview_url()
        import webbrowser as _wb
        _wb.open(url)
        _preview_open = True
        if view is not None:
            _bound_view_id = view.id()
        _log("preview ready: %s" % url)
        _start_scroll_poller()


def _start_scroll_poller():
    """Background tick: scroll-sync + idle server shutdown.

    Browser JS polls every ~400ms while the tab is open. If the user closes the
    tab/window without using the plugin command, requests stop and we free the
    port after ``server_idle_seconds``.
    """
    global _scroll_timer
    if not config.get("use_local_server", True):
        return
    if _scroll_timer is not None:
        return

    def _tick():
        global _scroll_timer, _last_browser_seq, _preview_open
        _scroll_timer = None
        if not _preview_open:
            return

        # Auto-stop server when browser tab is gone (no HTTP activity).
        idle_limit = float(config.get("server_idle_seconds", 45) or 0)
        if idle_limit > 0 and SERVER.running:
            try:
                idle = seconds_since_activity()
                if idle >= idle_limit:
                    _log(
                        "no client activity for %.0fs — stopping preview server"
                        % idle
                    )
                    # Don't try to close browser (already gone); just free port.
                    _preview_open = False
                    _stop_server()
                    return
            except Exception:
                pass

        if config.get("scroll_sync", True):
            try:
                line, seq = pop_browser_line()
                if seq > _last_browser_seq and line > 0:
                    _last_browser_seq = seq
                    sublime.set_timeout(lambda: _scroll_editor_to_line(line), 0)
            except Exception:
                pass

        if _preview_open:
            _scroll_timer = threading.Timer(0.5, _tick)
            _scroll_timer.daemon = True
            _scroll_timer.start()

    _scroll_timer = threading.Timer(0.5, _tick)
    _scroll_timer.daemon = True
    _scroll_timer.start()


def _scroll_editor_to_line(line):
    """Scroll the bound (or active) markdown view to 1-based line."""
    global _bound_view_id
    view = None
    for w in sublime.windows():
        for v in w.views():
            if _bound_view_id and v.id() == _bound_view_id:
                view = v
                break
            if view is None and v.match_selector(0, _MARKDOWN_SCOPE):
                view = v
        if view and _bound_view_id and view.id() == _bound_view_id:
            break
    if view is None:
        return
    try:
        pt = view.text_point(max(0, line - 1), 0)
        view.sel().clear()
        view.sel().add(sublime.Region(pt))
        view.show_at_center(pt)
    except Exception as e:
        _log("scroll editor failed: %s" % e)


def _render_settings():
    return {
        "mermaid_theme": config.get("mermaid_theme", "default") or "default",
        "enable_footnotes": bool(config.get("enable_footnotes", True)),
        "enable_task_lists": bool(config.get("enable_task_lists", True)),
        "enable_toc": bool(config.get("show_toc", True)),
        "strip_yaml": bool(config.get("strip_frontmatter", True)),
        "enable_math": bool(config.get("enable_katex", True)),
        "image_mode": "server" if config.get("use_local_server", True) else "file",
    }


# ── commands ────────────────────────────────────────────────────────────────

class MarkdownPreviewEnhancedToggleCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if view is None:
            _log("no view to preview")
            self.window.status_message("MarkdownPreviewEnhanced: no active view")
            return

        if _preview_alive() and seconds_since_activity() < 5:
            # Tab likely still open — just re-render, SSE pushes update
            _log("toggle: tab likely open → refresh via SSE")
            MarkdownPreviewEnhancedListener.render_view(view, force=True, open_browser=False)
            self.window.status_message("MarkdownPreviewEnhanced: refreshed")
            return

        _log("toggle: opening preview")
        self.window.status_message("MarkdownPreviewEnhanced: opening preview…")
        MarkdownPreviewEnhancedListener.render_view(view, force=True, open_browser=True)


class MarkdownPreviewEnhancedCloseCommand(sublime_plugin.WindowCommand):
    def run(self):
        _close_preview_ui(stop_server=True)
        self.window.status_message("MarkdownPreviewEnhanced: preview closed (server stopped)")


class MarkdownPreviewEnhancedRefreshCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if view is not None:
            MarkdownPreviewEnhancedListener.render_view(
                view, force=True, open_browser=not _preview_open)


class MarkdownPreviewEnhancedExportHtmlCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if view is None:
            return
        default_name = "export.html"
        if view.file_name():
            base = os.path.splitext(os.path.basename(view.file_name()))[0]
            default_name = base + ".html"
        default_path = os.path.join(config.output_dir(), default_name)

        def on_done(path):
            if not path:
                return
            text = view.substr(sublime.Region(0, view.size()))
            rs = _render_settings()
            try:
                dest, errors = export_html(
                    text,
                    path,
                    base_dir=_view_base_dir(view),
                    mermaid_theme=rs["mermaid_theme"],
                    show_toc=bool(config.get("show_toc", True)),
                    enable_katex=bool(config.get("enable_katex", True)),
                    custom_css=config.get("custom_css", "") or "",
                    title=_view_title(view),
                    log=_log,
                )
                msg = "Exported HTML: %s" % dest
                if errors:
                    msg += " (with warnings)"
                self.window.status_message(msg)
                sublime.message_dialog(msg)
            except Exception as e:
                sublime.error_message("Export HTML failed:\n%s" % e)
                _log(traceback.format_exc())

        self.window.show_input_panel(
            "Export HTML to:", default_path, on_done, None, None)


class MarkdownPreviewEnhancedExportPdfCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if view is None:
            return
        default_name = "export.pdf"
        if view.file_name():
            base = os.path.splitext(os.path.basename(view.file_name()))[0]
            default_name = base + ".pdf"
        default_path = os.path.join(config.output_dir(), default_name)

        def on_done(path):
            if not path:
                return
            text = view.substr(sublime.Region(0, view.size()))
            rs = _render_settings()
            self.window.status_message("MarkdownPreviewEnhanced: exporting PDF…")

            def _work():
                try:
                    dest = export_pdf(
                        text,
                        path,
                        base_dir=_view_base_dir(view),
                        mermaid_theme=rs["mermaid_theme"],
                        show_toc=False,
                        enable_katex=bool(config.get("enable_katex", True)),
                        custom_css=config.get("custom_css", "") or "",
                        title=_view_title(view),
                        log=_log,
                    )
                    sublime.set_timeout(
                        lambda: (
                            self.window.status_message("Exported PDF: %s" % dest),
                            sublime.message_dialog("Exported PDF:\n%s" % dest),
                        ),
                        0,
                    )
                except Exception as e:
                    err = str(e)
                    sublime.set_timeout(
                        lambda: sublime.error_message("Export PDF failed:\n%s" % err),
                        0,
                    )
                    _log(traceback.format_exc())

            threading.Thread(target=_work, daemon=True).start()

        self.window.show_input_panel(
            "Export PDF to:", default_path, on_done, None, None)


# ── event listener ──────────────────────────────────────────────────────────

class MarkdownPreviewEnhancedListener(sublime_plugin.EventListener):
    _timers = {}

    @classmethod
    def render_view(cls, view, force=False, open_browser=False):
        global _preview_open
        if view is None:
            return
        if not force and not view.match_selector(0, _MARKDOWN_SCOPE):
            return
        if not force and not _preview_open and not open_browser:
            return

        # Ensure renderer logs go to the same debug.log as the plugin.
        try:
            set_debug_log_path(config.debug_log_path())
        except Exception:
            pass

        text = view.substr(sublime.Region(0, view.size()))
        rs = _render_settings()
        base_dir = _view_base_dir(view)
        # Allow per-view override for mermaid theme
        mermaid_theme = view.settings().get(
            "markdown_preview_enhanced.mermaid_theme", rs["mermaid_theme"])

        # Start server early so the browser URL is valid immediately.
        if open_browser and config.get("use_local_server", True):
            try:
                _ensure_server()
            except Exception as e:
                _log("ensure_server failed: %s" % e)

        # Immediate loading shell so browser can open quickly on first toggle
        if open_browser:
            loading = (
                '<p style="color:#666;text-align:center;padding:40px">'
                "Rendering…</p>"
            )
            loading_result = {
                "body_html": loading,
                "toc_html": "",
                "hash": "loading-%s" % time.time(),
            }

            def _show_loading():
                try:
                    _publish(loading_result, view, force_open=True)
                except Exception:
                    _log("loading publish failed:\n%s" % traceback.format_exc())

            sublime.set_timeout(_show_loading, 0)

        def _work():
            try:
                _log("render: text len=%d base_dir=%s" % (len(text), base_dir))
                result = render_markdown(
                    text,
                    mermaid_theme=mermaid_theme,
                    base_dir=base_dir,
                    image_mode=rs["image_mode"],
                    enable_footnotes=rs["enable_footnotes"],
                    enable_task_lists=rs["enable_task_lists"],
                    enable_toc=rs["enable_toc"],
                    strip_yaml=rs["strip_yaml"],
                    enable_math=rs["enable_math"],
                )
                if result.get("errors"):
                    _log("render errors: %r" % result["errors"])
            except Exception as e:
                result = {
                    "body_html": "<pre>%s</pre>" % _escape(str(e)),
                    "toc_html": "",
                    "hash": "err",
                    "errors": [str(e)],
                }
                _log("render error:\n%s" % traceback.format_exc())

            def _done():
                try:
                    # force_open if user asked to open and we still aren't live
                    need_open = open_browser and not _preview_alive()
                    _publish(result, view, force_open=need_open)
                except Exception:
                    _log("publish failed:\n%s" % traceback.format_exc())

            sublime.set_timeout(_done, 0)

        threading.Thread(target=_work, daemon=True).start()

    def on_modified_async(self, view):
        global _preview_open
        if not _preview_open:
            return
        try:
            ok_scope = view.match_selector(0, _MARKDOWN_SCOPE)
        except Exception:
            ok_scope = False
        if not ok_scope:
            return
        bid = view.buffer_id()
        timer = self._timers.get(bid)
        if timer:
            timer.cancel()
        debounce = float(config.get("debounce_ms", 500) or 500) / 1000.0
        timer = threading.Timer(debounce, lambda: self.render_view(view))
        self._timers[bid] = timer
        timer.start()

    def on_selection_modified_async(self, view):
        """Push editor cursor line to the preview server for scroll sync."""
        global _preview_open, _bound_view_id
        if not _preview_open:
            return
        if not config.get("scroll_sync", True):
            return
        if not config.get("use_local_server", True):
            return
        if _bound_view_id and view.id() != _bound_view_id:
            # Still allow active markdown view
            if not view.match_selector(0, _MARKDOWN_SCOPE):
                return
        try:
            if not view.match_selector(0, _MARKDOWN_SCOPE):
                return
            sel = view.sel()
            if not sel:
                return
            row, _col = view.rowcol(sel[0].begin())
            set_editor_line(row + 1)
        except Exception:
            pass


def plugin_loaded():
    set_debug_log_path(config.debug_log_path())
    set_output_dir(config.output_dir())
    _log("plugin loaded")


def plugin_unloaded():
    global _preview_open
    _preview_open = False
    _stop_scroll_poller()
    _stop_server()
