// Swipe left or right to change page (frontend_conventions.md §13).
//
// On a page of the island, a swipe goes to the next or previous island item.
// On any other page, a swipe to the right is Back: it taps the page's Back
// button (the one with back_js), or calls dbBack() when the page has none.
//
// It works like a carousel: the page it goes to is ready beside the current
// one before the finger moves (a preview), both follow the finger, and on
// release both only finish moving. The real page is drawn once the preview
// has landed, with nothing left moving, so its work is never seen.
// - Between island pages the preview is the page kept in memory
//   (page_cache.js). With none ready, the swipe taps the island item.
// - Back shows the page Back goes to: what htmx would bring back (its saved
//   copy and scroll) or the page asked for anew. On release the swipe taps the
//   Back button, as always, and the navigation it starts is answered with the
//   preview instead of waiting for it. With none ready, the page leaves and
//   the one behind comes in when it arrives.
//
// Only transform, never opacity: a faded ancestor cuts the glass inside it
// off the page background (§10).
(function () {
  if (window.__dbSwipeNav) return;
  window.__dbSwipeNav = true;

  var LOCK_PX = 10;           // movement before deciding across or down
  var RATIO = 1.5;            // across must beat down by this much
  var COMMIT_PX = 90;         // released this far, it changes page
  var FLICK_PX = 50;          // or this far, if fast
  var FLICK_SPEED = 0.35;     // px per ms
  var RESIST = 0.15;          // how much the page follows with no page ready on that side
  var EDGE = 24;              // px from a side edge: the system's own Back gesture
  var COOLDOWN_MS = 500;
  var VELOCITY_WINDOW_MS = 100;
  var EASING = "cubic-bezier(0.25, 0.46, 0.45, 0.94)";  // starts at about the finger's speed
  var SLOPE = 1.8;            // that curve's starting speed, against its average
  var MIN_MS = 180;
  var MAX_MS = 320;
  var SPRING_MS = 200;
  var PREVIEW_DELAY_MS = 300;
  var SAFETY_MS = 3000;

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
  var previews = {};          // by step: +1 the next item, -1 the previous one
  var previewTimer = null;
  var safetyTimer = null;
  var ownSwap = false;        // the page being drawn is the landed preview
  var awaitingPage = false;   // #main_content is hidden until a page arrives

  // ---- Where we are ----

  function main() {
    return document.getElementById("main_content");
  }

  function reducedMotion() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function onPhone() {
    return !!(window.matchMedia && window.matchMedia("(pointer: coarse)").matches);
  }

  // The width of the page on screen, the distance between two pages side by
  // side (innerWidth would count a desktop scrollbar too).
  function pageWidth() {
    return document.documentElement.clientWidth || window.innerWidth;
  }

  function islandValue() {
    var path = window.location.pathname.replace(/\/+$/, "") || "/";
    return Object.prototype.hasOwnProperty.call(ISLAND_ROOTS, path) ? ISLAND_ROOTS[path] : null;
  }

  // The island item next to the current page on that side, or null (no
  // wrap-around). `url` only when the item may be preloaded (§12).
  function neighbor(step) {
    var current = islandValue();
    if (!current) return null;
    var items = Array.prototype.slice.call(
      document.querySelectorAll("#floating_island label[data-nav-item]")
    );
    var index = -1;
    for (var i = 0; i < items.length; i += 1) {
      if (items[i].getAttribute("data-nav-item") === current) index = i;
    }
    var item = index < 0 ? null : items[index + step];
    var input = item ? item.querySelector("input[type='radio']") : null;
    if (!input) return null;
    var url = input.matches("[data-preload][hx-get]") ? input.getAttribute("hx-get") : null;
    return { value: item.getAttribute("data-nav-item"), input: input, url: url };
  }

  function backAction() {
    var root = main();
    var button = root ? root.querySelector("[onclick*='dbBack(']") : null;
    if (button) return function () { button.click(); };
    return typeof window.dbBack === "function" ? function () { window.dbBack(); } : null;
  }

  // Where Back goes from this page (navigation.js), or null.
  function backTarget() {
    if (islandValue() || !window.dbHistory || !backAction()) return null;
    var root = main();
    var button = root ? root.querySelector("[onclick*='dbBack(']") : null;
    var match = button ? (button.getAttribute("onclick") || "").match(/dbBack\('([^']*)'\)/) : null;
    return window.dbHistory.backTarget(match ? match[1] : null);
  }

  function islandValueOf(url) {
    var path = (url || "").split("?")[0].replace(/\/+$/, "") || "/";
    return Object.prototype.hasOwnProperty.call(ISLAND_ROOTS, path) ? ISLAND_ROOTS[path] : null;
  }

  function sameUrl(a, b) {
    var normalize = function (url) {
      var parsed = new URL(url, window.location.origin);
      return (parsed.pathname.replace(/\/+$/, "") || "/") + parsed.search;
    };
    return !!a && !!b && normalize(a) === normalize(b);
  }

  function scrollsAcross(el) {
    var overflow = window.getComputedStyle(el).overflowX;
    return (overflow === "auto" || overflow === "scroll") && el.scrollWidth > el.clientWidth + 1;
  }

  // Whether a gesture that starts on `target` belongs to something else.
  function isExcluded(target) {
    for (var el = target; el && el !== document.body; el = el.parentElement) {
      if (el.nodeType !== 1) continue;
      if (el.hasAttribute("data-no-swipe") || el.isContentEditable) return true;
      var tag = el.tagName;
      if (tag === "TEXTAREA" || tag === "SELECT") return true;
      if (tag === "INPUT" && ["radio", "checkbox", "button", "submit"].indexOf(el.type) < 0) return true;
      if (scrollsAcross(el)) return true;
    }
    return false;
  }

  function blocked() {
    if (document.querySelector("dialog[open]")) return true;
    var selection = window.getSelection ? window.getSelection() : null;
    return !!(selection && String(selection).length);
  }

  // ---- Previews of the pages next door ----
  //
  // A layer right after #main_content (above it, under the island and the
  // cart button) holding the page in a shadow root: its ids, selectors and
  // forms stay out of the document, so no script of the web ever finds them.
  // Inert, hidden from assistive tech, nothing in it moves by itself, and it
  // opens where the real page will (DiaBot at its last turn, through the
  // `db:swipe-preview` event).
  //
  // It is part of the document, not fixed: placed where the window is when a
  // swipe starts and as tall as the window, so the browser draws it exactly
  // where it will draw the real page. A fixed layer does not cover the same
  // area as the document in Safari on an iPhone (the page goes on behind its
  // toolbars), and the page then moved a few pixels as it landed. At rest it
  // waits at the top of the document, where it never makes the page longer.
  //
  // It moves inside a frame that stays put and clips it (.db_swipe_frame):
  // off to one side, it would make the document wider, and a phone's browser
  // then zooms out to fit it, and back in as the page lands.

  function stylesheetHref() {
    var link = document.querySelector("link[rel='stylesheet'][href*='/css/output.css']");
    return link ? link.getAttribute("href") : null;
  }

  function buildPreview(step, target, html, scroll) {
    var root = main();
    var href = stylesheetHref();
    if (!root || !href) return;
    var frame = document.createElement("div");
    frame.className = "db_swipe_frame";
    frame.setAttribute("aria-hidden", "true");
    frame.setAttribute("inert", "");
    var host = document.createElement("div");
    host.className = "db_swipe_preview";
    frame.appendChild(host);
    var shadow = host.attachShadow({ mode: "open" });
    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    var still = document.createElement("style");
    still.textContent = "*, *::before, *::after { animation: none !important; transition: none !important; }";
    // Where #main_content sits with the page at the top (layout values: a
    // swipe may have it shifted right now).
    var page = document.createElement("div");
    page.style.cssText = "position:absolute;left:" + root.offsetLeft + "px;top:" + root.offsetTop +
      "px;width:" + root.offsetWidth + "px";
    page.innerHTML = html;
    var scripts = page.querySelectorAll("script");
    for (var i = 0; i < scripts.length; i += 1) scripts[i].remove();
    shadow.appendChild(link);
    shadow.appendChild(still);
    shadow.appendChild(page);
    root.after(frame);

    var preview = {
      step: step, url: target.url, value: target.value, html: html, scroll: scroll || 0,
      fromCache: !!target.fromCache, back: !!target.back,
      frame: frame, host: host, shadow: shadow, page: page, ready: false, height: 0, width: pageWidth(),
    };
    previews[step] = preview;
    place(preview, false);
    link.addEventListener("load", function () {
      if (previews[step] !== preview) return;
      preview.ready = true;
      settle(preview);
    });
  }

  // The scripts of the page make it look as it will once open (§13).
  function settle(preview) {
    preview.host.scrollTop = preview.scroll;
    document.dispatchEvent(new CustomEvent("db:swipe-preview", { detail: { root: preview.shadow, scroller: preview.host } }));
  }

  // Where the window is (a swipe starting), or at the top of the document
  // (at rest). As tall as the window: a new height (Safari's toolbars) lays
  // it out again.
  function place(preview, active) {
    preview.frame.style.top = (active ? window.scrollY : 0) + "px";
    var height = window.innerHeight;
    if (preview.height === height) return;
    preview.height = height;
    preview.frame.style.height = height + "px";
    if (preview.ready) settle(preview);
  }

  function dropPreview(step) {
    var preview = previews[step];
    if (preview) preview.frame.remove();
    delete previews[step];
  }

  function dropPreviews() {
    dropPreview(1);
    dropPreview(-1);
  }

  // Ready, for the page that side leads to now, and still good: what memory
  // holds for it (not expired, no save since), or htmx's saved copy.
  function readyPreview(step) {
    var preview = previews[step];
    var cache = window.dbPageCache;
    if (!preview || !preview.ready || !cache) return null;
    var target = islandValue() ? neighbor(step) : step < 0 ? backTarget() : null;
    if (!target || !sameUrl(target.url, preview.url)) return null;
    return preview.fromCache || cache.get(preview.url) === preview.html ? preview : null;
  }

  function prepare(step) {
    var cache = window.dbPageCache;
    var target = neighbor(step);
    if (!cache || !target || !target.url) {
      dropPreview(step);
      return;
    }
    var current = previews[step];
    if (current && current.url === target.url && cache.get(target.url) === current.html) return;
    cache.load(target.url).then(function (html) {
      var now = neighbor(step);
      if (!html || !now || now.url !== target.url || busy) return;
      if (previews[step] && previews[step].html === html) return;
      dropPreview(step);
      buildPreview(step, now, html);
    });
  }

  // The page Back goes to: htmx's saved copy when Back goes back in the
  // history and htmx kept one (it brings that back, scroll included), else
  // the page asked for anew, as htmx or dbBack would.
  function prepareBack() {
    var cache = window.dbPageCache;
    var target = backTarget();
    if (!cache || !target) {
      dropPreview(-1);
      return;
    }
    var current = previews[-1];
    if (current && sameUrl(current.url, target.url)) return;
    var saved = target.inHistory ? window.dbHistory.snapshot(target.url) : null;
    var entry = { url: target.url, value: islandValueOf(target.url), back: true };
    if (saved) {
      dropPreview(-1);
      entry.fromCache = true;
      buildPreview(-1, entry, saved.content, saved.scroll);
      return;
    }
    cache.load(target.url).then(function (html) {
      var now = backTarget();
      if (!html || !now || !sameUrl(now.url, target.url) || busy) return;
      dropPreview(-1);
      buildPreview(-1, entry, html, 0);
    });
  }

  function preparePreviews() {
    previewTimer = null;
    if (!onPhone() || reducedMotion() || busy || document.visibilityState !== "visible") return;
    if (islandValue()) {
      prepare(1);
      prepare(-1);
      return;
    }
    dropPreview(1);
    prepareBack();
  }

  function schedulePreviews() {
    if (previewTimer) window.clearTimeout(previewTimer);
    previewTimer = window.setTimeout(preparePreviews, PREVIEW_DELAY_MS);
  }

  // ---- Moving ----

  function offsetOf(el) {
    var match = (el.style.transform || "").match(/translateX\((-?[\d.]+)px\)/);
    return match ? parseFloat(match[1]) : 0;
  }

  function shift(el, x) {
    el.style.transform = x ? "translateX(" + x.toFixed(1) + "px)" : "";
  }

  // From where it is to `to` px, ending there. Run by the compositor, so a
  // busy page never makes it stutter.
  function slide(el, from, to, ms) {
    shift(el, to);
    if (!el.animate) return Promise.resolve();
    var motion = el.animate(
      [{ transform: "translateX(" + from + "px)" }, { transform: "translateX(" + to + "px)" }],
      { duration: ms, easing: EASING }
    );
    return motion.finished.catch(function () {});
  }

  // As long as the finger's speed asks for, within bounds.
  function durationFor(distance, speed) {
    var ms = speed > 0 ? (SLOPE * distance) / speed : MAX_MS;
    return Math.round(Math.min(MAX_MS, Math.max(MIN_MS, ms)));
  }

  function showPreview(step) {
    var other = previews[-step];
    if (other) other.frame.removeAttribute("data-shown");
    var preview = readyPreview(step);
    if (preview) preview.frame.setAttribute("data-shown", "");
    return preview;
  }

  function rest(preview) {
    preview.frame.removeAttribute("data-shown");
    shift(preview.host, 0);
    place(preview, false);
  }

  function hidePreviews() {
    [1, -1].forEach(function (step) {
      if (previews[step]) rest(previews[step]);
    });
  }

  function follow(dx) {
    var root = main();
    if (!root || reducedMotion()) return;
    var step = dx < 0 ? 1 : -1;
    if (islandValue()) {
      var preview = showPreview(step);
      shift(root, preview ? dx : dx * RESIST);
      if (preview) shift(preview.host, step * pageWidth() + dx);
      return;
    }
    var back = step < 0 ? showPreview(step) : null;
    shift(root, step < 0 && backAction() ? dx : dx * RESIST);
    if (back) shift(back.host, -pageWidth() + dx);
  }

  function springBack() {
    var root = main();
    if (!root || reducedMotion()) {
      hidePreviews();
      return;
    }
    slide(root, offsetOf(root), 0, SPRING_MS);
    [1, -1].forEach(function (step) {
      var preview = previews[step];
      if (!preview || !preview.frame.hasAttribute("data-shown")) return;
      var aside = step * pageWidth();
      slide(preview.host, offsetOf(preview.host), aside, SPRING_MS).then(function () {
        if (!busy && previews[step] === preview) rest(preview);
      });
    });
  }

  // ---- Changing page ----

  function finishEntries(root) {
    if (!root.getAnimations) return;
    root.getAnimations({ subtree: true }).forEach(function (motion) {
      if (!motion.effect || motion.effect.target === root) return;
      if (motion.effect.getTiming().iterations === Infinity) return;
      try { motion.finish(); } catch (error) { /* already gone */ }
    });
  }

  function stopMoving(el) {
    if (el.getAnimations) el.getAnimations().forEach(function (motion) { motion.cancel(); });
    shift(el, 0);
  }

  function release() {
    busy = false;
    if (safetyTimer) window.clearTimeout(safetyTimer);
    safetyTimer = null;
  }

  // Hidden until the next page arrives (or for 3 s at most).
  function awaitPage(root) {
    root.style.visibility = "hidden";
    awaitingPage = true;
    safetyTimer = window.setTimeout(function () {
      awaitingPage = false;
      root.style.visibility = "";
      release();
    }, SAFETY_MS);
  }

  // The preview has landed: the real page takes its place in the same frame.
  // Its entry animations finish at once (the preview already made the
  // arrival), and #main_content, off screen until now, goes back to rest.
  function land(preview) {
    var root = main();
    var step = preview.step;
    if (safetyTimer) window.clearTimeout(safetyTimer);
    if (preview.back) {
      landBack(preview);
      return;
    }
    // Before the swap: changed after it, the new page would play its entry.
    root.removeAttribute("data-swipe");
    ownSwap = true;
    // The page left is saved first, with its own scroll (page_cache.js).
    if (!window.dbPageCache || !window.dbPageCache.show(preview.url, preview.html)) {
      // Could not draw it: the island item, as a tap.
      ownSwap = false;
      stopMoving(root);
      dropPreview(step);
      var target = neighbor(step);
      if (target) {
        awaitPage(root);
        target.input.click();
      } else {
        release();
      }
      return;
    }
    settleLanded(preview);
  }

  // The real page, just drawn, at rest where the preview is: same scroll,
  // entries finished, #main_content back from off screen, the preview gone.
  function settleLanded(preview) {
    var root = main();
    var scroll = preview.host.scrollTop;
    finishEntries(root);
    stopMoving(root);
    window.scrollTo({ top: scroll, behavior: "auto" });
    dropPreview(preview.step);
    release();
  }

  // Back: the swipe taps the Back button, as always (it may do more, like
  // stopping the scanner), and the navigation that starts is answered with
  // the preview: htmx's restore after popstate, or the request of dbBack.
  var landingBack = null;
  var BACK_WAIT_MS = 1500;

  function landBack(preview) {
    landingBack = preview;
    // The Back button goes to the top before going back (dbBack): the preview
    // goes there with it, in the same frame, so it stays in view.
    preview.frame.style.top = "0px";
    window.scrollTo({ top: 0, behavior: "auto" });
    safetyTimer = window.setTimeout(function () {
      // Back went nowhere we could answer: the page comes back.
      if (landingBack !== preview) return;
      landingBack = null;
      stopMoving(main());
      dropPreview(preview.step);
      release();
    }, BACK_WAIT_MS);
    var action = backAction();
    if (action) action();
  }

  function answerBack(event, url) {
    var preview = landingBack;
    if (!preview || !sameUrl(url, preview.url)) return;
    event.preventDefault();
    landingBack = null;
    if (safetyTimer) window.clearTimeout(safetyTimer);
    var root = main();
    root.removeAttribute("data-swipe");
    ownSwap = true;
    if (!window.dbPageCache.restore(preview.url, preview.html)) {
      ownSwap = false;
      stopMoving(root);
      dropPreview(preview.step);
      release();
      return;
    }
    settleLanded(preview);
  }

  function onHistoryRestoreStart(event) {
    answerBack(event, event.detail && event.detail.path);
  }

  function onBackRequest(event) {
    var detail = event.detail || {};
    var config = detail.requestConfig || {};
    if (!detail.target || detail.target.id !== "main_content") return;
    if (String(config.verb || "get").toLowerCase() !== "get") return;
    answerBack(event, config.path);
  }

  function goToPreview(preview, dx, speed) {
    busy = true;
    lastSwipe = Date.now();
    var root = main();
    var width = pageWidth();
    var step = preview.step;
    var ms = durationFor(width - Math.abs(dx), speed);
    if (preview.value && typeof window.dbIslandSelect === "function") window.dbIslandSelect(preview.value);
    if (typeof window.dbSyncCartButton === "function") window.dbSyncCartButton(preview.page);
    slide(root, dx, -step * width, ms);
    slide(preview.host, step * width + dx, 0, ms).then(function () {
      if (busy && previews[step] === preview) land(preview);
    });
    // The animation never ended (the tab went to the background meanwhile).
    safetyTimer = window.setTimeout(function () {
      if (busy && previews[step] === preview) land(preview);
    }, SAFETY_MS);
  }

  // Back: the page leaves to the right, and the one behind comes in from the
  // left when it arrives (input.css). Usually at once: htmx keeps the pages
  // left behind.
  function goBack(action, dx, speed) {
    busy = true;
    lastSwipe = Date.now();
    var root = main();
    var width = pageWidth();
    function leave() {
      stopMoving(root);
      root.setAttribute("data-swipe", "prev");
      awaitPage(root);
      action();
    }
    if (reducedMotion()) {
      leave();
      return;
    }
    slide(root, dx, width, durationFor(width - Math.abs(dx), speed)).then(leave);
  }

  // Every way a page arrives (a swap, a history restore) replaces the
  // children of #main_content; a refresh inside a page does not.
  function onPageReplaced() {
    var root = main();
    dropPreviews();
    schedulePreviews();
    if (ownSwap) {
      ownSwap = false;
      return;
    }
    if (awaitingPage) {
      awaitingPage = false;
      root.style.visibility = "";
      release();
      return;  // data-swipe stays while this page is shown: removing it would play its entry again
    }
    if (busy) {
      // Another page arrived in the middle of a swipe (a tap on the island):
      // it wins, and the swipe stops where it is.
      stopMoving(root);
      release();
    }
    root.removeAttribute("data-swipe");
  }

  // ---- Touch ----

  function velocity(g) {
    var samples = g.samples;
    if (samples.length < 2) return 0;
    var first = samples[0];
    var last = samples[samples.length - 1];
    var elapsed = last.t - first.t;
    return elapsed > 0 ? Math.abs(last.x - first.x) / elapsed : 0;
  }

  function onStart(event) {
    gesture = null;
    if (busy || event.touches.length !== 1) return;
    var touch = event.touches[0];
    if (touch.clientX < EDGE || touch.clientX > window.innerWidth - EDGE) return;
    if (isExcluded(event.target)) return;
    [1, -1].forEach(function (step) {
      if (previews[step]) place(previews[step], true);
    });
    gesture = {
      x: touch.clientX,
      y: touch.clientY,
      mode: null,
      dx: 0,
      dy: 0,
      samples: [{ x: touch.clientX, t: Date.now() }],
    };
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
    var now = Date.now();
    gesture.dx = touch.clientX - gesture.x;
    gesture.dy = touch.clientY - gesture.y;
    gesture.samples.push({ x: touch.clientX, t: now });
    while (gesture.samples.length > 2 && now - gesture.samples[0].t > VELOCITY_WINDOW_MS) gesture.samples.shift();
    if (!gesture.mode) {
      if (Math.max(Math.abs(gesture.dx), Math.abs(gesture.dy)) < LOCK_PX) return;
      // Once the browser has started scrolling the page (the move can no
      // longer be cancelled), it stays a scroll.
      var across = Math.abs(gesture.dx) > RATIO * Math.abs(gesture.dy) && event.cancelable && !blocked();
      gesture.mode = across ? "across" : "down";
      // A page next door not ready (expired, a save since) starts now.
      if (gesture.mode === "across" && onPhone() && !reducedMotion()) {
        if (islandValue()) prepare(gesture.dx < 0 ? 1 : -1);
        else if (gesture.dx > 0) prepareBack();
      }
    }
    if (gesture.mode !== "across") return;
    // A swipe across does not scroll the page up or down as well: its momentum
    // would carry on after the swipe, and on an iPhone bounce at the top of
    // the new page.
    if (event.cancelable) event.preventDefault();
    follow(gesture.dx);
  }

  function onEnd() {
    if (!gesture) return;
    var g = gesture;
    gesture = null;
    if (g.mode !== "across") return;
    var dx = g.dx;
    var speed = velocity(g);
    var step = dx < 0 ? 1 : -1;
    var far = Math.abs(dx) >= COMMIT_PX || (Math.abs(dx) >= FLICK_PX && speed >= FLICK_SPEED);
    var across = Math.abs(dx) > RATIO * Math.abs(g.dy);
    var allowed = far && across && Date.now() - lastSwipe >= COOLDOWN_MS && !blocked();

    if (islandValue()) {
      var preview = readyPreview(step);
      if (allowed && preview && !reducedMotion()) {
        goToPreview(preview, dx, speed);
        return;
      }
      springBack();
      // No preview ready: the island item, as a tap.
      var target = neighbor(step);
      if (allowed && target) {
        lastSwipe = Date.now();
        target.input.click();
      }
      return;
    }
    var action = step < 0 ? backAction() : null;
    var back = step < 0 ? readyPreview(step) : null;
    if (allowed && back && !reducedMotion()) {
      goToPreview(back, dx, speed);
      return;
    }
    if (allowed && action) {
      if (previews[-1]) rest(previews[-1]);
      goBack(action, dx, speed);
      return;
    }
    springBack();
  }

  function bind() {
    document.addEventListener("touchstart", onStart, { passive: true });
    // Not passive: a swipe across stops the page from scrolling (onMove). The
    // handler is short, so scrolling does not wait on it.
    document.addEventListener("touchmove", onMove, { passive: false });
    document.addEventListener("touchend", onEnd, { passive: true });
    document.addEventListener("touchcancel", function () {
      if (gesture && gesture.mode === "across") springBack();
      gesture = null;
    }, { passive: true });

    var root = main();
    if (root && window.MutationObserver) {
      new MutationObserver(onPageReplaced).observe(root, { childList: true });
    }
    document.addEventListener("htmx:historyCacheHit", onHistoryRestoreStart);
    document.addEventListener("htmx:historyCacheMiss", onHistoryRestoreStart);
    document.addEventListener("htmx:beforeRequest", onBackRequest);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") schedulePreviews();
    });
    // Previews are laid out for one width (a new height only places them
    // again, as Safari's toolbars come and go while scrolling).
    window.addEventListener("resize", function () {
      if (busy) return;
      var stale = [1, -1].some(function (step) {
        return previews[step] && previews[step].width !== pageWidth();
      });
      if (!stale) return;
      dropPreviews();
      schedulePreviews();
    });
    schedulePreviews();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
