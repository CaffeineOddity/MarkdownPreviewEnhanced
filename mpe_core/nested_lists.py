"""列表嵌套按 2 个空格，缩进代码块仍按 4 个空格。

Python-Markdown 的 tab_length 同时管列表和缩进代码块，默认 4。
CommonMark / GitHub 的子列表缩进到上一项正文那一列（`* item` 是 2 个空格），
代码块却仍是 4 个空格。这里只替换列表处理器和列表缩进处理器，
不改 Markdown 实例上的 tab_length，因此顶层代码块不受影响。

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


class _TwoSpaceIndent(BlockProcessor):
    """插在列表处理器和 BlockProcessor 之间，把 tab_length 改成 2。

    必须继承 BlockProcessor。否则 C3 线性化会把它排到 BlockProcessor 后面，
    OListProcessor.__init__ 的 super() 到不了这里，正则仍按 4 空格编译。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tab_length = 2


class TwoSpaceOListProcessor(OListProcessor, _TwoSpaceIndent):
    """有序列表：2 空格嵌套，并且保留 start 属性。"""

    SIBLING_TAGS = ["ol"]
    LAZY_OL = False

    def __init__(self, parser):
        super().__init__(parser)
        # 0–1 个空格是同级项。2–3 个空格留给父类按 tab_length 编出来的 INDENT_RE。
        self.CHILD_RE = re.compile(
            r"^[ ]{0,%d}((\d+\.))[ ]+(.*)" % (self.tab_length - 1)
        )


class TwoSpaceUListProcessor(UListProcessor, _TwoSpaceIndent):
    """无序列表：2 空格嵌套，标记类型不与有序列表混用。"""

    SIBLING_TAGS = ["ul"]

    def __init__(self, parser):
        super().__init__(parser)
        self.RE = re.compile(
            r"^[ ]{0,%d}[*+-][ ]+(.*)" % (self.tab_length - 1)
        )
        self.CHILD_RE = re.compile(
            r"^[ ]{0,%d}(([*+-]))[ ]+(.*)" % (self.tab_length - 1)
        )


class TwoSpaceListIndentProcessor(ListIndentProcessor, _TwoSpaceIndent):
    """列表内部的续行也按 2 空格缩进，避免子列表被拆开。"""


class TwoSpaceListExtension(Extension):
    """用 2 空格列表处理器替换 Python-Markdown 默认的 4 空格列表。"""

    def extendMarkdown(self, md):
        md.parser.blockprocessors.register(
            TwoSpaceOListProcessor(md.parser), "olist", 40
        )
        md.parser.blockprocessors.register(
            TwoSpaceUListProcessor(md.parser), "ulist", 30
        )
        md.parser.blockprocessors.register(
            TwoSpaceListIndentProcessor(md.parser), "indent", 90
        )
