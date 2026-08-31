"""Export the active markdown view to PDF."""
import os
import threading
import traceback

import sublime
import sublime_plugin

from ..mpe_core import config
from ..mpe_core import log
from ..mpe_core.export_util import export_pdf
from ..mpe_core.render import render_settings, view_base_dir, view_title


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
