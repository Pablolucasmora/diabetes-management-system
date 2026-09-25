(function () {
  if (window.__dbSmartMacrosBootstrapped) {
    if (typeof window.dbSmartMacrosBindAll === "function") {
      window.dbSmartMacrosBindAll();
    }
    return;
  }
  window.__dbSmartMacrosBootstrapped = true;

  // Same grammar as parse_smart_macros in domain/nutrition.py: a sequence of
  // "<number> [unit] <macro name>" pairs; the number always goes first. Any
  // other text is an error, never a guess. The server is the authority; this
  // is only the preview.
  function normalizeText(text) {
    return String(text || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  var macroFamilies = [
    {
      field: "calories_100g",
      aliases: ["kcal", "kcals", "kca", "caloria", "calorias", "calorie", "calories", "cal", "cals", "energia", "ener", "ene"]
    },
    {
      field: "carbs_100g",
      aliases: ["hc", "ch", "hidrato", "hidratos", "hidrato de carbono", "hidratos de carbono", "carbo", "carbos", "carbohidrato", "carbohidratos", "carbohydrate", "carbohydrates", "carb", "carbs"]
    },
    {
      field: "sugars_100g",
      aliases: ["az", "azu", "azuc", "azuca", "azucar", "azucare", "azucares", "sugar", "sugars"]
    },
    {
      field: "proteins_100g",
      aliases: ["pr", "pro", "prot", "prote", "protein", "protei", "proteina", "proteinas", "proteins"]
    },
    {
      field: "fats_100g",
      aliases: ["gr", "gra", "gras", "grasa", "grasas", "fat", "fats", "lipido", "lipidos", "lipid", "lipids"]
    },
    {
      field: "saturated_100g",
      aliases: ["sat", "satu", "satur", "satura", "saturada", "saturadas", "grasa saturada", "grasas saturadas", "saturated", "saturated fat", "saturated fats", "st", "gs"]
    },
    {
      field: "fiber_100g",
      aliases: ["fb", "fib", "fibr", "fibra", "fibras", "fiber", "fibers", "fibre", "fibres"]
    }
  ];

  var macroAliases = {};
  for (var familyIndex = 0; familyIndex < macroFamilies.length; familyIndex += 1) {
    var familyAliases = macroFamilies[familyIndex].aliases;
    for (var aliasIndex = 0; aliasIndex < familyAliases.length; aliasIndex += 1) {
      macroAliases[familyAliases[aliasIndex]] = macroFamilies[familyIndex].field;
    }
  }
  var smartUnits = ["g", "gr", "gramos", "ml"];

  var prettyName = {
    calories_100g: "Kcal",
    carbs_100g: "Carbs",
    sugars_100g: "Sugars",
    proteins_100g: "Proteins",
    fats_100g: "Fats",
    saturated_100g: "Sat.",
    fiber_100g: "Fiber"
  };

  var pillColor = {
    calories_100g: "#111827",
    carbs_100g: "#3b82f6",
    sugars_100g: "#8b5cf6",
    proteins_100g: "#10b981",
    fats_100g: "#f59e0b",
    saturated_100g: "#ef4444",
    fiber_100g: "#6b7280"
  };
  // [0-9] and explicit whitespace, not \d/\s: they differ from Python.
  var regexSeparators = /[ \t\r\n,;+]*/y;
  var regexNumber = /[0-9]+(?:[.,][0-9]+)?/y;
  var regexName = /[ \t\r\n]*([a-z]+(?:[ \t\r\n]+[a-z]+)*)/y;

  function stickyMatch(regex, text, position) {
    regex.lastIndex = position;
    return regex.exec(text);
  }

  // Returns {values, error}. `error` is null or the same message the server
  // answers with a 422.
  function parseSmartMacros(text) {
    var values = {
      calories_100g: null,
      carbs_100g: null,
      sugars_100g: null,
      proteins_100g: null,
      fats_100g: null,
      saturated_100g: null,
      fiber_100g: null
    };
    var raw = normalizeText(text);
    var position = 0;
    while (true) {
      position += stickyMatch(regexSeparators, raw, position)[0].length;
      if (position >= raw.length) {
        return { values: values, error: null };
      }
      var number = stickyMatch(regexNumber, raw, position);
      if (!number) {
        return {
          values: values,
          error: "Write each value as a number followed by its macro, e.g. '30 carbs 20 proteins'."
        };
      }
      position += number[0].length;
      var name = stickyMatch(regexName, raw, position);
      if (!name) {
        return { values: values, error: "Add the macro name after " + number[0] + "." };
      }
      var words = name[1].split(/[ \t\r\n]+/);
      if (words.length > 1 && smartUnits.indexOf(words[0]) !== -1) {
        words = words.slice(1);
      }
      var label = words.join(" ");
      var field = Object.prototype.hasOwnProperty.call(macroAliases, label) ? macroAliases[label] : null;
      if (!field) {
        return { values: values, error: "Unknown macro '" + label + "'." };
      }
      if (values[field] !== null) {
        return { values: values, error: "Macro '" + label + "' is written more than once." };
      }
      values[field] = Number(number[0].replace(",", "."));
      position += name[0].length;
    }
  }
  window.dbSmartMacrosParse = parseSmartMacros;

  function renderPreview(outputEl, parsed) {
    if (!outputEl) return;
    if (parsed.error) {
      outputEl.textContent = parsed.error;
      return;
    }
    var values = parsed.values;
    var chips = [];
    var keys = Object.keys(values);
    for (var i = 0; i < keys.length; i += 1) {
      var key = keys[i];
      // value !== null paints an explicit 0 as well (measurement §2).
      if (values[key] !== null && values[key] !== undefined) {
        chips.push(
          '<span style="display:inline-block;padding:2px 8px;border-radius:999px;color:#fff;font-size:11px;margin:2px 4px 2px 0;background:' +
            pillColor[key] +
            ';">' +
            prettyName[key] +
            ": " +
            values[key] +
            "</span>"
        );
      }
    }

    if (!chips.length) {
      outputEl.textContent = "Type macros to preview what is detected.";
      return;
    }
    outputEl.innerHTML = '<span style="font-size:11px;color:#4b5563;">Detected: </span>' + chips.join("");
  }

  function syncInput(input) {
    if (!input) return;
    var prefix = input.dataset ? input.dataset.smartMacrosPrefix : null;
    if (!prefix && input.id && input.id.indexOf("_smart_macros_input") > 0) {
      prefix = input.id.replace("_smart_macros_input", "");
    }

    var outputSelector = input.dataset ? input.dataset.smartMacrosOutput : null;
    var outputEl = outputSelector ? document.querySelector(outputSelector) : null;
    if (!outputEl && prefix) {
      outputEl = document.getElementById(prefix + "_smart_macros_output");
    }
    if (!outputEl && input.nextElementSibling) {
      outputEl = input.nextElementSibling;
    }

    var parsed = parseSmartMacros(input.value || "");
    renderPreview(outputEl, parsed);
  }

  function bindOne(input) {
    if (!input || input.dataset.smartMacrosBound === "1") return;
    input.dataset.smartMacrosBound = "1";

    function sync() {
      syncInput(input);
    }

    input.addEventListener("input", sync);
    input.addEventListener("change", sync);
    sync();
  }

  function bindAll() {
    var nodes = document.querySelectorAll("[data-smart-macros='true'], [id$='_smart_macros_input']");
    for (var i = 0; i < nodes.length; i += 1) {
      bindOne(nodes[i]);
    }
  }
  window.dbSmartMacrosBindAll = bindAll;

  window.dbSmartMacrosSync = function (inputOrId) {
    if (!inputOrId) return;
    var input = inputOrId;
    if (typeof inputOrId === "string") {
      input = document.getElementById(inputOrId);
    }
    syncInput(input);
  };

  window.dbSmartMacrosSelfCheck = async function () {
    var response = await fetch("/data/smart_macros_cases.json", { cache: "no-store" });
    var cases = await response.json();
    var mismatches = [];
    for (var i = 0; i < cases.length; i += 1) {
      var parsed = parseSmartMacros(cases[i].text || "");
      var expectedError = cases[i].error || null;
      if (expectedError !== parsed.error) {
        mismatches.push({ case: i, text: cases[i].text, field: "error", expected: expectedError, got: parsed.error });
      }
      if (expectedError) continue;
      var expected = cases[i].expected || {};
      var keys = Object.keys(parsed.values);
      for (var j = 0; j < keys.length; j += 1) {
        var key = keys[j];
        var expectedValue = key in expected ? expected[key] : null;
        if (expectedValue !== parsed.values[key]) {
          mismatches.push({
            case: i,
            text: cases[i].text,
            field: key,
            expected: expectedValue,
            got: parsed.values[key]
          });
        }
      }
    }
    if (mismatches.length) {
      console.table(mismatches);
    } else {
      console.log("smart macros OK", cases.length);
    }
    return mismatches;
  };

  function attachSwapListener() {
    if (!document.body) return;
    document.body.addEventListener("htmx:afterSwap", bindAll);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      bindAll();
      attachSwapListener();
    });
  } else {
    bindAll();
    attachSwapListener();
  }
})();
