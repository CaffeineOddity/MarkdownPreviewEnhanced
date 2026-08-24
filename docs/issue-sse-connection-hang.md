# Bug: 多预览 tab 时新 tab 一直"加载中"（SSE 长连接占满 HTTP keep-alive 连接池）

## 环境

- Sublime Text 4200 (osx arm64)
- 插件：MarkdownPreviewEnhanced（自研，`MarkdownPreviewEnhanced.py` + `mpe_core/`）
- 本地 HTTP 服务器：`http://127.0.0.1:8765`，`ThreadingHTTPServer`（`ThreadingMixIn + HTTPServer`，`daemon_threads=True`）
- 浏览器：Google Chrome
- 预览页面：`http://127.0.0.1:8765/?file=<markdown路径>`，CSS/JS 全部内联进 HTML

## 现象

1. 打开第 1 个预览 tab：正常。
2. 继续打开更多 tab（实测第 4~6 个时触发）：新 tab 在 Chrome 里**一直转圈"加载中"**，页面内容不显示。
3. **关掉一个旧 tab 后立即恢复**——新 tab 马上加载成功。
4. 与本次改动的 mdpopups 迁移无关（原始 v0.1.5 就有此问题，`preview_server.py` 未做架构改动前即复现）。

## 架构（SSE 实时预览如何工作）

- 每个预览 tab 加载页面 HTML（内容已完整渲染并内联，**不依赖 SSE 也能显示**）。
- 页面 JS 用 `EventSource("/api/stream?file=<path>")` 建立 **SSE 长连接**，接收服务器推送的 `content` / `editorLine` / `close` 事件，实现"编辑器改动 → 浏览器实时刷新"。
- 服务器 `_api_stream` handler：`while True` 循环，`q.get(timeout=5)` 等待事件，有事件就 `wfile.write` 推送，空闲写 `: hb` 心跳。**连接永不主动关闭**（`self.close_connection = False`，HTTP/1.1 keep-alive 长连接）。

## 已做的修复（均未解决根因）

1. **客户端 visibility 管理**（`assets/preview.js`）：用 `document.visibilitychange`，tab 切走时 `es.close()` 断开 SSE、切回时重连。日志证实生效（每次切换都有 `sse drop ... Broken pipe` + `sse disconnect`）。
2. **服务器锁外推 SSE**：`_notify_sse` 移出 `_STATE.lock`，锁内只更新 channel 数据。
3. **心跳间隔 15s → 5s**：缩短断连感知时间。
4. **加锁诊断日志**：每次锁获取/释放写入 `/tmp/mpe_lock.log`。

## 关键证据链

### 证据 1：锁完全正常，不是锁竞争

`/tmp/mpe_lock.log`（每次 ACQ/REL 全记录）显示**所有锁获取 `wait=0.000s`、释放 `held=0.000s`**，无任何竞争或持锁阻塞。排除了 `_STATE.lock` 问题。

### 证据 2：页面请求正常，SSE 请求卡 4 秒

```
curl 页面请求 (?file=...):    HTTP 200, 0.002s   ← 正常
curl SSE (api/stream):        HTTP 200, 4.005s    ← 卡满 --max-time 4 超时
curl browser_scroll (POST):   HTTP 200, 4.002s    ← 卡满超时
```

### 证据 3：卡住的 SSE 请求其实到达了 handler，锁瞬间拿到，但响应延迟 4 秒

对卡住状态下的 SSE 请求做锁日志观测：

```
[14:57:22.568] ACQ api_stream_connect wait=0.000s   ← 请求已进入 _api_stream
[14:57:22.569] REL api_stream_connect held=0.001s   ← 锁瞬间拿到
SSE: 200 4.005400s                                   ← 但 curl 4 秒后才收到响应
```

→ 请求在**进入 handler 后、发出响应前**被阻塞了约 4 秒，阻塞点只能是 `_api_stream` 里的 `send_response(200)` / `end_headers()` / `wfile.write(initial)` / `flush()`（代码第 448-450 行）。

### 证据 4：ESTABLISHED 连接数恒为 12（6 对），不随 tab 关闭减少

`netstat` 反复显示 `127.0.0.1.8765` 上有 **12 条 ESTABLISHED = Chrome 侧 6 条 + 服务器侧 6 条**。即使 visibility 断开了 SSE、tab 已关，连接数也不下降。

## 根因（已确认）

两件事叠在一起，不是锁竞争：

1. **每个预览 tab 占用 2 条 Chrome HTTP/1.1 连接**
   - 页面 GET 默认 keep-alive：响应结束后 TCP **不关**，闲置占 1 条。
   - SSE `Connection: keep-alive` + `close_connection=False`：流永不结束，再占 1 条。
   - Chrome 对 `127.0.0.1:8765` 最多 **6 条**并发连接。3 个 tab = 6 条，第 4 个 tab 的页面请求只能排队 → 一直「加载中」。关掉一个旧 tab 立刻恢复。
2. **visibility 关 SSE 不够**：`es.close()` 只停浏览器端。服务器 `while True` 还在 `q.get`，且 HTML keep-alive 连接仍闲置占槽。隐藏 tab 各留 1 条 HTML 连接，可见 tab 再加 SSE，照样打满 6 条。
3. **断开检测滞后**：客户端关掉 socket 后，heartbeat `write` 往往要第二次才 EPIPE（第一次进内核发送缓冲就返回成功），线程/队列回收慢。`netstat` 上 ESTABLISHED 不随 tab 关闭下降。

curl 打 `/api/stream` 卡满 `--max-time` 是 SSE 本身不结束，不是证据。真正的协议层证据是：对 HTML 发 HTTP/1.1 `Connection: keep-alive`，同一 TCP 上第二条 GET 会立刻再拿到 `200`（连接被复用了）。

## 修复

1. **所有响应 `Connection: close`**（含页面、POST、SSE）。短请求用完即关 TCP，不进 keep-alive 池。SSE 仍然在 handler 里长写，但响应结束后（客户端断开）关连接，Chrome 不会拿它去排队下一个请求。
2. **SSE 循环用 `select` 探测对端 FIN/RST**，1s 内回收线程；`close_connection = True`，避免 `handle()` 在流结束后继续等下一条 keep-alive 请求。
3. **保留 visibility 管理**：隐藏 tab 主动 `es.close()`，同一窗口多 tab 时只有当前可见页占 1 条 SSE。这是锦上添花，不能单独解决问题。

不采用 HTTP/2（本地 `http.server` 实现成本高）。

回归：`python3 tests/test_preview_server_connection.py`

## 附加观察

- 服务器进程 PID 在每次 Sublime 重载插件/重启时变化（服务器生命周期绑定插件）。
- `ps -M`（macOS 线程数）返回 0，未能统计服务器线程数。
- 服务器日志中 `sse connect clients=N` 的 `clients` 是**按 channel（文档）**计数，不是全局连接数；日志从未出现跨文档的 `clients>1`（visibility 生效）。
