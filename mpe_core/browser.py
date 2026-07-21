"""Cross-platform browser open / close / focus for MarkdownPreviewEnhanced."""
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


# (bundle_id, display_name, applescript_name or None, supports_tab_script)
_MAC_BROWSERS = [
    ("com.google.Chrome", "Google Chrome", "Google Chrome", True),
    ("com.apple.Safari", "Safari", "Safari", True),
    ("org.mozilla.firefox", "Firefox", "Firefox", False),
    ("com.microsoft.edgemac", "Microsoft Edge", "Microsoft Edge", True),
    ("com.brave.Browser", "Brave Browser", "Brave Browser", True),
    ("com.operasoftware.Opera", "Opera", "Opera", False),
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
    # Prefer host:port for http; path for file://
    if url.startswith("http://") or url.startswith("https://"):
        # http://127.0.0.1:8765/ → 127.0.0.1:8765
        rest = url.split("://", 1)[-1]
        return rest.split("/", 1)[0]
    if url.startswith("file://"):
        return url.replace("file://", "")
    return url


class BrowserSession:
    """Tracks the last opened browser so we can focus or close it."""

    def __init__(self):
        self.proc = None
        self.as_name = None
        self.supports_tab_script = False
        self.system = _SYSTEM
        self.last_url = None
        self.app_name = None

    def open(self, url, preferred="auto", log=None, focus_existing=True):
        """Open *url*, or focus an existing tab that already shows it."""
        self.last_url = url
        log = log or (lambda m: None)
        preferred = (preferred or "auto").lower()

        if preferred == "default":
            return self._open_default(url, log)

        if self.system == "Darwin":
            return self._open_mac(url, preferred, log, focus_existing=focus_existing)
        if self.system == "Windows":
            return self._open_win(url, preferred, log)
        return self._open_linux(url, preferred, log)

    def focus(self, url=None, log=None):
        """Bring the preview browser tab to the front if we can find it."""
        log = log or (lambda m: None)
        url = url or self.last_url
        if not url:
            log("focus: no url")
            return False
        if self.system == "Darwin":
            return self._focus_mac(url, log)
        # Best-effort: re-open URL (browsers usually reuse/focus the tab)
        preferred = "auto"
        if self.app_name:
            preferred = self.app_name
        return self.open(url, preferred=preferred, log=log, focus_existing=True)

    def close(self, preview_file_hint=None, log=None):
        log = log or (lambda m: None)
        hint = preview_file_hint or _url_hint(self.last_url)
        if not hint:
            log("close: no hint available")
            return
        if self.system == "Darwin":
            hint = str(hint).replace("\\", "/").replace('"', "")
            # Collect unique AppleScript names, self.as_name first
            as_names = []
            if self.as_name:
                as_names.append(self.as_name)
            for _bid, _name, an, _tab in _MAC_BROWSERS:
                if an and an not in as_names:
                    as_names.append(an)
            for an in as_names:
                try:
                    if an == "Safari":
                        script = self._safari_close_script(hint)
                    else:
                        script = self._chrome_close_script(an, hint)
                    subprocess.run(
                        ["osascript", "-e", script],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                except Exception:
                    pass
        if self.proc is not None:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None

    # ── macOS ───────────────────────────────────────────────────────────────

    def _run_osascript(self, script, log, label):
        try:
            r = subprocess.run(
                ["osascript", "-e", script],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=8)
            if r.returncode != 0:
                err = (r.stderr or r.stdout or "").strip()
                log("%s AppleScript failed (%s): %s" % (label, r.returncode, err[:300]))
                return False
            return True
        except Exception as e:
            log("%s AppleScript error: %s" % (label, e))
            return False

    def _chrome_focus_or_open_script(self, app, url, hint):
        # Chromium-family: find tab by URL substring, else open tab / window.
        return (
            'tell application "%s"\n' % app +
            '  set targetURL to "%s"\n' % url +
            '  set hint to "%s"\n' % hint +
            "  set found to false\n"
            "  if (count of windows) > 0 then\n"
            "    repeat with w in windows\n"
            "      set tabIndex to 0\n"
            "      repeat with t in tabs of w\n"
            "        set tabIndex to tabIndex + 1\n"
            "        try\n"
            "          set u to URL of t\n"
            "          if u contains hint then\n"
            "            set active tab index of w to tabIndex\n"
            "            set index of w to 1\n"
            "            set found to true\n"
            "            exit repeat\n"
            "          end if\n"
            "        end try\n"
            "      end repeat\n"
            "      if found then exit repeat\n"
            "    end repeat\n"
            "  end if\n"
            "  if not found then\n"
            "    if (count of windows) = 0 then\n"
            "      make new window\n"
            "      set URL of active tab of front window to targetURL\n"
            "    else\n"
            "      tell front window to make new tab with properties {URL:targetURL}\n"
            "    end if\n"
            "  end if\n"
            "  activate\n"
            "end tell"
        )

    def _safari_focus_or_open_script(self, url, hint):
        return (
            'tell application "Safari"\n'
            '  set targetURL to "%s"\n' % url +
            '  set hint to "%s"\n' % hint +
            "  set found to false\n"
            "  if (count of windows) > 0 then\n"
            "    repeat with w in windows\n"
            "      repeat with t in tabs of w\n"
            "        try\n"
            "          set u to URL of t\n"
            "          if u contains hint then\n"
            "            set current tab of w to t\n"
            "            set index of w to 1\n"
            "            set found to true\n"
            "            exit repeat\n"
            "          end if\n"
            "        end try\n"
            "      end repeat\n"
            "      if found then exit repeat\n"
            "    end repeat\n"
            "  end if\n"
            "  if not found then\n"
            "    open location targetURL\n"
            "  end if\n"
            "  activate\n"
            "end tell"
        )

    def _chrome_close_script(self, app, hint):
        return (
            'tell application "%s"\n' % app +
            "  repeat with w in every window\n"
            "    repeat with t in every tab of w\n"
            "      try\n"
            "        set u to URL of t\n"
            '        if u contains "%s" then\n' % hint +
            "          close t\n"
            "          return\n"
            "        end if\n"
            "      end try\n"
            "    end repeat\n"
            "  end repeat\n"
            "end tell"
        )

    def _safari_close_script(self, hint):
        return (
            'tell application "Safari"\n'
            "  repeat with w in every window\n"
            "    repeat with t in every tab of w\n"
            "      try\n"
            "        set u to URL of t\n"
            '        if u contains "%s" then\n' % hint +
            "          close t\n"
            "          return\n"
            "        end if\n"
            "      end try\n"
            "    end repeat\n"
            "  end repeat\n"
            "end tell"
        )

    def _open_mac(self, url, preferred, log, focus_existing=True):
        name, as_name, tab_ok = self._detect_mac(preferred)
        self.as_name = as_name
        self.app_name = name
        self.supports_tab_script = tab_ok

        if not name:
            return self._open_default(url, log)

        hint = _url_hint(url).replace('"', "")
        url_safe = url.replace('"', "%22")

        if as_name and tab_ok and focus_existing:
            if as_name == "Safari":
                script = self._safari_focus_or_open_script(url_safe, hint)
            else:
                script = self._chrome_focus_or_open_script(as_name, url_safe, hint)
            if self._run_osascript(script, log, name):
                log("%s focus/open: %s" % (name, url))
                return True

        if as_name and not focus_existing:
            # Force a fresh load in a new tab
            if as_name == "Safari":
                script = (
                    'tell application "Safari"\n'
                    '  open location "%s"\n' % url_safe +
                    "  activate\n"
                    "end tell"
                )
            else:
                script = (
                    'tell application "%s"\n' % as_name +
                    "  if (count of windows) = 0 then\n"
                    "    make new window\n"
                    '    set URL of active tab of front window to "%s"\n' % url_safe +
                    "  else\n"
                    '    tell front window to make new tab with properties {URL:"%s"}\n' % url_safe +
                    "  end if\n"
                    "  activate\n"
                    "end tell"
                )
            if self._run_osascript(script, log, name):
                log("%s opened: %s" % (name, url))
                return True

        try:
            r = subprocess.run(
                ["open", "-a", name, url],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=5)
            if r.returncode == 0:
                log("%s opened via open -a: %s" % (name, url))
                return True
            log("open -a %s failed: %s" % (name, (r.stderr or "")[:200]))
        except Exception as e:
            log("open -a %s failed: %s" % (name, e))
        return self._open_default(url, log)

    def _focus_mac(self, url, log):
        name, as_name, tab_ok = self._detect_mac("auto")
        if self.as_name:
            as_name = self.as_name
            name = self.app_name or name
            tab_ok = self.supports_tab_script or tab_ok
        if not as_name or not tab_ok:
            # Fallback: open (often focuses existing)
            return self._open_mac(url, "auto", log, focus_existing=True)

        hint = _url_hint(url).replace('"', "")
        url_safe = url.replace('"', "%22")
        if as_name == "Safari":
            script = self._safari_focus_or_open_script(url_safe, hint)
        else:
            script = self._chrome_focus_or_open_script(as_name, url_safe, hint)
        ok = self._run_osascript(script, log, name or as_name)
        if ok:
            log("%s focused: %s" % (name or as_name, url))
        return ok

    def _detect_mac(self, preferred):
        found = []
        for bid, name, as_name, tab_ok in _MAC_BROWSERS:
            try:
                r = subprocess.run(
                    ["mdfind", "kMDItemCFBundleIdentifier == '%s'" % bid],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=3)
                if r.stdout.strip():
                    found.append((name, as_name, tab_ok))
            except Exception:
                pass
        if not found:
            return None, None, False
        for name, as_name, tab_ok in found:
            if _matches_preferred(preferred, name):
                return name, as_name, tab_ok
        return found[0]

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
    """Locate a Chrome/Chromium binary for headless PDF export."""
    if _SYSTEM == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ]
    elif _SYSTEM == "Windows":
        candidates = [p for _, p in _WIN_BROWSER_CMDS]
    else:
        candidates = [
            "google-chrome",
            "google-chrome-stable",
            "chromium-browser",
            "chromium",
            "microsoft-edge",
            "brave-browser",
        ]
    for c in candidates:
        if os.path.sep in c or (len(c) > 1 and c[1] == ":"):
            if os.path.isfile(c):
                return c
        else:
            try:
                r = subprocess.run(
                    ["which", c], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=3)
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip()
            except Exception:
                pass
    return None
