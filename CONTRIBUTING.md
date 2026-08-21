# Contributing

**English** | [中文](#中文)

Usage docs: [README.md](README.md) · [README_zh.md](README_zh.md)

This GitHub repo root **is** the Sublime package root. Do not nest plugin modules.

## Local build

```bash
./build.sh --dev                # unpacked overlay in Packages/ (live edit)
./build.sh --verify --from-git  # pack git HEAD like Package Control + smoke test
./release.sh 0.1.6 --dry-run    # preview a release
./release.sh 0.1.6              # verify, tag, push (channel is tags:true)
```

`--dev` writes `package-metadata.json` into the overlay so Package Control does not reinstall the channel zip over a local test. Prefer committing before `--from-git` / `release.sh`.

## Architecture

```
edit .md → debounce → render HTML → update_content()
                                      │
                                      ▼
                             SSE GET /api/stream
                                      │
                                      ▼
                          browser applyContent() in place
```

| Endpoint | Purpose |
| --- | --- |
| `GET /` | Preview shell |
| `GET /api/stream` | SSE (content + editor line) |
| `POST /api/browser_scroll` | Browser → editor scroll |
| `GET /api/export/html` | Standalone HTML |
| `GET /assets/*` | Vendored JS / CSS / fonts |
| `GET /doc/*` | Images next to the markdown file |

Debug files under `output_dir` (default: Sublime cache `MarkdownPreviewEnhanced/`): `preview.html`, `body.html`, `debug.log`.

## PRs

- Keep diffs surgical. Do not reformat untouched files.
- Do not commit `.omc/`, `__pycache__/`, or local test dumps.
- Do not reintroduce `repository.json` in this repo.
- Channel PRs (`sublimehq/package_control_channel`): change **only** the `MarkdownPreviewEnhanced` entry. Minimal keys: `details`, `labels`, `releases`. Do not add `homepage` / `author` / `readme` — GitHub already provides those. Daily releases do **not** need a channel PR (`"tags": true`).

---

## 中文

用法：[README_zh.md](README_zh.md)

本仓库根目录就是 Sublime 包根目录，不要把插件模块再套一层文件夹。

```bash
./build.sh --dev                # 解压到 Packages/ 方便改代码
./build.sh --verify --from-git  # 按 Package Control 方式打包并跑冒烟
./release.sh 0.1.6              # 校验、打 tag、推送（频道已是 tags:true）
```

`--dev` 会写 `package-metadata.json`，避免 Package Control 用频道 zip 盖掉本地测试包。打 tag 前先提交。

架构与接口见上文表格。调试文件在 `output_dir`（默认 Sublime 缓存）：`preview.html`、`body.html`、`debug.log`。

PR：改动尽量小；不要重排无关文件；不要提交 `.omc/`、`__pycache__/`；不要在本仓库加回 `repository.json`。改官方频道时只动 `MarkdownPreviewEnhanced` 那一条，日常发版不用开频道 PR。
