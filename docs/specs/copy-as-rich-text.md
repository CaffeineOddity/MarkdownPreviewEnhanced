# copy-as-rich-text

## 需求

把当前渲染结果以富文本（text/html）复制到剪贴板，可直接粘贴进邮件 / Word / Confluence / Google Docs。

## 行为

### 预览侧（浏览器）

- 侧栏工具栏新增 📋 按钮（`mdpp-copy-rich`），标题 "Copy as rich text"。
- 复制范围：`#mdpp-content`（正文，不含侧栏/TOC/工具栏）。
- 实现：`navigator.clipboard.write([new ClipboardItem({"text/html": Blob, "text/plain": Blob})])`；
  `ClipboardItem` 不可用时降级 `document.execCommand("copy")`（临时选中正文节点 + text/html dataTransfer）。
- 反馈：按钮短暂显示 ✓；失败 alert。
- dark mode 复制的 HTML 是内联样式的 `markdown-body` 片段，粘贴目标按其自身样式呈现（body 类名背景色不带入）。

### 编辑器侧（ST 命令）

- `MarkdownPreviewEnhanced: Copy as Rich Text` 命令（`commands/copy_rich_text.py`）。
- 流程：读当前 view 全文 → `md_renderer.render`（与预览同参数）→ 包一层带 `preview.css` 内联样式的最小 HTML 文档 → 经临时 HTML 文件交给系统剪贴板。
- 剪贴板写入方式：macOS 用 `osascript`（`set the clipboard to (read (POSIX file ...) as «class HTML»)`)；
  Windows 用 PowerShell `Set-Clipboard`（HTML 片段需 CF_HTML 头）；Linux 尝试 `xclip -t text/html` / `wl-copy`，无工具时报错提示用预览侧按钮。
- 命令在后台线程执行子进程，完成后 `status_message` 反馈。

## 涉及文件

- `assets/preview.js`：`mdppCopyRich()`；`html_builder.py` 工具栏加按钮
- `commands/copy_rich_text.py` + `Default.sublime-commands`
- `mpe_core/html_builder.py`：`build_clipboard_html(body_html)` — 供 ST 侧生成带样式的独立片段

## 验收标准

- 预览页点 📋 后在邮件/文档编辑器粘贴，保留标题/表格/代码块样式
- ST 命令复制后同样可粘贴为富文本（macOS / Windows；Linux 依赖 xclip/wl-copy）
- 复制的是渲染 HTML 而非 markdown 源码
