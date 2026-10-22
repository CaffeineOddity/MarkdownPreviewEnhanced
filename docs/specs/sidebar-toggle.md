# sidebar-toggle

关联：[GitHub Issue #12](https://github.com/CaffeineOddity/MarkdownPreviewEnhanced/issues/12)

## 背景

预览页左侧侧栏由三块组成：工具栏（`mdpp-toolbar-sidebar`）、预览标签列表
（`mdpp-tabs`）、目录（`mdpp-toc`）。其中工具栏与标签列表始终存在，
`show_toc` 只决定目录块出不出现；即使关掉 `show_toc`，左侧 240px 的列仍在。
用户希望完全隐藏整个侧栏，专注看正文。

## 目标

- 提供一个右下角悬浮的眼睛按钮，一键隐藏 / 显示整个侧栏
- 隐藏时侧栏整块消失，两列布局收回单列，正文居中铺满
- 状态记在浏览器 localStorage，刷新 / 换文档沿用，默认显示

## 方案

### 交互（html_builder.py + preview.js）

- 预览壳 `build_preview_shell` 的 `.mdpp-wrap` 之后新增
  `<button id="mdpp-sidebar-toggle" class="mdpp-sidebar-toggle">`，
  内含睁眼 / 闭眼两个内联 SVG（`stroke="currentColor"`，颜色随 CSS 变量
  自动适配暗黑模式），固定于预览页右下角。按钮不在侧栏内部，侧栏藏掉后
  仍可点回。图标由 CSS 按状态切换：侧栏可见显示「睁眼」（点击=隐藏），
  隐藏后显示「闭眼」（点击=显示）。
- `preview.js`：
  - `mdppToggleSidebar()` 在 `<body>` 上切换 `mdpp-sidebar-hidden` 类，
    并写 `localStorage["mdpp-sidebar"]`（`"hidden"` / `"visible"`）
  - `initSidebar()` 启动时读 localStorage 恢复；`title` / `aria-label` 在
    `Hide sidebar` / `Show sidebar` 间切换
- 不新增 Sublime 设置项，不新增命令，不绑快捷键（遵守
  [no-default-keybindings](no-default-keybindings.md)）

### CSS（preview.css）

- `body.mdpp-sidebar-hidden .mdpp-sidebar` 隐藏侧栏
- `body.mdpp-sidebar-hidden.mdpp-has-toc .mdpp-wrap` 收回单列
  （`display: block` + 居中 `max-width`），`.markdown-body` 恢复居中宽度
- `.mdpp-sidebar-toggle` 固定右下角、圆形、复用主题变量；`@media print`
  与侧栏一起隐藏

## 验收标准

- 点击眼睛按钮，整个侧栏（工具栏 + tabs + 目录）一起消失 / 出现，无刷新
- 隐藏后正文独占宽度、居中，无 240px 空列残留
- 刷新或重开预览后状态保持
- `show_toc` 语义不变：恢复侧栏后目录仍按该设置显示 / 隐藏
- 打印与导出 HTML / PDF 不含该按钮、不受影响

## 不做项

- 不分别隐藏工具栏 / tabs / 目录（整栏一个开关）
- 不做 ST 编辑器侧快捷键（issue #11 结论）
- 不改 `show_toc` 配置