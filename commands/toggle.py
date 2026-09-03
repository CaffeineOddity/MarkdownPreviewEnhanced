"""Toggle live preview for the active markdown view."""
import sublime
import sublime_plugin

from ..mpe_core import log
from ..mpe_core import tab_manager
from ..mpe_core.preview_server import pin_os_open_file, set_active_doc
from ..mpe_core.preview_state import ensure_server, is_preview_open
from ..mpe_core.preview_url import focus_preview_tab, open_preview_browser
from ..mpe_core.render import render_view


class MarkdownPreviewEnhancedToggleCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if view is None:
            log.info("no view to preview")
            self.window.status_message("MarkdownPreviewEnhanced: no active view")
            return

        fp = view.file_name()
        alive = tab_manager.is_alive(fp) if fp else False
        log.info("toggle: enter file=%s alive=%s tabs=%d preview_open=%s"
                  % (fp, alive, tab_manager.live_count(), is_preview_open()))
        if fp and alive:
            log.debug("toggle: reuse live tab %s tabs=%d"
                      % (fp, tab_manager.live_count()))
            pin_os_open_file(fp)
            set_active_doc(fp)
            focus_preview_tab(fp)
            render_view(view, force=True, open_browser=False)
            self.window.status_message("MarkdownPreviewEnhanced: focusing preview")
            log.info("toggle: reuse path done")
            return

        log.debug("toggle: open preview file=%s preview_open=%s tabs=%d"
                  % (fp, is_preview_open(), tab_manager.live_count()))
        self.window.status_message("MarkdownPreviewEnhanced: opening preview…")
        ensure_server()
        if fp:
            tab_manager.register(fp, view.id())
            tab_manager.bind_view(view)
            pin_os_open_file(fp)
        render_view(view, force=True, open_browser=False)
        url = tab_manager.preview_url(fp)
        log.info("toggle: open path -> ensure_server + open_browser url=%s" % url)
        open_preview_browser(url, True)
