"""在光标处插入演示模式的分页标记 ``<!-- pagebreak -->``。

默认不绑定任何键；命令面板用 ``MarkdownPreviewEnhanced: Insert Page Break``。
示例键位见 Default.sublime-keymap（super+alt+p / ctrl+alt+p，默认注释）。

见 docs/specs/insert-pagebreak.md。
"""
import sublime_plugin

from ._insert import insert_on_own_line

PAGEBREAK = "<!-- pagebreak -->"


class MarkdownPreviewEnhancedInsertPagebreakCommand(sublime_plugin.TextCommand):
    def is_enabled(self):
        return self.view.match_selector(0, "text.html.markdown")

    def run(self, edit):
        insert_on_own_line(self.view, edit, PAGEBREAK)