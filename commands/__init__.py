"""Sublime Text commands for MarkdownPreviewEnhanced.

Each command class is registered by Sublime via ``sublime_plugin.WindowCommand``.
These are thin wrappers that delegate to ``mpe_core.render`` and
``mpe_core.preview_state`` - all real logic lives there.
"""
import os
import threading
import traceback

import sublime
import sublime_plugin

from ..mpe_core import config
from ..mpe_core import log
from ..mpe_core.export_util import export_html, export_pdf
from ..mpe_core.render import (
    render_settings,
    render_view,
    view_base_dir,
    view_title,
)
from ..mpe_core.preview_state import (
    close_preview_ui,
    ensure_server,
    is_preview_open,
)
from ..mpe_core.preview_server import set_active_doc
from ..mpe_core import tab_manager
from ..mpe_core.preview_url import focus_preview_tab, open_preview_browser


class MarkdownPreviewEnhancedToggleCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if view is None:
            log.info("no view to preview")
            self.window.status_message("MarkdownPreviewEnhanced: no active view")
            return

        fp = view.file_name()
        if fp and tab_manager.is_alive(fp):
            log.debug("toggle: reuse live tab %s" % fp)
            set_active_doc(fp)
            focus_preview_tab(fp)
            render_view(view, force=True, open_browser=False)
            self.window.status_message("MarkdownPreviewEnhanced: focusing preview")
            return

        log.debug("toggle: open preview file=%s preview_open=%s"
                  % (fp, is_preview_open()))
        self.window.status_message("MarkdownPreviewEnhanced: opening preview…")
        ensure_server()
        if fp:
            tab_manager.register(fp, view.id())
            tab_manager.bind_view(view)
        render_view(view, force=True, open_browser=False)
        url = tab_manager.preview_url(fp)
        open_preview_browser(url, True)


class MarkdownPreviewEnhancedCloseCommand(sublime_plugin.WindowCommand):
    def run(self):
        close_preview_ui(stop_server=False)
        self.window.status_message(
            "MarkdownPreviewEnhanced: preview closed (server stops when idle)")


class MarkdownPreviewEnhancedRefreshCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if view is not None:
            render_view(view, force=True, open_browser=False)


class MarkdownPreviewEnhancedExportHtmlCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if view is None:
            return
        default_name = "export.html"
        if view.file_name():
            base = os.path.splitext(os.path.basename(view.file_name()))[0]
            default_name = base + ".html"
        default_path = os.path.join(config.output_dir(), default_name)

        def on_done(path):
            if not path:
                return
            text = view.substr(sublime.Region(0, view.size()))
            rs = render_settings()
            try:
                dest, errors = export_html(
                    text,
                    path,
                    base_dir=view_base_dir(view),
                    mermaid_theme=rs["mermaid_theme"],
                    show_toc=bool(config.get("show_toc", True)),
                    enable_katex=bool(config.get("enable_katex", True)),
                    custom_css=config.get("custom_css", "") or "",
                    title=view_title(view),
                    log=log.debug,
                    favicon=config.get("favicon", "") or "",
                )
                msg = "Exported HTML: %s" % dest
                if errors:
                    msg += " (with warnings)"
                self.window.status_message(msg)
                sublime.message_dialog(msg)
            except Exception as e:
                sublime.error_message("Export HTML failed:\n%s" % e)
                log.error(traceback.format_exc())

        self.window.show_input_panel(
            "Export HTML to:", default_path, on_done, None, None)


class MarkdownPreviewEnhancedExportPdfCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if view is None:
            return
        default_name = "export.pdf"
        if view.file_name():
            base = os.path.splitext(os.path.basename(view.file_name()))[0]
            default_name = base + ".pdf"
        default_path = os.path.join(config.output_dir(), default_name)

        def on_done(path):
            if not path:
                return
            text = view.substr(sublime.Region(0, view.size()))
            rs = render_settings()
            self.window.status_message("MarkdownPreviewEnhanced: exporting PDF…")

            def _work():
                try:
                    dest = export_pdf(
                        text,
                        path,
                        base_dir=view_base_dir(view),
                        mermaid_theme=rs["mermaid_theme"],
                        show_toc=False,
                        enable_katex=bool(config.get("enable_katex", True)),
                        custom_css=config.get("custom_css", "") or "",
                        title=view_title(view),
                        log=log.debug,
                        favicon=config.get("favicon", "") or "",
                    )
                    sublime.set_timeout(
                        lambda: (
                            self.window.status_message("Exported PDF: %s" % dest),
                            sublime.message_dialog("Exported PDF:\n%s" % dest),
                        ),
                        0,
                    )
                except Exception as e:
                    err = str(e)
                    sublime.set_timeout(
                        lambda: sublime.error_message(
                            "Export PDF failed:\n%s" % err),
                        0,
                    )
                    log.error(traceback.format_exc())

            threading.Thread(target=_work, daemon=True).start()

        self.window.show_input_panel(
            "Export PDF to:", default_path, on_done, None, None)
