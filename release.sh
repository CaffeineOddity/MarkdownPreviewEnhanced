#!/bin/bash
set -euo pipefail

# ── release.sh — tag a new release & update the Package Control channel PR ──
#
# Usage:
#   ./release.sh <version>          e.g.  ./release.sh 1.0.1
#   ./release.sh <version> --dry-run      preview only, don't push or PR
#
# What it does:
#   1. Verifies the working tree is clean
#   2. Updates repository.json version comment (informational)
#   3. Creates a git tag and pushes it
#   4. Forks & clones sublimehq/package_control_channel
#   5. Updates (or inserts) the MarkdownPreviewPro entry in repository/m.json
#   6. Pushes the fork and creates a PR (or updates the existing one)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ── args ────────────────────────────────────────────────────────────────────

VERSION="${1:-}"
DRY_RUN=false
if [ $# -ge 2 ] && [ "$2" = "--dry-run" ]; then
    DRY_RUN=true
fi

if [ -z "$VERSION" ]; then
    echo -e "${RED}Usage: $0 <version> [--dry-run]${NC}"
    echo "Example: $0 1.0.1"
    exit 1
fi

# Validate semver-ish
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+'; then
    echo -e "${YELLOW}Warning: '$VERSION' does not look like semver (x.y.z). Continue? [y/N]${NC}"
    read -r ans
    [ "$ans" = "y" ] || [ "$ans" = "Y" ] || exit 1
fi

# ── repo info ───────────────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

# Ensure we're on master and clean.
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "master" ]; then
    echo -e "${YELLOW}Not on master branch (current: $BRANCH). Continue? [y/N]${NC}"
    read -r ans
    [ "$ans" = "y" ] || [ "$ans" = "Y" ] || exit 1
fi

if ! git diff-index --quiet HEAD --; then
    echo -e "${RED}Working tree is dirty. Commit or stash changes first.${NC}"
    git status --short
    exit 1
fi

# Extract GitHub owner/repo from remote.
REMOTE_URL=$(git remote get-url origin)
OWNER_REPO=$(echo "$REMOTE_URL" | sed 's|.*github.com[:/]\(.*\)\.git|\1|')
OWNER="${OWNER_REPO%%/*}"
REPO_NAME="${OWNER_REPO##*/}"

echo -e "${GREEN}=== Releasing $REPO_NAME v$VERSION ===${NC}"
echo "  owner: $OWNER"
echo "  repo:  $REPO_NAME"
echo

# ── step 1: tag the release ─────────────────────────────────────────────────

echo -e "${YELLOW}[1/4] Building & tagging${NC}"

# Run build.sh if it exists, to make sure ST Packages are up-to-date.
if [ -x build.sh ]; then
    ./build.sh
fi

# Commit any changes from build.sh.
if ! git diff-index --quiet HEAD --; then
    git add -A
    git commit -m "v$VERSION"
fi

# Create and push tag.
if $DRY_RUN; then
    echo -e "${YELLOW}  [DRY-RUN] Would create and push tag $VERSION${NC}"
else
    if git rev-parse "refs/tags/$VERSION" >/dev/null 2>&1; then
        echo -e "${YELLOW}  Tag $VERSION already exists, skipping tag creation.${NC}"
    else
        git tag "$VERSION"
        echo -e "${GREEN}  Tag $VERSION created${NC}"
    fi
    # Disable LFS if it's configured (avoid timeout issues).
    git config lfs.https://github.com/${OWNER}/${REPO_NAME}.git/info/lfs.locksverify false 2>/dev/null || true
    git push
    git push --tags
    echo -e "${GREEN}  Pushed master + tag $VERSION${NC}"
fi

# ── step 2: fork & update channel ───────────────────────────────────────────

CHANNEL_REPO="sublimehq/package_control_channel"
CHANNEL_DIR="/tmp/package_control_channel_$$"

echo
echo -e "${YELLOW}[2/4] Forking $CHANNEL_REPO${NC}"

if $DRY_RUN; then
    echo -e "${YELLOW}  [DRY-RUN] Would fork & clone $CHANNEL_REPO${NC}"
else
    gh repo fork "$CHANNEL_REPO" --clone --remote-name origin "$CHANNEL_DIR" 2>&1 | tail -1
    cd "$CHANNEL_DIR"
    # Add upstream remote for PR targeting.
    git remote add upstream "https://github.com/$CHANNEL_REPO.git" 2>/dev/null || true
fi

# ── step 3: update repository/m.json ────────────────────────────────────────

