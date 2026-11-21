(function () {
  function routeToNavValue(path) {
    if (path.startsWith("/menu")) return "menu";
    if (path.startsWith("/stats")) return "stats";
    if (path.startsWith("/food")) return "food";
    if (path.startsWith("/settings")) return "settings";
    if (path.startsWith("/assistant")) return "assistant";
    return null;
  }

  // The island's height, for the glass cut to the pill plus DiaBot's circle
  // (input.css, .island_fill). Watched: fonts and labels change it after load.
  function syncIslandHeight() {
    var indicator = document.getElementById("island_active_indicator");
    var island = indicator ? indicator.parentElement : null;
    var wrapper = island ? island.parentElement : null;
    if (!wrapper) return;
    wrapper.style.setProperty("--island-h", island.offsetHeight + "px");
    // How far up from the bottom of the screen the island reaches, DiaBot's
    // circle included when it sticks out: what sits on it (the chat's composer) stands
    // flush on that, measured and not guessed.
    var rect = island.getBoundingClientRect();
    var bumpOn = parseFloat(getComputedStyle(wrapper).getPropertyValue("--bump-on")) || 0;
    var reach = window.innerHeight - (rect.top + rect.height / 2) + Math.max(bumpOn, rect.height) / 2;
    document.documentElement.style.setProperty("--island-reach", Math.ceil(reach) + "px");
  }

  // Writing the same place again, even a fraction of a pixel off (the island
  // resizes while DiaBot changes size), restarts the indicator's transition: the slide
  // then lands late, in two steps. Only a real change is written.
  var lastTarget = null;
  function place(indicator, width, height, x, y) {
    var t = lastTarget;
    if (t && Math.abs(t[0] - width) < 1 && Math.abs(t[1] - height) < 1 &&
        Math.abs(t[2] - x) < 1 && Math.abs(t[3] - y) < 1) return;
    lastTarget = [width, height, x, y];
    indicator.style.width = width + "px";
    indicator.style.height = height + "px";
    // left/top and not a transform: a transform runs on the compositor and the
    // size on the main thread, and on phones they drift apart, so the
    // indicator arrived in an arc. All four on one thread keep it straight.
    indicator.style.left = x + "px";
    indicator.style.top = y + "px";
    indicator.classList.remove("opacity-0");
    indicator.classList.add("opacity-100");
  }

  function moveIndicatorTo(item) {
    var indicator = document.getElementById("island_active_indicator");
    var island = indicator ? indicator.parentElement : null;
    if (!indicator || !island || !item) return;

    var islandRect = island.getBoundingClientRect();
    var itemRect = item.getBoundingClientRect();

    if (item.getAttribute("aria-label") === "DiaBot") {
      // DiaBot shrinks while the indicator slides to it: aim at its final size,
      // so both happen at once. The item keeps its rest size in the island
      // (only the circle changes), so its centre is the circle's.
      var wrapper = document.getElementById("floating_island");
      var size = parseFloat(getComputedStyle(wrapper).getPropertyValue("--bump-on")) || itemRect.width;
      var centerX = itemRect.left + itemRect.width / 2 - islandRect.left - island.clientLeft;
      var centerY = itemRect.top + itemRect.height / 2 - islandRect.top - island.clientTop;
      place(indicator, size, size, centerX - size / 2, centerY - size / 2);
      return;
    }

    // From the island's padding box, where the indicator is placed: without
    // its 1px border the indicator sat 1px off the item.
    place(
      indicator,
      itemRect.width,
      itemRect.height,
      itemRect.left - islandRect.left - island.clientLeft,
      itemRect.top - islandRect.top - island.clientTop
    );
  }

  function setCheckedByRoute() {
    var value = routeToNavValue(window.location.pathname);
    if (!value) return;
    var input = document.querySelector(
      "label[data-nav-item='" + value + "'] input[type='radio']"
    );
    if (input) input.checked = true;
  }

  function bind() {
    setCheckedByRoute();

    var items = document.querySelectorAll("label[data-nav-item]");
    items.forEach(function (item) {
      item.addEventListener("click", function () {
        moveIndicatorTo(item);
      });
    });

    function syncIndicator() {
      syncIslandHeight();
      var checkedInput = document.querySelector(
        "label[data-nav-item] input[type='radio']:checked"
      );
      var checkedItem = checkedInput ? checkedInput.closest("label[data-nav-item]") : null;
      if (checkedItem) moveIndicatorTo(checkedItem);
    }

    syncIndicator();
    window.setTimeout(syncIndicator, 120);

    var islandIndicator = document.getElementById("island_active_indicator");
    if (islandIndicator && window.ResizeObserver) {
      var observer = new ResizeObserver(function () {
        syncIndicator();
      });
      observer.observe(islandIndicator.parentElement);
    }

    window.addEventListener("resize", function () {
      window.requestAnimationFrame(syncIndicator);
      window.setTimeout(syncIndicator, 80);
    });

    window.addEventListener("orientationchange", function () {
      window.requestAnimationFrame(syncIndicator);
      window.setTimeout(syncIndicator, 140);
    });

    window.addEventListener("popstate", function () {
      setCheckedByRoute();
      syncIndicator();
    });

    document.body.addEventListener("htmx:afterSwap", function (event) {
      var target = event && event.detail ? event.detail.target : null;
      if (!target || target.id !== "main_content") return;
      setCheckedByRoute();
      syncIndicator();
      window.setTimeout(syncIndicator, 80);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
