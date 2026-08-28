"""Local HTTP preview server - singleton lifecycle wrapper.

The actual HTTP request handling lives in ``preview_handler`` and the
shared document state lives in ``preview_state_core``.  This module
owns the ``PreviewServer`` class (start/stop) and the module-level
``SERVER`` singleton that the plugin imports.

Re-exports the public API from ``preview_state_core`` for backward
compatibility so existing imports ``from .preview_server import
update_content`` still work.
"""
import sys
import threading
from http.server import HTTPServer
from socketserver import ThreadingMixIn

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
    has_active_sse_connection,
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


class PreviewServer:
    """Lifecycle wrapper around the threaded HTTP server."""

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
        set_log(log)
        if self.running:
            touch_activity()
            return self.base_url

        last_err = None
        for p in range(int(port), int(port) + 20):
            try:
                httpd = ThreadingHTTPServer((self.host, p), PreviewHandler)
                self._httpd = httpd
                self.port = p
                break
            except OSError as e:
                last_err = e
                continue
        if self._httpd is None:
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
        log("preview server stopped")


def _noop_log(msg):
    pass


# Module-level singleton used by the plugin.
SERVER = PreviewServer()
