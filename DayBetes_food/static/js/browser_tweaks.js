(function () {
  // iOS zooms the page in when a field with a font under 16px gets the focus,
  // and does not zoom back out. With maximum-scale=1 it no longer does it,
  // while pinch zoom keeps working (iOS ignores the cap for the user's own
  // gesture). Only on iOS: Android does not zoom on focus, and there the
  // cap would also block pinch zoom (frontend_conventions.md §2).
  var ua = navigator.userAgent || "";
  var iOS = /iP(hone|ad|od)/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (!iOS) return;

  function capZoom() {
    document.querySelectorAll('meta[name="viewport"]').forEach(function (meta) {
      var content = meta.getAttribute("content") || "";
      if (/maximum-scale/.test(content)) return;
      meta.setAttribute("content", content + ", maximum-scale=1");
    });
  }

  capZoom();
  document.addEventListener("DOMContentLoaded", capZoom);
})();

(function () {
  function detectIosSafari() {
    var ua = navigator.userAgent || "";
    var iOS = /iP(hone|ad|od)/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    var webkit = /WebKit/i.test(ua);
    var otherIosBrowser = /CriOS|FxiOS|EdgiOS|OPiOS/i.test(ua);
    return iOS && webkit && !otherIosBrowser;
  }

  function applyClass() {
    if (!document.documentElement) return;
    if (detectIosSafari()) {
      document.documentElement.classList.add("ios-safari");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyClass);
  } else {
    applyClass();
  }
})();

(function () {
  function lockHistoryForMutations(event) {
    var detail = event && event.detail ? event.detail : null;
    var cfg = detail && detail.requestConfig ? detail.requestConfig : null;
    if (!cfg) return;

    var verb = String(cfg.verb || "get").toLowerCase();
    if (verb === "get") return;

    // Keep URL/history stable for mutating HTMX requests.
    cfg.pushURL = false;
    cfg.replaceURL = false;
  }

  function bind() {
    if (!document.body) return;
    document.body.addEventListener("htmx:beforeRequest", lockHistoryForMutations);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
