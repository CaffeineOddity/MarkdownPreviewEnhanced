# Contributing

**English** | [中文](#中文)

Usage docs: [README.md](README.md) · [README_zh.md](README_zh.md)

This GitHub repo root **is** the Sublime package root. Do not nest plugin modules.

## Local build

```bash
./build.sh -i                   # pack + install zip like Package Control
./build.sh --verify --from-git  # pack git HEAD like Package Control + smoke test
./release.sh 0.1.6 --dry-run    # preview a release
./release.sh 0.1.6              # verify, tag, push (channel is tags:true)
```

`-i` installs to `Installed Packages/` (same layout as Package Control). Prefer committing before `--from-git` / `release.sh`.

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
| `GET /api/snapshot` | Follower tabs catch up without SSE |
| `GET /api/open_doc` | Preview tab list: focus that file in the editor |
| `POST /api/browser_scroll` | Browser → editor scroll |
| `GET /api/export/html` | Standalone HTML |
| `GET /assets/*` | Vendored JS / CSS / fonts |
| `GET /doc/*` | Images next to the markdown file |

Debug files under `output_dir` (default: Sublime cache `MarkdownPreviewEnhanced/`): `preview.html`, `body.html`, `debug.log`.

## Logging

Use `mpe_core.log`: `info` / `error` always print (few lines); `debug` is verbose.

- Git checkout: `DEBUG = True` in `mpe_core/log.py` (verbose).
- Tagged / Package Control install: `release.sh` sets `DEBUG = False` on the tag (quiet).
- Override on a quiet install: User settings `"debug": true`.

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
./build.sh -i                   # 打 zip 装进 Installed Packages（和 Package Control 一样）
./build.sh --verify --from-git  # 按 Package Control 方式打包并跑冒烟
./release.sh 0.1.6              # 校验、打 tag、推送（频道已是 tags:true）
```

打 tag 前先提交。

架构与接口见上文表格。调试文件在 `output_dir`（默认 Sublime 缓存）：`preview.html`、`body.html`、`debug.log`。

日志走 `mpe_core.log`：`info` / `error` 始终打印（少量），`debug` 为详细日志。git 检出默认详细；`release.sh` 打 tag 时关掉。发版安装排查可在 User 设置里加 `"debug": true`。

PR：改动尽量小；不要重排无关文件；不要提交 `.omc/`、`__pycache__/`；不要在本仓库加回 `repository.json`。改官方频道时只动 `MarkdownPreviewEnhanced` 那一条，日常发版不用开频道 PR。
