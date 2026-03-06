import json
from fasthtml.common import *

from DayBetes_food.database.queries.crud import get_cart_events
from DayBetes_food.components.cart.cart_shared import CHECKBOX_CLS


CATEGORY_OPTIONS = [
    "meat",
    "fish",
    "dairy",
    "eggs",
    "processed_meat",
    "legumes",
    "tubers",
    "nuts",
    "vegetables",
    "fruits",
    "cereals",
    "oils_and_fats",
    "sweets",
    "beverages",
    "sauces",
    "condiments",
    "supplements",
]

MEAL_TYPES = ["breakfast", "brunch", "lunch", "afternoon_snack", "dinner", "snack", "rescue"]

GLYCEMIC_INDEX_OPTIONS = ["high", "medium", "low"]

INITIAL_STATE_OPTIONS = ["solid", "mashed/creamy", "liquid", "gel"]

FILTER_ITEM_CLS = """
    px-3 py-1.5
    w-full
    text-[11px] md:text-xs
    rounded-full
    transition-all duration-200
    cursor-pointer
    border border-white/80
    shadow-sm
"""


def _help_icon(help_text: str):
    return Button(
        "?",
        type="button",
        title=help_text,
        onclick=f"alert({help_text!r});",
        cls="""
            web_button rounded-full
            h-4 w-4 md:h-5 md:w-5
            text-[10px] md:text-xs
            p-0 leading-none
            flex items-center justify-center
            shadow-none
        """,
    )


def _label_with_help(text: str, help_text: str):
    return Div(
        Label(text, cls="text-xs text-gray-700"),
        _help_icon(help_text),
        cls="flex items-center gap-1",
    )


def on_after(target="this", reload_page=True):
    reload_snippet = "setTimeout(function() { location.reload(); }, 600);" if reload_page else ""
    return {"hx-on:htmx:after-request": f"""
    var btn = {target if target == "this" else f"document.getElementById('{target}')"};
    if(!btn) return;
    if(event.detail.successful) {{
        btn.style.backgroundColor = 'rgb(74, 222, 128)';
    }} else {{
        btn.style.backgroundColor = 'rgb(248, 113, 113)';
    }}
    setTimeout(function() {{ btn.style.backgroundColor = ''; }}, 300);
    {reload_snippet}
"""}


def MealSelector(connection, user_id: int, selected_id: int = None):
    events = get_cart_events(connection, user_id)

    options = [
        Option(
            event["name"] or f"Meal {event['meal_time'].strftime('%H:%M')}",
            value=str(event["id"]),
            selected=(event["id"] == selected_id),
        )
        for event in events
    ]

    if not options:
        options = [Option("- No meals yet -", value="", cls="text-gray-500/50")]

    options.append(Option("New Meal", value="0", selected=(selected_id == 0)))

    return Div(
        Label("Meal selector", cls="text-xs text-gray-600", **{"for": "meal_selector"}),
        Select(
            *options,
            id="meal_selector",
            name="intake_event_id",
            data_skip_page_loading="true",
            aria_label="Meal selector",
            hx_get="/meal_selector_input",
            hx_target="#meal_name_input",
            hx_trigger="change",
            hx_include="this",
            style="color: gray" if not events else "",
            cls="""
            border-[1px] px-2 py-1
            md:text-sm lg:text-sm text-xs
            shadow-sm rounded-md focus:outline-none
            lg:w-40 md:w-40 w-32
            border-white cursor-pointer
            """,
        ),
        Div(id="meal_name_input", cls="lg:w-40 md:w-40 w-32 bg-transparent"),
        cls="flex items-center justify-center gap-2  md:w-md lg:w-md w-xs mb-3",
    )


def Filters():
    filters = [("All", "all"), ("Food", "food"), ("Recipes", "recipes"), ("Favs", "favs")]
    buttons = []
    for text, value in filters:
        buttons.append(
            Button(
                text,
                cls=f"{FILTER_ITEM_CLS} {'bg-black text-white shadow-md' if value == 'all' else 'bg-transparent text-gray-700'}",
                data_food_filter_btn="true",
                data_filter_value=value,
                data_skip_page_loading="true",
                hx_get="/food/list",
                hx_target="#food-list",
                hx_swap="innerHTML",
                hx_include="#food_search_input, #food_filter",
                **{
                    "hx-on:click": (
                        f"document.getElementById('food_filter').value='{value}';"
                        "var active='bg-black text-white shadow-md';"
                        "var inactive='bg-transparent text-gray-700';"
                        "document.querySelectorAll('[data-food-filter-btn]').forEach(function(btn){"
                        "btn.classList.remove('bg-black','text-white','shadow-md');"
                        "btn.classList.add('bg-transparent','text-gray-700');"
                        "});"
                        "this.classList.remove('bg-transparent','text-gray-700');"
                        "this.classList.add('bg-black','text-white','shadow-md');"
                    ),
                },
            )
        )

    return Div(
        Input(type="hidden", id="food_filter", name="filter", value="all"),
        Div(
            *buttons,
            cls="""
                relative
                flex items-center justify-between
                gap-3
                w-full
                rounded-full
            """,
        ),
        cls="md:w-md lg:w-md w-xs transition-all",
    )


def SearchInput():
    return Input(
        inputmode="text",
        placeholder="What did you eat?",
        name="search",
        id="food_search_input",
        data_skip_page_loading="true",
        cls="""
            web_input
            border-[0.6px] border-white inset-shadow-none
            rounded-2xl
            bg-gray-200/50
            md:w-md lg:w-md
            w-xs
            transition-all
            p-4
        """,
        hx_get="/food/list",
        hx_target="#food-list",
        hx_trigger="keyup changed delay:300ms",
        hx_include="#food_filter",
        hx_swap="innerHTML",
    )


def _labeled_input(
    label: str,
    name: str,
    typ: str = "text",
    placeholder: str = "",
    help_text: str = "",
    step: str = "",
    value: str | None = None,
):
    help_value = help_text or f"What to enter in {label}"
    return Div(
        _label_with_help(label, help_value),
        Input(
            type=typ,
            name=name,
            placeholder=placeholder,
            cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-base mr-1",
            onclick="this.select()",
            **({"step": step} if step else {}),
            **({"value": value} if value is not None else {}),
        ),
        cls="flex flex-col gap-1",
    )


