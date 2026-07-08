r"""MarkdownPreviewPro — live markdown preview in an external browser.

Press `super+shift+m` to open a browser window.  Press again to close + reopen
(refresh).  The HTML file is opened via ``file://`` URL — no local server, no
port management.

Browser: auto-detected (Chrome / Safari / Firefox / Edge / Brave / Opera).
Chrome-family: AppleScript new-window.  Others: ``open -a``.
"""
import os
import subprocess
import threading
import time
import traceback

import sublime
import sublime_plugin

from .md_renderer import render as render_markdown

PLUGIN_NAME = "MarkdownPreviewPro"

_DEBOUNCE_MS = 500
_MARKDOWN_SCOPE = "text.html.markdown"

_OUT_DIR = os.path.expanduser("~/Downloads/MarkdownPreviewPro")
os.makedirs(_OUT_DIR, exist_ok=True)
_PREVIEW_PATH = os.path.join(_OUT_DIR, "preview.html")
_DEBUG_LOG_PATH = os.path.join(_OUT_DIR, "debug.log")
_LAST_HTML_PATH = os.path.join(_OUT_DIR, "last_html.html")

_preview_open = False
_browser_proc = None
_browser_as_name = None


# ── logging ─────────────────────────────────────────────────────────────────

def _file_log(msg):
    import datetime
    try:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (ts, msg))
    except Exception:
        pass


def _log(msg):
    text = "[MarkdownPreviewPro] %s" % msg
    print(text)
    _file_log(msg)


# ── browser detection ───────────────────────────────────────────────────────

_BROWSER_CANDIDATES = [
    ("com.google.Chrome",       "Google Chrome",  "Google Chrome"),
    ("com.apple.Safari",        "Safari",         None),
    ("org.mozilla.firefox",     "Firefox",        None),
    ("com.microsoft.edgemac",   "Microsoft Edge", "Microsoft Edge"),
    ("com.brave.Browser",       "Brave Browser",  "Brave Browser"),
    ("com.operasoftware.Opera", "Opera",          None),
]


def _detect_browser():
    for _bid, name, as_name in _BROWSER_CANDIDATES:
        try:
            r = subprocess.run(
                ["mdfind", "kMDItemCFBundleIdentifier == '%s'" % _bid],
                capture_output=True, text=True, timeout=3)
            if r.stdout.strip():
                return name, as_name
        except Exception:
            pass
    return None, None


# ── browser open / close ────────────────────────────────────────────────────

