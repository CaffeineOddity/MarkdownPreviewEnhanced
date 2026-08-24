#!/usr/bin/env python3
"""Regression: preview HTTP responses must not enter the keep-alive reuse pool.

Chrome caps HTTP/1.1 at 6 connections per host. If the HTML page (or SSE)
advertises keep-alive, idle page sockets plus live EventSource sockets fill
that budget around tab 4–6 and a new tab spins forever. See
docs/issue-sse-connection-hang.md.
"""
from __future__ import print_function

import json
import os
import socket
import sys
import tempfile
import threading
import time
import types
import unittest
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# preview_server -> assets imports sublime at module load.
if "sublime" not in sys.modules:
    _sublime = types.ModuleType("sublime")
    _sublime.load_resource = lambda p: ""
    _sublime.load_binary_resource = lambda p: None
    sys.modules["sublime"] = _sublime

from mpe_core.preview_server import (  # noqa: E402
    PreviewServer,
    has_sse_clients,
    pop_open_docs,
    state,
    update_content,
)


def _recv_until_headers(sock, timeout):
    sock.settimeout(timeout)
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    header_blob, sep, rest = data.partition(b"\r\n\r\n")
    lines = header_blob.decode("iso-8859-1").split("\r\n")
    status = lines[0] if lines else ""
    headers = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return status, headers, rest


def _read_body(sock, headers, rest):
    length = headers.get("content-length")
    if length is None:
        return rest
    need = int(length)
    body = rest
    while len(body) < need:
        chunk = sock.recv(need - len(body))
        if not chunk:
            break
        body += chunk
    return body[:need]


def _http_get(sock, path, extra_headers=""):
    req = "GET %s HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: keep-alive\r\n%s\r\n" % (
        path,
        extra_headers,
    )
    sock.sendall(req.encode("ascii"))


