"""Cross-platform browser open / close for MarkdownPreviewEnhanced.

No AppleScript: macOS uses ``open -a``, Windows spawns the browser exe,
Linux uses xdg-open.  Focus/tab-switching between ST and the browser is
done in the browser itself (window.open('', name) via SSE switchTab),
not by driving the browser from the OS.
"""
import os
import subprocess
import sys
import webbrowser

# 用 sys.platform 判断系统,避免 import platform(评审告警);保持 "Darwin"/"Windows"/"Linux" 取值不变
_SYSTEM = {"darwin": "Darwin", "win32": "Windows"}.get(sys.platform, "Linux")


def _startupinfo():
    """Hide the console window when spawning subprocesses on Windows."""
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return si
    return None


_MAC_BROWSER_APPS = [
    ("com.google.Chrome", "Google Chrome"),
    ("com.apple.Safari", "Safari"),
    ("org.mozilla.firefox", "Firefox"),
    ("com.microsoft.edgemac", "Microsoft Edge"),
    ("com.brave.Browser", "Brave Browser"),
    ("com.operasoftware.Opera", "Opera"),
]

_WIN_BROWSER_CMDS = [
    ("chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    ("chrome", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ("msedge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ("msedge", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ("firefox", r"C:\Program Files\Mozilla Firefox\firefox.exe"),
    ("brave", r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"),
]

_LINUX_BROWSERS = [
    "google-chrome",
    "google-chrome-stable",
    "chromium-browser",
    "chromium",
    "firefox",
    "microsoft-edge",
    "brave-browser",
    "opera",
]

_ALIASES = {
    "chrome": ("google chrome", "chrome", "chromium"),
    "safari": ("safari",),
    "firefox": ("firefox",),
    "edge": ("microsoft edge", "msedge", "edge"),
    "brave": ("brave",),
    "opera": ("opera",),
}


def _matches_preferred(preferred, name):
    preferred = (preferred or "auto").lower()
    if preferred in ("auto", "default", ""):
        return True
    name_l = name.lower()
    if preferred in name_l:
        return True
    for alias in _ALIASES.get(preferred, (preferred,)):
        if alias in name_l:
            return True
    return False


def _url_hint(url):
    """Short stable substring used to find an existing preview tab."""
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url.split("://", 1)[-1]
    if url.startswith("file://"):
        return url.replace("file://", "")
    return url


class BrowserSession:
    """Tracks the last opened browser so we can close it."""

    def __init__(self):
        self.proc = None
        self.system = _SYSTEM
        self.last_url = None
        self.app_name = None

    def open(self, url, preferred="auto", log=None, focus_existing=True):
        """Open *url* in the preferred browser.

        ``focus_existing`` is accepted for API compatibility but has no
        OS-level effect - tab reuse/focus is handled in the browser via
        SSE switchTab + window.open('', name).
        """
        self.last_url = url
        log = log or (lambda m: None)
        preferred = (preferred or "auto").lower()

        if preferred == "default":
            return self._open_default(url, log)
        if self.system == "Darwin":
            return self._open_mac(url, preferred, log)
        if self.system == "Windows":
            return self._open_win(url, preferred, log)
        return self._open_linux(url, preferred, log)

    def close(self, preview_file_hint=None, log=None):
        """Best-effort close of the spawned browser process (if any).

        Preview tabs are closed by pushing an SSE 'close' event - the tab
        closes itself (window.close()).  This only cleans up a process we
        spawned ourselves.
        """
        log = log or (lambda m: None)
        if self.proc is not None:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None
            log("closed spawned browser process")

    # ── macOS: open -a (no AppleScript) ────────────────────────────────────

    def _open_mac(self, url, preferred, log):
        app = self._detect_mac_app(preferred)
        if not app:
            return self._open_default(url, log)
        self.app_name = app
        try:
            r = subprocess.run(
                ["open", "-a", app, url],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True, timeout=5)
            if r.returncode == 0:
                log("%s opened via open -a: %s" % (app, url))
                return True
            log("open -a %s failed: %s" % (app, (r.stderr or "")[:200]))
        except Exception as e:
            log("open -a %s failed: %s" % (app, e))
        return self._open_default(url, log)

    def _detect_mac_app(self, preferred):
        """Find an installed browser app that matches *preferred*."""
        if preferred not in ("auto", "default", ""):
            # Preferred name may not match bundle ids; check app display names first.
            for bid, name in _MAC_BROWSER_APPS:
                if _matches_preferred(preferred, name):
                    return name
        # Fall back to any installed browser (mdfind on bundle id).
        for bid, name in _MAC_BROWSER_APPS:
            try:
                r = subprocess.run(
                    ["mdfind", "kMDItemCFBundleIdentifier == '%s'" % bid],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    universal_newlines=True, timeout=3)
                if r.stdout.strip():
                    return name
            except Exception:
                continue
        return None

    # ── default / Windows / Linux ───────────────────────────────────────────

    def _open_default(self, url, log):
        try:
            webbrowser.open(url)
            log("opened via webbrowser: %s" % url)
            return True
        except Exception as e:
            log("webbrowser.open failed: %s" % e)
            return False

    def _open_win(self, url, preferred, log):
        for key, path in _WIN_BROWSER_CMDS:
            if preferred not in ("auto",) and not _matches_preferred(preferred, key):
                continue
            if os.path.isfile(path):
                try:
                    self.proc = subprocess.Popen(
                        [path, url],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        startupinfo=_startupinfo())
                    self.app_name = path
                    log("opened Windows browser %s: %s" % (path, url))
                    return True
                except Exception as e:
                    log("Windows browser failed %s: %s" % (path, e))

        for key, path in _WIN_BROWSER_CMDS:
            if os.path.isfile(path):
                try:
                    self.proc = subprocess.Popen(
                        [path, url],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        startupinfo=_startupinfo())
                    self.app_name = path
                    log("opened Windows browser %s: %s" % (path, url))
                    return True
                except Exception:
                    pass

        try:
            os.startfile(url)  # type: ignore[attr-defined]
            log("opened via os.startfile: %s" % url)
            return True
        except Exception:
            pass
        try:
            self.proc = subprocess.Popen(
                ["cmd", "/c", "start", "", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                startupinfo=_startupinfo())
            log("opened via cmd start: %s" % url)
            return True
        except Exception as e:
            log("cmd start failed: %s" % e)
            return self._open_default(url, log)

    def _open_linux(self, url, preferred, log):
        for name in _LINUX_BROWSERS:
            if preferred not in ("auto",) and not _matches_preferred(preferred, name):
                continue
            try:
                self.proc = subprocess.Popen(
                    [name, url],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    startupinfo=_startupinfo())
                self.app_name = name
                log("opened Linux browser %s: %s" % (name, url))
                return True
            except FileNotFoundError:
                continue
            except Exception as e:
                log("%s failed: %s" % (name, e))

        try:
            self.proc = subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                startupinfo=_startupinfo())
            log("opened via xdg-open: %s" % url)
            return True
        except Exception as e:
            log("xdg-open failed: %s" % e)
            return self._open_default(url, log)


def find_chrome_binary():
    """Locate a Chrome/Chromium executable on this platform."""
    if _SYSTEM == "Darwin":
        for bid, name in _MAC_BROWSER_APPS:
            if "chrome" in name.lower() or "chrom" in name.lower():
                try:
                    r = subprocess.run(
                        ["mdfind", "kMDItemCFBundleIdentifier == '%s'" % bid],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        universal_newlines=True, timeout=3)
                    if r.stdout.strip():
                        return name
                except Exception:
                    continue
        return "Google Chrome"
    if _SYSTEM == "Windows":
        for key, path in _WIN_BROWSER_CMDS:
            if "chrome" in key or "chrom" in path.lower():
                if os.path.isfile(path):
                    return path
        return None
    for name in _LINUX_BROWSERS:
        if "chrome" in name or "chrom" in name:
            try:
                r = subprocess.run(["which", name], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, universal_newlines=True, timeout=3)
                if r.stdout.strip():
                    return name
            except Exception:
                continue
    return None
