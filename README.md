# MarkdownPreviewEnhanced

> Package id: **MarkdownPreviewEnhanced**  
> Browser-first live Markdown preview for Sublime Text — SSE push, zero install dependencies.

![preview](./img/preview.png)

## Features

| Feature | Status |
|--------|--------|
| GitHub-inspired full HTML+CSS rendering | ✅ |
| SSE push live refresh (no polling, preserves scroll) | ✅ |
| Mermaid diagrams (flowchart, sequence, gantt, …) | ✅ |
| ECharts charts (pie, bar, line, scatter, …) | ✅ |
| KaTeX math rendering (`$...$`, `$$...$$`) | ✅ |
| GFM task lists (`- [ ]` / `- [x]`) | ✅ |
| Footnotes (`[^1]`) | ✅ |
| YAML frontmatter stripping | ✅ |
| TOC sidebar (sticky outline of headings) | ✅ |
| Code syntax highlighting (Pygments) | ✅ |
| Scroll sync (editor ↔ preview) | ✅ |
| Export to standalone HTML | ✅ |
| Export to PNG (html2canvas, in-browser) | ✅ |
| Export toolbar (PNG + HTML buttons on preview page) | ✅ |
| Relative image resolution (`./img/a.png`) | ✅ |
| Cross-platform (macOS / Windows / Linux) | ✅ |
| Dark mode friendly | ✅ |
| Zero install dependencies (all vendored) | ✅ |

## Requirements

- Sublime Text 4 (Build 4107+)
- **Nothing else** — python-markdown, Pygments, KaTeX, Mermaid, ECharts, html2canvas are all vendored
- **No Chrome required** — PNG via html2canvas, HTML via local server

## Usage

1. Open a `.md` file.
2. Press `Ctrl+Shift+M` (Windows/Linux) / `Cmd+Shift+M` (macOS).
3. A browser tab opens with the live preview.
4. Edit the markdown — the plugin re-renders and **SSE pushes** the update to the browser in-place. No polling, no scroll loss.
5. Press the shortcut again to **focus the existing preview tab**.  
   Use **Close Preview** to close the tab and stop the local server.

### Preview page toolbar

The preview page has export buttons in the bottom-left corner:

| Button | Action |
|--------|--------|
| 🖼️ | Export PNG — captures the rendered preview via html2canvas (2x resolution) |
| 💾 | Export HTML — downloads a clean standalone HTML file (no toolbar, no scripts) |

### Shortcuts

| macOS | Windows/Linux | Action |
|-------|---------------|--------|
| `Cmd+Shift+M` | `Ctrl+Shift+M` | Toggle Preview |
| `Cmd+Shift+Alt+M` | `Ctrl+Shift+Alt+M` | Close Preview |
| `Cmd+Shift+E` | `Ctrl+Shift+E` | Export HTML |
### Commands

| Command | Description |
| --- | --- |
| `MarkdownPreviewEnhanced: Toggle Preview` | Open / focus browser preview |
| `MarkdownPreviewEnhanced: Close Preview` | Close preview and stop server |
| `MarkdownPreviewEnhanced: Refresh Preview` | Force re-render |
| `MarkdownPreviewEnhanced: Export HTML…` | Write a standalone HTML file |
### Settings

Preferences → Package Settings → **MarkdownPreviewEnhanced** → Settings

| Setting | Default | Description |
| --- | --- | --- |
| `mermaid_theme` | `"default"` | `default`, `dark`, `forest`, `neutral` |
| `output_dir` | `""` | Empty = Sublime cache |
| `use_local_server` | `true` | Local HTTP server for SSE push / images / scroll sync |
| `server_port` | `8765` | Preferred port (tries next ports if busy) |
| `server_idle_seconds` | `45` | Auto-stop server after no browser activity (`0` = only on Close) |
| `browser` | `"auto"` | `auto`, `default`, `chrome`, `safari`, `firefox`, `edge`, … |
| `debounce_ms` | `500` | Live re-render debounce |
| `show_toc` | `true` | Sticky TOC sidebar |
| `enable_katex` | `true` | Math rendering (local KaTeX only) |
| `enable_task_lists` | `true` | `- [ ]` / `- [x]` |
| `enable_footnotes` | `true` | `[^1]` footnotes |
| `strip_frontmatter` | `true` | Strip leading YAML `---` blocks |
| `scroll_sync` | `true` | Editor ↔ preview scroll (needs local server) |
| `custom_css` | `""` | Path to extra CSS file |
| `favicon` | `""` | Empty = bundled icon; `"none"` = no icon; otherwise a local path or `http(s)` URL |

View-level override example:

```jsonc
{
    "markdown_preview_enhanced.mermaid_theme": "forest"
}
```

## Architecture

```
Sublime Text edits .md
       │
       ▼ on_modified_async (debounce 500ms)
  Python: render markdown → full HTML page
       │
       ▼ update_content()
  PreviewState updated
       │
       ▼ SSE push ("content" event)
  Browser: EventSource receives event
       │
       ▼ applyContent()
  DOM updated in-place (innerHTML swap)
  KaTeX, ECharts, Mermaid re-rendered
  Scroll position unchanged
```

The browser maintains one persistent SSE connection (`GET /api/stream`). The server pushes content only when the markdown changes. No polling, no page reloads.

API endpoints:

| Endpoint | Purpose |
|----------|---------|
| `GET /` | Serve full HTML preview page |
| `GET /api/stream` | SSE push (content + editor line) |
| `POST /api/browser_scroll` | Scroll sync (browser → editor) |
| `GET /api/export/html` | Clean standalone HTML export |
| `GET /assets/*` | Vendored JS/CSS/fonts |
| `GET /doc/*` | Local images from document directory |

## Installation

### Package Control

Command Palette → `Package Control: Install Package` → `MarkdownPreviewEnhanced`
(once accepted on the default channel).

### Manual

Clone or copy this repository **as** the package folder
`Packages/MarkdownPreviewEnhanced/` (repo root = package root):

| Platform | Path |
| --- | --- |
| macOS | `~/Library/Application Support/Sublime Text/Packages/MarkdownPreviewEnhanced/` |
| Linux | `~/.config/sublime-text/Packages/MarkdownPreviewEnhanced/` |
| Windows | `%APPDATA%\Sublime Text\Packages\MarkdownPreviewEnhanced\` |

## Development

```bash
./build.sh                    # build PC-like .sublime-package, verify, install as zip
./build.sh --dev              # rsync unpacked into Packages/ (live edit)
./build.sh --verify --from-git  # pack git HEAD like Package Control + smoke test
./release.sh 1.2.0            # verify zip, tag + push + Package Control PR
./release.sh 1.2.0 --dry-run  # preview only
```

Package Control installs a **zipped** `.sublime-package` from the GitHub tag
(`"tags": true`). `./build.sh` builds that zip (flat package root), checks
required assets/modules, and runs an offline smoke test *against the zip* so
local-only `open()` bugs cannot slip through. Prefer committing before
`--from-git` / `release.sh` so the tag matches what you verified.

`release.sh` updates only this package's entry in the channel file (no full
reformat). Channel metadata is minimal (`details` + `releases`).

### Debug logs

Under `output_dir` (default: Sublime cache `MarkdownPreviewEnhanced/`):

| File | Content |
| --- | --- |
| `preview.html` | Live shell HTML |
| `body.html` | Last body fragment |
| `debug.log` | Timestamped logs |

## License

MIT — see [LICENSE](LICENSE).
