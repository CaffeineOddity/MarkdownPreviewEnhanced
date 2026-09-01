# scroll-direction-tag

## 背景

ST→browser 的 `editorLine` 事件触发浏览器 `scrollToLine` → `scrollIntoView` →
`onScroll` → `reportBrowserScroll` 回传 ST，形成循环，导致 #4 报告的 Firefox
光标乱跳。

之前用 `_selfScrolling` 标志位 + `scrollend` 拦截，但时机不可靠。

## 目标

所有跨方向通信带来源标记，接收方据此拦截回环。

- ST→browser（SSE 事件）：payload 加 `from: "ST"`
- browser→ST（HTTP POST/GET 上报）：body/query 加 `from: "BS"`

## 行为约定

- 浏览器收到 `editorLine` 且 `from === "ST"` → 设 `_scrollFromST = true`
- `onScroll` 检查 `_scrollFromST`，为 true 时不调 `reportBrowserScroll`，
  并在 scrollend 或 800ms 后清除
- 用户手动滚动 → `onScroll` 时 `_scrollFromST === false` → 正常上报，
  上报 body 带 `from: "BS"`
- 后端 `/api/browser_scroll` 收到 `from === "BS"` 才写入 `browser_line`

## 涉及文件

- `mpe_core/preview_state_core.py`：`_json_with_file` 补 `from:"ST"`
- `assets/preview.js`：`editorLine` 处理处设标志；`reportBrowserScroll`
  body 加 `from:"BS"`；`onScroll` 检查标志
- `mpe_core/preview_handler.py`：`/api/browser_scroll` 校验 `from === "BS"`

## 验收标准

- ST 移动光标 → 浏览器滚动 → ST console 不出现 `WEB->ST browser_scroll`
- 用户手动滚浏览器 → ST console 出现 `WEB->ST browser_scroll`
- 其他 SSE 事件（content/close/tabs 等）payload 带 `from:"ST"` 但不影响行为

## 不做项

- 不改 `sendBeacon`（tab_close）和 `tab_open` 的 from 标记，它们不涉及回环
