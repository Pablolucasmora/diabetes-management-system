from fasthtml.common import *
from datetime import datetime
import json
from DayBetes_food.components.food.food_main import food_main
from DayBetes_food.components.ui import render_fragment, render_page
from DayBetes_food.database.queries.crud import (
    add_catalog_item,
    get_all_catalog,
    get_all_manual_intakes,
    get_all_recipes,
    add_intake_event,
    add_portion_detail,
    get_catalog_item,
    get_manual_intake,
    get_recipe,
    get_portion_detail_by_recipe,
    get_portion_detail,
    get_recipe_portions_by_origin,
    get_default_user_id,
    get_intake_event,
    update_catalog_item,
    update_catalog_favorite,
    update_manual_intake,
    update_recipe,
    add_manual_intake,
    add_recipe,
    add_food_brand,
    get_food_brand_suggestions,
    get_subtype_suggestions,
    get_manual_origin_suggestions,
    update_portion_detail_amount,
    update_portion_detail_fields,
    delete_portion_detail,
)
from DayBetes_food.components.food.foods import FoodSectionsContent, FavoriteButton, on_after
from DayBetes_food.components.food.foods import (
    CreateCatalogPage,
    CreateManualPage,
    CreateRecipePage,
    EditCatalogPage,
    EditManualPage,
    EditRecipePage,
    FoodDetailPage,
    RecipeIngredientPickerList,
    RecipeIngredientPickerPage,
    RecipeMacrosGrid,
)
from DayBetes_food.database.connection import get_connection


def _to_float(value: str):
    normalized = (value or "").strip().replace(",", ".")
    if not normalized:
        return None
    try:
        return float(normalized)
    except (TypeError, ValueError):
        return None


def _to_int(value: str):
    normalized = (value or "").strip()
    if not normalized:
        return None
    try:
        return int(normalized)
    except (TypeError, ValueError):
        return None


def _to_bool(value: str):
    return (value or "").strip().lower() in ("1", "true", "on", "yes")


def _macro_value(row: dict, macro_key: str):
    catalog_value = row.get(f"catalog_{macro_key}_100g")
    manual_value = row.get(f"manual_{macro_key}_100g")
    return catalog_value if catalog_value is not None else manual_value


def _build_detail_summary(entry_type: str, entry: dict, recipe_portions: list | None = None) -> dict:
    if entry_type == "catalog":
        return {
            "subtitle": entry.get("brand") or "No brand",
            "default_amount_g": float(entry.get("default_portion") or 100.0),
            "per100": {
                "calories_100g": float(entry.get("calories_100g") or 0.0),
                "carbs_100g": float(entry.get("carbs_100g") or 0.0),
                "sugars_100g": float(entry.get("sugars_100g") or 0.0),
                "fats_100g": float(entry.get("fats_100g") or 0.0),
                "saturated_100g": float(entry.get("saturated_100g") or 0.0),
                "proteins_100g": float(entry.get("proteins_100g") or 0.0),
                "fiber_100g": float(entry.get("fiber_100g") or 0.0),
            },
            "info_rows": [
                ("Category", str(entry.get("category") or "")),
                ("Subtype", str(entry.get("subtype") or "")),
                ("Initial state", str(entry.get("initial_state") or "")),
                ("Nutriscore", str(entry.get("nutriscore") or "")),
                ("NOVA", str(entry.get("nova") or "")),
                ("Yuka", str(entry.get("yuka") or "")),
                ("Caffeine", str(entry.get("caffeine") or "")),
                ("Alcohol", str(entry.get("alcohol") or "")),
                ("Barcode", str(entry.get("barcode") or "")),
                ("Cooking factor", str(entry.get("cooking_factor") or "")),
            ],
        }

    if entry_type == "manual_intake":
        return {
            "subtitle": entry.get("origin") or "Manual intake",
            "default_amount_g": float(entry.get("amount_g") or 100.0),
            "per100": {
                "calories_100g": float(entry.get("calories_100g") or 0.0),
                "carbs_100g": float(entry.get("carbs_100g") or 0.0),
                "sugars_100g": float(entry.get("sugars_100g") or 0.0),
                "fats_100g": float(entry.get("fats_100g") or 0.0),
                "saturated_100g": float(entry.get("saturated_100g") or 0.0),
                "proteins_100g": float(entry.get("proteins_100g") or 0.0),
                "fiber_100g": float(entry.get("fiber_100g") or 0.0),
            },
            "info_rows": [
                ("Description", str(entry.get("description") or "")),
                ("Subtype", str(entry.get("subtype") or "")),
                ("Origin", str(entry.get("origin") or "")),
                ("Stored amount", str(entry.get("amount_g") or "")),
                ("Glycemic index", str(entry.get("glycemic_index") or "")),
                ("IG confidence", str(entry.get("ig_confidence") or "")),
                ("Caffeine", str(entry.get("caffeine") or "")),
                ("Alcohol", str(entry.get("alcohol") or "")),
            ],
        }

    portions = recipe_portions or []
    total_amount = sum(float(row.get("amount_g") or 0.0) for row in portions)
    totals = {
        "calories_100g": 0.0,
        "carbs_100g": 0.0,
        "sugars_100g": 0.0,
        "fats_100g": 0.0,
        "saturated_100g": 0.0,
        "proteins_100g": 0.0,
        "fiber_100g": 0.0,
    }
    for row in portions:
        amount = float(row.get("amount_g") or 0.0)
        for key in list(totals.keys()):
            macro = _macro_value(row, key.replace("_100g", ""))
            if macro is None:
                continue
            totals[key] += amount * float(macro) / 100.0

    per100 = {}
    for key, total in totals.items():
        per100[key] = (total * 100.0 / total_amount) if total_amount > 0 else 0.0

    return {
        "subtitle": "Recipe",
        "default_amount_g": total_amount or 100.0,
        "per100": per100,
        "info_rows": [
            ("Meal type", str(entry.get("meal_type") or "")),
            ("Notes", str(entry.get("notes") or "")),
            ("Ingredients", str(len(portions))),
            ("Recipe amount", f"{total_amount:.1f}" if total_amount > 0 else ""),
        ],
    }


