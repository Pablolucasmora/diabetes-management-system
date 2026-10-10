(function () {
  var pendingRequests = 0;
  var overlayShownAt = 0;
  var hideTimer = null;
  var MIN_OVERLAY_MS = 140;

  function byId(id) {
    return document.getElementById(id);
  }

  function isMainTarget(target) {
    return !!(target && target.id === "main_content");
  }

  function isFoodListTarget(target) {
    return !!(target && target.id === "food-list");
  }

  function setFoodListLoading(active) {
    var list = byId("food-list");
    if (!list) return;
    if (active) {
      list.classList.add("opacity-55", "scale-[0.995]", "pointer-events-none");
      return;
    }
    list.classList.remove("opacity-55", "scale-[0.995]", "pointer-events-none");
  }

  function canHideOverlay() {
    return pendingRequests === 0;
  }

  function showOverlay() {
    var overlay = byId("page_loading_overlay");
    if (!overlay) return;

    if (hideTimer) {
      window.clearTimeout(hideTimer);
      hideTimer = null;
    }
    overlayShownAt = Date.now();
    overlay.classList.remove("invisible", "opacity-0");
    window.requestAnimationFrame(function () {
      overlay.classList.add("opacity-100");
    });
  }

  function hideOverlay() {
    var overlay = byId("page_loading_overlay");
    if (!overlay) return;
    var elapsed = Date.now() - overlayShownAt;
    var delay = Math.max(0, MIN_OVERLAY_MS - elapsed);

    if (hideTimer) window.clearTimeout(hideTimer);
    hideTimer = window.setTimeout(function () {
      overlay.classList.remove("opacity-100");
      overlay.classList.add("opacity-0");
      window.setTimeout(function () {
        if (overlay.classList.contains("opacity-0")) {
          overlay.classList.add("invisible");
        }
      }, 260);
    }, delay);
  }

  function setLoading(active) {
    if (active) {
      showOverlay();
      return;
    }
    if (canHideOverlay()) hideOverlay();
  }

  function bindListeners() {
    document.body.addEventListener("htmx:beforeRequest", function (event) {
      var elt = event && event.detail ? event.detail.elt : null;
      var xhr = event && event.detail ? event.detail.xhr : null;
      var target = event && event.detail ? event.detail.target : null;
      if (isFoodListTarget(target)) setFoodListLoading(true);
      var skip = !!(elt && elt.closest && elt.closest("[data-skip-page-loading='true']"));
      if (xhr) xhr.__skipPageLoading = skip;
      if (skip) return;
      pendingRequests += 1;
      setLoading(true);
    });

    function maybeStopLoading(event) {
      var xhr = event && event.detail ? event.detail.xhr : null;
      if (xhr && xhr.__skipPageLoading) return;
      pendingRequests = Math.max(0, pendingRequests - 1);
      if (pendingRequests === 0) setLoading(false);
    }

    document.body.addEventListener("htmx:afterRequest", function (event) {
      maybeStopLoading(event);
    });

    document.body.addEventListener("htmx:afterSwap", function (event) {
      var target = event && event.detail ? event.detail.target : null;
      if (isMainTarget(target)) {
        target.style.removeProperty("visibility");
        target.style.removeProperty("opacity");
      }
      if (isFoodListTarget(target)) setFoodListLoading(false);
      if (canHideOverlay()) setLoading(false);
    });

    document.body.addEventListener("htmx:responseError", function (event) {
      var detail = event && event.detail ? event.detail : {};
      var xhr = detail.xhr;
      var target = detail.target;
      if (xhr && xhr.status === 422 && target && xhr.responseText) {
        target.innerHTML = xhr.responseText;
      }
      pendingRequests = 0;
      setFoodListLoading(false);
      var main = byId("main_content");
      if (main) {
        main.style.removeProperty("visibility");
        main.style.removeProperty("opacity");
      }
      setLoading(false);
    });

    // Safari BFCache can restore the page with overlay visible.
    window.addEventListener("pageshow", function () {
      pendingRequests = 0;
      var overlay = byId("page_loading_overlay");
      if (!overlay) return;
      if (hideTimer) {
        window.clearTimeout(hideTimer);
        hideTimer = null;
      }
      overlay.classList.remove("opacity-100");
      overlay.classList.add("opacity-0", "invisible");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      bindListeners();
    });
  } else {
    bindListeners();
  }
})();
