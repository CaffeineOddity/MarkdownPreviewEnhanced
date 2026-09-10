"""任务列表 checkbox 回写（task_toggle）纯函数测试。"""
import unittest

from mpe_core.preview_state import _task_toggle_new_text


class TestTaskToggleNewText(unittest.TestCase):
    def test_open_to_checked(self):
        self.assertEqual(
            _task_toggle_new_text("- [ ] todo", True), "- [x] todo")

    def test_checked_to_open(self):
        self.assertEqual(
            _task_toggle_new_text("- [x] done", False), "- [ ] done")

    def test_upper_x_to_open(self):
        self.assertEqual(
            _task_toggle_new_text("- [X] done", False), "- [ ] done")

    def test_asterisk_marker(self):
        self.assertEqual(
            _task_toggle_new_text("* [ ] item", True), "* [x] item")

    def test_ordered_list(self):
        self.assertEqual(
            _task_toggle_new_text("1. [ ] item", True), "1. [x] item")

    def test_indented(self):
        self.assertEqual(
            _task_toggle_new_text("  - [ ] nested", True), "  - [x] nested")

    def test_inline_content_preserved(self):
        self.assertEqual(
            _task_toggle_new_text("- [ ] fix `code` and **bold**", True),
            "- [x] fix `code` and **bold**")

    def test_not_task_line_returns_none(self):
        self.assertIsNone(_task_toggle_new_text("- plain item", True))
        self.assertIsNone(_task_toggle_new_text("normal text", False))
        self.assertIsNone(_task_toggle_new_text("- [ ]no space", True))

    def test_empty_line_returns_none(self):
        self.assertIsNone(_task_toggle_new_text("", True))


if __name__ == "__main__":
    unittest.main()
