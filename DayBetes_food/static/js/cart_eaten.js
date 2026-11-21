// `Eating` in a cart card's macros summary (frontend_conventions.md §7.14): the
// served totals of each plate, scaled by what is typed in its `Eaten` field
// before confirming. Only a display: nothing is stored or sent. A value that
// confirm would reject (not a number, 0, over the plate) leaves that plate whole
// here; confirm still says why.
(function () {
  if (window.__dbCartEatenBootstrapped) return;
  window.__dbCartEatenBootstrapped = true;

  var MACROS = ["carbs", "sugars", "fats", "saturated", "proteins", "fiber"];

  function parseNumber(text) {
    var normalized = String(text || "").trim().replace(",", ".");
    if (normalized === "") return null;
    var value = Number(normalized);
    return Number.isFinite(value) ? value : NaN;
  }

  function plateFraction(form, plateId, plateAmount) {
    var input = form.querySelector('[name="ingested_value_' + plateId + '"]');
    if (!input) return 1;
    var value = parseNumber(input.value);
    if (value === null || Number.isNaN(value)) return 1;
    var unit = form.querySelector('[name="ingested_unit_' + plateId + '"]:checked');
    var fraction = unit && unit.value === "g" ? (plateAmount > 0 ? value / plateAmount : NaN) : value / 100;
    return fraction > 0 && fraction <= 1 ? fraction : 1;
  }

  function format(value) {
    return (Math.round(value * 10) / 10).toFixed(1);
  }

  function update(summary) {
    var eventId = summary.getAttribute("data-eaten-summary");
    var form = document.querySelector('form[data-draft-key="cart_eaten_' + eventId + '"]');
    var plates;
    try {
      plates = JSON.parse(summary.getAttribute("data-eaten-plates") || "{}");
    } catch (_) {
      return;
    }
    var eaten = { amount: 0, kcal: 0 };
    MACROS.forEach(function (key) { eaten[key] = 0; });
    var partial = false;
    Object.keys(plates).forEach(function (plateId) {
      var plate = plates[plateId];
      var fraction = form ? plateFraction(form, plateId, plate.amount) : 1;
      if (fraction < 1) partial = true;
      Object.keys(eaten).forEach(function (key) { eaten[key] += (plate[key] || 0) * fraction; });
    });

    var line = summary.querySelector("[data-eaten-line]");
    var total = summary.querySelector("[data-eaten-total]");
    if (line) line.classList.toggle("hidden", !partial);
    if (total) total.textContent = format(eaten.amount) + " g | " + Math.round(eaten.kcal) + " kcal";
    summary.querySelectorAll("[data-eaten-value]").forEach(function (el) {
      el.textContent = format(eaten[el.getAttribute("data-eaten-value")] || 0) + " g";
    });
    summary.querySelectorAll("[data-served-note]").forEach(function (el) {
      el.classList.toggle("hidden", !partial);
    });
  }

  function updateAll() {
    document.querySelectorAll("[data-eaten-summary]").forEach(update);
  }

  function isEatenField(el) {
    return el && el.name && /^ingested_(value|unit)_/.test(el.name);
  }

  document.addEventListener("input", function (event) {
    if (isEatenField(event.target)) updateAll();
  });
  document.addEventListener("change", function (event) {
    if (isEatenField(event.target)) updateAll();
  });
  // A repainted card or summary, and the draft restored on load
  // (static/js/form_drafts.js fills the fields without events).
  document.addEventListener("htmx:afterSettle", function () { setTimeout(updateAll, 0); });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { setTimeout(updateAll, 0); });
  } else {
    setTimeout(updateAll, 0);
  }
})();
