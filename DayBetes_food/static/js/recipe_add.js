// The step before adding a recipe to a meal (frontend_conventions.md §9.7).
(function () {
  if (window.__dbRecipeAddReady) return;
  window.__dbRecipeAddReady = true;
  var MODAL_ID = "recipe_add_modal";

  // The form arrived complete: only now does the pop-up open.
  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event && event.detail ? event.detail.target : null;
    if (target && target.id === "recipe_add_body" && window.dbOpenModal) window.dbOpenModal(MODAL_ID);
  });

  // Success of POST /add_recipe (HX-Trigger).
  document.body.addEventListener("recipeAdded", function () {
    if (window.dbCloseModal) window.dbCloseModal(MODAL_ID);
    if (window.dbShowAppNotice) window.dbShowAppNotice("Added to the meal");
  });
})();
