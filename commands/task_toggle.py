"""Apply a preview checkbox click back into the markdown buffer.

``view.replace`` needs an edit token, which only exists inside a TextCommand.
The HTTP handler only queues the click; the poller runs this command.
"""
import sublime_plugin

from ..mpe_core.preview_state import _apply_task_toggle_edit


class MarkdownPreviewEnhancedTaskToggleCommand(sublime_plugin.TextCommand):
    def run(self, edit, line, checked):
        _apply_task_toggle_edit(self.view, edit, int(line), bool(checked))
