// Actions pop-up of a food row (frontend_conventions.md §9.3.1). Holding a
// row of the Food list for HOLD_MS without moving, or a right click on it,
// asks the server for the menu (components/food/food_actions.py) and opens
// the pop-up once it is in. Releasing after a long press does not open the
// food's detail. Presentation only: the options and what they do come from
// the server.
(function () {
  if (window.__dbFoodActionsBootstrapped) return;
  window.__dbFoodActionsBootstrapped = true;

  var MODAL_ID = "food_actions_modal";
  var BODY_ID = "food_actions_modal_body";
  var HOLD_MS = 500;
  // Further than this the finger is scrolling, not holding.
  var MOVE_TOLERANCE_PX = 10;
  // Pressed look (§10) only once the hold is clearly not a tap.
  var PRESSED_AFTER_MS = 150;
  // On Android a long press also fires `contextmenu`: one menu per gesture.
  var REOPEN_GUARD_MS = 800;

  // Changing view inside the open pop-up (§10, as in the rescue pop-up): the
  // current view fades out, the card keeps its height until the fade ends,
  // then goes to the new height while the new view rises in. The shared
  // helpers are in static/js/modal.js.
  var motion = window.dbModalMotion;

  var press = null;
  var viewChange = null;
  var suppressClickOn = null;
  var lastOpenAt = 0;

  // Short tap felt in the finger when the pop-up opens, where the browser
  // has the vibration API (Android; Safari on iPhone does not).
  function haptic() {
    if (navigator.vibrate) navigator.vibrate(10);
  }

  function rowOf(target) {
    return target && target.closest ? target.closest("[data-food-actions]") : null;
  }

  function openMenu(row) {
    var now = Date.now();
    if (now - lastOpenAt < REOPEN_GUARD_MS) return;
    var trigger = row.querySelector("[data-food-actions-trigger]");
    if (!trigger || !document.getElementById(BODY_ID) || !window.htmx) return;
    lastOpenAt = now;
    window.htmx.trigger(trigger, "dbFoodActions");
  }

  function cancelPress() {
    if (!press) return;
    window.clearTimeout(press.timer);
    window.clearTimeout(press.pressedTimer);
    press.row.removeAttribute("data-food-pressed");
    press = null;
  }

  document.addEventListener("pointerdown", function (event) {
    cancelPress();
    // A new gesture: a click held back from an earlier one no longer applies
    // (iOS does not always send a click after a long press).
    suppressClickOn = null;
    if (!event.isPrimary || (event.pointerType === "mouse" && event.button !== 0)) return;
    var row = rowOf(event.target);
    // The star and the + of the row keep their own tap.
    if (!row || event.target.closest("[data-no-open]")) return;
    press = {
      row: row,
      x: event.clientX,
      y: event.clientY,
      pressedTimer: window.setTimeout(function () {
        if (press) press.row.setAttribute("data-food-pressed", "");
      }, PRESSED_AFTER_MS),
      timer: window.setTimeout(function () {
        if (!press) return;
        var held = press.row;
        cancelPress();
        haptic();
        suppressClickOn = held;
        openMenu(held);
      }, HOLD_MS),
    };
  });

  document.addEventListener("pointermove", function (event) {
    if (!press) return;
    if (Math.abs(event.clientX - press.x) > MOVE_TOLERANCE_PX || Math.abs(event.clientY - press.y) > MOVE_TOLERANCE_PX) {
      cancelPress();
    }
  });
  document.addEventListener("pointerup", cancelPress);
  document.addEventListener("pointercancel", cancelPress);
  window.addEventListener("scroll", cancelPress, { passive: true, capture: true });

  // Capture phase: runs before the row's own click (htmx), which would open
  // the food's detail.
  document.addEventListener("click", function (event) {
    if (!suppressClickOn) return;
    var row = rowOf(event.target);
    if (row === suppressClickOn) {
      event.preventDefault();
      event.stopPropagation();
    }
    suppressClickOn = null;
  }, true);

  // Right click on a computer; on Android, the system's long press.
  document.addEventListener("contextmenu", function (event) {
    var row = rowOf(event.target);
    if (!row) return;
    event.preventDefault();
    if (press) {
      // Android's long press got here before our timer: same tap.
      cancelPress();
      haptic();
      suppressClickOn = row;
    }
    openMenu(row);
  });

  // ---- Changing view ----

  function body() {
    return document.getElementById(BODY_ID);
  }

  function card() {
    var el = body();
    return el ? el.closest("[data-modal-card]") : null;
  }

  // Capture phase: the pop-up card stops the bubbling of its clicks
  // (components/modal.py). The current view starts to fade on the click,
  // while htmx asks for the next one.
  document.addEventListener("click", function (event) {
    var link = event.target && event.target.closest ? event.target.closest("[data-food-actions-view]") : null;
    var el = body();
    var c = card();
    if (!link || !el || !c || !el.contains(link)) return;
    viewChange = { fromHeight: c.offsetHeight, startedAt: Date.now() };
    motion.startFade(el);
  }, true);

  // The next view did not arrive (an error status or no connection): the
  // current one comes back. The error itself is shown by app_toast.js.
  function restoreView(event) {
    var target = event && event.detail ? event.detail.target : null;
    if (!target || target.id !== BODY_ID) return;
    motion.clear(target);
    viewChange = null;
  }
  document.body.addEventListener("htmx:responseError", restoreView);
  document.body.addEventListener("htmx:sendError", restoreView);

  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event && event.detail ? event.detail.target : null;
    if (!target || target.id !== BODY_ID) return;
    var change = viewChange;
    viewChange = null;
    if (!change) {
      // The menu arrived complete: only now does the pop-up open, with its
      // own animation and not the one of a view change.
      target.removeAttribute("data-enter");
      if (window.dbOpenModal) window.dbOpenModal(MODAL_ID);
      return;
    }
    // The new view is in but still hidden: the card keeps its old height
    // until the fade ends, so it changes size once.
    var c = card();
    c.style.height = change.fromHeight + "px";
    c.style.overflow = "hidden";
    var wait = motion.reduced() ? 0 : Math.max(0, motion.FADE_MS - (Date.now() - change.startedAt));
    window.setTimeout(function () {
      motion.animateCardHeight(c, function () {
        c.style.height = "";
        c.style.overflow = "";
        motion.clear(target);
      }, change.fromHeight);
      motion.riseIn(target);
    }, wait);
  });

  // A recipe picked in the pop-up: the food was added, the pop-up closes
  // and a notice says where, since the page does not show it.
  document.body.addEventListener("htmx:afterRequest", function (event) {
    var elt = event && event.detail ? event.detail.elt : null;
    if (!elt || !elt.hasAttribute || !elt.hasAttribute("data-food-actions-recipe")) return;
    if (!event.detail.successful) return;
    if (window.dbCloseModal) window.dbCloseModal(MODAL_ID);
    if (window.dbShowAppNotice) window.dbShowAppNotice("Added to " + elt.getAttribute("data-food-actions-recipe"));
  });
})();
