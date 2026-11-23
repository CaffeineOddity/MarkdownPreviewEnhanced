# list-nesting

关联：[Issue #23](https://github.com/CaffeineOddity/MarkdownPreviewEnhanced/issues/23)、
[Issue #27](https://github.com/CaffeineOddity/MarkdownPreviewEnhanced/issues/27)

状态：已实现（2026-11-23）；`tests/test_nested_list_indent.py` 自动回归。

## 背景

Python-Markdown 默认要求子列表缩进 4 个空格。v0.3.6 把列表处理器的
`tab_length` 固定为 2 来支持 issue #23 的两空格子列表，但因此只认 2–3 个
空格为一层：4 个空格或 tab 缩进的子列表被并进父项文字（issue #27）。

同期的 issue #27 示例里，列表前没有空行（`un-order points` 下一行就是
`- point 1`）。Python-Markdown 只认空行后的列表，于是整段都渲染成文字。

## 目标

- 子列表按父项正文列（content column）分层，2 / 3 / 4 个空格和 tab 都能嵌套。
- 段落里直接出现列表标记时，列表从中断处开始，与 CommonMark / GitHub 一致。
- 顶层缩进代码块、有序列表 `start`、`ul` / `ol` 不混表等既有行为不变。

## 行为约定

### 子列表层级

父项正文列 = 父项标记缩进 + 标记宽度 + 标记后的空格数
（`- ` 是 2，`1. ` 是 3）。同一列表块内，一条标记行算作子项的条件：

- 缩进 >= 父项标记缩进 + 2（保留 v0.3.6 的两空格习惯）
- 缩进 <= 父项正文列 + 3（再深就是父项文字；有空行时是缩进代码块）

tab 在列表解析前已由 Markdown 的 detab 预处理按 4 个空格展开。
更深的行保留相对缩进；同一层出现 `ul` 与 `ol` 时仍分成两张表。

跨空白行的缩进块拿不到父项源码，按层级估算正文列（每层最多 3 列）再留
3 个空格余量，避免把 4 个空格深的松散子列表误判成代码块。

### 段落中断

段落块里遇到以下行时，从该行开始一个新列表：

- 行首 0–3 个空格后接 `*` / `+` / `-`，或 `1.`
- 标记后至少一个空格或 tab，且后面有非空白内容

`2.` 等非 1 开始的有序列表、空列表项不中断段落。
中断按块解析，因此引用块、列表项内部的段落同样适用。

### 保持不变

- 顶层 4 空格缩进仍是代码块；列表项内的缩进代码块仍按空白行分隔。
- 有序列表 `start` 属性（issue #15）继续保留。
- 紧凑 / 松散列表、GFM 任务列表的结构不变。

## 涉及文件

- `mpe_core/nested_lists.py`：列表处理器、按正文列拆项、缩进块反缩进、
  段落中断处理器。
- `mpe_core/md_renderer.py`：注册 `ListNestingExtension`。
- `tests/test_nested_list_indent.py`：issue #23 / #27 回归。

## 验收标准

- issue #27 示例：`un-order points` / `order points` 渲染为段落，后面跟
  嵌套的 `ul` / `ol`，第二层正确缩进。
- 2 / 3 / 4 空格、tab、以及更深的三层列表均正确嵌套。
- `paragraph` 后的 `paragraph\n\n    code` 仍是代码块；
  `- item\n\n      code` 仍是列表项内的代码块。
- 有序列表从 3 开始时仍是 `<ol start="3">`。
- `python3 tests/run_all.py` 全绿。

## 不做项

- 不切换到 CommonMark 渲染器；只修列表缩进与段落中断。
- 不支持 `1)` 形式的有序列表标记。
- 顶层标记缩进 4 个空格及以上仍按缩进代码块处理。
- 不改变有序列表项内代码块的既有阈值（与 Python-Markdown 的
  `tab_length` 行为一致）。
