(function () {
  if (window.__dbCartUnitsBootstrapped) {
    if (typeof window.dbInitUnitSelects === "function") {
      window.dbInitUnitSelects(document);
    }
    return;
  }
  window.__dbCartUnitsBootstrapped = true;

  function byId(id) {
    return document.getElementById(id);
  }

  function getFactor(selectEl) {
    if (!selectEl || !selectEl.options || selectEl.selectedIndex < 0) return 1;
    var opt = selectEl.options[selectEl.selectedIndex];
    var raw = opt.getAttribute("data-factor") || "1";
    var value = Number(raw);
    return Number.isFinite(value) && value > 0 ? value : 1;
  }

  function parseDisplay(value) {
    var normalized = String(value || "").trim().replace(",", ".");
    if (normalized === "") return 0;
    var n = Number(normalized);
    return Number.isFinite(n) ? n : 0;
  }

  function formatDisplay(value) {
    return String((Math.round(value * 100) / 100).toFixed(2)).replace(".", ",");
  }

  window.dbRecalcGrams = function (displayInputId, selectId, gramsInputId, send) {
    var displayInput = byId(displayInputId);
    var select = byId(selectId);
    var gramsInput = byId(gramsInputId);
    if (!displayInput || !select || !gramsInput) return;

    var display = parseDisplay(displayInput.value);
    var factor = getFactor(select);
    var grams = display * factor;
    gramsInput.value = String(grams);

    if (send) {
      gramsInput.dispatchEvent(new Event("change", { bubbles: true }));
    }
  };

  window.dbRecalcDisplayFromGrams = function (displayInputId, selectId, gramsInputId, sideUnitId) {
    var displayInput = byId(displayInputId);
    var select = byId(selectId);
    var gramsInput = byId(gramsInputId);
    if (!displayInput || !select || !gramsInput) return;

    var grams = Number(gramsInput.value || "0");
    var factor = getFactor(select);
    var display = factor > 0 ? grams / factor : 0;
    displayInput.value = formatDisplay(display);

    if (sideUnitId) {
      var sideUnit = byId(sideUnitId);
      if (sideUnit && select.options && select.selectedIndex >= 0) {
        var unitLabel = select.options[select.selectedIndex].getAttribute("data-unit-label") || "";
        sideUnit.textContent = unitLabel;
      }
    }
  };

  function hasOption(selectEl, value) {
    if (!selectEl || !selectEl.options) return false;
    for (var i = 0; i < selectEl.options.length; i += 1) {
      if (selectEl.options[i].value === value) return true;
    }
    return false;
  }

  function initUnitSelect(selectEl) {
    if (!selectEl) return;
    // Idempotency: initAllUnitSelects runs over `document` on every swap, so
    // an already initialized select is visited again. Without this mark it
    // would pile up one "change" listener per swap.
    if (selectEl.dataset.dbUnitsInit === "1") return;
    selectEl.dataset.dbUnitsInit = "1";
    var persistKey = selectEl.getAttribute("data-persist-key");
    var displayId = selectEl.getAttribute("data-display-id");
    var gramsId = selectEl.getAttribute("data-grams-id");
    var sideUnitId = selectEl.getAttribute("data-side-unit-id");

    if (persistKey) {
      var saved = window.localStorage ? window.localStorage.getItem(persistKey) : null;
      if (saved && hasOption(selectEl, saved)) {
        selectEl.value = saved;
      }
    }

    if (displayId && gramsId) {
      window.dbRecalcDisplayFromGrams(displayId, selectEl.id, gramsId, sideUnitId);
    }

    selectEl.addEventListener("change", function () {
      if (persistKey && window.localStorage) {
        window.localStorage.setItem(persistKey, selectEl.value);
      }
    });
  }

  function initAllUnitSelects(root) {
    var scope = root || document;
    var selects = scope.querySelectorAll("select[data-persist-key]");
    selects.forEach(initUnitSelect);
  }
  window.dbInitUnitSelects = initAllUnitSelects;

  function bindInitEvents() {
    initAllUnitSelects(document);
    // Reacts to any swap (the whole cart, #cart_events_list or a
    // #cart_card_event_{id} card): the local cart refresh (decision
    // 2026-09-10) can insert new selects into targets other than
    // #main_content.
    //
    // It walks `document`, not `event.detail.target`: with
    // hx-swap="outerHTML" —the swap every cart action uses— the event's
    // target is the *replaced* node, already detached from the DOM, so the
    // newly inserted selects would not show up in its querySelectorAll
    // (finding 42 of audit/audit_intake_event.md, checked in the browser).
    // Walking the document is cheap and idempotent: initUnitSelect marks the
    // already initialized selects with data-db-units-init.
    document.body.addEventListener("htmx:afterSwap", function () {
      initAllUnitSelects(document);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindInitEvents);
  } else {
    bindInitEvents();
  }
})();

(function () {
  // A partial refresh is not a page change and must not move the scroll
  // (frontend_conventions.md §5). The cart actions replace the whole card
  // with hx-swap="outerHTML", and when the focused node disappears from the
  // DOM —a button like `Apply all`, which has no id htmx could restore— the
  // browser may reposition the page on its own. Here the position is saved
  // before the swap and restored afterwards, only if it changed and only for
  // the cart targets.
  if (window.__dbCartScrollGuard) return;
  window.__dbCartScrollGuard = true;

  var savedScrollY = null;

  function isCartTarget(target) {
    if (!target || !target.id) return false;
    return (
      target.id.indexOf("cart_card_event_") === 0 ||
      target.id === "cart_events_list" ||
      target.id === "cart_body"
    );
  }

  function restore(clear) {
    if (savedScrollY === null) return;
    if (Math.abs(window.scrollY - savedScrollY) >= 2) {
      window.scrollTo({ top: savedScrollY, behavior: "auto" });
    }
    if (clear) savedScrollY = null;
  }

  function bind() {
    document.body.addEventListener("htmx:beforeSwap", function (event) {
      var detail = event && event.detail ? event.detail : null;
      if (!detail || !isCartTarget(detail.target)) return;
      savedScrollY = window.scrollY;
    });

    // It is restored at both moments: afterSwap sets the right position right
    // away and afterSettle keeps it if the browser moves it while settling the
    // new content.
    document.body.addEventListener("htmx:afterSwap", function () {
      restore(false);
    });
    document.body.addEventListener("htmx:afterSettle", function () {
      restore(true);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
