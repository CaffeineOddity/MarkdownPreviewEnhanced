"""Local HTTP preview server - singleton lifecycle wrapper.

The actual HTTP request handling lives in ``preview_handler`` and the
shared document state lives in ``preview_state_core``.  This module
owns the ``PreviewServer`` class (start/stop) and the module-level
``SERVER`` singleton that the plugin imports.

Re-exports the public API from ``preview_state_core`` for backward
compatibility so existing imports ``from .preview_server import
update_content`` still work.
"""
import binascii
import os
import re
import sys
import threading
from http.server import HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlsplit, urlunsplit

from .preview_state_core import (
    # state
    state,
    set_log,
    get_log,
    _file_key_from_query,
    touch_activity,
    seconds_since_activity,
    update_content,
    set_editor_line,
    set_active_doc,
    pop_browser_lines,
    close_browser_tabs,
    set_output_dir,
    queue_open_doc,
    pop_open_docs,
    queue_task_toggle,
    pop_task_toggles,
    has_active_sse_connection,
    pin_os_open_file,
    reset_os_open_pin,
    tab_switch_allowed,
)
from .preview_handler import PreviewHandler


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Threaded HTTP server - Python 3.3+ compatible (ST3/ST4 safe)."""
    daemon_threads = True

    def handle_error(self, request, client_address):
        # 浏览器关闭标签/刷新页面时 SSE 连接被重置,属于正常噪音
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError,
                            BrokenPipeError)):
            return
        HTTPServer.handle_error(self, request, client_address)


_TOKEN_IN_TEXT = re.compile(r"token=[^&\s\"']+")


def append_auth_token(url, token):
    """Append the session token as a ``token`` query param."""
    if not url or not token or "token=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return "%s%stoken=%s" % (url, sep, token)


def strip_auth_token(url):
    """Return *url* without the session token query param."""
    if not url or "token=" not in url:
        return url
    parts = urlsplit(url)
    kept = [
        piece for piece in parts.query.split("&")
        if piece and not piece.startswith("token=")
    ]
    return urlunsplit((
        parts.scheme, parts.netloc, parts.path, "&".join(kept), parts.fragment,
    ))


def redact_auth_text(text):
    """Hide the session token if a URL or log line contains one."""
    if not text or "token=" not in text:
        return text
    return _TOKEN_IN_TEXT.sub("token=***", text)


class PreviewServer:
    """Lifecycle wrapper around the threaded HTTP server.

    ``token`` is a per-process secret. Preview URLs carry it once so the
    browser can set a cookie; every sensitive request must present it.
    """

    def __init__(self):
        self._httpd = None
        self._thread = None
        self.port = None
        self.host = "127.0.0.1"
        self.token = None

    @property
    def running(self):
        return self._httpd is not None

    @property
    def base_url(self):
        if not self.port:
            return None
        return "http://%s:%d" % (self.host, self.port)

    def start(self, port=8765, log=None):
        set_log(log)
        if self.running:
            touch_activity()
            return self.base_url

        self.token = binascii.hexlify(os.urandom(24)).decode("ascii")
        last_err = None
        for p in range(int(port), int(port) + 20):
            try:
                httpd = ThreadingHTTPServer((self.host, p), PreviewHandler)
                httpd.auth_token = self.token
                self._httpd = httpd
                self.port = p
                break
            except OSError as e:
                last_err = e
                continue
        if self._httpd is None:
            self.token = None
            (log or _noop_log)("server start failed: %s" % last_err)
            return None

        def _run():
            try:
                self._httpd.serve_forever(poll_interval=0.3)
            except Exception:
                pass

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        touch_activity()
        (log or _noop_log)("preview server on %s" % self.base_url)
        return self.base_url

    def stop(self, log=None):
        log = log or _noop_log
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
        self.token = None
        log("preview server stopped")


def _noop_log(msg):
    pass


# Module-level singleton used by the plugin.
SERVER = PreviewServer()
