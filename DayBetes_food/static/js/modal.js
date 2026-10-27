// Opens and closes the pop-ups built with components/modal.py. Each one is a
// <dialog> shown with showModal(), so the browser paints it above the whole
// page; `id` names the dimmed layer inside it (frontend_conventions.md §8).
(function () {
  window.dbOpenModal = function (id) {
    var layer = document.getElementById(id);
    if (!layer) return;
    var dialog = layer.closest("dialog");
    if (dialog && !dialog.open) {
      dialog.showModal();
      // A dialog that was hidden has no painted start state yet: reading the
      // layout makes the browser apply it, so the fade and the card's grow
      // always run instead of the pop-up appearing at once.
      void layer.offsetWidth;
    }
    window.requestAnimationFrame(function () {
      layer.classList.remove("opacity-0");
      layer.classList.add("opacity-100");
    });
  };

  // Motion shared by the pop-ups (frontend_conventions.md §10): opacity and
  // transform, short, and none when the system asks to reduce motion. The
  // card's height is the exception of §10 for the rescue and the food
  // actions pop-ups.
  var FADE_MS = 150;
  var HEIGHT_MS = 220;

  function reduced() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function clear(el) {
    el.style.transition = "";
    el.style.opacity = "";
    el.style.transform = "";
  }

  // Starts fading `el` out and leaves it hidden until `clear(el)`.
  function startFade(el) {
    if (!el || reduced()) return;
    el.style.transition = "opacity " + FADE_MS + "ms ease, transform " + FADE_MS + "ms ease";
    el.style.opacity = "0";
    el.style.transform = "translateY(-4px)";
  }

  // Fades `el` out, then runs `done` and gives `el` its styles back.
  function fadeOut(el, done) {
    if (!el || reduced()) {
      if (done) done();
      return;
    }
    startFade(el);
    window.setTimeout(function () {
      if (done) done();
      clear(el);
    }, FADE_MS);
  }

  // Replays the rise-in of `el` (the [data-enter] rules of input.css).
  function riseIn(el) {
    if (!el || reduced()) return;
    el.removeAttribute("data-enter");
    void el.offsetWidth;
    el.setAttribute("data-enter", "");
  }

  // Runs `change` and animates `card` from its old height to the new one,
  // instead of letting it jump. `fromHeight` is passed when the change
  // already happened (an htmx swap); afterwards the height is left free.
  function animateCardHeight(card, change, fromHeight) {
    if (!card || reduced()) {
      if (change) change();
      return;
    }
    var from = fromHeight != null ? fromHeight : card.offsetHeight;
    if (change) change();
    var to = card.offsetHeight;
    if (Math.abs(to - from) < 2) return;
    card.style.height = from + "px";
    card.style.overflow = "hidden";
    void card.offsetHeight;
    card.style.transition = "height " + HEIGHT_MS + "ms cubic-bezier(0.2, 0.8, 0.2, 1)";
    card.style.height = to + "px";
    window.setTimeout(function () {
      card.style.height = "";
      card.style.overflow = "";
      card.style.transition = "";
    }, HEIGHT_MS + 20);
  }

  window.dbModalMotion = {
    FADE_MS: FADE_MS,
    reduced: reduced,
    clear: clear,
    startFade: startFade,
    fadeOut: fadeOut,
    riseIn: riseIn,
    animateCardHeight: animateCardHeight,
  };

  window.dbCloseModal = function (id) {
    var layer = document.getElementById(id);
    if (!layer) return;
    layer.classList.remove("opacity-100");
    layer.classList.add("opacity-0");
    var dialog = layer.closest("dialog");
    // The dialog closes once the fade-out ends, unless it was reopened.
    window.setTimeout(function () {
      if (dialog && dialog.open && layer.classList.contains("opacity-0")) dialog.close();
    }, 200);
  };
})();
