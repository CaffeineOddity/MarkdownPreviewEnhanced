# task-list-checkbox-sync

## 需求

预览里的 GFM 任务列表（`- [ ]` / `- [x]`）checkbox 可点击，点击后回写编辑器源文件，
实现预览 ↔ 编辑器双向同步。当前 `_apply_task_lists` 渲染的 checkbox 带 `disabled`，纯展示。

## 行为

- 渲染：checkbox 不再带 `disabled`（与 GitHub 一致）；`<li>` 上的 `data-line` 已由
  `_inject_block_lines` 注入，指向 `- [ ]` 所在的源码行（1-based，含 frontmatter offset）。
- 浏览器侧（`assets/preview.js`）：事件委托监听 `.task-list-item-checkbox` 点击；
  取最近 `li[data-line]` 的行号与 checked 状态，POST `/api/task_toggle`
  `{file, line, checked}`。仅 server 模式生效；file/export 模式 checkbox 可视觉切换但不落盘。
- 服务端（`mpe_core/preview_handler.py`）：新 POST 路由 `/api/task_toggle`，校验
  `line > 0`、`file` 非空后，向 `preview_state_core` 队列投递事件。
- ST 侧（`mpe_core/preview_state.py`）：后台 `_tick` 轮询 `pop_task_toggles()`，
  经 `tab_manager.get_view_id_for_file` 找到视图，`sublime.set_timeout` 内用
  TextCommand 原子替换该行列表标记：
  - 匹配 `^(\s*(?:[-*+]|\d+\.)\s+\[)([ xX])(\])`，group2 按目标状态替换为空格或 `x`；
  - 行内容不匹配（文件已改、行号漂移）时静默跳过并记 debug 日志，不报错；
  - 多窗口查找视图复用 `_scroll_editor_to_line` 的遍历方式。
- 回环：源文件变更触发的正常 debounce 重渲染会推新 HTML，checkbox 状态保持一致；
  不做额外抑制。
- 范围：仅支持 `- ` / `* ` / `+ ` / 有序列表的任务项；fence 内、引用内的不处理
  （blockquote 内的 li data-line 同样来自块扫描，行为一致，无需特判）。

## 涉及文件

- `mpe_core/preview_state_core.py`：`queue_task_toggle()` / `pop_task_toggles()`
- `mpe_core/preview_handler.py`：`/api/task_toggle` 路由
- `mpe_core/preview_state.py`：`_tick` 消费事件；`_apply_task_toggle_edit(view, line, checked)`
  纯函数 `_task_toggle_new_text(line_text, checked)` 供测试
- `mpe_core/md_renderer.py`：`_apply_task_lists` 去掉 `disabled`
- `assets/preview.js`：`bindTaskToggle()`，在 `mdppInit` 与 `applyContent` 后挂接
  （事件委托只需挂一次，`mdppInit` 挂即可）
- `tests/test_task_toggle.py`

## 验收标准

- 预览点击未勾选项 → 源文件对应行 `[ ]` 变 `[x]`；点击已勾选项反向。
- `enable_task_lists: false` 时不渲染 checkbox（既有行为）。
- 行号对应的文本不再是任务项时，不改动文件、无异常。
- `_task_toggle_new_text` 纯函数单测覆盖 `[ ]`→`[x]`、`[X]`→`[ ]`、非任务行返回 None。
- 既有 80 个测试全部通过。

## 已知边界与不做项

- 不做浏览器侧乐观锁：并发改文件时以「行文本匹配」为唯一一致性校验。
- file:// 模式（use_local_server=false）不支持回写。
- 不新增设置项，跟随 `enable_task_lists`。
