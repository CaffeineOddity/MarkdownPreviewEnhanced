#!/usr/bin/env python3
"""CodeHilite 扩展构造的版本兼容测试 (issue #14)."""
import unittest
from unittest import mock

from mpe_core import md_renderer as mdr


def _fake_codehilite(config):
    """按给定 config 造一个记录构造 kwargs 的假 CodeHiliteExtension 类。"""
    captured = {}

    class FakeCodeHiliteExtension:
        pass

    def __init__(self, **kwargs):
        captured.update(kwargs)

    FakeCodeHiliteExtension.__init__ = __init__
    FakeCodeHiliteExtension.config = config
    FakeCodeHiliteExtension.captured = captured
    return FakeCodeHiliteExtension


class TestBuildCodeHilite(unittest.TestCase):
    def test_modern_markdown_passes_formatter(self):
        fake = _fake_codehilite({"pygments_formatter": ["html", "desc"]})
        with mock.patch.object(mdr, "CodeHiliteExtension", fake), \
                mock.patch.object(mdr, "_table_linenos_formatter", return_value="FORMATTER"):
            mdr._build_codehilite()
        self.assertEqual(fake.captured, {
            "guess_lang": False,
            "linenums": True,
            "pygments_formatter": "FORMATTER",
        })

    def test_legacy_markdown_omits_formatter(self):
        fake = _fake_codehilite({
            "linenums": [None, "desc"],
            "guess_lang": [False, "desc"],
        })
        with mock.patch.object(mdr, "CodeHiliteExtension", fake):
            mdr._build_codehilite()
        self.assertEqual(fake.captured, {"guess_lang": False, "linenums": True})


if __name__ == "__main__":
    unittest.main()