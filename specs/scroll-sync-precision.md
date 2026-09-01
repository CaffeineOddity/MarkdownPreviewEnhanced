# scroll-sync-precision

## 背景

当前 `data-line` 只注入 h1–h6 标题（`md_renderer._inject_heading_lines`）。
表格、段落、列表项、代码块等无 `data-line`，导致：

- ST→browser：光标在表格/段落内时，`scrollToLine` 找不到匹配节点，
  滚到最近标题（可能在上或下），预览跳到错误位置。
- browser→ST：`findNearestLine` 同样只认标题，滚动在段落间无法精确上报。
- 点击预览段落无法定位到 ST 对应行。

## 目标

每个源码行对应的渲染后块级元素都有 `data-line`，实现：
- ST 光标行 → browser 精确滚动到对应元素
- browser 滚动 → ST 精确定位到对应行
- 点击 browser 元素 → ST 跳到对应行

## 方案

渲染前按源码行号标记每个块级元素。python-markdown 的 Treeprocessor
不够可靠（表格/代码块行号映射复杂），改用**渲染后正则注入**：

在 `md_renderer.render()` 中，`_inject_heading_lines` 之后新增
`_inject_block_lines(html, text, line_offset)`，对渲染后 HTML 的
块级元素按源码行号注入 `data-line`。

### 注入策略

源码按行扫描，记录每个块级结构起始行号；渲染后 HTML 按元素顺序匹配：

| 源码结构 | 渲染后 HTML | 注入目标 |
|----------|-------------|----------|
| `# 标题` | `<h1>…</h1>` | `<h1>` (已有) |
| `| a | b |` | `<table>` | `<table>` 首个 `<tr>` (跳过表头) |
| `- item` | `<li>…</li>` | `<li>` |
| `> quote` | `<blockquote>` | `<blockquote>` |
| ` ```code``` ` | `<pre>` | `<pre>` |
| 段落 | `<p>…</p>` | `<p>` |
| `1. item` | `<li>` (ol) | `<li>` |

### 行号映射

源码逐行扫描，记录每个块级元素的起始行号（1-based + line_offset）。
渲染后 HTML 按出现顺序匹配同类型元素。

已知边界：
- 嵌套列表只标外层 `<li>`
- mermaid/echarts 替换后的 `<div>` 不标
- 内联 HTML 标记的行不标

## 涉及文件

- `mpe_core/md_renderer.py`：新增 `_collect_block_lines` + `_inject_block_lines`
- `assets/preview.js`：`findNearestLine` / `scrollToLine` 已支持 `[data-line]`，无需改
- `MarkdownPreviewEnhanced.py`：恢复 `pop_browser_lines` 消费逻辑（双向同步）

## 验收标准

- ST 光标在表格行 → browser 滚到对应 `<tr>` 附近
- ST 光标在段落 → browser 滚到对应 `<p>`
- browser 滚动 → ST 光标跳到对应行（±1 行）
- 点击 browser 段落 → ST 跳到对应行
- h1–h6 仍精确（不回归）

## 不做项

- 不做内联元素（`<span>`/`<a>`/`<code>`）的 data-line
- 不做嵌套列表内层 `<li>` 的 data-line
