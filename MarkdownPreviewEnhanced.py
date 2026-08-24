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

# markdown + pygments come from the mdpopups dependency (dependencies.json);
# this package runs on the Python 3.8 plugin host (.python-version=3.8).
# md_renderer imports mdpopups lazily inside its render path, so no top-level
# sys.modules wiring is needed here (see issue #2).

from .mpe_core import config
from .mpe_core.browser import BrowserSession
from .mpe_core.export_util import export_html, export_pdf
from .mpe_core.html_builder import build_preview_shell
from .mpe_core.md_renderer import render as render_markdown, set_debug_log_path
from .mpe_core.preview_server import (
    SERVER,
    seconds_since_activity,
    pop_open_docs,
    pop_browser_lines,
    has_sse_clients,
    set_editor_line,
    set_output_dir,
    update_content,
)

PLUGIN_NAME = "MarkdownPreviewEnhanced"
_MARKDOWN_SCOPE = "text.html.markdown"

_preview_open = False
_browser = BrowserSession()
_bound_view_id = None
_last_browser_seqs = {}  # 频道 -> 已处理的 browser_line 序号
_bound_views = {}  # 频道(文档路径) -> view.id()
_scroll_timer = None
# 最近一次打开浏览器标签的时间;SSE 连接有建立延迟,宽限期内不判死
_last_browser_open = 0.0
# 浏览器链接点击后等待 on_load_async 渲染的文件
_pending_link_opens = set()


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


def _preview_url(file_path=None):
    if config.get("use_local_server", True):
        if not SERVER.running:
            _ensure_server()
        if SERVER.running:
            # URL 体现当前文档:?file=/abs/path.md,可直接收藏/重开
            if file_path:
                from urllib.parse import quote as _quote
                return SERVER.base_url + "/?file=" + _quote(file_path, safe="")
            return SERVER.base_url + "/"
    return "file://" + config.preview_path()


def _open_preview_browser(url, focus_existing):
    """打开或聚焦预览标签.在后台线程跑,避免 osascript 卡住 UI.

    focus_existing 只在 SSE 仍然连着时为 True.SSE 已断却去 focus,
    会命中正在关闭/已无 EventSource 的僵尸标签,这次按键等于丢掉.
    """
    global _preview_open, _last_browser_open
    _last_browser_open = time.time()
    _preview_open = True
    preferred = config.get("browser", "auto") or "auto"
    _log("browser open: focus_existing=%s url=%s" % (focus_existing, url))

    def _work():
        try:
            ok = _browser.open(
                url,
                preferred=preferred,
                log=_log,
                focus_existing=focus_existing,
            )
            if not ok:
                _log("browser open returned False: %s" % url)
        except Exception as e:
            _log("browser open failed: %s" % e)

    threading.Thread(target=_work, daemon=True).start()
    _start_scroll_poller()


def _preview_alive():
    """True if we believe the live preview session is still usable.

    SSE 已断开时只有「刚 webbrowser.open、等 EventSource 连上」这 3 秒
    算活着,用来挡住同一轮 loading+正文 开两个标签.不能拿它决定
    用户 Toggle 要不要打开:否则链接已断的那次重新激活会被丢掉.
    """
    global _preview_open
    if not _preview_open:
        return False
    if config.get("use_local_server", True) and not SERVER.running:
        _log("preview flag was set but server is down; treating as closed")
        _preview_open = False
        return False
    if config.get("use_local_server", True) and not has_sse_clients():
        age = time.time() - _last_browser_open
        if age > 3:
            _log("no preview page connected via SSE; treating as closed")
            _preview_open = False
            return False
        _log("no SSE yet; within open grace (%.2fs) — not a live tab" % age)
        return True
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
    favicon = config.get("favicon", "") or ""
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
        favicon=favicon,
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
        channel_key = view.file_name() if view is not None else None
        if view is not None:
            _bound_views[channel_key or ""] = view.id()
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
                "favicon": favicon,
            },
            file_path=channel_key,
        )

    _write_files(shell, body)

    sse_live = has_sse_clients()
    if force_open or not _preview_open:
        file_path = view.file_name() if view is not None else None
        url = _preview_url(file_path)
        if view is not None:
            _bound_view_id = view.id()
        _log("preview ready: %s" % url)
        # SSE 已断 = 没有可复用的活标签,必须新开,不能 focus 僵尸页
        _open_preview_browser(url, sse_live)
    else:
        _log(
            "skip browser open (force_open=%s preview_open=%s sse=%s)"
            % (force_open, _preview_open, sse_live)
        )


