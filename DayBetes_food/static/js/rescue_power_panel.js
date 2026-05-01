(function () {
  var STORAGE_KEY = "db_rescue_power_state_v1";

  function byId(id) { return document.getElementById(id); }
  function num(v, d) {
    var n = parseFloat(String(v == null ? "" : v).replace(",", "."));
    return Number.isFinite(n) ? n : d;
  }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function nowHHMM() {
    var d = new Date();
    var hh = String(d.getHours()).padStart(2, "0");
    var mm = String(d.getMinutes()).padStart(2, "0");
    return hh + ":" + mm;
  }

  function readState() {
    try {
      var raw = window.localStorage ? window.localStorage.getItem(STORAGE_KEY) : null;
      return raw ? JSON.parse(raw) : null;
    } catch (_) { return null; }
  }

  function writeState(state) {
    try {
      if (window.localStorage) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state || {}));
    } catch (_) {}
  }

  function recalc() {
    var unit = byId("rescue_unit");
    var amountInput = byId("rescue_amount_value");
    var percentInput = byId("rescue_eaten_percent");
    var servingHidden = byId("rescue_serving_g");
    var availableHidden = byId("rescue_available_g");
    var consumedHidden = byId("rescue_consumed_g");
    var consumedLabel = byId("rescue_consumed_label");
    var leftoverLabel = byId("rescue_leftover_label");
    if (!unit || !amountInput || !percentInput || !servingHidden || !availableHidden || !consumedHidden) return;

    var amount = Math.max(0, num(amountInput.value, 0));
    var serving = Math.max(0.001, num(servingHidden.value, 100));
    var available = Math.max(0, num(availableHidden.value, 0));
    var percent = clamp(num(percentInput.value, 100), 0, 100);

    var baseG = unit.value === "servings" ? amount * serving : amount;
    var consumed = clamp(baseG * (percent / 100.0), 0, available > 0 ? available : baseG);
    var leftover = Math.max(0, (available > 0 ? available : baseG) - consumed);

    consumedHidden.value = String(consumed.toFixed(3));
    if (consumedLabel) consumedLabel.textContent = consumed.toFixed(1) + " g";
    if (leftoverLabel) leftoverLabel.textContent = leftover.toFixed(1) + " g";

    var state = readState() || {};
    state.unit = unit.value;
    state.amount = amount;
    state.percent = percent;
    state.leftover_g = leftover;
    writeState(state);
  }

  function applyPicked(button) {
    if (!button) return;
    var entryType = button.getAttribute("data-entry_type") || "";
    var entryId = button.getAttribute("data-entry_id") || "";
    var entryName = button.getAttribute("data-entry_name") || "";
    var servingG = num(button.getAttribute("data-serving_g"), 100);
    var availableGAttr = button.getAttribute("data-available_g");
    var availableG = availableGAttr ? num(availableGAttr, 0) : 0;

    var hiddenType = byId("rescue_entry_type");
    var hiddenId = byId("rescue_entry_id");
    var hiddenServing = byId("rescue_serving_g");
    var hiddenAvailable = byId("rescue_available_g");
    var selectedLabel = byId("rescue_selected_label");
    var amountInput = byId("rescue_amount_value");

    if (hiddenType) hiddenType.value = entryType;
    if (hiddenId) hiddenId.value = entryId;
    if (hiddenServing) hiddenServing.value = String(servingG);

    var state = readState() || {};
    var sameAsLast = state.entry_type === entryType && String(state.entry_id || "") === String(entryId || "");
    var available = sameAsLast ? Math.max(0, num(state.leftover_g, availableG)) : Math.max(0, availableG || servingG);
    if (hiddenAvailable) hiddenAvailable.value = String(available);

    if (selectedLabel) selectedLabel.textContent = entryName + " · available " + available.toFixed(1) + " g";
    if (amountInput) amountInput.value = String(available.toFixed(1));

    state.entry_type = entryType;
    state.entry_id = entryId;
    state.entry_name = entryName;
    state.serving_g = servingG;
    state.leftover_g = available;
    writeState(state);
    recalc();
  }

  function restoreFromState() {
    var state = readState();
    if (!state) return;
    var unit = byId("rescue_unit");
    var amountInput = byId("rescue_amount_value");
    var percentInput = byId("rescue_eaten_percent");
    var mealHour = byId("rescue_meal_hour");
    var hiddenType = byId("rescue_entry_type");
    var hiddenId = byId("rescue_entry_id");
    var hiddenServing = byId("rescue_serving_g");
    var hiddenAvailable = byId("rescue_available_g");
    var selectedLabel = byId("rescue_selected_label");
    if (unit && state.unit) unit.value = state.unit;
    if (amountInput && state.amount != null) amountInput.value = String(state.amount);
    if (percentInput && state.percent != null) percentInput.value = String(state.percent);
    if (mealHour && !mealHour.value) mealHour.value = nowHHMM();
    if (hiddenType && state.entry_type) hiddenType.value = String(state.entry_type);
    if (hiddenId && state.entry_id != null) hiddenId.value = String(state.entry_id);
    if (hiddenServing && state.serving_g != null) hiddenServing.value = String(state.serving_g);
    if (hiddenAvailable && state.leftover_g != null) hiddenAvailable.value = String(Math.max(0, num(state.leftover_g, 0)));
    if (selectedLabel && state.entry_name) {
      selectedLabel.textContent = String(state.entry_name) + " · available " + Math.max(0, num(state.leftover_g, 0)).toFixed(1) + " g";
    }
  }

  function bind() {
    var form = byId("rescue_power_form");
    if (!form || form.dataset.rescueBound === "1") return;
    form.dataset.rescueBound = "1";

    var mealHour = byId("rescue_meal_hour");
    if (mealHour && !mealHour.value) mealHour.value = nowHHMM();
    restoreFromState();

    form.addEventListener("click", function (ev) {
      var t = ev.target;
      if (!t || !t.closest) return;
      var pick = t.closest("[data-rescue-pick='true']");
      if (!pick) return;
      ev.preventDefault();
      applyPicked(pick);
    });

    ["rescue_unit", "rescue_amount_value", "rescue_eaten_percent"].forEach(function (id) {
      var el = byId(id);
      if (el) el.addEventListener("input", recalc);
      if (el) el.addEventListener("change", recalc);
    });

    form.addEventListener("submit", function () {
      recalc();
    });

    document.body.addEventListener("htmx:afterRequest", function (ev) {
      var req = ev && ev.detail ? ev.detail.requestConfig : null;
      var path = req && req.path ? String(req.path) : "";
      if (path.indexOf("/food/rescue/log") === -1) return;
      if (!(ev.detail && ev.detail.successful)) return;
      var state = readState() || {};
      var avail = num(byId("rescue_available_g") ? byId("rescue_available_g").value : 0, 0);
      var consumed = num(byId("rescue_consumed_g") ? byId("rescue_consumed_g").value : 0, 0);
      state.leftover_g = Math.max(0, avail - consumed);
      writeState(state);
      if (byId("rescue_available_g")) byId("rescue_available_g").value = String(state.leftover_g);
      if (byId("rescue_amount_value")) byId("rescue_amount_value").value = String(state.leftover_g.toFixed(1));
      recalc();
    });

    recalc();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
  document.body.addEventListener("htmx:afterSwap", bind);
})();
