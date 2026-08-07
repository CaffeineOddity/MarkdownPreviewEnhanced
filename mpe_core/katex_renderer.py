"""Server-side KaTeX rendering via Node + vendored katex.min.js.

Avoids relying on browser CDN/async load order. Falls back to plain
``.mdpp-math`` markers for client-side render if Node is unavailable.

KaTeX assets live inside the package (possibly a ``.sublime-package`` zip),
so they are materialised into Sublime's cache directory before Node reads them.
"""
import hashlib
import os
import subprocess
import json
import threading

from . import assets as pkg_assets

_CACHE = {}
_CACHE_LOCK = threading.Lock()
_NODE = None
_NODE_CHECKED = False
_PATHS_LOCK = threading.Lock()
_KATEX_JS = None  # set lazily via _ensure_katex_paths()
_HELPER = None


def _find_node():
    global _NODE, _NODE_CHECKED
    if _NODE_CHECKED:
        return _NODE
    _NODE_CHECKED = True
    # Reuse mermaid's discovery when possible
    try:
        from .mermaid_renderer import _find_node as _mmd_find
        path, _dir = _mmd_find()
        if path:
            _NODE = path
            return _NODE
    except Exception:
        pass
    for cand in (
        "node",
        "/opt/homebrew/bin/node",
        "/usr/local/bin/node",
    ):
        try:
            r = subprocess.run(
                [cand, "--version"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=5,
            )
            if r.returncode == 0:
                _NODE = cand
                return _NODE
        except Exception:
            continue
    _NODE = None
    return None


def _ensure_katex_paths():
    """Extract katex.min.js into the cache and return (js_path, helper_path)."""
    global _KATEX_JS, _HELPER
    with _PATHS_LOCK:
        if (
            _KATEX_JS
            and os.path.isfile(_KATEX_JS)
            and _HELPER
            and os.path.isfile(_HELPER)
        ):
            return _KATEX_JS, _HELPER
        root = pkg_assets.extract_katex()
        if not root:
            return None, None
        js = os.path.join(root, "katex.min.js")
        helper = os.path.join(root, "_render_worker.js")
        if not os.path.isfile(js):
            return None, None
        _KATEX_JS = js
        _HELPER = helper
        return _KATEX_JS, _HELPER


def _ensure_helper():
    """Write a tiny Node worker that reads JSON lines and prints HTML."""
    js_path, helper = _ensure_katex_paths()
    if not js_path or not helper:
        return None
    if os.path.isfile(helper) and os.path.getsize(helper) > 50:
        return helper
    src = r"""
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const katexPath = path.join(__dirname, "katex.min.js");
const code = fs.readFileSync(katexPath, "utf8");
const sandbox = { module: { exports: {} }, exports: {}, console };
sandbox.window = sandbox;
sandbox.self = sandbox;
sandbox.global = sandbox;
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const katex = sandbox.katex || sandbox.module.exports || sandbox.exports;
if (!katex || !katex.renderToString) {
  console.error("katex not loaded");
  process.exit(2);
}
const input = fs.readFileSync(0, "utf8");
let jobs;
try { jobs = JSON.parse(input); } catch (e) {
  console.error("bad json", e);
  process.exit(1);
}
const out = [];
for (const job of jobs) {
  try {
    const html = katex.renderToString(job.tex || "", {
      displayMode: !!job.display,
      throwOnError: false,
      strict: "ignore",
      output: "html"
    });
    out.push({ ok: true, html: html });
  } catch (e) {
    out.push({ ok: false, error: String(e && e.message ? e.message : e) });
  }
}
process.stdout.write(JSON.stringify(out));
"""
    try:
        os.makedirs(os.path.dirname(helper), exist_ok=True)
        with open(helper, "w", encoding="utf-8") as f:
            f.write(src.strip() + "\n")
    except Exception as e:
        print("[MarkdownPreviewEnhanced] katex SSR: cannot write helper: %s" % e)
        return None
    return helper


def render_tex_batch(jobs):
    """Render a list of {tex, display} dicts → list of HTML strings or None on hard fail.

    Each result is either rendered HTML (str) or None if that job failed.
    Returns None if Node/KaTeX is completely unavailable.
    """
    if not jobs:
        return []
    node = _find_node()
    if not node:
        # Lazy log once
        if not getattr(render_tex_batch, "_logged_no_node", False):
            print("[MarkdownPreviewEnhanced] katex SSR: node not found on PATH")
            render_tex_batch._logged_no_node = True
        return None
    js_path, _helper_path = _ensure_katex_paths()
    if not js_path:
        if not getattr(render_tex_batch, "_logged_no_js", False):
            print("[MarkdownPreviewEnhanced] katex SSR: katex.min.js unavailable")
            render_tex_batch._logged_no_js = True
        return None

    # Cache lookup
    results = [None] * len(jobs)
    todo_idx = []
    todo_jobs = []
    with _CACHE_LOCK:
        for i, job in enumerate(jobs):
            tex = job.get("tex") or ""
            display = bool(job.get("display"))
            key = hashlib.sha256(
                ("v1|%s|%s" % (display, tex)).encode("utf-8")
            ).hexdigest()
            if key in _CACHE:
                results[i] = _CACHE[key]
            else:
                todo_idx.append(i)
                todo_jobs.append({"tex": tex, "display": display, "key": key})

    if not todo_jobs:
        return results

    helper = _ensure_helper()
    if not helper:
        if not getattr(render_tex_batch, "_logged_no_helper", False):
            print("[MarkdownPreviewEnhanced] katex SSR: helper script unavailable")
            render_tex_batch._logged_no_helper = True
        return None
    try:
        payload = json.dumps(
            [{"tex": j["tex"], "display": j["display"]} for j in todo_jobs],
            ensure_ascii=False,
        )
        env = os.environ.copy()
        # Ensure node can be found by shebang-less call
        r = subprocess.run(
            [node, helper],
            input=payload,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=30,
            env=env,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "")[:300]
            print("[MarkdownPreviewEnhanced] katex SSR node failed: %s" % err)
            return None
        out = json.loads(r.stdout or "[]")
    except Exception as e:
        print("[MarkdownPreviewEnhanced] katex SSR exception: %s" % e)
        return None

    with _CACHE_LOCK:
        for j, item in zip(todo_jobs, out):
            if item.get("ok") and item.get("html"):
                _CACHE[j["key"]] = item["html"]
            else:
                _CACHE[j["key"]] = None  # remember failure as miss for client fallback
        for i, j in zip(todo_idx, todo_jobs):
            results[i] = _CACHE.get(j["key"])

    return results


def render_tex(tex, display=False):
    """Render one formula. Returns HTML string or None."""
    batch = render_tex_batch([{"tex": tex, "display": display}])
    if batch is None:
        return None
    return batch[0]
