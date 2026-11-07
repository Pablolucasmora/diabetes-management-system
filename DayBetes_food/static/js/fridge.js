// Events of the fridge routes (code_conventions.md §9.5, HX-Trigger): the actions
// pop-up closes after a change, and a notice says what happened where the page
// does not show it (error_conventions.md §7.1). Presentation only.
(function () {
  if (window.__dbFridgeBootstrapped) return;
  window.__dbFridgeBootstrapped = true;

  var ACTIONS_MODAL_ID = "food_actions_modal";
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

  // A food saved into a new container, from its page or from its row.
  document.body.addEventListener("fridgeStored", function (event) {
    closeActions();
    var location = event && event.detail ? event.detail.location : "";
    notice(STORED_NOTICES[location] || STORED_NOTICES.fridge);
  });
})();