def _searchable_autocomplete_input(
    label: str,
    name: str,
    options: list[str] | None = None,
    help_text: str = "",
    placeholder: str = "",
    allow_add: bool = True,
    value: str | None = None,
):
    normalized_options = sorted({(opt or "").strip() for opt in (options or []) if (opt or "").strip()})
    options_json = json.dumps(normalized_options)
    placeholder_value = placeholder or f"Type {label.lower()}"
    help_value = help_text or f"Search and select {label.lower()}."
    return Div(
        _label_with_help(label, help_value),
        Div(
            Input(
                type="text",
                name=name,
                data_searchable_input="true",
                placeholder=placeholder_value,
                autocomplete="off",
                cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-base mr-1",
                onclick="this.select()",
                **({"value": value} if value is not None else {}),
            ),
            Div(
                data_searchable_suggestions="true",
                cls="""
                    absolute left-0 right-0 top-full mt-1 z-[70]
                    rounded-md border border-gray-200
                    bg-white opacity-100 shadow-lg
                    overflow-hidden
                """,
                style="display:none;background:#fff;backdrop-filter:none;z-index:70;",
            ),
            data_searchable_autocomplete="true",
            data_searchable_options=options_json,
            data_searchable_allow_add="1" if allow_add else "0",
            cls="relative",
        ),
        cls="flex flex-col gap-1",
    )


def _brand_autocomplete_input(brand_options: list[str] | None = None, value: str | None = None):
    return _searchable_autocomplete_input(
        label="Brand",
        name="brand",
        options=brand_options,
        help_text="Brand or manufacturer name.",
        placeholder="Type brand",
        allow_add=True,
        value=value,
    )


def _searchable_autocomplete_bootstrap_script():
    return Script(
        """
        (function () {
          if (window.__dbSearchableAutocompleteBootstrapped) return;
          window.__dbSearchableAutocompleteBootstrapped = true;

          function normalize(v) { return String(v || "").trim(); }
          function escapeHtml(v) {
            return String(v || "")
              .replace(/&/g, "&amp;")
              .replace(/</g, "&lt;")
              .replace(/>/g, "&gt;")
              .replace(/"/g, "&quot;")
              .replace(/'/g, "&#39;");
          }

          function bindOne(root) {
            if (!root || root.dataset.searchableBound === "1") return;
            root.dataset.searchableBound = "1";

            var input = root.querySelector("[data-searchable-input='true']");
            var box = root.querySelector("[data-searchable-suggestions='true']");
            if (!input || !box) return;

            var options = [];
            try { options = JSON.parse(root.dataset.searchableOptions || "[]"); }
            catch (_) { options = []; }
            var allowAdd = root.dataset.searchableAllowAdd === "1";

            function closeBox() {
              box.style.display = "none";
              box.innerHTML = "";
              root.style.zIndex = "";
            }

            function similarityScore(nameLower, qLower) {
              if (!qLower) return 0;
              if (nameLower === qLower) return 1000;
              if (nameLower.indexOf(qLower) === 0) return 800;
              if (nameLower.indexOf(qLower) !== -1) return 600;

              var qSet = new Set(qLower.split(""));
              var nSet = new Set(nameLower.split(""));
              var inter = 0;
              qSet.forEach(function (ch) { if (nSet.has(ch)) inter += 1; });
              var union = new Set([].concat(Array.from(qSet), Array.from(nSet))).size || 1;
              return Math.floor((inter / union) * 300);
            }

            function render() {
              var q = normalize(input.value);
              var qLower = q.toLowerCase();
              var matches = [];

              for (var i = 0; i < options.length; i += 1) {
                var name = normalize(options[i]);
                if (!name) continue;
                var lower = name.toLowerCase();
                var score = similarityScore(lower, qLower);
                if (!q || score > 0) matches.push({ name: name, score: score });
              }

              matches.sort(function (a, b) {
                if (b.score !== a.score) return b.score - a.score;
                return a.name.localeCompare(b.name);
              });

              var rows = [];
              for (var j = 0; j < matches.length; j += 1) {
                var label = matches[j].name;
                var safe = escapeHtml(label);
                rows.push(
                  "<li class='border-b border-gray-200'>" +
                  "<button type='button' data-searchable-pick='" +
                  safe +
                  "' class='w-full text-left px-3 py-2 bg-white hover:bg-gray-200 text-sm text-gray-800 transition-colors'>" +
                  safe +
                  "</button></li>"
                );
              }

              var exactExists = options.some(function (x) {
                return normalize(x).toLowerCase() === qLower;
              });

              if (allowAdd && q && !exactExists) {
                rows.push(
                  "<li class='border-b border-gray-200'>" +
                  "<button type='button' data-searchable-add='true' class='w-full text-left px-3 py-2 bg-white hover:bg-gray-200 text-sm font-semibold text-gray-800 transition-colors'>Add: '" +
                  escapeHtml(q) +
                  "'</button></li>"
                );
              }

              if (rows.length) {
                box.innerHTML = (
                  "<div data-searchable-scroll='true' class='p-0 max-h-44 overflow-y-auto' " +
                  "style='-webkit-overflow-scrolling:touch;overscroll-behavior:contain;touch-action:pan-y;'>" +
                  "<ul>" + rows.join("") + "</ul></div>"
                );
                var items = box.querySelectorAll("li");
                if (items.length > 0) items[items.length - 1].classList.remove("border-b", "border-gray-200");
                var scrollArea = box.querySelector("[data-searchable-scroll='true']");
                if (scrollArea) {
                  scrollArea.addEventListener("wheel", function (ev) { ev.stopPropagation(); }, { passive: true });
                  scrollArea.addEventListener("touchmove", function (ev) { ev.stopPropagation(); }, { passive: true });
                }
                root.style.zIndex = "80";
              } else {
                box.innerHTML = "";
                root.style.zIndex = "";
              }
              box.style.display = rows.length ? "block" : "none";
            }

            box.addEventListener("click", function (ev) {
              var target = ev.target;
              if (!target) return;
              if (target.dataset && target.dataset.searchableAdd === "true") {
                var q = normalize(input.value);
                if (!q) return;
                var exists = options.some(function (x) { return normalize(x).toLowerCase() === q.toLowerCase(); });
                if (!exists) options.push(q);
                input.value = q;
                closeBox();
                return;
              }
              var pick = target.dataset ? target.dataset.searchablePick : "";
              if (pick) {
                input.value = pick;
                closeBox();
              }
            });

            input.addEventListener("focus", render);
            input.addEventListener("input", render);
            input.addEventListener("keydown", function (ev) {
              if (ev.key === "Escape") closeBox();
            });
            document.addEventListener("click", function (ev) {
              var target = ev.target;
              if (!root.contains(target)) {
                closeBox();
                return;
              }
              if (target !== input && !box.contains(target)) {
                closeBox();
              }
            });
          }

          function bindAll() {
            var roots = document.querySelectorAll("[data-searchable-autocomplete='true']");
            for (var i = 0; i < roots.length; i += 1) bindOne(roots[i]);
          }

          if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", bindAll);
          } else {
            bindAll();
          }
          document.body.addEventListener("htmx:afterSwap", bindAll);
        })();
        """
    )


def _labeled_select(label: str, name: str, options: list[str], help_text: str = "", selected_value: str = ""):
    help_value = help_text or f"What to select in {label}"
    return Div(
        _label_with_help(label, help_value),
        Select(
            Option("-", value="", selected=(selected_value == "")),
            *[Option(opt, value=opt, selected=(opt == selected_value)) for opt in options],
            name=name,
            cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-xs mr-1",
        ),
        cls="flex flex-col gap-1",
    )


