"""Code highlighting helpers.

Pygments is wired in via markdown's codehilite extension, so this module only
provides helpers for the bundled highlight stylesheet.
"""
from . import assets as pkg_assets


def highlight_css():
    """Return the highlight stylesheet text (zip-safe)."""
    return pkg_assets.read_text("assets/highlight.css")


def highlight_css_path():
    """Deprecated path helper — zip installs have no real package directory.

    Prefer ``highlight_css()`` or ``html_builder`` inlining. Returns a best-effort
    filesystem path that only works for unpacked installs.
    """
    import os
    from . import PACKAGE_ROOT
    return os.path.join(PACKAGE_ROOT, "assets", "highlight.css")
