"""Assemble full HTML documents for live preview and export.

KaTeX and Mermaid are always served from vendored package assets — never from a CDN.
"""
import base64
import os

from . import assets as pkg_assets

_ICON_MIME = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _asset_exists(name):
    return pkg_assets.exists("assets/" + name)


def _load_asset(name):
    """Read a text asset from the package (works for zip and unpacked installs)."""
    return pkg_assets.read_text("assets/" + name)


def _katex_available():
    return (
        pkg_assets.exists("assets/katex/katex.min.css")
        and pkg_assets.exists("assets/katex/katex.min.js")
    )


def _katex_urls(use_server=True):
    """Return (css_href, js_href) from local package assets only."""
    if not _katex_available():
        return None, None
    if use_server:
        return "/assets/katex/katex.min.css", "/assets/katex/katex.min.js"
    # Offline / file:// export: materialise KaTeX into the cache so the
    # browser can resolve real disk paths (zip installs have no PACKAGE_ROOT dir).
    root = pkg_assets.extract_katex()
    if not root:
        return None, None
    css = os.path.join(root, "katex.min.css").replace("\\", "/")
    js = os.path.join(root, "katex.min.js").replace("\\", "/")
    return "file://" + css, "file://" + js


def _katex_css_inlined():
    """Inline vendored KaTeX CSS for offline export (no network)."""
    css = pkg_assets.read_text("assets/katex/katex.min.css")
    if not css:
        return ""
    # Rewrite relative font URLs to absolute file:// paths under the extracted
    # cache directory so standalone HTML export still finds the font files.
    root = pkg_assets.extract_katex()
    if root:
        fonts_dir = os.path.join(root, "fonts").replace("\\", "/")
        base = "file://" + fonts_dir + "/"
        css = css.replace("url(fonts/", "url(" + base)
        css = css.replace("url('fonts/", "url('" + base)
        css = css.replace('url("fonts/', 'url("' + base)
    return css


def _katex_head(enabled, use_server=True, inline_css=False):
    """Load local KaTeX CSS/JS only. No CDN fallbacks."""
    if not enabled:
        return ""

    parts = []
    if inline_css:
        inlined = _katex_css_inlined()
        if inlined:
            parts.append("<style id=\"mdpp-katex-css\">\n%s\n</style>\n" % inlined)
    else:
        css_href, js_href = _katex_urls(use_server=use_server)
        if css_href:
            parts.append(
                '  <link id="mdpp-katex-css" rel="stylesheet" href="%s">\n' % css_href
            )
        else:
            # Last resort: inline if link path missing
            inlined = _katex_css_inlined()
            if inlined:
                parts.append("<style id=\"mdpp-katex-css\">\n%s\n</style>\n" % inlined)

    # Client-side fallback render only loads local JS (SSR covers most cases).
    css_href, js_href = _katex_urls(use_server=use_server)
    if js_href:
        parts.append(
            '  <script src="%s"\n'
            '    onload="if(window.mdppRenderMathSafe)window.mdppRenderMathSafe();'
            'else if(window.mdppRenderMath)window.mdppRenderMath();"></script>\n'
            % js_href
        )
    return "".join(parts)


