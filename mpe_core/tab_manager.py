"""Unified mapping: file_path ↔ ST view_id ↔ browser tab (1:1:1).

This module is the registry.  SSE/HTTP start-stop lives in ``preview_state``.
Browser tabs announce themselves via ``/api/tab_open`` / ``/api/tab_close``;
those handlers call ``tab_open`` / ``tab_close`` here.

A row exists from ``register`` (Cmd+Shift+M, before OS-open) or ``tab_open``
(page load).  ``alive`` is True only after ``tab_open``.  Closing a tab deletes
the row when ``gen`` matches, so a stale close cannot drop the replacement tab.
"""
import threading
import time
from urllib.parse import quote as _quote

import sublime

from . import config
from . import log
from .preview_server import SERVER


# ── internal state ───────────────────────────────────────────────────────────

_lock = threading.Lock()
# file_path -> {view_id, gen, alive, ts}
_tabs = {}
_bound_views = {}            # file_path (str) -> view.id() (int); ST-side cache
_bound_view_id = None        # "current" view.id() - used by on_selection_modified
_pending_link_opens = set()  # file paths waiting for on_load_async


# ── file_path ↔ view ────────────────────────────────────────────────────────

def bind_view(view):
    """Record that *view* is the active editor for its file_path.

    Called from ``render.publish`` after rendering a view.  Last activated
    view wins when the same file is open in a split.
    """
    global _bound_view_id
    if view is None:
        return
    fp = view.file_name()
    log.debug(f"bind_view ==> {fp}")
    if fp:
        _bound_views[fp] = view.id()
        with _lock:
            rec = _tabs.get(fp)
            if rec is not None:
                rec["view_id"] = view.id()
    _bound_view_id = view.id()


def get_view_id_for_file(file_path):
    """Return the view.id() bound to *file_path*, or None."""
    fp = file_path or ""
    with _lock:
        rec = _tabs.get(fp)
        if rec and rec.get("view_id") is not None:
            return rec["view_id"]
    return _bound_views.get(fp)


def get_bound_view_id():
    """Return the 'current' bound view id (for on_selection_modified filtering)."""
    return _bound_view_id


def set_bound_view_id(view_id):
    global _bound_view_id
    _bound_view_id = view_id


def find_view_by_file(file_path):
    """Search all open ST views for one whose file_name() matches *file_path*.

    Returns the ``sublime.View`` or ``None``.
    """
    if not file_path:
        return None
    for w in sublime.windows():
        for v in w.views():
            if v.file_name() == file_path:
                return v
    return None


def focus_view_for_file(file_path):
    """Switch the ST active view to the one for *file_path*. Returns True if found.

    必须用 view 所在 window,不能用 active_window():用户点浏览器时 ST 在后台,
    对错误 window 调 focus_view 等于没切。ST 失焦时 focus_view 也常被忽略,
    ST4 再用 select_sheets 选中对应 sheet.
    """
    v = find_view_by_file(file_path)
    if v is None:
        log.debug("focus_view: no view for %s" % file_path)
        return False
    window = v.window()
    if window is None:
        window = sublime.active_window()
    if window is None:
        log.debug("focus_view: no window for %s" % file_path)
        return False
    group, _index = window.get_view_index(v)
    if group >= 0:
        window.focus_group(group)
    window.focus_view(v)
    sheet_fn = getattr(v, "sheet", None)
    select_sheets = getattr(window, "select_sheets", None)
    if sheet_fn and select_sheets:
        sheet = sheet_fn()
        if sheet is not None:
            select_sheets([sheet])
    active = window.active_view()
    active_fn = active.file_name() if active is not None else None
    log.debug("focus_view file=%s active=%s" % (file_path, active_fn))
    return True


# ── pending link opens (browser -> ST on_load_async) ────────────────────────

def add_pending_open(file_path):
    """Mark *file_path* as waiting for ``on_load_async``."""
    _pending_link_opens.add(file_path)


def consume_pending_open(file_path):
    """If *file_path* was pending, remove and return True; else False."""
    if file_path in _pending_link_opens:
        _pending_link_opens.discard(file_path)
        return True
    return False


def has_pending_opens():
    return bool(_pending_link_opens)


# ── file_path ↔ browser tab (generation / liveness) ─────────────────────────