class PreviewConnectionTests(unittest.TestCase):
    def setUp(self):
        self.srv = PreviewServer()
        url = self.srv.start(port=18765, log=lambda m: None)
        self.assertIsNotNone(url, "failed to bind preview server")
        self.port = self.srv.port
        with state().lock:
            for ch in state().channels.values():
                ch.sse_queues[:] = []
            if hasattr(state(), "global_sse_queues"):
                state().global_sse_queues[:] = []
            ch = state().channel("")
            ch.shell_html = "<html><body>preview-ok</body></html>"
            ch.body_html = "<p>body</p>"
            ch.toc_html = ""

    def tearDown(self):
        self.srv.stop()

    def _connect(self):
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=2)
        sock.settimeout(2)
        return sock

    def test_html_page_sends_connection_close(self):
        sock = self._connect()
        try:
            _http_get(sock, "/")
            status, headers, rest = _recv_until_headers(sock, timeout=2)
            _read_body(sock, headers, rest)
            self.assertTrue(status.startswith("HTTP/1.1 200"), status)
            self.assertEqual(headers.get("connection", "").lower(), "close")
        finally:
            sock.close()

    def test_html_page_does_not_keep_tcp_for_reuse(self):
        """Even if the client asked for keep-alive, the socket must close.

        An idle keep-alive HTML socket costs one of Chrome's 6 slots and is
        what made the visibility-based SSE close insufficient.
        """
        sock = self._connect()
        try:
            _http_get(sock, "/")
            status, headers, rest = _recv_until_headers(sock, timeout=2)
            _read_body(sock, headers, rest)
            self.assertTrue(status.startswith("HTTP/1.1 200"), status)
            # Server closed: a follow-up request on this TCP connection
            # must not be answered (recv → empty / connection error).
            try:
                _http_get(sock, "/")
                sock.settimeout(1)
                leftover = sock.recv(64)
            except (socket.timeout, ConnectionResetError, BrokenPipeError, OSError):
                leftover = b""
            self.assertEqual(leftover, b"", "server kept the HTML connection alive")
        finally:
            sock.close()

    def test_sse_sends_connection_close(self):
        sock = self._connect()
        try:
            _http_get(sock, "/api/stream", extra_headers="Accept: text/event-stream\r\n")
            status, headers, rest = _recv_until_headers(sock, timeout=2)
            self.assertTrue(status.startswith("HTTP/1.1 200"), status)
            self.assertIn("text/event-stream", headers.get("content-type", ""))
            self.assertEqual(headers.get("connection", "").lower(), "close")
            combined = rest
            deadline = time.time() + 2
            while b"event: content" not in combined and time.time() < deadline:
                combined += sock.recv(4096)
            self.assertIn(b"event: content", combined)
        finally:
            sock.close()

    def test_sse_disconnect_releases_channel(self):
        sock = self._connect()
        try:
            _http_get(sock, "/api/stream", extra_headers="Accept: text/event-stream\r\n")
            _recv_until_headers(sock, timeout=2)
            self.assertTrue(has_sse_clients())
        finally:
            sock.close()
        deadline = time.time() + 7
        while time.time() < deadline and has_sse_clients():
            time.sleep(0.2)
        self.assertFalse(has_sse_clients(), "SSE thread leaked after client disconnect")

    def test_short_post_not_blocked_by_open_sse(self):
        streams = []
        try:
            for _ in range(6):
                sock = self._connect()
                _http_get(sock, "/api/stream", extra_headers="Accept: text/event-stream\r\n")
                _recv_until_headers(sock, timeout=2)
                streams.append(sock)
            post = self._connect()
            try:
                body = b'{"line":1,"file":""}'
                req = (
                    "POST /api/browser_scroll HTTP/1.1\r\n"
                    "Host: 127.0.0.1\r\n"
                    "Content-Type: application/json\r\n"
                    "Content-Length: %d\r\n"
                    "Connection: keep-alive\r\n"
                    "\r\n"
                ) % len(body)
                t0 = time.time()
                post.sendall(req.encode("ascii") + body)
                status, headers, rest = _recv_until_headers(post, timeout=2)
                _read_body(post, headers, rest)
                elapsed = time.time() - t0
                self.assertTrue(status.startswith("HTTP/1.1 200"), status)
                self.assertEqual(headers.get("connection", "").lower(), "close")
                self.assertLess(elapsed, 1.0, "short POST stalled for %.3fs" % elapsed)
            finally:
                post.close()
        finally:
            for sock in streams:
                sock.close()

    def test_global_stream_tags_file_on_content(self):
        """Leader EventSource uses /api/stream with no ?file= and must see
        every document's updates, tagged so tabs can filter by path."""
        sock = self._connect()
        try:
            _http_get(sock, "/api/stream", extra_headers="Accept: text/event-stream\r\n")
            status, headers, rest = _recv_until_headers(sock, timeout=2)
            self.assertTrue(status.startswith("HTTP/1.1 200"), status)
            combined = rest
            deadline = time.time() + 2
            while b"event: content" not in combined and time.time() < deadline:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                combined += chunk
            self.assertIn(b"event: content", combined)
            update_content(
                "<p>doc-a</p>", "", "", "", None,
                file_path="/tmp/doc-a.md",
            )
            deadline = time.time() + 2
            while b"doc-a.md" not in combined and time.time() < deadline:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                combined += chunk
            self.assertIn(b"/tmp/doc-a.md", combined)
            self.assertIn(b"doc-a", combined)
        finally:
            sock.close()

    def test_global_stream_counts_as_sse_client(self):
        sock = self._connect()
        try:
            _http_get(sock, "/api/stream", extra_headers="Accept: text/event-stream\r\n")
            _recv_until_headers(sock, timeout=2)
            self.assertTrue(has_sse_clients())
        finally:
            sock.close()

    def test_snapshot_returns_current_html(self):
        """Follower tabs have no EventSource; they load a snapshot over HTTP.

        Clicking a .md link serves Rendering... before the plugin finishes, then
        the content event may already have been broadcast. Snapshot is how the
        new tab catches up.
        """
        update_content(
            "<p>snap-body</p>", "<nav>snap-toc</nav>", "", "", None,
            file_path="/tmp/snap.md",
        )
        sock = self._connect()
        try:
            _http_get(sock, "/api/snapshot?file=" + quote("/tmp/snap.md"))
            status, headers, rest = _recv_until_headers(sock, timeout=2)
            body = _read_body(sock, headers, rest)
            self.assertTrue(status.startswith("HTTP/1.1 200"), status)
            self.assertEqual(headers.get("connection", "").lower(), "close")
            data = json.loads(body.decode("utf-8"))
            self.assertEqual(data.get("file"), "/tmp/snap.md")
            self.assertEqual(data.get("html"), "<p>snap-body</p>")
            self.assertEqual(data.get("toc"), "<nav>snap-toc</nav>")
        finally:
            sock.close()

    def test_shell_waits_for_pending_render(self):
        """Clicking a .md link GETs the page before the plugin finishes.

        The handler must wait for shell_html instead of immediately returning
        the Rendering... placeholder (which then sits there until 5MB of
        mermaid/echarts finish loading and snapshot JS can run).
        """
        fd, path = tempfile.mkstemp(suffix=".md")
        os.write(fd, b"# wait")
        os.close(fd)
        try:
            def publish():
                time.sleep(0.2)
                with state().lock:
                    ch = state().channel(path)
                    ch.shell_html = "<html><body>rendered-ok</body></html>"
                    ch.body_html = "<p>rendered-ok</p>"

            threading.Thread(target=publish).start()
            sock = self._connect()
            try:
                t0 = time.time()
                _http_get(sock, "/?file=" + quote(path))
                status, headers, rest = _recv_until_headers(sock, timeout=3)
                body = _read_body(sock, headers, rest)
                elapsed = time.time() - t0
                self.assertTrue(status.startswith("HTTP/1.1 200"), status)
                self.assertIn(b"rendered-ok", body)
                self.assertNotIn(b"Rendering...", body)
                self.assertLess(elapsed, 2.0)
                self.assertGreaterEqual(elapsed, 0.15)
            finally:
                sock.close()
        finally:
            os.remove(path)

    def test_package_assets_are_browser_cacheable(self):
        from mpe_core import assets as pkg_assets
        orig = pkg_assets.read_bytes
        pkg_assets.read_bytes = lambda rel: b"/* mermaid */" if rel.endswith(".js") else orig(rel)
        sock = self._connect()
        try:
            _http_get(sock, "/assets/mermaid.min.js")
            status, headers, rest = _recv_until_headers(sock, timeout=2)
            _read_body(sock, headers, rest)
            self.assertTrue(status.startswith("HTTP/1.1 200"), status)
            cache = headers.get("cache-control", "").lower()
            self.assertIn("max-age", cache)
            self.assertNotEqual(cache, "no-store")
            etag = headers.get("etag", "").strip('"')
            self.assertTrue(etag)
        finally:
            sock.close()
            pkg_assets.read_bytes = orig

        sock2 = self._connect()
        try:
            extra = "If-None-Match: \"%s\"\r\n" % etag
            _http_get(sock2, "/assets/mermaid.min.js", extra_headers=extra)
            status2, headers2, rest2 = _recv_until_headers(sock2, timeout=2)
            self.assertTrue(status2.startswith("HTTP/1.1 304"), status2)
        finally:
            sock2.close()
            from mpe_core import preview_server as ps
            ps._ASSET_MEM.clear()

    def test_open_doc_queues_path(self):
        fd, path = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        try:
            sock = self._connect()
            try:
                _http_get(sock, "/api/open_doc?file=" + quote(path, safe=""))
                status, headers, rest = _recv_until_headers(sock, timeout=2)
                self.assertTrue(status.startswith("HTTP/1.1 204"), status)
                self.assertEqual(headers.get("connection", "").lower(), "close")
            finally:
                sock.close()
            self.assertEqual(pop_open_docs(), [path])
        finally:
            os.remove(path)


