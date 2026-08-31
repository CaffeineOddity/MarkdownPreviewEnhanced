"""Document channels, shared preview state, and SSE fan-out helpers.

Owns ``DocChannel`` (per-document state + SSE queues) and ``PreviewState``
(the global mutable state shared between the plugin and the HTTP server).
All public functions that mutate or read this state live here so the
HTTP handler and the plugin don't touch the internals directly.
"""
import json
import queue
import time
import threading

from urllib.parse import unquote, parse_qs


# ── logging hook (set by PreviewServer.start) ────────────────────────────────

_LOG = lambda m: None


def set_log(fn):
    """Set the logger function (called from PreviewServer.start)."""
    global _LOG
    _LOG = fn or (lambda m: None)


def get_log():
    return _LOG


# ── SSE JSON wrapper ─────────────────────────────────────────────────────────

def _json_with_file(payload_json, file_key):
    """给 SSE JSON 补上 file,让全局流上的各 tab 能按文档过滤。"""
    try:
        obj = json.loads(payload_json) if payload_json else {}
    except Exception:
        obj = {}
    if not isinstance(obj, dict):
        obj = {"data": obj}
    obj["file"] = file_key or ""
    return json.dumps(obj, ensure_ascii=False)


# ── per-document channel ─────────────────────────────────────────────────────

class DocChannel:
    """单个文档的预览状态与 SSE 频道(按文档路径分频道,互不干扰)。"""

    def __init__(self):
        self.file_key = ""
        self.body_html = ""
        self.toc_html = ""
        self.full_html = ""
        self.doc_dir = None
        self.editor_line = 0       # cursor line (1-based) -> browser
        self.browser_line = 0      # visible line reported by browser -> editor
        self.browser_line_seq = 0
        self.shell_html = ""       # complete HTML page; served at /?file=<path>
        self.raw_markdown = ""
        self.export_base_dir = None
        self.export_settings = {}
        self.sse_queues = []       # list of queue.Queue

    def _notify_sse(self, event_type, payload_json):
        """Push an SSE event to this channel and to the origin-wide stream."""
        wrapped = _json_with_file(payload_json, self.file_key)
        _LOG("ST->WEB sse push event=%s file=%s" % (event_type, self.file_key))
        with _STATE.lock:
            targets = list(self.sse_queues) + list(_STATE.global_sse_queues)
            _LOG("  targets=%d (channel=%d global=%d)" % (
                len(targets), len(self.sse_queues), len(_STATE.global_sse_queues)))
            dead = []
            for q in targets:
                try:
                    q.put_nowait((event_type, wrapped))
                except queue.Full:
                    dead.append(q)
            for q in dead:
                if q in self.sse_queues:
                    self.sse_queues.remove(q)
                elif q in _STATE.global_sse_queues:
                    _STATE.global_sse_queues.remove(q)
        if dead:
            _LOG("sse fanout %s: dropped %d full queue(s)" % (
                event_type, len(dead)))


# ── global shared state ──────────────────────────────────────────────────────

class PreviewState:
    """Shared mutable state between the plugin and the HTTP server."""

    def __init__(self):
        self.lock = threading.Lock()
        self.channels = {"": DocChannel()}
        self.global_sse_queues = []
        self.output_dir = None
        self.last_activity = 0.0
        self.pending_open_docs = []

    def channel(self, file_path):
        """Return (creating if needed) the channel for *file_path*. Caller holds lock."""
        key = file_path or ""
        ch = self.channels.get(key)
        if ch is None:
            ch = DocChannel()
            self.channels[key] = ch
        ch.file_key = key
        return ch


_STATE = PreviewState()

# OS-open / Toggle 后短时间内,Chrome 会先把旧窗口(仍显示上一份预览)拉到前台,
# 旧 tab 的 notifyDocSwitch 会把 ST 拽回去。这段时间只接受「刚打开的那份」的 tab_switch.
_os_open_file = None
_os_open_pin_until = 0.0


def pin_os_open_file(file_path, seconds=2.0):
    """After Toggle OS-open, ignore tab_switch open_doc for any other file.

    Also SSE pinTab so existing preview pages skip notifyDocSwitch.
    """
    global _os_open_file, _os_open_pin_until
    _os_open_file = file_path or ""
    _os_open_pin_until = time.time() + float(seconds)
    payload = json.dumps({}, ensure_ascii=False)
    _push_all_sse("pinTab", payload, _os_open_file)


def reset_os_open_pin():
    global _os_open_file, _os_open_pin_until
    _os_open_file = None
    _os_open_pin_until = 0.0


def tab_switch_allowed(file_path):
    if time.time() >= _os_open_pin_until:
        return True
    return (file_path or "") == _os_open_file


# ── public API ───────────────────────────────────────────────────────────────

def state():
    return _STATE


def _escape(s):
    import html as _html
    return _html.escape(s or "", quote=True)


def _file_key_from_query(query):
    """从 query 提取频道标识:?file=<编码后的绝对路径>;无则返回 ""。"""
    q = unquote(query or "").strip()
    if not q:
        return ""
    try:
        params = parse_qs(q)
        if "file" in params and params["file"]:
            return params["file"][0]
    except Exception:
        pass
    for prefix in ("file://", "file="):
        if q.startswith(prefix):
            q = q[len(prefix):]
            break
    if q.startswith("file://"):
        q = q[len("file://"):]
    return q


def touch_activity():
    with _STATE.lock:
        _STATE.last_activity = time.time()


def seconds_since_activity():
    with _STATE.lock:
        if not _STATE.last_activity:
            return 1e9
        return time.time() - _STATE.last_activity


