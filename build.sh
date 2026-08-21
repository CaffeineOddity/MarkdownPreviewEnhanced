#!/bin/bash
# build.sh — build / install / verify MarkdownPreviewEnhanced for Sublime Text.
#
# Package Control installs a *zipped* ``.sublime-package`` built from the GitHub
# tag (``"tags": true``). Local ``rsync`` into Packages/ is convenient for
# editing but hides zip-only bugs. This script can produce and validate the same
# kind of zip PC users get.
#
# Usage:
#   ./build.sh                # package zip + verify + install as PC-like zip
#   ./build.sh --dev          # rsync unpacked into Packages/ (live edit)
#   ./build.sh --package      # only write dist/*.sublime-package
#   ./build.sh --verify       # package (if needed) + offline zip smoke tests
#   ./build.sh --install-zip  # package + install zip to Installed Packages/
#   ./build.sh --help
#
# Source of the zip:
#   --from-git     use ``git archive`` (what PC gets from a pushed tag; default
#                  when the worktree is clean)
#   --from-worktree  pack the working tree with the same export-ignore rules
#                  (default when the worktree is dirty, so uncommitted fixes
#                  can be tested before tagging)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

PKG_NAME="MarkdownPreviewEnhanced"
DIST_DIR="${REPO_ROOT}/dist"
ZIP_PATH="${DIST_DIR}/${PKG_NAME}.sublime-package"

ST_SUPPORT="${HOME}/Library/Application Support/Sublime Text"
ST_PACKAGES="${ST_SUPPORT}/Packages/${PKG_NAME}"
ST_INSTALLED="${ST_SUPPORT}/Installed Packages/${PKG_NAME}.sublime-package"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
NC=$'\033[0m'

MODE="all"          # all | dev | package | verify | install-zip
SOURCE=""           # git | worktree | auto

usage() {
    sed -n '2,22p' "$0" | sed 's/^# \?//'
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dev) MODE="dev" ;;
        --package) MODE="package" ;;
        --verify) MODE="verify" ;;
        --install-zip) MODE="install-zip" ;;
        --from-git) SOURCE="git" ;;
        --from-worktree) SOURCE="worktree" ;;
        -h|--help) usage ;;
        *)
            echo "${RED}Unknown option: $1${NC}" >&2
            usage
            ;;
    esac
    shift
done

worktree_dirty() {
    ! git diff-index --quiet HEAD -- 2>/dev/null \
        || [ -n "$(git ls-files --others --exclude-standard)" ]
}

resolve_source() {
    if [ -n "$SOURCE" ]; then
        return
    fi
    if worktree_dirty; then
        SOURCE="worktree"
        echo "${YELLOW}Worktree dirty → packaging from worktree (not yet on GitHub).${NC}"
        echo "${YELLOW}Commit before release so Package Control gets the same bits.${NC}"
    else
        SOURCE="git"
        echo "Worktree clean → packaging from git archive (Package Control parity)."
    fi
}

