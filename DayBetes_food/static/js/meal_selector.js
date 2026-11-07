// The meal selector of Food (frontend_conventions.md §7.7). When an add creates a
// new meal because none was chosen, the route sends `mealCreated` (HX-Trigger)
// with its id and label: the meal is added to the selector and left chosen, so
// the next add goes to the same meal instead of creating another one.
// Presentation only.
(function () {
  if (window.__dbMealSelectorReady) return;
  window.__dbMealSelectorReady = true;

  document.body.addEventListener("mealCreated", function (event) {
    var select = document.getElementById("meal_selector");
    var detail = event && event.detail ? event.detail : null;
    if (!select || !detail || detail.id == null) return;
    var id = String(detail.id);

    var option = null;
    for (var i = 0; i < select.options.length; i++) {
      if (select.options[i].value === id) option = select.options[i];
    }
    if (!option) {
      option = new Option(detail.label || "Meal " + id, id);
      var newMeal = null;
      for (var j = 0; j < select.options.length; j++) {
        if (select.options[j].value === "0") newMeal = select.options[j];
      }
      select.insertBefore(option, newMeal);
    }
    // The "- No meals yet -" placeholder no longer applies.
    for (var k = select.options.length - 1; k >= 0; k--) {
      if (select.options[k].value === "") select.remove(k);
    }
    select.style.color = "";
    select.value = id;
    // The same change the user would make: the plate selector is redrawn with
    // the new meal's plates and the meal name box is hidden.
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
})();
