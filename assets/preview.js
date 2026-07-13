/* MarkdownPreviewEnhanced client: SSE push, TOC, scroll sync, export */
(function () {
  "use strict";

  var cfg = window.MDPP_CONFIG || { mode: "file", scrollSync: true, showToc: true };
  var scrollKey = "mdpp-scroll-y";
  var lastReportedLine = 0;
  var lastEditorLine = 0;
  var es = null;           // EventSource
  var reconnectTimer = null;

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
  }

  // ── SSE connection ────────────────────────────────────────────────────

  function connectStream() {
    if (es) { es.close(); es = null; }
    if (cfg.mode !== "server") return;

    es = new EventSource("/api/stream");

    es.addEventListener("content", function (e) {
      try {
        applyContent(JSON.parse(e.data));
      } catch (err) {
        console.warn("[MDPP] SSE content parse error", err);
      }
    });

    es.addEventListener("editorLine", function (e) {
      try {
        var d = JSON.parse(e.data);
        if (d.line && d.line !== lastEditorLine) {
          lastEditorLine = d.line;
          scrollToLine(d.line);
        }
      } catch (err) {}
    });

    es.onerror = function () {
      es.close();
      es = null;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(connectStream, 2000);
    };

    // Close on page unload
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
      body: JSON.stringify({ line: line }),
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
    fetch("/api/export/html")
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

  // ── init ─────────────────────────────────────────────────────────────

  window.mdppInit = function mdppInit() {
    restoreScroll();
    callRenderMath();
    bindTocClicks();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("beforeunload", saveScroll);

    if (cfg.mode === "server") {
      connectStream();
    }
  };
})();
