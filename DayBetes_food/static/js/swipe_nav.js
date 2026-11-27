// Swipe left or right to change page (frontend_conventions.md §13).
//
// On a page of the island, a swipe taps the next or previous island item, so it
// does exactly what tapping it does (indicator, history, preload, scroll). On
// any other page, a swipe to the right is Back: it taps the page's Back button
// (the one with back_js), or calls dbBack() when the page has none.
// Decided on lifting the finger; the page does not follow it.
(function () {
  if (window.__dbSwipeNav) return;
  window.__dbSwipeNav = true;

  var MIN_DX = 70;          // px across
  var RATIO = 2;            // at least twice as much across as down
  var MAX_MS = 600;         // a swipe, not a slow drag
  var EDGE = 24;            // px from a side edge: the system's own Back gesture
  var COOLDOWN_MS = 500;    // a second quick swipe does not skip two pages

  var ISLAND_ROOTS = {
    "/": "menu",
    "/menu": "menu",
    "/stats": "stats",
    "/assistant": "assistant",
    "/food": "food",
    "/settings": "settings",
  };

  var start = null;
  var lastSwipe = 0;
  var clearTimer = null;

  function islandValue() {
    var path = window.location.pathname.replace(/\/+$/, "") || "/";
    return Object.prototype.hasOwnProperty.call(ISLAND_ROOTS, path) ? ISLAND_ROOTS[path] : null;
  }

  function scrollsAcross(el) {
    var style = window.getComputedStyle(el);
    var overflow = style.overflowX;
    return (overflow === "auto" || overflow === "scroll") && el.scrollWidth > el.clientWidth + 1;
  }

  // Whether a gesture that starts on `target` belongs to something else.
  function isExcluded(target) {
    for (var el = target; el && el !== document.body; el = el.parentElement) {
      if (el.nodeType !== 1) continue;
      if (el.hasAttribute("data-no-swipe")) return true;
      if (el.isContentEditable) return true;
      var tag = el.tagName;
      if (tag === "TEXTAREA" || tag === "SELECT") return true;
      if (tag === "INPUT" && el.type !== "radio" && el.type !== "checkbox" && el.type !== "button" && el.type !== "submit") return true;
      if (scrollsAcross(el)) return true;
    }
    return false;
  }

  function blocked() {
    if (document.querySelector("dialog[open]")) return true;
    var selection = window.getSelection ? window.getSelection() : null;
    return !!(selection && String(selection).length);
  }

  // The new page slides in from the side the finger moved away from.
  //
  // data-swipe stays on #main_content while the page it brought is shown:
  // removing it changes the children's animation-name, and the browser then
  // plays the usual rise-in once more, a flash after the page had settled. It
  // is only dropped when the next page comes in without a swipe, before that
  // page is painted (a MutationObserver runs before the next frame).
  var pending = false;

  function markDirection(direction) {
    var main = document.getElementById("main_content");
    if (!main) return;
    main.setAttribute("data-swipe", direction);
    pending = true;
    if (clearTimer) window.clearTimeout(clearTimer);
    // No page came (an error, a Back with nothing behind): the next one
    // comes in as usual.
    clearTimer = window.setTimeout(clearDirection, 3000);
  }

  function clearDirection() {
    pending = false;
    if (clearTimer) window.clearTimeout(clearTimer);
    clearTimer = null;
  }

  function onPageReplaced() {
    if (pending) {
      clearDirection();
      return;
    }
    var main = document.getElementById("main_content");
    if (main) main.removeAttribute("data-swipe");
  }

  function goIsland(current, step) {
    var items = Array.prototype.slice.call(
      document.querySelectorAll("#floating_island label[data-nav-item]")
    );
    var index = -1;
    for (var i = 0; i < items.length; i += 1) {
      if (items[i].getAttribute("data-nav-item") === current) index = i;
    }
    if (index < 0) return false;
    var next = items[index + step];
    if (!next) return false;  // no wrap-around
    var input = next.querySelector("input[type='radio']");
    if (!input) return false;
    markDirection(step > 0 ? "next" : "prev");
    input.click();
    return true;
  }

  function goBack() {
    markDirection("prev");
    var main = document.getElementById("main_content");
    var button = main ? main.querySelector("[onclick*='dbBack(']") : null;
    if (button) {
      button.click();
    } else if (typeof window.dbBack === "function") {
      window.dbBack();
    } else {
      clearDirection();
      return false;
    }
    return true;
  }

  function onStart(event) {
    start = null;
    if (event.touches.length !== 1) return;
    var touch = event.touches[0];
    if (touch.clientX < EDGE || touch.clientX > window.innerWidth - EDGE) return;
    if (isExcluded(event.target)) return;
    start = { x: touch.clientX, y: touch.clientY, t: Date.now() };
  }

  function onMove(event) {
    // A second finger turns it into something else (a pinch).
    if (start && event.touches.length !== 1) start = null;
  }

  function onEnd(event) {
    if (!start) return;
    var begin = start;
    start = null;
    var touch = event.changedTouches[0];
    if (!touch) return;
    var dx = touch.clientX - begin.x;
    var dy = touch.clientY - begin.y;
    var now = Date.now();
    if (now - begin.t > MAX_MS) return;
    if (Math.abs(dx) < MIN_DX || Math.abs(dx) < RATIO * Math.abs(dy)) return;
    if (now - lastSwipe < COOLDOWN_MS || blocked()) return;

    // Finger to the left: the next page comes in from the right.
    var step = dx < 0 ? 1 : -1;
    var current = islandValue();
    var done = current ? goIsland(current, step) : step < 0 && goBack();
    if (done) lastSwipe = now;
  }

  function bind() {
    document.addEventListener("touchstart", onStart, { passive: true });
    document.addEventListener("touchmove", onMove, { passive: true });
    document.addEventListener("touchend", onEnd, { passive: true });
    document.addEventListener("touchcancel", function () { start = null; }, { passive: true });

    // Every way a page arrives (a swap, a history restore) replaces the
    // children of #main_content; a refresh inside a page does not.
    var main = document.getElementById("main_content");
    if (main && window.MutationObserver) {
      new MutationObserver(onPageReplaced).observe(main, { childList: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
