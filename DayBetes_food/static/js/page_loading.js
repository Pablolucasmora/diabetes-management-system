(function () {
  var pendingRequests = 0;
  var overlayShownAt = 0;
  var hideTimer = null;
  var showTimer = null;
  // A quick answer shows no overlay at all: it is only for slow ones
  // (frontend_conventions.md §10).
  var SHOW_DELAY_MS = 400;
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

  function cancelShow() {
    if (showTimer) window.clearTimeout(showTimer);
    showTimer = null;
  }

  function hideOverlay() {
    cancelShow();
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
      if (!showTimer) {
        showTimer = window.setTimeout(function () {
          showTimer = null;
          if (pendingRequests > 0) showOverlay();
        }, SHOW_DELAY_MS);
      }
      return;
    }
    if (canHideOverlay()) hideOverlay();
  }

  function bindListeners() {
    // A request counts from the moment it is sent (htmx:beforeSend) until the
    // browser ends it (loadend, which also comes after an error, an abort or a
    // timeout). htmx's beforeRequest/afterRequest pair is not enough: a request
    // cancelled at beforeRequest (a swipe answering it with the page in memory,
    // frontend_conventions.md §13; the preload extension, §12) never gets its
    // afterRequest, nor one whose element is gone by the time it is answered
    // (a cart card repainted meanwhile), and Loading... then stayed on.
    var listRequests = 0;

    document.body.addEventListener("htmx:beforeSend", function (event) {
      var detail = event && event.detail ? event.detail : {};
      var xhr = detail.xhr;
      if (!xhr) return;
      var config = detail.requestConfig;
      if (config && config.headers && config.headers["HX-Preloaded"] === "true") return;
      var forList = isFoodListTarget(detail.target);
      if (forList) {
        listRequests += 1;
        setFoodListLoading(true);
      }
      var elt = detail.elt;
      var skip = !!(elt && elt.closest && elt.closest("[data-skip-page-loading='true']"));
      if (!skip) {
        pendingRequests += 1;
        setLoading(true);
      }
      xhr.addEventListener("loadend", function () {
        if (forList) {
          listRequests = Math.max(0, listRequests - 1);
          if (listRequests === 0) setFoodListLoading(false);
        }
        if (skip) return;
        pendingRequests = Math.max(0, pendingRequests - 1);
        if (pendingRequests === 0) setLoading(false);
      });
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
      cancelShow();
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
