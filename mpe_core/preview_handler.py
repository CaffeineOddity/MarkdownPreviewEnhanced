"""HTTP request handler for the preview server.

All routing (GET/POST), SSE streaming, asset serving, and API endpoints
live here.  State is accessed through ``preview_state_core``.
"""
import hashlib
import hmac
import json
import os
import queue
import select
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote, urlparse, parse_qs

from . import assets as pkg_assets
from . import preview_state_core as _core

# 预览页会加载的资源。其它扩展（.env、密钥、源码）一律不从 /doc/ 送出。
_DOC_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp", ".avif",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp4", ".webm", ".ogg", ".mp3", ".wav", ".m4a", ".mov",
    ".css", ".pdf",
    ".md", ".markdown",
})

_LOCAL_HOSTS = frozenset(("127.0.0.1", "localhost"))


def host_allowed(host_header):
    """True when Host is this loopback server, not a DNS-rebound name."""
    if not host_header:
        return False
    host = host_header.strip().lower()
    if not host or host.startswith("["):
        return False
    hostname = host.split(":", 1)[0]
    return hostname in _LOCAL_HOSTS


def fetch_site_allowed(site):
    """Browser Sec-Fetch-Site. Cross-site and same-site (other port) are refused.

    Missing header is allowed so non-browser clients that already hold the
    token (tests, the first OS-opened navigation on older browsers) still work.
    A web page cannot omit this header.
    """
    value = (site or "").strip().lower()
    return value in ("", "none", "same-origin")


def origin_allowed(origin, port):
    """True when Origin is absent or is this server's own origin."""
    if not origin:
        return True
    port = str(port)
    return origin in (
        "http://127.0.0.1:%s" % port,
        "http://localhost:%s" % port,
    )


def token_matches(expected, presented):
    """Constant-time compare. Empty or mismatched tokens fail closed."""
    if not expected or not presented or not isinstance(presented, str):
        return False
    try:
        left = expected.encode("utf-8")
        right = presented.encode("utf-8")
    except Exception:
        return False
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def cookie_value(header, name):
    """Return one cookie value, or ''."""
    if not header or not name:
        return ""
    prefix = name + "="
    for part in header.split(";"):
        part = part.strip()
        if part.startswith(prefix):
            return part[len(prefix):]
    return ""


def presented_tokens(header_token, query, cookie_header):
    """Token candidates from ``X-MPE-Token``, ``?token=``, and the cookie."""
    found = []
    if header_token:
        found.append(header_token.strip())
    for item in (parse_qs(query or "").get("token") or []):
        if item:
            found.append(item)
    baked = cookie_value(cookie_header or "", "mpe_token")
    if baked:
        found.append(baked)
    return found


def any_token_matches(expected, candidates):
    for candidate in candidates:
        if token_matches(expected, candidate):
            return True
    return False


def doc_rel_allowed(rel):
    """True when *rel* is a preview asset, not a hidden or secret file."""
    text = unquote(rel or "").replace("\\", "/").split("?", 1)[0]
    base = text.rsplit("/", 1)[-1]
    if not base or base.startswith("."):
        return False
    ext = os.path.splitext(base)[1].lower()
    return ext in _DOC_EXTENSIONS


def redact_query(query):
    """Drop the token before a request line is written to the log."""
    if not query:
        return ""
    kept = [
        piece for piece in query.split("&")
        if piece and not piece.startswith("token=")
    ]
    redacted = "&".join(kept)
    if "token=" in (query or ""):
        redacted = (redacted + "&" if redacted else "") + "token=***"
    return redacted


# ── asset cache ─────────────────────────────────────────────────────────────

_ASSET_MEM = {}
_ASSET_MEM_LOCK = __import__("threading").Lock()


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


# ── connection liveness check ───────────────────────────────────────────────

def _peer_gone(conn):
    """True if the client closed, reset, or wrote unexpected extra bytes."""
    try:
        readable, _, exceptional = select.select([conn], [], [conn], 0)
        return bool(readable or exceptional)
    except (ValueError, OSError):
        return True


