"""Export rendered markdown to standalone HTML, PDF, or PNG."""
import os
import subprocess
import tempfile

from .browser import find_chrome_binary
from .html_builder import build_export_html
from .md_renderer import render as render_markdown, rewrite_image_srcs


def _render_standalone(text, base_dir, mermaid_theme, show_toc, enable_katex,
                       custom_css, title, log, favicon):
    """Shared helper: render markdown and build standalone export HTML."""
    result = render_markdown(
        text,
        mermaid_theme=mermaid_theme,
        base_dir=base_dir,
        image_mode="file",
        enable_toc=show_toc,
    )
    body = result["body_html"]
    toc = result["toc_html"] if show_toc else ""
    if base_dir:
        body = rewrite_image_srcs(body, base_dir, mode="file")
    html = build_export_html(
        body,
        toc_html=toc,
        show_toc=show_toc and bool(toc),
        enable_katex=enable_katex,
        custom_css=custom_css,
        title=title,
        favicon=favicon,
    )
    return html, result.get("errors") or []


def export_html(
    text,
    dest_path,
    base_dir=None,
    mermaid_theme="default",
    show_toc=True,
    enable_katex=True,
    custom_css="",
    title="Markdown Export",
    log=None,
    favicon="",
):
    log = log or (lambda m: None)
    html, errors = _render_standalone(
        text, base_dir, mermaid_theme, show_toc, enable_katex,
        custom_css, title, log, favicon,
    )
    dest_path = os.path.expanduser(dest_path)
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(html)
    log("exported HTML → %s" % dest_path)
    return dest_path, errors


def export_pdf(
    text,
    dest_path,
    base_dir=None,
    mermaid_theme="default",
    show_toc=False,
    enable_katex=True,
    custom_css="",
    title="Markdown Export",
    log=None,
    favicon="",
):
    """Render via headless Chrome/Chromium --print-to-pdf."""
    log = log or (lambda m: None)
    chrome = find_chrome_binary()
    if not chrome:
        raise RuntimeError(
            "No Chrome/Chromium/Edge found for PDF export. "
            "Install Chrome or export HTML and print manually."
        )

    html, _errors = _render_standalone(
        text, base_dir, mermaid_theme, show_toc, enable_katex,
        custom_css, title, log, favicon,
    )

    fd, tmp_html = tempfile.mkstemp(suffix=".html", prefix="mdpp_export_")
    os.close(fd)
    try:
        with open(tmp_html, "w", encoding="utf-8") as f:
            f.write(html)
        dest_path = os.path.expanduser(dest_path)
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        url = "file://" + tmp_html
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--virtual-time-budget=10000",
            "--run-all-compositor-stages-before-draw",
            "--print-to-pdf=" + dest_path,
            url,
        ]
        r = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        if r.returncode != 0 or not os.path.isfile(dest_path):
            err = (r.stderr or b"").decode("utf-8", errors="replace")[:500]
            raise RuntimeError("PDF export failed: %s" % (err or "unknown"))
        log("exported PDF → %s" % dest_path)
        return dest_path
    finally:
        try:
            os.unlink(tmp_html)
        except Exception:
            pass


def export_png(
    text,
    dest_path,
    base_dir=None,
    mermaid_theme="default",
    show_toc=False,
    enable_katex=True,
    custom_css="",
    title="Markdown Export",
    log=None,
    favicon="",
):
    """Render via headless Chrome/Chromium --screenshot."""
    log = log or (lambda m: None)
    chrome = find_chrome_binary()
    if not chrome:
        raise RuntimeError(
            "No Chrome/Chromium/Edge found for PNG export. "
            "Install Chrome or use a different browser."
        )

    html, _errors = _render_standalone(
        text, base_dir, mermaid_theme, show_toc, enable_katex,
        custom_css, title, log, favicon,
    )

    fd, tmp_html = tempfile.mkstemp(suffix=".html", prefix="mdpp_export_")
    os.close(fd)
    try:
        with open(tmp_html, "w", encoding="utf-8") as f:
            f.write(html)
        dest_path = os.path.expanduser(dest_path)
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        url = "file://" + tmp_html
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--window-size=1200,900",
            "--virtual-time-budget=10000",
            "--run-all-compositor-stages-before-draw",
            "--screenshot=" + dest_path,
            url,
        ]
        r = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        if r.returncode != 0 or not os.path.isfile(dest_path):
            err = (r.stderr or b"").decode("utf-8", errors="replace")[:500]
            raise RuntimeError("PNG export failed: %s" % (err or "unknown"))
        log("exported PNG → %s" % dest_path)
        return dest_path
    finally:
        try:
            os.unlink(tmp_html)
        except Exception:
            pass
