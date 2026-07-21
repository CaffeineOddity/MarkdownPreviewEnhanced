#!/bin/bash
set -euo pipefail

# Deploy package files from the repo root into Sublime Text Packages/.
# The GitHub repository root *is* the package root (Package Control requirement).

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
PKG_NAME="MarkdownPreviewEnhanced"
DST="${HOME}/Library/Application Support/Sublime Text/Packages/${PKG_NAME}"

echo "=== ${PKG_NAME} build ==="
echo "  src: ${REPO_ROOT}"
echo "  dst: ${DST}"

mkdir -p "${DST}"

# Sync package contents only — exclude tooling / VCS / agent state.
rsync -av --delete \
    --exclude='.git/' \
    --exclude='.claude/' \
    --exclude='.omc/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.python-version' \
    --exclude='.DS_Store' \
    --exclude='.gitignore' \
    --exclude='build.sh' \
    --exclude='release.sh' \
    --exclude='st_package_reviewer.sh' \
    --exclude='AGENTS.md' \
    --exclude='docs/' \
    --exclude='repository.json' \
    --exclude='repository.json.example' \
    "${REPO_ROOT}/" "${DST}/"

echo "  done ✓"
echo ""
echo "Files copied:"
find "${DST}" -type f -not -path '*__pycache__*' -not -name '*.pyc' | sort | while read -r f; do
    echo "  ${f#${DST}/}"
done
