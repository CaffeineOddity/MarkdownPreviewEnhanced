# link-fragment-anchor

关联：[GitHub Issue #22](https://github.com/CaffeineOddity/MarkdownPreviewEnhanced/issues/22)

状态：已实现（2026-11-07）；自动回归通过，手动用例待在 Sublime Text 内实测。

## 背景

`[字色](../試驗檔/文繞圖效果.md#字色)` 在预览里点开是 404
（`/doc/試驗檔/文繞圖效果.md#字色` → "Nothing matches the given URI"）；
去掉 `#字色` 的同一条链接能正常打开文档。

两处断裂：

1. `mpe_core/md_renderer.py` 的 `rewrite_link_hrefs()` 用整串（含 `#fragment`）
   判 `endswith(".md")` 和 `os.path.exists()`，都失败 → 落到 `/doc/` 分支，
   而 `/doc/` 里开头的 `../` 被钳到根，指向不存在的路径。
2. `assets/preview.js` 的 `switchToPreview()` 拼 `/?file=<abs>` 时丢掉
   fragment；即使带上了，新页面渲染完也不会滚到 `location.hash` 指向的标题。

## 目标

- 跨文件标题链接（`../other.md#heading`）点开后：打开正确文档，并滚到该标题
- 同文档的「跨文件写法」链接（`../same.md#heading`）原地滚动，不重开页面
- 与页内锚点（`#heading`）行为一致：支持中文 / Unicode 标题 id
- 无 fragment 的相对链接、其他协议链接行为不变

## 方案

### 服务端（`mpe_core/md_renderer.py`）

`rewrite_link_hrefs()` 先用 `#` 把 href 切成「路径 + fragment」：

- 路径部分参与 `.md` 判断、`os.path.exists()` 探测、`/doc/` 相对路径计算
- fragment 原样（不二次编码）拼回重写后的 URL：
  - `/?file=<quote(abs path)>#fragment`
  - `/doc/<rel>#fragment`
- 特殊协议 / 页内锚点 / 已是 `/?file=` 的链接仍原样返回

### 客户端（`assets/preview.js`）

- `switchToPreview(file, hash)`：`hash` 拼在 `withAuthQuery()` 之后
  （口令查询参数不能落到 fragment 里）
- 目标就是当前文档时只滚动，不重开
- `bindPreviewDocLinks()` 从 href 里取出 fragment 一起传给 `switchToPreview()`
- 新增 `scrollToId()` / `decodeHashId()` / `scrollToInitialHash()`：
  - 页面加载后（`mdppInit`）与每次 `applyContent()` 后调用
  - 只成功滚动一次（`hashScrollDone`），后续 SSE 刷新不再抢滚动位置
  - `location.hash` 是 percent-encoded，`decodeURIComponent` 后按 `id` 查找；
    解码失败退回原始串

## 验收标准

- `[字色](../試驗檔/文繞圖效果.md#字色)` → 打开 `/?file=<abs>`，落地即滚到 `字色` 标题
- `[Hello](../other.md#hello-world)` → 滚到 ASCII 标题
- `[同文件](../same.md#字色)` → 不刷新，原地滚到标题
- `[无锚点](../other.md)` → 行为与修复前一致
- `[外链](https://example.com/a#b)`、`[页内](#字色)` → 不改写
- `tests/test_link_fragment_anchor.py` 全绿

## 不做项

- 不改 `/doc/` 路由与 `../` 钳制规则
- 不处理图片 `src` 的 fragment
- 不做 `hashchange`（手动改地址栏 hash / 前进后退）监听

## 验证

- 自动：`tests/test_link_fragment_anchor.py`（12 条），`python3 tests/run_all.py`
- 手动：[跨文件标题链接](../issuses_case.md#7-跨文件标题链接issue-22)（issue #22）
