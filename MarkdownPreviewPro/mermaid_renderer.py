"""Mermaid → SVG rendering via mermaid-cli (mmdc).

Strategy:
  1. Locate a usable `node` binary. Sublime Text (launched from the Dock/Finder)
     does NOT inherit the user's login-shell PATH, so `npx`/`node` resolved via
     `#!/usr/bin/env node` fail with "env: node: No such file or directory".
     We probe known locations (nvm, homebrew, /usr/local/bin) and fall back to
     the system PATH, then pass an explicit PATH/env to the subprocess.
  2. Locate the `mmdc` CLI. We prefer the npx-cached copy
     (~/.npm/_npx/<hash>/node_modules/.bin/mmdc) so we don't re-trigger an
     npx download on every render. If absent, we run `npx mmdc` (which still
     needs our resolved node on PATH).

Uses a hash-keyed cache to avoid re-running mmdc for unchanged diagrams.
Falls back gracefully when node/mmdc is unavailable.
"""
import hashlib
import os
import re
import subprocess
import tempfile

try:
    import sublime  # noqa: F401  (ensures this module is treated as a 3.8 plugin)
except Exception:
    sublime = None  # allow import outside ST (tests / standalone verification)

# Cache directory under the user's Packages/User folder (set lazily).
_CACHE_DIR = None
_SVG_SEQ = 0


def _cache_dir():
    global _CACHE_DIR
    if _CACHE_DIR is None:
        if sublime is not None:
            base = sublime.cache_path()
        else:
            base = os.path.join(os.path.expanduser("~"), ".cache")
        cache = os.path.join(base, "MarkdownPreviewPro", "mermaid")
        os.makedirs(cache, exist_ok=True)
        _CACHE_DIR = cache
    return _CACHE_DIR


# --- node / mmdc discovery -------------------------------------------------

def _candidate_node_paths():
    """Yield absolute paths to candidate `node` binaries, best first."""
    seen = set()
    home = os.path.expanduser("~")

    # 1. nvm versions (newest first)
    nvm_dir = os.path.join(home, ".nvm", "versions", "node")
    if os.path.isdir(nvm_dir):
        try:
            for name in sorted(os.listdir(nvm_dir), reverse=True):
                p = os.path.join(nvm_dir, name, "bin", "node")
                if os.path.isfile(p) and p not in seen:
                    seen.add(p)
                    yield p
        except OSError:
            pass

    # 2. homebrew (Apple Silicon then Intel)
    for base in ("/opt/homebrew/bin/node", "/usr/local/bin/node"):
        if os.path.isfile(base) and base not in seen:
            seen.add(base)
            yield base
    # homebrew cellar nodes
    for cellar in ("/opt/homebrew/Cellar/node", "/usr/local/Cellar/node"):
        if os.path.isdir(cellar):
            try:
                for name in sorted(os.listdir(cellar), reverse=True):
                    p = os.path.join(cellar, name, "bin", "node")
                    if os.path.isfile(p) and p not in seen:
                        seen.add(p)
                        yield p
            except OSError:
                pass

    # 3. whatever `which node` finds on the current (possibly login) PATH
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d:
            continue
        p = os.path.join(d, "node")
        if os.path.isfile(p) and p not in seen:
            seen.add(p)
            yield p


