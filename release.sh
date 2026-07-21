#!/bin/bash
set -euo pipefail

# release.sh - tag a release & open/update the Package Control channel PR.
#
# Usage:
#   ./release.sh <version>          e.g.  ./release.sh 0.1.0
#   ./release.sh <version> --dry-run
#
# Channel entry is minimal (details + releases only). GitHub metadata supplies
# homepage / author / readme / issues. The channel file is updated surgically
# so the rest of repository/m.json is not reformatted.

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

VERSION="${1:-}"
DRY_RUN=false
if [ $# -ge 2 ] && [ "$2" = "--dry-run" ]; then
    DRY_RUN=true
fi

if [ -z "$VERSION" ]; then
    echo -e "${RED}Usage: $0 <version> [--dry-run]${NC}"
    exit 1
fi

if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+'; then
    echo -e "${YELLOW}Warning: '$VERSION' does not look like semver (x.y.z). Continue? [y/N]${NC}"
    read -r ans
    [ "$ans" = "y" ] || [ "$ans" = "Y" ] || exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

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

REMOTE_URL=$(git remote get-url origin)
OWNER_REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github.com[:/]([^/]+/[^/.]+)(\.git)?$|\1|')
OWNER="${OWNER_REPO%%/*}"
REPO_NAME="${OWNER_REPO##*/}"

PKG_NAME="MarkdownPreviewEnhanced"

echo -e "${GREEN}=== Releasing $REPO_NAME v$VERSION ===${NC}"
echo "  owner: $OWNER"
echo "  package: $PKG_NAME"
echo

echo -e "${YELLOW}[1/4] Building & tagging${NC}"

if [ -x build.sh ]; then
    ./build.sh
fi

if $DRY_RUN; then
    echo -e "${YELLOW}  [DRY-RUN] Would create and push tag $VERSION${NC}"
else
    if git rev-parse "refs/tags/$VERSION" >/dev/null 2>&1; then
        echo -e "${YELLOW}  Tag $VERSION already exists, skipping tag creation.${NC}"
    else
        git tag "$VERSION"
        echo -e "${GREEN}  Tag $VERSION created${NC}"
    fi
    git push
    git push --tags
    echo -e "${GREEN}  Pushed master + tag $VERSION${NC}"
fi

CHANNEL_REPO="sublimehq/package_control_channel"
CHANNEL_DIR="/tmp/package_control_channel_$$"

echo
echo -e "${YELLOW}[2/4] Forking $CHANNEL_REPO${NC}"

if $DRY_RUN; then
    echo -e "${YELLOW}  [DRY-RUN] Would fork & clone $CHANNEL_REPO${NC}"
else
    gh repo fork "$CHANNEL_REPO" --clone --remote-name origin "$CHANNEL_DIR" 2>&1 | tail -1
    cd "$CHANNEL_DIR"
    git remote add upstream "https://github.com/$CHANNEL_REPO.git" 2>/dev/null || true
fi

echo
echo -e "${YELLOW}[3/4] Updating repository/m.json (surgical, no full reformat)${NC}"

if $DRY_RUN; then
    echo -e "${YELLOW}  [DRY-RUN] Would upsert minimal $PKG_NAME entry${NC}"
else
    python3 << PYEOF
import re
import sys

path = "$CHANNEL_DIR/repository/m.json"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# 最小入口:details + labels + releases。name 可由 details 推导,省略(评审要求)。
# 用真实 tab 的三引号串构造,缩进对齐 repository/m.json(包对象 { 在 2 tab,键 3 tab)。
# entry[1:] 去掉三引号开头的换行。
entry = """
		{
			"details": "https://github.com/$OWNER/$REPO_NAME",
			"labels": ["markdown", "preview", "mermaid", "live preview", "syntax highlighting"],
			"releases": [
				{
					"sublime_text": ">=4107",
					"tags": true
				}
			]
		}"""
entry = entry[1:]

# 包名 = details URL 末段(repo 名),用于字母序定位与去重。
PKG_LOWER = "markdownpreviewenhanced"

# 按 details URL 匹配已有入口(m.json 入口不含 name),命中则就地替换,保持其余文件不变。
pattern = re.compile(
    r'\{\s*"details"\s*:\s*"https?://[^/]+/[^/]+/MarkdownPreviewEnhanced(?:\.git)?"'
    r'[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
    re.DOTALL,
)

if pattern.search(text):
    new_text, n = pattern.subn(entry, text, count=1)
    if n != 1:
        print("ERROR: expected exactly one MarkdownPreviewEnhanced entry", file=sys.stderr)
        sys.exit(1)
    print("Updated existing MarkdownPreviewEnhanced entry")
else:
    # 按包名字母序插入:找第一个 repo 名 >= 本包的入口,插在它所在行行首之前,
    # 保证插入入口与后续入口的前导缩进(2 tab)一致。
    insert_at = None
    for m in re.finditer(r'\{\s*"details"\s*:\s*"https?://[^/]+/[^/]+/([^/"]+?)(?:\.git)?"', text):
        if m.group(1).lower() >= PKG_LOWER:
            insert_at = text.rfind("\n", 0, m.start()) + 1
            break

    if insert_at is None:
        # 末尾追加:在 packages 数组闭合 \n\t] 前插入,并保证前一入口有尾逗号。
        idx = text.rfind("\n\t]")
        if idx < 0:
            print("ERROR: cannot find end of packages array", file=sys.stderr)
            sys.exit(1)
        before = text[:idx].rstrip()
        if not before.endswith(","):
            before += ","
        new_text = before + "\n" + entry + text[idx:]
    else:
        new_text = text[:insert_at] + entry + ",\n" + text[insert_at:]
    print("Inserted MarkdownPreviewEnhanced entry")

with open(path, "w", encoding="utf-8", newline="\n") as f:
    f.write(new_text)
print("Wrote", path)
PYEOF
    echo -e "${GREEN}  Done${NC}"
fi

echo
echo -e "${YELLOW}[4/4] Creating PR${NC}"

if $DRY_RUN; then
    echo -e "${YELLOW}  [DRY-RUN] Would push branch and create PR${NC}"
else
    cd "$CHANNEL_DIR"
    BRANCH_NAME="add-markdownpreviewenhanced"

    if git rev-parse --verify "origin/$BRANCH_NAME" >/dev/null 2>&1; then
        git checkout -b "$BRANCH_NAME" "origin/$BRANCH_NAME"
    else
        git checkout -b "$BRANCH_NAME"
    fi

    git add repository/m.json
    if git diff-index --quiet HEAD --; then
        echo -e "${YELLOW}  No changes to repository/m.json - skipping PR.${NC}"
    else
        git commit -m "Update MarkdownPreviewEnhanced package entry"

        git push -f origin "$BRANCH_NAME"

        EXISTING_PR=$(gh pr list \
            --repo "$CHANNEL_REPO" \
            --head "$OWNER:$BRANCH_NAME" \
            --state open \
            --json number \
            --jq '.[0].number' 2>/dev/null || echo "")

        if [ -n "$EXISTING_PR" ]; then
            echo -e "${GREEN}  PR #$EXISTING_PR already exists - updated branch.${NC}"
            echo -e "${GREEN}  PR URL: https://github.com/$CHANNEL_REPO/pull/$EXISTING_PR${NC}"
        else
            # PR body 严格遵循 package_control_channel 的 PR 模板(含勾选框),否则不予评审。
            BODY_FILE="$CHANNEL_DIR/.pr_body.md"
            cat > "$BODY_FILE" <<BODYEOF
- [x] I'm the package's author and/or maintainer.
- [x] I have read [the docs](https://docs.sublimetext.io/guide/package-control/submitting.html).
- [x] I have tagged a release with a [semver](https://semver.org) version number.
- [x] My package repo has a description and a README describing what it's for and how to use it.
- [x] My package doesn't add context menu entries. *
- [x] My package doesn't add key bindings. **
- [x] Any commands are available via the command palette.
- [x] Preferences and keybindings (if any) are listed in the menu and the command palette, and open in split view.
- [x] If my package is a syntax it doesn't also add a color scheme. ***
- [x] I use [.gitattributes](https://www.git-scm.com/docs/gitattributes#_export_ignore) to exclude files from the package: images, test files, sublime-project/workspace.

## MarkdownPreviewEnhanced v$VERSION

**Repository:** https://github.com/$OWNER/$REPO_NAME
**Tag:** \`$VERSION\`

Live markdown preview in an external browser with full HTML/CSS, tables, Mermaid, KaTeX, and ECharts. Mirrors the editing buffer in real time; the preview updates on every save.

My package is similar to MarkdownPreview and MarkdownLivePreview. However it should still be added because it renders in an external browser with full HTML/CSS support and rich diagram/math libraries (Mermaid, KaTeX, ECharts), none of which the existing packages provide.
BODYEOF
            PR_URL=$(gh pr create \
                --repo "$CHANNEL_REPO" \
                --head "$OWNER:$BRANCH_NAME" \
                --base master \
                --title "Add MarkdownPreviewEnhanced package (v$VERSION)" \
                --body-file "$BODY_FILE" 2>&1)
            echo -e "${GREEN}  PR created: $PR_URL${NC}"
        fi
    fi
fi

echo
echo -e "${GREEN}=== Release v$VERSION complete! ===${NC}"
if $DRY_RUN; then
    echo -e "${YELLOW}  (Dry run - nothing was actually pushed)${NC}"
fi

rm -rf "$CHANNEL_DIR"
