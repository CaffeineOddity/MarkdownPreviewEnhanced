#!/bin/bash
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)/MarkdownPreviewPro"
DST="${HOME}/Library/Application Support/Sublime Text/Packages/MarkdownPreviewPro"

echo "=== MarkdownPreviewPro build ==="
echo "  src: ${SRC}"
echo "  dst: ${DST}"

if [ ! -d "${SRC}" ]; then
    echo "ERROR: source dir not found: ${SRC}"
    exit 1
fi

# Backup existing files (one-level deep, timestamped)
BACKUP_DIR="$(dirname "${DST}")/.MarkdownPreviewPro_bak_$(date +%Y%m%d_%H%M%S)"
if [ -d "${DST}" ]; then
    mkdir -p "${BACKUP_DIR}"
    cp -R "${DST}" "${BACKUP_DIR}/"
    echo "  backup: ${BACKUP_DIR}"
fi

# Create target dir
mkdir -p "${DST}"

# Rsync source → dest, excluding caches
rsync -av --delete \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.python-version' \
    --exclude='.DS_Store' \
    "${SRC}/" "${DST}/"

echo "  done ✓"
echo ""
echo "Files copied:"
find "${DST}" -type f -not -path '*__pycache__*' -not -name '*.pyc' | sort | while read f; do
    echo "  ${f#${DST}/}"
done