def _find_node():
    """Return (node_path, node_dir) for the first working node binary, or (None, None)."""
    for p in _candidate_node_paths():
        try:
            r = subprocess.run(
                [p, "--version"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=10,
            )
            if r.returncode == 0 and r.stdout.strip():
                return p, os.path.dirname(p)
        except Exception:
            continue
    return None, None


def _find_mmdc():
    """Return the absolute path to a usable mmdc CLI script, or None.

    Prefer the npx cache so we avoid a download on every render.
    """
    home = os.path.expanduser("~")
    npx_cache = os.path.join(home, ".npm", "_npx")
    if os.path.isdir(npx_cache):
        try:
            for entry in os.listdir(npx_cache):
                cand = os.path.join(
                    npx_cache, entry, "node_modules",
                    "@mermaid-js", "mermaid-cli", "src", "cli.js",
                )
                if os.path.isfile(cand):
                    return cand
        except OSError:
            pass
    return None


_NODE_CACHE = None  # (node_path, node_dir) or None


def _resolve_node():
    global _NODE_CACHE
    if _NODE_CACHE is None:
        _NODE_CACHE = _find_node()  # may be (None, None)
    return _NODE_CACHE


def render_mermaid(code, theme="default"):
    """Render a mermaid diagram to an SVG string.

    Returns (svg, error). On success error is None.
    """
    key = hashlib.sha256(("v2|%s|%s" % (theme, code)).encode("utf-8")).hexdigest()
    cache_file = os.path.join(_cache_dir(), key + ".svg")

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return f.read(), None
        except Exception:
            pass

    # Write the mermaid source to a temp file.
    fd, src_path = tempfile.mkstemp(suffix=".mmd")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code)

        node_path, node_dir = _resolve_node()
        mmdc_path = _find_mmdc()

        if node_path is None:
            return None, ("mermaid: node not found (install Node.js or add it "
                          "to PATH). Looked in nvm/homebrew/PATH.")
        if mmdc_path is None:
            return None, ("mermaid: mermaid-cli not found. Run "
                          "`npx -p @mermaid-js/mermaid-cli mmdc -V` once to "
                          "cache it, then retry.")

        # Invoke mmdc's cli.js directly with our explicit node binary. This
        # avoids the `#!/usr/bin/env node` shebang, which fails in Sublime's
        # GUI-launched environment (node not on PATH there).
        cmd = [
            node_path, mmdc_path,
            "-i", src_path,
            "-o", "-",            # SVG to stdout
            "-t", theme,
            "-b", "transparent",
            "--quiet",
        ]
        # Build a clean environment: system paths + the node dir so mmdc's
        # child processes (puppeteer/chromium) can find node if needed.
        run_env = dict(os.environ)
        run_env["PATH"] = os.pathsep.join(
            [p for p in [node_dir, "/usr/local/bin", "/usr/bin", "/bin",
                         run_env.get("PATH", "")] if p]
        )
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=90,
                env=run_env,
            )
        except FileNotFoundError:
            return None, "mermaid: node binary vanished between resolve and run"
        except subprocess.TimeoutExpired:
            return None, "mermaid-cli timed out (>90s)"

        if proc.returncode != 0:
            msg = proc.stderr.decode("utf-8", "replace").strip() or "mermaid-cli failed"
            return None, "mermaid: " + msg[:200]

        svg = proc.stdout.decode("utf-8", "replace")
        if not svg.strip():
            return None, "mermaid: empty output"

        # Sublime's minihtml does not render <foreignObject> (which mermaid
        # uses for node labels). Strip the foreignObject blocks and pull the
        # plain text out so labels still appear as inline SVG text.
        svg = _simplify_svg(svg)

        # Cache it.
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(svg)
        except Exception:
            pass

        return svg, None
    finally:
        try:
            os.remove(src_path)
        except Exception:
            pass


# --- SVG id unique-ification ─────────────────────────────────────────────────
# Mermaid-cli hard-codes id="my-svg" and an internal #my-svg stylesheet.
# Multiple diagrams on one page would collide — we rename them.
# No longer strips <foreignObject> — we now render in a full browser which
# supports it natively.

def _simplify_svg(svg):
    """Make the root SVG id unique so multiple diagrams don't collide.

    No longer strips <foreignObject> — we now render in a full browser which
    supports it natively (unlike minihtml).  """
    if 'id="my-svg"' not in svg:
        return svg

    # Give each diagram a distinct SVG id (mermaid-cli hard-codes id="my-svg"
    # and uses #my-svg in an internal <style>, so collisions break styling).
    global _SVG_SEQ
    _SVG_SEQ += 1
    new_id = "mdpp-svg-%d" % _SVG_SEQ
    svg = svg.replace('id="my-svg"', 'id="%s"' % new_id, 1)
    svg = svg.replace("#my-svg", "#" + new_id)
    return svg