def _katex_rerender_snippet(enabled):
    """JS: render remaining .mdpp-math nodes with katex.render (idempotent + retry)."""
    if not enabled:
        return (
            "window.mdppRenderMath=function(){return true;};"
            "window.mdppRenderMathSafe=function(){};"
        )
    return r"""
window.mdppRenderMath = function mdppRenderMath() {
  if (!window.katex || typeof window.katex.render !== "function") {
    return false;
  }
  var nodes = document.querySelectorAll(".mdpp-math:not([data-mdpp-rendered])");
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    var tex = el.getAttribute("data-tex");
    if (tex == null || tex === "") {
      tex = (el.textContent || "").replace(/^\s+|\s+$/g, "");
    }
    if (!tex) {
      el.setAttribute("data-mdpp-rendered", "1");
      continue;
    }
    var display = el.getAttribute("data-display") === "true";
    try {
      el.textContent = "";
      window.katex.render(tex, el, {
        displayMode: display,
        throwOnError: false,
        strict: "ignore",
        output: "html"
      });
      el.setAttribute("data-mdpp-rendered", "1");
    } catch (e) {
      el.textContent = tex;
      el.setAttribute("data-mdpp-rendered", "err");
      el.setAttribute("title", String(e && e.message ? e.message : e));
      console.warn("[MDPP] katex.render failed:", tex, e);
    }
  }
  return true;
};
window.mdppRenderMathSafe = function mdppRenderMathSafe() {
  if (window.mdppRenderMath && window.mdppRenderMath()) return;
  if (window.mdppRenderMathSafe._timer) return;
  var n = 0;
  window.mdppRenderMathSafe._timer = setInterval(function () {
    n += 1;
    if ((window.mdppRenderMath && window.mdppRenderMath()) || n > 80) {
      clearInterval(window.mdppRenderMathSafe._timer);
      window.mdppRenderMathSafe._timer = null;
    }
  }, 100);
};
""".strip()


def _svg_data_uri(svg_text):
    raw = (svg_text or "").encode("utf-8")
    return "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")


def _file_data_uri(path):
    """把本地图标文件读成 data URI.文件不存在则返回空串."""
    if not path or not os.path.isfile(path):
        return "", ""
    ext = os.path.splitext(path)[1].lower()
    mime = _ICON_MIME.get(ext, "application/octet-stream")
    with open(path, "rb") as f:
        data = f.read()
    href = "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii"))
    return href, mime


def _favicon_tag(favicon, use_server):
    """生成 <link rel="icon">.空值用包内默认图标;`none` 禁用."""
    raw = (favicon or "").strip()
    if raw.lower() == "none":
        return ""

    href = ""
    mime = ""
    lowered = raw.lower()
    if lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("data:"):
        href = raw
    elif raw:
        try:
            href, mime = _file_data_uri(os.path.expanduser(raw))
        except OSError:
            return ""
        if not href:
            return ""
    elif use_server:
        href = "/assets/favicon.svg"
        mime = "image/svg+xml"
    else:
        svg = _load_asset("favicon.svg")
        if not svg:
            return ""
        href = _svg_data_uri(svg)
        mime = "image/svg+xml"

    type_attr = (' type="%s"' % mime) if mime else ""
    return '  <link rel="icon" href="%s"%s>\n' % (_escape_html(href), type_attr)


