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

  function syncFoodTopSpacing(force) {
    var topBar = byId("food_top_bar");
    var wrapper = byId("food_list_wrapper");
    if (!topBar || !wrapper) return;
    var rect = topBar.getBoundingClientRect();
    var safeGap = 12;
    var requiredTop = Math.max(180, Math.ceil(rect.bottom + safeGap));
    var currentTop = parseFloat(window.getComputedStyle(wrapper).paddingTop || "0") || 0;
    // Avoid visual jump on initial load: don't reduce spacing unless explicitly forced (e.g. resize).
    if (!force && requiredTop < currentTop) return;
    wrapper.style.paddingTop = requiredTop + "px";
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

  function waitForImages(container, timeoutMs) {
    var root = container || byId("main_content");
    if (!root) return Promise.resolve();
    var imgs = Array.prototype.slice.call(root.querySelectorAll("img")).filter(function (img) {
      return !img.complete;
    });
    if (!imgs.length) return Promise.resolve();

    return new Promise(function (resolve) {
      var done = false;
      var pending = imgs.length;
      var timer = window.setTimeout(function () {
        if (done) return;
        done = true;
        resolve();
      }, timeoutMs || 550);

      function completeOne() {
        if (done) return;
        pending -= 1;
        if (pending <= 0) {
          done = true;
          window.clearTimeout(timer);
          resolve();
        }
      }

      imgs.forEach(function (img) {
        img.addEventListener("load", completeOne, { once: true });
        img.addEventListener("error", completeOne, { once: true });
      });
    });
  }

  function bindListeners() {
    document.body.addEventListener("htmx:beforeRequest", function (event) {
      var elt = event && event.detail ? event.detail.elt : null;
      var xhr = event && event.detail ? event.detail.xhr : null;
      var target = event && event.detail ? event.detail.target : null;
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
      syncFoodTopSpacing(false);
      if (canHideOverlay()) setLoading(false);
    });

    document.body.addEventListener("htmx:afterSettle", function (event) {
      var target = event && event.detail ? event.detail.target : null;
      if (!isMainTarget(target)) return;
      waitForImages(target, 550).then(function () {
        syncFoodTopSpacing(false);
      });
    });

    document.body.addEventListener("htmx:responseError", function () {
      pendingRequests = 0;
      var main = byId("main_content");
      if (main) {
        main.style.removeProperty("visibility");
        main.style.removeProperty("opacity");
      }
      setLoading(false);
    });

    window.addEventListener("resize", function () {
      syncFoodTopSpacing(true);
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
      syncFoodTopSpacing(false);
    });
  } else {
    bindListeners();
    syncFoodTopSpacing(false);
  }
})();
