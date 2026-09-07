# emoji-shortcode

## 需求

预览渲染支持 GFM emoji shortcode：`:smile:` → 😄，与 GitHub 渲染一致。

## 行为

- 转换范围：正文文本；**跳过** code fence、inline code、HTML 属性（src/href/title 等）、math、mermaid/echarts 内容。
- 语法：`:alias:`，alias 为 `[A-Za-z0-9_+-]+`，两侧需 word 边界（`:smile:` 中 `smile` 前后不是字母数字）。
- 映射：vendor `gemoji` db（MIT），构建期生成 `mpe_core/emoji_map.py`（alias → emoji 字符），约 1900 条。GitHub 专属吉祥物 shortcode（`octocat`、`shipit` 等 23 个，无 Unicode 字符）不收录。
- 未识别的 shortcode 原样保留，不报错。
- 设置项 `enable_emoji`（默认 `true`），`false` 时完全跳过替换。
- 渲染时机：markdown convert 之前在源码文本上替换（与 math 提取同级），fence/inline code 先 stash 再替换。

## 涉及文件

- `mpe_core/emoji_map.py`：生成映射（数据文件）
- `mpe_core/md_renderer.py`：新增 `_replace_emoji(text)`，在 `_extract_math` 的 stash 之后、math 提取之前调用
- `mpe_core/render.py`：`render_settings()` 增加 `enable_emoji`
- `MarkdownPreviewEnhanced.sublime-settings`：`enable_emoji`

## 验收标准

- `:smile:` 渲染为 😄；`:1-944-v2:` 等未识别的原样输出
- code fence / inline code 内 `:smile:` 不替换
- heading、表格单元格内的 shortcode 正常替换
- `enable_emoji: false` 时 `:smile:` 原样输出
- `tests/test_emoji.py` 覆盖上述行为
