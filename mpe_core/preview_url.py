"""Browser tab interaction: open preview tabs.

URL construction is delegated to ``tab_manager.preview_url`` so there is
a single source of truth for file_path ↔ URL mapping.

Tab focusing:
- ST -> WEB: AppleScript focuses the existing tab by URL (macOS); SSE
  ``switchTab`` is still pushed for JS. Never OS-opens a second tab.
- WEB -> ST: ``notifyDocSwitch`` -> ``/api/open_doc``
- In-page Preview Tabs click uses ``window.open(url, name)`` (user gesture);
  a miss creates a tab that ``tab_open``/``close_old`` takes over.
"""
import threading

from . import config
from . import log
from .browser import BrowserSession
from . import preview_state
from . import tab_manager

_browser = BrowserSession()


def open_preview_browser(url, focus_existing):
    """Open a preview tab. Runs in a background thread.

    Caller must only invoke this when the file has no live tab.
    ``focus_existing`` is accepted for API compatibility.
    """
    preview_state.mark_browser_open()
    preferred = config.get("browser", "auto") or "auto"
    log.debug("browser open: focus_existing=%s url=%s" % (focus_existing, url))

    def _work():
        try:
            ok = _browser.open(
                url,
                preferred=preferred,
                log=preview_state.browser_log,
                focus_existing=focus_existing,
            )
            if not ok:
                log.error("browser open returned False: %s" % url)
        except Exception as e:
            log.error("browser open failed: %s" % e)

    threading.Thread(target=_work, daemon=True).start()
    preview_state.start_scroll_poller()


def focus_preview_tab(file_path):
    """Bring the existing preview tab for *file_path* to the front. No new tab.

    If focusing fails (browser not detected / tab gone), fall back to opening
    a new browser tab so the user always gets a visible preview.
    """
    if not file_path:
        return
    url = tab_manager.preview_url(file_path)
    log.debug("focus existing preview tab: %s" % url)

    def _work():
        try:
            ok = _browser.focus_existing_tab(url, log=preview_state.browser_log)
            if not ok:
                log.info("focus existing tab missed - opening new: %s" % url)
                open_preview_browser(url, focus_existing=False)
        except Exception as e:
            log.error("focus existing tab failed: %s" % e)
            open_preview_browser(url, focus_existing=False)

    threading.Thread(target=_work, daemon=True).start()
