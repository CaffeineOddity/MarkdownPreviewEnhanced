"""Build a reveal.js presentation page from rendered body HTML.

Takes the same body_html that the normal preview uses, splits it on <hr>
(horizontal rule — the Markdown ``---`` slide separator), and wraps each
fragment as a reveal.js <section>.  All assets (reveal.js, reveal.css,
themes) are vendored under ``assets/reveal/`` — no CDN, fully offline.
"""
from . import assets as pkg_assets


_REVEAL_JS = "assets/reveal.min.js"
_REVEAL_CSS = "assets/reveal/reset.css", "assets/reveal/reveal.css"
_THEME_BLACK = "assets/reveal/theme-black.css"
_THEME_WHITE = "assets/reveal/theme-white.css"

# Overrides loaded AFTER reset/reveal/theme so they win the cascade at equal
# specificity. Document style: left-aligned content like the normal preview
# (reveal's default centers everything, and the theme's ``.reveal table {
# margin: auto }`` centers tables — both unwanted here).
_PRESENTATION_CSS = """
/* ── presentation overrides (document style, left-aligned) ────────── */
/* Kill theme quirks that fight the markdown rendering: 42px base with
   uppercase headings, oversized em-based sizes, double-shrunk code, and
   the theme's pre shadow / max-height clip. Typography is pinned in px
   against a fixed 1280x720 slide so proportions stay predictable. */
.reveal {
  --r-main-font-size: 30px;
  --r-main-font: var(--mdpp-font);
  --r-heading-font: var(--mdpp-font);
  --r-code-font: var(--mdpp-mono);
  --r-heading-text-transform: none;
  --r-block-margin: 0.6em;
  font-size: 30px;
  line-height: 1.55;
}
.reveal .slides { text-align: left; }
.reveal .markdown-body {
  background: transparent;
  margin: 0;
  padding: 0;
  max-width: none;
  width: 100%;
  font-size: inherit;
}
.reveal h1 { font-size: 52px; text-transform: none; text-shadow: none; }
.reveal h2 { font-size: 38px; text-transform: none; text-shadow: none; }
.reveal h3 { font-size: 30px; text-transform: none; text-shadow: none; }
.reveal h4, .reveal h5, .reveal h6 { font-size: 28px; }
.reveal .markdown-body h1,
.reveal .markdown-body h2,
.reveal .markdown-body h3,
.reveal .markdown-body h4,
.reveal .markdown-body h5,
.reveal .markdown-body h6,
.reveal .markdown-body p,
.reveal .markdown-body li { text-align: left; }
.reveal .markdown-body code {
  /* inline code only — never shrink block code twice */
  font-size: 0.85em;
}
.reveal .markdown-body :not(pre) > code { font-size: 0.85em; }
.reveal pre {
  display: block;
  width: auto;
  margin: 0.6em 0;
  text-align: left;
  font-size: 20px;
  line-height: 1.5;
  font-weight: normal;
  box-shadow: var(--mdpp-shadow);
}
.reveal pre code {
  padding: 0;
  max-height: none;
  font-size: 100%;
}
.reveal .markdown-body table {
  display: block;
  width: max-content;
  max-width: 100%;
  margin: 0 0 1em;
  overflow: auto;
  font-size: 24px;
}
.reveal .markdown-body th,
.reveal .markdown-body td { padding: 0.45em 0.7em; }
.reveal ul, .reveal ol {
  display: block;
  text-align: left;
  margin: 0 0 0.6em 1.4em;
}
.reveal .markdown-body img {
  border: none;
  box-shadow: none;
  max-width: 90%;
  max-height: 60vh;
}
.reveal .katex-display { font-size: 1em; margin: 0.5em 0; }
.reveal pre.mermaid, .reveal .mermaid-svg { max-width: 90%; margin: 0.5em 0; }
"""


def _load_text(rel):
    return pkg_assets.read_text(rel) or ""


