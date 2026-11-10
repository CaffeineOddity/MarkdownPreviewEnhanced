# 导出默认路径 export_dir

## 背景与目标

Export PDF / Export HTML 通过 `show_input_panel` 询问目标路径。当前默认总是
`output_dir() / <basename>.{pdf,html}`（空 `output_dir` 时为 Sublime 缓存），
与源 `.md` 所在目录无关。日常把导出放在源文件旁需要每次手改路径。

本需求：增加**仅影响导出建议路径**的设置 `export_dir`，不改动预览临时文件
所用的 `output_dir`（`preview.html` / `body.html` / `debug.log` 等）。

## 设计

- 新设置项 `export_dir`（默认 `""`）：
  - `""`：行为与旧版一致，`output_dir() / <basename>.{pdf,html}`。
  - `"beside_source"`：`<dirname(md)> / <basename>.{pdf,html}`。
  - 其他非空字符串：`expanduser(path) / <basename>.{pdf,html}`。
- 实现位置：`mpe_core/config.py` 的 `export_default_path(file_name, ext)`；
  `commands/export_pdf.py` 与 `commands/export_html.py` 用其结果作为
  input panel 默认值。用户仍可在面板中改路径。
- 未保存 / 无 `file_name`：文件名回落 `export.{pdf,html}`；
  `beside_source` 无源路径时回落 `output_dir`。
- PNG 导出走浏览器下载，无 Sublime input panel，不改。

## 行为约定

- 默认空字符串，非破坏性；需要「导出在源文件旁」时用户设置
  `"export_dir": "beside_source"`。
- 不创建目标目录（仅建议路径）；写入仍由现有导出逻辑负责。
- 不把预览缓存写到源目录。

## 验收标准

1. `export_dir` 为空时，建议路径与改前相同（`output_dir` + basename）。
2. `"beside_source"` + 已保存 md：建议路径为源文件同目录下的 `.pdf` / `.html`。
3. 自定义目录（含 `~`）时，建议路径为该目录下的 basename。
4. 无 `file_name` 时使用 `export.{ext}`，且 `beside_source` 回落 `output_dir`。
5. `tests/test_export_dir.py` 覆盖上述分支。

## 已知边界与不做项

- 不自动记住上次导出路径。
- 不改 PNG / 浏览器下载路径。
- 不把 `output_dir` 语义改为源目录旁。
