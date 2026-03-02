(function () {
  var pendingRequests = 0;
  var overlayShownAt = 0;
  var hideTimer = null;
  var MIN_OVERLAY_MS = 140;
  var pendingMainReveal = 0;

  function byId(id) {
    return document.getElementById(id);
  }

  function isMainTarget(target) {
    return !!(target && target.id === "main_content");
  }

  function animateElement(el, keyframes, options) {
    if (!el || !el.animate) return;
    try {
      el.animate(keyframes, options);
    } catch (_) {
      // Ignore animation failures and keep UX functional.
    }
  }

  function canHideOverlay() {
    return pendingRequests === 0 && pendingMainReveal === 0;
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
      if (xhr) xhr.__mainNavigation = isMainTarget(target);
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

    document.body.addEventListener("htmx:afterSwap", function () {
      if (canHideOverlay()) setLoading(false);
    });

    // For full-page swaps, keep new content hidden until settle+assets are ready.
    document.body.addEventListener("htmx:beforeSwap", function (event) {
      var xhr = event && event.detail ? event.detail.xhr : null;
      var target = event && event.detail ? event.detail.target : null;
      if (!(xhr && xhr.__mainNavigation)) return;
      if (!isMainTarget(target)) return;
      pendingMainReveal += 1;
      target.style.visibility = "hidden";
      target.style.opacity = "0";
    });

    document.body.addEventListener("htmx:afterSettle", function (event) {
      var xhr = event && event.detail ? event.detail.xhr : null;
      var target = event && event.detail ? event.detail.target : null;
      if (!(xhr && xhr.__mainNavigation)) return;
      if (!isMainTarget(target)) return;

      waitForImages(target, 550).then(function () {
        target.style.visibility = "visible";
        animateElement(
          target,
          [{ opacity: 0 }, { opacity: 1 }],
          { duration: 170, easing: "ease-out", fill: "forwards" }
        );
        pendingMainReveal = Math.max(0, pendingMainReveal - 1);
        if (canHideOverlay()) setLoading(false);
      });
    });

    document.body.addEventListener("htmx:responseError", function () {
      pendingRequests = 0;
      pendingMainReveal = 0;
      var main = byId("main_content");
      if (main) {
        main.style.visibility = "visible";
        main.style.opacity = "1";
      }
      setLoading(false);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindListeners);
  } else {
    bindListeners();
  }
})();
