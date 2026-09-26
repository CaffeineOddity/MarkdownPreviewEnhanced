"""Preview session state, tab-count server lifecycle, and background poller.

HTTP/SSE stay up while ``tab_manager`` has any session row (pending register
or live tab).  They stop after the last tab closes (STOP_GRACE covers F5)
or when live tabs exist but SSE is gone for CRASH_IDLE (browser crash).
"""
import re
import threading
import time

import sublime

from . import config
from . import log
from . import tab_manager
from .preview_server import (
    SERVER,
    pop_open_docs,
    pop_browser_lines,
    pop_task_toggles,
    has_active_sse_connection,
    set_editor_line,
    set_output_dir,
)

# ── session state ────────────────────────────────────────────────────────────

_preview_open = False
_last_browser_open = 0.0     # ts of last OS-open (diagnostics)
_sse_dead_since = None       # ts when SSE first went missing while tabs alive
_empty_since = None          # ts when session_count first hit 0
STOP_GRACE = 2.0             # wait after last tab_close before stop (F5)
CRASH_IDLE = 60.0            # live tabs but no SSE: assume crash

_scroll_timer = None
_last_browser_seqs = {}      # 频道 -> 已处理的 browser_line 序号

# Re-export tab_manager state for backward compatibility (MarkdownPreviewEnhanced.py
# imports _bound_view_id and _pending_link_opens from here).
_bound_view_id = tab_manager.get_bound_view_id()
_bound_views = tab_manager._bound_views
_pending_link_opens = tab_manager._pending_link_opens


# ── logging shims ────────────────────────────────────────────────────────────

def server_log(msg):
    text = msg or ""
    low = text.lower()
    if "failed" in low or "error" in low:
        log.error(text)
    elif text.startswith("preview server"):
        log.info(text)
    else:
        log.debug(text)


def browser_log(msg):
    text = msg or ""
    low = text.lower()
    if "failed" in low or "error" in low:
        log.error(text)
    else:
        log.debug(text)


# ── server lifecycle ─────────────────────────────────────────────────────────

def ensure_server():
    """Start the HTTP server if not already running. Returns base_url or None."""
    if not config.get("use_local_server", True):
        return None
    set_output_dir(config.output_dir())
    port = int(config.get("server_port", 8765) or 8765)
    url = SERVER.start(port=port, log=server_log)
    if not url:
        log.error("failed to start preview server on port %s" % port)
        return None
    global _preview_open, _empty_since, _sse_dead_since
    _preview_open = True
    _empty_since = None
    _sse_dead_since = None
    start_scroll_poller()
    return url


def stop_server():
    """Release the local HTTP port."""
    if SERVER.running:
        try:
            SERVER.stop(log=server_log)
        except Exception as e:
            log.error("server stop failed: %s" % e)


# ── preview-liveness checks ─────────────────────────────────────────────────

def is_preview_open():
    """True while the HTTP server is up (a preview session exists)."""
    if config.get("use_local_server", True):
        return bool(_preview_open and SERVER.running)
    return _preview_open


def set_preview_open(value):
    global _preview_open
    _preview_open = value


def preview_alive():
    """True if the preview HTTP session is still running.

    Liveness is tab-registry + server, not a 3s SSE guess.  Missing SSE
    while tabs are alive is handled by CRASH_IDLE in ``_tick``.
    """
    return is_preview_open()


# ── browser-tab coordination ─────────────────────────────────────────────────

def mark_browser_open():
    """Record that we just asked the browser to open/focus a preview tab."""
    global _preview_open, _last_browser_open
    _last_browser_open = time.time()
    _preview_open = True


def close_preview_ui(stop_server=False):
    """Ask preview tabs to close themselves. Server stops via STOP_GRACE
    unless *stop_server* is True (plugin unload).
    """
    global _preview_open
    from .preview_state_core import close_browser_tabs
    from .browser import BrowserSession
    close_browser_tabs()
    tab_manager.reset()
    _browser = BrowserSession()
    hint = None
    if SERVER.running and SERVER.port:
        hint = ":%d" % SERVER.port
    else:
        hint = config.preview_path()
    _browser.close(preview_file_hint=hint, log=browser_log)
    if stop_server:
        _preview_open = False
        stop_scroll_poller()
        stop_server_internal()
    log.info("preview closed (server %s)" % ("stopped" if stop_server else "kept"))


def stop_scroll_poller():
    global _scroll_timer
    if _scroll_timer is not None:
        try:
            _scroll_timer.cancel()
        except Exception:
            pass
        _scroll_timer = None


