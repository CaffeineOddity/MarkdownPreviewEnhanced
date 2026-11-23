"""列表嵌套按父项正文列，缩进代码块仍按 4 个空格。

Python-Markdown 的 tab_length 同时管列表和缩进代码块，默认 4。
CommonMark / GitHub 的子列表缩进到上一项正文那一列（`* item` 是 2 个空格，
`1. item` 是 3 个空格），最多再深 3 个空格；代码块却仍是 4 个空格。
这里只替换列表处理器和列表缩进处理器，不改 Markdown 实例上的 tab_length，
因此顶层代码块不受影响。

v0.3.6 只认 2–3 个空格为一层，4 个空格或 tab 缩进的子列表会被并进父项文本
（issue #27）。现在按每一层父项的正文列判断子列表，2 / 3 / 4 个空格和 tab
都能正确分层；更深的行仍按父项文字或缩进代码块处理。

另加段落中断：段落里出现 `- item` 或以 1 开始的有序列表时，列表从该行开始，
与 CommonMark / GitHub 一致（issue #27 的示例列表前没有空行）。

有序列表起始编号仍关闭 lazy ol（issue #15）。ul 与 ol 也不再并成一张表。
"""
import re

from mdpopups.markdown.blockprocessors import (
    BlockProcessor,
    ListIndentProcessor,
    OListProcessor,
    UListProcessor,
)
from mdpopups.markdown.extensions import Extension

# 行首的列表标记，含缩进与标记后的空格。用于拆列表块和判断缩进块。
_MARKER_RE = re.compile(r"^([ ]*)((\d+\.)|[*+-])([ ]+)(.*)$")

# 能中断段落的列表标记：任意缩进的无序列表，或以 1 开始的有序列表。
# 顶层列表标记前最多 3 个空格，再深就是缩进代码块。
_INTERRUPT_RE = re.compile(r"(?m)^ {0,3}(?:[*+-]|1\.)[ \t]+(?=\S)")


def _leading_spaces(line):
    """返回行首空格数。tab 已由 Markdown 的 detab 预处理展开。"""
    return len(line) - len(line.lstrip(" "))


def _dedent_block(text, cut):
    """每行最多去掉 cut 个前导空格，保留更深的相对缩进。"""
    lines = []
    for line in text.split("\n"):
        if not line.strip():
            lines.append("")
            continue
        line_cut = min(cut, _leading_spaces(line))
        lines.append(line[line_cut:])
    return "\n".join(lines)


