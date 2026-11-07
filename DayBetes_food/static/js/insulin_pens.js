// Insulin pens (frontend_conventions.md §9.9). Presentation only:
// - `+ New pen` in a pen selector opens the pop-up of a new pen and keeps the
//   previous choice; nothing is saved by choosing it (the cart's hx-trigger skips it).
// - `+ New brand` in that pop-up shows the fields of the new brand.
// - `penCreated` (HX-Trigger of POST /insulin/pens) closes the pop-up, adds the pen to
//   the selectors of the page and chooses it in the one that opened the pop-up.
// - `insulinChanged` (settings) closes the open pop-up and repaints the list.
(function () {
  if (window.__dbInsulinPensReady) return;
  window.__dbInsulinPensReady = true;

  var MODAL_ID = "insulin_pen_modal";
  var NEW = "new";

  function notice(message) {
    if (window.dbShowAppNotice) window.dbShowAppNotice(message);
  }

  // The settings page that is open, Pens or Brands, is repainted whole.
  function refreshSettings() {
    if (!window.htmx) return;
    if (document.getElementById("insulin_pens_body")) {
      window.htmx.ajax("GET", "/settings/insulin/pens/list", { target: "#insulin_pens_body", swap: "innerHTML" });
    }
    if (document.getElementById("insulin_brands_body")) {
      window.htmx.ajax("GET", "/settings/insulin/brands/list", { target: "#insulin_brands_body", swap: "innerHTML" });
    }
  }

  function resetPenForm() {
    var modal = document.getElementById(MODAL_ID);
    var form = modal ? modal.querySelector("[data-pen-form]") : null;
    if (!form) return;
    form.reset();
    var fields = form.querySelector("[data-new-brand-fields]");
    if (fields) fields.classList.add("hidden");
    var error = document.getElementById(MODAL_ID + "_error");
    if (error) error.innerHTML = "";
  }

  // The choice before `+ New pen`, to go back to it.
  document.addEventListener("focusin", function (event) {
    var select = event.target;
    if (select && select.matches && select.matches("select[data-pen-select]") && select.value !== NEW) {
      select.dataset.prev = select.value;
    }
  });

  document.addEventListener("change", function (event) {
    var select = event.target;
    if (!select || !select.matches) return;
    if (select.matches("select[data-pen-select]")) {
      if (select.value === NEW) {
        select.value = select.dataset.prev || "";
        window.__dbPenOpener = select;
        resetPenForm();
        if (window.dbOpenModal) window.dbOpenModal(MODAL_ID);
      } else {
        select.dataset.prev = select.value;
      }
      return;
    }
    if (select.matches("select[data-brand-select]")) {
      var form = select.closest("form");
      var fields = form ? form.querySelector("[data-new-brand-fields]") : null;
      if (fields) fields.classList.toggle("hidden", select.value !== NEW);
    }
  });

  document.body.addEventListener("penCreated", function (event) {
    var detail = event && event.detail ? event.detail : null;
    if (window.dbCloseModal) window.dbCloseModal(MODAL_ID);
    if (!detail || detail.id == null) return;
    var id = String(detail.id);
    var opener = window.__dbPenOpener;
    window.__dbPenOpener = null;
    document.querySelectorAll("select[data-pen-select]").forEach(function (select) {
      if (select.dataset.penType && select.dataset.penType !== detail.insulin_type) return;
      var newOption = select.querySelector('option[value="' + NEW + '"]');
      var option = new Option(detail.label, id);
      option.dataset.insulinType = detail.insulin_type;
      select.insertBefore(option, newOption);
    });
    if (opener && document.body.contains(opener) && opener.querySelector('option[value="' + id + '"]')) {
      opener.value = id;
      opener.dataset.prev = id;
      // The same change the user would make: the cart saves it.
      opener.dispatchEvent(new Event("change", { bubbles: true }));
    }
    notice("Pen ready");
    refreshSettings();
  });

  document.body.addEventListener("insulinChanged", function (event) {
    var detail = event && event.detail ? event.detail : null;
    if (detail && detail.modal && window.dbCloseModal) window.dbCloseModal(detail.modal);
    refreshSettings();
  });
})();