def stop_server_internal():
    """Alias kept for close_preview_ui internal call."""
    stop_server()


# ── browser -> ST doc switch ─────────────────────────────────────────────────

# Direction guard: while this window is active, on_activated_async will NOT
# push switchTab back. Breaks the WEB->ST -> ST->WEB -> WEB->ST loop
# (browser tab switch -> ST focus_view -> on_activated_async -> switchTab ->
# window.open -> hasFocus -> notifyDocSwitch -> ...).
# Time-based because focus_view triggers on_activated_async asynchronously.
_suppress_st_to_web_until = 0.0


def suppress_st_to_web(value):
    """Arm the direction guard. False is a no-op so a 2s window is not cleared."""
    global _suppress_st_to_web_until
    if value:
        _suppress_st_to_web_until = time.time() + 2.0


def is_st_to_web_suppressed():
    return time.time() < _suppress_st_to_web_until


def open_doc_from_browser(path, focus_browser=True):
    """Browser notified us: user switched to a doc's preview tab.

    Only switch the ST editor. Never OS-open a browser tab.
    """
    suppress_st_to_web(True)
    if tab_manager.focus_view_for_file(path):
        v = tab_manager.find_view_by_file(path)
        from .render import render_view
        render_view(v, force=True, open_browser=False)
        return
    tab_manager.add_pending_open(path)
    sublime.active_window().open_file(path)


# ── browser → ST scroll ──────────────────────────────────────────────────────

_MARKDOWN_SCOPE = "text.html.markdown"


def _scroll_editor_to_line(line, view_id):
    """Scroll the bound markdown view to 1-based line."""
    view = None
    for w in sublime.windows():
        for v in w.views():
            if view_id and v.id() == view_id:
                view = v
                break
            if view is None and v.match_selector(0, _MARKDOWN_SCOPE):
                view = v
        if view and view_id and view.id() == view_id:
            break
    if view is None:
        return
    try:
        pt = view.text_point(max(0, line - 1), 0)
        view.sel().clear()
        view.sel().add(sublime.Region(pt))
        # Pin the line to the top of the viewport (same as the browser
        # scrollToLine pad). show_at_center would put it mid-screen and
        # look "off" relative to the preview.
        xy = view.text_to_layout(pt)
        vx, _vy = view.viewport_position()
        view.set_viewport_position((vx, max(0, xy[1])), False)
    except Exception as e:
        log.debug("scroll editor failed: %s" % e)


# ── browser → ST checkbox 回写 ───────────────────────────────────────────────

# 任务项列表标记：`- [ ]` / `* [x]` / `1. [X]`（捕获 [ 前缀、标记字符、] 后缀）。
# 要求 ] 后是空白或行尾（`[ ]nospace` 不算任务标记，与 GFM 一致）；
# 尾部的空白只做 look-ahead 消费，不并入替换范围。
_TASK_ITEM_RE = re.compile(r"^(\s*(?:[-*+]|\d+\.)\s+\[)([ xX])(\])(?=\s|$)")


def _task_toggle_new_text(line_text, checked):
    """返回把 *line_text* 的任务标记改成 *checked* 状态后的新行文本。

    行不是任务项时返回 None（调用方跳过，不动文件）。
    """
    m = _TASK_ITEM_RE.match(line_text)
    if not m:
        return None
    mark = "x" if checked else " "
    return m.group(1) + mark + m.group(3) + line_text[m.end():]


def _apply_task_toggle_edit(view, edit, line, checked):
    """把 *view* 中 1-based *line* 行的任务标记替换为 *checked* 状态。

    必须在 TextCommand 里调用：``view.replace`` 需要这次 ``run`` 的 edit。
    行内容不再是任务项（文件已改、行号漂移）时静默跳过。
    """
    if view is None or edit is None or line < 1:
        return
    try:
        line_pt = view.text_point(line - 1, 0)
        line_region = view.line(line_pt)
        line_text = view.substr(line_region)
        new_text = _task_toggle_new_text(line_text, checked)
        if new_text is None or new_text == line_text:
            log.debug("task_toggle skipped line=%d (not a task item)" % line)
            return
        # 只替换 [ ] / [x] 的标记字符，保留行内其余内容
        m = _TASK_ITEM_RE.match(line_text)
        mark_start = line_region.begin() + m.start(2)
        mark_end = line_region.begin() + m.end(2)
        view.replace(
            edit, sublime.Region(mark_start, mark_end),
            "x" if checked else " ")
        log.debug("task_toggle applied line=%d checked=%s" % (line, checked))
    except Exception as e:
        log.error("task_toggle edit failed line=%d: %s" % (line, e))


