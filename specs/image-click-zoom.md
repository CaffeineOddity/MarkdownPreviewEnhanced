# image-click-zoom

## 需求

预览中点击普通图片放大查看：全屏遮罩 + 拖拽平移 + 滚轮缩放 + Esc 关闭，
交互与既有 Mermaid click-to-zoom 一致。

## 行为

- 触发：点击 `.markdown-body img`（`#mdpp-content` 内）打开 zoom overlay。
  排除场景：图片在 `<a>` 内（点击应走链接）、`img` 是 data:/svg 图标尺寸极小
  （< 32px 视为图标不放大）、点击发生在 mermaid zoom overlay 打开时。
- 实现方式：复用 Mermaid zoom 的 overlay 基础设施
  （`preview.js` 的 `mermaidZoomRoot` 及拖拽/滚轮/Esc 处理），把 mover 内容从
  svg clone 泛化为任意节点 clone；`openMermaidZoom` 泛化为 `openZoomOverlay(node, kind)`。
  mermaid 分支保持向量宽度逻辑，img 分支用 `img.naturalWidth/naturalHeight` 初始适配。
- 初始尺寸：图片按容器 70% 视口宽等比缩放，`image-rendering: auto`；
  放大超过 100% 后光标 grab。
- 关闭：× 按钮、点 backdrop、Esc（`mdppInit` 已有 Escape 监听，追加 close 调用）。
- 打印/PNG 导出：overlay 在 `@media print` 下隐藏（沿用既有规则）。
- 暗色模式：backdrop 半透明黑，无需分支。
- 演示模式（`/presentation`）不注入此交互，slides 页无变更。

## 涉及文件

- `assets/preview.js`：泛化 `openMermaidZoom` → `openZoomOverlay`；新增
  `bindImageZoom()`（事件委托，挂 `mdppInit` 一次即可，SSE 替换 DOM 不失效）
- `assets/preview.css`：img 的 `cursor: zoom-in`；zoom canvas 内 img 样式
- `tests/`：无 JS 测试基建，行为靠人工冒烟（README 冒烟清单）

## 验收标准

- 点击普通图片打开 overlay，可拖拽、滚轮缩放（0.4x–6x）、Esc/×/点空白关闭。
- 图片包在链接里时点击走链接不放大。
- mermaid 图放大行为与之前完全一致（回归）。
- `applyContent` SSE 刷新后新图片仍可点击放大。

## 已知边界与不做项

- 不做双击还原、不做画廊多图切换（YAGNI，无第二个使用方）。
- 不处理懒加载中的占位图（`loading=lazy` 未加载完成时点击不放大）。
