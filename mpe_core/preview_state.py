"""Preview session state, tab-count server lifecycle, and background poller.

HTTP/SSE stay up while ``tab_manager`` has any session row (pending register
or live tab).  They stop after the last tab closes (STOP_GRACE covers F5)
or when live tabs exist but SSE is gone for CRASH_IDLE (browser crash).
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
_last_browser_open = 0.0     # ts of last OS-open (diagnostics)
_sse_dead_since = None       # ts when SSE first went missing while tabs alive
_empty_since = None          # ts when session_count first hit 0
STOP_GRACE = 2.0             # wait after last tab_close before stop (F5)
CRASH_IDLE = 60.0            # live tabs but no SSE: assume crash

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
            pop_browser_lines()
        except Exception:
            pass

        try:
            docs = pop_open_docs()
            if docs:
                items = [(d["path"], d.get("focus_browser", False)) for d in docs]
                for path, fb in items:
                    log.debug("open doc from browser: %s (focus_browser=%s)"
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
