# gfm-callout

## 需求

支持 GitHub 风格 Callout（Alert）语法：`> [!NOTE]` / `> [!TIP]` / `> [!IMPORTANT]` /
`> [!WARNING]` / `> [!CAUTION]`，渲染为带图标与配色的提示块，与 GitHub 外观对齐。

## 行为

- 语法：blockquote 首行为 `[!TYPE]`（大小写不敏感，允许首行尾随空白）；可选自定义标题
  `[!NOTE] 标题文字`。TYPE 之外的 `[!FOO]` 按 GitHub 规则视为普通引用，不特殊渲染。
- 输出结构：在 `blockquote` 上加 `class="mdpp-callout mdpp-callout-note"`，首行
  转换为 `<p class="mdpp-callout-title">…</p>`（含 SVG 图标），其余内容原样保留。
  不改 DOM 嵌套结构，滚动同步的 `data-line` 注入不受影响（blockquote 仍是首个
  `>` 行标注）。
- 实现方式：`render()` 内 markdown convert 之后的 HTML 后处理（与 `_apply_task_lists`
  同级、同模式），不写 markdown Extension：
  1. 正则定位 `<blockquote>` 开标签后紧跟的第一个 `<p>`，检查其文本是否以 `[!TYPE]` 开头；
  2. 命中则改写 class 与标题段落；HTML 嵌套不可靠时保持原文不报错。
- 图标：内联 SVG（GitHub octicon 风格，MIT），五类各一，颜色用 `currentColor`。
- 配色：亮/暗两套，色板取 GitHub Primer（note=蓝、tip=绿、important=紫、
  warning=黄、caution=红），CSS 变量挂在 `assets/preview.css`。
- 渲染范围：预览与导出共用 `render()`，天然一致；`enable_task_lists=false` 等开关不影响。

## 涉及文件

- `mpe_core/md_renderer.py`：`_apply_callouts(html)` 后处理 + 五类类型表
- `assets/preview.css`：`.mdpp-callout` 与五类变体、暗色适配
- `tests/test_gfm_callout.py`

## 验收标准

- 五类 TYPE 均渲染出对应 class、标题与图标；自定义标题生效，缺省用 TYPE 名大写。
- `[!FOO]`、普通 `> 引用`、非首行 `[!NOTE]` 均保持普通 blockquote。
- callout 内代码块、列表、嵌套引用正常渲染。
- 亮/暗主题下边框与图标颜色正确（人工目检 + class 断言）。
- 现有测试全部通过。

## 已知边界与不做项

- 不支持折叠（`+`/`-` 折叠标记是 Obsidian 扩展，GitHub 不支持，不做）。
- 不改 `presentation_builder`：callout 作为一个块随 slide 切分逻辑自然工作。
