// Rescue pop-up (frontend_conventions.md §9.6). Presentation only: the lines
// are painted by the server and the server converts every amount. This
// shows the picker or the "+ Add another food" button, removes lines, moves
// an amount with − / +, adds a repeated food to its line and closes the
// pop-up when the rescue is registered. Nothing is stored in localStorage
// and no field takes the focus on its own (it would open a phone keyboard).
//
// Motion (frontend_conventions.md §10): opacity and transform, short, and
// none when the system asks to reduce motion. The card's height is the one
// exception the user asked for: it grows and shrinks instead of jumping.
(function () {
  if (window.__dbRescueBootstrapped) return;
  window.__dbRescueBootstrapped = true;

  var MODAL_ID = "rescue_modal";
  var FADE_MS = 150;
  // Step of the − / + buttons per amount unit (AmountInputUnit codes).
  var STEP_BY_UNIT = { portion: 1, g: 10, oz: 1, lb: 0.25 };
  var HEIGHT_MS = 220;
  var pickerFadeStartedAt = 0;
  var heightBeforeSwap = null;

  function byId(id) {
    return document.getElementById(id);
  }

  function reducedMotion() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function lineCount() {
    var lines = byId("rescue_lines");
    return lines ? lines.querySelectorAll("[data-rescue-line]").length : 0;
  }

  // ---- Motion helpers ----

  function clearMotion(el) {
    el.style.transition = "";
    el.style.opacity = "";
    el.style.transform = "";
  }

  function fadeOut(el, done) {
    if (!el || reducedMotion()) {
      if (done) done();
      return;
    }
    el.style.transition = "opacity " + FADE_MS + "ms ease, transform " + FADE_MS + "ms ease";
    el.style.opacity = "0";
    el.style.transform = "translateY(-4px)";
    window.setTimeout(function () {
      if (done) done();
      clearMotion(el);
    }, FADE_MS);
  }

  function riseIn(el) {
    if (!el || reducedMotion()) return;
    el.removeAttribute("data-enter");
    void el.offsetWidth;
    el.setAttribute("data-enter", "");
  }

  function fadeIn(el) {
    if (!el || reducedMotion()) return;
    el.style.opacity = "0";
    el.style.transform = "translateY(4px)";
    void el.offsetWidth;
    el.style.transition = "opacity 200ms ease, transform 200ms cubic-bezier(0.2, 0.8, 0.2, 1)";
    el.style.opacity = "1";
    el.style.transform = "none";
    window.setTimeout(function () { clearMotion(el); }, 220);
  }

  function card() {
    var form = byId("rescue_form");
    return form ? form.closest("[data-modal-card]") : null;
  }

  // Runs `change` and animates the pop-up card from its old height to the
  // new one, instead of letting it jump (§10, exception asked by the user).
  // `fromHeight` is passed when the change already happened (an htmx swap).
  function animateCardHeight(change, fromHeight) {
    var el = card();
    if (!el || reducedMotion()) {
      if (change) change();
      return;
    }
    var from = fromHeight != null ? fromHeight : el.offsetHeight;
    if (change) change();
    var to = el.offsetHeight;
    if (Math.abs(to - from) < 2) return;
    el.style.height = from + "px";
    el.style.overflow = "hidden";
    void el.offsetHeight;
    el.style.transition = "height " + HEIGHT_MS + "ms cubic-bezier(0.2, 0.8, 0.2, 1)";
    el.style.height = to + "px";
    window.setTimeout(function () {
      el.style.height = "";
      el.style.overflow = "";
      el.style.transition = "";
    }, HEIGHT_MS + 20);
  }

  // ---- Picker and lines ----

  function setPickerVisible(show) {
    var picker = byId("rescue_picker");
    var addAnother = byId("rescue_add_another");
    if (picker) picker.classList.toggle("hidden", !show);
    if (addAnother) addAnother.classList.toggle("hidden", show || lineCount() === 0);
  }

  function showPicker() {
    setPickerVisible(true);
    fadeIn(byId("rescue_picker"));
  }

  function hidePicker() {
    var picker = byId("rescue_picker");
    var wasHidden = picker && picker.classList.contains("hidden");
    setPickerVisible(false);
    if (!wasHidden) fadeIn(byId("rescue_add_another"));
  }

  function clearSearch() {
    var search = byId("rescue_search_input");
    if (search && search.value) {
      search.value = "";
      if (window.htmx) window.htmx.trigger(search, "input");
    }
  }

  function refresh() {
    var submit = byId("rescue_submit");
    if (submit) submit.disabled = lineCount() === 0;
  }

  function formatAmount(value) {
    return String(Math.round(value * 100) / 100);
  }

  // Picking a food already in the list adds to its line instead of a second
  // one, as the cart does (§9.6; the server merges them anyway, §4.6.4).
  // Returns false when there is no such line.
  function addToExistingLine(key) {
    var lines = byId("rescue_lines");
    if (!lines || !key) return false;
    var line = null;
    lines.querySelectorAll("[data-rescue-line]").forEach(function (el) {
      if (el.getAttribute("data-rescue-line") === key) line = el;
    });
    if (!line) return false;
    var input = line.querySelector("input[name='amount_value']");
    var unit = line.querySelector("select[name='amount_unit']");
    var servingG = parseFloat(line.getAttribute("data-rescue-serving-g") || "");
    var current = parseFloat(String(input && input.value ? input.value : "0").replace(",", "."));
    if (!Number.isFinite(current)) current = 0;
    if (input && unit && unit.value === "portion") {
      input.value = formatAmount(current + 1);
    } else if (input && unit && unit.value === "g" && Number.isFinite(servingG) && servingG > 0) {
      input.value = formatAmount(current + servingG);
    }
    // Otherwise there is no reliable amount to add: the line is only
    // highlighted so the user adjusts it.
    line.style.transition = "box-shadow 200ms ease";
    line.style.boxShadow = "0 0 0 2px var(--color-ink)";
    window.setTimeout(function () { line.style.boxShadow = ""; }, 700);
    return true;
  }

  function stepAmount(button) {
    var line = button.closest("[data-rescue-line]");
    if (!line) return;
    var input = line.querySelector("input[name='amount_value']");
    var unit = line.querySelector("select[name='amount_unit']");
    if (!input) return;
    var step = STEP_BY_UNIT[unit ? unit.value : "g"] || 1;
    var current = parseFloat(String(input.value || "0").replace(",", "."));
    if (!Number.isFinite(current)) current = 0;
    var next = current + step * Number(button.getAttribute("data-rescue-step") || "0");
    // Never down to zero: a portion of 0 g is not admitted (decision 2026-09-22).
    if (next <= 0) next = current > step ? step : current;
    input.value = formatAmount(next);
  }

  // Capture phase: the pop-up card stops the bubbling of its clicks
  // (components/modal.py), so a listener on document would never see them.
  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest || !target.closest("#rescue_form")) return;

    var pick = target.closest("[data-rescue-pick]");
    if (pick) {
      if (addToExistingLine(pick.getAttribute("data-rescue-pick"))) {
        // Stops htmx from asking for a second line.
        event.preventDefault();
        event.stopPropagation();
        fadeOut(byId("rescue_picker"), function () {
          animateCardHeight(function () {
            clearSearch();
            hidePicker();
          });
        });
        return;
      }
      // The picker starts to fade while the line is requested; htmx
      // carries on with the click.
      pickerFadeStartedAt = Date.now();
      var picker = byId("rescue_picker");
      if (picker && !reducedMotion()) {
        picker.style.transition = "opacity " + FADE_MS + "ms ease, transform " + FADE_MS + "ms ease";
        picker.style.opacity = "0";
        picker.style.transform = "translateY(-4px)";
      }
      return;
    }
    var remove = target.closest("[data-rescue-remove]");
    if (remove) {
      var line = remove.closest("[data-rescue-line]");
      fadeOut(line, function () {
        animateCardHeight(function () {
          if (line) line.remove();
          if (lineCount() === 0) showPicker();
          else setPickerVisible(false);
        });
        refresh();
      });
      return;
    }
    var step = target.closest("[data-rescue-step]");
    if (step) {
      stepAmount(step);
      return;
    }
    if (target.closest("#rescue_add_another")) {
      animateCardHeight(function () {
        byId("rescue_add_another").classList.add("hidden");
        showPicker();
      });
    }
  }, true);

  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event && event.detail ? event.detail.target : null;
    if (!target) return;
    if (target.id === "rescue_lines") {
      // The new line takes no space until the picker has faded out: then
      // the picker leaves and the line comes in as one height change of the
      // card, instead of the card growing first and shrinking after.
      var lines = target.querySelectorAll("[data-rescue-line]");
      var line = lines.length ? lines[lines.length - 1] : null;
      if (line) line.classList.add("hidden");
      var wait = Math.max(0, FADE_MS - (Date.now() - pickerFadeStartedAt));
      window.setTimeout(function () {
        animateCardHeight(function () {
          var picker = byId("rescue_picker");
          if (picker) clearMotion(picker);
          clearSearch();
          hidePicker();
          if (line) line.classList.remove("hidden");
        });
        riseIn(line);
        refresh();
      }, reducedMotion() ? 0 : wait);
    } else if (heightBeforeSwap != null && (target.id === "rescue_picker_results" || target.id === "rescue_form_error")) {
      // New search results or a validation message: the card follows.
      var from = heightBeforeSwap;
      heightBeforeSwap = null;
      animateCardHeight(null, from);
    } else if (target.id === "rescue_modal_body") {
      // The form arrived complete (with its food list): only now does the
      // pop-up open, in one animation instead of growing as parts arrive.
      refresh();
      if (window.dbOpenModal) window.dbOpenModal(MODAL_ID);
    }
  });

  document.body.addEventListener("htmx:beforeSwap", function (event) {
    var target = event && event.detail ? event.detail.target : null;
    if (!target || (target.id !== "rescue_picker_results" && target.id !== "rescue_form_error")) return;
    var el = card();
    heightBeforeSwap = el ? el.offsetHeight : null;
  });

  // The line request failed: the picker comes back.
  document.body.addEventListener("htmx:responseError", function (event) {
    var target = event && event.detail ? event.detail.target : null;
    if (target && target.id === "rescue_lines") {
      var picker = byId("rescue_picker");
      if (picker) clearMotion(picker);
    }
  });

  // Success of POST /food/rescue/log (HX-Trigger).
  document.body.addEventListener("rescueRegistered", function () {
    if (window.dbCloseModal) window.dbCloseModal(MODAL_ID);
    if (window.dbShowAppNotice) window.dbShowAppNotice("Rescue registered");
  });
})();
