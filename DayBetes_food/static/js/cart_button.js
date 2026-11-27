// The floating cart button (#cart_button) is hidden on every page whose content
// carries data-hide-cart="true" (frontend_conventions.md §14): checked on each
// new page, whatever opened it (the island, a link, Back, a swipe, a reload).
(function () {
  if (window.__dbCartButton) return;
  window.__dbCartButton = true;

  function setVisible(cart, visible) {
    if (cart.__hideTimer) {
      window.clearTimeout(cart.__hideTimer);
      cart.__hideTimer = null;
    }
    if (visible) {
      cart.style.visibility = "";
      cart.style.opacity = "";
      cart.style.pointerEvents = "";
      cart.classList.remove("invisible", "opacity-0", "pointer-events-none");
      cart.classList.add("opacity-100");
      return;
    }
    cart.style.visibility = "";
    cart.classList.remove("opacity-100");
    cart.classList.add("opacity-0", "pointer-events-none");
    cart.__hideTimer = window.setTimeout(function () {
      cart.classList.add("invisible");
      cart.__hideTimer = null;
    }, 110);
  }

  function sync() {
    var cart = document.getElementById("cart_button");
    if (!cart) return;
    var main = document.getElementById("main_content");
    var hide = !!(main && main.querySelector("[data-hide-cart='true']"));
    setVisible(cart, !hide);
  }

  window.dbSyncCartButton = sync;

  function bind() {
    sync();
    document.body.addEventListener("htmx:afterSwap", sync);
    document.body.addEventListener("htmx:historyRestore", sync);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
