"""Assemble full HTML documents for live preview and export.

KaTeX and Mermaid are always served from vendored package assets — never from a CDN.
"""
import os


def _mermaid_js_path():
    path = os.path.join(os.path.dirname(__file__), "assets", "mermaid.min.js")
    if os.path.isfile(path):
        return path
    return None


def _echarts_js_path():
    path = os.path.join(os.path.dirname(__file__), "assets", "echarts.min.js")
    if os.path.isfile(path):
        return path
    return None


def _load_asset(name):
    path = os.path.join(os.path.dirname(__file__), "assets", name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _katex_local_paths():
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "katex")
    css = os.path.join(base, "katex.min.css")
    js = os.path.join(base, "katex.min.js")
    if os.path.isfile(css) and os.path.isfile(js):
        return css, js
    return None, None


def _katex_urls(use_server=True):
    """Return (css_href, js_href) from local package assets only."""
    css_path, js_path = _katex_local_paths()
    if not css_path or not js_path:
        return None, None
    if use_server:
        return "/assets/katex/katex.min.css", "/assets/katex/katex.min.js"
    return "file://" + css_path, "file://" + js_path


def _katex_css_inlined():
    """Inline vendored KaTeX CSS for offline export (no network)."""
    css_path, _ = _katex_local_paths()
    if not css_path:
        return ""
    try:
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()
    except Exception:
        return ""
    # Rewrite relative font URLs so they still resolve next to the CSS file
    # when the stylesheet is inlined into a standalone HTML export.
    fonts_dir = os.path.join(os.path.dirname(css_path), "fonts")
    if os.path.isdir(fonts_dir):
        # Keep url(fonts/...) — export HTML is typically opened near assets,
        # or the user can use preview server. Prefer absolute file:// for fonts.
        base = "file://" + fonts_dir.replace("\\", "/") + "/"
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


def build_preview_shell(
    body_html,
    toc_html="",
    show_toc=True,
    enable_katex=True,
    scroll_sync=True,
    use_server=True,
    custom_css="",
    title="Markdown Preview",
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
    mermaid_path = _mermaid_js_path()
    if mermaid_path:
        if use_server:
            mermaid_tag = '<script src="/assets/mermaid.min.js"></script>\n'
        else:
            mermaid_tag = '<script src="file://%s"></script>\n' % mermaid_path.replace("\\", "/")

    echarts_tag = ""
    echarts_path = _echarts_js_path()
    if echarts_path:
        if use_server:
            echarts_tag = '<script src="/assets/echarts.min.js"></script>\n'
        else:
            echarts_tag = '<script src="file://%s"></script>\n' % echarts_path.replace("\\", "/")

    html2canvas_tag = ""
    if use_server:
        html2canvas_path = os.path.join(os.path.dirname(__file__), "assets", "html2canvas.min.js")
        if os.path.isfile(html2canvas_path):
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
        "<style>\n%s\n%s\n</style>\n"
        "<script>%s</script>\n"
        "</head>\n"
        "<body class=\"%s\" data-mdpp-mode=\"%s\">\n"
        "<div class=\"mdpp-toolbar\">\n"
        "<button id=\"mdpp-export-pdf\" title=\"Export PDF\" onclick=\"mdppExportPdf()\">📄</button>\n"
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
        "if(window.mermaid){mermaid.initialize({theme:'default'});mermaid.run();}"
        "if(window.mdppInit)mdppInit();"
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
    mermaid_path = _mermaid_js_path()
    if mermaid_path:
        try:
            with open(mermaid_path, "r", encoding="utf-8") as f:
                mermaid_tag = "<script>%s</script>\n" % f.read()
        except Exception:
            mermaid_tag = '<script src="file://%s"></script>\n' % mermaid_path.replace("\\", "/")

    echarts_tag = ""
    echarts_path = _echarts_js_path()
    if echarts_path:
        try:
            with open(echarts_path, "r", encoding="utf-8") as f:
                echarts_tag = "<script>%s</script>\n" % f.read()
        except Exception:
            echarts_tag = '<script src="file://%s"></script>\n' % echarts_path.replace("\\", "/")

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
        "<style>\n%s\n%s\n"
        "@media print { "
        "html,body{background:#fff!important;color:#000!important;font-size:13pt!important;line-height:1.6!important} "
        ".mdpp-toc{display:none!important} "
        ".mdpp-wrap{display:block!important;max-width:none!important;padding:0!important} "
        "@page{margin:1.5cm;size:A4} "
        ".markdown-body{max-width:none!important;padding:0!important;margin:0!important} "
        ".markdown-body *{box-shadow:none!important;text-shadow:none!important} "
        ".markdown-body pre,.markdown-body code,.markdown-body .codehilite{white-space:pre-wrap!important;word-break:break-all!important;overflow-wrap:break-word!important;background:#f5f5f5!important;border:1px solid #ccc!important;color:#000!important} "
        ".markdown-body table{display:table!important;width:100%!important;overflow:visible!important} "
        ".markdown-body img,.markdown-body svg{max-width:100%!important;height:auto!important} "
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
