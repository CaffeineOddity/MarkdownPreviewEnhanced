# frontmatter 标题 / 日期 / 标签

## 背景与目标

文首 YAML frontmatter 现被 `strip_frontmatter` 剥掉后即丢弃，导出标题一律
用文件名。本需求只读三个键，用于预览顶栏与导出标题：

- `title`
- `date`
- `tags`

零新依赖，手写迷你 YAML 子集；其余键忽略。

## 行为约定

- 只解析文首 `--- ... ---` 块内的 `title`、`date`、`tags`；值缺失的键缺省。
- `tags` 支持内联 `[a, b, c]` 与块列表 `- a`，均规整为字符串列表。
- **预览顶栏**：有任意三键之一时，在正文上方渲染一行
  「`<title>` · `<date>` · tag1 tag2 tag3」；没有 frontmatter 时保持现状
  （不追加这一行）。
- **导出标题**：HTML/PDF 的 `<title>` 与导出落入文件名优先用 `title`，
  无 `title` 时退回现有文件名逻辑。
- **演示模式**：不显示 frontmatter 顶栏（标题沿用现有文件名）。

## 数据结构

`md_renderer.render()` 返回 dict 增加一栏：

```python
"frontmatter": {"title": str|None, "date": str|None, "tags": list[str]}
```

无 frontmatter 时为 `None`。解析用独立纯函数
`parse_frontmatter(fm: str) -> dict`，只认 `key: value` 的简单形态。

## 涉及文件

- `mpe_core/md_renderer.py`（`parse_frontmatter`、`render` 返回 frontmatter）
- `mpe_core/render.py`（`publish` 把 frontmatter title 传入 shell）
- `mpe_core/html_builder.py`（`build_preview_shell` / `build_export_html`
  加 frontmatter 顶栏参数与标题）
- `mpe_core/export_util.py`（导出标题用 frontmatter title）
- `assets/preview.css`（顶栏样式，含暗色）

## 验收标准

- 有 frontmatter 时顶栏显示标题/日期/标签；无 frontmatter 无顶栏。
- HTML/PDF 的 `<title>` 与导出文件名用 `title`，无 `title` 退回文件名。
- 标签内联与块列表两种写法都解析正确。

## 已知边界与不做项

- 不做完整 YAML（嵌套、锚点、引用、多行折叠）。非法/复杂值按原样字符串。
- 不把 frontmatter 内容渲染进正文。
- 不把日期 / 标签写入 PDF 元信息（仅页面展示）。