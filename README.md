# MarkdownPreviewEnhanced

**English** | [中文](README_zh.md)

Browser live Markdown preview for Sublime Text 4. No extra installs.

![preview](./img/preview.png)

## Features

| Preview | Markdown |
| --- | --- |
| ✅ Live preview in the browser | ✅ GitHub-style HTML / CSS |
| ✅ SSE in-place update (no reload) | ✅ Syntax highlighting |
| ✅ One file ↔ one preview tab | ✅ GFM task lists |
| ✅ Editor ↔ preview tab switch | ✅ Footnotes |
| ✅ Scroll position kept | ✅ YAML frontmatter |
| ✅ TOC + preview tab list | ✅ KaTeX (`$…$` / `$$…$$`) |
| ✅ Presentation mode (16:9 slides) | ✅ Mermaid diagrams |
| ✅ Relative images (`./img/a.png`) | ✅ ECharts |
| ✅ Export HTML / PNG / PDF | ✅ No extra installs |
| ✅ Custom CSS & favicon | |
| ✅ macOS / Windows / Linux | |

## Install

Command Palette → `Package Control: Install Package` → `MarkdownPreviewEnhanced`

Or clone this repo to `Packages/MarkdownPreviewEnhanced/` (repo root = package root).

## Usage

Open a `.md` file, then:

| macOS | Windows / Linux | Action |
| --- | --- | --- |
| `Cmd+Shift+M` | `Ctrl+Shift+M` | Open / focus preview |
| `Cmd+Shift+Alt+M` | `Ctrl+Shift+Alt+M` | Close preview tabs (server stops when idle) |
| `Cmd+Shift+E` | `Ctrl+Shift+E` | Export HTML |

Command Palette also has Toggle, Close, Refresh, Presentation Mode, Export HTML, Export PDF.

Edit the file — the browser updates in place (SSE), scroll is kept. Press the shortcut again to focus the existing tab (does not stack another tab). Switching a preview tab in the browser focuses the matching Sublime view, and the other way around.

If you paste a preview URL into a new browser tab, the old tab for that file is replaced (Chrome may block `window.close()` on tabs you created yourself; those show a banner instead). The local server stays up while any preview tab is open, and stops shortly after the last one closes.

Preview sidebar toolbar: 🖼️ PNG snapshot, 💾 standalone HTML, 📽️ presentation, ☕ tip.

### Presentation mode

Open from the 📽️ button or **MarkdownPreviewEnhanced: Presentation Mode**. Slides are built from the same rendered HTML as live preview (headings, code, tables, KaTeX, Mermaid, ECharts). A new slide starts at every `h1`–`h4`. Navigate with arrow keys, click the left/right edges, or the HUD. Canvas is 16:9, scaled to the window.

## Settings

Preferences → Package Settings → **MarkdownPreviewEnhanced** → Settings

| Setting | Default | Description |
| --- | --- | --- |
| `mermaid_theme` | `"default"` | `default` / `dark` / `forest` / `neutral` |
| `output_dir` | `""` | Empty = Sublime cache |
| `use_local_server` | `true` | SSE, images, scroll sync |
| `server_port` | `8765` | Tries the next ports if busy |
| `server_idle_seconds` | `0` | Idle auto-stop; `0` = until Close / Sublime exit |
| `browser` | `"auto"` | `auto` / `chrome` / `safari` / `firefox` / `edge` / … |
| `debounce_ms` | `500` | Re-render delay while typing |
| `show_toc` | `true` | TOC sidebar |
| `enable_katex` | `true` | `$...$` / `$$...$$` |
| `enable_task_lists` | `true` | `- [ ]` / `- [x]` |
| `enable_footnotes` | `true` | `[^1]` |
| `strip_frontmatter` | `true` | Strip leading `---` YAML |
| `scroll_sync` | `true` | Editor ↔ preview (needs local server) |
| `custom_css` | `""` | Extra CSS file path (`~` ok) |
| `favicon` | `""` | Empty = bundled icon; `"none"` = no icon; otherwise a local path or `http(s)` URL |

Per-view override:

```jsonc
{
    "markdown_preview_enhanced.mermaid_theme": "forest"
}
```

Requires Sublime Text 4 (Build 4107+). Math, diagrams, and highlighting are vendored — nothing else to install.

Build / PR notes: [CONTRIBUTING.md](CONTRIBUTING.md)

## Support

If this package is useful:

- [Buy Me a Coffee](https://buymeacoffee.com/caffeineoddity)
- WeChat 赞赏:

<p><img src="img/wechat-sponsor.jpg" width="180" alt="WeChat 赞赏码"></p>

## License

MIT — [LICENSE](LICENSE)
