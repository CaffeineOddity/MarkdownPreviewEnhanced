# insert-pagebreak

关联：[presentation-pagebreak](presentation-pagebreak.md)（`<!-- pagebreak -->` 的语义）

## 背景

演示模式用**独立成行**的 `<!-- pagebreak -->` 强制分页（见
presentation-pagebreak.md）。手打这段注释容易出错，需要一个命令在光标处
快速插入，并提供一个可自行启用的示例快捷键。

## 目标

- 新增命令 `MarkdownPreviewEnhanced: Insert Page Break`，在光标处插入
  独立成行的 `<!-- pagebreak -->`。
- 仅 markdown 视图可用。
- 遵守 [no-default-keybindings](no-default-keybindings.md)：不默认绑定键，
  在 `Default.sublime-keymap` 提供注释示例（`super+alt+p` / `ctrl+alt+p`）。

## 行为约定

- 命令名 `markdown_preview_enhanced_insert_pagebreak`。
- 对每个选区：光标不在行首时先在光标处断行，再插入 `<!-- pagebreak -->`
  加换行，保证标记独立成行且不吞两侧内容。
- 多选区按从后往前的顺序处理，避免插入后坐标偏移。
- 仅当视图匹配 `text.html.markdown` 时 `is_enabled` 为真。

## 验收标准

- `.md` 文件光标处插入 `<!-- pagebreak -->`（独立一行）；行中间触发时原行
  在标记处断开、前后内容保留。
- 非 markdown 文件命令不可用。
- `python3 tests/run_all.py` 全绿。
- README 双语 Key bindings 小节含 `super+alt+p` / `ctrl+alt+p` 示例。

## 不做项

- 不默认绑定任何键（见 no-default-keybindings.md）。
- 不做「已存在 pagebreak 则跳过」等去重逻辑。