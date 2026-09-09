# MarkdownPreviewEnhanced

[English](README.md) | **中文**

Sublime Text 4 的浏览器实时 Markdown 预览。零额外依赖。

![preview](./img/preview.png)

## 功能

| 预览 | Markdown |
| --- | --- |
| ✅ 浏览器实时预览 | ✅ GitHub 风格 HTML / CSS |
| ✅ SSE 原地更新（不刷新） | ✅ 代码高亮 |
| ✅ 一文件一预览 tab | ✅ GFM 任务列表 |
| ✅ 编辑器 ↔ 预览 tab 互切 | ✅ 脚注 |
| ✅ 滚动同步（编辑器 ↔ 预览） | ✅ GFM emoji（`:smile:`） |
| ✅ 目录 + 预览 tab 列表 | ✅ YAML frontmatter |
| ✅ 演示模式（16:9 幻灯片） | ✅ KaTeX（`$…$` / `$$…$$`） |
| ✅ 暗色模式（跟随系统，可记住） | ✅ Mermaid 图（点击放大） |
| ✅ 复制为富文本（📋 / 命令） | ✅ ECharts |
| ✅ 粘贴为 markdown（⇧⌘V / 右键） | ✅ 零额外依赖 |
| ✅ 代码块复制按钮 | |
| ✅ 相对路径图片（`./img/a.png`） | |
| ✅ 导出 HTML / PNG / PDF | |
| ✅ 自定义 CSS 和 favicon | |
| ✅ macOS / Windows / Linux | |

## 安装

命令面板 → `Package Control: Install Package` → `MarkdownPreviewEnhanced`

或把本仓库克隆到 `Packages/MarkdownPreviewEnhanced/`（仓库根目录就是包根目录）。

## 用法

打开 `.md` 文件后按 `Cmd+Shift+M`（Windows / Linux：`Ctrl+Shift+M`）打开 / 聚焦预览。

这是唯一的另一个默认快捷键（issue #6 -- 不覆盖系统常用快捷键）。关闭、刷新、演示模式、导出 HTML / PDF 都在命令面板里；需要快捷键可在 `User/Default (OSX).sublime-keymap` 自行绑定。

### 粘贴为 markdown

从网页复制内容后，在 `.md` 文件里按 `Cmd+Shift+V`（Windows / Linux：`Ctrl+Shift+V`）或右键 -> **Paste as Markdown**。剪贴板的 HTML 会被转为 markdown（标题、粗体斜体、链接、列表、代码块、GFM 表格）并插入光标处。如果剪贴板没有 HTML（比如从终端复制的纯文本），会自动降级为普通粘贴。Linux 上需要 `xclip` 或 `wl-clipboard`。设置 `paste_download_images` 为 `true` 可把远程图片下载到 `media/`（默认关闭）。

编辑时浏览器原地更新（SSE），滚动位置保留。再按一次快捷键会聚焦已有标签，不会再叠一张。浏览器里切预览 tab，Sublime 会切到对应 view，反过来也一样。

把已有预览 URL 粘到新标签时，会接管该文件的旧会话（Chrome 对「自己新建再粘贴」的标签可能不让脚本关，旧页会提示你手动关）。只要还有预览 tab 开着，本地服务器就保持；全部关掉后很快停服。

预览侧栏工具条：📋 复制为富文本，🖼️ 导出 PNG，💾 导出独立 HTML，📽️ 演示模式，🌙 / ☀️ 暗色模式，☕ tip。

鼠标悬停预览里的代码块会出现 **Copy** 按钮，一键复制代码原文。**复制为富文本**把渲染后的 HTML 放进剪贴板（浏览器按钮，或命令面板里的 **MarkdownPreviewEnhanced: Copy as Rich Text**），可直接粘贴进邮件、Word、Confluence 并保留样式。Linux 上编辑器命令需要 `xclip` 或 `wl-copy`；浏览器按钮不受此限制。

暗色模式默认跟随系统，点过一次后记在浏览器里。暗色下 Mermaid 用暗色主题。点击 Mermaid 图进入放大（拖动平移、滚轮缩放、`Esc` 关闭）。在 Sublime 里点某一行，预览会把对应块滚到窗口中间（Mermaid 围栏里的行也会对上图里的位置）。

### 演示模式

点 📽️ 或命令 **MarkdownPreviewEnhanced: Presentation Mode**。幻灯片用的就是实时预览同一套渲染（标题、代码、表格、KaTeX、Mermaid、ECharts）。每个 `h1`–`h4` 开一页。方向键、左右边缘点击或右下角 HUD 翻页。画布 16:9，按窗口缩放。

## 设置

Preferences → Package Settings → **MarkdownPreviewEnhanced** → Settings

| 设置 | 默认 | 说明 |
| --- | --- | --- |
| `mermaid_theme` | `"default"` | 导出 / 文件模式：`default` / `dark` / `forest` / `neutral`。实时预览跟随页面明暗。 |
| `output_dir` | `""` | 空 = Sublime 缓存目录 |
| `use_local_server` | `true` | SSE、相对图片、滚动同步 |
| `server_port` | `8765` | 占用时会尝试后续端口 |
| `server_idle_seconds` | `0` | 空闲自动停服；`0` = 直到 Close / 退出 Sublime |
| `browser` | `"auto"` | `auto` / `chrome` / `safari` / `firefox` / `edge` / … |
| `debounce_ms` | `500` | 输入时的重渲染延迟 |
| `show_toc` | `true` | 目录侧栏 |
| `enable_katex` | `true` | `$...$` / `$$...$$` |
| `enable_emoji` | `true` | GFM emoji shortcode（`:smile:`） |
| `enable_task_lists` | `true` | `- [ ]` / `- [x]` |
| `enable_footnotes` | `true` | `[^1]` |
| `strip_frontmatter` | `true` | 去掉文首 YAML `---` |
| `scroll_sync` | `true` | 编辑器 ↔ 预览（需要本地服务器） |
| `paste_download_images` | `false` | 粘贴为 markdown：把远程图片下载到 `media/` |
| `paste_images_dir` | `"media"` | 下载图片子目录（相对 md 文件） |
| `custom_css` | `""` | 额外 CSS 路径（可用 `~`） |
| `embed_images` | `true` | 导出 HTML/PDF：本地图内嵌 base64，产物单文件可移植 |
| `favicon` | `""` | 空 = 包内默认图标；`"none"` = 不要图标；否则填本地路径或 `http(s)` URL |

单视图覆盖：

```jsonc
{
    "markdown_preview_enhanced.mermaid_theme": "forest"
}
```

需要 Sublime Text 4（Build 4107+）。公式、图表、高亮都已内置，不用再装别的。

二次开发 / PR：[CONTRIBUTING.md](CONTRIBUTING.md)

## 赞助

觉得有用可以请杯咖啡：

- [Buy Me a Coffee](https://buymeacoffee.com/caffeineoddity)
- 微信赞赏：

<p><img src="img/wechat-sponsor.jpg" width="180" alt="微信赞赏码"></p>

## 许可

MIT — [LICENSE](LICENSE)
