// The filters pop-up of Food (frontend_conventions.md §9.3). The controls of the pop-up
// are a draft: only Confirm copies them to the fields the list requests include.
(function () {
  if (window.__dbFoodFiltersReady) return;
  window.__dbFoodFiltersReady = true;
  var MODAL_ID = "food_filters_modal";

  function byId(id) {
    return document.getElementById(id);
  }

  function mealChecks() {
    return document.querySelectorAll("[data-food-filter-meal]");
  }

  // Opening discards what a cancelled pop-up left in the draft.
  window.dbOpenFoodFilters = function () {
    var applied = byId("food_recipes_meal");
    var chosen = applied && applied.value ? applied.value.split(",") : [];
    mealChecks().forEach(function (check) {
      check.checked = chosen.indexOf(check.value) !== -1;
    });
    if (window.dbOpenModal) window.dbOpenModal(MODAL_ID);
  };

  // Back to no filters, in the draft: like any other change, Confirm applies it.
  window.dbResetFoodFilters = function () {
    mealChecks().forEach(function (check) {
      check.checked = false;
    });
  };

  // Runs before htmx sends the request of the Confirm button, which includes the field.
  window.dbApplyFoodFilters = function () {
    var applied = byId("food_recipes_meal");
    var mark = byId("food_filters_active");
    var chosen = [];
    mealChecks().forEach(function (check) {
      if (check.checked) chosen.push(check.value);
    });
    if (applied) applied.value = chosen.join(",");
    if (mark) mark.classList.toggle("hidden", chosen.length === 0);
    if (window.dbCloseModal) window.dbCloseModal(MODAL_ID);
  };
})();