def _available():
    """True if reveal.js core JS + CSS are present in the package."""
    return (
        pkg_assets.exists(_REVEAL_JS)
        and pkg_assets.exists("assets/reveal/reveal.css")
    )


def _split_slides(body_html):
    """Split rendered HTML into slide fragments on <hr> tags.

    Markdown ``---`` (with blank lines around it) becomes ``<hr>``.  We
    split on any ``<hr ...>`` tag, preserving the inner HTML of each
    fragment.
    """
    import re
    # Split on <hr>, <hr/>, <hr />, <hr class="..."> — any variant.
    parts = re.split(r"<hr\s*/?>", body_html, flags=re.IGNORECASE)
    slides = []
    for p in parts:
        stripped = p.strip()
        if stripped:
            slides.append(stripped)
    if not slides:
        slides = [body_html or "<p>No content</p>"]
    return slides


def build_presentation(
    body_html,
    title="Presentation",
    theme="white",
    enable_katex=True,
):
    """Return a full HTML document string for a reveal.js slide deck.

    Parameters
    ----------
    body_html : str
        Already-rendered HTML body (from md_renderer.render).
    title : str
        Browser tab / deck title.
    theme : str
        ``"white"`` (default, good for projectors) or ``"black"``.
    enable_katex : bool
        If True, inject the same KaTeX CSS/JS links the normal preview uses.
    """
    if not _available():
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>reveal.js missing</title></head>"
            "<body style='font-family:sans-serif;padding:40px;color:#333'>"
            "<h2>Presentation mode unavailable</h2>"
            "<p>reveal.js assets are not installed.</p>"
            "</body></html>"
        )

    slides = _split_slides(body_html)

    # Wrap each slide in .markdown-body so the normal preview's content
    # styles (tables, code, quotes, lists …) apply inside reveal slides.
    sections = []
    for s in slides:
        sections.append(
            '<section><div class="markdown-body">%s</div></section>' % s
        )
    slides_html = "\n".join(sections)

    # --- CSS (inlined for a self-contained page) ----------------------
    # Order matters: preview.css first so reveal's reset/theme override the
    # page-level styles (body/html) while .markdown-body content styles win
    # by specificity and keep the markdown rendering (tables, code, …).
    # _PRESENTATION_CSS goes LAST so it beats theme rules (e.g. the theme's
    # ``.reveal table { margin: auto }``) at equal specificity.
    css_parts = [_load_text("assets/preview.css")]
    for rel in _REVEAL_CSS:
        css_parts.append(_load_text(rel))
    if theme == "black":
        css_parts.append(_load_text(_THEME_BLACK))
    else:
        css_parts.append(_load_text(_THEME_WHITE))
    # Highlight CSS from the normal preview so code blocks look the same.
    css_parts.append(_load_text("assets/highlight.css"))
    css_parts.append(_PRESENTATION_CSS)
    inlined_css = "\n".join(css_parts)

    # --- KaTeX (optional, reuse normal preview paths) -----------------
    katex_head = ""
    if enable_katex:
        css_href = "/assets/katex/katex.min.css"
        js_href = "/assets/katex/katex.min.js"
        if pkg_assets.exists("assets/katex/katex.min.css"):
            katex_head = (
                '<link rel="stylesheet" href="%s">\n'
                '  <script src="%s" async onload='
                '"if(window.mdppRenderMathSafe)window.mdppRenderMathSafe();'
                'else if(window.mdppRenderMath)window.mdppRenderMath();"></script>\n'
                % (css_href, js_href)
            )

    # --- reveal.js core JS (inlined) ----------------------------------
    reveal_js = _load_text(_REVEAL_JS)

    # --- KaTeX re-render snippet (same as normal preview) -------------
    from .html_builder import _katex_rerender_snippet
    katex_snippet = _katex_rerender_snippet(enable_katex)

    # --- Mermaid / echarts: load from /assets/ like the normal preview -
    extra_scripts = (
        '<script>(function(){'
        'function when(name,fn){'
        'if(window[name]){fn();return;}'
        'var n=0,t=setInterval(function(){'
        'n+=1;if(window[name]){clearInterval(t);fn();}'
        'else if(n>200){clearInterval(t);}},50);}'
        'when("mermaid",function(){'
        'try{mermaid.initialize({theme:"default",startOnLint:!1});'
        'mermaid.run();}catch(e){console.warn("[MDPP] mermaid",e);}});'
        'var _r=function(){'
        'if(!window.echarts)return;'
        'var el=document.querySelector('
        '".mdpp-echarts:not([data-mdpp-rendered])");'
        'if(!el)return;'
        'var s=el.parentElement.nextElementSibling;'
        'if(!s||!s.classList.contains("mdpp-echarts-config"))return;'
        'try{var opt=JSON.parse(s.textContent.trim());'
        'var ch=echarts.init(el);ch.setOption(opt);'
        'el.setAttribute("data-mdpp-rendered","1");'
        'window.addEventListener("resize",function(){ch.resize();});'
        '}catch(e){console.error("[MDPP] echarts",e);}};'
        'when("echarts",_r);window.mdppRenderEcharts=_r;'
        '})();</script>\n'
    )
    # Load mermaid + echarts from server /assets/ (cached by browser).
    cache_loader = (
        '<script>(function(){'
        'var urls=["/assets/mermaid.min.js","/assets/echarts.min.js"];'
        'function addSrc(u){var s=document.createElement("script");'
        's.src=u;s.async=true;document.head.appendChild(s);}'
        'if(!window.caches){urls.forEach(addSrc);return;}'
        'caches.open("mdpp-static-v1").then(function(c){'
        'urls.forEach(function(u){'
        'c.match(u).then(function(h){'
        'if(h){h.arrayBuffer().then(function(b){'
        'var s=document.createElement("script");s.async=true;'
        's.src=URL.createObjectURL(new Blob([b],'
        '{type:"application/javascript"}));'
        'document.head.appendChild(s);});return;}'
        'fetch(u).then(function(r){c.put(u,r.clone());'
        'r.arrayBuffer().then(function(b){'
        'var s=document.createElement("script");s.async=true;'
        's.src=URL.createObjectURL(new Blob([b],'
        '{type:"application/javascript"}));'
        'document.head.appendChild(s);});});});});});'
        '})();</script>\n'
    )

    html = (
        "<!DOCTYPE html>\n"
        "<html lang='en'>\n"
        "<head>\n"
        "<meta charset='utf-8'>\n"
        "<meta name='viewport' content='width=device-width, initial-scale=1, "
        "maximum-scale=1, user-scalable=no'>\n"
        "<title>%s</title>\n"
        "<style>\n%s\n</style>\n"
        "%s"
        "</head>\n"
        "<body>\n"
        "<div class='reveal'>\n"
        "<div class='slides'>\n"
        "%s\n"
        "</div>\n"
        "</div>\n"
        "<script>%s</script>\n"
        "<script>%s</script>\n"
        "%s"
        "%s"
        "<script>\n"
        "Reveal.initialize({\n"
        "  controls: true,\n"
        "  progress: true,\n"
        "  center: false,\n"
        "  hash: true,\n"
        "  transition: 'slide',\n"
        "  width: 1280,\n"
        "  height: 720,\n"
        "  margin: 0.08,\n"
        "  minScale: 0.2,\n"
        "  maxScale: 2.0,\n"
        "});\n"
        "// Re-render math after each slide is shown.\n"
        "Reveal.on('slidechanged', function() {\n"
        "  if (window.mdppRenderMathSafe) window.mdppRenderMathSafe();\n"
        "  if (window.mdppRenderEcharts) window.mdppRenderEcharts();\n"
        "});\n"
        "if (window.mdppRenderMathSafe) window.mdppRenderMathSafe();\n"
        "</script>\n"
        "</body>\n"
        "</html>\n"
    ) % (
        title,
        inlined_css,
        katex_head,
        slides_html,
        katex_snippet,
        reveal_js,
        cache_loader,
        extra_scripts,
    )
    return html
