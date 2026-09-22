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
    // Idempotencia: initAllUnitSelects se ejecuta sobre `document` en cada
    // swap, así que un select ya inicializado se vuelve a visitar. Sin esta
    // marca acumularía un listener "change" por swap.
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
    // Reacciona a cualquier swap (carrito completo, #cart_events_list o una
    // tarjeta #cart_card_event_{id}): el refresco local del carrito
    // (decisión 2026-09-10) puede insertar selects nuevos en targets que no
    // son #main_content.
    //
    // Se recorre `document`, no `event.detail.target`: con hx-swap="outerHTML"
    // —el swap que usan todas las acciones del carrito— el target del evento
    // es el nodo *sustituido*, que ya está desconectado del DOM, así que los
    // selects recién insertados no aparecerían en su querySelectorAll
    // (hallazgo 42 de audit/audit_intake_event.md, comprobado en navegador).
    // Recorrer el documento es barato y idempotente: initUnitSelect marca los
    // selects ya inicializados con data-db-units-init.
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
