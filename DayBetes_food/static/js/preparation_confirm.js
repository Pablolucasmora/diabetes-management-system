// Preparation to confirm (frontend_conventions.md §7.1, §9.4): picking a value
// is local; the tick saves the chosen fields (cart) or copies them to the food
// page's `Preparation` fields, and the block folds away (§10). `Dismiss`
// removes it without saving; in the cart the browser remembers it.
(function () {
  if (window.dbPreparationConfirm) return;
  window.dbPreparationConfirm = true;

  var FOLD_MS = 220;
  // Order of the food page's summary line, as in a cart row.
  var SUMMARY_FIELDS = ["cooking", "final_state", "conservation"];

  function reduced() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  // Browser storage can be missing or blocked: then a dismissal is not remembered.
  function remembered(key) {
    try { return !!key && window.localStorage.getItem(key) === "1"; } catch (e) { return false; }
  }

  function remember(key) {
    try { if (key) window.localStorage.setItem(key, "1"); } catch (e) { /* not remembered */ }
  }

  function setChosen(pill, chosen) {
    var block = pill.closest("[data-prep-confirm]");
    pill.setAttribute("aria-pressed", chosen ? "true" : "false");
    var add = (chosen ? block.dataset.chosenCls : block.dataset.idleCls).split(" ");
    var remove = (chosen ? block.dataset.idleCls : block.dataset.chosenCls).split(" ");
    remove.forEach(function (name) { if (name) pill.classList.remove(name); });
    add.forEach(function (name) { if (name) pill.classList.add(name); });
  }

  // Each field of the block and its chosen value ("" = none chosen).
  function chosenValues(block) {
    var values = {};
    block.querySelectorAll("[data-prep-pill]").forEach(function (pill) {
      var field = pill.dataset.prepPill;
      if (!(field in values)) values[field] = "";
      if (pill.getAttribute("aria-pressed") === "true") values[field] = pill.dataset.prepValue;
    });
    return values;
  }

  // Folds the block: it fades and its height (and the gap above it) goes to 0.
  function fold(block, done) {
    block.dataset.folding = "1";
    if (reduced()) {
      if (done) done();
      return;
    }
    var parent = block.parentElement;
    var gap = parent ? parseFloat(window.getComputedStyle(parent).rowGap) || 0 : 0;
    block.style.height = block.offsetHeight + "px";
    block.style.overflow = "hidden";
    void block.offsetHeight;
    block.style.transition =
      "height " + FOLD_MS + "ms cubic-bezier(0.2, 0.8, 0.2, 1), opacity " + FOLD_MS + "ms ease, " +
      "margin-top " + FOLD_MS + "ms cubic-bezier(0.2, 0.8, 0.2, 1), padding " + FOLD_MS + "ms ease";
    block.style.height = "0px";
    block.style.opacity = "0";
    block.style.paddingTop = "0px";
    block.style.paddingBottom = "0px";
    block.style.marginTop = -gap + "px";
    window.setTimeout(function () { if (done) done(); }, FOLD_MS);
  }

  function unfold(block) {
    delete block.dataset.folding;
    ["height", "overflow", "transition", "opacity", "paddingTop", "paddingBottom", "marginTop"].forEach(
      function (name) { block.style[name] = ""; }
    );
  }

  // Food page: the summary line shows what `Preparation` will send.
  function refreshSummary(scopeId) {
    var line = document.querySelector('[data-prep-summary="' + scopeId + '"]');
    var scope = document.getElementById(scopeId);
    if (!line || !scope || !line.dataset.shown) return;
    var parts = [];
    SUMMARY_FIELDS.forEach(function (field) {
      var input = scope.querySelector('input[name="' + field + '"]');
      if (input && input.value.trim()) parts.push(input.value.trim());
    });
    line.textContent = parts.join(" · ");
    line.hidden = parts.length === 0;
  }

  function resolveWithSummary(block) {
    var scopeId = block.dataset.prepScope;
    fold(block, function () {
      block.remove();
      var line = document.querySelector('[data-prep-summary="' + scopeId + '"]');
      if (line) line.dataset.shown = "1";
      refreshSummary(scopeId);
    });
  }

  // Cart: a dismissed block is not drawn again when its card is repainted.
  function hideDismissed() {
    document.querySelectorAll("[data-prep-confirm][data-prep-key]").forEach(function (block) {
      if (remembered(block.dataset.prepKey)) block.remove();
    });
  }

  document.addEventListener("DOMContentLoaded", hideDismissed);
  // Right after the swap, before the browser paints the new card.
  document.addEventListener("htmx:afterSwap", hideDismissed);

  document.addEventListener("click", function (event) {
    var pill = event.target.closest("[data-prep-pill]");
    if (pill) {
      var block = pill.closest("[data-prep-confirm]");
      var field = pill.dataset.prepPill;
      var wasChosen = pill.getAttribute("aria-pressed") === "true";
      block.querySelectorAll('[data-prep-pill="' + field + '"]').forEach(function (other) {
        setChosen(other, other === pill && !wasChosen);
      });
      var input = block.querySelector('[data-prep-input="' + field + '"]');
      if (input) input.value = wasChosen ? "" : pill.dataset.prepValue;
      return;
    }
    var dismiss = event.target.closest("[data-prep-dismiss]");
    if (dismiss) {
      var dismissed = dismiss.closest("[data-prep-confirm]");
      remember(dismissed.dataset.prepKey);
      fold(dismissed, function () { dismissed.remove(); });
      return;
    }
    var tick = event.target.closest("[data-prep-tick]");
    if (!tick) return;
    var tickBlock = tick.closest("[data-prep-confirm]");
    if (tick.dataset.prepTick === "save") {
      // htmx sends the request on this same click; its swap waits for the fold.
      tick.setAttribute("hx-swap", reduced() ? "outerHTML" : "outerHTML swap:" + FOLD_MS + "ms");
      fold(tickBlock);
      return;
    }
    // Food page: the page's own fields are the ones sent.
    tickBlock.dataset.folding = "1";
    var scope = document.getElementById(tickBlock.dataset.prepScope);
    var values = chosenValues(tickBlock);
    Object.keys(values).forEach(function (name) {
      var target = scope && scope.querySelector('input[name="' + name + '"]');
      if (!target || !values[name]) return;
      target.value = values[name];
      target.dispatchEvent(new Event("change", { bubbles: true }));
    });
    resolveWithSummary(tickBlock);
  });

  // Food page: a change in `Preparation` keeps the summary line in step and,
  // when it fills both fields of the block by hand, folds the block away too.
  document.addEventListener("change", function (event) {
    var input = event.target;
    if (!input.name) return;
    document.querySelectorAll("[data-prep-summary]").forEach(function (line) {
      var lineScope = document.getElementById(line.dataset.prepSummary);
      if (lineScope && lineScope.contains(input)) refreshSummary(line.dataset.prepSummary);
    });
    var block = document.querySelector('[data-prep-confirm][data-prep-mode="copy"]');
    if (!block || block.dataset.folding) return;
    var scope = document.getElementById(block.dataset.prepScope);
    if (!scope || !scope.contains(input)) return;
    var fields = Object.keys(chosenValues(block));
    if (fields.indexOf(input.name) === -1) return;
    var allSet = fields.every(function (name) {
      var target = scope.querySelector('input[name="' + name + '"]');
      return target && target.value.trim() !== "";
    });
    if (allSet) resolveWithSummary(block);
  });

  // A failed save leaves the block where it was, so nothing is lost silently.
  ["htmx:responseError", "htmx:sendError"].forEach(function (name) {
    document.addEventListener(name, function (event) {
      var source = event.detail && event.detail.elt;
      if (!source || !source.matches || !source.matches("[data-prep-tick]")) return;
      var block = source.closest("[data-prep-confirm]");
      if (block) unfold(block);
    });
  });
})();
