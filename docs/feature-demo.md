

# 新功能预览验证

> 打开本文件预览，逐段验证相对 v0.2.7 新增的功能。
> 顶部 frontmatter 应渲染为一行顶栏：「功能预览验证 · 2026-10-20 · 演示分页 代码块 剪贴板截图」。

## 1. 代码块文件名 / 行号 / 高亮

```python title="app.py" {1,3-5}
import os
import sys

def greet(name):
    print(f"hello, {name}")

def main():
    greet(os.getenv("USER", "world"))

if __name__ == "__main__":
    main()
```

预期：代码块头部显示文件名 `app.py`；行号列出现；第 1、3、4、5 行高亮；头部 Copy 只复制纯代码、不混入行号。

另一个只有高亮、无文件名（应无头部但仍显示行号+高亮）：

```python {2}
import os


def greet(name):
    return f"hello, {name}"
```
<!-- notes  'note here'-->

## 2. 演示分页 + 演讲者备注

<!-- pagebreak -->

## 第二页

<!-- notes 这是第二页的演讲者备注，演示模式按 N 显示/隐藏 -->

上面那行 `<!-- pagebreak -->` 强制分页；进入 Presentation Mode（命令面板 `MarkdownPreviewEnhanced: Presentation Mode`）后应切成两页，右下角按 `N` 显示/隐藏备注。预览正文与导出产物中不应看到这两条注释文本。

<!-- pagebreak -->

## 第三页

<!-- notes 第三页备注一。 -->
<!-- notes 第三页备注二，应与上面的备注合并为一页备注。 -->

连续多条 notes 应合并为当前页一份备注。

## 3. frontmatter 顶栏

本文件顶部 frontmatter 已含 `title` / `date` / `tags`，正文上方应显示顶栏。删除文首 `--- ... ---` 后刷新，顶栏应消失。

## 4. 剪贴板截图粘贴

在任意处定位光标后，截一张图（剪贴板里是位图），运行 `MarkdownPreviewEnhanced: Paste as Markdown`（或你自行绑定的键），应生成 `media/pasted-*.png` 并插入 `![](media/xxx.png)`。

（复制网页富文本再运行同一命令，应走 HTML→markdown；复制纯文本应降级普通粘贴。）