# 剪贴板截图粘贴

## 背景与目标

现有「Paste as Markdown」（`Cmd+Shift+V`）只读剪贴板的 HTML 转 markdown，
并可选择把远程图下载到 `media/`；但不处理系统截图（剪贴板里的位图）。
本需求让同一命令先尝试位图：有图就存盘并插入 `![](media/xxx.png)`，
没图才走现有 HTML→markdown / 纯文本降级。不新增快捷键。

## 行为约定

- 触发时机：`MarkdownPreviewEnhancedPasteAsMarkdownCommand.run()` 先探测
  剪贴板位图，有则走图片分支；无则完全沿用现有逻辑（HTML→markdown，
  无 HTML 再降级普通粘贴）。
- 存盘目录：沿用设置 `paste_images_dir`（默认 `media/`），相对当前 md 文件
  所在目录；文件无路径（未保存）时不落盘、直接在状态栏提示。
- 命名：`pasted-<时间戳>.png`（同秒冲突时追加序号去重）。
- 插入文本：`![](media/<文件名>)`，状态栏提示已存入路径。
- 探测失败 / 无位图：静默回到 HTML 分支，不报错、不弹窗。

## 数据结构

新增 `mpe_core/clipboard_image.py`：

```python
read_clipboard_image() -> bytes | None   # PNG 字节；无位图/不支持返回 None
```

平台实现：

- macOS：`osascript -e 'the clipboard as «class PNGf»'`，解 hex 得 PNG。
- Windows：PowerShell `System.Windows.Forms.Clipboard::GetImage()` 存临时 PNG
  再读回。
- Linux：X11 `xclip -selection clipboard -t image/png -o`；Wayland
  `wl-paste --type image/png`。

命令入口保持不变，`commands/paste_html_as_markdown.py` 在 `_work()` 开头
先 `read_clipboard_image()`。

## 涉及文件

- `mpe_core/clipboard_image.py`（新，平台读位图）
- `commands/paste_html_as_markdown.py`（命令入口合入图片分支）
- `docs/specs/paste-html-as-markdown.md`（已有命令的扩展，不重复其内容）

## 验收标准

- 剪贴板是截图时 `Cmd+Shift+V` 存 `media/pasted-*.png` 并插入相对路径图片。
- 剪贴板是网页 HTML 时行为与现状一致。
- 剪贴板无 HTML 无图时仍降级普通粘贴。

## 已知边界与不做项

- 不做剪贴板监听 / 自动粘贴（与 `paste-html-as-markdown.md` 一致）。
- 只支持 PNG（截图系统剪贴板的常见位图 PNG；JPEG 等按 PNG 写入）。
- 不做图片压缩 / 缩放。