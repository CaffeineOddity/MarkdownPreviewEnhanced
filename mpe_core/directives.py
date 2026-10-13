"""Page-directive handling shared by the presentation deck and export.

Two HTML-comment directives drive both the slide deck and print pagination:

  ``<!-- pagebreak -->`` — force a page break (slide split / print page).
  ``<!-- notes ... -->`` — speaker notes for the enclosing slide (deck only).

Both survive python-markdown as raw HTML comments (verified against the
bundled python-markdown at build time); downstream code removes them where
they must not surface (exported HTML/PDF, copied HTML).
"""
import re

PAGEBREAK_RE = re.compile(r"<!--\s*pagebreak\s*-->", re.IGNORECASE)
NOTES_RE = re.compile(
    r"<!--\s*notes\b(?P<body>.*?)-->", re.DOTALL | re.IGNORECASE,
)


def split_slides(body_html):
    """Split *body_html* into slides and per-slide speaker notes.

    Returns a list of ``{"html": str, "notes": list[str]}`` in document order.
    A document without ``<!-- pagebreak -->`` becomes a single slide. Empty
    slides (a leading or consecutive pagebreak) are dropped, as are their
    orphan notes.
    """
    slides = []
    for segment in PAGEBREAK_RE.split(body_html):
        notes = NOTES_RE.findall(segment)
        html = NOTES_RE.sub("", segment).strip()
        if not html and not notes:
            continue
        slides.append({
            "html": html or "<p>No content</p>",
            "notes": [n.strip() for n in notes if n.strip()],
        })
    if not slides:
        slides = [{"html": "<p>No content</p>", "notes": []}]
    return slides


def convert_pagebreaks(body_html):
    """Prepare body for standalone HTML/PDF export.

    Removes speaker notes and turns pagebreak comments into an empty
    ``.mdpp-pagebreak`` element that print CSS breaks after.
    """
    html = NOTES_RE.sub("", body_html)
    return PAGEBREAK_RE.sub('<div class="mdpp-pagebreak"></div>', html)