# gfm-inline-syntax

## 需求

补齐常用 GFM/扩展内联语法：删除线 `~~text~~`、高亮 `==text==`、上标 `^text^`、下标 `~text~`。
当前渲染管线只有 emphasis/strong 等核心语法，`~~` 原样输出。

## 行为

- 实现方式：python-markdown 内联处理在 emphasis 之后无法通过 postprocess 稳定恢复
  嵌套标签，因此实现为一个 markdown Extension（`mdpp_inline`），注册
  `treeprocessor`，在跑树阶段扫描 `text` 节点并按正则拆分。
- 语法与优先级（同一遍扫描，先匹配先得）：
  - 删除线：`~~text~~`（`~~` 优先于下标 `~`；不允许内容以 `~`/空白开头结尾）
  - 高亮：`==text==`（内容不以空白开头结尾；`==` 两侧需非 `=` 字符）
  - 上标：`^text^`（内容不含空白；允许紧贴单词，如 `x^2^`）
  - 下标：`~text~`（内容不含空白；单个 `~`，两个 `~~` 已被删除线消费）
- 代码保护：treeprocessor 阶段 code fence 与 inline code 已是 `code` 节点，天然不受影响；
  math 由 `_extract_math` 在 convert 前 stash，也不受影响。
- 输出标签：`del`、`mark`、`sup`、`sub`。
- 渲染范围：预览、导出 HTML/PDF/PNG、富文本复制共用同一条 `render()` 链路，天然一致。
- 无设置项（跟随核心语法，不做开关；YAGNI）。

## 涉及文件

- `mpe_core/mdpp_inline.py`：新目录文件不适用（该需求是渲染器内部扩展），
  新建 `mpe_core/mdpp_inline.py`（Extension + Treeprocessor，高内聚单文件）
- `mpe_core/md_renderer.py`：`render()` 与 fallback 分支注册 `MdppInlineExtension()`
- `assets/preview.css`：`mark` 的亮/暗两套配色（`del/sup/sub` 用浏览器默认，
  GitHub 亦如此）
- `tests/test_gfm_inline.py`

## 验收标准

- `~~删除~~` → `<del>删除</del>`；`==高亮==` → `<mark>高亮</mark>`；
  `x^2^` → `x<sup>2</sup>`；`H~2~O` → `H<sub>2</sub>O`。
- code fence / inline code / math 中的上述记号原样保留。
- `~~` 嵌套 `**bold**` 等内联格式正常（treeprocessor 拆分后 markdown 继续处理子节点）。
- `a~~b~~c`（紧贴单词）与 GitHub 一致生效；`~ 单个波浪线` 不误伤。
- 回归：现有 emoji、math、task list 测试通过。

## 已知边界与不做项

- 不支持跨行匹配（内联语法单行为限，与 GitHub 一致）。
- 不做 `\~~` 转义特判——反斜杠转义由 markdown 核心处理，treeprocessor 只见已转义文本。