# ── HTTP handler ────────────────────────────────────────────────────────────

class PreviewHandler(BaseHTTPRequestHandler):
    """HTTP/1.1 handler; SSE-friendly (no keep-alive reuse)."""

    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # silence stderr spam; plugin has its own logger

    # ── shared headers ──────────────────────────────────────────────────────

    def _auth_token(self):
        return getattr(self.server, "auth_token", "") or ""

    def _request_allowed(self, parsed):
        """Sensitive routes require the session token and a same-origin browser.

        ``Access-Control-Allow-Origin: *`` used to let any page read the
        response. State-changing GETs still run without CORS, so the token
        and ``Sec-Fetch-Site`` / ``Origin`` checks are what actually stop
        another tab from driving the server.
        """
        if not fetch_site_allowed(self.headers.get("Sec-Fetch-Site")):
            return False
        port = self.server.server_address[1]
        if not origin_allowed(self.headers.get("Origin"), port):
            return False
        candidates = presented_tokens(
            self.headers.get("X-MPE-Token"),
            parsed.query,
            self.headers.get("Cookie"),
        )
        return any_token_matches(self._auth_token(), candidates)

    def _common_headers(self, cache_control, set_cookie=False):
        self.send_header("Cache-Control", cache_control)
        self.send_header("Connection", "close")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        if set_cookie:
            token = self._auth_token()
            if token:
                # Session cookie. SameSite=Strict keeps it off cross-site
                # requests; HttpOnly keeps page scripts from reading it.
                self.send_header(
                    "Set-Cookie",
                    "mpe_token=%s; HttpOnly; SameSite=Strict; Path=/" % token,
                )

    def _cors(self):
        self._common_headers("no-store", set_cookie=True)

    def _static_headers(self):
        self._common_headers("public, max-age=31536000, immutable")

    def _forbid(self):
        body = b'{"error":"forbidden"}'
        self.send_response(403)
        self._common_headers("no-store")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _inject_client_token(self, html):
        """Give the preview page the token, then drop it from the address bar.

        Subresources and later navigations authenticate with the cookie set
        on this response. API calls also send ``X-MPE-Token`` so they still
        work if the cookie is missing.
        """
        token = self._auth_token()
        if not token or not html:
            return html
        snippet = (
            "<script>window.MDPP_TOKEN=%s;"
            "(function(){try{var u=new URL(location.href);"
            "if(!u.searchParams.has('token'))return;"
            "u.searchParams.delete('token');"
            "history.replaceState(null,'',u.pathname+u.search+u.hash);"
            "}catch(e){}})();</script>\n"
        ) % json.dumps(token)
        pos = html.lower().find("<head>")
        if pos >= 0:
            insert_at = pos + len("<head>")
            return html[:insert_at] + "\n" + snippet + html[insert_at:]
        return snippet + html

    # ── routing ────────────────────────────────────────────────────────────

    def do_OPTIONS(self):
        parsed = urlparse(self.path)
        if not host_allowed(self.headers.get("Host")) or not self._request_allowed(parsed):
            self._forbid()
            return
        _core.touch_activity()
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if not host_allowed(self.headers.get("Host")):
            self._forbid()
            return
        # Package JS/CSS/fonts are not user data. The preview page loads them
        # by URL and they must stay cacheable, so they are not behind the token.
        if path.startswith("/assets/"):
            _core.touch_activity()
            _core.get_log()("WEB->ST GET %s" % path)
            self._serve_package_asset(path[len("/assets/"):])
            return
        if not self._request_allowed(parsed):
            _core.get_log()("WEB->ST rejected GET %s" % path)
            self._forbid()
            return
        _core.touch_activity()
        _core.get_log()("WEB->ST GET %s?%s" % (path, redact_query(parsed.query)))

        if path in ("/", "/preview.html", "/index.html"):
            file_key = _core._file_key_from_query(parsed.query)
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
        if path == "/api/tab_open":
            self._api_tab_open(parsed.query)
            return
        if path == "/api/tab_close":
            self._api_tab_close(parsed.query)
            return
        if path == "/presentation":
            self._serve_presentation(parsed.query)
            return
        if path.startswith("/doc/"):
            self._serve_doc(path[len("/doc/"):])
            return
        if path.startswith("/assets/"):
            self._serve_package_asset(path[len("/assets/"):])
            return
        self._serve_output(path.lstrip("/"))

    def do_POST(self):
        parsed = urlparse(self.path)
        if (
            not host_allowed(self.headers.get("Host"))
            or not self._request_allowed(parsed)
        ):
            _core.get_log()("WEB->ST rejected POST %s" % parsed.path)
            try:
                length = int(self.headers.get("Content-Length", 0) or 0)
            except (TypeError, ValueError):
                length = 0
            if length > 0:
                self.rfile.read(length)
            self._forbid()
            return
        _core.touch_activity()
        _core.get_log()("WEB->ST POST %s" % parsed.path)
        if parsed.path == "/api/tab_close":
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length:
                self.rfile.read(length)
            self._api_tab_close(parsed.query)
            return
        if parsed.path == "/api/browser_scroll":
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                data = {}
            line = int(data.get("line") or 0)
            file_key = data.get("file") or ""
            from_tag = data.get("from") or ""
            # 只接受浏览器主动滚动上报（from:"BS"），拦截 ST→browser 回环
            if from_tag != "BS":
                _core.get_log()("WEB->ST browser_scroll REJECTED from=%s line=%d file=%s"
                                % (from_tag, line, file_key))
            else:
                _core.get_log()("WEB->ST browser_scroll line=%d file=%s" % (line, file_key))
                with _core._STATE.lock:
                    ch = _core._STATE.channel(file_key)
                    if line > 0:
                        ch.browser_line = line
                        ch.browser_line_seq += 1
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        if parsed.path == "/api/task_toggle":
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                data = {}
            line = int(data.get("line") or 0)
            checked = bool(data.get("checked"))
            file_key = data.get("file") or ""
            ok = False
            if file_key and line > 0:
                _core.queue_task_toggle(file_key, line, checked)
                ok = True
            _core.get_log()("WEB->ST task_toggle line=%d checked=%s file=%s ok=%s"
                            % (line, checked, file_key, ok))
            resp = json.dumps({"ok": ok}, ensure_ascii=False).encode("utf-8")
            self.send_response(200 if ok else 400)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return
        self.send_error(404)

    # ── doc queue from query ───────────────────────────────────────────────

    def _queue_doc_from_query(self, query):
        raw = query or ""
        params = parse_qs(raw)
        # ?file=<path>&token=<secret>：token 不能被拼进路径。
        # 老地址 ?file:///abs/a.md 没有 '='，parse_qs 解析不到 file。
        if "file" in params or "token" in params:
            q = (params.get("file") or [""])[0]
            if not q:
                return True
        else:
            q = unquote(raw).strip()
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
        from . import tab_manager
        with _core._STATE.lock:
            ch = _core._STATE.channels.get(q)
            has_html = ch is not None and (ch.shell_html or ch.body_html)
        # Toggle 已经 register+render 再 OS-open:有行且有 html,不再 queue。
        # 点链接打开尚未登记的文件:即使频道里有残留 html 也要切 ST。
        if has_html and tab_manager.has_session(q):
            return True
        _core.queue_open_doc(q, focus_browser=False)
        return True

    def _serve_query_error(self, query):
        params = parse_qs(query or "")
        if params.get("file"):
            q = params["file"][0]
        else:
            q = unquote(query or "").strip()
            if q.startswith("file://"):
                q = q[len("file://"):]
            elif q.startswith("file="):
                q = q[len("file="):]
            token_at = q.find("&token=")
            if token_at >= 0:
                q = q[:token_at]
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
        ) % (_core._escape(q), reason, self.server.server_address[1])
        data = html.encode("utf-8")
        self.send_response(400)
        self._cors()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ── shell serving ───────────────────────────────────────────────────────

    def _serve_shell(self, file_key):
        html = ""
        deadline = time.time() + 2.0
        while True:
            with _core._STATE.lock:
                ch = _core._STATE.channel(file_key)
                html = ch.shell_html or ch.full_html
            if html or time.time() >= deadline:
                break
            time.sleep(0.03)
        if not html:
            from .html_builder import build_preview_shell
            html = build_preview_shell(
                '<p style="color:#666;text-align:center;padding:40px">Rendering...</p>',
                use_server=True,
                title=os.path.basename(file_key or "preview"),
            )
        data = self._inject_client_token(html).encode("utf-8")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_presentation(self, query):
        """Serve a slide deck from the channel body_html. Wait up to 2s."""
        from .presentation_builder import build_presentation

        file_key = _core._file_key_from_query(query)
        body_html = ""
        deadline = time.time() + 2.0
        while True:
            with _core._STATE.lock:
                ch = _core._STATE.channel(file_key)
                body_html = ch.body_html
            if body_html or time.time() >= deadline:
                break
            time.sleep(0.03)
        if not body_html:
            body_html = (
                '<p style="color:#666;text-align:center">Rendering…</p>'
            )
        title = os.path.basename(file_key) if file_key else "Presentation"
        html = build_presentation(body_html, title=title)
        data = self._inject_client_token(html).encode("utf-8")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ── API endpoints ───────────────────────────────────────────────────────

    def _api_open_doc(self, query):
        file_key = _core._file_key_from_query(query)
        if (
            not file_key
            or not os.path.isabs(file_key)
            or not file_key.lower().endswith(".md")
        ):
            self.send_error(400, "invalid file")
            return
        params = parse_qs(query)
        tab_switch = params.get("tab_switch", ["0"])[0] == "1"
        if tab_switch and not _core.tab_switch_allowed(file_key):
            _core.get_log()("open_doc ignored (os-open pin) file=%s" % file_key)
            self.send_response(204)
            self._cors()
            self.end_headers()
            return
        _core.queue_open_doc(file_key, focus_browser=False)
        _core.get_log()("open_doc file=%s tab_switch=%s" % (file_key, tab_switch))
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _api_tab_open(self, query):
        file_key = _core._file_key_from_query(query)
        if not file_key or not os.path.isabs(file_key):
            self.send_error(400, "invalid file")
            return
        result = _core.handle_tab_open(file_key)
        data = json.dumps(result or {}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api_tab_close(self, query):
        file_key = _core._file_key_from_query(query)
        params = parse_qs(query or "")
        gen_raw = (params.get("gen") or ["0"])[0]
        try:
            gen = int(gen_raw)
        except (TypeError, ValueError):
            gen = 0
        if file_key:
            hist_raw = (params.get("hist") or [""])[0]
            _core.handle_tab_close(file_key, gen)
            _core.get_log()("tab_close file=%s gen=%s hist=%s"
                            % (file_key, gen, hist_raw))
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _api_snapshot(self, query):
        file_key = _core._file_key_from_query(query)
        payload = _core.snapshot_payload(file_key)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api_export_html(self, query):
        from .html_builder import build_export_html
        from .md_renderer import render as render_markdown, rewrite_image_srcs

        file_key = _core._file_key_from_query(query)
        with _core._STATE.lock:
            ch = _core._STATE.channel(file_key)
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
                {"error": str(e)}, ensure_ascii=False
            ).encode("utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    # ── SSE streaming ───────────────────────────────────────────────────────

    def _api_stream(self, query):
        raw_query = query or ""
        global_scope = "file=" not in raw_query and "file://" not in raw_query
        file_key = _core._file_key_from_query(raw_query)
        q = queue.Queue(maxsize=64)
        snapshots = []
        with _core._STATE.lock:
            if global_scope:
                _core._STATE.global_sse_queues.append(q)
                for key, ch in _core._STATE.channels.items():
                    snapshots.append((key, ch.body_html, ch.toc_html, ch.editor_line))
                client_count = len(_core._STATE.global_sse_queues)
            else:
                ch = _core._STATE.channel(file_key)
                ch.sse_queues.append(q)
                snapshots.append(
                    (file_key, ch.body_html, ch.toc_html, ch.editor_line)
                )
                client_count = len(ch.sse_queues)

        _core.get_log()("sse connect file=%s global=%s clients=%d queue=%d" % (
            "*" if global_scope else file_key, global_scope, client_count, q.qsize()))
        try:
            self.close_connection = True
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for key, body, toc, line in snapshots:
                initial = json.dumps({
                    "html": body, "toc": toc, "file": key,
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
            from . import tab_manager
            tabs_payload = json.dumps(
                {"files": tab_manager.live_files(), "file": ""},
                ensure_ascii=False,
            )
            self.wfile.write(
                ("event: tabs\ndata: %s\n\n" % tabs_payload).encode("utf-8")
            )
            self.wfile.flush()
            _core.touch_activity()

            while True:
                if _peer_gone(self.connection):
                    break
                try:
                    event_type, payload = q.get(timeout=1)
                except queue.Empty:
                    if _peer_gone(self.connection):
                        break
                    self.wfile.write(b"event: ping\ndata: {}\n\n")
                    self.wfile.flush()
                    _core.touch_activity()
                    continue
                self.wfile.write(
                    ("event: %s\ndata: %s\n\n" % (event_type, payload)).encode("utf-8")
                )
                self.wfile.flush()
                _core.touch_activity()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            _core.get_log()("sse drop file=%s err=%s" % (
                "*" if global_scope else file_key, sys.exc_info()[1]))
        finally:
            self.close_connection = True
            with _core._STATE.lock:
                if global_scope:
                    if q in _core._STATE.global_sse_queues:
                        _core._STATE.global_sse_queues.remove(q)
                    remaining = len(_core._STATE.global_sse_queues)
                else:
                    if q in ch.sse_queues:
                        ch.sse_queues.remove(q)
                    remaining = len(ch.sse_queues)
            _core.get_log()("sse disconnect file=%s clients=%d" % (
                "*" if global_scope else file_key, remaining))

    # ── static file serving ─────────────────────────────────────────────────

    def _safe_join(self, root, rel):
        rel = unquote(rel).replace("\\", "/")
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
        ext = os.path.splitext(full)[1].lower()
        if not content_type:
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
                ".markdown": "text/markdown; charset=utf-8",
                ".ico": "image/x-icon",
                ".bmp": "image/bmp",
                ".avif": "image/avif",
                ".pdf": "application/pdf",
                ".woff": "font/woff",
                ".woff2": "font/woff2",
                ".ttf": "font/ttf",
                ".otf": "font/otf",
                ".eot": "application/vnd.ms-fontobject",
                ".mp4": "video/mp4",
                ".webm": "video/webm",
                ".mp3": "audio/mpeg",
                ".wav": "audio/wav",
                ".m4a": "audio/mp4",
                ".mov": "video/quicktime",
            }.get(ext, "application/octet-stream")
        self.send_response(200)
        self._cors()
        # SVG/HTML opened as a document must not run script in this origin.
        if ext in (".svg", ".html", ".htm", ".xhtml", ".xml"):
            self.send_header(
                "Content-Security-Policy", "default-src 'none'; sandbox",
            )
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_doc(self, rel):
        if not doc_rel_allowed(rel):
            self.send_error(404)
            return
        with _core._STATE.lock:
            doc_dirs = [ch.doc_dir for ch in _core._STATE.channels.values() if ch.doc_dir]
        for doc_dir in doc_dirs:
            full = self._safe_join(doc_dir, rel)
            if full and os.path.isfile(full):
                self._serve_file(full)
                return
        self.send_error(404)

    def _serve_package_asset(self, rel):
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
        with _core._STATE.lock:
            out = _core._STATE.output_dir
        if not out:
            self.send_error(404)
            return
        full = self._safe_join(out, rel)
        self._serve_file(full)
