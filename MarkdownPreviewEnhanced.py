"""MarkdownPreviewEnhanced - browser live preview.

Plugin entry point: registers the event listener and ST lifecycle hooks.
All commands live in ``commands/``; rendering, server, browser, and state
logic live in ``mpe_core/``.
"""
import sublime
import sublime_plugin

from .mpe_core import config
from .mpe_core import log
from .mpe_core.render import render_view
from .mpe_core.preview_state import (
    set_output_dir,
    set_preview_open,
    start_scroll_poller,
    stop_scroll_poller,
    stop_server,
)
from .mpe_core.preview_server import set_editor_line, set_active_doc
from .mpe_core import tab_manager

# Import commands so Sublime registers them
from .commands import *  # noqa: F401,F403

_MARKDOWN_SCOPE = "text.html.markdown"


class MarkdownPreviewEnhancedListener(sublime_plugin.EventListener):
    _timers = {}
    _last_switch_tab = None  # last file pushed via ST->WEB switchTab (loop guard)

    def on_load_async(self, view):
        """Browser link click triggered file load - render + focus preview."""
        fn = view.file_name()
        if fn and tab_manager.consume_pending_open(fn):
            render_view(view, force=True, open_browser=False)

    def on_activated_async(self, view):
        """ST->WEB: editor view switched - push switchTab so the matching
        browser tab focuses itself via window.open('', windowName).

        Cross-platform (no AppleScript). Direction guard: if this view
        activation came from a WEB->ST doc switch (open_doc_from_browser
        focusing the view), skip - echoing switchTab back would loop.
        """
        from .mpe_core.preview_state import (
            is_preview_open, is_st_to_web_suppressed)
        if not is_preview_open():
            return
        if is_st_to_web_suppressed():
            log.debug("ST->WEB suppressed (WEB->ST echo)")
            return
        if not config.get("use_local_server", True):
            return
        try:
            if not view.match_selector(0, _MARKDOWN_SCOPE):
                return
            fn = view.file_name()
            if fn and fn != _last_switch_tab:
                _last_switch_tab = fn
                log.debug("ST->WEB switchTab push: %s" % fn)
                set_active_doc(fn)
        except Exception:
            pass

    def on_modified_async(self, view):
        from .mpe_core.preview_state import is_preview_open
        if not is_preview_open():
            return
        try:
            ok_scope = view.match_selector(0, _MARKDOWN_SCOPE)
        except Exception:
            ok_scope = False
        if not ok_scope:
            return
        bid = view.buffer_id()
        timer = self._timers.get(bid)
        if timer:
            timer.cancel()
        import threading
        debounce = float(config.get("debounce_ms", 500) or 500) / 1000.0
        timer = threading.Timer(debounce, lambda: render_view(view))
        self._timers[bid] = timer
        timer.start()

    def on_selection_modified_async(self, view):
        """Push editor cursor line to the preview server (ST -> browser only)."""
        from .mpe_core.preview_state import is_preview_open
        if not is_preview_open():
            return
        if not config.get("scroll_sync", True):
            return
        if not config.get("use_local_server", True):
            return
        bound_id = tab_manager.get_bound_view_id()
        if bound_id and view.id() != bound_id:
            if not view.match_selector(0, _MARKDOWN_SCOPE):
                return
        try:
            if not view.match_selector(0, _MARKDOWN_SCOPE):
                return
            sel = view.sel()
            if not sel:
                return
            row, _col = view.rowcol(sel[0].begin())
            set_editor_line(row + 1, file_path=view.file_name())
        except Exception:
            pass


def plugin_loaded():
    log.clear()
    set_output_dir(config.output_dir())
    log.info("plugin loaded")


def plugin_unloaded():
    set_preview_open(False)
    stop_scroll_poller()
    stop_server()
    tab_manager.reset()