def build_preview_shell(
    body_html,
    toc_html="",
    show_toc=True,
    enable_katex=True,
    scroll_sync=True,
    use_server=True,
    custom_css="",
    title="Markdown Preview",
    favicon="",
):
    """Build the stable shell page (polls /api/content when use_server)."""
    css = _load_asset("preview.css")
    hl_css = _load_asset("highlight.css")
    js = _load_asset("preview.js")
    if custom_css:
        try:
            with open(os.path.expanduser(custom_css), "r", encoding="utf-8") as f:
                css = css + "\n" + f.read()
        except Exception:
            pass

    toc_block = ""
    layout_class = "mdpp-layout"
    if show_toc and toc_html:
        toc_block = (
            '<aside id="mdpp-toc" class="mdpp-toc" aria-label="Table of contents">%s</aside>'
            % toc_html
        )
        layout_class += " mdpp-has-toc"
    elif show_toc:
        toc_block = (
            '<aside id="mdpp-toc" class="mdpp-toc mdpp-toc-empty" '
            'aria-label="Table of contents"></aside>'
        )
        layout_class += " mdpp-has-toc"

    mode = "server" if use_server else "file"
    config_js = (
        "window.MDPP_CONFIG=%s;" % _json({
            "mode": mode,
            "scrollSync": bool(scroll_sync),
            "showToc": bool(show_toc),
            "katex": bool(enable_katex),
        })
    )

    mermaid_tag = ""
    if _asset_exists("mermaid.min.js"):
        if use_server:
            mermaid_tag = '<script src="/assets/mermaid.min.js"></script>\n'
        else:
            # Offline: inline so zip installs don't need a disk path.
            src = _load_asset("mermaid.min.js")
            if src:
                mermaid_tag = "<script>%s</script>\n" % src

    echarts_tag = ""
    if _asset_exists("echarts.min.js"):
        if use_server:
            echarts_tag = '<script src="/assets/echarts.min.js"></script>\n'
        else:
            src = _load_asset("echarts.min.js")
            if src:
                echarts_tag = "<script>%s</script>\n" % src

    html2canvas_tag = ""
    if use_server and _asset_exists("html2canvas.min.js"):
        html2canvas_tag = '<script src="/assets/html2canvas.min.js"></script>\n'

    meta_refresh = ""
    if not use_server:
        meta_refresh = '<meta http-equiv="refresh" content="2">\n'

    return (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        "<meta charset=\"utf-8\">\n"
        "%s"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>%s</title>\n"
        "%s"
        "%s"
        "<style>\n%s\n%s\n</style>\n"
        "<script>%s</script>\n"
        "</head>\n"
        "<body class=\"%s\" data-mdpp-mode=\"%s\">\n"
        "<div class=\"mdpp-toolbar\">\n"
        "<button id=\"mdpp-export-png\" title=\"Export PNG\" onclick=\"mdppExportPng()\">🖼️</button>\n"
        "<button id=\"mdpp-export-html\" title=\"Export HTML\" onclick=\"mdppExportHtml()\">💾</button>\n"
        "</div>\n"
        "<div class=\"mdpp-wrap\">\n"
        "%s\n"
        "<main id=\"mdpp-content\" class=\"markdown-body\">%s</main>\n"
        "</div>\n"
        "%s"
        "%s"
        "%s"
        "<script>%s</script>\n"
        "<script>%s</script>\n"
        "<script>%s</script>\n"
        "</body>\n"
        "</html>\n"
    ) % (
        meta_refresh,
        _escape_html(title),
        _favicon_tag(favicon, use_server),
        _katex_head(enable_katex, use_server=use_server, inline_css=False),
        css,
        hl_css,
        config_js,
        layout_class,
        mode,
        toc_block,
        body_html,
        mermaid_tag,
        echarts_tag,
        html2canvas_tag,
        _katex_rerender_snippet(enable_katex),
        js,
        "document.addEventListener('DOMContentLoaded',function(){"
        "if(window.mdppInit)mdppInit();"
        "try{if(window.mermaid){mermaid.initialize({theme:'default'});mermaid.run();}}"
        "catch(e){console.warn('[MDPP] mermaid init',e);}"
        "if(window.mdppRenderMathSafe)mdppRenderMathSafe();"
        "var _mdppRenderEcharts=function(){"
        "var el=document.querySelector('.mdpp-echarts:not([data-mdpp-rendered])');"
        "if(!el)return;"
        "var s=el.parentElement.nextElementSibling;"
        "if(!s||!s.classList.contains('mdpp-echarts-config'))return;"
        "try{var txt=s.textContent.trim();var opt=JSON.parse(txt);"
        "var ch=echarts.init(el);ch.setOption(opt);"
        "el.setAttribute('data-mdpp-rendered','1');"
        "window.addEventListener('resize',function(){ch.resize();});"
        "}catch(e){console.error('[MDPP] echarts error',e);}"
        "};"
        "_mdppRenderEcharts();"
        "window.mdppRenderEcharts=_mdppRenderEcharts;"
        "});",
    )


