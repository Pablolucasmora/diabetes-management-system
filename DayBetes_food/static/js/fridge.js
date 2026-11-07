// Events of the fridge routes (code_conventions.md §9.5, HX-Trigger): the actions
// pop-up closes after a change, a notice says what happened where the page does
// not show it (error_conventions.md §7.1), and the leftovers pop-up of the cart
// opens and closes. Presentation only.
(function () {
  if (window.__dbFridgeBootstrapped) return;
  window.__dbFridgeBootstrapped = true;

  var ACTIONS_MODAL_ID = "food_actions_modal";
  var RECIPE_ADD_MODAL_ID = "recipe_add_modal";
  var LEFTOVERS_MODAL_ID = "cart_leftovers_modal";
  var LEFTOVERS_BODY_ID = "cart_leftovers_body";
  var STORED_NOTICES = { fridge: "Saved to the fridge", freezer: "Saved to the freezer" };

  function closeActions() {
    if (window.dbCloseModal) window.dbCloseModal(ACTIONS_MODAL_ID);
  }

  function notice(message) {
    if (window.dbShowAppNotice) window.dbShowAppNotice(message);
  }

  // A container edited, discarded or taken from: the list is already repainted.
  document.body.addEventListener("fridgeChanged", closeActions);

  // Taken into a meal, which this page does not show.
  document.body.addEventListener("fridgeTaken", function () {
    notice("Added to your meal");
  });

  // A food or a recipe saved into a new container, from its page, its row or the
  // recipe's step before adding.
  document.body.addEventListener("fridgeStored", function (event) {
    closeActions();
    if (window.dbCloseModal) window.dbCloseModal(RECIPE_ADD_MODAL_ID);
    var location = event && event.detail ? event.detail.location : "";
    notice(STORED_NOTICES[location] || STORED_NOTICES.fridge);
  });

  // The leftovers pop-up of the cart (components/cart/cart_leftovers.py): the
  // confirm route sends it instead of confirming, and it opens once it is in.
  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event && event.detail ? event.detail.target : null;
    if (target && target.id === LEFTOVERS_BODY_ID && window.dbOpenModal) window.dbOpenModal(LEFTOVERS_MODAL_ID);
  });

  // The meal was confirmed, from its card or from the pop-up. Its eaten draft is
  // done (cart_components.eaten_draft_key): confirmed from the pop-up, the card's
  // own form never sees the response that would clear it.
  document.body.addEventListener("mealConfirmed", function (event) {
    if (window.dbCloseModal) window.dbCloseModal(LEFTOVERS_MODAL_ID);
    var eventId = event && event.detail ? event.detail.event_id : null;
    if (eventId == null) return;
    try { window.localStorage.removeItem("cart_eaten_" + eventId); } catch (_) {}
  });
})();
