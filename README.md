# MarkdownPreviewPro

A live, side-by-side Markdown preview plugin for Sublime Text — rendered inline
with Sublime's minihtml, **no external browser or HTML page is opened**.

![preview](docs/screenshot.png)

## Features

- **Toggle preview** with `super+shift+m` (macOS) / `ctrl+shift+m`
  (Windows/Linux). The window splits 50/50; the preview lives on the right.
- **Live updates** as you type (500ms debounce).
- **Mermaid diagrams** rendered to SVG via [mermaid-cli](https://github.com/mermaid-js/mermaid-cli)
  (invoked through `npx`, no global install required).
- **Syntax-highlighted code blocks** via [Pygments](https://pygments.org/).
- Tables, fenced code, TOC, attribute lists, and more (via
  [python-markdown](https://python-markdown.github.io/) extensions).

## Requirements

- Sublime Text 4 (Build 4000+) — uses `window.new_html_sheet` / minihtml.
- **Node.js** on your `PATH` (used only for Mermaid rendering through `npx`).
  The first Mermaid diagram fetches `@mermaid-js/mermaid-cli`, which may take a
  moment; results are cached.
- **python-markdown** and **Pygments** are vendored under `MarkdownPreviewPro/lib/`,
  so no external Python dependencies are required.

## Usage

1. Open a `.md` file.
2. Press `super+shift+m` (macOS) to toggle the preview panel.
3. Keep editing — the preview updates live.
4. Press the shortcut again (or close the preview sheet) to collapse back to a
   single column.

### Commands (Command Palette)

- `MarkdownPreviewPro: Toggle Preview`
- `MarkdownPreviewPro: Refresh Preview`

### Settings

| Setting | Default | Description |
| --- | --- | --- |
| `markdown_preview_pro.mermaid_theme` | `"default"` | Mermaid theme: `default`, `dark`, or `forest`. |

Example:

```jsonc
{
    "markdown_preview_pro.mermaid_theme": "dark"
}
```

## How it works

The plugin converts the current markdown buffer to HTML with python-markdown
(fenced code, tables, codehilite, toc, attr_list, nl2br). Mermaid fenced code
blocks are intercepted and rendered to inline SVG via mermaid-cli; all other
fenced blocks are syntax-highlighted with Pygments. The resulting HTML document
(with inlined CSS and SVG) is shown in a Sublime HTML sheet using minihtml —
displayed directly inside the editor window, split 50/50 with the source.

Mermaid SVGs are cached by `sha256(theme + source)` under
`Cache/MarkdownPreviewPro/mermaid/` to avoid re-running mermaid-cli on every
keystroke.

## Installation

### Via Package Control (once published)

1. Open the Command Palette → `Package Control: Install Package`.
2. Search for `MarkdownPreviewPro` and select it.

### Manual

Copy the `MarkdownPreviewPro` folder into your Sublime Text `Packages/`
directory:

- macOS: `~/Library/Application Support/Sublime Text/Packages/`
- Linux: `~/.config/sublime-text/Packages/`
- Windows: `%APPDATA%\Sublime Text\Packages\`

## Publishing to Package Control

This repository is structured to be listed on
[packagecontrol.io](https://packagecontrol.io). To submit:

1. Tag a release with a semantic version, e.g. `git tag 1.0.0 && git push --tags`.
2. Open a PR against [`packagecontrol/package_control`](https://github.com/wbond/package_control)
   adding an entry under `repository/` (see `repository.json.example` in this
   repo) — or use the "Submit a Package" page on packagecontrol.io.
3. Ensure `repository.json` reflects your public git URL and the release
   tag.

A ready-to-use `repository.json` snippet is provided in
[`repository.json`](repository.json).

### Pre-publish checklist

- [ ] `git init` the repo and push to a public GitHub/GitLab URL.
- [ ] Replace `YOUR_GITHUB_USER` in `repository.json` with your account.
- [ ] Tag the first release: `git tag 1.0.0`.
- [ ] `messages.json` + `messages/1.0.0.txt` release note (present).
- [ ] Submit via packagecontrol.io → "Submit a Package", pasting the
      `repository.json` URL (host the `repository.json` file at the repo root).
- [ ] Verify the package installs cleanly via Package Control on a fresh ST.

## License

MIT — see [LICENSE](LICENSE).
