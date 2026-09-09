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
| ✅ Scroll sync (editor ↔ preview) | ✅ GFM emoji (`:smile:`) |
| ✅ TOC + preview tab list | ✅ YAML frontmatter |
| ✅ Presentation mode (16:9 slides) | ✅ KaTeX (`$…$` / `$$…$$`) |
| ✅ Dark mode (follows system, persisted) | ✅ Mermaid diagrams (click to zoom) |
| ✅ Copy as rich text (📋 / command) | ✅ ECharts |
| ✅ Paste as markdown (⇧⌘V / right-click) | ✅ No extra installs |
| ✅ Code block copy button | |
| ✅ Relative images (`./img/a.png`) | |
| ✅ Export HTML / PNG / PDF | |
| ✅ Custom CSS & favicon | |
| ✅ macOS / Windows / Linux | |

## Install

Command Palette → `Package Control: Install Package` → `MarkdownPreviewEnhanced`

Or clone this repo to `Packages/MarkdownPreviewEnhanced/` (repo root = package root).

## Usage

Open a `.md` file, then press `Cmd+Shift+M` (Windows / Linux: `Ctrl+Shift+M`) to open / focus the preview.

This is the only other default key binding (issue #6 - don't shadow common shortcuts). Close, Refresh, Presentation Mode, Export HTML and Export PDF are available from the Command Palette; add your own bindings in `User/Default (OSX).sublime-keymap` if wanted.

### Paste as markdown

Copy content from a web page, then in a `.md` file press `Cmd+Shift+V` (Windows / Linux: `Ctrl+Shift+V`) or right-click -> **Paste as Markdown**. The clipboard HTML is converted to markdown (headings, bold/italic, links, lists, code blocks, GFM tables) and inserted at the cursor. If the clipboard has no HTML (e.g. plain text copied from a terminal), it falls back to a normal paste. On Linux the command needs `xclip` or `wl-clipboard`. Set `paste_download_images` to `true` to download remote images locally into `media/` (off by default).

Edit the file — the browser updates in place (SSE), scroll is kept. Press the shortcut again to focus the existing tab (does not stack another tab). Switching a preview tab in the browser focuses the matching Sublime view, and the other way around.

If you paste a preview URL into a new browser tab, the old tab for that file is replaced (Chrome may block `window.close()` on tabs you created yourself; those show a banner instead). The local server stays up while any preview tab is open, and stops shortly after the last one closes.

Preview sidebar toolbar: 📋 copy as rich text, 🖼️ PNG snapshot, 💾 standalone HTML, 📽️ presentation, 🌙 / ☀️ dark mode, ☕ tip.

Hover any code block in the preview for a **Copy** button. **Copy as rich text** puts the rendered HTML on the clipboard (browser button, or `MarkdownPreviewEnhanced: Copy as Rich Text` in the Command Palette) so it can be pasted into mail, Word, or Confluence with styling intact. On Linux the command needs `xclip` or `wl-copy`; the browser button works everywhere.

Dark mode follows `prefers-color-scheme` until you toggle it; the choice is stored in the browser. Mermaid uses its `dark` theme with the page. Click a Mermaid diagram to enlarge it (drag to pan, scroll wheel to zoom, `Esc` to close). Clicking a line in Sublime scrolls that block to the middle of the preview (including lines inside a Mermaid fence).

### Presentation mode

Open from the 📽️ button or **MarkdownPreviewEnhanced: Presentation Mode**. Slides are built from the same rendered HTML as live preview (headings, code, tables, KaTeX, Mermaid, ECharts). A new slide starts at every `h1`–`h4`. Navigate with arrow keys, click the left/right edges, or the HUD. Canvas is 16:9, scaled to the window.

## Settings

Preferences → Package Settings → **MarkdownPreviewEnhanced** → Settings

| Setting | Default | Description |
| --- | --- | --- |
| `mermaid_theme` | `"default"` | Export / file-mode diagrams: `default` / `dark` / `forest` / `neutral`. Live preview follows the page theme. |
| `output_dir` | `""` | Empty = Sublime cache |
| `use_local_server` | `true` | SSE, images, scroll sync |
| `server_port` | `8765` | Tries the next ports if busy |
| `server_idle_seconds` | `0` | Idle auto-stop; `0` = until Close / Sublime exit |
| `browser` | `"auto"` | `auto` / `chrome` / `safari` / `firefox` / `edge` / … |
| `debounce_ms` | `500` | Re-render delay while typing |
| `show_toc` | `true` | TOC sidebar |
| `enable_katex` | `true` | `$...$` / `$$...$$` |
| `enable_emoji` | `true` | GFM emoji shortcodes (`:smile:`) |
| `enable_task_lists` | `true` | `- [ ]` / `- [x]` |
| `enable_footnotes` | `true` | `[^1]` |
| `strip_frontmatter` | `true` | Strip leading `---` YAML |
| `scroll_sync` | `true` | Editor ↔ preview (needs local server) |
| `paste_download_images` | `false` | Paste as markdown: download remote images to `media/` |
| `paste_images_dir` | `"media"` | Subdirectory for downloaded images (relative to md file) |
| `custom_css` | `""` | Extra CSS file path (`~` ok) |
| `embed_images` | `true` | Export HTML/PDF: embed local images as base64 so output is fully portable |
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
