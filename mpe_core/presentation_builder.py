"""Build a presentation (slide deck) page using the normal preview's own
markdown rendering — no third-party framework.

Slides are the already-rendered body_html split at every h1–h4 heading:
each heading opens a new slide, and the content under it stays on that
slide.  Each slide is a plain ``.markdown-body`` page shown full screen,
one at a time.  Tables, code blocks, quotes, KaTeX, mermaid and echarts
render *identically* to the live preview because the very same
preview.css is inlined here.
"""
import re

from . import assets as pkg_assets
from .html_builder import _katex_rerender_snippet


# Full-screen deck chrome: one .mdpp-slide per viewport, a thin progress
# bar, prev/next HUD, and two invisible edge click-zones.  Inactive slides
# are visibility:hidden (not display:none) so mermaid/KaTeX can measure
# layout while hidden and render at correct size on first visit.
_DECK_CSS = """
/* ── deck shell: fixed 16:9 canvas scaled to fit, like reveal.js ─────── */
/* Every slide is a fixed 1280x720 canvas; JS computes a uniform
   transform:scale() so the canvas always fits the viewport and is
   centered on the stage. Content never changes slide geometry. */
:root { --mdpp-slide-w: 1600px; --mdpp-slide-h: 100vh; }
html, body {
  margin: 0;
  padding: 0;
  height: 100%;
  overflow: hidden;
  background: #000;
  color: var(--mdpp-fg);
  font-family: var(--mdpp-font);
}
.mdpp-slide {
  position: fixed;
  top: 0;
  left: 0;
  width: var(--mdpp-slide-w);
  height: var(--mdpp-slide-h);
  visibility: hidden;
  transform-origin: top left;
  /* JS sets transform: scale(s) — s = vw/W so width always fills */
  overflow: hidden;                 /* clip at canvas boundary */
}
.mdpp-slide.active { visibility: visible; }
.mdpp-slide > .markdown-body {
  box-sizing: border-box;
  width: 100%;
  max-width: none;                 /* override preview.css 820px cap */
  height: 100%;
  padding: 48px 64px;
  font-size: 20px;
  line-height: 1.6;
  text-align: left;
  background: var(--mdpp-bg);
  border: none;
  border-radius: 0;
  box-shadow: none;
  overflow-y: auto;                 /* scroll inside the fixed canvas */
  scrollbar-width: none;            /* Firefox: hide scrollbar */
}
.mdpp-slide > .markdown-body::-webkit-scrollbar {
  width: 0; height: 0; display: none;  /* Chrome/Safari: hide scrollbar */
}
/* first heading of each slide gets some breathing room back */
.mdpp-slide > .markdown-body > :first-child { margin-top: 0 !important; }

/* ── chrome: progress bar + HUD + click zones ────────────────────────── */
#mdpp-progress {
  position: fixed;
  left: 0;
  bottom: 0;
  height: 3px;
  width: 0;
  background: var(--mdpp-accent);
  transition: width 0.15s ease;
  z-index: 51;
}
.mdpp-hud {
  position: fixed;
  right: 16px;
  bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  font: 13px/1 var(--mdpp-font);
  color: var(--mdpp-muted);
  z-index: 50;
  user-select: none;
}
.mdpp-hud button {
  border: 1px solid var(--mdpp-border);
  background: var(--mdpp-surface);
  border-radius: 6px;
  min-width: 30px;
  height: 27px;
  cursor: pointer;
  font: inherit;
  color: inherit;
}
.mdpp-hud button:hover { background: var(--mdpp-surface-2); }
.mdpp-click {
  position: fixed;
  top: 0;
  bottom: 44px;
  width: 22%;
  z-index: 40;
  cursor: pointer;
}
.mdpp-click-l { left: 0; cursor: w-resize; }
.mdpp-click-r { right: 0; cursor: e-resize; }
@media print {
  :root { --mdpp-slide-w: auto; --mdpp-slide-h: auto; }
  html, body { height: auto; overflow: visible; background: #fff; }
  #mdpp-progress, .mdpp-hud, .mdpp-click { display: none !important; }
  .mdpp-slide {
    position: static;
    width: auto;
    height: auto;
    transform: none !important;
    visibility: visible;
    page-break-after: always;
  }
  .mdpp-slide > .markdown-body {
    width: auto;
    height: auto;
    overflow: visible;
    border: none;
    border-radius: 0;
    box-shadow: none;
    padding: 20px;
    font-size: 11pt;
  }
}
"""

