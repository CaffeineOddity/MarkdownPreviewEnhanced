# 演示分页统一 + 演讲者备注

## 背景与目标

现状（`mpe_core/presentation_builder.py` 的 `_split_slides`）按 `h1`–`h4` 切页，
PDF 导出无法手动分页，也没有演讲者备注。目标是用**同一种注释**同时驱动三处：

- 演示模式切页；
- HTML / PDF 导出的打印分页；
- 演讲者备注（仅演示模式可见）。

## 语法

| 注释 | 含义 |
| --- | --- |
| `<!-- pagebreak -->` | 独立一行，强制分页 |
| `<!-- notes ... -->` | 单行或多行，紧跟其所属于的那一页 |

两条注释在预览正文与导出产物中都不显示（HTML 注释本身不可见；备注内容
额外从导出产物中剥离）。

## 行为约定

- **切页**：演示模式只看 `<!-- pagebreak -->`，标题（`h1`–`h4`）不再自动切页。
  无 pagebreak 时整篇一页；pagebreak 之前的空内容丢弃；连续多个 pagebreak
  不产生空页。
- **备注归属**：一条（或多条连续的）`notes` 注释属于它前面的最后一张页；
  同页多条备注按顺序合并为一页备注。文档最开头（首个 pagebreak 之前）的
  notes 属于第 1 页。
- **备注展示**：演示页右下角浮层，按 `N` 显示 / 隐藏当前页备注；无备注的页
  不响应 `N`。浮层仅存在于演示页，不进预览正文、不进 HTML/PDF 导出。
- **导出分页**：HTML/PDF 里 `<!-- pagebreak -->` 转为分页点（打印 CSS
  `break-after: page`）；`<!-- notes -->` 整体删除。

## 数据结构

`presentation_builder` 新增：

```python
split_slides(body_html) -> list[Slice]
Slice = {"html": str, "notes": list[str]}
```

`export` 侧新增 `convert_pagebreaks(body_html) -> str`：删除 notes、把
pagebreak 注释替换为分页占位元素。

## 实现约束

- mdpopups（python-markdown）默认保留原始 HTML 注释。若实测发现注释被吞，
  则在 `md_renderer.render()` 里把这两条注释 stash 成占位符、`md.convert`
  之后再还原（复用现有 mermaid/math 的 stash 模式）。实现时先用单测锁定
  注释能穿透到 `body_html`。

## 涉及文件

- `mpe_core/presentation_builder.py`（`_split_slides` 改写、备注浮层 CSS/JS）
- `mpe_core/html_builder.py` 或 `mpe_core/export_util.py`（`convert_pagebreaks`）
- `mpe_core/md_renderer.py`（仅当注释被吞时加 stash）

## 验收标准

- 无 pagebreak 的文稿整篇一页；每处 `<!-- pagebreak -->` 切开一页；标题不再切页。
- 备注按 `N` 在当前页角落显示/隐藏，进切页后自动清除。
- 带 pagebreak 的 PDF 打印产物在标记处分页；HTML/PDF 里看不到 notes 文本。

## 已知边界与不做项

- 不做双屏演讲者视图、不做下一页预览。
- 备注内容按纯文本处理，不渲染 markdown。