def _favorite_checkbox(name: str = "favorite", checked: bool = True, centered: bool = False):
    return Div(
        Label(
            Input(
                type="checkbox",
                name=name,
                value="true",
                checked=checked,
                cls=CHECKBOX_CLS,
            ),
            Span(
                Svg(
                    Path(
                        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z",
                        fill_rule="evenodd",
                        clip_rule="evenodd",
                    ),
                    xmlns="http://www.w3.org/2000/svg",
                    cls="h-3.5 w-3.5",
                    viewBox="0 0 20 20",
                    fill="currentColor",
                    stroke="currentColor",
                    stroke_width="1",
                ),
                cls="""
                    absolute text-white opacity-0 peer-checked:opacity-100
                    top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2
                    pointer-events-none
                """,
            ),
            cls="flex items-center cursor-pointer relative h-5 w-5",
        ),
        Span("Favorite", cls="text-xs text-gray-700"),
        _help_icon("Mark as favorite so it appears highlighted and in Favs filter."),
        cls=(
            "flex items-center justify-center gap-2 col-span-1 md:col-span-2"
            if centered
            else "flex items-center justify-end gap-2 col-span-1 md:col-span-2"
        ),
    )


def _smart_macros_block(prefix: str):
    input_id = f"{prefix}_smart_macros_input"
    output_id = f"{prefix}_smart_macros_output"
    return Div(
        _label_with_help(
            "Smart macros (per 100g/ml)",
            (
                "Write macros in free text. Examples: '120kcal 30hc 12az 20prot 10 grasas 3 sat 5 fibra', "
                "'carbs 30g proteins 20g'. Synonyms accepted: hc/ch/hidratos/carbos, "
                "prote/prot/proteina, grasas/gr/grasa, sat/saturadas/st/gs, fibra/fb, az/azucar, kcal/cal."
            ),
        ),
        Input(
            type="text",
            id=input_id,
            placeholder="Ej: 120kcal, 30hc, 12az, 20prot, 10 grasas, 3 sat, 5 fibra",
            data_smart_macros="true",
            data_smart_macros_output=f"#{output_id}",
            data_smart_macros_prefix=prefix,
            oninput="dbSmartMacrosSync(this)",
            onchange="dbSmartMacrosSync(this)",
            cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-base",
        ),
        Div("Escribe macros para ver la deteccion.", id=output_id, cls="text-xs text-gray-700 min-h-5"),
        # Hidden fields populated by Smart Macros parser
        Input(type="hidden", name="calories_100g", id=f"{prefix}_calories_100g", value="0"),
        Input(type="hidden", name="carbs_100g", id=f"{prefix}_carbs_100g", value="0"),
        Input(type="hidden", name="sugars_100g", id=f"{prefix}_sugars_100g", value="0"),
        Input(type="hidden", name="proteins_100g", id=f"{prefix}_proteins_100g", value="0"),
        Input(type="hidden", name="fats_100g", id=f"{prefix}_fats_100g", value="0"),
        Input(type="hidden", name="saturated_100g", id=f"{prefix}_saturated_100g", value="0"),
        Input(type="hidden", name="fiber_100g", id=f"{prefix}_fiber_100g", value="0"),
        cls="flex flex-col gap-1 col-span-1 md:col-span-2",
    )


def _advanced_toggle(section_id: str):
    return Div(
        Button(
            "Advanced",
            type="button",
            cls="web_button px-2 py-1 text-xs w-fit",
            onclick=(
                f"const el=document.getElementById('{section_id}');"
                "if(!el) return;"
                "el.classList.toggle('hidden');"
            ),
        ),
        cls="col-span-1 md:col-span-2",
    )


def QuickCreateButtons():
    return Div(
        Button(
            "Add catalog",
            type="button",
            cls="web_button px-2 py-1 text-[10px] md:text-xs w-full",
            hx_get="/food/create/catalog/form",
            hx_target="#main_content",
            hx_swap="innerHTML",
            hx_push_url="true",
        ),
        Button(
            "Add manual",
            type="button",
            cls="web_button px-2 py-1 text-[10px] md:text-xs w-full",
            hx_get="/food/create/manual/form",
            hx_target="#main_content",
            hx_swap="innerHTML",
            hx_push_url="true",
        ),
        Button(
            "Add recipe",
            type="button",
            cls="web_button px-2 py-1 text-[10px] md:text-xs w-full",
            hx_get="/food/create/recipe/form",
            hx_target="#main_content",
            hx_swap="innerHTML",
            hx_push_url="true",
        ),
        cls="flex items-center justify-between gap-2 md:w-md lg:w-md w-xs",
    )


def CreateCatalogPanel(brand_options: list[str] | None = None, subtype_options: list[str] | None = None):
    return Div(
        Form(
            Div(
                _labeled_input("Name*", "name"),
                _brand_autocomplete_input(brand_options=brand_options),
                _searchable_autocomplete_input("Category*", "category", CATEGORY_OPTIONS, allow_add=True),
                _searchable_autocomplete_input("Subtype*", "subtype", subtype_options or [], allow_add=True),
                _searchable_autocomplete_input("Initial state", "initial_state", INITIAL_STATE_OPTIONS, allow_add=False),
                _searchable_autocomplete_input("Nutriscore", "nutriscore", ["A", "B", "C", "D", "E"], allow_add=False),
                _labeled_input("NOVA (1-4)", "nova", "number"),
                _labeled_input("Yuka (0-100)", "yuka", "number"),
                _labeled_input("Default portion", "default_portion", "number", step="any"),
                _labeled_input("Calories/100g", "calories_100g", "number"),
                _labeled_input("Carbs/100g", "carbs_100g", "number"),
                _labeled_input("Sugars/100g", "sugars_100g", "number"),
                _labeled_input("Fats/100g", "fats_100g", "number"),
                _labeled_input("Saturated/100g", "saturated_100g", "number"),
                _labeled_input("Proteins/100g", "proteins_100g", "number"),
                _labeled_input("Fiber/100g", "fiber_100g", "number"),
                _labeled_input("Caffeine", "caffeine", "number"),
                _labeled_input("Alcohol", "alcohol", "number"),
                _labeled_input("Barcode", "barcode"),
                _labeled_input("Cooking factor", "cooking_factor", "number"),
                _favorite_checkbox(),
                cls="grid grid-cols-2 gap-2",
            ),
            Button(
                "Create catalog item",
                type="submit",
                cls="web_button px-3 py-2 text-xs",
            ),
            hx_post="/food/create/catalog",
            hx_target="#create_catalog_result",
            hx_swap="innerHTML",
            cls="web_container p-3 rounded-2xl flex flex-col gap-3",
        ),
        Div(id="create_catalog_result", cls="text-xs"),
        id="create_catalog_panel",
        cls="hidden md:w-md lg:w-md w-xs flex flex-col gap-2",
    )


