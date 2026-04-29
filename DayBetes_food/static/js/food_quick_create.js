(function () {
  var BUTTON_ID = "food_quick_create_toggle";
  var MENU_ID = "food_quick_create_menu";
  var menuOpen = false;
  var hideTimer = null;

  function byId(id) {
    return document.getElementById(id);
  }

  function syncFoodSpacingWithMenu(open) {
    var topBar = byId("food_top_bar");
    var wrapper = byId("food_list_wrapper");
    var menu = byId(MENU_ID);
    if (!topBar || !wrapper || !menu) return;

    if (!open) {
      wrapper.style.removeProperty("padding-top");
      return;
    }

    var topRect = topBar.getBoundingClientRect();
    var menuHeight = menu.scrollHeight || menu.getBoundingClientRect().height || 0;
    var safeGap = 12;
    var requiredTop = Math.max(180, Math.ceil(topRect.bottom + menuHeight + safeGap));
    wrapper.style.paddingTop = requiredTop + "px";
  }

  function syncState(open) {
    var btn = byId(BUTTON_ID);
    var menu = byId(MENU_ID);
    if (!btn || !menu) return;

    if (hideTimer) {
      window.clearTimeout(hideTimer);
      hideTimer = null;
    }

    menuOpen = open;
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    menu.dataset.open = open ? "true" : "false";

    if (open) {
      menu.style.visibility = "visible";
      menu.style.pointerEvents = "auto";
      syncFoodSpacingWithMenu(true);
      window.requestAnimationFrame(function () {
        menu.style.opacity = "1";
        menu.style.transform = "translateY(0) scale(1)";
        // Re-sync after paint to capture final menu height.
        syncFoodSpacingWithMenu(true);
      });
      return;
    }

    menu.style.opacity = "0";
    menu.style.transform = "translateY(-8px) scale(0.97)";
    menu.style.pointerEvents = "none";
    hideTimer = window.setTimeout(function () {
      if (menu.dataset.open !== "true") {
        menu.style.visibility = "hidden";
      }
    }, 180);
    syncFoodSpacingWithMenu(false);
  }

  function toggleMenu() {
    syncState(!menuOpen);
  }

  function closeMenu() {
    syncState(false);
  }

  document.addEventListener("click", function (event) {
    var btn = byId(BUTTON_ID);
    var menu = byId(MENU_ID);
    if (!btn || !menu) return;

    var target = event.target;
    if (!target) return;

    if (btn.contains(target)) {
      event.preventDefault();
      event.stopPropagation();
      toggleMenu();
      return;
    }

    if (menu.contains(target)) {
      return;
    }

    if (menuOpen) closeMenu();
  }, true);

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && menuOpen) {
      closeMenu();
    }
  });

  document.addEventListener("htmx:afterSwap", function () {
    closeMenu();
  });

  document.addEventListener("DOMContentLoaded", function () {
    closeMenu();
  });
})();