def _sorted_food_entries(catalog_items, manual_items, recipes):
    entries = []
    for item in catalog_items:
        entries.append({"entry_type": "catalog", **item})
    for item in manual_items:
        entries.append({"entry_type": "manual_intake", **item})
    for item in recipes:
        entries.append({"entry_type": "recipe", **item})
    entries.sort(key=lambda item: (0 if item.get("favorite") else 1, (item.get("name") or "").lower()))
    return entries


def _filtered_entries(connection, search: str = "", filter_value: str = "all", include_recipes: bool = True):
    user_id = get_default_user_id(connection)

    catalog_items = get_all_catalog(connection, search=search or None)
    manual_items = get_all_manual_intakes(connection, users_id=user_id, search=search or None) if user_id else []
    recipes = get_all_recipes(connection, users_id=user_id, search=search or None) if user_id and include_recipes else []

    if filter_value == "food":
        entries = _sorted_food_entries(catalog_items, manual_items, [])
    elif filter_value == "recipes":
        entries = _sorted_food_entries([], [], recipes)
    elif filter_value == "favs":
        entries = _sorted_food_entries(
            [item for item in catalog_items if item.get("favorite")],
            [item for item in manual_items if item.get("favorite")],
            [item for item in recipes if item.get("favorite")],
        )
    else:
        entries = _sorted_food_entries(catalog_items, manual_items, recipes)

    return entries



def _error_msg(text: str):
    return render_fragment(
        Div(
            P("Error", cls="text-[11px] font-semibold text-red-800"),
            P(text, cls="text-xs text-red-700"),
            cls="web_container p-2 rounded-lg border border-red-200/70 bg-red-50/60",
        )
    )


