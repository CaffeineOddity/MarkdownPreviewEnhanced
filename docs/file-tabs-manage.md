# File ↔ Tab 管理

## 目标

SSE 和 HTTP Server 生命周期绑定到浏览器 tab。**所有浏览器 tab 关闭 → 断 SSE + 停 HTTP Server。**

## 数据结构

一张表，file_path ↔ view_id 1:1：

```python
_tabs = {}   # file_path -> view_id
```

## tab_manager.py

纯增删改查：

```python
_tabs = {}

def register(file_path, view_id):  _tabs[file_path] = view_id
def remove(file_path):             _tabs.pop(file_path, None)
def has(file_path):                return file_path in _tabs
def get_view_id(file_path):        return _tabs.get(file_path)
def count():                       return len(_tabs)
def reset():                       _tabs.clear()
```

断开判定在 `preview_state.py` 的 `_tick`：

```python
if tab_manager.count() == 0:
    stop_server()
```

## 流程图

```mermaid
flowchart TD
  subgraph ST侧
    A1["Shift+Cmd+M (reuse=False)"] --> C{"has(file)?"}
    A2["收到 tab_open (reuse=True)"] --> C
    C -->|否| B["register: file→view_id"]
    C -->|是| D{"reuse?"}
    D -->|False| G["SSE + HTTP 保活（不关）"]
    D -->|True| P["SSE push close_old"]
    B --> E["返回 URL 给浏览器"]
    E --> G
    P --> J

    N["收到 tab_close"] --> J["remove(file)"]
    J --> K{"count() == 0?"}
    K -->|否| G
    K -->|是| L["断 SSE + 停 HTTP Server"]
  end

  subgraph 浏览器侧
    E2["Shift+Cmd+M 拿到 URL，加载"] --> Q2["fetch tab_open?reuse=false"]
    M["复制 URL"] --> M2["加载 URL"] --> Q3["fetch tab_open?reuse=true"]
    H["关 tab"] --> I["sendBeacon tab_close"]
    S["收到 close_old"] --> T["关自己"]
  end

  E -.-> E2
  Q2 -.-> A1
  Q3 -.-> A2
  I -.-> N
  P -.-> S
```

## 时序图：正常打开 → 关闭

```mermaid
sequenceDiagram
  participant ST
  participant tab_manager
  participant Server
  participant Browser

  ST->>tab_manager: register(file=A, view_id=1)
  tab_manager->>Server: ensure_server()
  Server->>Browser: open ?file=A
  Browser->>Server: SSE 建立

  Browser->>Server: tab_close(file=A)
  Server->>tab_manager: remove(file=A)
  tab_manager->>tab_manager: count() == 0
  tab_manager->>Server: stop SSE + stop HTTP
```

## 时序图：复制 URL 开新 tab

```mermaid
sequenceDiagram
  participant Browser
  participant Server
  participant tab_manager

  Note over Browser: 已有 tab: ?file=A

  Browser->>Server: 粘贴 URL 开新 tab ?file=A
  Server->>tab_manager: tab_open(file=A)
  tab_manager->>tab_manager: has(A) = True
  tab_manager->>Browser: SSE push close_old(file=A)
  Browser->>Browser: 关旧 tab
  Browser->>Server: tab_close(file=A) 旧
  Server->>tab_manager: remove(file=A)
  tab_manager->>tab_manager: 新 tab 接管，重新 register
```

## 时序图：浏览器崩溃兜底

```mermaid
sequenceDiagram
  participant tab_manager
  participant Server
  participant Browser

  tab_manager->>Server: ensure_server()
  Server->>Browser: open ?file=A
  Browser->>Server: SSE 建立

  Note over Browser: 崩溃 ✗
  Note over Server: 无 tab_close，_tabs 残留
  Note over Server: SSE 断开 > 60s
  Server->>tab_manager: 兜底清零
  tab_manager->>Server: stop SSE + stop HTTP
```

## 改动清单

| 文件 | 改动 |
|------|------|
| `tab_manager.py` | 一张表 `_tabs`，纯增删改查 |
| `preview_state.py` | `mark_browser_open` 调 `register`；`_tick` 改 `count()==0` 才断；SSE 断开 >60s 兜底 |
| `preview_handler.py` | 加 `/api/tab_close` 路由；`/api/stream` 首次连接查 `has`，已有则 SSE push `close_old` |
| `preview.js` | `publishTabBye` 加 `sendBeacon('/api/tab_close')`；收到 `close_old` 关自己 |
| `preview_url.py` | `open_preview_browser` 传 `file + view_id` 给 `register` |

## 设计要点

- **一张表** `_tabs`：`file_path ↔ view_id`，1:1
- **tab_manager.py 纯增删改查**，不管断开逻辑
- **断开判定在 `preview_state.py`**：`count() == 0`
- **一个 file 一个 tab**：复制 URL → 关旧 → 新接管
- **打开**：后端 `register`
- **关闭**：前端 `sendBeacon` → 后端 `remove`
- **崩溃兜底**：SSE 断开 >60s 清零