def CreateManualPanel(subtype_options: list[str] | None = None, origin_options: list[str] | None = None):
    return Div(
        Form(
            Div(
                _labeled_input("Name*", "name"),
                _labeled_input("Description", "description"),
                _searchable_autocomplete_input("Subtype*", "subtype", subtype_options or [], allow_add=True),
                _searchable_autocomplete_input("Origin", "source_origin", origin_options or [], allow_add=True),
                _labeled_input("Amount g*", "amount_g", "number"),
                _labeled_input("Calories/100g", "calories_100g", "number"),
                _labeled_input("Carbs/100g", "carbs_100g", "number"),
                _labeled_input("Sugars/100g", "sugars_100g", "number"),
                _labeled_input("Fats/100g", "fats_100g", "number"),
                _labeled_input("Saturated/100g", "saturated_100g", "number"),
                _labeled_input("Proteins/100g", "proteins_100g", "number"),
                _labeled_input("Fiber/100g", "fiber_100g", "number"),
                _labeled_input("Caffeine", "caffeine", "number"),
                _labeled_input("Alcohol", "alcohol", "number"),
                _searchable_autocomplete_input("Glycemic index", "glycemic_index", GLYCEMIC_INDEX_OPTIONS, help_text="Estimated glycemic index level."),
                _labeled_input("IG confidence 1-5", "ig_confidence", "number"),
                _favorite_checkbox(),
                cls="grid grid-cols-2 gap-2",
            ),
            Button(
                "Create manual intake",
                type="submit",
                cls="web_button px-3 py-2 text-xs",
            ),
            hx_post="/food/create/manual",
            hx_target="#create_manual_result",
            hx_swap="innerHTML",
            cls="web_container p-3 rounded-2xl flex flex-col gap-3",
        ),
        Div(id="create_manual_result", cls="text-xs"),
        id="create_manual_panel",
        cls="hidden md:w-md lg:w-md w-xs flex flex-col gap-2",
    )


def CreateRecipePanel():
    return Div(
        Form(
            Div(
                _labeled_input("Name*", "name"),
                _labeled_select("Meal type", "meal_type", MEAL_TYPES),
                Div(
                    Label("Notes", cls="text-xs text-gray-700"),
                    Textarea(
                        "",
                        name="notes",
                        rows="3",
                        cls="web_input border border-white rounded-lg px-2 py-1 text-xs",
                    ),
                    cls="flex flex-col gap-1 col-span-2",
                ),
                _favorite_checkbox(),
                cls="grid grid-cols-2 gap-2",
            ),
            Button(
                "Create recipe",
                type="submit",
                cls="web_button px-3 py-2 text-xs",
            ),
            hx_post="/food/create/recipe",
            hx_target="#create_recipe_result",
            hx_swap="innerHTML",
            cls="web_container p-3 rounded-2xl flex flex-col gap-3",
        ),
        Div(id="create_recipe_result", cls="text-xs"),
        id="create_recipe_panel",
        cls="hidden md:w-md lg:w-md w-xs flex flex-col gap-2",
    )


def _create_page_shell(title: str, form, result_id: str):
    return Div(
        Div(
            H1(title, cls="text-xl font-bold"),
            cls="flex items-center justify-center gap-3 w-full",
        ),
        Div(form, cls="w-full"),
        Div(id=result_id, cls="text-xs w-full"),
        _searchable_autocomplete_bootstrap_script(),
        Script(src="/js/smart_macros.js", defer="defer"),
        data_hide_cart="true",
        cls="""
            flex flex-col items-center
            gap-4
            md:mt-7 lg:mt-7 mt-2
            md:w-md lg:w-md w-xs
            w-full mx-auto
            md:mb-28 lg:mb-28 mb-24
        """,
    )


def CreateCatalogPage(brand_options: list[str] | None = None, subtype_options: list[str] | None = None):
    result_id = "create_catalog_result_page"
    form = Form(
        Div(
            _labeled_input("Name*", "name", help_text="Product name. Required."),
            _brand_autocomplete_input(brand_options=brand_options),
            _searchable_autocomplete_input(
                "Category*",
                "category",
                CATEGORY_OPTIONS,
                help_text="Main category. Required.",
                allow_add=True,
            ),
            _searchable_autocomplete_input(
                "Subtype*",
                "subtype",
                subtype_options or [],
                help_text="Specific subtype, e.g. yogurt, pasta, soda. Required.",
                allow_add=True,
            ),
            _smart_macros_block("catalog"),
            _labeled_input("Default portion", "default_portion", "number", help_text="Default serving size in g/ml.", step="any"),
            _favorite_checkbox(),
            _advanced_toggle("catalog_advanced"),
            Div(
                _searchable_autocomplete_input(
                    "Initial state",
                    "initial_state",
                    INITIAL_STATE_OPTIONS,
                    help_text="Physical state before preparation.",
                    allow_add=False,
                ),
                _searchable_autocomplete_input(
                    "Nutriscore",
                    "nutriscore",
                    ["A", "B", "C", "D", "E"],
                    help_text="Nutrition quality score from A to E.",
                    allow_add=False,
                ),
                _labeled_input("NOVA (1-4)", "nova", "number", help_text="Food processing level from 1 to 4."),
                _labeled_input("Yuka (0-100)", "yuka", "number", help_text="Optional Yuka-style score from 0 to 100."),
                _labeled_input("Caffeine", "caffeine", "number", help_text="Caffeine content in mg per 100g/ml."),
                _labeled_input("Alcohol", "alcohol", "number", help_text="Alcohol content in grams per 100g/ml."),
                _labeled_input("Barcode", "barcode", help_text="Optional product barcode."),
                _labeled_input("Cooking factor", "cooking_factor", "number", help_text="Raw/cooked weight conversion factor."),
                id="catalog_advanced",
                cls="hidden grid grid-cols-1 md:grid-cols-2 gap-2 col-span-1 md:col-span-2",
            ),
            cls="grid grid-cols-1 md:grid-cols-2 gap-2",
        ),
        Button("Create catalog item", type="submit", cls="web_button px-3 py-2 text-xs"),
        hx_post="/food/create/catalog",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        cls="web_container p-3 rounded-2xl flex flex-col gap-3 w-full",
    )
    return _create_page_shell("Create Catalog", form, result_id)