def register(file_path, view_id=None):
    """Ensure a registry row. Does not mark the browser tab alive."""
    if not file_path:
        return
    with _lock:
        rec = _tabs.get(file_path)
        if rec is None:
            _tabs[file_path] = {
                "view_id": view_id,
                "gen": 0,
                "alive": False,
                "ts": time.time(),
            }
        else:
            if view_id is not None:
                rec["view_id"] = view_id
            rec["ts"] = time.time()
    if view_id is not None:
        _bound_views[file_path] = view_id


def tab_open(file_path):
    """Mark *file_path* as having a live browser tab. Bump generation.

    Returns a dict ``{file, gen, old_gen, replaced, files}``, or None if
    *file_path* is empty.
    """
    if not file_path:
        return None
    with _lock:
        rec = _tabs.get(file_path)
        old_gen = rec["gen"] if rec and rec.get("alive") else None
        if rec is None:
            rec = {"view_id": None, "gen": 0, "alive": False, "ts": time.time()}
            _tabs[file_path] = rec
        rec["gen"] = int(rec.get("gen") or 0) + 1
        rec["alive"] = True
        rec["ts"] = time.time()
        files = _live_files_unlocked()
        return {
            "file": file_path,
            "gen": rec["gen"],
            "old_gen": old_gen,
            "replaced": old_gen is not None,
            "files": files,
        }


def tab_close(file_path, gen):
    """Remove the row if *gen* matches the current generation. Idempotent."""
    if not file_path:
        return False
    try:
        gen = int(gen)
    except (TypeError, ValueError):
        return False
    with _lock:
        rec = _tabs.get(file_path)
        if rec is None:
            return False
        if int(rec.get("gen") or 0) != gen:
            return False
        _tabs.pop(file_path, None)
        return True


def is_alive(file_path):
    if not file_path:
        return False
    with _lock:
        rec = _tabs.get(file_path)
        return bool(rec and rec.get("alive"))


def live_count():
    with _lock:
        return sum(1 for rec in _tabs.values() if rec.get("alive"))


def live_files():
    with _lock:
        return _live_files_unlocked()


def session_count():
    """Rows including pending (registered, not yet tab_open)."""
    with _lock:
        return len(_tabs)


def has_session(file_path):
    """True if *file_path* has a registry row (pending or live)."""
    if not file_path:
        return False
    with _lock:
        return file_path in _tabs


def drop_stale_pending(max_age=15.0):
    """Drop register-only rows that never got a tab_open. Returns dropped count."""
    now = time.time()
    dropped = 0
    with _lock:
        stale = [
            fp for fp, rec in _tabs.items()
            if not rec.get("alive") and (now - rec.get("ts", 0)) > max_age
        ]
        for fp in stale:
            _tabs.pop(fp, None)
            dropped += 1
    return dropped


def _live_files_unlocked():
    return sorted(fp for fp, rec in _tabs.items() if rec.get("alive"))


# ── file_path ↔ URL ──────────────────────────────────────────────────────────

def preview_url(file_path=None):
    """Return the preview URL for *file_path* (or the generic URL).

    Server mode: ``http://127.0.0.1:<port>/?file=<abspath>``
    File mode:   ``file://<preview_path>``
    """
    if config.get("use_local_server", True):
        if not SERVER.running:
            from . import preview_state
            preview_state.ensure_server()
        if SERVER.running:
            if file_path:
                return SERVER.base_url + "/?file=" + _quote(file_path, safe="")
            return SERVER.base_url + "/"
    return "file://" + config.preview_path()


# ── file_path ↔ channel (server-side) ────────────────────────────────────────

def channel_has_content(file_path):
    """True if the server-side channel for *file_path* already has rendered content."""
    from .preview_state_core import state
    with state().lock:
        ch = state().channels.get(file_path or "")
        return ch is not None and bool(ch.shell_html or ch.body_html)


# ── session reset ────────────────────────────────────────────────────────────

def reset():
    """Clear all bindings (called on close / plugin unload)."""
    global _bound_view_id
    with _lock:
        _tabs.clear()
    _bound_views.clear()
    _bound_link_opens_clear()
    _bound_view_id = None


def _bound_link_opens_clear():
    _pending_link_opens.clear()
