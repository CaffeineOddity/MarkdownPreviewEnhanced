#!/usr/bin/env python3
"""Regenerate mpe_core/emoji_map.py from the gemoji database.

Source: https://raw.githubusercontent.com/github/gemoji/master/db/emoji.json
GitHub-only mascot aliases (no Unicode character) are omitted.

Usage: python3 scripts/build_emoji_map.py [path-to-emoji.json]
Without an argument the JSON is fetched from the gemoji repo.
"""
import json
import sys
import urllib.request

OUT = "mpe_core/emoji_map.py"
SOURCE_URL = (
    "https://raw.githubusercontent.com/github/gemoji/master/db/emoji.json"
)
# GitHub mascot shortcodes with no Unicode character — not renderable.
GH_MASCOTS = {
    "accessibility", "atom", "basecamp", "basecampy", "bowtie", "copilot",
    "dependabot", "electron", "feelsgood", "finnadie", "fishsticks",
    "goberserk", "godmode", "hurtrealbad", "neckbeard", "octocat", "rage1",
    "rage2", "rage3", "rage4", "shipit", "suspect", "trollface",
}


def load_db():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            return json.load(f)
    print("fetching %s" % SOURCE_URL)
    with urllib.request.urlopen(SOURCE_URL, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    db = load_db()
    alias_map = {}
    for entry in db:
        ch = entry.get("emoji", "")
        if not ch:
            continue
        for alias in entry.get("aliases", []):
            if alias in GH_MASCOTS:
                continue
            if alias in alias_map and alias_map[alias] != ch:
                raise SystemExit("conflicting alias: %s" % alias)
            alias_map[alias] = ch

    lines = [
        '"""GFM emoji shortcode map: alias -> unicode emoji.',
        "",
        "Generated from the gemoji database (MIT, github/gemoji).",
        "GitHub-only mascot aliases without a Unicode character are omitted.",
        "Regenerate with scripts/build_emoji_map.py (see that script).",
        '"""',
        "",
        "# fmt: off",
        "",
        "EMOJI_ALIASES = {",
    ]
    for alias in sorted(alias_map):
        lines.append('    "%s": "%s",' % (alias, alias_map[alias]))
    lines.append("}")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("written %s: %d aliases" % (OUT, len(alias_map)))


if __name__ == "__main__":
    main()