def CreateManualPage(subtype_options: list[str] | None = None, origin_options: list[str] | None = None):
    result_id = "create_manual_result_page"
    form = Form(
        Div(
            _labeled_input("Name*", "name", help_text="Manual intake name. Required."),
            _labeled_input("Description", "description", help_text="Optional short description."),
            _searchable_autocomplete_input(
                "Subtype*",
                "subtype",
                subtype_options or [],
                help_text="Specific subtype. Required.",
                allow_add=True,
            ),
            _searchable_autocomplete_input(
                "Origin",
                "source_origin",
                origin_options or [],
                help_text="Where it came from (home, restaurant, etc.).",
                allow_add=True,
            ),
            _labeled_input("Amount g*", "amount_g", "number", help_text="Consumed amount in grams/ml. Required."),
            _smart_macros_block("manual"),
            _favorite_checkbox(),
            _advanced_toggle("manual_advanced"),
            Div(
                _labeled_input("Caffeine", "caffeine", "number", help_text="Caffeine content in mg per 100g/ml."),
                _labeled_input("Alcohol", "alcohol", "number", help_text="Alcohol content in grams per 100g/ml."),
                _searchable_autocomplete_input("Glycemic index", "glycemic_index", GLYCEMIC_INDEX_OPTIONS, help_text="Estimated glycemic index level."),
                _labeled_input("IG confidence 1-5", "ig_confidence", "number", help_text="Confidence in glycemic index estimate (1 low, 5 high)."),
                id="manual_advanced",
                cls="hidden grid grid-cols-1 md:grid-cols-2 gap-2 col-span-1 md:col-span-2",
            ),
            cls="grid grid-cols-1 md:grid-cols-2 gap-2",
        ),
        Button("Create manual intake", type="submit", cls="web_button px-3 py-2 text-xs"),
        hx_post="/food/create/manual",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        cls="web_container p-3 rounded-2xl flex flex-col gap-3 w-full",
    )
    return _create_page_shell("Create Manual Intake", form, result_id)


def CreateRecipePage():
    result_id = "create_recipe_result_page"
    form = Form(
        Div(
            _labeled_input("Name*", "name", help_text="Recipe name. Required."),
            _labeled_select("Meal type", "meal_type", MEAL_TYPES, help_text="When this recipe is usually eaten."),
            _favorite_checkbox(),
            _advanced_toggle("recipe_advanced"),
            Div(
                Div(
                    _label_with_help("Notes", "Optional instructions, comments, or context about this recipe."),
                    Textarea(
                        "",
                        name="notes",
                        rows="3",
                        cls="web_input border border-white rounded-lg px-2 py-1 text-xs",
                    ),
                    cls="flex flex-col gap-1 col-span-1 md:col-span-2",
                ),
                id="recipe_advanced",
                cls="hidden grid grid-cols-1 md:grid-cols-2 gap-2 col-span-1 md:col-span-2",
            ),
            cls="grid grid-cols-1 md:grid-cols-2 gap-2",
        ),
        Button("Create recipe", type="submit", cls="web_button px-3 py-2 text-xs"),
        hx_post="/food/create/recipe",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        cls="web_container p-3 rounded-2xl flex flex-col gap-3 w-full",
    )
    return _create_page_shell("Create Recipe", form, result_id)


def _input_value(value) -> str:
    if value is None:
        return ""
    return str(value)


def _edit_page_shell(form, result_id: str):
    return Div(
        Div(form, cls="w-full"),
        Div(id=result_id, cls="text-xs w-full"),
        _searchable_autocomplete_bootstrap_script(),
        data_hide_cart="true",
        cls="""
            flex flex-col items-center
            gap-4
            md:mt-7 lg:mt-7 mt-2
            md:w-md lg:w-md w-xs
            w-full mx-auto
            md:mb-28 lg:mb-28 mb-24
        """,
    )


def _edit_tile(content, cls: str = ""):
    extra = f" {cls.strip()}" if cls and cls.strip() else ""
    return Div(content, cls=f"web_container p-3 rounded-xl flex flex-col gap-1{extra}")


def _edit_name_input(value: str):
    return Textarea(
        value,
        name="name",
        rows="2",
        cls="""
            w-full text-2xl font-bold text-black text-center
            px-0 py-0 border-0 rounded-none
            bg-transparent shadow-none
            focus:outline-none resize-none mr-1
        """,
        style="background:transparent;border-color:transparent;box-shadow:none;",
    )


