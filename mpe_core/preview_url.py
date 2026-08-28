"""Browser tab interaction: open preview tabs.

URL construction is delegated to ``tab_manager.preview_url`` so there is
a single source of truth for file_path ↔ URL mapping.

Tab focusing between ST and the browser is handled in the browser itself:
- ST -> WEB: SSE ``switchTab`` -> matching tab calls ``window.open('', name)``
- WEB -> ST: ``notifyDocSwitch`` -> ``/api/open_doc``
No OS-level browser scripting (AppleScript) is used - cross-platform.
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

    ``focus_existing`` is accepted for API compatibility; tab reuse is
    handled in the browser (stable URL + window.name) not via OS scripting.
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