def update_content(body_html, toc_html, full_html, content_hash, doc_dir,
                   shell_html=None, raw_markdown=None, export_base_dir=None,
                   export_settings=None, file_path=None):
    """Update the channel of *file_path* and push content via SSE."""
    with _STATE.lock:
        ch = _STATE.channel(file_path)
        ch.body_html = body_html or ""
        ch.toc_html = toc_html or ""
        ch.full_html = full_html or ""
        if doc_dir:
            ch.doc_dir = doc_dir
        if shell_html is not None:
            ch.shell_html = shell_html
        if raw_markdown is not None:
            ch.raw_markdown = raw_markdown
        if export_base_dir is not None:
            ch.export_base_dir = export_base_dir
        if export_settings is not None:
            ch.export_settings = export_settings
        payload = json.dumps({
            "html": ch.body_html,
            "toc": ch.toc_html,
        }, ensure_ascii=False)
    ch._notify_sse("content", payload)


def set_editor_line(line, file_path=None):
    with _STATE.lock:
        ch = _STATE.channel(file_path)
        ch.editor_line = int(line or 0)
        payload = json.dumps({"line": ch.editor_line}, ensure_ascii=False)
    ch._notify_sse("editorLine", payload)


def pop_browser_lines():
    """Return [(file_path, line, seq)] for channels with new browser scroll."""
    with _STATE.lock:
        events = []
        for key, ch in _STATE.channels.items():
            if ch.browser_line:
                events.append((key, ch.browser_line, ch.browser_line_seq))
                ch.browser_line = 0
        return events


def close_browser_tabs():
    """Push a 'close' event to all connected SSE listeners."""
    with _STATE.lock:
        channels = list(_STATE.channels.values())
    for ch in channels:
        ch._notify_sse("close", "{}")


def set_output_dir(path):
    with _STATE.lock:
        _STATE.output_dir = path


def set_active_doc(file_path=None):
    """ST->WEB: push 'switchTab' SSE event so the matching browser tab focuses itself.

    The matching tab (data.file === channelFile) calls window.focus().
    Cross-platform - no AppleScript.
    """
    import json as _json
    with _STATE.lock:
        ch = _STATE.channel(file_path)
        payload = _json.dumps({}, ensure_ascii=False)
    ch._notify_sse("switchTab", payload)


def _push_all_sse(event_type, payload_json, file_key=""):
    """Fan an event out to every SSE listener (global + per-channel)."""
    wrapped = _json_with_file(payload_json, file_key)
    with _STATE.lock:
        targets = list(_STATE.global_sse_queues)
        for ch in _STATE.channels.values():
            targets.extend(ch.sse_queues)
        dead = []
        for q in targets:
            try:
                q.put_nowait((event_type, wrapped))
            except queue.Full:
                dead.append(q)
        for q in dead:
            if q in _STATE.global_sse_queues:
                _STATE.global_sse_queues.remove(q)
            else:
                for ch in _STATE.channels.values():
                    if q in ch.sse_queues:
                        ch.sse_queues.remove(q)
                        break


def notify_close_old(file_path, gen):
    payload = json.dumps({"gen": int(gen)}, ensure_ascii=False)
    _push_all_sse("close_old", payload, file_path)


def notify_tabs(files=None):
    from . import tab_manager
    if files is None:
        files = tab_manager.live_files()
    payload = json.dumps({"files": list(files)}, ensure_ascii=False)
    _push_all_sse("tabs", payload, "")


def snapshot_payload(file_path):
    """Current html/toc/line for *file_path* (same body as /api/snapshot)."""
    with _STATE.lock:
        ch = _STATE.channel(file_path)
        return {
            "file": file_path or "",
            "html": ch.body_html,
            "toc": ch.toc_html,
            "line": ch.editor_line,
        }


def handle_tab_open(file_path):
    """Register a live browser tab. Returns the tab_open result dict."""
    from . import tab_manager
    result = tab_manager.tab_open(file_path)
    if result is None:
        return None
    if result.get("replaced"):
        notify_close_old(file_path, result["old_gen"])
        _LOG("close_old file=%s gen=%s" % (file_path, result["old_gen"]))
    notify_tabs(result.get("files"))
    _LOG("tab_open file=%s tabs=%d replaced=%s"
         % (file_path, tab_manager.live_count(), result.get("replaced")))
    snap = snapshot_payload(file_path)
    result["html"] = snap["html"]
    result["toc"] = snap["toc"]
    result["line"] = snap["line"]
    return result


def handle_tab_close(file_path, gen):
    from . import tab_manager
    removed = tab_manager.tab_close(file_path, gen)
    notify_tabs()
    if removed:
        remaining = tab_manager.live_count()
        _LOG("tab_close file=%s remaining=%d" % (file_path, remaining))
    return removed


def queue_open_doc(path, focus_browser=False):
    """Queue an absolute .md path for the plugin to open as a standard preview.

    ``focus_browser`` is unused for OS-open (tabs are 1:1 via the registry);
    kept so queued items still carry the flag for logging.
    """
    with _STATE.lock:
        for item in _STATE.pending_open_docs:
            if item["path"] == path:
                if focus_browser:
                    item["focus_browser"] = True
                return
        _STATE.pending_open_docs.append(
            {"path": path, "focus_browser": focus_browser})


def pop_open_docs():
    """Return and clear queued .md open requests from the browser."""
    with _STATE.lock:
        docs = list(_STATE.pending_open_docs)
        _STATE.pending_open_docs = []
        return docs


def has_active_sse_connection():
    """True if the leader tab's SSE connection is still open.

    Due to the leader-election design (see preview.js), the entire browser
    session shares a single EventSource to /api/stream. This returns True
    when that one connection exists, meaning at least one preview tab is alive.
    """
    with _STATE.lock:
        if _STATE.global_sse_queues:
            return True
        return any(ch.sse_queues for ch in _STATE.channels.values())
