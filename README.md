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
| ✅ TOC + preview tab list | ✅ YAML frontmatter (title / date / tags banner) |
| ✅ Presentation mode (16:9 slides, page breaks + notes) | ✅ KaTeX (`$…$` / `$$…$$`) |
| ✅ Dark mode (follows system, persisted) | ✅ Mermaid diagrams (click to zoom) |
| ✅ Copy as rich text (📋 / command) | ✅ ECharts |
| ✅ Paste as markdown (right-click / command, HTML + screenshots) | ✅ Callouts (`> [!NOTE]`) |
| ✅ Code block copy button | ✅ `~~del~~` `==mark==` `^sup^` `~sub~` |
| | ✅ Code block filename / line numbers / highlight |
| ✅ Relative images (`./img/a.png`) | ✅ Task list checkbox sync (click in preview) |
| ✅ Export HTML / PNG / PDF | ✅ Image click zoom |
| ✅ Custom CSS & favicon | ✅ No extra installs |
| ✅ macOS / Windows / Linux | |

## Install

Command Palette → `Package Control: Install Package` → `MarkdownPreviewEnhanced`

Or clone this repo to `Packages/MarkdownPreviewEnhanced/` (repo root = package root).

## Usage

Open a `.md` file and run **MarkdownPreviewEnhanced: Toggle Preview** to open / focus the preview. The package ships **no default key bindings** (so it never overrides Sublime's built-in shortcuts — [issue #11](https://github.com/CaffeineOddity/MarkdownPreviewEnhanced/issues/11)); see [Key bindings](#key-bindings).

- **Paste as Markdown** (right-click or Command Palette) converts clipboard HTML to markdown (headings, bold/italic, links, lists, code blocks, GFM tables); no HTML → plain paste. Linux needs `xclip` / `wl-clipboard`. Set `paste_download_images` to `true` to save remote images into `media/`.
- Editing updates the preview in place (SSE), scroll kept. Re-running the command focuses the existing tab. Switching tabs in the browser focuses the matching Sublime view, and vice versa. The local server stays up while any preview tab is open and stops shortly after the last one closes.
- Sidebar toolbar: 📋 copy as rich text, 🖼️ PNG, 💾 standalone HTML, 📽️ presentation, 🌙/☀️ dark mode, ☕ tip.
- The 👁️ button at the bottom-right hides/shows the whole sidebar (toolbar, tabs, TOC) so you can focus on the preview; the choice is remembered.
- Hover a code block for a **Copy** button. **Copy as Rich Text** copies the rendered HTML to the clipboard (browser button or Command Palette) for mail / Word / Confluence.
- Dark mode follows `prefers-color-scheme`; the choice is stored in the browser. Click a Mermaid diagram or image to zoom. Clicking a line in Sublime scrolls the matching block to the middle of the preview.
- GFM task-list checkboxes are clickable and write back to the file. Callouts (`> [!NOTE]` / `TIP` / `IMPORTANT` / `WARNING` / `CAUTION`), `~~del~~`, `==mark==`, `^sup^`, `~sub~` render in preview and exports.

### Presentation mode

📽️ or **MarkdownPreviewEnhanced: Presentation Mode**. Slides reuse the live-preview HTML; every `h1`–`h4` starts a new slide. 16:9 canvas; navigate with arrow keys, edge click, or the HUD.

## Key bindings

The package ships **no default key bindings** ([issue #11](https://github.com/CaffeineOddity/MarkdownPreviewEnhanced/issues/11)). Bind them yourself:

- Command Palette → **Preferences: MarkdownPreviewEnhanced Key Bindings** opens a two-pane editor: the example on the left, your `User` keymap on the right. Save the right pane to apply.
- Or paste into the `User` keymap:

```json
[
    { "keys": ["super+alt+m"], "command": "markdown_preview_enhanced_toggle" },
    { "keys": ["super+alt+v"], "command": "markdown_preview_enhanced_paste_as_markdown" },
    { "keys": ["super+alt+p"], "command": "markdown_preview_enhanced_insert_pagebreak" },
    { "keys": ["super+alt+n"], "command": "markdown_preview_enhanced_insert_notes" }
]
```

Use `ctrl` instead of `super` on Windows / Linux. `super+alt` / `ctrl+alt` avoid the built-in **Expand Selection to Brackets** / **Paste and Indent** (which sit on `super+shift+m` / `super+shift+v`). Other commands live under the `MarkdownPreviewEnhanced:` prefix.

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
