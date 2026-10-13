"""Read a bitmap image from the OS clipboard as PNG bytes.

Used by "Paste as Markdown" to save a system screenshot to ``media/`` and
insert a relative ``![](…)`` link. Returns ``None`` when the clipboard holds
no image or when no platform tool is available, so the caller silently falls
back to the existing HTML→markdown path.

- macOS: ``osascript 'the clipboard as «class PNGf»'`` (hex-encoded PNG).
- Windows: PowerShell wraps ``System.Windows.Forms.Clipboard::GetImage()`` and
  saves a PNG to a temp file which is read back.
- Linux: ``xclip -selection clipboard -t image/png -o`` (X11) or
  ``wl-paste --type image/png`` (Wayland).
"""
import binascii
import os
import re
import subprocess
import sys
import tempfile

_OSA_PNGF_RE = re.compile(r"«data PNGf([0-9A-Fa-f]+)»")
_MAX_IMAGE_BYTES = 30 * 1024 * 1024


def read_clipboard_image():
    """Return PNG bytes from the clipboard, or ``None``."""
    if sys.platform == "darwin":
        return _read_macos()
    if sys.platform == "win32":
        return _read_windows()
    return _read_linux()


def _run(argv, stdin_bytes=None, timeout=15):
    try:
        return subprocess.run(
            argv,
            input=stdin_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _png_or_none(raw):
    if not raw or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    if len(raw) > _MAX_IMAGE_BYTES:
        return None
    return raw


def _read_macos():
    r = _run(["osascript", "-e", "the clipboard as «class PNGf»"])
    if r is None or r.returncode != 0:
        return None
    m = _OSA_PNGF_RE.search((r.stdout or b"").decode("utf-8", "replace"))
    if not m:
        return None
    try:
        return _png_or_none(binascii.unhexlify(m.group(1)))
    except (binascii.Error, ValueError):
        return None


def _read_windows():
    fd, tmp = tempfile.mkstemp(suffix=".png", prefix="mdpp_clip_")
    os.close(fd)
    try:
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "Add-Type -AssemblyName System.Drawing;"
            "$img = [System.Windows.Forms.Clipboard]::GetImage();"
            "if ($img) { $img.Save('%s', [System.Drawing.Imaging.ImageFormat]::Png) }"
            % tmp.replace("'", "''")
        )
        r = _run(["powershell", "-NoProfile", "-Command", script], timeout=20)
        if r is None or r.returncode != 0 or not os.path.isfile(tmp):
            return None
        with open(tmp, "rb") as f:
            return _png_or_none(f.read())
    except (OSError, IOError):
        return None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _read_linux():
    # try xclip (X11) then wl-paste (Wayland)
    r = _run(["xclip", "-selection", "clipboard", "-t", "image/png", "-o"])
    if r is not None and r.returncode == 0:
        return _png_or_none(r.stdout)
    r = _run(["wl-paste", "--type", "image/png"])
    if r is not None and r.returncode == 0:
        return _png_or_none(r.stdout)
    return None