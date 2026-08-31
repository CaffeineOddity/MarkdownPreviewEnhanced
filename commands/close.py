"""Close preview UI; HTTP server stops when no live tabs remain."""
import sublime_plugin

from ..mpe_core.preview_state import close_preview_ui


class MarkdownPreviewEnhancedCloseCommand(sublime_plugin.WindowCommand):
    def run(self):
        close_preview_ui(stop_server=False)
        self.window.status_message(
            "MarkdownPreviewEnhanced: preview closed (server stops when idle)")
