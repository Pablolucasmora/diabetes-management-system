(function () {
  if (window.__dbFoodDetailBootstrapped) {
    if (typeof window.dbFoodDetailBindAll === "function") {
      window.dbFoodDetailBindAll(document);
    }
    if (typeof window.dbFoodDetailSyncCart === "function") {
      window.dbFoodDetailSyncCart(document);
    }
    return;
  }
  window.__dbFoodDetailBootstrapped = true;

  function byId(id) {
    return document.getElementById(id);
  }

  function toNumber(value) {
    var n = Number(value);
    return Number.isFinite(n) ? n : 0;
  }

  function parseDisplay(value) {
    var normalized = String(value || "").trim().replace(",", ".");
    if (!normalized) return 0;
    var n = Number(normalized);
    return Number.isFinite(n) ? n : 0;
  }

  function formatValue(value, decimals) {
    var d = typeof decimals === "number" ? decimals : 1;
    var factor = Math.pow(10, d);
    var rounded = Math.round(value * factor) / factor;
    return String(rounded.toFixed(d)).replace(".", ",");
  }

  function selectedOption(selectEl) {
    if (!selectEl || !selectEl.options || selectEl.selectedIndex < 0) return null;
    return selectEl.options[selectEl.selectedIndex];
  }

  function getFactor(selectEl) {
    var opt = selectedOption(selectEl);
    if (!opt) return 1;
    var raw = opt.getAttribute("data-factor") || "1";
    var n = Number(raw);
    return Number.isFinite(n) && n > 0 ? n : 1;
  }

  function getUnitLabel(selectEl) {
    var opt = selectedOption(selectEl);
    if (!opt) return "serving";
    return opt.getAttribute("data-unit-label") || "serving";
  }

  function setCartVisible(visible) {
    var cart = byId("cart_button");
    if (!cart) return;
    if (visible) {
      cart.style.visibility = "";
      cart.style.opacity = "";
      cart.style.pointerEvents = "";
      cart.classList.remove("invisible", "opacity-0", "pointer-events-none");
      cart.classList.add("opacity-100");
      return;
    }
    cart.classList.remove("opacity-100");
    cart.classList.add("invisible", "opacity-0", "pointer-events-none");
  }

  function syncCartVisibility() {
    var hideCart = !!document.querySelector("[data-hide-cart='true']");
    setCartVisible(!hideCart);
  }
  window.dbFoodDetailSyncCart = syncCartVisibility;

  function updateMacros(root, grams) {
    var nodes = root.querySelectorAll("[data-detail-macro-key]");
    for (var i = 0; i < nodes.length; i += 1) {
      var node = nodes[i];
      var per100 = toNumber(node.getAttribute("data-per100"));
      var value = (grams * per100) / 100;
      var unit = node.getAttribute("data-unit") || "g";
      var decimals = unit === "kcal" ? 0 : 1;
      node.textContent = formatValue(value, decimals) + " " + unit;
    }
  }

  function getRefs(root) {
    var displayId = root.getAttribute("data-detail-display-id");
    var selectId = root.getAttribute("data-detail-select-id");
    var gramsId = root.getAttribute("data-detail-grams-id");
    var sideUnitId = root.getAttribute("data-detail-side-unit-id");
    var plateValueId = root.getAttribute("data-detail-plate-value-id");
    var plateUnitId = root.getAttribute("data-detail-plate-unit-id");
    var plateUnitBtnId = root.getAttribute("data-detail-plate-unit-btn-id");
    var plateGramsId = root.getAttribute("data-detail-plate-grams-id");
    var plateEquivalentId = root.getAttribute("data-detail-plate-equivalent-id");
    var leftoversId = root.getAttribute("data-detail-leftovers-id");
    return {
      displayInput: byId(displayId),
      select: byId(selectId),
      gramsInput: byId(gramsId),
      sideUnit: byId(sideUnitId),
      plateValueInput: byId(plateValueId),
      plateUnitInput: byId(plateUnitId),
      plateUnitBtn: byId(plateUnitBtnId),
      plateGramsInput: byId(plateGramsId),
      plateEquivalent: byId(plateEquivalentId),
      leftovers: byId(leftoversId),
    };
  }

  function persist(root, refs) {
    var key = root.getAttribute("data-detail-persist-key");
    if (!key || !window.localStorage || !refs.gramsInput || !refs.select) return;
    var payload = {
      grams: String(refs.gramsInput.value || "0"),
      unit: String(refs.select.value || "portion"),
      plateValue: refs.plateValueInput ? String(refs.plateValueInput.value || "100") : "100",
      plateUnit: refs.plateUnitInput ? String(refs.plateUnitInput.value || "%") : "%",
    };
    window.localStorage.setItem(key, JSON.stringify(payload));
  }

  function restore(root, refs) {
    var key = root.getAttribute("data-detail-persist-key");
    if (!key || !window.localStorage || !refs.gramsInput || !refs.select) return;
    var raw = window.localStorage.getItem(key);
    if (!raw) return;
    try {
      var payload = JSON.parse(raw);
      if (payload && typeof payload.unit === "string") {
        refs.select.value = payload.unit;
      }
      if (payload && payload.grams != null) {
        refs.gramsInput.value = String(payload.grams);
      }
      if (refs.plateValueInput && payload && payload.plateValue != null) {
        refs.plateValueInput.value = String(payload.plateValue);
      }
      if (refs.plateUnitInput && payload && typeof payload.plateUnit === "string") {
        refs.plateUnitInput.value = payload.plateUnit === "g" ? "g" : "%";
      }
    } catch (_) {}
  }

  function updatePlateUnitButton(refs) {
    if (!refs || !refs.plateUnitBtn || !refs.plateUnitInput) return;
    refs.plateUnitBtn.textContent = refs.plateUnitInput.value === "g" ? "g" : "%";
  }

  function updatePlateEquivalent(root, refs, plateGrams) {
    if (!refs || !refs.plateEquivalent) return;
    var unit = root.getAttribute("data-detail-base-unit") || "g";
    var totalGrams = Math.max(0, toNumber(refs.gramsInput ? refs.gramsInput.value : "0"));
    refs.plateEquivalent.textContent =
      "Total amount (plate amount): " +
      formatValue(totalGrams, 1) +
      " (" +
      formatValue(plateGrams, 1) +
      ") " +
      unit;
  }

  function updateLeftovers(root, refs, plateGrams) {
    if (!refs || !refs.leftovers) return;
    var unit = root.getAttribute("data-detail-base-unit") || "g";
    var totalGrams = Math.max(0, toNumber(refs.gramsInput ? refs.gramsInput.value : "0"));
    var leftovers = Math.max(0, totalGrams - Math.max(0, plateGrams));
    refs.leftovers.textContent = "Will be saved in fridge: " + formatValue(leftovers, 1) + " " + unit;
  }

  function platedGramsFromState(root, refs, normalizeInput) {
    if (!refs || !refs.gramsInput) return 0;
    var shouldNormalize = !!normalizeInput;
    var totalGrams = Math.max(0, toNumber(refs.gramsInput.value || "0"));
    if (!refs.plateGramsInput || !refs.plateValueInput || !refs.plateUnitInput) {
      return totalGrams;
    }
    var unit = refs.plateUnitInput ? refs.plateUnitInput.value : "%";
    var rawValue = refs.plateValueInput ? parseDisplay(refs.plateValueInput.value) : 100;
    var grams = 0;
    if (unit === "g") {
      grams = Math.max(0, Math.min(totalGrams, rawValue));
      if (shouldNormalize && refs.plateValueInput) {
        refs.plateValueInput.value = formatValue(grams, 1);
      }
    } else {
      var pct = Math.max(0, Math.min(100, rawValue));
      if (shouldNormalize && refs.plateValueInput) {
        refs.plateValueInput.value = formatValue(pct, 1);
      }
      grams = (totalGrams * pct) / 100;
    }
    grams = Math.max(0, Math.min(totalGrams, grams));
    refs.plateGramsInput.value = String(grams);
    updatePlateUnitButton(refs);
    updatePlateEquivalent(root, refs, grams);
    updateLeftovers(root, refs, grams);
    return grams;
  }

  function refreshPlate(root, refs, normalizeInput) {
    var plated = platedGramsFromState(root, refs, normalizeInput);
    updateMacros(root, plated);
  }

  function syncDisplayFromGrams(root, refs) {
    if (!refs.displayInput || !refs.select || !refs.gramsInput) return;
    var grams = toNumber(refs.gramsInput.value || "0");
    var factor = getFactor(refs.select);
    var display = factor > 0 ? grams / factor : 0;
    refs.displayInput.value = formatValue(display, 2);
    if (refs.sideUnit) {
      refs.sideUnit.textContent = getUnitLabel(refs.select);
    }
    refreshPlate(root, refs, false);
  }

  function syncGramsFromDisplay(root, refs) {
    if (!refs.displayInput || !refs.select || !refs.gramsInput) return;
    var display = parseDisplay(refs.displayInput.value);
    var grams = display * getFactor(refs.select);
    refs.gramsInput.value = String(grams);
    if (refs.sideUnit) {
      refs.sideUnit.textContent = getUnitLabel(refs.select);
    }
    refreshPlate(root, refs, true);
  }

  function bindOne(root) {
    if (!root || root.dataset.detailBound === "1") return;
    root.dataset.detailBound = "1";

    var refs = getRefs(root);
    if (!refs.displayInput || !refs.select || !refs.gramsInput) return;

    restore(root, refs);
    updatePlateUnitButton(refs);
    syncDisplayFromGrams(root, refs);

    refs.displayInput.addEventListener("change", function () {
      syncGramsFromDisplay(root, refs);
      persist(root, refs);
    });
    refs.displayInput.addEventListener("blur", function () {
      syncGramsFromDisplay(root, refs);
      persist(root, refs);
    });

    refs.select.addEventListener("change", function () {
      syncDisplayFromGrams(root, refs);
      persist(root, refs);
    });

    if (refs.plateValueInput) {
      refs.plateValueInput.addEventListener("input", function () {
        refreshPlate(root, refs, false);
        persist(root, refs);
      });
      refs.plateValueInput.addEventListener("change", function () {
        refreshPlate(root, refs, true);
        persist(root, refs);
      });
      refs.plateValueInput.addEventListener("blur", function () {
        refreshPlate(root, refs, true);
        persist(root, refs);
      });
    }
  }

  function bindAll(scope) {
    var root = scope || document;
    var nodes = root.querySelectorAll("[data-food-detail='true']");
    for (var i = 0; i < nodes.length; i += 1) {
      bindOne(nodes[i]);
    }
  }
  window.dbFoodDetailBindAll = bindAll;

  window.dbFoodDetailRefresh = function (rootId) {
    var root = typeof rootId === "string" ? byId(rootId) : rootId;
    if (!root) return;
    var refs = getRefs(root);
    syncGramsFromDisplay(root, refs);
    persist(root, refs);
  };

  window.dbFoodDetailOnUnitChange = function (rootId) {
    var root = typeof rootId === "string" ? byId(rootId) : rootId;
    if (!root) return;
    var refs = getRefs(root);
    syncDisplayFromGrams(root, refs);
    persist(root, refs);
  };

  window.dbFoodDetailPlateRefresh = function (rootId) {
    var root = typeof rootId === "string" ? byId(rootId) : rootId;
    if (!root) return;
    var refs = getRefs(root);
    refreshPlate(root, refs, false);
    persist(root, refs);
  };

  window.dbFoodDetailTogglePlateUnit = function (rootId) {
    var root = typeof rootId === "string" ? byId(rootId) : rootId;
    if (!root) return;
    var refs = getRefs(root);
    if (!refs.plateUnitInput || !refs.plateValueInput) return;

    var total = toNumber(refs.gramsInput ? refs.gramsInput.value : "0");
    var currentPlated = platedGramsFromState(root, refs, false);
    if (refs.plateUnitInput.value === "%") {
      refs.plateUnitInput.value = "g";
      refs.plateValueInput.value = formatValue(currentPlated, 1);
    } else {
      refs.plateUnitInput.value = "%";
      var pct = total > 0 ? (currentPlated * 100) / total : 0;
      refs.plateValueInput.value = formatValue(pct, 1);
    }
    refreshPlate(root, refs, true);
    persist(root, refs);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      bindAll(document);
      syncCartVisibility();
    });
  } else {
    bindAll(document);
    syncCartVisibility();
  }

  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event && event.detail ? event.detail.target : null;
    bindAll(target || document);
    syncCartVisibility();
  });

  document.body.addEventListener("recipe-amount-updated", function (event) {
    var detail = event && event.detail ? event.detail : {};
    var recipeId = Number(detail.recipe_id || 0);
    if (!recipeId) return;
    var root = byId("food_detail_recipe_" + String(recipeId));
    if (!root) return;
    var refs = getRefs(root);
    if (!refs || !refs.gramsInput || !refs.select) return;

    var totalAmount = Number(detail.total_amount || 0);
    if (!Number.isFinite(totalAmount) || totalAmount <= 0) return;

    refs.gramsInput.value = String(totalAmount);
    if (refs.select.options && refs.select.options.length > 0) {
      var opt = refs.select.options[0];
      if (opt && opt.value === "portion") {
        var unit = root.getAttribute("data-detail-base-unit") || "g";
        var rounded = Math.max(1, Math.round(totalAmount));
        opt.setAttribute("data-factor", String(totalAmount));
        opt.textContent = "serving (" + String(rounded) + unit + ")";
      }
    }
    syncDisplayFromGrams(root, refs);
    persist(root, refs);
  });
})();
