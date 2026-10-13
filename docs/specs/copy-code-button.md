# copy-code-button

## 需求

预览页每个代码块提供一键「复制」：hover 代码块右上角出现按钮，点击后代码文本进剪贴板，按钮短暂显示 ✓。

## 行为

- 目标元素：`.markdown-body pre`（含 `.codehilite pre`）；mermaid fence（`pre.mermaid`）与 echarts 容器**不加**按钮。
- 按钮 hover 时出现（触屏设备常显），绝对定位于 pre 右上角；暗黑主题适配。
- 复制内容：代码块可见文本（`textContent`），原样保留换行；优先 `navigator.clipboard.writeText`，失败降级 `document.execCommand("copy")`。
- 内容更新（SSE 重渲染）后按钮随之重建；重复绑定需幂等（参照 `bindMermaidZoom` 的 `_bound` 模式，用事件委托）。
- 导出 HTML / PNG / 打印时按钮不出现（`@media print` 已隐藏 toolbar；导出 standalone HTML 不含 preview.js，天然无按钮）。

## 涉及文件

- `assets/preview.js`：`bindCopyCode()`，document 级事件委托 + `applyContent` 后调用
- `assets/preview.css`：`.mdpp-code-copy` 样式（light/dark/print）

## 验收标准

- hover 任一代码块出现复制按钮；点击后剪贴板为代码原文
- mermaid / echarts 块无复制按钮
- SSE 更新后按钮仍可用（事件委托不受 innerHTML 替换影响）
- 打印/导出 PNG 不含按钮
