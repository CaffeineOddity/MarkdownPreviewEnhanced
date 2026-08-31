"""Export the active markdown view to a standalone HTML file."""
import os
import traceback

import sublime
import sublime_plugin

from ..mpe_core import config
from ..mpe_core import log
from ..mpe_core.export_util import export_html
from ..mpe_core.render import render_settings, view_base_dir, view_title


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
