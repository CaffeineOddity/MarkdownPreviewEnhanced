# MarkdownPreviewEnhanced

[English](README.md) | **中文**

Sublime Text 4 的浏览器实时 Markdown 预览。零额外依赖。

![preview](./img/preview.png)

## 功能

| 预览 | Markdown |
| --- | --- |
| ✅ 浏览器实时预览 | ✅ GitHub 风格 HTML / CSS |
| ✅ SSE 原地更新（不刷新） | ✅ 代码高亮 |
| ✅ 滚动位置保留 | ✅ GFM 任务列表 |
| ✅ 编辑器 ↔ 预览滚动同步 | ✅ 脚注 |
| ✅ 目录侧栏 | ✅ YAML frontmatter |
| ✅ 相对路径图片（`./img/a.png`） | ✅ KaTeX（`$…$` / `$$…$$`） |
| ✅ 导出 HTML / PNG / PDF | ✅ Mermaid 图 |
| ✅ 自定义 CSS 和 favicon | ✅ ECharts |
| ✅ macOS / Windows / Linux | ✅ 零额外依赖 |

## 安装

命令面板 → `Package Control: Install Package` → `MarkdownPreviewEnhanced`

或把本仓库克隆到 `Packages/MarkdownPreviewEnhanced/`（仓库根目录就是包根目录）。

## 用法

打开 `.md` 文件后：

| macOS | Windows / Linux | 作用 |
| --- | --- | --- |
| `Cmd+Shift+M` | `Ctrl+Shift+M` | 打开 / 聚焦预览 |
| `Cmd+Shift+Alt+M` | `Ctrl+Shift+Alt+M` | 关闭预览（并停止本地服务器） |
| `Cmd+Shift+E` | `Ctrl+Shift+E` | 导出 HTML |

命令面板里还有 Toggle、Close、Refresh、Export HTML、Export PDF。

编辑时浏览器原地更新（SSE），滚动位置保留。再按一次快捷键会聚焦已有标签。

预览页左下角：🖼️ 导出 PNG，💾 导出独立 HTML。

## 设置

Preferences → Package Settings → **MarkdownPreviewEnhanced** → Settings

| 设置 | 默认 | 说明 |
| --- | --- | --- |
| `mermaid_theme` | `"default"` | `default` / `dark` / `forest` / `neutral` |
| `output_dir` | `""` | 空 = Sublime 缓存目录 |
| `use_local_server` | `true` | SSE、相对图片、滚动同步 |
| `server_port` | `8765` | 占用时会尝试后续端口 |
| `server_idle_seconds` | `0` | 空闲自动停服；`0` = 直到 Close / 退出 Sublime |
| `browser` | `"auto"` | `auto` / `chrome` / `safari` / `firefox` / `edge` / … |
| `debounce_ms` | `500` | 输入时的重渲染延迟 |
| `show_toc` | `true` | 目录侧栏 |
| `enable_katex` | `true` | `$...$` / `$$...$$` |
| `enable_task_lists` | `true` | `- [ ]` / `- [x]` |
| `enable_footnotes` | `true` | `[^1]` |
| `strip_frontmatter` | `true` | 去掉文首 YAML `---` |
| `scroll_sync` | `true` | 编辑器 ↔ 预览（需要本地服务器） |
| `custom_css` | `""` | 额外 CSS 路径（可用 `~`） |
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
