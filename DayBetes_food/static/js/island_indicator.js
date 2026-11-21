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
  }

  function moveIndicatorTo(item) {
    var indicator = document.getElementById("island_active_indicator");
    var island = indicator ? indicator.parentElement : null;
    if (!indicator || !island || !item) return;

    var islandRect = island.getBoundingClientRect();
    var itemRect = item.getBoundingClientRect();

    indicator.style.width = itemRect.width + "px";
    indicator.style.height = itemRect.height + "px";
    // From the island's padding box, where the indicator is placed: without
    // its 1px border the indicator sat 1px off the item.
    indicator.style.transform =
      "translate(" +
      (itemRect.left - islandRect.left - island.clientLeft) +
      "px," +
      (itemRect.top - islandRect.top - island.clientTop) +
      "px)";
    indicator.classList.remove("opacity-0");
    indicator.classList.add("opacity-100");
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
      new ResizeObserver(function () {
        syncIndicator();
      }).observe(islandIndicator.parentElement);
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
