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
