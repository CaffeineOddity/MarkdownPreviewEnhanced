"""Force-render the active markdown view into the live preview."""
import sublime_plugin

from ..mpe_core.render import render_view


class MarkdownPreviewEnhancedRefreshCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if view is not None:
            render_view(view, force=True, open_browser=False)
