"""Preview session state, SSE-driven server lifecycle, and background poller.

Owns the ``_preview_open`` flag, SSE idle timer, and the background tick
that drains browser requests and shuts the server down when SSE goes away.
File_path ↔ view ↔ URL mappings live in ``tab_manager``.
"""
import os
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
    has_active_sse_connection,
    set_editor_line,
    set_output_dir,
)

# ── session state ────────────────────────────────────────────────────────────

_preview_open = False
_last_browser_open = 0.0     # ts of last browser open; SSE grace window
_sse_dead_since = None       # ts when SSE first went missing
SSE_IDLE_SECONDS = 10        # stop server after this many s with no SSE

_scroll_timer = None

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
    return _preview_open


def set_preview_open(value):
    global _preview_open
    _preview_open = value


def preview_alive():
    """True if we believe the live preview session is still usable.

    SSE 已断开时只有「刚 open、等 EventSource 连上」这 3 秒算活着,
    用来挡住同一轮 loading+正文 开两个标签.
    """
    global _preview_open
    if not _preview_open:
        return False
    if config.get("use_local_server", True) and not SERVER.running:
        log.debug("preview flag was set but server is down; treating as closed")
        _preview_open = False
        return False
    if config.get("use_local_server", True) and not has_active_sse_connection():
        age = time.time() - _last_browser_open
        if age > 3:
            log.debug("no preview page connected via SSE; treating as closed")
            _preview_open = False
            return False
        log.debug("no SSE yet; within open grace (%.2fs) - not a live tab" % age)
        return True
    return True


# ── browser-tab coordination ─────────────────────────────────────────────────

def mark_browser_open():
    """Record that we just asked the browser to open/focus a preview tab."""
    global _preview_open, _last_browser_open
    _last_browser_open = time.time()
    _preview_open = True


def close_preview_ui(stop_server=False):
    """Close browser window and optionally stop the local server.

    stop_server=False (default): close the browser tab(s) but keep the
    HTTP server running - it will be stopped by the idle poller when the
    SSE connection stays gone for SSE_IDLE_SECONDS. Pass True only on
    plugin_unloaded (ST exit must release the port immediately).
    """
    global _preview_open
    from .browser import BrowserSession
    _browser = BrowserSession()
    hint = None
    if SERVER.running and SERVER.port:
        hint = ":%d" % SERVER.port
    else:
        hint = config.preview_path()
    _browser.close(preview_file_hint=hint, log=browser_log)
    _preview_open = False
    stop_scroll_poller()
    if stop_server:
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
    """Set the direction guard (True while handling a WEB->ST doc switch)."""
    global _suppress_st_to_web_until
    if value:
        _suppress_st_to_web_until = time.time() + 2.0
    else:
        _suppress_st_to_web_until = 0.0


def is_st_to_web_suppressed():
    return time.time() < _suppress_st_to_web_until


def open_doc_from_browser(path, focus_browser=True):
    """Browser notified us: user switched to a doc's preview tab.

    The browser tab is already in front (the user clicked it), so we only
    switch the ST editor.  ``focus_browser`` is kept for API compatibility
    but no OS-level browser focusing happens (cross-platform).
    """
    if tab_manager.focus_view_for_file(path):
        v = tab_manager.find_view_by_file(path)
        # Focus the ST view; suppress the ST->WEB echo so we don't loop.
        suppress_st_to_web(True)
        try:
            from .render import render_view
            render_view(v, force=True, open_browser=False)
        finally:
            suppress_st_to_web(False)
        return
    tab_manager.add_pending_open(path)
    sublime.active_window().open_file(path)


# ── background poller ───────────────────────────────────────────────────────

def start_scroll_poller():
    """Background tick: SSE-driven server shutdown + browser-request drain.

    Polls every ~100ms. The HTTP server stays alive as long as the
    leader tab's SSE connection is open. When SSE goes away (all preview
    tabs closed), we wait SSE_IDLE_SECONDS before stopping the server.
    """
    global _scroll_timer
    if not config.get("use_local_server", True):
        return
    if _scroll_timer is not None:
        return

    def _tick():
        global _scroll_timer, _preview_open
        global _sse_dead_since
        _scroll_timer = None
        if not _preview_open:
            return

        # ── SSE-driven server shutdown ──────────────────────────────
        if SERVER.running:
            try:
                if has_active_sse_connection():
                    _sse_dead_since = None
                else:
                    now = time.time()
                    if _sse_dead_since is None:
                        _sse_dead_since = now
                        log.info("SSE connection gone - starting %ds idle timer"
                                 % SSE_IDLE_SECONDS)
                    elapsed = now - _sse_dead_since
                    if elapsed >= SSE_IDLE_SECONDS:
                        log.info("no SSE for %.0fs - stopping preview server"
                                 % elapsed)
                        _preview_open = False
                        _sse_dead_since = None
                        stop_server_internal()
                        return
            except Exception:
                pass

        # Scroll sync is unidirectional: ST -> browser only.
        # Drain browser scroll reports so they don't pile up.
        try:
            pop_browser_lines()
        except Exception:
            pass

        # Browser -> ST doc switch (sidebar tab click or native tab switch)
        try:
            docs = pop_open_docs()
            if docs:
                items = [(d["path"], d.get("focus_browser", True)) for d in docs]
                for path, fb in items:
                    log.debug("open doc from browser link: %s (focus_browser=%s)"
                              % (path, fb))
                sublime.set_timeout(
                    lambda: [open_doc_from_browser(p, focus_browser=fb)
                             for p, fb in items], 0
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
