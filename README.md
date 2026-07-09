# MarkdownPreviewPro

Live Markdown preview in an external browser with full HTML+CSS rendering —
native `<table>`, mermaid diagrams, and syntax-highlighted code blocks.

![preview](docs/screenshot.png)

## Features

- **Browser preview** — full HTML+CSS engine (native `<table>`, GitHub-style
  CSS).  No compromise on rendering quality.
- **Live refresh** — file changes are picked up automatically via
  `<meta http-equiv="refresh">` polling.
- **Mermaid diagrams** — rendered to SVG by
  [mermaid-cli](https://github.com/mermaid-js/mermaid-cli) (`mmdc`).
- **Syntax-highlighted code blocks** — via [Pygments](https://pygments.org/).
- **Multi-browser auto-detection** — Chrome, Safari, Firefox, Edge, Brave,
  Opera.  Chrome-family browsers get AppleScript new-window + focus.
- **Zero external Python deps** — python-markdown and Pygments are vendored
  under `lib/`.

## Requirements

- Sublime Text 4 (Build 4107+).
- **Node.js** for mermaid rendering (optional — diagrams that fail to render
  show a fallback error message).  First run may be slow while `npx` caches
  `@mermaid-js/mermaid-cli`; results are cached on disk after that.

## Usage

1. Open a `.md` file.
2. Press `super+shift+m` (macOS) / `ctrl+shift+m` (Windows/Linux).
3. A browser window opens showing the rendered preview.
4. Press `super+shift+m` again to close + reopen (refresh).
5. Edit the markdown — the preview picks up changes within 1 second.

### Commands

| Command | Description |
| --- | --- |
| `MarkdownPreviewPro: Toggle Preview` | Open/close the browser preview |
| `MarkdownPreviewPro: Close Preview` | Close browser window |
| `MarkdownPreviewPro: Refresh Preview` | Force re-render |

### Settings

| Setting | Default | Description |
| --- | --- | --- |
| `markdown_preview_pro.mermaid_theme` | `"default"` | Mermaid theme: `default`, `dark`, `forest`, `neutral`. |

Example in your `Preferences.sublime-settings`:

```jsonc
{
    "markdown_preview_pro.mermaid_theme": "dark"
}
```

## How it works

1. The plugin reads the current markdown buffer.
2. Mermaid fenced code blocks are extracted and rendered to SVG via `mmdc`
   (subprocess calling `npx`).
3. The rest of the markdown is converted to HTML by python-markdown with
   extensions: tables, fenced_code, codehilite, toc, attr_list, nl2br.
4. The SVG and HTML are assembled into a full `<!DOCTYPE html>` document with
   inlined CSS, and written to
   `~/Downloads/MarkdownPreviewPro/preview.html`.
5. The file is opened in the default browser via `file://` URL.  The page
   polls for file changes and auto-refreshes.

Debug logs and the last rendered HTML are also written to
`~/Downloads/MarkdownPreviewPro/` (`debug.log`, `last_html.html`).

## Installation

### Via Package Control

Open the Command Palette → `Package Control: Install Package` → search for
`MarkdownPreviewPro`.

### Manual

Copy the `MarkdownPreviewPro` folder into your Sublime Text `Packages/`
directory:

| Platform | Path |
| --- | --- |
| macOS | `~/Library/Application Support/Sublime Text/Packages/` |
| Linux | `~/.config/sublime-text/Packages/` |
| Windows | `%APPDATA%\Sublime Text\Packages\` |

## Development

### Build & deploy

```bash
./build.sh                    # rsync into ST Packages/ with backup
```

### Release

```bash
./release.sh 1.0.1            # tag + push + create Package Control PR
./release.sh 1.0.1 --dry-run  # preview only, nothing pushed
```

The script:
1. Runs `build.sh` to sync the latest code.
2. Creates a git tag and pushes to GitHub.
3. Forks [`sublimehq/package_control_channel`](https://github.com/sublimehq/package_control_channel).
4. Updates `repository/m.json` with the new entry (or inserts it alphabetically).
5. Pushes the fork and creates/updates a PR.

### Debug logs

All output goes to `~/Downloads/MarkdownPreviewPro/`:

| File | Content |
| --- | --- |
| `preview.html` | Live HTML (what the browser loads) |
| `last_html.html` | Snapshot of the last rendered HTML |
| `debug.log` | Timestamped plugin logs |

## License

MIT — see [LICENSE](LICENSE).