class PreviewTabHintTests(unittest.TestCase):
    def test_hints_cover_encoded_and_decoded_file_query(self):
        from mpe_core.browser import _as_url_matches, _preview_match_hints

        encoded = "http://127.0.0.1:8765/?file=%2Ftmp%2Falpha.md"
        decoded = "http://127.0.0.1:8765/?file=/tmp/alpha.md"
        for url in (encoded, decoded):
            hints = _preview_match_hints(url)
            self.assertTrue(
                any(h.endswith("/?file=%2Ftmp%2Falpha.md") for h in hints), hints)
            self.assertTrue(
                any(h.endswith("/?file=/tmp/alpha.md") for h in hints), hints)
            expr = _as_url_matches(hints)
            self.assertIn(" or ", expr)
            self.assertIn("%2Ftmp%2Falpha.md", expr)
            self.assertIn("/tmp/alpha.md", expr)

    def test_focus_only_script_does_not_open_tab(self):
        from mpe_core.browser import BrowserSession, _preview_match_hints

        url = "http://127.0.0.1:8765/?file=%2Ftmp%2Falpha.md"
        hints = _preview_match_hints(url)
        session = BrowserSession()
        script = session._chrome_focus_or_open_script(
            "Google Chrome", url, hints, False)
        self.assertNotIn("make new tab", script)
        self.assertIn("if found then activate", script)
        script_open = session._chrome_focus_or_open_script(
            "Google Chrome", url, hints, True)
        self.assertIn("make new tab", script_open)


if __name__ == "__main__":
    unittest.main()