def build_export_html(
    body_html,
    toc_html="",
    show_toc=True,
    enable_katex=True,
    custom_css="",
    title="Markdown Export",
    favicon="",
):
    """Standalone HTML. KaTeX CSS is inlined from vendored assets (no CDN)."""
    css = _load_asset("preview.css")
    hl_css = _load_asset("highlight.css")
    if custom_css:
        try:
            with open(os.path.expanduser(custom_css), "r", encoding="utf-8") as f:
                css = css + "\n" + f.read()
        except Exception:
            pass

    mermaid_tag = ""
    mermaid_src = _load_asset("mermaid.min.js")
    if mermaid_src:
        mermaid_tag = "<script>%s</script>\n" % mermaid_src

    echarts_tag = ""
    echarts_src = _load_asset("echarts.min.js")
    if echarts_src:
        echarts_tag = "<script>%s</script>\n" % echarts_src

    toc_block = ""
    layout_class = "mdpp-layout mdpp-export"
    if show_toc and toc_html:
        toc_block = (
            '<aside class="mdpp-toc" aria-label="Table of contents">%s</aside>'
            % toc_html
        )
        layout_class += " mdpp-has-toc"

    return (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>%s</title>\n"
        "%s"
        "%s"
        "<style>\n%s\n%s\n"
        "@media print { "
        "html,body{background:#fff!important;color:#000!important;font-size:13pt!important;line-height:1.6!important} "
        ".mdpp-toc{display:none!important} "
        ".mdpp-wrap{display:block!important;max-width:none!important;padding:0!important} "
        "@page{margin:1.5cm;size:A4} "
        ".markdown-body{max-width:none!important;padding:0!important;margin:0!important} "
        ".markdown-body *{box-shadow:none!important;text-shadow:none!important} "
        ".markdown-body pre,.markdown-body code,.markdown-body .codehilite{white-space:pre-wrap!important;word-break:break-all!important;overflow-wrap:break-word!important;background:#f5f5f5!important;border:1px solid #ccc!important;color:#000!important} "
        ".markdown-body table{display:table!important;width:100%%!important;overflow:visible!important} "
        ".markdown-body img,.markdown-body svg{max-width:100%%!important;height:auto!important} "
        ".markdown-body a{color:#000!important} "
        "}\n"
        "</style>\n"
        "</head>\n"
        "<body class=\"%s\">\n"
        "<div class=\"mdpp-wrap\">\n"
        "%s\n"
        "<main class=\"markdown-body\">%s</main>\n"
        "</div>\n"
        "%s"
        "%s"
        "<script>%s</script>\n"
        "<script>"
        "document.addEventListener('DOMContentLoaded',function(){"
        "if(window.mermaid){mermaid.initialize({theme:'default'});mermaid.run();}"
        "if(window.mdppRenderMathSafe)mdppRenderMathSafe();"
        "var _mdppRenderEcharts=function(){"
        "var el=document.querySelector('.mdpp-echarts:not([data-mdpp-rendered])');"
        "if(!el)return;"
        "var s=el.parentElement.nextElementSibling;"
        "if(!s||!s.classList.contains('mdpp-echarts-config'))return;"
        "try{var txt=s.textContent.trim();var opt=JSON.parse(txt);"
        "var ch=echarts.init(el);ch.setOption(opt);"
        "el.setAttribute('data-mdpp-rendered','1');"
        "window.addEventListener('resize',function(){ch.resize();});"
        "}catch(e){console.error('[MDPP] echarts error',e);}"
        "};"
        "_mdppRenderEcharts();"
        "window.mdppRenderEcharts=_mdppRenderEcharts;"
        "});"
        "</script>\n"
        "</body>\n"
        "</html>\n"
    ) % (
        _escape_html(title),
        _favicon_tag(favicon, False),
        _katex_head(enable_katex, use_server=False, inline_css=True),
        css,
        hl_css,
        layout_class,
        toc_block,
        body_html,
        mermaid_tag,
        echarts_tag,
        _katex_rerender_snippet(enable_katex),
    )


def _json(obj):
    import json
    return json.dumps(obj, ensure_ascii=False)


def _escape_html(s):
    import html as _html
    return _html.escape(s or "")
