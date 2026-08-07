"""Resource loading that works for both unpacked Packages/ and zipped
.sublime-package installs.

When a package is installed via Package Control it lives as a zip archive
(``Installed Packages/<Name>.sublime-package``); ordinary ``open()`` on
``__file__``-derived paths cannot reach files inside it. Sublime Text ships
``sublime.load_resource`` / ``load_binary_resource`` which transparently read
from either layout, so every asset read goes through this module.
"""
import os

import sublime

_PKG = "MarkdownPreviewEnhanced"


def _resource_path(rel):
    rel = rel.replace("\\", "/").lstrip("/")
    return "Packages/%s/%s" % (_PKG, rel)


def read_text(rel):
    """Read a UTF-8 text resource, or return '' if missing."""
    try:
        return sublime.load_resource(_resource_path(rel))
    except Exception:
        return ""


def read_bytes(rel):
    """Read a binary resource, or return None if missing."""
    try:
        return sublime.load_binary_resource(_resource_path(rel))
    except Exception:
        return None


def exists(rel):
    return read_bytes(rel) is not None


# KaTeX ships a directory of font files that the browser (and the offline
# export) need to reach by path. For preview mode the HTTP server streams them
# straight from the package resource; for export / the Node SSR worker we
# extract the KaTeX runtime once into the Sublime cache so an external process
# can read them from a real directory.

_KATEX_FILES = (
    "katex.min.js",
    "katex.min.css",
)
_KATEX_FONT_EXTS = (".woff2", ".woff", ".ttf")


def _cache_root():
    base = sublime.cache_path()
    root = os.path.join(base, _PKG, "katex")
    os.makedirs(os.path.join(root, "fonts"), exist_ok=True)
    return root


def extract_katex():
    """Materialise katex.min.js, katex.min.css and its fonts in the cache.

    Returns the directory containing ``katex.min.js`` / ``katex.min.js`` and a
    ``fonts/`` subdirectory, or None if the resources are unavailable.
    Safe to call repeatedly; files are overwritten only if missing.
    """
    root = _cache_root()
    for name in _KATEX_FILES:
        rel = "assets/katex/%s" % name
        dst = os.path.join(root, name)
        if not os.path.isfile(dst) or os.path.getsize(dst) == 0:
            data = read_bytes(rel)
            if data is None:
                return None
            with open(dst, "wb") as f:
                f.write(data)
    # Discover and extract fonts. The font filenames are stable and listed in
    # katex.min.css; enumerate known extensions under assets/katex/fonts via
    # find_resources.
    try:
        found = sublime.find_resources("")  # some builds ignore empty arg
    except Exception:
        found = []
    font_resources = [
        r for r in sublime.find_resources("KaTeX_*")
        if "/%s/assets/katex/fonts/" % _PKG in r
    ]
    for res in font_resources:
        if not res.lower().endswith(_KATEX_FONT_EXTS):
            continue
        fname = res.rsplit("/", 1)[-1]
        dst = os.path.join(root, "fonts", fname)
        if not os.path.isfile(dst) or os.path.getsize(dst) == 0:
            try:
                data = sublime.load_binary_resource(res)
            except Exception:
                continue
            with open(dst, "wb") as f:
                f.write(data)
    return root
