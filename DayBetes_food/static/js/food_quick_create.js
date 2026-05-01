(function () {
  var MENUS = [
    { buttonId: "food_quick_create_toggle", menuId: "food_quick_create_menu" },
    { buttonId: "food_power_toggle", menuId: "food_power_menu" }
  ];
  var menuOpenId = "";
  var hideTimer = null;

  function byId(id) {
    return document.getElementById(id);
  }

  function setBackgroundBlur(open) {
    var wrapper = byId("food_list_wrapper");
    var topBar = byId("food_top_bar");
    var cart = byId("cart_button");
    var blurValue = open ? "blur(1px)" : "";

    if (open) {
      if (wrapper) {
        wrapper.style.filter = blurValue;
        wrapper.style.transition = "filter 180ms ease";
        wrapper.style.pointerEvents = "none";
      }
      if (topBar) {
        var children = topBar.children || [];
        for (var i = 0; i < children.length; i += 1) {
          var child = children[i];
          if (child && child.getAttribute && child.getAttribute("data-quick-create-root") === "true") continue;
          if (child) {
            child.style.filter = blurValue;
            child.style.transition = "filter 180ms ease";
            child.style.pointerEvents = "none";
          }
        }
      }
      if (cart) {
        cart.style.filter = blurValue;
        cart.style.transition = "filter 180ms ease";
        cart.style.pointerEvents = "none";
      }
      return;
    }

    if (wrapper) {
      wrapper.style.filter = "";
      wrapper.style.transition = "";
      wrapper.style.pointerEvents = "";
    }
    if (topBar) {
      var topChildren = topBar.children || [];
      for (var j = 0; j < topChildren.length; j += 1) {
        var topChild = topChildren[j];
        if (topChild && topChild.getAttribute && topChild.getAttribute("data-quick-create-root") === "true") continue;
        if (topChild) {
          topChild.style.filter = "";
          topChild.style.transition = "";
          topChild.style.pointerEvents = "";
        }
      }
    }
    if (cart) {
      cart.style.filter = "";
      cart.style.transition = "";
      cart.style.pointerEvents = "";
    }
  }

  function hideOne(menu, btn) {
    if (hideTimer) {
      window.clearTimeout(hideTimer);
      hideTimer = null;
    }
    if (btn) btn.setAttribute("aria-expanded", "false");
    menu.dataset.open = "false";
    menu.style.opacity = "0";
    menu.style.transform = "translateY(-8px) scale(0.97)";
    menu.style.pointerEvents = "none";
    hideTimer = window.setTimeout(function () {
      if (menu.dataset.open !== "true") {
        menu.style.visibility = "hidden";
      }
    }, 180);
  }

  function closeAllMenus() {
    menuOpenId = "";
    for (var i = 0; i < MENUS.length; i += 1) {
      var btn = byId(MENUS[i].buttonId);
      var menu = byId(MENUS[i].menuId);
      if (!menu) continue;
      hideOne(menu, btn);
    }
    setBackgroundBlur(false);
  }

  function openMenu(menuId) {
    var cfg = null;
    for (var i = 0; i < MENUS.length; i += 1) {
      if (MENUS[i].menuId === menuId) { cfg = MENUS[i]; break; }
    }
    if (!cfg) return;
    var btn = byId(cfg.buttonId);
    var menu = byId(cfg.menuId);
    if (!btn || !menu) return;
    closeAllMenus();
    menuOpenId = cfg.menuId;
    btn.setAttribute("aria-expanded", "true");
    menu.dataset.open = "true";
    setBackgroundBlur(true);
    menu.style.visibility = "visible";
    menu.style.pointerEvents = "auto";
    window.requestAnimationFrame(function () {
      menu.style.opacity = "1";
      menu.style.transform = "translateY(0) scale(1)";
    });
  }

  function toggleMenu(menuId) {
    if (menuOpenId === menuId) {
      closeAllMenus();
      return;
    }
    openMenu(menuId);
  }

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target) return;

    for (var i = 0; i < MENUS.length; i += 1) {
      var btn = byId(MENUS[i].buttonId);
      var menu = byId(MENUS[i].menuId);
      if (!btn || !menu) continue;
      if (btn.contains(target)) {
        event.preventDefault();
        event.stopPropagation();
        toggleMenu(MENUS[i].menuId);
        return;
      }
      if (menu.contains(target)) return;
    }

    if (menuOpenId) closeAllMenus();
  }, true);

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && menuOpenId) {
      closeAllMenus();
    }
  });

  document.addEventListener("htmx:afterSwap", function () {
    closeAllMenus();
  });

  document.addEventListener("htmx:beforeRequest", function (event) {
    if (!menuOpenId) return;
    var menu = byId(menuOpenId);
    var elt = event && event.detail ? event.detail.elt : null;
    if (menu && elt && menu.contains(elt)) {
      closeAllMenus();
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    closeAllMenus();
  });
})();
