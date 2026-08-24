/* MarkdownPreviewEnhanced client: SSE push, TOC, scroll sync, export */
(function () {
  "use strict";

  var cfg = window.MDPP_CONFIG || { mode: "file", scrollSync: true, showToc: true };

  // 频道标识:地址栏 ?file= 参数,决定 SSE/滚动上报归属哪个文档
  var channelFile = "";
  try {
    channelFile = new URLSearchParams(window.location.search).get("file") || "";
  } catch (err) {}
  var channelQuery = channelFile ? "?file=" + encodeURIComponent(channelFile) : "";
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
    rememberPayload(name, data);
    if (name === "content") {
      if (!eventMatchesTab(data)) return;
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
      window.close();
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
    stream.addEventListener("ping", function () {
      if (isLeader) bcSend({ type: "leader-hello", id: tabId });
    });
    // EventSource 在 CONNECTING 时也会打 error.这里若 es.close(),
    // 握手中的连接会被掐掉,之后 has_sse_clients 一直是 False,
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
    if (msg.type === "who-is-leader" && isLeader) {
      bcSend({ type: "leader-hello", id: tabId });
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

  function bindBroadcast() {
    if (!bc || bindBroadcast._bound) return;
    bindBroadcast._bound = true;
    bc.onmessage = onBcMessage;
    window.addEventListener("pagehide", function (ev) {
      if (ev && ev.persisted) return;
      announceLeaderGone();
    });
    window.addEventListener("beforeunload", function () {
      announceLeaderGone();
      disconnectStream();
    });
  }

  // 无 BroadcastChannel 时退回「仅可见 tab 持有 SSE」
  function onVisibilityChange() {
    if (document.hidden) {
      disconnectStream();
    } else {
      connectStream();
    }
  }

  function bindVisibility() {
    if (bindVisibility._bound) return;
    bindVisibility._bound = true;
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("beforeunload", function () {
      if (es) { es.close(); es = null; }
    });
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

  // ── init ─────────────────────────────────────────────────────────────

  window.mdppInit = function mdppInit() {
    restoreScroll();
    callRenderMath();
    bindTocClicks();
    updateTocActive();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("beforeunload", saveScroll);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") window.mdppCloseSponsor();
    });

    if (cfg.mode === "server") {
      if (bc) {
        bindBroadcast();
        fetchSnapshot();
        bcSend({ type: "need-snapshot", file: channelFile, id: tabId });
        startElection();
      } else {
        bindVisibility();
        fetchSnapshot();
        connectStream();
      }
    }
  };
})();