class _FlexibleIndent(BlockProcessor):
    """插在列表处理器和 BlockProcessor 之间，把 tab_length 改成 2。

    必须继承 BlockProcessor。否则 C3 线性化会把它排到 BlockProcessor 后面，
    OListProcessor.__init__ 的 super() 到不了这里，正则仍按 4 空格编译。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tab_length = 2


class _FlexibleListItems:
    """按父项正文列拆列表块，产出可递归解析的 item 字符串。

    Python-Markdown 的 get_items 按固定 tab_length 判断缩进，父子项宽度
    不一致时会并错层。这里维护缩进栈：标记缩进落在父项标记缩进 + 2 到
    父项正文列 + 3 之间才算子列表，否则仍是父项文字。子项输出时缩进到
    父项的正文列，交给 OListProcessor.run 递归解析。
    """

    def get_items(self, block):
        items = []
        # 每层打开项：(子项缩进下限, 原始正文列, 归一化正文列)。
        levels = []
        for line in block.split("\n"):
            if not line.strip():
                if items:
                    items[-1] = "{}\n".format(items[-1])
                continue
            match = _MARKER_RE.match(line)
            if not match:
                if items:
                    items[-1] = "{}\n{}".format(items[-1], line)
                continue
            indent = len(match.group(1))
            marker = match.group(2)
            spaces = match.group(4)
            text = match.group(5)

            # 先探测这条标记属于哪一层，确认接受后再更新栈。
            # 子列表最少比父项标记深 2 个空格（v0.3.6 的两空格习惯），
            # 最多到父项正文列 + 3（再深是父项文字或缩进代码）。
            probe = list(levels)
            while probe and indent < probe[-1][0]:
                probe.pop()
            if probe and indent > probe[-1][1] + 3:
                if items:
                    items[-1] = "{}\n{}".format(items[-1], line)
                continue
            level = len(probe)
            if level == 0 and not self._is_list_marker(marker):
                # 顶层 ul / ol 不并成一张表，另一种标记当普通文字。
                if items:
                    items[-1] = "{}\n{}".format(items[-1], line)
                continue

            # 归一化缩进取父项的正文列：有序列表的标记更宽，子项要从
            # `1. ` 的正文列（3）起，不能固定按 2 个空格一层。
            if level == 0:
                canonical_indent = 0
            else:
                canonical_indent = probe[level - 1][2]
            canonical_content = canonical_indent + len(marker) + len(spaces)
            levels = probe
            levels.append((
                indent + 2,
                indent + len(marker) + len(spaces),
                canonical_content,
            ))

            if level == 0:
                if not items and self.TAG == "ol":
                    self.STARTSWITH = marker[:-1]
                items.append(text)
            else:
                canonical = "{}{}{}{}".format(
                    " " * canonical_indent, marker, spaces, text
                )
                if items and items[-1].startswith("  "):
                    items[-1] = "{}\n{}".format(items[-1], canonical)
                else:
                    items.append(canonical)
        return items

    def _is_list_marker(self, marker):
        """顶层标记是否属于当前列表类型（ul 与 ol 不混）。"""
        if self.TAG == "ul":
            return marker in ("*", "+", "-")
        return marker.endswith(".") and marker[:-1].isdigit()


class _FlexibleOList(_FlexibleListItems, OListProcessor, _FlexibleIndent):
    """有序列表：按父项正文列嵌套，并且保留 start 属性。"""

    SIBLING_TAGS = ["ol"]
    LAZY_OL = False

    def __init__(self, parser):
        super().__init__(parser)
        # 顶层标记前最多 3 个空格。
        self.RE = re.compile(r"^[ ]{0,3}\d+\.[ ]+(.*)")


class _FlexibleUList(_FlexibleListItems, UListProcessor, _FlexibleIndent):
    """无序列表：按父项正文列嵌套，标记类型不与有序列表混用。"""

    SIBLING_TAGS = ["ul"]

    def __init__(self, parser):
        super().__init__(parser)
        self.RE = re.compile(r"^[ ]{0,3}[*+-][ ]+(.*)")


class FlexibleListIndentProcessor(ListIndentProcessor, _FlexibleIndent):
    """列表内部的续行按 2 空格缩进；子列表标记按实际缩进反缩进。"""

    def looseDetab(self, text, level=1):
        first_line = text.split("\n", 1)[0]
        match = _MARKER_RE.match(first_line)
        if match:
            indent = len(match.group(1))
            content_column = self.tab_length * level
            # 每层正文列最多 3（`1. `），再留 3 个空格的余量。
            if content_column <= indent <= 3 * level + 3:
                # 缩进宽度可能不是 2 的倍数（3、4、tab），按实际宽度整体
                # 反缩进，避免 4 空格被算成两层或 3 空格留下残余缩进。
                return _dedent_block(text, indent)
        return super().looseDetab(text, level)


class ListInterruptProcessor(BlockProcessor):
    """让列表中断段落，和 CommonMark / GitHub 一致。

    Python-Markdown 只认空行之后的列表。这里在段落块中找到第一条
    `- item` / `1. item`，把前面的文字交给普通块处理器，列表部分插回
    待处理队列，后续仍由列表处理器解析。
    """

    def test(self, parent, block):
        match = _INTERRUPT_RE.search(block)
        return bool(match) and match.start() > 0

    def run(self, parent, blocks):
        block = blocks.pop(0)
        match = _INTERRUPT_RE.search(block)
        before = block[: match.start()].rstrip("\n")
        after = block[match.start():]
        self.parser.parseBlocks(parent, [before])
        blocks.insert(0, after)


class ListNestingExtension(Extension):
    """用 CommonMark 风格的列表处理器替换 Python-Markdown 的 4 空格列表。"""

    def extendMarkdown(self, md):
        md.parser.blockprocessors.register(
            _FlexibleOList(md.parser), "olist", 40
        )
        md.parser.blockprocessors.register(
            _FlexibleUList(md.parser), "ulist", 30
        )
        md.parser.blockprocessors.register(
            FlexibleListIndentProcessor(md.parser), "indent", 90
        )
        md.parser.blockprocessors.register(
            ListInterruptProcessor(md.parser), "list_interrupt", 11
        )
