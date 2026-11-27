// Swipe left or right to change page (frontend_conventions.md §13).
//
// On a page of the island, a swipe taps the next or previous island item, so it
// does exactly what tapping it does (indicator, history). On any other page, a
// swipe to the right is Back: it taps the page's Back button (the one with
// back_js), or calls dbBack() when the page has none.
//
// One continuous movement: while the finger moves across, the page follows it
// and the page it heads to is preloaded; on release the page slides out
// beyond that side and only then is the next one asked for, which comes in
// from beyond the other side. A short or undecided swipe springs back.
// Only transform, never opacity: a faded ancestor cuts the glass inside it
// off the page background (frontend §10).
(function () {
  if (window.__dbSwipeNav) return;
  window.__dbSwipeNav = true;

  var LOCK_PX = 10;         // movement before deciding across or down
  var RATIO = 1.5;          // across must beat down by this much
  var COMMIT_PX = 90;       // released this far, it changes page
  var FLICK_PX = 50;        // or this far, if fast
  var FLICK_SPEED = 0.35;   // px per ms
  var FOLLOW = 1;           // the page stays under the finger
  var RESIST = 0.15;        // the same, with no page on that side
  var EXIT_MS = 160;        // out beyond the side of the screen
  var SPRING_MS = 180;
  var EDGE = 24;            // px from a side edge: the system's own Back gesture
  var COOLDOWN_MS = 500;

  var ISLAND_ROOTS = {
    "/": "menu",
    "/menu": "menu",
    "/stats": "stats",
    "/assistant": "assistant",
    "/food": "food",
    "/settings": "settings",
  };

  var gesture = null;
  var busy = false;
  var lastSwipe = 0;
  var safetyTimer = null;
  var pendingDirection = false;
  var baseTransition = "";

  function main() {
    return document.getElementById("main_content");
  }

  function reducedMotion() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

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

  // What a swipe of the finger towards `step` (+1 left, -1 right) does here,
  // or null when there is nothing on that side.
  function actionFor(step) {
    var current = islandValue();
    if (current) {
      var items = Array.prototype.slice.call(
        document.querySelectorAll("#floating_island label[data-nav-item]")
      );
      var index = -1;
      for (var i = 0; i < items.length; i += 1) {
        if (items[i].getAttribute("data-nav-item") === current) index = i;
      }
      var next = index < 0 ? null : items[index + step];  // no wrap-around
      var input = next ? next.querySelector("input[type='radio']") : null;
      return input ? { input: input } : null;
    }
    if (step > 0) return null;
    var root = main();
    var button = root ? root.querySelector("[onclick*='dbBack(']") : null;
    if (button) return { button: button };
    return typeof window.dbBack === "function" ? { back: true } : null;
  }

  function run(action) {
    if (action.input) action.input.click();
    else if (action.button) action.button.click();
    else window.dbBack();
  }

  // ---- The page under the finger ----

  function setMain(transform, transition) {
    var el = main();
    if (!el) return;
    el.style.transition = transition || "none";
    el.style.transform = transform;
  }

  // Back at rest at once, with no transition: a transform left on the page
  // would trap its fixed children (§10).
  function resetMain() {
    var el = main();
    if (!el) return;
    el.style.transition = "none";
    el.style.transform = "";
    void el.offsetWidth;  // applied before the page's own transition is back
    el.style.transition = baseTransition;
  }

  function follow(dx, action) {
    var shift = dx * (action ? FOLLOW : RESIST);
    setMain("translateX(" + shift.toFixed(1) + "px)");
  }

  function springBack() {
    setMain("", "transform " + SPRING_MS + "ms ease-out");
    window.setTimeout(function () {
      if (!busy) resetMain();
    }, SPRING_MS + 20);
  }

  // ---- Changing page ----

  // The new page comes in from the side the finger moved away from
  // (input.css). data-swipe stays while that page is shown: removing it
  // would play the page's entry once more. It goes when the next page comes
  // in without a swipe.
  function onPageReplaced() {
    if (busy) {
      busy = false;
      if (safetyTimer) window.clearTimeout(safetyTimer);
      safetyTimer = null;
      resetMain();
    }
    if (pendingDirection) {
      pendingDirection = false;
      return;
    }
    var el = main();
    if (el) el.removeAttribute("data-swipe");
  }

  function go(action, step) {
    busy = true;
    lastSwipe = Date.now();
    var el = main();
    var animate = !reducedMotion();

    function change() {
      // Off the screen by now, so going to the top is not seen.
      window.scrollTo({ top: 0, behavior: "auto" });
      if (el) el.setAttribute("data-swipe", step > 0 ? "next" : "prev");
      pendingDirection = true;
      run(action);
    }

    // No page came (an error, nothing behind): the page shows again.
    safetyTimer = window.setTimeout(function () {
      busy = false;
      pendingDirection = false;
      resetMain();
    }, 3000);

    if (!animate) {
      change();
      return;
    }
    setMain("translateX(" + (-step * 100) + "vw)", "transform " + EXIT_MS + "ms ease-in");
    window.setTimeout(change, EXIT_MS);
  }

  // ---- Touch ----

  function onStart(event) {
    gesture = null;
    if (busy || event.touches.length !== 1) return;
    var touch = event.touches[0];
    if (touch.clientX < EDGE || touch.clientX > window.innerWidth - EDGE) return;
    if (isExcluded(event.target)) return;
    gesture = { x: touch.clientX, y: touch.clientY, t: Date.now(), mode: null, dx: 0, dy: 0 };
  }

  function onMove(event) {
    if (!gesture) return;
    if (event.touches.length !== 1) {
      // A second finger turns it into something else (a pinch).
      if (gesture.mode === "across") springBack();
      gesture = null;
      return;
    }
    var touch = event.touches[0];
    gesture.dx = touch.clientX - gesture.x;
    gesture.dy = touch.clientY - gesture.y;
    if (!gesture.mode) {
      if (Math.max(Math.abs(gesture.dx), Math.abs(gesture.dy)) < LOCK_PX) return;
      if (Math.abs(gesture.dx) <= RATIO * Math.abs(gesture.dy) || blocked()) {
        gesture.mode = "down";
        return;
      }
      gesture.mode = "across";
      // The page it is heading to starts coming now (preload.js, §12).
      var ahead = actionFor(gesture.dx < 0 ? 1 : -1);
      if (ahead && ahead.input && typeof window.dbPreload === "function") window.dbPreload(ahead.input);
    }
    if (gesture.mode !== "across" || reducedMotion()) return;
    follow(gesture.dx, actionFor(gesture.dx < 0 ? 1 : -1));
  }

  function onEnd() {
    if (!gesture) return;
    var g = gesture;
    gesture = null;
    if (g.mode !== "across") return;
    var dx = g.dx;
    var speed = Math.abs(dx) / Math.max(1, Date.now() - g.t);
    var step = dx < 0 ? 1 : -1;
    var action = actionFor(step);
    var far = Math.abs(dx) >= COMMIT_PX || (Math.abs(dx) >= FLICK_PX && speed >= FLICK_SPEED);
    var across = Math.abs(dx) > RATIO * Math.abs(g.dy);
    if (action && far && across && Date.now() - lastSwipe >= COOLDOWN_MS && !blocked()) {
      go(action, step);
      return;
    }
    if (!reducedMotion()) springBack();
  }

  function bind() {
    var el = main();
    baseTransition = el ? el.style.transition : "";

    document.addEventListener("touchstart", onStart, { passive: true });
    document.addEventListener("touchmove", onMove, { passive: true });
    document.addEventListener("touchend", onEnd, { passive: true });
    document.addEventListener("touchcancel", function () {
      if (gesture && gesture.mode === "across") springBack();
      gesture = null;
    }, { passive: true });

    // Every way a page arrives (a swap, a history restore) replaces the
    // children of #main_content; a refresh inside a page does not. The
    // observer runs before the next frame, so the new page is never painted
    // shifted or faded.
    if (el && window.MutationObserver) {
      new MutationObserver(onPageReplaced).observe(el, { childList: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
