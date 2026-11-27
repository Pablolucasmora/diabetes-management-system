// Preload on touch (frontend_conventions.md §12), with htmx's `preload`
// extension. This file decides when: it sends the marked element's own GET
// (`data-preload`, with its `hx-get`) with `HX-Preloaded: true`, and the
// extension stops that request before any swap and keeps its response. Not the
// extension's own listeners: they skip a control inside a label, which is
// what the island's items are, and fire on every touch of a scrolled list.
//
// - A finger: once it has rested 60 ms without moving. A mouse: on press.
// - A tap on a label preloads its control (the island's hidden radios).
// - Nothing inside a row's own controls (`data-no-open`): the star or `+`.
// - Once per element every 10 s, the time the response is kept.
//
// The server keeps a preloaded response 10 s in the browser cache, varying on
// `X-Data-Version` (main.py). That number goes up after every successful save,
// so a page preloaded before a change is never shown after it.
(function () {
  if (window.__dbPreload) return;
  window.__dbPreload = true;

  var REST_MS = 60;
  var KEPT_MS = 10000;
  var MOVE_PX = 10;
  // Starts from the load time, so a reload never reuses an older number.
  var dataVersion = Date.now();

  function preloadTarget(target) {
    if (!target || !target.closest || target.closest("[data-no-open]")) return null;
    var label = target.closest("label");
    if (label) {
      var control = label.querySelector("[data-preload][hx-get]");
      if (control) return control;
    }
    return target.closest("[data-preload][hx-get]");
  }

  function preload(elt) {
    if (!elt || !window.htmx) return;
    var now = Date.now();
    if (elt.__dbPreloadedAt && now - elt.__dbPreloadedAt < KEPT_MS) return;
    elt.__dbPreloadedAt = now;
    window.htmx.ajax("GET", elt.getAttribute("hx-get"), { source: elt, headers: { "HX-Preloaded": "true" } });
  }

  // The number below, for the pages swipe_nav.js keeps in memory (§13): one
  // kept under an older number is never shown.
  window.dbDataVersion = function () {
    return dataVersion;
  };

  var pending = null;

  function cancel() {
    if (pending) window.clearTimeout(pending.timer);
    pending = null;
  }

  document.addEventListener("touchstart", function (event) {
    cancel();
    var elt = preloadTarget(event.target);
    var touch = event.touches && event.touches[0];
    if (!elt || !touch || event.touches.length > 1) return;
    pending = {
      x: touch.clientX,
      y: touch.clientY,
      timer: window.setTimeout(function () { pending = null; preload(elt); }, REST_MS),
    };
  }, { passive: true, capture: true });

  document.addEventListener("touchmove", function (event) {
    var touch = event.touches && event.touches[0];
    if (!pending || !touch) return;
    if (Math.abs(touch.clientX - pending.x) > MOVE_PX || Math.abs(touch.clientY - pending.y) > MOVE_PX) cancel();
  }, { passive: true, capture: true });

  document.addEventListener("touchend", cancel, { passive: true, capture: true });
  document.addEventListener("touchcancel", cancel, { passive: true, capture: true });

  document.addEventListener("mousedown", function (event) {
    // A touch also sends a compatibility mousedown after touchend: the touch
    // already decided, so only a real mouse counts here.
    if (event.sourceCapabilities && event.sourceCapabilities.firesTouchEvents) return;
    if (event.button !== 0) return;
    preload(preloadTarget(event.target));
  }, { capture: true });

  document.addEventListener("htmx:configRequest", function (event) {
    event.detail.headers["X-Data-Version"] = String(dataVersion);
  });

  document.addEventListener("htmx:afterRequest", function (event) {
    var detail = event.detail || {};
    var verb = String((detail.requestConfig && detail.requestConfig.verb) || "get").toLowerCase();
    if (verb !== "get" && detail.successful) dataVersion += 1;
  });
})();
