"""Settings helpers for MarkdownPreviewEnhanced."""
import os

import sublime

_SETTINGS_FILE = "MarkdownPreviewEnhanced.sublime-settings"
_DEFAULT_OUT = os.path.expanduser("~/Downloads/MarkdownPreviewEnhanced")


def settings():
    return sublime.load_settings(_SETTINGS_FILE)


def get(key, default=None):
    return settings().get(key, default)


def output_dir():
    """Return the preview/export output directory (created if needed)."""
    raw = get("output_dir", "") or ""
    raw = str(raw).strip()
    if not raw:
        # Prefer Sublime cache when available; fall back to Downloads.
        try:
            base = sublime.cache_path()
            path = os.path.join(base, "MarkdownPreviewEnhanced")
        except Exception:
            path = _DEFAULT_OUT
    else:
        path = os.path.expanduser(raw)
    os.makedirs(path, exist_ok=True)
    return path


def export_default_path(file_name, ext):
    """Suggested path for Export PDF/HTML input panel.

    ``export_dir`` (export-only; does not affect preview ``output_dir``):
    - ``""``: ``output_dir() / <basename><ext>``
    - ``"beside_source"``: same directory as the saved markdown file
    - any other non-empty string: ``expanduser(path) / <basename><ext>``

    Untitled / unsaved views (no ``file_name``) use ``export.<ext>`` and fall
    back to ``output_dir`` when ``export_dir`` is empty or ``beside_source``.
    """
    if file_name:
        base = os.path.splitext(os.path.basename(file_name))[0]
        name = base + ext
    else:
        name = "export" + ext
    raw = str(get("export_dir", "") or "").strip()
    if raw == "beside_source":
        if file_name:
            return os.path.join(os.path.dirname(file_name), name)
        return os.path.join(output_dir(), name)
    if raw:
        return os.path.join(os.path.expanduser(raw), name)
    return os.path.join(output_dir(), name)


def preview_path():
    return os.path.join(output_dir(), "preview.html")


def debug_log_path():
    return os.path.join(output_dir(), "debug.log")


def last_html_path():
    return os.path.join(output_dir(), "last_html.html")


def media_cache_dir():
    path = os.path.join(output_dir(), "media")
    os.makedirs(path, exist_ok=True)
    return path