def _open_browser(file_url):
    """Open *file_url* in a new browser window."""
    global _browser_proc, _browser_as_name
    name, _browser_as_name = _detect_browser()

    if not name:
        _browser_proc = subprocess.Popen(
            ["open", file_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _log("opened via system default: %s" % file_url)
        return True

    if _browser_as_name:
        try:
            script = (
                'tell application "%s"\n' % _browser_as_name +
                '  make new window\n'
                '  set URL of active tab of front window to "%s"\n' % file_url +
                '  activate\n'
                'end tell'
            )
            _browser_proc = subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _log("%s opened via AppleScript: %s" % (name, file_url))
            return True
        except Exception as e:
            _log("%s AppleScript failed: %s" % (name, e))

    try:
        _browser_proc = subprocess.Popen(
            ["open", "-a", name, file_url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _log("%s opened via open -a: %s" % (name, file_url))
        return True
    except Exception as e:
        _log("open -a %s failed: %s" % (name, e))
        return False


def _close_browser():
    """Close the browser window showing our preview file."""
    global _browser_proc, _browser_as_name
    if _browser_as_name:
        try:
            script = (
                'tell application "%s"\n' % _browser_as_name +
                '  repeat with w in every window\n'
                '    repeat with t in every tab of w\n'
                '      if URL of t starts with "file://%s" then\n' % _PREVIEW_PATH +
                '        close w\n'
                '        exit repeat\n'
                '      end if\n'
                '    end repeat\n'
                '  end repeat\n'
                'end tell'
            )
            subprocess.run(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        except Exception:
            pass
    if _browser_proc is not None:
        try:
            _browser_proc.terminate()
        except Exception:
            pass
        _browser_proc = None
    _log("browser closed")


# ── HTML builder ────────────────────────────────────────────────────────────

def _load_asset(name):
    path = os.path.join(os.path.dirname(__file__), "assets", name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        _log("asset load failed (%s): %s" % (name, e))
        return ""


def _build_html(fragment):
    css = _load_asset("preview.css")
    hl_css = _load_asset("highlight.css")
    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"zh-CN\">\n"
        "<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta http-equiv=\"refresh\" content=\"1\">\n"
        "<style>\n%s\n%s\n</style>\n"
        "</head>\n"
        "<body>\n"
        "<div class='markdown-body'>%s</div>\n"
        "</body>\n"
        "</html>\n"
    ) % (css, hl_css, fragment)


def _write_html_only(html):
    """Write the HTML to disk without opening the browser."""
    try:
        with open(_PREVIEW_PATH, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        _log("write preview.html failed: %s" % e)
    try:
        with open(_LAST_HTML_PATH, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass


def _write_and_open(fragment):
    """Write HTML, then open or refresh browser."""
    global _preview_open

    html = _build_html(fragment)

    # Write debug copies.
    try:
        with open(_PREVIEW_PATH, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        _log("write preview.html failed: %s" % e)
    try:
        with open(_LAST_HTML_PATH, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass

    if not _preview_open:
        file_url = "file://" + _PREVIEW_PATH
        if _open_browser(file_url):
            _preview_open = True
            _log("preview opened")
    # When already open, <meta refresh> picks up the changes.


# ── commands ────────────────────────────────────────────────────────────────

class MarkdownPreviewProToggleCommand(sublime_plugin.WindowCommand):
    def run(self):
        global _preview_open
        if _preview_open:
            # Close + reopen (forces fresh page load).
            _close_browser()
            _preview_open = False

        view = self.window.active_view()
        if view is None:
            _log("no view to preview")
            return
        MarkdownPreviewProListener.render_view(view, force=True)


class MarkdownPreviewProCloseCommand(sublime_plugin.WindowCommand):
    def run(self):
        global _preview_open
        _close_browser()
        _preview_open = False
        _log("preview closed")
        self.window.status_message("MarkdownPreviewPro: preview closed")


class MarkdownPreviewProRefreshCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if view is not None:
            MarkdownPreviewProListener.render_view(view, force=True)


# ── event listener ──────────────────────────────────────────────────────────

class MarkdownPreviewProListener(sublime_plugin.EventListener):
    _timers = {}

    @classmethod
    def render_view(cls, view, force=False):
        global _preview_open
        if view is None:
            return
        if not force and not view.match_selector(0, _MARKDOWN_SCOPE):
            return

        text = view.substr(sublime.Region(0, view.size()))
        mermaid_theme = view.settings().get(
            "markdown_preview_pro.mermaid_theme", "default")

        # Write a "loading" page immediately so the browser opens right away.
        sublime.set_timeout(
            lambda: _write_and_open(
                '<p style="color:#666;text-align:center;padding:40px">'
                'Rendering…</p>'), 0)

        def _work():
            try:
                _log("render: text len=%d" % len(text))
                fragment, errors = render_markdown(
                    text, mermaid_theme=mermaid_theme)
                if errors:
                    _log("render errors: %r" % errors)
            except Exception as e:
                fragment = "<pre>%s</pre>" % _escape(str(e))
                _log("render error:\n%s" % traceback.format_exc())
            sublime.set_timeout(lambda: _write_and_open(fragment), 0)

        threading.Thread(target=_work, daemon=True).start()

    def on_modified_async(self, view):
        global _preview_open
        if not _preview_open:
            return
        try:
            ok_scope = view.match_selector(0, _MARKDOWN_SCOPE)
        except Exception:
            ok_scope = False
        if not ok_scope:
            return
        bid = view.buffer_id()
        timer = self._timers.get(bid)
        if timer:
            timer.cancel()
        timer = threading.Timer(
            _DEBOUNCE_MS / 1000.0, lambda: self.render_view(view))
        self._timers[bid] = timer
        timer.start()


def _escape(s):
    import html as _html
    return _html.escape(s)


def plugin_loaded():
    _log("plugin loaded")
