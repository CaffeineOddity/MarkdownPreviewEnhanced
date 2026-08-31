"""Open the current markdown as a slide deck at ``/presentation?file=``."""
import threading
import traceback

import sublime
import sublime_plugin

from ..mpe_core import config
from ..mpe_core import log
from ..mpe_core.preview_server import SERVER
from ..mpe_core.preview_state import ensure_server
from ..mpe_core.preview_url import open_preview_browser
from ..mpe_core.render import render_view


class MarkdownPreviewEnhancedPresentationCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if view is None:
            self.window.status_message("MarkdownPreviewEnhanced: no active view")
            return
        if not config.get("use_local_server", True):
            sublime.error_message(
                "Presentation mode requires the local server.\n"
                "Enable \"use_local_server\" in settings.")
            return
        ensure_server()
        if not SERVER.running:
            self.window.status_message(
                "MarkdownPreviewEnhanced: server not running")
            return
        fp = view.file_name() or ""

        def _work():
            try:
                render_view(view, force=True, open_browser=False)
            except Exception:
                log.error("presentation render failed:\n%s" % traceback.format_exc())

            def _open():
                from urllib.parse import quote as _quote
                url = SERVER.base_url + "/presentation"
                if fp:
                    url += "?file=" + _quote(fp, safe="")
                open_preview_browser(url, False)
                log.info("presentation: %s" % url)
                self.window.status_message(
                    "MarkdownPreviewEnhanced: presentation opened")

            sublime.set_timeout(_open, 0)

        threading.Thread(target=_work, daemon=True).start()
