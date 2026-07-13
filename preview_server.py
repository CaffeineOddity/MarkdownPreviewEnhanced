"""Local HTTP server for live preview, media, SSE push, and scroll-sync."""
import json
import os
import queue
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import unquote, urlparse


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Threaded HTTP server — Python 3.3+ compatible (ST3/ST4 safe)."""
    daemon_threads = True


class PreviewState:
    """Shared mutable state between the plugin and the HTTP server."""

    def __init__(self):
        self.lock = threading.Lock()
        self.body_html = ""
        self.toc_html = ""
        self.full_html = ""
        self.doc_dir = None  # directory of the current markdown file
        self.editor_line = 0  # cursor line in editor (1-based) → browser
        self.browser_line = 0  # visible line reported by browser → editor
        self.browser_line_seq = 0
        self.output_dir = None
        self.shell_html = ""  # complete HTML page; served at /
        self.last_activity = 0.0  # unix time of last HTTP request
        # For server-side export (PDF/PNG/HTML)
        self.raw_markdown = ""
        self.export_base_dir = None
        self.export_settings = {}  # render settings dict
        # SSE push — one persistent connection, server pushes on content change
        self.sse_queues = []  # list of queue.Queue

    def _notify_sse(self, event_type, payload_json):
        """Push an SSE event to all connected listeners. Caller must hold lock."""
        dead = []
        for q in self.sse_queues:
            try:
                q.put_nowait((event_type, payload_json))
            except queue.Full:
                dead.append(q)
        for q in dead:
            self.sse_queues.remove(q)


_STATE = PreviewState()


def state():
    return _STATE


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
                   raw_markdown=None, export_base_dir=None, export_settings=None):
    with _STATE.lock:
        _STATE.body_html = body_html or ""
        _STATE.toc_html = toc_html or ""
        _STATE.full_html = full_html or ""
        if doc_dir:
            _STATE.doc_dir = doc_dir
        if shell_html is not None:
            _STATE.shell_html = shell_html
        if raw_markdown is not None:
            _STATE.raw_markdown = raw_markdown
        if export_base_dir is not None:
            _STATE.export_base_dir = export_base_dir
        if export_settings is not None:
            _STATE.export_settings = export_settings
        # Push to SSE listeners — browser updates DOM in-place, no reload
        payload = json.dumps({
            "html": _STATE.body_html,
            "toc": _STATE.toc_html,
        }, ensure_ascii=False)
        _STATE._notify_sse("content", payload)


def set_editor_line(line):
    with _STATE.lock:
        _STATE.editor_line = int(line or 0)
        payload = json.dumps({"line": _STATE.editor_line}, ensure_ascii=False)
        _STATE._notify_sse("editorLine", payload)


def pop_browser_line():
    """Return (line, seq) if browser reported a new scroll target for the editor."""
    with _STATE.lock:
        line = _STATE.browser_line
        seq = _STATE.browser_line_seq
        return line, seq


def close_browser_tabs():
    """Push a 'close' event to all connected SSE listeners — each tab closes itself."""
    with _STATE.lock:
        _STATE._notify_sse("close", "{}")


def set_output_dir(path):
    with _STATE.lock:
        _STATE.output_dir = path


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Silence default stderr spam; plugin has its own logger.
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")

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
            self._serve_shell()
            return
        if path == "/api/export/html":
            self._api_export_html()
            return
        if path == "/api/stream":
            self._api_stream()
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
            with _STATE.lock:
                if line > 0:
                    _STATE.browser_line = line
                    _STATE.browser_line_seq += 1
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        self.send_error(404)

    def _serve_shell(self):
        with _STATE.lock:
            html = _STATE.shell_html or _STATE.full_html or "<html><body>Loading…</body></html>"
        data = html.encode("utf-8")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api_export_html(self):
        """Generate clean standalone HTML (no toolbar, no polling) and return it."""
        from .html_builder import build_export_html
        from .md_renderer import render as render_markdown, rewrite_image_srcs

        with _STATE.lock:
            raw = _STATE.raw_markdown
            base_dir = _STATE.export_base_dir or _STATE.doc_dir
            settings = dict(_STATE.export_settings)
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

    def _api_stream(self):
        """SSE endpoint — server pushes content/editor-line to browser in-place."""
        q = queue.Queue(maxsize=64)
        with _STATE.lock:
            _STATE.sse_queues.append(q)
            # Send current snapshot on connect
            initial = json.dumps({
                "html": _STATE.body_html,
                "toc": _STATE.toc_html,
            }, ensure_ascii=False)
            initial_line = json.dumps({"line": _STATE.editor_line}, ensure_ascii=False)

        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(("event: content\ndata: %s\n\n" % initial).encode("utf-8"))
            self.wfile.write(("event: editorLine\ndata: %s\n\n" % initial_line).encode("utf-8"))
            self.wfile.flush()
            touch_activity()

            while True:
                try:
                    event_type, payload = q.get(timeout=15)
                    self.wfile.write(
                        ("event: %s\ndata: %s\n\n" % (event_type, payload)).encode("utf-8")
                    )
                    self.wfile.flush()
                    touch_activity()
                except queue.Empty:
                    self.wfile.write(": hb\n\n".encode("utf-8"))
                    self.wfile.flush()
                    touch_activity()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            with _STATE.lock:
                if q in _STATE.sse_queues:
                    _STATE.sse_queues.remove(q)

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
            }.get(ext, "application/octet-stream")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_doc(self, rel):
        with _STATE.lock:
            doc_dir = _STATE.doc_dir
        if not doc_dir:
            self.send_error(404)
            return
        full = self._safe_join(doc_dir, rel)
        self._serve_file(full)

    def _serve_package_asset(self, rel):
        assets = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        full = self._safe_join(assets, rel)
        self._serve_file(full)

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
        log = log or (lambda m: None)
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
