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
