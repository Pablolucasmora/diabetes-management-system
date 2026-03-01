(function () {
  var pendingRequests = 0;

  function byId(id) {
    return document.getElementById(id);
  }

  function setLoading(active) {
    var overlay = byId("page_loading_overlay");
    var main = byId("main_content");
    if (!overlay || !main) return;

    if (active) {
      overlay.classList.remove("invisible", "opacity-0");
      window.requestAnimationFrame(function () {
        overlay.classList.add("opacity-100");
      });
      main.style.opacity = "0.28";
      main.style.filter = "blur(1.2px)";
      return;
    }

    overlay.classList.remove("opacity-100");
    overlay.classList.add("opacity-0");
    window.setTimeout(function () {
      if (overlay.classList.contains("opacity-0")) {
        overlay.classList.add("invisible");
      }
    }, 260);
    window.requestAnimationFrame(function () {
      main.style.opacity = "1";
      main.style.filter = "none";
    });
  }

  function bindListeners() {
    document.body.addEventListener("htmx:beforeRequest", function () {
      pendingRequests += 1;
      setLoading(true);
    });

    function maybeStopLoading() {
      pendingRequests = Math.max(0, pendingRequests - 1);
      if (pendingRequests === 0) setLoading(false);
    }

    document.body.addEventListener("htmx:afterRequest", function () {
      maybeStopLoading();
    });

    document.body.addEventListener("htmx:afterSwap", function () {
      if (pendingRequests === 0) setLoading(false);
    });

    document.body.addEventListener("htmx:responseError", function () {
      pendingRequests = 0;
      setLoading(false);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindListeners);
  } else {
    bindListeners();
  }
})();
