"""GFM/扩展内联语法 markdown Extension：删除线、高亮、上标、下标。

语法（treeprocessor 阶段处理，同一次扫描，先匹配先得）：
  - ~~删除~~  → <del>（~~ 优先于 ~ 下标）
  - ==高亮==  → <mark>
  - ^上标^    → <sup>（内容不含空白）
  - ~下标~    → <sub>（内容不含空白）

为什么用 treeprocessor 而不是 HTML postprocess：内联语法会嵌套（如
``~~**bold**~~``），跑树阶段拆分 text 节点后 markdown 内联处理器还会继续
处理新元素的内容，嵌套格式天然正确。

code fence 与 inline code 在跑树阶段已是 <code> 节点，跳过即可；math 在
convert 前已被 stash 成占位符，同样不受影响。
"""
import re
import xml.etree.ElementTree as etree

from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor


# 单遍组合正则。删除线分支要求内容不以 ~ 开头结尾且非空；
# 高亮同理；上下标内容不含空白（与 GFM 下标扩展一致）。
# sup/sub 不加前置 lookbehind：x^2^ 这类紧贴写法是主要使用场景。
_INLINE_MD_RE = re.compile(
    r"~~(?P<del>[^~\s](?:[^~]*[^~\s])?)~~"
    r"|==(?P<mark>[^=\s](?:[^=]*[^=\s])?)=="
    r"|\^(?P<sup>[^\s^]+)\^"
    r"|~(?P<sub>[^\s~]+)~"
)


def _split_text(text):
    """把 text 拆成 [(kind, value)]；kind ∈ text|del|mark|sup|sub。"""
    out = []
    pos = 0
    for m in _INLINE_MD_RE.finditer(text):
        if m.start() > pos:
            out.append(("text", text[pos:m.start()]))
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
        pos = m.end()
    if pos < len(text):
        out.append(("text", text[pos:]))
    return out


def _inline_only(parts):
    """全部是纯文本时返回 True（无需改造）。"""
    return all(kind == "text" for kind, _ in parts)


class MdppInlineTreeprocessor(Treeprocessor):
    """跑树阶段拆分 text / tail 节点，产出 del/mark/sup/sub 元素。"""

    def run(self, root):
        for parent in list(root.iter()):
            if parent.tag == "code":
                continue
            # parent.text
            if parent.text:
                parts = _split_text(parent.text)
                if not _inline_only(parts):
                    self._replace_text(parent, parts)
            # 每个 child 的 tail（child 为 code 时仍处理其 tail）。
            # 倒序遍历：_replace_tail 会在 child 之后插入新元素。
            for child in reversed(list(parent)):
                if child.tail:
                    parts = _split_text(child.tail)
                    if not _inline_only(parts):
                        self._replace_tail(parent, child, parts)

    @staticmethod
    def _make_elem(kind, value):
        el = etree.Element(kind)
        el.text = value
        return el

    def _replace_text(self, parent, parts):
        """parent.text 替换为 parts，保持片段先后顺序。

        parent.text 语义上位于全部子元素之前，所以首个片段是 text 时留在
        parent.text；后续 text 片段作为前一个元素的 tail 挂载，收尾 text
        挂在最后一个新元素的 tail 上。
        """
        first_kind, first_value = parts[0]
        rest = parts[1:] if first_kind == "text" else parts
        parent.text = first_value if first_kind == "text" else None
        offset = 0
        for kind, value in rest:
            if kind == "text":
                if offset > 0:
                    prev = parent[offset - 1]
                    prev.tail = (prev.tail or "") + value
                else:
                    # 首片段即元素且紧跟 text：text 无处可挂，作为 parent.text。
                    # 此时 parent.text 必为 None。
                    parent.text = value
                continue
            el = self._make_elem(kind, value)
            parent.insert(offset, el)
            offset += 1

    def _replace_tail(self, parent, child, parts):
        """child.tail 替换为 parts，保持片段先后顺序。

        text 片段留在 child.tail（或上一个新元素的 tail），元素插到 child
        之后、原下一个兄弟之前。
        """
        first_kind, first_value = parts[0]
        rest = parts[1:] if first_kind == "text" else parts
        child.tail = first_value if first_kind == "text" else None
        index = list(parent).index(child) + 1
        for kind, value in rest:
            if kind == "text":
                prev = parent[index - 1]
                if prev is child:
                    child.tail = (child.tail or "") + value
                else:
                    prev.tail = (prev.tail or "") + value
                continue
            el = self._make_elem(kind, value)
            parent.insert(index, el)
            index += 1


class MdppInlineExtension(Extension):
    def extendMarkdown(self, md):
        # 注册在 Prettify(5) 之后、Unescape(8) 之前，紧跟内联处理结果，
        # 保证 **bold** 先变成 <strong>，~~**bold**~~ 之类嵌套再由我们拆分。
        md.treeprocessors.register(MdppInlineTreeprocessor(md), "mdpp_inline", 6.5)
