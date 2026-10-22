"""把一段文本按独立成行插入光标处（供分页/备注插入命令复用）。"""


def insert_on_own_line(view, edit, text):
    """在各选区光标处插入 *text*，保证其独立成行。

    从后往前处理，避免前面选区插入后改变后面选区的坐标。
    """
    for region in reversed(list(view.sel())):
        point = region.begin()
        line = view.line(point)
        prefix = "" if point == line.begin() else "\n"
        suffix = "" if point == line.end() else "\n"
        view.insert(edit, point, prefix + text + suffix)