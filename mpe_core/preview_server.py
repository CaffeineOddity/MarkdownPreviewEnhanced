"""Local HTTP server for live preview, media, SSE push, and scroll-sync."""
import hashlib
import json
import os
import queue
import select
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import unquote, urlparse

from . import assets as pkg_assets

# 包内静态资源进程内缓存:(bytes, etag)
_ASSET_MEM = {}
_ASSET_MEM_LOCK = threading.Lock()


def _cached_package_asset(resource_rel):
    with _ASSET_MEM_LOCK:
        hit = _ASSET_MEM.get(resource_rel)
        if hit is not None:
            return hit
    data = pkg_assets.read_bytes(resource_rel)
    if data is None:
        return None
    etag = hashlib.sha256(data).hexdigest()[:16]
    packed = (data, etag)
    with _ASSET_MEM_LOCK:
        _ASSET_MEM[resource_rel] = packed
    return packed


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Threaded HTTP server — Python 3.3+ compatible (ST3/ST4 safe)."""
    daemon_threads = True


    def handle_error(self, request, client_address):
        # 浏览器关闭标签/刷新页面时 SSE 连接被重置,属于正常噪音
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError,
                            BrokenPipeError)):
            return
        HTTPServer.handle_error(self, request, client_address)


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


class DocChannel:
    """单个文档的预览状态与 SSE 频道(按文档路径分频道,互不干扰)。"""

    def __init__(self):
        self.file_key = ""
        self.body_html = ""
        self.toc_html = ""
        self.full_html = ""
        self.doc_dir = None  # directory of the markdown file
        self.editor_line = 0  # cursor line in editor (1-based) -> browser
        self.browser_line = 0  # visible line reported by browser -> editor
        self.browser_line_seq = 0
        self.shell_html = ""  # complete HTML page; served at /?file=<path>
        # For server-side export (PDF/PNG/HTML)
        self.raw_markdown = ""
        self.export_base_dir = None
        self.export_settings = {}  # render settings dict
        # SSE push - pages of this document hold persistent connections
        self.sse_queues = []  # list of queue.Queue

    def _notify_sse(self, event_type, payload_json):
        """Push an SSE event to this channel and to the origin-wide stream."""
        wrapped = _json_with_file(payload_json, self.file_key)
        with _STATE.lock:
            targets = list(self.sse_queues) + list(_STATE.global_sse_queues)
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


class PreviewState:
    """Shared mutable state between the plugin and the HTTP server."""

    def __init__(self):
        self.lock = threading.Lock()
        # 文档路径 -> 频道;"" 为无文件名视图(未保存 buffer)的默认频道
        self.channels = {"": DocChannel()}
        # 无 ?file= 的 /api/stream:一条连接收全部文档(BroadcastChannel 选主用)
        self.global_sse_queues = []
        self.output_dir = None
        self.last_activity = 0.0  # unix time of last HTTP request
        # 浏览器点击 .md 链接 -> 插件按标准预览流程打开该文件
        self.pending_open_docs = []  # list of absolute .md paths

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


def _escape(s):
    """HTML 转义,用于错误页展示用户输入的路径。"""
    import html as _html
    return _html.escape(s or "", quote=True)


def state():
    return _STATE


def _file_key_from_query(query):
    """从 query 提取频道标识:?file=<编码后的绝对路径>;无则返回 ""。"""
    q = unquote(query or "").strip()
    if not q:
        return ""
    for prefix in ("file://", "file="):
        if q.startswith(prefix):
            q = q[len(prefix):]
            break
    if q.startswith("file://"):
        q = q[len("file://"):]
    return q


def touch_activity():
    """Record that a client is still talking to the server."""
    with _STATE.lock:
        _STATE.last_activity = time.time()


def seconds_since_activity():
    with _STATE.lock:
        if not _STATE.last_activity:
            return 1e9
        return time.time() - _STATE.last_activity


def update_content(body_html, toc_html, full_html, content_hash, doc_dir, shell_html=None,
                   raw_markdown=None, export_base_dir=None, export_settings=None,
                   file_path=None):
    """Update the channel of *file_path*(默认频道用于无文件名视图)。"""
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
    # SSE fan-out outside the lock.
    ch._notify_sse("content", payload)


def set_editor_line(line, file_path=None):
    with _STATE.lock:
        ch = _STATE.channel(file_path)
        ch.editor_line = int(line or 0)
        payload = json.dumps({"line": ch.editor_line}, ensure_ascii=False)
    # SSE fan-out outside the lock.
    ch._notify_sse("editorLine", payload)


def pop_browser_lines():
    """Return [(file_path, line, seq)] for channels with new browser scroll reports."""
    with _STATE.lock:
        events = []
        for key, ch in _STATE.channels.items():
            if ch.browser_line:
                events.append((key, ch.browser_line, ch.browser_line_seq))
                ch.browser_line = 0
        return events


def close_browser_tabs():
    """Push a 'close' event to all connected SSE listeners - each tab closes itself."""
    with _STATE.lock:
        channels = list(_STATE.channels.values())
    # SSE fan-out outside the lock.
    for ch in channels:
        ch._notify_sse("close", "{}")


def set_output_dir(path):
    with _STATE.lock:
        _STATE.output_dir = path


def queue_open_doc(path):
    """Queue an absolute .md path for the plugin to open as a standard preview."""
    with _STATE.lock:
        if path not in _STATE.pending_open_docs:
            _STATE.pending_open_docs.append(path)


def pop_open_docs():
    """Return and clear queued .md open requests from the browser."""
    with _STATE.lock:
        docs = list(_STATE.pending_open_docs)
        _STATE.pending_open_docs = []
        return docs


def has_active_sse_connection():
    """True if the leader tab's SSE connection is still open.

    Due to the leader-election design (see preview.js), the entire
    browser session shares a single EventSource to /api/stream. This
    function returns True when that one connection exists, meaning at
    least one preview tab is alive.
    """
    with _STATE.lock:
        if _STATE.global_sse_queues:
            return True
        return any(ch.sse_queues for ch in _STATE.channels.values())



_LOG = lambda m: None


def _peer_gone(conn):
    """True if the client closed, reset, or wrote unexpected extra bytes.

    EventSource 在 GET 之后不再发送数据。socket 变可读只可能是 FIN/RST,
    或浏览器把这条 SSE 连接拿去发了下一个 HTTP 请求 —— 两种情况都应结束本流。
    """
    try:
        readable, _, exceptional = select.select([conn], [], [conn], 0)
        return bool(readable or exceptional)
    except (ValueError, OSError):
        return True


class _Handler(BaseHTTPRequestHandler):
    # HTTP/1.1 才能流式写 SSE(无 Content-Length)。但必须禁用 keep-alive:
    # Chrome 对同一 host 只有 6 条 HTTP/1.1 连接,页面 keep-alive 加上永不结束
    # 的 SSE 会把连接池占满,新预览 tab 一直「加载中」。见
    # docs/issue-sse-connection-hang.md。
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Silence default stderr spam; plugin has its own logger.
        pass

    def _common_headers(self, cache_control):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", cache_control)
        # 短请求立刻关 TCP,不进 Chrome keep-alive 池,把 6 条连接留给可见 tab 的 SSE。
        self.send_header("Connection", "close")

    def _cors(self):
        self._common_headers("no-store")

    def _static_headers(self):
        # 包内 mermaid/echarts/katex 不变,让浏览器跨 tab 复用,避免每页再拉 5MB。
        self._common_headers("public, max-age=31536000, immutable")

    def do_OPTIONS(self):
        touch_activity()
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        touch_activity()
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/preview.html", "/index.html"):
            file_key = _file_key_from_query(parsed.query)
            if not self._queue_doc_from_query(parsed.query):
                self._serve_query_error(parsed.query)
                return
            self._serve_shell(file_key)
            return
        if path == "/api/export/html":
            self._api_export_html(parsed.query)
            return
        if path == "/api/stream":
            self._api_stream(parsed.query)
            return
        if path == "/api/snapshot":
            self._api_snapshot(parsed.query)
            return
        if path == "/api/open_doc":
            self._api_open_doc(parsed.query)
            return
        if path.startswith("/doc/"):
            self._serve_doc(path[len("/doc/"):])
            return
        if path.startswith("/assets/"):
            self._serve_package_asset(path[len("/assets/"):])
            return
        # Fallback: files under output_dir
        self._serve_output(path.lstrip("/"))

    def do_POST(self):
        touch_activity()
        parsed = urlparse(self.path)
        if parsed.path == "/api/browser_scroll":
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                data = {}
            line = int(data.get("line") or 0)
            file_key = data.get("file") or ""
            with _STATE.lock:
                ch = _STATE.channel(file_key)
                if line > 0:
                    ch.browser_line = line
                    ch.browser_line_seq += 1
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        self.send_error(404)

    def _queue_doc_from_query(self, query):
        """支持 /?file:///abs/path.md 直接以标准预览流程打开任意 markdown。

        目标文件入队后正常返回 shell 页,SSE 会把渲染结果推进该页面。
        返回 False 表示 query 为空(正常预览)或目标不合法(调用方报错)。
        """
        q = unquote(query or "").strip()
        if not q:
            return True
        for prefix in ("file://", "file="):
            if q.startswith(prefix):
                q = q[len(prefix):]
                break
        if q.startswith("file://"):
            q = q[len("file://"):]
        if not os.path.isabs(q):
            return False
        if not q.lower().endswith(".md"):
            return False
        if not os.path.isfile(q):
            return False
        # 频道里已有该文档的 shell,说明插件刚 Toggle 过,GET /?file=
        # 只是浏览器在加载预览页,不要再通知插件「打开这个文件」.
        # 点其它 .md 链接时目标频道还是空的,仍会入队.
        with _STATE.lock:
            ch = _STATE.channels.get(q)
            if ch is not None and (ch.shell_html or ch.body_html):
                return True
        queue_open_doc(q)
        return True

    def _serve_query_error(self, query):
        """目标文件不合法时返回显式错误页,而不是静默显示上一个文档。"""
        q = unquote(query or "").strip()
        if q.startswith("file://"):
            q = q[len("file://"):]
        elif q.startswith("file="):
            q = q[len("file="):]
        if os.path.isdir(q):
            reason = "是一个目录,请指向具体的 .md 文件"
        elif not q.lower().endswith(".md"):
            reason = "不是 .md 文件"
        elif not os.path.exists(q):
            reason = "文件不存在"
        else:
            reason = "不是常规文件"
        html = (
            "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
            "<title>预览失败</title></head>"
            "<body style=\"font-family:sans-serif;color:#333;padding:40px\">"
            "<h2>无法预览</h2>"
            "<p><code>%s</code> %s。</p>"
            "<p>用法:<code>http://127.0.0.1:%d/?file:///abs/path/to/doc.md</code></p>"
            "</body></html>"
        ) % (_escape(q), reason, self.server.server_address[1])
        data = html.encode("utf-8")
        self.send_response(400)
        self._cors()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_shell(self, file_key):
        # 点 .md 链接时 GET 比插件渲染更早。先等最多 2s 要到正文,
        # 避免立刻返回 Rendering... 再卡在 mermaid/echarts 下载上.
        html = ""
        deadline = time.time() + 2.0
        while True:
            with _STATE.lock:
                ch = _STATE.channel(file_key)
                html = ch.shell_html or ch.full_html
            if html or time.time() >= deadline:
                break
            time.sleep(0.03)
        if not html:
            # 频道尚未渲染:占位页,客户端再靠 snapshot/SSE 补正文
            from .html_builder import build_preview_shell
            html = build_preview_shell(
                '<p style="color:#666;text-align:center;padding:40px">Rendering...</p>',
                use_server=True,
                title=os.path.basename(file_key or "preview"),
            )
        data = html.encode("utf-8")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api_open_doc(self, query):
        """预览 tab 列表点选:通知插件聚焦对应编辑器,不新开浏览器页。"""
        file_key = _file_key_from_query(query)
        if (
            not file_key
            or not os.path.isabs(file_key)
            or not file_key.lower().endswith(".md")
        ):
            self.send_error(400, "invalid file")
            return
        queue_open_doc(file_key)
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _api_snapshot(self, query):
        """Short JSON dump of one channel — follower tabs catch up without SSE."""
        file_key = _file_key_from_query(query)
        with _STATE.lock:
            ch = _STATE.channel(file_key)
            payload = {
                "file": file_key,
                "html": ch.body_html,
                "toc": ch.toc_html,
                "line": ch.editor_line,
            }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api_export_html(self, query):
        """Generate clean standalone HTML (no toolbar, no polling) and return it."""
        from .html_builder import build_export_html
        from .md_renderer import render as render_markdown, rewrite_image_srcs

        file_key = _file_key_from_query(query)
        with _STATE.lock:
            ch = _STATE.channel(file_key)
            raw = ch.raw_markdown
            base_dir = ch.export_base_dir or ch.doc_dir
            settings = dict(ch.export_settings)
        if not raw:
            self.send_error(400, "No markdown content available for export")
            return

        try:
            result = render_markdown(
                raw,
                mermaid_theme=settings.get("mermaid_theme", "default"),
                base_dir=base_dir,
                image_mode="file",
                enable_toc=settings.get("show_toc", False),
            )
            body = result["body_html"]
            toc = result["toc_html"] if settings.get("show_toc") else ""
            if base_dir:
                body = rewrite_image_srcs(body, base_dir, mode="file")
            html = build_export_html(
                body,
                toc_html=toc,
                show_toc=settings.get("show_toc", False) and bool(toc),
                enable_katex=settings.get("enable_katex", True),
                custom_css=settings.get("custom_css", ""),
                title=settings.get("title", "Markdown Export"),
                favicon=settings.get("favicon", ""),
            )
            data = html.encode("utf-8")
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header(
                "Content-Disposition",
                'attachment; filename="%s.html"'
                % (settings.get("title", "export") or "export"),
            )
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            traceback.print_exc()
            self.send_response(500)
            self._cors()
            self.send_header("Content-Type", "application/json")
            payload = json.dumps(
                {"error": str(e)},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def _api_stream(self, query):
        """SSE endpoint — server pushes content/editor-line to browser in-place.

        无 file= 时加入全局流(一条连接收全部文档,给 BroadcastChannel 选主用);
        有 file= 时只订该文档(无 BroadcastChannel 的回退路径)。
        """
        raw_query = query or ""
        global_scope = "file=" not in raw_query and "file://" not in raw_query
        file_key = _file_key_from_query(raw_query)
        q = queue.Queue(maxsize=64)
        snapshots = []
        with _STATE.lock:
            if global_scope:
                _STATE.global_sse_queues.append(q)
                for key, ch in _STATE.channels.items():
                    snapshots.append((key, ch.body_html, ch.toc_html, ch.editor_line))
                client_count = len(_STATE.global_sse_queues)
            else:
                ch = _STATE.channel(file_key)
                ch.sse_queues.append(q)
                snapshots.append(
                    (file_key, ch.body_html, ch.toc_html, ch.editor_line)
                )
                client_count = len(ch.sse_queues)

        _LOG("sse connect file=%s global=%s clients=%d queue=%d" % (
            "*" if global_scope else file_key, global_scope, client_count, q.qsize()))
        try:
            # SSE 持续写直到客户端断开;响应结束后必须关连接,不能 keep-alive 复用。
            self.close_connection = True
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for key, body, toc, line in snapshots:
                initial = json.dumps({
                    "html": body,
                    "toc": toc,
                    "file": key,
                }, ensure_ascii=False)
                initial_line = json.dumps(
                    {"line": line, "file": key}, ensure_ascii=False
                )
                self.wfile.write(
                    ("event: content\ndata: %s\n\n" % initial).encode("utf-8")
                )
                self.wfile.write(
                    ("event: editorLine\ndata: %s\n\n" % initial_line).encode("utf-8")
                )
            self.wfile.flush()
            touch_activity()

            while True:
                if _peer_gone(self.connection):
                    break
                try:
                    event_type, payload = q.get(timeout=1)
                except queue.Empty:
                    if _peer_gone(self.connection):
                        break
                    # 具名 ping 而不是 SSE 注释:选主 tab 要转发给其它 tab 续租
                    self.wfile.write(b"event: ping\ndata: {}\n\n")
                    self.wfile.flush()
                    touch_activity()
                    continue
                self.wfile.write(
                    ("event: %s\ndata: %s\n\n" % (event_type, payload)).encode("utf-8")
                )
                self.wfile.flush()
                touch_activity()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            _LOG("sse drop file=%s err=%s" % (
                "*" if global_scope else file_key, sys.exc_info()[1]))
        finally:
            self.close_connection = True
            with _STATE.lock:
                if global_scope:
                    if q in _STATE.global_sse_queues:
                        _STATE.global_sse_queues.remove(q)
                    remaining = len(_STATE.global_sse_queues)
                else:
                    if q in ch.sse_queues:
                        ch.sse_queues.remove(q)
                    remaining = len(ch.sse_queues)
            _LOG("sse disconnect file=%s clients=%d" % (
                "*" if global_scope else file_key, remaining))

    def _safe_join(self, root, rel):
        rel = unquote(rel).replace("\\", "/")
        # prevent path traversal
        parts = []
        for p in rel.split("/"):
            if p in ("", "."):
                continue
            if p == "..":
                return None
            parts.append(p)
        full = os.path.normpath(os.path.join(root, *parts))
        root_norm = os.path.normpath(root)
        if not full.startswith(root_norm + os.sep) and full != root_norm:
            return None
        return full

    def _serve_file(self, full, content_type=None):
        if not full or not os.path.isfile(full):
            self.send_error(404)
            return
        try:
            with open(full, "rb") as f:
                data = f.read()
        except Exception:
            self.send_error(404)
            return
        if not content_type:
            ext = os.path.splitext(full)[1].lower()
            content_type = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
                ".json": "application/json",
                ".md": "text/markdown; charset=utf-8",
            }.get(ext, "application/octet-stream")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_doc(self, rel):
        """/doc/ URL 不携带频道信息,遍历各频道 doc_dir 定位存在的文件。"""
        with _STATE.lock:
            doc_dirs = [ch.doc_dir for ch in _STATE.channels.values() if ch.doc_dir]
        for doc_dir in doc_dirs:
            full = self._safe_join(doc_dir, rel)
            if full and os.path.isfile(full):
                self._serve_file(full)
                return
        self.send_error(404)

    def _serve_package_asset(self, rel):
        """Serve files from package assets/ via sublime resources (zip-safe)."""
        rel = unquote(rel).replace("\\", "/")
        parts = []
        for p in rel.split("/"):
            if p in ("", "."):
                continue
            if p == "..":
                self.send_error(404)
                return
            parts.append(p)
        if not parts:
            self.send_error(404)
            return
        resource_rel = "assets/" + "/".join(parts)
        packed = _cached_package_asset(resource_rel)
        if packed is None:
            self.send_error(404)
            return
        data, etag = packed
        ext = os.path.splitext(parts[-1])[1].lower()
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".json": "application/json",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
            ".ttf": "font/ttf",
            ".otf": "font/otf",
        }.get(ext, "application/octet-stream")
        inm = (self.headers.get("If-None-Match") or "").replace("W/", "").replace('"', "")
        if etag and etag in inm:
            self.send_response(304)
            self._static_headers()
            self.send_header("ETag", '"%s"' % etag)
            self.end_headers()
            return
        self.send_response(200)
        self._static_headers()
        self.send_header("ETag", '"%s"' % etag)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_output(self, rel):
        with _STATE.lock:
            out = _STATE.output_dir
        if not out:
            self.send_error(404)
            return
        full = self._safe_join(out, rel)
        self._serve_file(full)


class PreviewServer:
    def __init__(self):
        self._httpd = None
        self._thread = None
        self.port = None
        self.host = "127.0.0.1"

    @property
    def running(self):
        return self._httpd is not None

    @property
    def base_url(self):
        if not self.port:
            return None
        return "http://%s:%d" % (self.host, self.port)

    def start(self, port=8765, log=None):
        global _LOG
        log = log or (lambda m: None)
        _LOG = log
        if self.running:
            touch_activity()
            return self.base_url

        # Try preferred port, then next few.
        last_err = None
        for p in range(int(port), int(port) + 20):
            try:
                httpd = ThreadingHTTPServer((self.host, p), _Handler)
                self._httpd = httpd
                self.port = p
                break
            except OSError as e:
                last_err = e
                continue
        if self._httpd is None:
            log("server start failed: %s" % last_err)
            return None

        def _run():
            try:
                self._httpd.serve_forever(poll_interval=0.3)
            except Exception:
                pass

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        touch_activity()
        log("preview server on %s" % self.base_url)
        return self.base_url

    def stop(self, log=None):
        log = log or (lambda m: None)
        if self._httpd is None:
            return
        try:
            self._httpd.shutdown()
        except Exception:
            pass
        try:
            self._httpd.server_close()
        except Exception:
            pass
        self._httpd = None
        self._thread = None
        self.port = None
        log("preview server stopped")


# Module-level singleton used by the plugin.
SERVER = PreviewServer()
