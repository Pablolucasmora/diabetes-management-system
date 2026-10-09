(function () {
  if (window.__dbManualIntakeFormBootstrapped) {
    if (typeof window.dbManualModeInitAll === "function") {
      window.dbManualModeInitAll();
    }
    return;
  }
  window.__dbManualIntakeFormBootstrapped = true;

  // Presentation only (code_conventions.md 7.13): the server always converts
  // the totals and checks the converted values (measurement_conventions.md 5.4).
  var PER_100G = "per_100g";
  var PORTION_TOTAL = "portion_total";

  function formOf(element) {
    return element ? element.closest("form") : null;
  }

  function modeSelectOf(form) {
    return form ? form.querySelector("select[data-manual-mode]") : null;
  }

  function parseNumber(raw) {
    var text = String(raw || "").trim().replace(",", ".");
    if (!text) return null;
    var value = Number(text);
    return isFinite(value) ? value : null;
  }

  function setHint(form, text) {
    var hint = form.querySelector("[data-manual-mode-hint]");
    if (hint) hint.textContent = text || "";
  }

  // Labels follow the mode; the per-100 g `max` only applies per 100 g,
  // because a total may legitimately exceed it.
  function applyMode(form) {
    var select = modeSelectOf(form);
    if (!select) return;
    var total = select.value === PORTION_TOTAL;
    var labels = form.querySelectorAll("[data-mode-label]");
    for (var i = 0; i < labels.length; i += 1) {
      var text = total ? labels[i].dataset.labelTotal : labels[i].dataset.labelPer100;
      if (text) labels[i].textContent = text;
    }
    var fields = form.querySelectorAll("[data-max-per100]");
    for (var j = 0; j < fields.length; j += 1) {
      if (total) {
        fields[j].removeAttribute("max");
      } else {
        fields[j].setAttribute("max", fields[j].dataset.maxPer100);
      }
    }
  }

  // Edit form only (data-manual-convert): the typed values are converted on
  // screen with the form's weight, unrounded. The create form keeps the
  // smart-macros text as typed, so it only changes labels.
  function convertValues(form, nextMode, weight) {
    var fields = form.querySelectorAll("[data-nutrient-field]");
    for (var i = 0; i < fields.length; i += 1) {
      var value = parseNumber(fields[i].value);
      if (value === null) continue;
      var converted = nextMode === PORTION_TOTAL ? (value * weight) / 100 : (value * 100) / weight;
      fields[i].value = String(converted);
    }
  }

  window.dbManualModeChange = function (select) {
    var form = formOf(select);
    if (!form) return;
    var previous = select.dataset.current || PER_100G;
    var next = select.value;
    if (form.dataset.manualConvert === "true" && previous !== next) {
      var weightInput = form.querySelector("[data-manual-weight]");
      var weight = parseNumber(weightInput ? weightInput.value : "");
      if (weight === null || weight <= 0) {
        select.value = previous;
        setHint(form, "Enter the serving weight first.");
        return;
      }
      convertValues(form, next, weight);
    }
    select.dataset.current = next;
    setHint(form, "");
    applyMode(form);
  };

  window.dbManualModeInitAll = function () {
    var selects = document.querySelectorAll("select[data-manual-mode]");
    for (var i = 0; i < selects.length; i += 1) {
      selects[i].dataset.current = selects[i].value;
      applyMode(formOf(selects[i]));
    }
  };

  function attachSwapListener() {
    if (!document.body) return;
    document.body.addEventListener("htmx:afterSettle", window.dbManualModeInitAll);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      window.dbManualModeInitAll();
      attachSwapListener();
    });
  } else {
    window.dbManualModeInitAll();
    attachSwapListener();
  }
})();
