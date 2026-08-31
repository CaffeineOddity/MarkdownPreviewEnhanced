"""Markdown rendering pipeline and result publishing.

Takes a Sublime view, renders it to HTML (via ``md_renderer``), builds
the preview shell (via ``html_builder``), pushes the result to the HTTP
server (SSE fan-out) and/or disk, and optionally opens the browser.

This module is the single entry point for "render this view and update
the preview".  It never OS-opens a browser tab — that is Toggle's job
when the file has no live tab.
"""
import os
import threading
import traceback

import sublime

from . import config
from . import log
from . import preview_state
from . import tab_manager
from .html_builder import build_preview_shell
from .md_renderer import render as render_markdown
from .preview_server import (
    has_active_sse_connection,
    set_output_dir,
    update_content,
)

_MARKDOWN_SCOPE = "text.html.markdown"


def _escape(s):
    import html as _html
    return _html.escape(s or "", quote=True)


def view_base_dir(view):
    path = view.file_name() if view else None
    if path:
        return os.path.dirname(path)
    return None


def view_title(view):
    name = view.file_name() if view else None
    if name:
        return os.path.basename(name)
    return "Markdown Preview"


def render_settings():
    return {
        "mermaid_theme": config.get("mermaid_theme", "default") or "default",
        "enable_footnotes": bool(config.get("enable_footnotes", True)),
        "enable_task_lists": bool(config.get("enable_task_lists", True)),
        "enable_toc": bool(config.get("show_toc", True)),
        "strip_yaml": bool(config.get("strip_frontmatter", True)),
        "enable_math": bool(config.get("enable_katex", True)),
        "image_mode": "server" if config.get("use_local_server", True) else "file",
    }


def _write_files(shell_html, body_html):
    preview = config.preview_path()
    last = config.last_html_path()
    try:
        with open(preview, "w", encoding="utf-8") as f:
            f.write(shell_html)
    except Exception as e:
        log.error("write preview.html failed: %s" % e)
    try:
        with open(last, "w", encoding="utf-8") as f:
            f.write(shell_html)
    except Exception:
        pass
    try:
        body_path = os.path.join(config.output_dir(), "body.html")
        with open(body_path, "w", encoding="utf-8") as f:
            f.write(body_html)
    except Exception:
        pass


def publish(result, view, force_open=False):
    """Push rendered result to disk + server and optionally open browser."""
    show_toc = bool(config.get("show_toc", True))
    enable_katex = bool(config.get("enable_katex", True))
    scroll_sync = bool(config.get("scroll_sync", True))
    use_server = bool(config.get("use_local_server", True))
    custom_css = config.get("custom_css", "") or ""
    favicon = config.get("favicon", "") or ""
    title = view_title(view)

    body = result["body_html"]
    toc = result["toc_html"] if show_toc else ""
    content_hash = result["hash"]

    shell = build_preview_shell(
        body,
        toc_html=toc,
        show_toc=show_toc,
        enable_katex=enable_katex,
        scroll_sync=scroll_sync and use_server,
        use_server=use_server,
        custom_css=custom_css,
        title=title,
        favicon=favicon,
    )

    base_dir = view_base_dir(view)
    set_output_dir(config.output_dir())

    raw_md = ""
    try:
        if view is not None:
            raw_md = view.substr(sublime.Region(0, view.size()))
    except Exception:
        pass

    if use_server:
        preview_state.ensure_server()
        channel_key = view.file_name() if view is not None else None
        tab_manager.bind_view(view)
        update_content(
            body_html=body,
            toc_html=toc,
            full_html=shell,
            content_hash=content_hash,
            doc_dir=base_dir,
            shell_html=shell,
            raw_markdown=raw_md,
            export_base_dir=base_dir,
            export_settings={
                "mermaid_theme": config.get("mermaid_theme", "default") or "default",
                "show_toc": False,
                "enable_katex": enable_katex,
                "custom_css": custom_css,
                "title": title,
                "favicon": favicon,
            },
            file_path=channel_key,
        )

    _write_files(shell, body)

    log.debug(
        "content published (force_open=%s preview_open=%s sse=%s)"
        % (force_open, preview_state.is_preview_open(), has_active_sse_connection())
    )


def render_view(view, force=False, open_browser=False, focus_browser=False):
    """Render *view* to HTML and publish to preview.

    This is the single entry point called from commands, event listener,
    and browser-initiated doc switches.
    """
    if view is None:
        return
    if not force and not view.match_selector(0, _MARKDOWN_SCOPE):
        return
    if not force and not preview_state.is_preview_open() and not open_browser:
        return

    text = view.substr(sublime.Region(0, view.size()))
    rs = render_settings()
    base_dir = view_base_dir(view)
    mermaid_theme = view.settings().get(
        "markdown_preview_enhanced.mermaid_theme", rs["mermaid_theme"])

    if open_browser and config.get("use_local_server", True):
        try:
            preview_state.ensure_server()
        except Exception as e:
            log.error("ensure_server failed: %s" % e)

    def _work():
        try:
            log.debug("render: text len=%d base_dir=%s" % (len(text), base_dir))
            result = render_markdown(
                text,
                mermaid_theme=mermaid_theme,
                base_dir=base_dir,
                image_mode=rs["image_mode"],
                enable_footnotes=rs["enable_footnotes"],
                enable_task_lists=rs["enable_task_lists"],
                enable_toc=rs["enable_toc"],
                strip_yaml=rs["strip_yaml"],
                enable_math=rs["enable_math"],
            )
            if result.get("errors"):
                log.error("render errors: %r" % result["errors"])
        except Exception as e:
            result = {
                "body_html": "<pre>%s</pre>" % _escape(str(e)),
                "toc_html": "",
                "hash": "err",
                "errors": [str(e)],
            }
            log.error("render error:\n%s" % traceback.format_exc())

        def _done():
            try:
                publish(result, view, force_open=False)
            except Exception:
                log.error("publish failed:\n%s" % traceback.format_exc())

        sublime.set_timeout(_done, 0)

    threading.Thread(target=_work, daemon=True).start()