def EditCatalogPage(entry: dict, brand_options: list[str] | None = None, subtype_options: list[str] | None = None):
    result_id = f"edit_catalog_result_{entry['id']}"
    form = Form(
        _edit_name_input(_input_value(entry.get("name"))),
        _edit_tile(_brand_autocomplete_input(brand_options=brand_options, value=_input_value(entry.get("brand")))),
        Div(
            H2("Macros Summary", cls="font-semibold text-gray-900"),
            Div(
                _edit_tile(_labeled_input("Calories/100g", "calories_100g", "number", value=_input_value(entry.get("calories_100g")))),
                _edit_tile(_labeled_input("Carbs/100g", "carbs_100g", "number", value=_input_value(entry.get("carbs_100g")))),
                _edit_tile(_labeled_input("Sugars/100g", "sugars_100g", "number", value=_input_value(entry.get("sugars_100g")))),
                _edit_tile(_labeled_input("Fats/100g", "fats_100g", "number", value=_input_value(entry.get("fats_100g")))),
                _edit_tile(_labeled_input("Saturated/100g", "saturated_100g", "number", value=_input_value(entry.get("saturated_100g")))),
                _edit_tile(_labeled_input("Proteins/100g", "proteins_100g", "number", value=_input_value(entry.get("proteins_100g")))),
                _edit_tile(_labeled_input("Fiber/100g", "fiber_100g", "number", value=_input_value(entry.get("fiber_100g")))),
                cls="grid grid-cols-2 md:grid-cols-3 gap-2",
            ),
            cls="flex flex-col gap-2 w-full",
        ),
        Div(
            H2("Details", cls="font-semibold text-gray-900"),
            Div(
                _edit_tile(_searchable_autocomplete_input("Category*", "category", CATEGORY_OPTIONS, allow_add=True, value=_input_value(entry.get("category")))),
                _edit_tile(_searchable_autocomplete_input("Subtype*", "subtype", subtype_options or [], allow_add=True, value=_input_value(entry.get("subtype")))),
                _edit_tile(_labeled_input("Default portion", "default_portion", "number", step="any", value=_input_value(entry.get("default_portion")))),
                _edit_tile(_searchable_autocomplete_input("Initial state", "initial_state", INITIAL_STATE_OPTIONS, allow_add=False, value=_input_value(entry.get("initial_state")))),
                _edit_tile(_searchable_autocomplete_input("Nutriscore", "nutriscore", ["A", "B", "C", "D", "E"], allow_add=False, value=_input_value(entry.get("nutriscore")))),
                _edit_tile(_labeled_input("NOVA (1-4)", "nova", "number", value=_input_value(entry.get("nova")))),
                _edit_tile(_labeled_input("Yuka (0-100)", "yuka", "number", value=_input_value(entry.get("yuka")))),
                _edit_tile(_labeled_input("Caffeine", "caffeine", "number", value=_input_value(entry.get("caffeine")))),
                _edit_tile(_labeled_input("Alcohol", "alcohol", "number", value=_input_value(entry.get("alcohol")))),
                _edit_tile(_labeled_input("Barcode", "barcode", value=_input_value(entry.get("barcode")))),
                _edit_tile(_labeled_input("Cooking factor", "cooking_factor", "number", value=_input_value(entry.get("cooking_factor")))),
                _edit_tile(
                    Div(
                        _favorite_checkbox(checked=bool(entry.get("favorite")), centered=True),
                        cls="h-full min-h-20 flex items-center justify-center",
                    )
                ),
                cls="grid grid-cols-1 md:grid-cols-2 gap-2",
            ),
            cls="flex flex-col gap-2 w-full",
        ),
        Div(
            Button(
                "Back",
                type="button",
                cls="""
                    web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl
                    bg-white/85 text-gray-800 border border-gray-300
                    shadow-[0_6px_20px_rgba(17,24,39,0.08)]
                """,
                hx_get=f"/food/item/catalog/{entry['id']}",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            Button("Save changes", type="submit", cls="web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl bg-black text-white border-black"),
            cls="grid grid-cols-2 gap-3",
        ),
        hx_post=f"/food/edit/catalog/{entry['id']}",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        cls="flex flex-col gap-3 w-full",
    )
    return _edit_page_shell(form, result_id)


def EditManualPage(entry: dict, subtype_options: list[str] | None = None, origin_options: list[str] | None = None):
    result_id = f"edit_manual_result_{entry['id']}"
    form = Form(
        _edit_name_input(_input_value(entry.get("name"))),
        _edit_tile(_searchable_autocomplete_input("Brand / Origin", "source_origin", origin_options or [], allow_add=True, value=_input_value(entry.get("origin")))),
        Div(
            H2("Macros Summary", cls="font-semibold text-gray-900"),
            Div(
                _edit_tile(_labeled_input("Calories/100g", "calories_100g", "number", value=_input_value(entry.get("calories_100g")))),
                _edit_tile(_labeled_input("Carbs/100g", "carbs_100g", "number", value=_input_value(entry.get("carbs_100g")))),
                _edit_tile(_labeled_input("Sugars/100g", "sugars_100g", "number", value=_input_value(entry.get("sugars_100g")))),
                _edit_tile(_labeled_input("Fats/100g", "fats_100g", "number", value=_input_value(entry.get("fats_100g")))),
                _edit_tile(_labeled_input("Saturated/100g", "saturated_100g", "number", value=_input_value(entry.get("saturated_100g")))),
                _edit_tile(_labeled_input("Proteins/100g", "proteins_100g", "number", value=_input_value(entry.get("proteins_100g")))),
                _edit_tile(_labeled_input("Fiber/100g", "fiber_100g", "number", value=_input_value(entry.get("fiber_100g")))),
                cls="grid grid-cols-2 md:grid-cols-3 gap-2",
            ),
            cls="flex flex-col gap-2 w-full",
        ),
        Div(
            H2("Details", cls="font-semibold text-gray-900"),
            Div(
                _edit_tile(
                    Div(
                        _label_with_help("Description", "Optional short description."),
                        Textarea(
                            _input_value(entry.get("description")),
                            name="description",
                            rows="4",
                            cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-base mr-1 w-full",
                        ),
                        cls="flex flex-col gap-1",
                    ),
                    cls="col-span-1 md:col-span-2",
                ),
                _edit_tile(_searchable_autocomplete_input("Subtype*", "subtype", subtype_options or [], allow_add=True, value=_input_value(entry.get("subtype")))),
                _edit_tile(_labeled_input("Amount g*", "amount_g", "number", value=_input_value(entry.get("amount_g")))),
                _edit_tile(_labeled_input("Caffeine", "caffeine", "number", value=_input_value(entry.get("caffeine")))),
                _edit_tile(_labeled_input("Alcohol", "alcohol", "number", value=_input_value(entry.get("alcohol")))),
                _edit_tile(_searchable_autocomplete_input("Glycemic index", "glycemic_index", GLYCEMIC_INDEX_OPTIONS, allow_add=False, value=_input_value(entry.get("glycemic_index")))),
                _edit_tile(_labeled_input("IG confidence 1-5", "ig_confidence", "number", value=_input_value(entry.get("ig_confidence")))),
                _edit_tile(
                    Div(
                        _favorite_checkbox(checked=bool(entry.get("favorite")), centered=True),
                        cls="h-full min-h-20 flex items-center justify-center",
                    )
                ),
                cls="grid grid-cols-1 md:grid-cols-2 gap-2",
            ),
            cls="flex flex-col gap-2 w-full",
        ),
        Div(
            Button(
                "Back",
                type="button",
                cls="""
                    web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl
                    bg-white/85 text-gray-800 border border-gray-300
                    shadow-[0_6px_20px_rgba(17,24,39,0.08)]
                """,
                hx_get=f"/food/item/manual_intake/{entry['id']}",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            Button("Save changes", type="submit", cls="web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl bg-black text-white border-black"),
            cls="grid grid-cols-2 gap-3",
        ),
        hx_post=f"/food/edit/manual/{entry['id']}",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        cls="flex flex-col gap-3 w-full",
    )
    return _edit_page_shell(form, result_id)


def EditRecipePage(entry: dict):
    result_id = f"edit_recipe_result_{entry['id']}"
    form = Form(
        _edit_name_input(_input_value(entry.get("name"))),
        Div(
            H2("Details", cls="font-semibold text-gray-900"),
            Div(
                _edit_tile(_labeled_select("Meal type", "meal_type", MEAL_TYPES, selected_value=_input_value(entry.get("meal_type")))),
                _edit_tile(
                    Div(
                        _favorite_checkbox(checked=bool(entry.get("favorite")), centered=True),
                        cls="h-full min-h-20 flex items-center justify-center",
                    )
                ),
                _edit_tile(
                    Div(
                        _label_with_help("Notes", "Optional instructions, comments, or context about this recipe."),
                        Textarea(
                            _input_value(entry.get("notes")),
                            name="notes",
                            rows="3",
                            onclick="this.select()",
                            cls="web_input border border-white rounded-lg px-2 py-1 text-xs mr-1",
                        ),
                        cls="flex flex-col gap-1",
                    )
                ),
                cls="grid grid-cols-1 md:grid-cols-2 gap-2",
            ),
            cls="flex flex-col gap-2 w-full",
        ),
        Div(
            Button(
                "Back",
                type="button",
                cls="""
                    web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl
                    bg-white/85 text-gray-800 border border-gray-300
                    shadow-[0_6px_20px_rgba(17,24,39,0.08)]
                """,
                hx_get=f"/food/item/recipe/{entry['id']}",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            Button("Save changes", type="submit", cls="web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl bg-black text-white border-black"),
            cls="grid grid-cols-2 gap-3",
        ),
        hx_post=f"/food/edit/recipe/{entry['id']}",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        cls="flex flex-col gap-3 w-full",
    )
    return _edit_page_shell(form, result_id)


def FavoriteButton(entry_type: str, entry_id: int, favorite: bool):
    icon = "/images/content/fav_icon.svg" if favorite else "/images/content/not_fav_icon.svg"
    return Button(
        Img(src=icon, cls="w-4 h-4", alt=""),
        type="button",
        aria_label="Toggle favorite",
        title="Toggle favorite",
        cls="""
            web_button p-1.5
            border-gray-500/30 shadow-none
            w-8 h-8
            flex items-center justify-center
            hover:bg-gray-500/20
        """,
        hx_post=f"/food/favorite/{entry_type}/{entry_id}",
        hx_target="this",
        hx_swap="outerHTML",
        hx_trigger="click consume",
        data_skip_page_loading="true",
        data_no_open="true",
    )


def AddButton(**attrs):
    attrs.setdefault("hx_include", "#meal_selector")
    attrs.setdefault("data_skip_page_loading", "true")
    attrs.setdefault("hx_target", "this")
    attrs.setdefault("hx_trigger", "click consume")
    attrs.setdefault("data_no_open", "true")
    return Button(
        "+",
        cls="""
            web_button
            rounded-lg
            border-gray-500/30 shadow-none
            hover:bg-gray-500/50
            w-8 h-8
            flex items-center justify-center
            transition-colors duration-300
            text-base
        """,
        hx_swap="none",
        **on_after(reload_page=False),
        **attrs,
    )


def _entry_meta(food):
    if food["entry_type"] == "catalog":
        carbs = food.get("carbs_100g")
        return f"Food · {carbs if carbs is not None else '-'} CH"
    if food["entry_type"] == "manual_intake":
        carbs = food.get("carbs_100g")
        return f"Manual · {carbs if carbs is not None else '-'} CH"
    return "Recipe"


def _float_or_zero(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _display_base_unit(entry_type: str, item: dict) -> str:
    if entry_type == "catalog" and (item.get("category") or "").strip().lower() == "beverages":
        return "ml"
    if entry_type == "manual_intake":
        subtype = (item.get("subtype") or "").strip().lower()
        liquid_hints = ("drink", "beverage", "juice", "soda", "smoothie", "milk", "coffee", "tea", "bebida")
        if any(token in subtype for token in liquid_hints):
            return "ml"
    return "g"


def _detail_unit_options(base_amount: float, base_unit: str):
    hundred_label = f"100{base_unit}"
    one_label = base_unit
    return [
        Option(
            f"serving ({base_amount:.0f}{base_unit})",
            value="portion",
            selected=True,
            data_factor=f"{base_amount:.6f}",
            data_unit_label="serving",
        ),
        Option(f"{hundred_label} (100{base_unit})", value="x100", data_factor="100.000000", data_unit_label=hundred_label),
        Option(f"{one_label} (1{base_unit})", value=base_unit, data_factor="1.000000", data_unit_label=one_label),
        Option(f"lb (453.59{base_unit})", value="lb", data_factor="453.592370", data_unit_label="lb"),
        Option(f"oz (28.35{base_unit})", value="oz", data_factor="28.349523", data_unit_label="oz"),
    ]


def _detail_macro_tiles(per100: dict, amount_g: float):
    specs = [
        ("calories_100g", "Calories", "kcal"),
        ("carbs_100g", "Carbs", "g"),
        ("sugars_100g", "Sugars", "g"),
        ("fats_100g", "Fats", "g"),
        ("saturated_100g", "Saturated", "g"),
        ("proteins_100g", "Proteins", "g"),
        ("fiber_100g", "Fiber", "g"),
    ]
    tiles = []
    for key, label, unit in specs:
        amount = (amount_g * _float_or_zero(per100.get(key))) / 100.0
        amount_text = f"{amount:.0f} {unit}" if unit == "kcal" else f"{amount:.1f} {unit}"
        tiles.append(
            Div(
                Span(label, cls="text-xs text-gray-600"),
                Span(
                    amount_text,
                    data_detail_macro_key=key,
                    data_per100=f"{_float_or_zero(per100.get(key)):.6f}",
                    data_unit=unit,
                    cls="text-base font-semibold text-gray-900",
                ),
                cls="web_container p-3 rounded-xl flex flex-col gap-1",
            )
        )
    return tiles


def _detail_info_rows(rows: list[tuple[str, str]]):
    blocks = []
    for label, value in rows:
        clean = (value or "").strip()
        if not clean:
            continue
        blocks.append(
            Div(
                Span(label, cls="text-xs text-gray-600"),
                Span(clean, cls="text-sm text-gray-900"),
                cls="web_container p-3 rounded-xl flex flex-col gap-1",
            )
        )
    if not blocks:
        return Div("No extra info yet.", cls="text-sm text-gray-500")
    return Div(*blocks, cls="grid grid-cols-1 md:grid-cols-2 gap-2")


def FoodDetailPage(connection, user_id: int, entry_type: str, entry: dict, summary: dict):
    base_unit = _display_base_unit(entry_type, entry)
    default_amount = max(1.0, _float_or_zero(summary.get("default_amount_g")) or 100.0)
    amount_display = f"{default_amount:.2f}".replace(".", ",")
    per100 = summary.get("per100") or {}
    info_rows = summary.get("info_rows") or []
    subtitle = summary.get("subtitle") or ""
    edit_label = {"catalog": "Edit food", "manual_intake": "Edit manual", "recipe": "Edit recipe"}.get(entry_type, "Edit")
    edit_href = {
        "catalog": f"/food/edit/catalog/{entry['id']}/form",
        "manual_intake": f"/food/edit/manual_intake/{entry['id']}/form",
        "recipe": f"/food/edit/recipe/{entry['id']}/form",
    }.get(entry_type, "/food")

    root_id = f"food_detail_{entry_type}_{entry['id']}"
    display_id = f"{root_id}_display"
    grams_id = f"{root_id}_grams"
    select_id = f"{root_id}_select"
    side_unit_id = f"{root_id}_side_unit"
    plate_value_id = f"{root_id}_plate_value"
    plate_unit_id = f"{root_id}_plate_unit"
    plate_unit_btn_id = f"{root_id}_plate_unit_btn"
    plate_grams_id = f"{root_id}_plate_grams"
    plate_equivalent_id = f"{root_id}_plate_equivalent"
    leftovers_id = f"{root_id}_leftovers"
    msg_id = f"{root_id}_msg"
    persist_key = f"food_detail_amount_{entry_type}_{entry['id']}"

    return Div(
        Div(
            H1(entry.get("name") or "-", cls="text-2xl font-bold text-gray-900"),
            P(subtitle, cls="text-sm text-gray-600"),
            cls="flex flex-col gap-1",
        ),
        MealSelector(connection, user_id=user_id or 0),
        Div(
            Form(
                Div(
                    Input(
                        type="text",
                        id=display_id,
                        inputmode="decimal",
                        value=amount_display,
                        aria_label="Food amount",
                        cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 w-24 text-base",
                        onchange=f"dbFoodDetailRefresh('{root_id}')",
                        onclick="this.select()",
                    ),
                    Span("serving", id=side_unit_id, cls="text-xs text-gray-600"),
                    Select(
                        *_detail_unit_options(default_amount, base_unit),
                        id=select_id,
                        data_display_id=display_id,
                        data_grams_id=grams_id,
                        data_side_unit_id=side_unit_id,
                        data_persist_key=f"food_detail_unit_{entry_type}_{entry['id']}",
                        aria_label="Food unit selector",
                        cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-xs md:text-sm justify-self-end",
                        onchange=f"dbFoodDetailOnUnitChange('{root_id}')",
                    ),
                    Input(type="hidden", name="total_amount_g", id=grams_id, value=f"{default_amount:.6f}"),
                    cls="flex items-center gap-2",
                ),
                Div(
                    Span("To plate", cls="text-xs text-gray-600"),
                    Input(
                        type="text",
                        id=plate_value_id,
                        inputmode="decimal",
                        value="100",
                        aria_label="Amount to plate",
                        cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 w-20 text-base",
                        oninput=f"dbFoodDetailPlateRefresh('{root_id}')",
                        onchange=f"dbFoodDetailPlateRefresh('{root_id}')",
                        onclick="this.select()",
                    ),
                    Button(
                        "%",
                        type="button",
                        id=plate_unit_btn_id,
                        aria_label="Toggle to plate unit",
                        onclick=f"dbFoodDetailTogglePlateUnit('{root_id}')",
                        cls="""
                            web_button px-2 py-1 text-sm min-w-10
                            border border-gray-300 bg-white/85
                        """,
                    ),
                    Input(type="hidden", id=plate_unit_id, value="%"),
                    Input(type="hidden", name="amount_g", id=plate_grams_id, value=f"{default_amount:.6f}"),
                    cls="flex items-center gap-2",
                ),
                P(
                    f"Total amount (plate amount): {default_amount:.1f} ({default_amount:.1f}) {base_unit}",
                    id=plate_equivalent_id,
                    data_detail_plate_equivalent="true",
                    cls="text-xs text-gray-600",
                ),
                P(
                    f"Will be saved in fridge: {0.0:.1f} {base_unit}",
                    id=leftovers_id,
                    data_detail_leftovers="true",
                    cls="text-xs text-gray-600",
                ),
                cls="web_container p-3 rounded-2xl flex flex-col gap-2",
            ),
            cls="w-full",
        ),
        Div(
            H2("Macros Summary", cls="font-semibold text-gray-900"),
            Div(*_detail_macro_tiles(per100, default_amount), id=f"{root_id}_macros", cls="grid grid-cols-2 md:grid-cols-3 gap-2"),
            cls="flex flex-col gap-2 w-full",
        ),
        Div(
            H2("Details", cls="font-semibold text-gray-900"),
            _detail_info_rows(info_rows),
            cls="flex flex-col gap-2 w-full",
        ),
        Div(
            Button(
                edit_label,
                type="button",
                cls="""
                    web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl
                    bg-white/85 text-gray-800 border border-gray-300
                    shadow-[0_6px_20px_rgba(17,24,39,0.08)]
                """,
                hx_get=edit_href,
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            Button(
                "Log food",
                type="button",
                cls="web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl bg-black text-white border-black",
                hx_post=f"/food/log/{entry_type}/{entry['id']}",
                hx_target=f"#{msg_id}",
                hx_swap="innerHTML",
                hx_include=f"#meal_selector, #{plate_grams_id}, #{grams_id}",
                data_skip_page_loading="true",
            ),
            cls="w-full grid grid-cols-2 gap-3",
        ),
        Div(id=msg_id, cls="min-h-6 text-xs"),
        Script(src="/js/cart_units.js", defer="defer"),
        Script(src="/js/food_detail.js", defer="defer"),
        data_food_detail="true",
        data_detail_display_id=display_id,
        data_detail_select_id=select_id,
        data_detail_grams_id=grams_id,
        data_detail_side_unit_id=side_unit_id,
        data_detail_plate_value_id=plate_value_id,
        data_detail_plate_unit_id=plate_unit_id,
        data_detail_plate_unit_btn_id=plate_unit_btn_id,
        data_detail_plate_grams_id=plate_grams_id,
        data_detail_plate_equivalent_id=plate_equivalent_id,
        data_detail_leftovers_id=leftovers_id,
        data_detail_base_unit=base_unit,
        data_detail_persist_key=persist_key,
        data_hide_cart="true",
        id=root_id,
        cls="""
            flex flex-col items-center
            gap-4
            md:mt-7 lg:mt-7 mt-2
            md:w-md lg:w-md w-xs
            w-full mx-auto
            md:mb-28 lg:mb-28 mb-24
        """,
    )


def FoodCard(food):
    add_path = f"/add_food/{food['id']}"
    if food["entry_type"] == "manual_intake":
        add_path = f"/add_manual_intake/{food['id']}"
    if food["entry_type"] == "recipe":
        add_path = f"/add_recipe/{food['id']}"

    return Div(
        Div(
            H1(food["name"], cls="text-left font-semibold hover:underline"),
            Div(_entry_meta(food), cls="text-sm text-gray-700"),
            cls="flex flex-col gap-0.5 min-w-0",
        ),
        Div(
            FavoriteButton(food["entry_type"], food["id"], bool(food.get("favorite"))),
            AddButton(hx_post=add_path),
            cls="flex items-center gap-2 ml-3",
        ),
        hx_get=f"/food/item/{food['entry_type']}/{food['id']}",
        hx_target="#main_content",
        hx_swap="innerHTML",
        hx_push_url="true",
        hx_trigger="click[!event.target.closest('[data-no-open]')]",
        cls="web_button food_entry flex items-center justify-between cursor-pointer",
    )


def FoodSectionsContent(foods):
    grouped = {"catalog": [], "recipe": [], "manual_intake": []}
    for food in foods:
        entry_type = food.get("entry_type")
        if entry_type in grouped:
            grouped[entry_type].append(food)

    sections = []
    for entry_type, title in (
        ("catalog", "Food"),
        ("recipe", "Recipes"),
        ("manual_intake", "Manual intake"),
    ):
        items = grouped[entry_type]
        if not items:
            continue
        sections.append(H2(title, cls="text-gray-700"))
        sections.extend(FoodCard(item) for item in items)
    return sections


def FoodList(foods):
    if not foods:
        return Div(H2("No items", cls="text-gray-600"), cls="flex flex-col items-center")

    return Div(
        *FoodSectionsContent(foods),
        id="food-list",
        cls="flex flex-col items-center md:gap-3 lg:gap-3 gap-2 mt-4",
    )
