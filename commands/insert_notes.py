"""在光标处插入演讲者备注模板 ``<!-- notes  'note here'-->``。

与 insert_pagebreak 复用同一插入逻辑（commands/_insert.py 的
insert_on_own_line），仅插入文本不同；插入后把 ``'note here'`` 改为实际备注。

默认不绑定任何键；命令面板用 ``MarkdownPreviewEnhanced: Insert Speaker Notes``。
示例键位见 Default.sublime-keymap（super+alt+n / ctrl+alt+n，默认注释）。

见 docs/specs/insert-notes.md。
"""
import sublime_plugin

from ._insert import insert_on_own_line

NOTES_TEMPLATE = "<!-- notes  'note here'-->"


class MarkdownPreviewEnhancedInsertNotesCommand(sublime_plugin.TextCommand):
    def is_enabled(self):
        return self.view.match_selector(0, "text.html.markdown")

    def run(self, edit):
        insert_on_own_line(self.view, edit, NOTES_TEMPLATE)