/* MarkdownPreviewEnhanced client: SSE push, TOC, scroll sync, export */
(function () {
  "use strict";

  var cfg = window.MDPP_CONFIG || { mode: "file", scrollSync: true, showToc: true };

  function ts() {
    var d = new Date();
    return d.getHours() + ":" + d.getMinutes() + ":" + d.getSeconds() + "." +
      ("00" + d.getMilliseconds()).slice(-3);
  }

  // 频道标识:地址栏 ?file= 参数,决定 SSE/滚动上报归属哪个文档
  var channelFile = "";
  try {
    channelFile = new URLSearchParams(window.location.search).get("file") || "";
  } catch (err) {}
  var channelQuery = channelFile ? "?file=" + encodeURIComponent(channelFile) : "";

  function windowNameFor(file) {
    return "mdpp_" + encodeURIComponent(file || "untitled");
  }

  try { window.name = windowNameFor(channelFile); } catch (err) {}

  var scrollKey = "mdpp-scroll-y";
  var lastReportedLine = 0;
  var lastEditorLine = 0;
  var es = null;           // EventSource — 全 origin 只有选中的 leader tab 持有
  var reconnectTimer = null;
  var bc = null;
  var tabId = Math.random().toString(36).slice(2) + "-" + String(Date.now());
  var isLeader = false;
  var currentLeader = null;
  var electTimer = null;
  var leaderWatchdog = null;
  var lastContent = {};   // file -> last content payload (leader 补给晚到的 tab)
  var lastEditor = {};    // file -> last editorLine payload
  var openTabs = {};      // tabId -> {file, title}
  var serverTabs = [];    // authoritative live files from SSE "tabs"
  var tabGen = 0;         // generation from /api/tab_open
  var _latestFocusClaim = { id: null, t: 0 };  // newest focus-claim seen
  try {
    if (typeof BroadcastChannel === "function") {
      bc = new BroadcastChannel("mdpp-preview-sse");
    }
  } catch (err) {
    bc = null;
  }

  function $(id) {
    return document.getElementById(id);
  }

  function saveScroll() {
    try {
      localStorage.setItem(scrollKey, String(window.scrollY || 0));
    } catch (e) {}
  }

  function restoreScroll() {
    try {
      var y = parseInt(localStorage.getItem(scrollKey) || "0", 10);
      if (y > 0) window.scrollTo(0, y);
    } catch (e) {}
  }

  function callRenderMath() {
    try {
      if (typeof window.mdppRenderMath === "function" && window.mdppRenderMath()) return;
      if (typeof window.mdppRenderMathSafe === "function") window.mdppRenderMathSafe();
    } catch (e) {}
  }

  // ── DOM update (SSE "content" event) ──────────────────────────────────

  function updateToc(tocHtml) {
    var toc = $("mdpp-toc");
    if (!toc) return;
    if (tocHtml) {
      toc.innerHTML = tocHtml;
      toc.classList.remove("mdpp-toc-empty");
    }
  }

  function applyContent(data) {
    var content = $("mdpp-content");
    if (content && typeof data.html === "string") {
      content.innerHTML = data.html;
    }
    if (typeof data.toc === "string") {
      updateToc(data.toc);
    }
    callRenderMath();
    if (typeof window.mdppRenderEcharts === "function") window.mdppRenderEcharts();
    if (typeof window.mermaid !== "undefined") {
      mermaid.run().catch(function (e) { console.warn("[MDPP] mermaid run error", e); });
    }
    bindTocClicks();
    tocActiveId = null;
    updateTocActive();
  }

  // ── SSE + BroadcastChannel ───────────────────────────────────────────
  //
  // Chrome HTTP/1.1 每 host 最多 6 条连接。各 tab 自己开 EventSource 会在
  // 第 7 个预览页卡死。这里全 origin 只让一个 leader tab 持有 /api/stream
  // (全局流,事件带 file),其它 tab 经 BroadcastChannel 收同一份推送。
  //
  // 点 .md 链接时页面往往先拿到 "Rendering..." 占位,插件稍后才 publish。
  // 跟随 tab 没有 EventSource,若错过那一次 BC 推送就会一直停在占位页,
  // 所以打开时再拉一次 /api/snapshot,并向 leader 要缓存。

  function bcSend(msg) {
    if (!bc) return;
    try { bc.postMessage(msg); } catch (err) {}
  }

  function parseEventData(raw) {
    var data = JSON.parse(raw);
    return data && typeof data === "object" ? data : {};
  }

  function eventMatchesTab(data) {
    if (!data || typeof data.file !== "string") return true;
    return data.file === channelFile;
  }

  function rememberPayload(name, data) {
    if (!data || typeof data.file !== "string") return;
    if (name === "content") lastContent[data.file] = data;
    if (name === "editorLine") lastEditor[data.file] = data;
  }

  function handleSseEvent(name, data) {
    console.log(ts() + " [MDPP] handleSseEvent name=%s file=%s tabFile=%s",
                name, data && data.file, channelFile);
    rememberPayload(name, data);
    if (name === "content") {
      if (!eventMatchesTab(data)) {
        console.log(ts() + " [MDPP] content ignored (file mismatch)");
        return;
      }
      applyContent(data);
      return;
    }
    if (name === "editorLine") {
      if (!eventMatchesTab(data)) return;
      if (data.line && data.line !== lastEditorLine) {
        lastEditorLine = data.line;
        scrollToLine(data.line);
      }
      return;
    }
    if (name === "close") {
      if (data && data.file && data.file !== channelFile) return;
      retirePreviewTab();
      return;
    }
    if (name === "close_old") {
      if (data && data.file === channelFile && Number(data.gen) === tabGen) {
        console.log(ts() + " [MDPP] close_old gen=" + tabGen);
        retirePreviewTab();
      }
      return;
    }
    if (name === "tabs") {
      if (data && data.files && data.files.length >= 0) {
        serverTabs = data.files;
        renderTabList();
      }
      return;
    }
    if (name === "pinTab") {
      _pinFile = (data && data.file) || "";
      _pinUntil = Date.now() + 2000;
      console.log(ts() + " [MDPP] pinTab file=" + _pinFile);
      return;
    }
    if (name === "switchTab") {
      console.log(ts() + " [MDPP] switchTab received file=" + (data && data.file) + " tabFile=" + channelFile);
      if (data && data.file === channelFile) {
        try { window.focus(); } catch (err) {}
      }
      return;
    }
  }

  function attachStreamHandlers(stream) {
    stream.addEventListener("content", function (e) {
      try {
        var data = parseEventData(e.data);
        handleSseEvent("content", data);
        bcSend({ type: "sse", event: "content", data: data });
      } catch (err) {
        console.warn("[MDPP] SSE content parse error", err);
      }
    });
    stream.addEventListener("editorLine", function (e) {
      try {
        var data = parseEventData(e.data);
        handleSseEvent("editorLine", data);
        bcSend({ type: "sse", event: "editorLine", data: data });
      } catch (err) {}
    });
    stream.addEventListener("close", function (e) {
      var data = {};
      try { data = parseEventData(e.data); } catch (err) {}
      bcSend({ type: "sse", event: "close", data: data });
      handleSseEvent("close", data);
    });
    stream.addEventListener("switchTab", function (e) {
      try {
        var data = parseEventData(e.data);
        handleSseEvent("switchTab", data);
        bcSend({ type: "sse", event: "switchTab", data: data });
      } catch (err) {}
    });
    stream.addEventListener("close_old", function (e) {
      try {
        var data = parseEventData(e.data);
        handleSseEvent("close_old", data);
        bcSend({ type: "sse", event: "close_old", data: data });
      } catch (err) {}
    });
    stream.addEventListener("tabs", function (e) {
      try {
        var data = parseEventData(e.data);
        handleSseEvent("tabs", data);
        bcSend({ type: "sse", event: "tabs", data: data });
      } catch (err) {}
    });
    stream.addEventListener("pinTab", function (e) {
      try {
        var data = parseEventData(e.data);
        handleSseEvent("pinTab", data);
        bcSend({ type: "sse", event: "pinTab", data: data });
      } catch (err) {}
    });
    stream.addEventListener("ping", function () {
      if (isLeader) bcSend({ type: "leader-hello", id: tabId });
    });
    // EventSource 在 CONNECTING 时也会打 error.这里若 es.close(),
    // 握手中的连接会被掐掉,之后 has_active_sse_connection 一直是 False,
    // Toggle 每次都当死标签再开一页.
    stream.onerror = function () {
      if (!stream || stream !== es) return;
      if (stream.readyState === EventSource.CONNECTING) return;
      if (stream.readyState === EventSource.OPEN) return;
      stream.close();
      if (es === stream) es = null;
      if (isLeader || !bc) {
        if (reconnectTimer) clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(connectStream, 2000);
      }
    };
  }

  function connectStream() {
    if (es) { es.close(); es = null; }
    if (cfg.mode !== "server") return;
    if (bc) {
      if (!isLeader) return;
      es = new EventSource("/api/stream");
    } else {
      if (document.hidden) return;
      es = new EventSource("/api/stream" + channelQuery);
    }
    attachStreamHandlers(es);
  }

  function disconnectStream() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    if (es) { es.close(); es = null; }
  }

  function clearLeaderWatchdog() {
    if (leaderWatchdog) { clearTimeout(leaderWatchdog); leaderWatchdog = null; }
  }

  function armLeaderWatchdog() {
    clearLeaderWatchdog();
    leaderWatchdog = setTimeout(function () {
      currentLeader = null;
      startElection();
    }, 5000);
  }

  function resignLeader() {
    if (!isLeader) return;
    isLeader = false;
    disconnectStream();
  }

  function becomeLeader() {
    if (isLeader) return;
    isLeader = true;
    currentLeader = tabId;
    clearLeaderWatchdog();
    connectStream();
    bcSend({ type: "leader-hello", id: tabId });
  }

  function onLeaderHello(id) {
    if (!id) return;
    currentLeader = id;
    if (isLeader && id !== tabId && id < tabId) {
      resignLeader();
    }
    if (id !== tabId) armLeaderWatchdog();
  }

  function startElection() {
    if (!bc) return;
    if (electTimer) clearTimeout(electTimer);
    bcSend({ type: "who-is-leader", id: tabId });
    electTimer = setTimeout(function () {
      electTimer = null;
      if (!currentLeader || currentLeader === tabId) becomeLeader();
    }, 80);
  }

  function onBcMessage(ev) {
    var msg = ev.data;
    if (!msg || !msg.type) return;
    if (msg.type === "sse") {
      handleSseEvent(msg.event, msg.data || {});
      if (currentLeader && currentLeader !== tabId) armLeaderWatchdog();
      return;
    }
    if (msg.type === "leader-hello") {
      onLeaderHello(msg.id);
      return;
    }
    if (msg.type === "leader-bye") {
      if (msg.id === currentLeader) {
        currentLeader = null;
        startElection();
      }
      return;
    }
    if (msg.type === "who-is-leader") {
      if (isLeader) bcSend({ type: "leader-hello", id: tabId });
      publishTabHello(true);
      return;
    }
    if (msg.type === "preview-visible") {
      if (msg.file) _lastPreviewVisibleFile = msg.file;
      return;
    }
    if (msg.type === "focus-claim") {
      // Tab-switch arbitration: remember the latest focus claim from any tab.
      // document.hasFocus() is unreliable with DevTools (multiple tabs report
      // true), so we use window focus events + timestamps to pick the real one.
      if (msg.t && msg.t > _latestFocusClaim.t) {
        _latestFocusClaim = { id: msg.id, t: msg.t };
      }
      return;
    }
    if (msg.type === "need-snapshot" && isLeader) {
      var f = typeof msg.file === "string" ? msg.file : "";
      if (lastContent[f]) {
        bcSend({ type: "sse", event: "content", data: lastContent[f] });
      }
      if (lastEditor[f]) {
        bcSend({ type: "sse", event: "editorLine", data: lastEditor[f] });
      }
      return;
    }
    if (msg.type === "tab-hello") {
      rememberOpenTab(msg);
      if (!msg.echo) publishTabHello(true);
      return;
    }
    if (msg.type === "tab-bye") {
      if (msg.id) delete openTabs[msg.id];
      renderTabList();
      return;
    }
    if (msg.type === "focus-tab" && msg.file === channelFile) {
      try { window.focus(); } catch (err) {}
    }
  }

  function htmlIsPlaceholder(html) {
    return !html || /Rendering[\.…]/i.test(html);
  }

  function fetchSnapshot(attempt) {
    if (cfg.mode !== "server") return;
    var n = attempt || 0;
    fetch("/api/snapshot" + channelQuery, { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var html = data && typeof data.html === "string" ? data.html : "";
        if (html && !htmlIsPlaceholder(html)) {
          handleSseEvent("content", data);
          if (data.line) handleSseEvent("editorLine", data);
          return;
        }
        if (n < 40) {
          setTimeout(function () { fetchSnapshot(n + 1); }, 50);
        }
      })
      .catch(function () {
        if (n < 40) {
          setTimeout(function () { fetchSnapshot(n + 1); }, 50);
        }
      });
  }

  function announceLeaderGone() {
    if (isLeader) {
      bcSend({ type: "leader-bye", id: tabId });
      resignLeader();
    }
  }

  function retirePreviewTab() {
    console.log(ts() + " [MDPP] retirePreviewTab gen=" + tabGen
                + " history=" + (history.length || 0));
    publishTabBye();
    announceLeaderGone();
    disconnectStream();
    try { window.close(); } catch (err) {}
    // Chrome 禁止脚本关掉地址栏 / open -a 打开的 tab。关不掉就退出会话并提示。
    setTimeout(function () {
      if (window.closed) return;
      if (document.getElementById("mdpp-replaced")) return;
      var bar = document.createElement("div");
      bar.id = "mdpp-replaced";
      bar.setAttribute("role", "status");
      bar.style.cssText = "position:sticky;top:0;z-index:99999;padding:10px 16px;"
        + "background:#3d2a00;color:#fff;font:14px/1.4 sans-serif;";
      bar.textContent = "This preview is open in another tab. You can close this one.";
      if (document.body) {
        document.body.insertBefore(bar, document.body.firstChild);
      }
      document.title = "(已替换) " + document.title;
    }, 100);
  }

  function bindBroadcast() {
    if (!bc || bindBroadcast._bound) return;
    bindBroadcast._bound = true;
    bc.onmessage = onBcMessage;
    window.addEventListener("pagehide", function (ev) {
      if (ev && ev.persisted) return;
      publishTabBye();
      announceLeaderGone();
    });
    window.addEventListener("beforeunload", function () {
      publishTabBye();
      announceLeaderGone();
      disconnectStream();
    });
    // 用户切到这个预览标签(浏览器顶部 tab 栏)时,通知服务器切 ST 文档。
    // 只用 visibilitychange:它只在 tab 真正从 hidden->visible 时触发,
    // 不会像 window.focus 那样在被切走的 tab 上也误触发。
    document.addEventListener("visibilitychange", onVisibilityChange);
    // Tab-switch detection via window focus + BC timestamp arbitration.
    // document.hasFocus() is unreliable with DevTools open (multiple tabs
    // report true), and visibilitychange doesn't fire either. So every tab
    // broadcasts a focus-claim on window focus; after a short delay only the
    // tab with the newest claim notifies ST.
    window.addEventListener("focus", onWindowFocus);
    console.log(ts() + " [MDPP] bindBroadcast done, focus arbitration armed file=" + channelFile);
    publishTabHello(false);
  }

  // 无 BroadcastChannel 时退回「仅可见 tab 持有 SSE」
  // 有 BroadcastChannel 时也监听 visibilitychange:用户切回一个已有的
  // 预览标签时,通知服务器切换 ST 到对应文档(单向 ST←browser doc switch)。
  // ── doc switch notification (browser tab → ST) ──────────────────────
  // When the user switches to a preview tab via the browser's tab bar,
  // notify the server so ST focuses the matching editor view.
  // We throttle + deduplicate to avoid loops (ST render → SSE push →
  // DOM update → spurious focus event → another notification).

  var _lastNotifyFile = "";
  var _lastNotifyTime = 0;
  var _pinFile = "";
  var _pinUntil = 0;
  var _lastPreviewVisibleFile = "";

  function notifyDocSwitch() {
    if (cfg.mode !== "server" || !channelFile) {
      return;
    }
    var now = Date.now();
    if (_pinFile && now < _pinUntil && channelFile !== _pinFile) {
      console.log(ts() + " [MDPP] notifyDocSwitch skipped (pin) file=" + channelFile);
      return;
    }
    // Deduplicate: don't notify for the same file within 3 seconds
    if (channelFile === _lastNotifyFile && (now - _lastNotifyTime) < 3000) {
      return;
    }
    _lastNotifyFile = channelFile;
    _lastNotifyTime = now;
    console.log(ts() + " [MDPP] notifyDocSwitch file=" + channelFile);
    fetch("/api/open_doc?file=" + encodeURIComponent(channelFile)
          + "&tab_switch=1",
          { cache: "no-store" }).catch(function (e) {
      console.log(ts() + " [MDPP] notifyDocSwitch fetch error: " + e);
    });
  }

  function onBecameVisible() {
    if (!channelFile || document.hidden) return;
    if (_pinFile && Date.now() < _pinUntil && channelFile !== _pinFile) {
      console.log(ts() + " [MDPP] visible skipped (pin) file=" + channelFile);
      return;
    }
    // 同一份预览 tab 再次 visible = Chrome 窗口重新获焦,不是切 tab。
    if (_lastPreviewVisibleFile === channelFile) {
      console.log(ts() + " [MDPP] notifyDocSwitch skipped (window refocus) file=" + channelFile);
      return;
    }
    _lastPreviewVisibleFile = channelFile;
    bcSend({ type: "preview-visible", file: channelFile });
    notifyDocSwitch();
  }

  function onVisibilityChange() {
    console.log(ts() + " [MDPP] visibilitychange hidden=" + document.hidden + " file=" + channelFile);
    // Leader keeps /api/stream while hidden. Without BroadcastChannel we still
    // drop SSE on hide so Chrome's 6-connection cap is not filled by background tabs.
    if (!bc) {
      if (document.hidden) {
        disconnectStream();
      } else {
        connectStream();
        onBecameVisible();
      }
      return;
    }
    if (!document.hidden) {
      onBecameVisible();
    }
  }

  // Window focus fires on BOTH tabs when switching (Chrome quirk with
  // DevTools). Broadcast a timestamped claim; after 150ms only the tab with
  // the newest claim (i.e. the one the user actually switched TO) notifies.
  function onWindowFocus() {
    if (document.hidden) return;
    var myT = Date.now();
    bcSend({ type: "focus-claim", id: tabId, t: myT });
    setTimeout(function () {
      if (document.hidden) return;
      if (myT > _latestFocusClaim.t) {
        console.log(ts() + " [MDPP] focus arbitration won file=" + channelFile);
        onBecameVisible();
      } else {
        console.log(ts() + " [MDPP] focus arbitration lost (newer claim) file=" + channelFile);
      }
    }, 150);
  }


  function bindVisibility() {
    if (bindVisibility._bound) return;
    bindVisibility._bound = true;
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("beforeunload", function () {
      if (es) { es.close(); es = null; }
    });
  }

  // ── Preview tabs (侧栏上方的打开文档列表,TOC 在下) ───────────────────

  function fileBasename(path) {
    if (!path) return document.title || "Preview";
    var i = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
    return i >= 0 ? path.slice(i + 1) : path;
  }

  function escHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function currentTabMeta() {
    return { file: channelFile, title: fileBasename(channelFile) };
  }

  function publishTabHello(echo) {
    var meta = currentTabMeta();
    bcSend({
      type: "tab-hello",
      id: tabId,
      file: meta.file,
      title: meta.title,
      echo: !!echo,
    });
  }

  function publishTabBye() {
    bcSend({ type: "tab-bye", id: tabId });
    if (cfg.mode !== "server" || !channelFile || !tabGen) return;
    var url = "/api/tab_close?file=" + encodeURIComponent(channelFile)
      + "&gen=" + tabGen + "&hist=" + (history.length || 0);
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon(url);
        return;
      }
    } catch (err) {}
    fetch(url, { method: "POST", cache: "no-store", keepalive: true }).catch(function () {});
  }

  function announceTab() {
    if (cfg.mode !== "server" || !channelFile) {
      return Promise.resolve(false);
    }
    return fetch("/api/tab_open?file=" + encodeURIComponent(channelFile), { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        tabGen = data && data.gen ? data.gen : 0;
        if (data && data.files) {
          serverTabs = data.files;
          renderTabList();
        }
        console.log(ts() + " [MDPP] tab_open gen=" + tabGen);
        var html = data && typeof data.html === "string" ? data.html : "";
        if (html && !htmlIsPlaceholder(html)) {
          handleSseEvent("content", data);
          if (data.line) handleSseEvent("editorLine", data);
          return true;
        }
        return false;
      })
      .catch(function (err) {
        console.log(ts() + " [MDPP] tab_open failed: " + err);
        return false;
      });
  }

  function rememberOpenTab(msg) {
    if (!msg || !msg.id || msg.id === tabId) return;
    openTabs[msg.id] = {
      file: typeof msg.file === "string" ? msg.file : "",
      title: msg.title || fileBasename(msg.file),
    };
    renderTabList();
  }

  function fileIsAlive(file) {
    if (!file) return false;
    if (file === channelFile) return true;
    if (serverTabs.indexOf(file) !== -1) return true;
    var ids = Object.keys(openTabs);
    for (var i = 0; i < ids.length; i++) {
      if (openTabs[ids[i]] && openTabs[ids[i]].file === file) return true;
    }
    return false;
  }

  function collectedTabs() {
    var byFile = {};
    byFile[channelFile || ""] = { file: channelFile, title: fileBasename(channelFile) };
    serverTabs.forEach(function (f) {
      if (!byFile[f]) byFile[f] = { file: f, title: fileBasename(f) };
    });
    Object.keys(openTabs).forEach(function (id) {
      var it = openTabs[id];
      var key = it.file || "";
      if (!byFile[key]) byFile[key] = { file: key, title: it.title || fileBasename(key) };
    });
    return Object.keys(byFile).sort(function (a, b) {
      return (byFile[a].title || "").localeCompare(byFile[b].title || "");
    }).map(function (k) { return byFile[k]; });
  }

  function renderTabList() {
    var list = $("mdpp-tabs-list");
    if (!list) return;
    var items = collectedTabs();
    var html = "";
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      var active = it.file === channelFile ? " mdpp-tabs-active" : "";
      html += '<li class="mdpp-tabs-item' + active + '">'
        + '<a href="/?file=' + encodeURIComponent(it.file) + '" data-file="'
        + escHtml(it.file) + '">' + escHtml(it.title) + "</a></li>";
    }
    list.innerHTML = html;
  }

  function fileFromHref(href) {
    if (!href) return "";
    try {
      var u = new URL(href, window.location.href);
      if (u.origin !== window.location.origin) return "";
      if (u.pathname !== "/" && u.pathname !== "") return "";
      return u.searchParams.get("file") || "";
    } catch (err) {
      return "";
    }
  }

  function switchToPreview(file) {
    if (!file || file === channelFile) return;
    var url = "/?file=" + encodeURIComponent(file);
    var name = windowNameFor(file);
    var alive = fileIsAlive(file);
    // User gesture: window.open(url, name) either reuses a named window or
    // opens one in front. If a second tab is created, tab_open + close_old
    // keeps 1:1. Empty-url open is not used (about:blank on OS-opened tabs).
    // 尚未有活 tab 时 GET /?file= 会 queue ST,不必再打一遍 open_doc。
    try {
      window.open(url, name);
    } catch (err) {
      window.location.href = url;
    }
    bcSend({ type: "focus-tab", file: file });
    if (cfg.mode === "server" && alive) {
      fetch("/api/open_doc?file=" + encodeURIComponent(file) + "&tab_switch=1",
            { cache: "no-store" }).catch(function () {});
    }
  }

  function bindTabList() {
    var nav = $("mdpp-tabs");
    if (!nav || bindTabList._bound) return;
    bindTabList._bound = true;
    nav.addEventListener("click", function (ev) {
      var a = ev.target.closest ? ev.target.closest("a") : null;
      if (!a || !nav.contains(a)) return;
      ev.preventDefault();
      var file = a.getAttribute("data-file") || fileFromHref(a.getAttribute("href") || "");
      switchToPreview(file);
    });
    renderTabList();
  }

  function bindPreviewDocLinks() {
    if (bindPreviewDocLinks._bound) return;
    bindPreviewDocLinks._bound = true;
    document.addEventListener("click", function (ev) {
      if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) {
        return;
      }
      var a = ev.target.closest ? ev.target.closest("a") : null;
      if (!a) return;
      var file = fileFromHref(a.getAttribute("href") || "");
      if (!file) return;
      ev.preventDefault();
      switchToPreview(file);
    }, false);
  }

  // ── TOC ──────────────────────────────────────────────────────────────

  function bindTocClicks() {
    var toc = $("mdpp-toc");
    if (!toc) return;
    toc.onclick = function (ev) {
      var a = ev.target.closest ? ev.target.closest("a") : null;
      if (!a) return;
      var href = a.getAttribute("href") || "";
      if (href.charAt(0) === "#") {
        var id = decodeURIComponent(href.slice(1));
        var el = document.getElementById(id);
        if (el) {
          ev.preventDefault();
          el.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    };
  }

  // ── TOC scrollspy:滚动时高亮当前 section ─────────────────────────────

  var tocActiveId = null;

  function updateTocActive() {
    var toc = $("mdpp-toc");
    if (!toc) return;
    // 找视口顶部所在 section:最后一个 top <= 阈值的标题
    var headings = document.querySelectorAll("#mdpp-content h1[id], #mdpp-content h2[id], #mdpp-content h3[id], #mdpp-content h4[id], #mdpp-content h5[id], #mdpp-content h6[id]");
    var currentId = null;
    for (var i = 0; i < headings.length; i++) {
      if (headings[i].getBoundingClientRect().top <= 100) {
        currentId = headings[i].id;
      } else {
        break;
      }
    }
    if (currentId === tocActiveId) return;
    tocActiveId = currentId;
    var links = toc.querySelectorAll("a[href^='#']");
    var activeLink = null;
    for (var j = 0; j < links.length; j++) {
      var link = links[j];
      var isActive = currentId !== null &&
        decodeURIComponent(link.getAttribute("href").slice(1)) === currentId;
      link.classList.toggle("mdpp-toc-active", isActive);
      if (isActive) activeLink = link;
    }
    // TOC 跟随滚动,保持当前项可见
    if (activeLink && toc.scrollHeight > toc.clientHeight) {
      var top = activeLink.offsetTop - toc.clientHeight / 2;
      toc.scrollTop = Math.max(0, top);
    }
  }

  // ── scroll sync (browser → editor) ───────────────────────────────────

  function findNearestLine() {
    var nodes = document.querySelectorAll("[data-line]");
    var best = 0;
    var bestTop = -Infinity;
    var viewTop = window.scrollY || 0;
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var top = el.getBoundingClientRect().top + viewTop;
      var line = parseInt(el.getAttribute("data-line"), 10) || 0;
      if (top <= viewTop + 80 && top > bestTop) {
        bestTop = top;
        best = line;
      }
    }
    return best;
  }

  function reportBrowserScroll() {
    if (cfg.mode !== "server" || !cfg.scrollSync) return;
    var line = findNearestLine();
    if (!line || line === lastReportedLine) return;
    lastReportedLine = line;
    fetch("/api/browser_scroll", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ line: line, file: channelFile }),
    }).catch(function () {});
  }

  function scrollToLine(line) {
    if (!line) return;
    var nodes = document.querySelectorAll("[data-line]");
    var target = null;
    var bestDiff = Infinity;
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var l = parseInt(el.getAttribute("data-line"), 10) || 0;
      var diff = Math.abs(l - line);
      if (diff < bestDiff) { bestDiff = diff; target = el; }
      if (l === line) { target = el; break; }
    }
    if (target) {
      target.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  }

  function onScroll() {
    saveScroll();
    updateTocActive();
    if (cfg.scrollSync) {
      if (onScroll._t) clearTimeout(onScroll._t);
      onScroll._t = setTimeout(reportBrowserScroll, 150);
    }
  }

  // ── export buttons ───────────────────────────────────────────────────

  function setExportLoading(btnId, loading) {
    var btn = $(btnId);
    if (!btn) return;
    if (loading) {
      btn.disabled = true;
      btn.setAttribute("data-orig-text", btn.textContent);
      btn.textContent = "⏳";
      btn.classList.add("mdpp-btn-loading");
    } else {
      btn.disabled = false;
      var orig = btn.getAttribute("data-orig-text");
      if (orig) btn.textContent = orig;
      btn.classList.remove("mdpp-btn-loading");
    }
  }

  function downloadBlob(blob, filename) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  window.mdppExportPng = function mdppExportPng() {
    setExportLoading("mdpp-export-png", true);
    var target = document.getElementById("mdpp-content") || document.body;
    try {
      html2canvas(target, {
        scale: 2,
        useCORS: true,
        allowTaint: true,
        backgroundColor: "#ffffff",
      }).then(function (canvas) {
        canvas.toBlob(function (blob) {
          var title = (document.title || "export").replace(/[^\w.-]/g, "_");
          downloadBlob(blob, title + ".png");
          setExportLoading("mdpp-export-png", false);
        }, "image/png");
      }).catch(function (err) {
        setExportLoading("mdpp-export-png", false);
        alert("PNG export failed.\n\n" + (err.message || ""));
      });
    } catch (err) {
      setExportLoading("mdpp-export-png", false);
      alert("PNG export requires html2canvas. Please check the browser console.");
    }
  };

  window.mdppExportHtml = function mdppExportHtml() {
    setExportLoading("mdpp-export-html", true);
    fetch("/api/export/html" + channelQuery)
      .then(function (r) {
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.error || "export failed"); });
        return r.blob();
      })
      .then(function (blob) {
        var title = (document.title || "export").replace(/[^\w.-]/g, "_");
        downloadBlob(blob, title + ".html");
        setExportLoading("mdpp-export-html", false);
      })
      .catch(function (err) {
        setExportLoading("mdpp-export-html", false);
        // Fallback: download current DOM
        try {
          var html = document.documentElement.outerHTML;
          var title = (document.title || "export").replace(/[^\w.-]/g, "_");
          downloadBlob(new Blob(["<!DOCTYPE html>\n" + html], { type: "text/html" }), title + ".html");
        } catch (e) {}
      });
  };

  window.mdppCloseSponsor = function mdppCloseSponsor() {
    var el = $("mdpp-sponsor-modal");
    if (el) el.hidden = true;
  };

  window.mdppShowSponsor = function mdppShowSponsor() {
    var el = $("mdpp-sponsor-modal");
    if (el) el.hidden = false;
  };

  // ── presentation mode ─────────────────────────────────────────────────

  window.mdppOpenPresentation = function mdppOpenPresentation() {
    // Reuse the current URL's ?file= param (or channelQuery) so the
    // presentation page shows the same document.
    var q = channelQuery || "";
    window.open("/presentation" + q, "_blank");
  };

  // ── init ─────────────────────────────────────────────────────────────

  window.mdppInit = function mdppInit() {
    console.log(ts() + " [MDPP] mdppInit called, bc=" + (typeof BroadcastChannel !== "undefined") + " mode=" + cfg.mode + " file=" + channelFile);
    restoreScroll();
    callRenderMath();
    bindTabList();
    bindPreviewDocLinks();
    bindTocClicks();
    updateTocActive();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("beforeunload", saveScroll);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") window.mdppCloseSponsor();
    });

    if (cfg.mode === "server") {
      // 本页 GET /?file= 已经 queue 过 ST,启动时的 focus 不再打 open_doc。
      _lastNotifyFile = channelFile;
      _lastNotifyTime = Date.now();
      _lastPreviewVisibleFile = channelFile;
      announceTab().then(function (hasHtml) {
        if (bc) {
          bindBroadcast();
          if (!document.hidden) {
            bcSend({ type: "preview-visible", file: channelFile });
          }
          if (!hasHtml) {
            fetchSnapshot();
            bcSend({ type: "need-snapshot", file: channelFile, id: tabId });
          }
          startElection();
        } else {
          bindVisibility();
          if (!hasHtml) fetchSnapshot();
          connectStream();
        }
      });
    }
  };
})();
