# dark-mode

关联：[GitHub Issue #5](https://github.com/CaffeineOddity/MarkdownPreviewEnhanced/issues/5)

## 背景

预览页目前只有浅色配色（`preview.css` 的 `:root` 变量 + `highlight.css`
的 GitHub-light 代码高亮）。用户希望提供暗黑模式，避免白色刺眼。

## 目标

- 预览页支持暗黑模式；样式切换由 CSS 变量驱动，不改渲染管线
- 左侧工具栏（`mdpp-toolbar-sidebar`）增加切换按钮：☀️/🌙，点击在
  light/dark 间切换，记住选择（localStorage），下次打开沿用
- 默认跟随系统 `prefers-color-scheme`（无用户显式选择时）

## 方案

### CSS（preview.css）

- 暗黑变量定义在 `html[data-mdpp-theme="dark"]` 下（不用 media query 单独
  定义，便于 JS 切换属性而非切换整段样式）
- 默认（light）保持现有 `:root` 变量不变
- `highlight.css` 增加暗黑覆盖：`html[data-mdpp-theme="dark"] .codehilite …`
  （GitHub-dark 配色的 token 颜色）
- 暗黑模式下 `img`/`mermaid` 背景保持页面配色；导出/打印仍强制白底

### 按钮（html_builder.py + preview.js）

- 工具栏追加 `<button id="mdpp-theme-toggle">`，位于 sponsor 之前
- `preview.js`：
  - 启动时读 `localStorage["mdpp-theme"]`；无值则用
    `matchMedia("(prefers-color-scheme: dark)")` 初始化
  - 点击按钮切换 `data-mdpp-theme` 并持久化；按钮 emoji 随主题切换
    （light 显示 🌙 表示"切到暗色"，dark 显示 ☀️ 表示"切到亮色"）

## 验收标准

- 点击工具栏按钮，页面在 light/dark 间切换，无刷新、无闪烁
- 刷新或重开预览后主题保持
- 无显式选择时跟随系统主题变化
- 代码高亮在暗黑下可读（GitHub-dark token 色）
- 打印/导出 PNG/HTML 不受暗黑影响（仍白底）
- light 模式渲染与 0.1.9 完全一致（不回归）

## 不做项

- 不提供多套主题（只 light/dark）
- 不做 ST 编辑器侧配色同步
- 不改 presentation 幻灯片配色（后续需求再议）

## 实现备注（已完成）

- PNG 导出（html2canvas）渲染期间临时切回 light 主题再恢复，
  避免暗黑下浅色文字画在 `#ffffff` 画布上不可见
- 独立 HTML 导出（`build_export_html`）无 `data-mdpp-theme` 属性，
  天然走 light 变量，无需改；其内联 print 段也已强制白底
- 工具栏按钮文字随主题切换：light 显示 🌙（切到暗），dark 显示 ☀️（切到亮）
- 已用 headless Chrome + 最小 CSS 页面验证 light/dark 截图确实不同