# Vanilla-JS deck controller (~1.4 KB, no dependencies).
_DECK_JS = r"""
(function () {
  var slides = Array.prototype.slice.call(
    document.querySelectorAll(".mdpp-slide"));
  if (!slides.length) return;
  var bar = document.getElementById("mdpp-progress");
  var cur = document.getElementById("mdpp-cur");
  var h = parseInt(location.hash.replace("#", ""), 10);
  var idx = isNaN(h) ? 0 : Math.max(0, Math.min(slides.length - 1, h - 1));

  /* Fill the entire viewport width. The slide height tracks the
     viewport so overflow-y scrolling inside .markdown-body always
     reaches the bottom — no content trapped below the fold by a
     fixed 900px canvas scaled beyond the screen. */
  var W = 1600;
  function fit() {
    var vw = window.innerWidth, vh = window.innerHeight;
    var s = vw / W;
    s = Math.max(0.1, Math.min(s, 3));
    for (var k = 0; k < slides.length; k++) {
      slides[k].style.transform = "scale(" + s + ")";
      slides[k].style.height = vh + "px";
    }
  }
  window.addEventListener("resize", fit);

  function go(n) {
    idx = Math.max(0, Math.min(slides.length - 1, n));
    for (var k = 0; k < slides.length; k++) {
      slides[k].classList.toggle("active", k === idx);
    }
    cur.textContent = String(idx + 1);
    bar.style.width = (((idx + 1) / slides.length) * 100) + "%";
    if (slides[idx]) slides[idx].scrollTop = 0;
    try { history.replaceState(null, "", "#" + (idx + 1)); } catch (e) {}
    if (window.mdppRenderMathSafe) window.mdppRenderMathSafe();
    if (window.mdppRenderEcharts) window.mdppRenderEcharts();
  }
  function next() { go(idx + 1); }
  function prev() { go(idx - 1); }

  document.getElementById("mdpp-next").addEventListener("click", next);
  document.getElementById("mdpp-prev").addEventListener("click", prev);
  document.querySelector(".mdpp-click-r").addEventListener("click", next);
  document.querySelector(".mdpp-click-l").addEventListener("click", prev);

  document.addEventListener("keydown", function (e) {
    var tag = e.target && e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA") return;
    switch (e.key) {
      case "ArrowRight":
      case "ArrowDown":
      case "PageDown":
      case " ":
        next(); e.preventDefault(); break;
      case "ArrowLeft":
      case "ArrowUp":
      case "PageUp":
        prev(); e.preventDefault(); break;
      case "Home": go(0); e.preventDefault(); break;
      case "End": go(slides.length - 1); e.preventDefault(); break;
      case "f": case "F":
        if (document.fullscreenElement) { document.exitFullscreen(); }
        else if (document.documentElement.requestFullscreen) {
          document.documentElement.requestFullscreen();
        }
        e.preventDefault(); break;
      default: break;
    }
  });

  document.getElementById("mdpp-total").textContent = String(slides.length);
  fit();
  go(idx);
})();
"""


def _split_slides(body_html):
    """Split rendered HTML into slides at every heading (h1–h4).

    Each ``<h1>``…``<h4>`` opens a new slide; everything up to the next
    heading belongs to that slide.  Content before the first heading
    becomes its own opening slide.  A document without headings renders
    as a single slide.  Markdown ``---`` still shows as a plain rule
    inside a slide — it no longer breaks pages.
    """
    chunks = re.split(
        r"(?i)(<h[1-4](?:\s[^>]*)?>)", body_html)
    slides = []
    # Leading content before the first heading (title blurb, lists …).
    if chunks[0].strip():
        slides.append(chunks[0].strip())
    for i in range(1, len(chunks) - 1, 2):
        tag = chunks[i]
        content = chunks[i + 1].strip() if i + 1 < len(chunks) else ""
        slides.append((tag + content).strip())
    if not slides:
        slides = [body_html.strip() or "<p>No content</p>"]
    return slides