def _dispatch_task_toggle(file_key, view_id, line, checked):
    """在主线程用 TextCommand 写回。直接 view.replace 没有 edit，会被 ST 拒绝。"""
    view = _find_markdown_view(view_id) if view_id else None
    if view is None:
        view = tab_manager.find_view_by_file(file_key)
    if view is None:
        log.debug("task_toggle skipped: no view file=%s line=%d" % (file_key, line))
        return
    view.run_command(
        "markdown_preview_enhanced_task_toggle",
        {"line": int(line), "checked": bool(checked)},
    )


def _find_markdown_view(view_id):
    """按 view_id 精确查找视图，找不到退回第一个 markdown 视图。"""
    for w in sublime.windows():
        for v in w.views():
            if view_id and v.id() == view_id:
                return v
            if view_id is None and v.match_selector(0, _MARKDOWN_SCOPE):
                return v
    return None


# ── background poller ───────────────────────────────────────────────────────

def start_scroll_poller():
    """Background tick: tab-count shutdown + browser-request drain."""
    global _scroll_timer
    if not config.get("use_local_server", True):
        return
    if _scroll_timer is not None:
        return

    def _tick():
        global _scroll_timer, _preview_open
        global _sse_dead_since, _empty_since
        _scroll_timer = None
        if not _preview_open:
            return

        if SERVER.running:
            try:
                tab_manager.drop_stale_pending(max_age=30.0)
                now = time.time()
                sessions = tab_manager.session_count()
                live = tab_manager.live_count()
                if sessions == 0:
                    _sse_dead_since = None
                    if _empty_since is None:
                        _empty_since = now
                        log.debug("no preview tabs - starting %.0fs stop grace"
                                  % STOP_GRACE)
                    elif now - _empty_since >= STOP_GRACE:
                        log.info("all preview tabs closed - stopping HTTP server")
                        _preview_open = False
                        _empty_since = None
                        stop_server_internal()
                        return
                else:
                    _empty_since = None
                    if live > 0 and not has_active_sse_connection():
                        if _sse_dead_since is None:
                            _sse_dead_since = now
                            log.info("SSE gone with live tabs - crash idle %ds"
                                     % int(CRASH_IDLE))
                        elif now - _sse_dead_since >= CRASH_IDLE:
                            log.info("no SSE for %.0fs - stopping HTTP server"
                                     % (now - _sse_dead_since))
                            tab_manager.reset()
                            _preview_open = False
                            _sse_dead_since = None
                            stop_server_internal()
                            return
                    else:
                        _sse_dead_since = None
            except Exception as e:
                log.error("preview tick lifecycle failed: %s" % e)

        try:
            if config.get("scroll_sync", True):
                for channel_key, line, seq in pop_browser_lines():
                    if seq > _last_browser_seqs.get(channel_key, 0) and line > 0:
                        _last_browser_seqs[channel_key] = seq
                        view_id = tab_manager.get_view_id_for_file(channel_key)
                        sublime.set_timeout(
                            lambda l=line, v=view_id: _scroll_editor_to_line(l, v), 0
                        )
            else:
                pop_browser_lines()
        except Exception:
            pass

        try:
            docs = pop_open_docs()
            if docs:
                items = [(d["path"], d.get("focus_browser", False)) for d in docs]
                for path, fb in items:
                    log.debug("open doc from browser: %s (focus_browser=%s) tabs=%d"
                              % (path, fb, tab_manager.live_count()))
                sublime.set_timeout(
                    lambda: [open_doc_from_browser(p, focus_browser=fb)
                             for p, fb in items], 0
                )
        except Exception:
            pass

        try:
            toggles = pop_task_toggles()
            for file_key, line, checked in toggles:
                view_id = tab_manager.get_view_id_for_file(file_key)
                sublime.set_timeout(
                    lambda fk=file_key, vl=view_id, l=line, c=checked: (
                        _dispatch_task_toggle(fk, vl, l, c)), 0
                )
        except Exception:
            pass

        if _preview_open:
            _scroll_timer = threading.Timer(0.1, _tick)
            _scroll_timer.daemon = True
            _scroll_timer.start()

    _scroll_timer = threading.Timer(0.1, _tick)
    _scroll_timer.daemon = True
    _scroll_timer.start()