# Paths that must never ship in the .sublime-package (mirror .gitattributes
# export-ignore + a few extra safety excludes).
should_exclude() {
    local rel="$1"
    case "$rel" in
        .git/*|.git) return 0 ;;
        .claude/*|.claude|.omc/*|.omc) return 0 ;;
        __pycache__/*|*/__pycache__/*|*.pyc|*.pyo) return 0 ;;
        .DS_Store|*/.DS_Store|.gitignore|.gitattributes) return 0 ;;
        .python-version) return 0 ;;
        build.sh|release.sh|st_package_reviewer.sh|AGENTS.md|README.md|README_zh.md|CONTRIBUTING.md|LICENSE) return 0 ;;
        docs|docs/*|img|img/*|dist|dist/*) return 0 ;;
        *.sublime-project|*.sublime-workspace) return 0 ;;
        repository.json|repository.json.example) return 0 ;;
        .gitcafe/*|.gitcafe) return 0 ;;
    esac
    return 1
}

REQUIRED_FILES=(
    "MarkdownPreviewEnhanced.py"
    "MarkdownPreviewEnhanced.sublime-settings"
    "Default.sublime-commands"
    "Default (OSX).sublime-keymap"
    "Default (Windows).sublime-keymap"
    "Default (Linux).sublime-keymap"
    "Main.sublime-menu"
    "messages.json"
    "mpe_core/__init__.py"
    "mpe_core/assets.py"
    "mpe_core/html_builder.py"
    "mpe_core/preview_server.py"
    "mpe_core/md_renderer.py"
    "mpe_core/katex_renderer.py"
    "mpe_core/markdown/__init__.py"
    "mpe_core/markdown/extensions/fenced_code.py"
    "mpe_core/markdown/extensions/codehilite.py"
    "mpe_core/pygments/__init__.py"
    "mpe_core/pygments/lexers/__init__.py"
    "assets/preview.css"
    "assets/highlight.css"
    "assets/preview.js"
    "assets/favicon.svg"
    "assets/mermaid.min.js"
    "assets/echarts.min.js"
    "assets/html2canvas.min.js"
    "assets/katex/katex.min.js"
    "assets/katex/katex.min.css"
    "assets/katex/fonts/KaTeX_Main-Regular.woff2"
)

package_from_git() {
    mkdir -p "$DIST_DIR"
    # git archive honors .gitattributes export-ignore — same as GitHub zipball.
    git archive --format=zip --prefix="" HEAD -o "$ZIP_PATH"
    echo "  wrote ${ZIP_PATH} (git archive HEAD)"
}

package_from_worktree() {
    mkdir -p "$DIST_DIR"
    local tmp stage
    tmp="$(mktemp -d "${TMPDIR:-/tmp}/mpe_pkg.XXXXXX")"
    stage="${tmp}/stage"
    mkdir -p "$stage"

    # Copy runtime tree with the same excludes PC-facing archives use.
    (
        cd "$REPO_ROOT"
        find . -type f -print | sed 's|^\./||' | while IFS= read -r rel; do
            if should_exclude "$rel"; then
                continue
            fi
            mkdir -p "$stage/$(dirname "$rel")"
            cp -p "$rel" "$stage/$rel"
        done
    )

    rm -f "$ZIP_PATH"
    (
        cd "$stage"
        # Zip contents at package root (no nested MarkdownPreviewEnhanced/).
        zip -qr "$ZIP_PATH" .
    )
    rm -rf "$tmp"
    echo "  wrote ${ZIP_PATH} (worktree)"
}

package_zip() {
    resolve_source
    echo "=== package (${SOURCE}) ==="
    case "$SOURCE" in
        git) package_from_git ;;
        worktree) package_from_worktree ;;
        *) echo "${RED}bad SOURCE=$SOURCE${NC}" >&2; exit 1 ;;
    esac
    echo "  size: $(wc -c < "$ZIP_PATH" | tr -d ' ') bytes"
}

validate_zip_layout() {
    echo "=== validate zip layout ==="
    if [ ! -f "$ZIP_PATH" ]; then
        echo "${RED}missing $ZIP_PATH — run package first${NC}" >&2
        exit 1
    fi

    python3 - "$ZIP_PATH" "${REQUIRED_FILES[@]}" <<'PY'
import sys, zipfile

zip_path = sys.argv[1]
required = sys.argv[2:]
zf = zipfile.ZipFile(zip_path)
names = set(zf.namelist())

# Package Control / Sublime expect files at the *root* of the zip, not nested
# under MarkdownPreviewEnhanced/...
nested = [n for n in names if n.startswith("MarkdownPreviewEnhanced/")]
if nested:
    print("ERROR: zip has nested package folder (Package Control expects flat root)")
    print("  example:", nested[0])
    sys.exit(1)

missing = [p for p in required if p not in names]
if missing:
    print("ERROR: required files missing from package zip:")
    for p in missing:
        print("  -", p)
    sys.exit(1)

# Fonts: KaTeX needs the full set under assets/katex/fonts/
fonts = [n for n in names if n.startswith("assets/katex/fonts/") and not n.endswith("/")]
if len(fonts) < 30:
    print("ERROR: expected many KaTeX fonts, found", len(fonts))
    sys.exit(1)

# Guard against accidentally shipping agent / cache junk.
bad = [n for n in names if n.startswith((".git/", ".omc/", "docs/", "dist/", "__pycache__/"))
       or n.endswith((".pyc", ".pyo"))]
if bad:
    print("ERROR: disallowed paths in zip:")
    for p in bad[:20]:
        print("  -", p)
    sys.exit(1)

print("  files:", len(names))
print("  katex fonts:", len(fonts))
print("  layout OK")
PY
}

verify_zip_runtime() {
    echo "=== offline zip runtime smoke test ==="
    python3 - "$ZIP_PATH" <<'PY'
import importlib
import os
import sys
import tempfile
import types
import zipfile

zip_path = sys.argv[1]
assert os.path.isfile(zip_path), zip_path

# --- sublime stub that reads package resources from the zip ---
zf = zipfile.ZipFile(zip_path)
sublime = types.ModuleType("sublime")

def load_resource(p):
    # Packages/MarkdownPreviewEnhanced/<rel>
    prefix = "Packages/MarkdownPreviewEnhanced/"
    if not p.startswith(prefix):
        raise IOError(p)
    return zf.read(p[len(prefix):]).decode("utf-8")

def load_binary_resource(p):
    prefix = "Packages/MarkdownPreviewEnhanced/"
    if not p.startswith(prefix):
        raise IOError(p)
    return zf.read(p[len(prefix):])

def find_resources(pat):
    out = []
    for n in zf.namelist():
        base = n.rsplit("/", 1)[-1]
        if pat == "KaTeX_*" and base.startswith("KaTeX_"):
            out.append("Packages/MarkdownPreviewEnhanced/" + n)
        elif pat and pat in n:
            out.append("Packages/MarkdownPreviewEnhanced/" + n)
    return out

cache = tempfile.mkdtemp(prefix="mpe_verify_cache_")
sublime.load_resource = load_resource
sublime.load_binary_resource = load_binary_resource
sublime.find_resources = find_resources
sublime.cache_path = lambda: cache
sys.modules["sublime"] = sublime

# Put the .sublime-package on sys.path exactly like Sublime does.
sys.path.insert(0, zip_path)

# Drop any already-imported copies from the repo checkout.
for k in list(sys.modules):
    if (
        k == "mpe_core"
        or k.startswith("mpe_core.")
        or k in ("markdown", "pygments")
        or k.startswith("markdown.")
        or k.startswith("pygments.")
    ):
        del sys.modules[k]

# Also remove the repo root from path so we cannot accidentally import unpacked sources.
repo_hints = []
for p in list(sys.path):
    if p and p != zip_path and os.path.isdir(p) and os.path.isfile(
        os.path.join(p, "MarkdownPreviewEnhanced.py")
    ):
        repo_hints.append(p)
for p in repo_hints:
    sys.path.remove(p)

import mpe_core  # noqa: E402  — installs vendor aliases from *inside* the zip

# Bug A: bare-name aliases must be the same objects as mpe_core.*
assert "markdown" in sys.modules, "markdown alias missing (zip install broken)"
assert "pygments" in sys.modules, "pygments alias missing (zip install broken)"
assert sys.modules["markdown"] is sys.modules["mpe_core.markdown"], "markdown identity split"
assert sys.modules["pygments"] is sys.modules["mpe_core.pygments"], "pygments identity split"

m = importlib.import_module("markdown.extensions.fenced_code")
assert m is sys.modules["mpe_core.markdown.extensions.fenced_code"]

import pygments.lexers  # noqa: F401
assert sys.modules["pygments.lexers"] is sys.modules["mpe_core.pygments.lexers"]

from mpe_core.md_renderer import render

out = render(
    "# T\n\n```python\nprint(1)\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n",
    base_dir=None,
)
assert not out.get("errors"), out.get("errors")
assert "<table>" in out["body_html"]
assert "codehilite" in out["body_html"]
# Real Pygments token spans — not the plain <pre class="codehilite"><code> fallback
assert "<span" in out["body_html"], "code highlight missing pygments spans"

# Bug B: assets via sublime.load_resource
from mpe_core import assets

css = assets.read_text("assets/preview.css")
assert css and "body" in css.lower(), "preview.css empty from zip"
assert assets.exists("assets/katex/katex.min.js")
root = assets.extract_katex()
assert root and os.path.isfile(os.path.join(root, "katex.min.js"))
fonts = os.listdir(os.path.join(root, "fonts"))
assert fonts, "no katex fonts extracted"

from mpe_core import html_builder

shell = html_builder.build_preview_shell(
    "<h1>T</h1>", enable_katex=True, use_server=True
)
assert css[:80] in shell or "markdown-body" in shell
assert "/assets/katex/katex.min.css" in shell

print("  zip runtime OK (aliases + render + assets)")
zf.close()
PY
}

deploy_unpacked() {
    echo "=== deploy unpacked → ${ST_PACKAGES} ==="
    mkdir -p "$ST_PACKAGES"
    # Prefer installing from the verified zip so unpacked == what PC ships.
    if [ -f "$ZIP_PATH" ]; then
        local tmp
        tmp="$(mktemp -d "${TMPDIR:-/tmp}/mpe_unpack.XXXXXX")"
        unzip -q "$ZIP_PATH" -d "$tmp"
        rsync -a --delete \
            --exclude='__pycache__/' \
            --exclude='*.pyc' \
            "${tmp}/" "${ST_PACKAGES}/"
        rm -rf "$tmp"
    else
        rsync -a --delete \
            --exclude='.git/' \
            --exclude='.claude/' \
            --exclude='.omc/' \
            --exclude='__pycache__/' \
            --exclude='*.pyc' \
            --exclude='.python-version' \
            --exclude='.DS_Store' \
            --exclude='.gitignore' \
            --exclude='.gitattributes' \
            --exclude='build.sh' \
            --exclude='release.sh' \
            --exclude='AGENTS.md' \
            --exclude='docs/' \
            --exclude='img/' \
            --exclude='dist/' \
            --exclude='repository.json' \
            --exclude='repository.json.example' \
            --exclude='*.sublime-keymap.example' \
            "${REPO_ROOT}/" "${ST_PACKAGES}/"
    fi
    # Package Control 看到 installed_packages 里有同名包、但 unpacked
    # 目录没有 package-metadata.json,就会在启动时 ignore → 重装 0.1.4 →
    # plugin_unloaded 把刚拉起的预览服务器杀掉(日志里约 1.5s).
    python3 - "$ST_PACKAGES/package-metadata.json" <<'PY'
import json, sys, time
path = sys.argv[1]
meta = {
    "name": "MarkdownPreviewEnhanced",
    "version": "0.1.4",
    "sublime_text": ">=4107",
    "platforms": ["*"],
    "python_version": "3.3",
    "url": "https://github.com/CaffeineOddity/MarkdownPreviewEnhanced",
    "description": "local --dev overlay (not a channel install)",
    "install_time": time.time(),
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(meta, f)
print("  wrote", path)
PY
    if [ -f "$ST_INSTALLED" ]; then
        rm -f "$ST_INSTALLED"
        echo "  removed Installed Packages zip (unpacked overlay is the test install)"
    fi
    echo "  done (unpacked)"
}

install_zip() {
    echo "=== install zip (Package Control layout) ==="
    if [ ! -f "$ZIP_PATH" ]; then
        package_zip
        validate_zip_layout
    fi
    mkdir -p "$(dirname "$ST_INSTALLED")"
    # Remove unpacked copy so Sublime loads the zip (PC users only have the zip).
    if [ -d "$ST_PACKAGES" ]; then
        echo "  removing unpacked ${ST_PACKAGES} (so zip is active)"
        rm -rf "$ST_PACKAGES"
    fi
    cp -f "$ZIP_PATH" "$ST_INSTALLED"
    echo "  installed → ${ST_INSTALLED}"
    echo "  ${YELLOW}Restart Sublime Text or reload the plugin.${NC}"
    echo "  ${YELLOW}Warning: if Package Control lists ${PKG_NAME}, it may overwrite this zip with the channel release on startup. For local testing use: ./build.sh --dev${NC}"
}

# --- main ---
case "$MODE" in
    dev)
        package_zip
        validate_zip_layout
        deploy_unpacked
        # unpacked Packages/ wins over Installed Packages zip (and over
        # Package Control re-installing the channel release).
        if [ -f "$ST_INSTALLED" ]; then
            echo "${YELLOW}Note: unpacked Packages/ overrides Installed Packages zip.${NC}"
        fi
        ;;
    package)
        package_zip
        validate_zip_layout
        ;;
    verify)
        package_zip
        validate_zip_layout
        verify_zip_runtime
        ;;
    install-zip)
        package_zip
        validate_zip_layout
        verify_zip_runtime
        install_zip
        ;;
    all)
        package_zip
        validate_zip_layout
        verify_zip_runtime
        install_zip
        ;;
    *)
        echo "${RED}unknown mode $MODE${NC}" >&2
        exit 1
        ;;
esac

echo
echo "${GREEN}=== build done (${MODE}) ===${NC}"
if [ -f "$ZIP_PATH" ]; then
    echo "  package: $ZIP_PATH"
fi