def _open_doc_from_browser(path):
    """浏览器里点了其它 .md 链接时,在编辑器打开并预览.

    Toggle 打开 /?file=当前文档 时服务器也会入队同一路径,不能再
    open_browser,否则会和 Toggle 抢「要不要开标签」,SSE 将断未断
    时把重新激活丢掉.
    """
    window = sublime.active_window()
    for v in window.views():
        if v.file_name() == path:
            window.focus_view(v)
            already_this = _bound_views.get(path) == v.id()
            MarkdownPreviewEnhancedListener.render_view(
                v, force=True, open_browser=not already_this)
            return
    _pending_link_opens.add(path)
    window.open_file(path)


def _start_scroll_poller():
    """Background tick: scroll-sync + optional idle server shutdown.

    Browser JS polls every ~400ms while the tab is open. If the user closes the
    tab/window without using the plugin command, requests stop and we free the
    port after ``server_idle_seconds`` (default 0 = keep server alive for the
    Sublime session so /doc/ links keep working).
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
        # Default 0 = server stays up for the Sublime session so /doc/ links
        # keep working after the preview tab is closed.
        idle_limit = float(config.get("server_idle_seconds", 0) or 0)
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
                for channel_key, line, seq in pop_browser_lines():
                    if seq > _last_browser_seqs.get(channel_key, 0) and line > 0:
                        _last_browser_seqs[channel_key] = seq
                        view_id = _bound_views.get(channel_key)
                        sublime.set_timeout(
                            lambda l=line, v=view_id: _scroll_editor_to_line(l, v), 0
                        )
            except Exception:
                pass

        # 浏览器里点击 .md 链接 -> 以标准预览流程打开该文件
        # (sublime API 仅限主线程,tick 是后台线程,必须 set_timeout 切换)
        try:
            docs = pop_open_docs()
            if docs:
                for path in docs:
                    _log("open doc from browser link: %s" % path)
                sublime.set_timeout(
                    lambda: [_open_doc_from_browser(p) for p in docs], 0
                )
        except Exception:
            pass

        if _preview_open:
            _scroll_timer = threading.Timer(0.5, _tick)
            _scroll_timer.daemon = True
            _scroll_timer.start()

    _scroll_timer = threading.Timer(0.5, _tick)
    _scroll_timer.daemon = True
    _scroll_timer.start()


def _scroll_editor_to_line(line, view_id=None):
    """Scroll the bound (or active) markdown view to 1-based line."""
    global _bound_view_id
    target_id = view_id or _bound_view_id
    view = None
    for w in sublime.windows():
        for v in w.views():
            if target_id and v.id() == target_id:
                view = v
                break
            if view is None and v.match_selector(0, _MARKDOWN_SCOPE):
                view = v
        if view and target_id and view.id() == target_id:
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

        # 不先发 SSE close:关标签是异步的,随后 _preview_alive() 仍为 True
        # 会跳过 webbrowser.open,表现为快捷键按了没反应.已有标签改由
        # BrowserSession.open(focus_existing=True) 聚焦,没有则新开.
        _log(
            "toggle: open preview (sse=%s preview_open=%s)"
            % (has_sse_clients(), _preview_open)
        )
        self.window.status_message("MarkdownPreviewEnhanced: opening preview…")
        MarkdownPreviewEnhancedListener.render_view(
            view, force=True, open_browser=True, focus_browser=True)


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
                    favicon=config.get("favicon", "") or "",
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
                        favicon=config.get("favicon", "") or "",
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

    def on_load_async(self, view):
        """浏览器链接点击触发的文件加载完成后,走标准预览流程。"""
        fn = view.file_name()
        if fn and fn in _pending_link_opens:
            _pending_link_opens.discard(fn)
            MarkdownPreviewEnhancedListener.render_view(view, force=True, open_browser=True)

    @classmethod
    def render_view(cls, view, force=False, open_browser=False, focus_browser=False):
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
                    # Toggle 始终 open/focus;浏览器内点链接时若标签已在
                    # 就只推内容,避免 /?file= 回环不断开新标签.
                    should_open = focus_browser or not _preview_alive()
                    _publish(loading_result, view, force_open=should_open)
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
                    # 正文推送默认不新开标签.仅当用户要求打开、SSE 已断、
                    # 且不在「刚 open 等连上」宽限内时才补开.
                    sse_live = has_sse_clients()
                    awaiting = _preview_alive()
                    need_open = open_browser and not sse_live and not awaiting
                    if open_browser and not sse_live and awaiting:
                        _log(
                            "content publish: SSE dead but in open grace; "
                            "not opening a second tab"
                        )
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
            set_editor_line(row + 1, file_path=view.file_name())
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
