# insert-notes

关联：[presentation-pagebreak](presentation-pagebreak.md)（`<!-- notes ... -->` 语法）、
[insert-pagebreak](insert-pagebreak.md)（同类插入命令）

## 背景

演示模式用 `<!-- notes ... -->` 携带演讲者备注（见 presentation-pagebreak.md）。
手打这段注释容易出错，需要一个命令快速插入，并提供可自行启用的示例快捷键。

## 目标

- 新增命令 `MarkdownPreviewEnhanced: Insert Speaker Notes`：在光标处插入
  **独立成行**的模板 `<!-- notes  'note here'-->`，用户把 `'note here'` 替换为
  实际备注。
- 仅 markdown 视图可用。
- 遵守 no-default-keybindings.md：不默认绑定键，在 Default.sublime-keymap 提供
  注释示例（`super+alt+n` / `ctrl+alt+n`）。

## 行为约定

- 命令名 `markdown_preview_enhanced_insert_notes`。
- 与 insert-pagebreak 完全复用「独立成行插入」逻辑（`commands/_insert.py` 的
  `insert_on_own_line`），仅模板文本不同。
- 模板为 `<!-- notes  'note here'-->`，`'note here'` 是占位提示，按纯文本处理。
- 仅当视图匹配 `text.html.markdown` 时 `is_enabled` 为真。

## 验收标准

- `.md` 文件光标处插入独立成行的 `<!-- notes  'note here'-->`。
- 非 markdown 文件命令不可用。
- `python3 tests/run_all.py` 全绿。
- README 双语 Key bindings 小节含 `super+alt+n` / `ctrl+alt+n` 示例。

## 不做项

- 不默认绑定任何键。
- 不渲染/转义备注内容；不做多行备注编辑。