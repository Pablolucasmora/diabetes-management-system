// Opens and closes the pop-ups built with components/modal.py. Each one is a
// <dialog> shown with showModal(), so the browser paints it above the whole
// page; `id` names the dimmed layer inside it (frontend_conventions.md §8).
(function () {
  window.dbOpenModal = function (id) {
    var layer = document.getElementById(id);
    if (!layer) return;
    var dialog = layer.closest("dialog");
    if (dialog && !dialog.open) dialog.showModal();
    window.requestAnimationFrame(function () {
      layer.classList.remove("opacity-0");
      layer.classList.add("opacity-100");
    });
  };

  window.dbCloseModal = function (id) {
    var layer = document.getElementById(id);
    if (!layer) return;
    layer.classList.remove("opacity-100");
    layer.classList.add("opacity-0");
    var dialog = layer.closest("dialog");
    // The dialog closes once the fade-out ends, unless it was reopened.
    window.setTimeout(function () {
      if (dialog && dialog.open && layer.classList.contains("opacity-0")) dialog.close();
    }, 200);
  };
})();
