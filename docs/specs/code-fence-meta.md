# 代码块文件名 / 行号 / 高亮

## 背景与目标

现有围栏代码块只做语法高亮 + 客户端 Copy 按钮。本需求给围栏 info string
加三个可选元信息，渲染出文档站常见的代码块头部：

- 文件名 `title="..."`；
- 高亮行 `{1,3-5}`；
- 行号（所有围栏代码块都显示）。

零新依赖，不加设置项。

## 语法

````text
```python title="app.py" {1,3-5}
```
````

- `lang` 仍是首个 token（可省略）。
- `title="..."`：双引号包裹的文件名，可含空格，可省略。
- `{...}`：逗号分隔的正整数或区间 `a-b`，可省略；`title` 与 `{}` 顺序可换。
- 无 `title` 无 `{}` 的普通块也有头部（语言 + Copy）和行号列。

## 行为约定

- **头部**：每个围栏代码块都渲染头部，Copy 按钮在头部里，不进代码区。
  有 `title` 时头部是文件名 + 语言 + Copy；没有 `title` 时是语言 + Copy，
  语言也没有时只剩 Copy。
- **行号**：所有围栏代码块都显示行号列，与有没有 `title` / `{}` 无关。
- **高亮**：`{}` 指定的行加背景高亮；区间越界的行忽略。
- **复制**：Copy 仍复制纯代码文本——行号列是独立列，不进复制内容；
  高亮行拆分不改变代码文本。

## 数据结构

在渲染前剥离 info string 里的 `title` / `{}`，按文档顺序记录元信息，
渲染后按同一文档顺序 zip 回每个代码块：

```python
parse_fence_info(info: str) -> (lang, title_or_None, hl_lines_or_None)
```

元信息列表与产出 `<pre>` 一一对应；mermaid / echarts 走独立 stash，不参与计数。

## 涉及文件

- `mpe_core/code_fence.py`（新：info 解析 + 渲染前剥离 + 渲染后组装）
- `mpe_core/md_renderer.py`（接入剥离与组装的调用点）
- `assets/preview.css` / `assets/highlight.css`（头部、行号列、高亮样式，含暗色）
- `assets/preview.js`（`bindCopyCode` 支持头部里的按钮；`decorateCodeCopyButtons`
  跳过已带 `.mdpp-code` 的块）

## 验收标准

- `title` 显示在头部、`{}` 高亮对应行、每个围栏代码块都有头部和行号列。
- 无 `title` 的块，Copy 也在头部里，不盖住第一行代码。
- Copy 得到纯代码文本（含高亮/行号时也不混入行号）。
- 无元信息的普通代码块也有行号列，现有测试全部通过。

## 已知边界与不做项

- 不做 `title` 之外的自定义头部按钮 / 折叠。
- 不做跨文件的 include 代码块。
- 行号对齐以制表符展开后的视觉行为为准，不以源码 tab 宽度精确对齐。