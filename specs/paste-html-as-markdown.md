# paste-html-as-markdown

## 需求

用户在浏览器里复制网页内容后，在 ST 的 markdown 文件里执行本插件命令，
剪贴板中的 HTML（text/html 格式）被转换为 markdown 源码并插入光标处。
与 `copy-as-rich-text` 互为逆操作：那个是 MD→HTML 写剪贴板，这个是 HTML→MD 读剪贴板。

参考实现：MarkdownWriter（Windows-only，ctypes 读 CF_HTML + 内置 html2text）；
本插件做跨平台版本。

## 行为

### 命令

- `MarkdownPreviewEnhanced: Paste as Markdown`（`commands/paste_html_as_markdown.py`，
  class `MarkdownPreviewEnhancedPasteAsMarkdownCommand`，TextCommand）。
- 仅 markdown 文件可用（`match_selector(0, "text.html.markdown")`）。
- 后台线程执行子进程；完成后主线程插入所有选区并 `status_message` 反馈；
  失败 `error_message` 报具体原因（命令、stderr、退出码）。

### 剪贴板 HTML 读取（平台分支）

| 平台 | 读取方式 |
|---|---|
| macOS | `osascript -e 'the clipboard as «class HTML»'`，输出 `«data HTML…»` hex，解析出字节再 utf-8 解码 |
| Windows | PowerShell `Get-Clipboard -TextFormatType Html`（返回 CF_HTML 全文，需剥掉头部、按 StartHTML/EndHTML 偏移截取） |
| Linux X11 | `xclip -selection clipboard -t text/html -o` |
| Linux Wayland | `wl-paste --type text/html` |

- Linux 先 `which xclip` / `which wl-paste` 探测（沿用 copy_rich_text 的探测写法），
  都没有时报错提示安装。
- 读不到 HTML（剪贴板只有纯文本）时降级为普通粘贴（`view.run_command("paste")`），
  并 `status_message` 说明。

### HTML → Markdown 转换

- 转换器随包内置（vendored，均 MIT，许可全文在 `mpe_core/_vendor/licenses/`），
  不要求用户装 pip 包，不新增 dependencies.json 条目。
  **版本锁定 py3.8 兼容**（ST 4200 host 是 python 3.8，vendor 前必须核对
  PyPI 的 `Requires-Python`，新版 typing_extensions 4.16 在 3.8 import 即崩）：
  - markdownify 0.13.1（six 依赖已移除，仅 `str()` 两处）
  - beautifulsoup4 4.12.3（不依赖 typing_extensions）
  - soupsieve 2.5
- 配置：`heading_style="ATX"`、`bullets="-"`。
- 输入预处理：剥掉 `<meta>` / `<style>` / `<script>` 标签与 HTML 注释
  （Chrome 片段带 meta，Firefox 片段带 StartFragment 注释包装）。

### 图片本地化（可选，默认关）

- 设置 `paste_download_images`（默认 false）、`paste_images_dir`（默认 `media`，
  相对当前 md 文件目录）。
- 开启时：转换结果中匹配 `![](\1)` 的 http(s) 图片 URL，逐个下载
  （带 UA 头，10s 超时），按 `crc32(内容)` 命名存盘，扩展名按 Content-Type
  （png/jpeg/gif 之外保留 URL 后缀或默认 .png）；替换为相对路径。
- 下载失败的图片保留原 URL，`status_message` 提示几张失败。
- 校验：Content-Length 上限 20MB；下载内容用 PNG/JPEG/GIF 魔数粗校验，不符则保留原 URL。

## 不做项

- 不做剪贴板监听/自动粘贴，只做显式命令。

## 入口

- 命令面板：`MarkdownPreviewEnhanced: Paste as Markdown`。
- 右键菜单（`Context.sublime-menu`）：markdown 文件内显示 "Paste as Markdown"
  （命令 `is_visible()` 已限定 `text.html.markdown`）。
- 默认快捷键：macOS `super+shift+v`，Windows/Linux `ctrl+shift+v`
  （与 toggle 的 `super/ctrl+shift+m` 对齐；已核验官方 Default 包与常见第三方
  均未占用，用户可在 User keymap 覆盖或删除）。
- 不解析 Windows CF_HTML 的 StartFragment/EndSelection 精确选区——整段 EndHTML 内内容都交给转换器。

## 涉及文件

- `specs/paste-html-as-markdown.md`（本文件）
- `mpe_core/_vendor/`（markdownify + bs4 + soupsieve，均 MIT，版本见上文锁定）
- `commands/paste_html_as_markdown.py`（新命令）
- `commands/__init__.py`（导出新命令）
- `Default.sublime-commands`（命令面板条目）
- `MarkdownPreviewEnhanced.sublime-settings`（`paste_download_images`、`paste_images_dir`）
- `tests/test_paste_html.py`（转换 + 平台分支的单测）

## 验收标准

- 浏览器复制一段带标题/列表/链接/图片的网页，ST 里执行命令，得到结构正确的 markdown。
- macOS / Windows / Linux(X11) / Linux(Wayland) 四分支各自可用；无工具时给出可操作的报错。
- 剪贴板无 HTML 时降级普通粘贴，不报错。
- `paste_download_images=true` 时图片落盘到 `paste_images_dir` 并替换为相对路径。
- `python3 tests/run_all.py` 通过。