def _static_scripts():
    """Load mermaid + echarts from the local server (Cache-Storage backed)."""
    return (
        '<script>(function(){'
        'var urls=["/assets/mermaid.min.js","/assets/echarts.min.js"];'
        'function addSrc(u){var s=document.createElement("script");'
        's.src=u;s.async=true;document.head.appendChild(s);}'
        'if(!window.caches){urls.forEach(addSrc);return;}'
        'caches.open("mdpp-static-v1").then(function(c){'
        'urls.forEach(function(u){'
        'c.match(u).then(function(h){'
        'if(h){h.arrayBuffer().then(inject);}else{addSrc(u);}'
        'function inject(b){var s=document.createElement("script");'
        's.async=true;'
        's.src=URL.createObjectURL(new Blob([b],'
        '{type:"application/javascript"}));'
        'document.head.appendChild(s);}})'
        '.catch(function(){addSrc(u);});});});})();</script>\n',
        '<script>(function(){'
        'var n=0,t=setInterval(function(){n+=1;'
        'if(n>240){clearInterval(t);return;}'
        'if(window.mermaid&&!window.__mdppMm){window.__mdppMm=1;'
        'try{mermaid.initialize({theme:"default",startOnLoad:false});'
        'mermaid.run();}catch(e){console.warn("[MDPP] mermaid",e);}}'
        'if(window.echarts){clearInterval(t);_r();}'
        'function _r(){try{var els=document.querySelectorAll('
        '".mdpp-echarts:not([data-mdpp-rendered])");'
        'for(var k=0;k<els.length;k++){var el=els[k];'
        'var s=el.parentElement.nextElementSibling;'
        'if(!s||!s.classList.contains("mdpp-echarts-config"))continue;'
        'var opt=JSON.parse(s.textContent.trim());'
        'var ch=echarts.init(el);ch.setOption(opt);'
        'el.setAttribute("data-mdpp-rendered","1");'
        'window.addEventListener("resize",(function(c){'
        'return function(){c.resize();};})(ch));}}catch(e){'
        'console.error("[MDPP] echarts",e);}}},250);})();</script>\n'
    )


def build_presentation(body_html, title="Presentation", enable_katex=True):
    """Return a standalone slide-deck HTML document.

    The look & feel is exactly the normal preview: preview.css +
    highlight.css inline, KaTeX loaded from package assets.  Only the
    paging chrome is added on top.
    """
    css_parts = [
        pkg_assets.read_text("assets/preview.css") or "",
        pkg_assets.read_text("assets/highlight.css") or "",
        _DECK_CSS,
    ]
    inlined_css = "\n".join(css_parts)

    katex_head = ""
    if enable_katex and pkg_assets.exists("assets/katex/katex.min.css"):
        katex_head = (
            '<link rel="stylesheet" href="/assets/katex/katex.min.css">\n'
            '  <script src="/assets/katex/katex.min.js" async onload='
            '"if(window.mdppRenderMathSafe)window.mdppRenderMathSafe();"></script>\n'
        )

    slides = _split_slides(body_html)
    sections = "\n".join(
        '<div class="mdpp-slide%s"><div class="markdown-body">%s</div></div>'
        % (" active" if n == 0 else "", s)
        for n, s in enumerate(slides)
    )

    loader_js, init_js = _static_scripts()

    html = (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, "
        "initial-scale=1\">\n"
        "<title>%s</title>\n"
        "<style>\n%s\n</style>\n"
        "%s"
        "</head>\n"
        "<body>\n"
        "%s\n"
        "<div id=\"mdpp-progress\"></div>\n"
        "<div class=\"mdpp-click mdpp-click-l\" title=\"Previous (←)\"></div>\n"
        "<div class=\"mdpp-click mdpp-click-r\" title=\"Next (→)\"></div>\n"
        "<div class=\"mdpp-hud\">\n"
        "<button id=\"mdpp-prev\" title=\"Previous (←)\">‹</button>\n"
        "<span><span id=\"mdpp-cur\">1</span>/<span id=\"mdpp-total\">?</span>"
        "</span>\n"
        "<button id=\"mdpp-next\" title=\"Next (→)\">›</button>\n"
        "</div>\n"
        "<script>%s</script>\n"
        "%s"
        "%s"
        "<script>%s</script>\n"
        "</body>\n"
        "</html>\n"
    ) % (
        title,
        inlined_css,
        katex_head,
        sections,
        _katex_rerender_snippet(enable_katex),
        loader_js,
        init_js,
        _DECK_JS,
    )
    return html