def setup_food_routes(rt):
    
    @rt("/food")
    def get(request):
        return render_page(request, food_main)

    @rt("/food/create/catalog/form")
    def get(request: Request, barcode: str = ""):
        with get_connection() as connection:
            brands = get_food_brand_suggestions(connection, search="", limit=500)
            subtypes = get_subtype_suggestions(connection, search="", limit=500)
        return render_page(
            request,
            lambda _: CreateCatalogPage(
                brand_options=brands,
                subtype_options=subtypes,
                barcode_prefill=(barcode or "").strip(),
            ),
            show_cart=False,
        )

    @rt("/food/create/manual/form")
    def get(request: Request):
        with get_connection() as connection:
            subtypes = get_subtype_suggestions(connection, search="", limit=500)
            origins = get_manual_origin_suggestions(connection, search="", limit=500)
        return render_page(request, lambda _: CreateManualPage(subtype_options=subtypes, origin_options=origins), show_cart=False)

    @rt("/food/create/recipe/form")
    def get(request: Request):
        return render_page(request, lambda _: CreateRecipePage(), show_cart=False)

    @rt("/food/item/{entry_type}/{entry_id}")
    def get(request: Request, entry_type: str, entry_id: int):
        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            entry = None
            recipe_portions = None
            if entry_type == "catalog":
                entry = get_catalog_item(connection, entry_id)
            elif entry_type == "manual_intake":
                entry = get_manual_intake(connection, entry_id)
            elif entry_type == "recipe":
                entry = get_recipe(connection, entry_id)
                recipe_portions = get_portion_detail_by_recipe(connection, entry_id) if entry else []
            if not entry:
                return HTMLResponse(status_code=404)
            summary = _build_detail_summary(entry_type, entry, recipe_portions=recipe_portions)
        return render_page(
            request,
            lambda conn: FoodDetailPage(
                conn,
                user_id=user_id or 0,
                entry_type=entry_type,
                entry=entry,
                summary=summary,
                recipe_portions=recipe_portions,
            ),
            show_cart=False,
        )

    @rt("/food/recipe/{recipe_id}/ingredients/form")
    def get(request: Request, recipe_id: int):
        with get_connection() as connection:
            recipe = get_recipe(connection, recipe_id)
            if not recipe:
                return HTMLResponse(status_code=404)
            entries = _filtered_entries(connection, search="", filter_value="food", include_recipes=False)
        return render_page(request, lambda _: RecipeIngredientPickerPage(recipe_entry=recipe, foods=entries), show_cart=False)

    @rt("/food/recipe/{recipe_id}/ingredients/list")
    def get(request: Request, recipe_id: int, search: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        with get_connection() as connection:
            recipe = get_recipe(connection, recipe_id)
            if not recipe:
                return HTMLResponse(status_code=404)
            entries = _filtered_entries(connection, search=search, filter_value="food", include_recipes=False)
        return render_fragment(RecipeIngredientPickerList(recipe_id=recipe_id, foods=entries))

    @rt("/food/recipe/{recipe_id}/ingredients/add/{entry_type}/{entry_id}")
    def post(request: Request, recipe_id: int, entry_type: str, entry_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        if entry_type not in ("catalog", "manual_intake"):
            return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=400)

        with get_connection() as connection:
            recipe = get_recipe(connection, recipe_id)
            if not recipe:
                return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=404)

            amount_g = 100.0
            if entry_type == "catalog":
                item = get_catalog_item(connection, entry_id)
                if not item:
                    return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=404)
                amount_g = max(1.0, float(item.get("default_portion") or 100.0))
            else:
                item = get_manual_intake(connection, entry_id)
                if not item:
                    return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=404)
                amount_g = max(1.0, float(item.get("amount_g") or 100.0))

            existing = get_recipe_portions_by_origin(connection, recipe_id=recipe_id, origin=entry_type, origin_id=entry_id)
            if existing:
                keep = existing[0]
                total_amount = sum(float(row.get("amount_g") or 0.0) for row in existing) + amount_g
                updated = update_portion_detail_amount(connection, portion_id=int(keep["id"]), amount_g=total_amount)
                deleted_ok = True
                for duplicate in existing[1:]:
                    deleted_ok = delete_portion_detail(connection, int(duplicate["id"])) and deleted_ok
                ok = bool(updated and deleted_ok)
            else:
                created = add_portion_detail(
                    connection,
                    origin=entry_type,
                    origin_id=entry_id,
                    destination="recipe",
                    destination_id=recipe_id,
                    amount_g=amount_g,
                )
                ok = bool(created)

        return HTMLResponse("", headers={"HX-Trigger": "addSuccess" if ok else "addError"})

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/amount")
    def post(request: Request, recipe_id: int, portion_id: int, amount_g: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        parsed_amount = _to_float(amount_g)
        if parsed_amount is None or parsed_amount <= 0:
            return render_fragment(P("Invalid amount.", cls="text-red-700"))

        with get_connection() as connection:
            recipe = get_recipe(connection, recipe_id)
            if not recipe:
                return render_fragment(P("Recipe not found.", cls="text-red-700"))
            portion = get_portion_detail(connection, portion_id)
            if not portion or int(portion.get("recipe_id") or 0) != recipe_id:
                return render_fragment(P("Ingredient not found.", cls="text-red-700"))
            updated = update_portion_detail_amount(connection, portion_id=portion_id, amount_g=parsed_amount)
            recipe_portions = get_portion_detail_by_recipe(connection, recipe_id) if updated else []
            recipe_total_amount = sum(float(row.get("amount_g") or 0.0) for row in recipe_portions)

        if not updated:
            return render_fragment(P("Could not update ingredient.", cls="text-red-700"))
        response = render_fragment(P("Saved", cls="text-green-700"))
        response.headers["HX-Trigger"] = json.dumps(
            {
                "recipe-amount-updated": {
                    "recipe_id": recipe_id,
                    "total_amount": recipe_total_amount,
                }
            }
        )
        return response

    @rt("/food/recipe/{recipe_id}/macros")
    def get(request: Request, recipe_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        with get_connection() as connection:
            recipe = get_recipe(connection, recipe_id)
            if not recipe:
                return HTMLResponse(status_code=404)
            portions = get_portion_detail_by_recipe(connection, recipe_id)
            summary = _build_detail_summary("recipe", recipe, recipe_portions=portions)
            per100 = summary.get("per100") or {}
            total_amount = max(1.0, _to_float(str(summary.get("default_amount_g") or 0.0)) or 1.0)
        return render_fragment(RecipeMacrosGrid(recipe_id=recipe_id, per100=per100, total_amount=total_amount))

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/advanced")
    def post(
        request: Request,
        recipe_id: int,
        portion_id: int,
        cooking: str = "",
        final_state: str = "",
        conservation: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            recipe = get_recipe(connection, recipe_id)
            if not recipe:
                return render_fragment(P("Recipe not found.", cls="text-red-700"))
            portion = get_portion_detail(connection, portion_id)
            if not portion or int(portion.get("recipe_id") or 0) != recipe_id:
                return render_fragment(P("Ingredient not found.", cls="text-red-700"))
                updated = update_portion_detail_fields(
                    connection,
                    portion_id=portion_id,
                    cooking=(cooking or "").strip() or None,
                    final_state=(final_state or "").strip() or None,
                    conservation=((conservation or "").strip() or None),
                )

        if not updated:
            return render_fragment(P("Could not save advanced fields.", cls="text-red-700"))
        return render_fragment(P("Advanced saved", cls="text-green-700"))

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/delete")
    def post(request: Request, recipe_id: int, portion_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            recipe = get_recipe(connection, recipe_id)
            if not recipe:
                return HTMLResponse(status_code=404)
            portion = get_portion_detail(connection, portion_id)
            if not portion or int(portion.get("recipe_id") or 0) != recipe_id:
                return HTMLResponse(status_code=404)
            ok = delete_portion_detail(connection, portion_id)

        return HTMLResponse("", status_code=200 if ok else 400)

    @rt("/food/edit/{entry_type}/{entry_id}/form")
    def get(request: Request, entry_type: str, entry_id: int):
        with get_connection() as connection:
            entry = None
            if entry_type == "catalog":
                entry = get_catalog_item(connection, entry_id)
                if not entry:
                    return HTMLResponse(status_code=404)
                brands = get_food_brand_suggestions(connection, search="", limit=500)
                subtypes = get_subtype_suggestions(connection, search="", limit=500)
                return render_page(
                    request,
                    lambda _: EditCatalogPage(entry=entry, brand_options=brands, subtype_options=subtypes),
                    show_cart=False,
                )
            if entry_type == "manual_intake":
                entry = get_manual_intake(connection, entry_id)
                if not entry:
                    return HTMLResponse(status_code=404)
                subtypes = get_subtype_suggestions(connection, search="", limit=500)
                origins = get_manual_origin_suggestions(connection, search="", limit=500)
                return render_page(
                    request,
                    lambda _: EditManualPage(entry=entry, subtype_options=subtypes, origin_options=origins),
                    show_cart=False,
                )
            if entry_type == "recipe":
                entry = get_recipe(connection, entry_id)
                if not entry:
                    return HTMLResponse(status_code=404)
                return render_page(request, lambda _: EditRecipePage(entry=entry), show_cart=False)
        return HTMLResponse(status_code=404)

    @rt("/food/log/{entry_type}/{entry_id}")
    def post(
        request: Request,
        entry_type: str,
        entry_id: int,
        amount_g: str = "",
        total_amount_g: str = "",
        intake_event_id: str = "",
        cooking: str = "",
        final_state: str = "",
        conservation: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        parsed_amount = _to_float(amount_g)
        parsed_total = _to_float(total_amount_g)
        if parsed_amount is None or parsed_amount <= 0:
            return render_fragment(P("Amount must be greater than 0.", cls="text-red-700"))
        if parsed_total is not None and parsed_total > 0:
            parsed_amount = min(parsed_amount, parsed_total)

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return render_fragment(P("No users available.", cls="text-red-700"))

            if intake_event_id and intake_event_id.isdigit() and int(intake_event_id) != 0:
                event_id = int(intake_event_id)
            else:
                event_id = add_intake_event(connection, users_id=user_id, state="planned")

            if not event_id:
                return render_fragment(P("Could not create meal event.", cls="text-red-700"))

            event_data = get_intake_event(connection, event_id)
            offset_minutes = 0
            if event_data and event_data.get("meal_time"):
                delta = datetime.now() - event_data["meal_time"]
                offset_minutes = int(delta.total_seconds() // 60)

            created = []
            if entry_type == "catalog":
                created.append(
                    add_portion_detail(
                        connection,
                        origin="catalog",
                        origin_id=entry_id,
                        destination="intake_event",
                        destination_id=event_id,
                        amount_g=parsed_amount,
                        cooking=(cooking or "").strip() or None,
                        final_state=(final_state or "").strip() or None,
                        conservation=((conservation or "").strip() or None),
                        strictly_weighed=True,
                        macros_quality=True,
                        plate_amount=parsed_amount,
                        offset_minutes=offset_minutes,
                    )
                )
            elif entry_type == "manual_intake":
                created.append(
                    add_portion_detail(
                        connection,
                        origin="manual_intake",
                        origin_id=entry_id,
                        destination="intake_event",
                        destination_id=event_id,
                        amount_g=parsed_amount,
                        cooking=(cooking or "").strip() or None,
                        final_state=(final_state or "").strip() or None,
                        conservation=((conservation or "").strip() or None),
                        strictly_weighed=True,
                        macros_quality=True,
                        plate_amount=parsed_amount,
                        offset_minutes=offset_minutes,
                    )
                )
            elif entry_type == "recipe":
                recipe_rows = get_portion_detail_by_recipe(connection, entry_id)
                total_recipe_amount = sum(float(row.get("amount_g") or 0.0) for row in recipe_rows)
                if total_recipe_amount <= 0:
                    return render_fragment(P("Recipe has no ingredients to log.", cls="text-red-700"))
                factor = parsed_amount / total_recipe_amount
                for row in recipe_rows:
                    row_amount = float(row.get("amount_g") or 0.0) * factor
                    if row_amount <= 0:
                        continue
                    if row.get("catalog_id"):
                        created.append(
                            add_portion_detail(
                                connection,
                                origin="catalog",
                                origin_id=int(row["catalog_id"]),
                                destination="intake_event",
                                destination_id=event_id,
                                amount_g=row_amount,
                                cooking=row.get("cooking"),
                                conservation=row.get("conservation"),
                                final_state=row.get("final_state"),
                                strictly_weighed=True,
                                macros_quality=True,
                                plate_amount=row_amount,
                                is_cooked_weight=bool(row.get("is_cooked_weight")),
                                offset_minutes=offset_minutes,
                            )
                        )
                    elif row.get("manual_intake_id"):
                        created.append(
                            add_portion_detail(
                                connection,
                                origin="manual_intake",
                                origin_id=int(row["manual_intake_id"]),
                                destination="intake_event",
                                destination_id=event_id,
                                amount_g=row_amount,
                                cooking=row.get("cooking"),
                                conservation=row.get("conservation"),
                                final_state=row.get("final_state"),
                                strictly_weighed=True,
                                macros_quality=True,
                                plate_amount=row_amount,
                                is_cooked_weight=bool(row.get("is_cooked_weight")),
                                offset_minutes=offset_minutes,
                            )
                        )
            else:
                return render_fragment(P("Unsupported entry type.", cls="text-red-700"))

            ok = bool(created) and all(created)
            if ok:
                return HTMLResponse("", headers={"HX-Redirect": "/food"})
            return render_fragment(P("Could not log food.", cls="text-red-700"))

    @rt("/food/list")
    def get(request: Request, search: str = "", filter: str = "all"):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            entries = _filtered_entries(connection, search=search, filter_value=filter)
        if not entries:
            return render_fragment(H2("No items", cls="text-gray-600"))
        return render_fragment(tuple(FoodSectionsContent(entries)))

    @rt("/search_food")
    def get(request: Request, search: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        with get_connection() as connection:
            entries = _filtered_entries(connection, search=search, filter_value="all")
        if not entries:
            return render_fragment(H2("No items", cls="text-gray-600"))
        return render_fragment(tuple(FoodSectionsContent(entries)))

    @rt("/add_food/{food_id}")
    def post(request: Request, food_id: int, intake_event_id: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        
        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return HTMLResponse("No users", status_code=400)

            event_id = None
            if intake_event_id and intake_event_id.isdigit() and int(intake_event_id) != 0:
                event_id = int(intake_event_id)
            else:
                event_id = add_intake_event(
                    connection,
                    users_id=user_id,
                    state="planned",
                )

            catalog_item = get_catalog_item(connection, food_id)
            portion_amount = 100
            if catalog_item and catalog_item.get("default_portion"):
                portion_amount = catalog_item["default_portion"]

            portion_id = None
            if event_id:
                event_data = get_intake_event(connection, event_id)
                offset_minutes = 0
                if event_data and event_data.get("meal_time"):
                    delta = datetime.now() - event_data["meal_time"]
                    offset_minutes = int(delta.total_seconds() // 60)

                portion_id = add_portion_detail(
                    connection,
                    origin="catalog",
                    origin_id=food_id,
                    destination="intake_event",
                    destination_id=event_id,
                    amount_g=portion_amount,
                    macros_quality=True,
                    offset_minutes=offset_minutes,
                )

            headers = {"HX-Trigger": "addSuccess" if portion_id else "addError"}
            return HTMLResponse("", headers=headers)

    @rt("/add_manual_intake/{intake_id}")
    def post(request: Request, intake_id: int, intake_event_id: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return HTMLResponse("No users", status_code=400)

            event_id = None
            if intake_event_id and intake_event_id.isdigit() and int(intake_event_id) != 0:
                event_id = int(intake_event_id)
            else:
                event_id = add_intake_event(connection, users_id=user_id, state="planned")

            intake_item = get_manual_intake(connection, intake_id)
            if not intake_item:
                return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=404)

            portion_amount = float(intake_item.get("amount_g") or 100.0)
            event_data = get_intake_event(connection, event_id)
            offset_minutes = 0
            if event_data and event_data.get("meal_time"):
                delta = datetime.now() - event_data["meal_time"]
                offset_minutes = int(delta.total_seconds() // 60)

            portion_id = add_portion_detail(
                connection,
                origin="manual_intake",
                origin_id=intake_id,
                destination="intake_event",
                destination_id=event_id,
                amount_g=portion_amount,
                macros_quality=True,
                offset_minutes=offset_minutes,
            )
            headers = {"HX-Trigger": "addSuccess" if portion_id else "addError"}
            return HTMLResponse("", headers=headers)

    @rt("/add_recipe/{recipe_id}")
    def post(request: Request, recipe_id: int, intake_event_id: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return HTMLResponse("No users", status_code=400)

            recipe = get_recipe(connection, recipe_id)
            if not recipe:
                return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=404)

            if intake_event_id and intake_event_id.isdigit() and int(intake_event_id) != 0:
                event_id = int(intake_event_id)
            else:
                event_id = add_intake_event(
                    connection,
                    users_id=user_id,
                    state="planned",
                    meal_type=recipe.get("meal_type"),
                    name=recipe.get("name"),
                )

            event_data = get_intake_event(connection, event_id)
            offset_minutes = 0
            if event_data and event_data.get("meal_time"):
                delta = datetime.now() - event_data["meal_time"]
                offset_minutes = int(delta.total_seconds() // 60)

            recipe_portions = get_portion_detail_by_recipe(connection, recipe_id)
            created_ids = []
            for row in recipe_portions:
                if row.get("catalog_id"):
                    created_ids.append(
                        add_portion_detail(
                            connection,
                            origin="catalog",
                            origin_id=int(row["catalog_id"]),
                            destination="intake_event",
                            destination_id=event_id,
                            amount_g=float(row.get("amount_g") or 0.0),
                            cooking=row.get("cooking"),
                            conservation=row.get("conservation"),
                            final_state=row.get("final_state"),
                            macros_quality=True,
                            plate_amount=row.get("plate_amount"),
                            is_cooked_weight=bool(row.get("is_cooked_weight")),
                            offset_minutes=offset_minutes,
                        )
                    )
                elif row.get("manual_intake_id"):
                    created_ids.append(
                        add_portion_detail(
                            connection,
                            origin="manual_intake",
                            origin_id=int(row["manual_intake_id"]),
                            destination="intake_event",
                            destination_id=event_id,
                            amount_g=float(row.get("amount_g") or 0.0),
                            cooking=row.get("cooking"),
                            conservation=row.get("conservation"),
                            final_state=row.get("final_state"),
                            macros_quality=True,
                            plate_amount=row.get("plate_amount"),
                            is_cooked_weight=bool(row.get("is_cooked_weight")),
                            offset_minutes=offset_minutes,
                        )
                    )

            ok = bool(recipe_portions) and all(created_ids)
            headers = {"HX-Trigger": "addSuccess" if ok else "addError"}
            return HTMLResponse("", headers=headers)

    @rt("/food/favorite/{entry_type}/{entry_id}")
    def post(request: Request, entry_type: str, entry_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            current = None
            updated = False
            if entry_type == "catalog":
                current = get_catalog_item(connection, entry_id)
                if current:
                    updated = update_catalog_favorite(connection, entry_id, not bool(current.get("favorite")))
                    current["favorite"] = not bool(current.get("favorite"))
            elif entry_type == "manual_intake":
                current = get_manual_intake(connection, entry_id)
                if current:
                    new_value = not bool(current.get("favorite"))
                    updated = update_manual_intake(connection, entry_id, {"favorite": new_value})
                    current["favorite"] = new_value
            elif entry_type == "recipe":
                current = get_recipe(connection, entry_id)
                if current:
                    new_value = not bool(current.get("favorite"))
                    updated = update_recipe(connection, entry_id, favorite=new_value)
                    current["favorite"] = new_value

            if not current or not updated:
                return HTMLResponse(status_code=400)

            return render_fragment(FavoriteButton(entry_type, entry_id, bool(current.get("favorite"))))

    @rt("/food/edit/catalog/{entry_id}")
    def post(
        request: Request,
        entry_id: int,
        name: str = "",
        brand: str = "",
        category: str = "",
        subtype: str = "",
        initial_state: str = "",
        nutriscore: str = "",
        nova: str = "",
        yuka: str = "",
        default_portion: str = "",
        calories_100g: str = "",
        carbs_100g: str = "",
        sugars_100g: str = "",
        fats_100g: str = "",
        saturated_100g: str = "",
        proteins_100g: str = "",
        fiber_100g: str = "",
        caffeine: str = "",
        alcohol: str = "",
        barcode: str = "",
        cooking_factor: str = "",
        favorite: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        clean_category = (category or "").strip()
        clean_subtype = (subtype or "").strip()
        if not clean_name or not clean_category or not clean_subtype:
            return _error_msg("Name, category and subtype are required.")

        with get_connection() as connection:
            current = get_catalog_item(connection, entry_id)
            if not current:
                return _error_msg("Catalog item not found.")

            existing = get_all_catalog(connection, search=clean_name)
            duplicated = any(
                ((item.get("name") or "").strip().lower() == clean_name.lower()) and int(item.get("id") or 0) != entry_id
                for item in existing
            )
            if duplicated:
                return _error_msg("A catalog item with that name already exists.")

            clean_brand = (brand or "").strip()
            favorite_value = None if (favorite or "").strip() == "" else _to_bool(favorite)
            payload = {
                "name": clean_name,
                "brand": clean_brand or None,
                "category": clean_category,
                "subtype": clean_subtype,
                "initial_state": initial_state.strip() or None,
                "nutriscore": nutriscore.strip() or None,
                "nova": _to_int(nova),
                "yuka": _to_int(yuka),
                "default_portion": _to_float(default_portion),
                "calories_100g": _to_float(calories_100g),
                "carbs_100g": _to_float(carbs_100g),
                "sugars_100g": _to_float(sugars_100g),
                "fats_100g": _to_float(fats_100g),
                "saturated_100g": _to_float(saturated_100g),
                "proteins_100g": _to_float(proteins_100g),
                "fiber_100g": _to_float(fiber_100g),
                "caffeine": _to_float(caffeine),
                "alcohol": _to_float(alcohol),
                "barcode": barcode.strip() or None,
                "cooking_factor": _to_float(cooking_factor),
                "favorite": favorite_value,
            }
            updated = update_catalog_item(connection, entry_id, payload)
            if not updated:
                return _error_msg("Catalog item could not be updated.")
            if clean_brand:
                add_food_brand(connection, clean_brand)
            return HTMLResponse("", headers={"HX-Redirect": f"/food/item/catalog/{entry_id}"})

    @rt("/food/edit/manual/{entry_id}")
    def post(
        request: Request,
        entry_id: int,
        name: str = "",
        description: str = "",
        subtype: str = "",
        source_origin: str = "",
        amount_g: str = "",
        calories_100g: str = "",
        carbs_100g: str = "",
        sugars_100g: str = "",
        fats_100g: str = "",
        saturated_100g: str = "",
        proteins_100g: str = "",
        fiber_100g: str = "",
        caffeine: str = "",
        alcohol: str = "",
        glycemic_index: str = "",
        ig_confidence: str = "",
        favorite: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        clean_subtype = (subtype or "").strip()
        if not clean_name or not clean_subtype or not amount_g:
            return _error_msg("Name, subtype and amount are required.")

        try:
            amount_value = float(amount_g)
            if amount_value <= 0:
                return _error_msg("Amount must be greater than zero.")
        except (TypeError, ValueError):
            return _error_msg("Amount must be numeric.")

        with get_connection() as connection:
            current = get_manual_intake(connection, entry_id)
            if not current:
                return _error_msg("Manual intake not found.")
            user_id = get_default_user_id(connection)
            existing = get_all_manual_intakes(connection, users_id=user_id, search=clean_name)
            duplicated = any(
                ((item.get("name") or "").strip().lower() == clean_name.lower()) and int(item.get("id") or 0) != entry_id
                for item in existing
            )
            if duplicated:
                return _error_msg("A manual intake with that name already exists for this user.")

            payload = {
                "name": clean_name,
                "description": description.strip() or None,
                "subtype": clean_subtype,
                "origin": source_origin.strip() or None,
                "amount_g": amount_value,
                "calories_100g": _to_float(calories_100g),
                "carbs_100g": _to_float(carbs_100g),
                "sugars_100g": _to_float(sugars_100g),
                "fats_100g": _to_float(fats_100g),
                "saturated_100g": _to_float(saturated_100g),
                "proteins_100g": _to_float(proteins_100g),
                "fiber_100g": _to_float(fiber_100g),
                "caffeine": _to_float(caffeine),
                "alcohol": _to_float(alcohol),
                "glycemic_index": glycemic_index.strip() or None,
                "ig_confidence": _to_int(ig_confidence),
                "favorite": (None if (favorite or "").strip() == "" else _to_bool(favorite)),
            }
            updated = update_manual_intake(connection, entry_id, payload)
            if not updated:
                return _error_msg("Manual intake could not be updated.")
            return HTMLResponse("", headers={"HX-Redirect": f"/food/item/manual_intake/{entry_id}"})

    @rt("/food/edit/recipe/{entry_id}")
    def post(
        request: Request,
        entry_id: int,
        name: str = "",
        meal_type: str = "",
        notes: str = "",
        favorite: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        if not clean_name:
            return _error_msg("Recipe name is required.")
        with get_connection() as connection:
            current = get_recipe(connection, entry_id)
            if not current:
                return _error_msg("Recipe not found.")
            updated = update_recipe(
                connection,
                entry_id,
                name=clean_name,
                meal_type=meal_type.strip() or None,
                notes=notes.strip() or None,
                favorite=(None if (favorite or "").strip() == "" else _to_bool(favorite)),
            )
            if not updated:
                return _error_msg("Recipe could not be updated.")
            return HTMLResponse("", headers={"HX-Redirect": f"/food/item/recipe/{entry_id}"})

    @rt("/food/create/catalog")
    def post(
        request: Request,
        name: str = "",
        brand: str = "",
        category: str = "",
        subtype: str = "",
        initial_state: str = "",
        nutriscore: str = "",
        nova: str = "",
        yuka: str = "",
        default_portion: str = "",
        calories_100g: str = "",
        carbs_100g: str = "",
        sugars_100g: str = "",
        fats_100g: str = "",
        saturated_100g: str = "",
        proteins_100g: str = "",
        fiber_100g: str = "",
        caffeine: str = "",
        alcohol: str = "",
        barcode: str = "",
        cooking_factor: str = "",
        favorite: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        clean_category = (category or "").strip()
        clean_subtype = (subtype or "").strip()
        if not clean_name or not clean_category or not clean_subtype:
            return _error_msg("Name, category and subtype are required.")

        with get_connection() as connection:
            existing = get_all_catalog(connection, search=clean_name)
            if any(((item.get("name") or "").strip().lower() == clean_name.lower()) for item in existing):
                return _error_msg("A catalog item with that name already exists.")

            user_id = get_default_user_id(connection)
            clean_brand = (brand or "").strip()
            payload = {
                "created_by": user_id,
                "name": clean_name,
                "brand": clean_brand or None,
                "category": clean_category,
                "subtype": clean_subtype,
                "initial_state": initial_state.strip() or None,
                "nutriscore": nutriscore.strip() or None,
                "nova": _to_int(nova),
                "yuka": _to_int(yuka),
                "default_portion": _to_float(default_portion),
                "calories_100g": _to_float(calories_100g),
                "carbs_100g": _to_float(carbs_100g),
                "sugars_100g": _to_float(sugars_100g),
                "fats_100g": _to_float(fats_100g),
                "saturated_100g": _to_float(saturated_100g),
                "proteins_100g": _to_float(proteins_100g),
                "fiber_100g": _to_float(fiber_100g),
                "caffeine": _to_float(caffeine),
                "alcohol": _to_float(alcohol),
                "barcode": barcode.strip() or None,
                "cooking_factor": _to_float(cooking_factor),
                "favorite": _to_bool(favorite),
            }
            created_id = add_catalog_item(connection, payload)
            if not created_id:
                return _error_msg("Catalog item could not be created. Check required fields and uniqueness constraints.")
            if clean_brand:
                add_food_brand(connection, clean_brand)
            return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/create/manual")
    def post(
        request: Request,
        name: str = "",
        description: str = "",
        subtype: str = "",
        source_origin: str = "",
        amount_g: str = "",
        calories_100g: str = "",
        carbs_100g: str = "",
        sugars_100g: str = "",
        fats_100g: str = "",
        saturated_100g: str = "",
        proteins_100g: str = "",
        fiber_100g: str = "",
        caffeine: str = "",
        alcohol: str = "",
        glycemic_index: str = "",
        ig_confidence: str = "",
        favorite: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        clean_subtype = (subtype or "").strip()
        if not clean_name or not clean_subtype or not amount_g:
            return _error_msg("Name, subtype and amount are required.")

        try:
            amount_value = float(amount_g)
            if amount_value <= 0:
                return _error_msg("Amount must be greater than zero.")
        except (TypeError, ValueError):
            return _error_msg("Amount must be numeric.")

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return _error_msg("No users found.")

            existing = get_all_manual_intakes(connection, users_id=user_id, search=clean_name)
            if any(((item.get("name") or "").strip().lower() == clean_name.lower()) for item in existing):
                return _error_msg("A manual intake with that name already exists for this user.")

            payload = {
                "created_by": user_id,
                "name": clean_name,
                "description": description.strip() or None,
                "subtype": clean_subtype,
                "origin": source_origin.strip() or None,
                "amount_g": amount_value,
                "calories_100g": _to_float(calories_100g),
                "carbs_100g": _to_float(carbs_100g),
                "sugars_100g": _to_float(sugars_100g),
                "fats_100g": _to_float(fats_100g),
                "saturated_100g": _to_float(saturated_100g),
                "proteins_100g": _to_float(proteins_100g),
                "fiber_100g": _to_float(fiber_100g),
                "caffeine": _to_float(caffeine),
                "alcohol": _to_float(alcohol),
                "glycemic_index": glycemic_index.strip() or None,
                "ig_confidence": _to_int(ig_confidence),
                "favorite": _to_bool(favorite),
            }
            created_id = add_manual_intake(connection, payload)
            if not created_id:
                return _error_msg("Manual intake could not be created. Check required fields and constraints.")
            return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/create/recipe")
    def post(
        request: Request,
        name: str = "",
        meal_type: str = "",
        notes: str = "",
        favorite: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        if not clean_name:
            return _error_msg("Recipe name is required.")

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return _error_msg("No users found.")
            created_id = add_recipe(
                connection,
                users_id=user_id,
                name=clean_name,
                meal_type=meal_type.strip() or None,
                notes=notes.strip() or None,
                favorite=_to_bool(favorite),
            )
            if not created_id:
                return _error_msg("Recipe could not be created. Check required fields and constraints.")
            return HTMLResponse("", headers={"HX-Redirect": f"/food/item/recipe/{created_id}"})
    
    @rt("/meal_selector_input")
    def get(request: Request, intake_event_id: str):
        if intake_event_id != "0":
            return render_fragment("")
        
        return render_fragment(Div(
            Input(
                placeholder="Meal name",
                name="meal_name",
                id="meal_name_input_text",
                autofocus="autofocus",
                data_skip_page_loading="true",
                cls="""
                border-[1px] px-2 py-1
                md:text-sm lg:text-sm text-base
                shadow-sm rounded-md focus:outline-none
                border-gray-300 w-full
                """,
                hx_post="/create_named_event",
                hx_trigger="keyup[keyCode==13]",
                hx_target="#meal_name_input",
                hx_swap="none",
                hx_include="this",
                **on_after("add_meal_btn")
            ),
            Button(
                "Add",
                id="add_meal_btn",
                data_skip_page_loading="true",
                cls="""
                border-[1px] px-2 py-1
                md:text-sm lg:text-sm text-xs
                shadow-sm rounded-md cursor-pointer
                border-gray-300 hover:bg-gray-200
                transition-colors duration-300
                """,
                hx_post="/create_named_event",
                hx_target="#meal_name_input",
                hx_swap="none",
                hx_include="#meal_name_input_text",
                **on_after()
            ),
            cls="flex gap-2 w-full"        
            ))

    @rt("/create_named_event")
    def post(request: Request, meal_name: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        
        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return HTMLResponse("No users", status_code=400)

            event_id = add_intake_event(
                connection,
                users_id=user_id,
                state="planned",
                name=meal_name or None,
            )

            headers = {"HX-Trigger": "addSuccess" if event_id else "addError"}
            return HTMLResponse("", headers=headers)