echo
echo -e "${YELLOW}[3/4] Updating repository/m.json${NC}"

if $DRY_RUN; then
    echo -e "${YELLOW}  [DRY-RUN] Would insert/update MarkdownPreviewPro entry${NC}"
else
    python3 << PYEOF
import json

with open('$CHANNEL_DIR/repository/m.json', 'r') as f:
    data = json.load(f)

packages = data['packages']

# Look for existing entry, or find insertion point.
entry = {
    "name": "MarkdownPreviewPro",
    "details": "https://github.com/$OWNER/$REPO_NAME",
    "homepage": "https://github.com/$OWNER/$REPO_NAME",
    "author": "$OWNER",
    "readme": "https://raw.githubusercontent.com/$OWNER/$REPO_NAME/master/README.md",
    "issues": "https://github.com/$OWNER/$REPO_NAME/issues",
    "labels": ["markdown", "preview", "mermaid", "live preview", "syntax highlighting", "table"],
    "releases": [
        {
            "sublime_text": ">=4107",
            "tags": True
        }
    ]
}

existing_idx = None
for i, p in enumerate(packages):
    if p.get('name') == 'MarkdownPreviewPro':
        existing_idx = i
        break

if existing_idx is not None:
    packages[existing_idx] = entry
    print(f"Updated existing entry at position {existing_idx}")
else:
    # Insert alphabetically.
    insert_at = 0
    for i, p in enumerate(packages):
        if p.get('name', '').lower() >= 'markdownpreviewpro':
            insert_at = i
            break
    else:
        insert_at = len(packages)
    packages.insert(insert_at, entry)
    print(f"Inserted at position {insert_at}")

with open('$CHANNEL_DIR/repository/m.json', 'w') as f:
    json.dump(data, f, indent='\t')
    f.write('\n')
PYEOF
    echo -e "${GREEN}  Done${NC}"
fi

# ── step 4: push fork & create/update PR ────────────────────────────────────

echo
echo -e "${YELLOW}[4/4] Creating PR${NC}"

if $DRY_RUN; then
    echo -e "${YELLOW}  [DRY-RUN] Would push branch and create PR${NC}"
else
    cd "$CHANNEL_DIR"
    BRANCH_NAME="add-markdownpreviewpro"

    # Checkout existing branch or create new.
    if git rev-parse --verify "origin/$BRANCH_NAME" >/dev/null 2>&1; then
        git checkout -b "$BRANCH_NAME" "origin/$BRANCH_NAME"
    else
        git checkout -b "$BRANCH_NAME"
    fi

    git add repository/m.json
    if git diff-index --quiet HEAD --; then
        echo -e "${YELLOW}  No changes to repository/m.json — skipping PR.${NC}"
    else
        git commit -m "Update MarkdownPreviewPro to v$VERSION"

        # Force push the branch (channel repo prefers clean single-commit branches).
        git push -f origin "$BRANCH_NAME"

        # Check if a PR already exists for this branch.
        EXISTING_PR=$(gh pr list \
            --repo "$CHANNEL_REPO" \
            --head "$OWNER:$BRANCH_NAME" \
            --state open \
            --json number \
            --jq '.[0].number' 2>/dev/null || echo "")

        if [ -n "$EXISTING_PR" ]; then
            echo -e "${GREEN}  PR #$EXISTING_PR already exists — updated branch.${NC}"
            echo -e "${GREEN}  PR URL: https://github.com/$CHANNEL_REPO/pull/$EXISTING_PR${NC}"
        else
            PR_URL=$(gh pr create \
                --repo "$CHANNEL_REPO" \
                --head "$OWNER:$BRANCH_NAME" \
                --base master \
                --title "Add MarkdownPreviewPro package (v$VERSION)" \
                --body "## MarkdownPreviewPro v$VERSION

**Repository:** https://github.com/$OWNER/$REPO_NAME
**Tag:** \`$VERSION\`

Live markdown preview in external browser with full HTML+CSS rendering, native table support, mermaid diagrams, and code highlighting.

🤖 Generated with [Claude Code](https://claude.com/claude-code)" 2>&1)
            echo -e "${GREEN}  PR created: $PR_URL${NC}"
        fi
    fi
fi

# ── done ────────────────────────────────────────────────────────────────────

echo
echo -e "${GREEN}=== Release v$VERSION complete! ===${NC}"
if $DRY_RUN; then
    echo -e "${YELLOW}  (Dry run — nothing was actually pushed)${NC}"
fi

# Clean up.
rm -rf "$CHANNEL_DIR"
