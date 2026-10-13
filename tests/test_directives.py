#!/usr/bin/env python3
"""分页注释/备注拆分与导出分页转换测试 (docs/specs/presentation-pagebreak.md)."""
import unittest

from mpe_core.directives import convert_pagebreaks, split_slides


class TestSplitSlides(unittest.TestCase):
    def test_no_pagebreak_single_slide(self):
        slides = split_slides("<h1>T</h1><p>x</p>")
        self.assertEqual(len(slides), 1)
        self.assertEqual(slides[0]["notes"], [])

    def test_pagebreak_splits(self):
        body = "<h1>A</h1><!-- pagebreak --><h1>B</h1>"
        slides = split_slides(body)
        self.assertEqual(len(slides), 2)
        self.assertIn("A", slides[0]["html"])
        self.assertIn("B", slides[1]["html"])

    def test_notes_attach_to_slide(self):
        body = ("<p>1</p><!-- pagebreak --><p>2</p>"
                "<!-- notes hello --><!-- pagebreak --><p>3</p>")
        slides = split_slides(body)
        self.assertEqual(slides[1]["notes"], ["hello"])
        self.assertNotIn("notes", slides[1]["html"])

    def test_empty_slides_dropped(self):
        body = "<!-- pagebreak --><p>x</p><!-- pagebreak --><!-- pagebreak -->"
        slides = split_slides(body)
        self.assertEqual(len(slides), 1)


class TestConvertPagebreaks(unittest.TestCase):
    def test_converts_and_strips_notes(self):
        html = convert_pagebreaks("<p>x</p><!-- pagebreak --><!-- notes n --><p>y</p>")
        self.assertIn('class="mdpp-pagebreak"', html)
        self.assertNotIn("notes", html)


if __name__ == "__main__":
    unittest.main()