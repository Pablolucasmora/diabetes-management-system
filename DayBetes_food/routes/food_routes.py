from fasthtml.common import *
from datetime import datetime
from DayBetes_food.components.food.food_main import food_main
from DayBetes_food.components.ui import render_page
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
    get_default_user_id,
    get_intake_event,
    update_catalog_favorite,
    update_manual_intake,
    update_recipe,
    add_manual_intake,
    add_recipe,
)
from DayBetes_food.components.food.foods import FoodSectionsContent, FavoriteButton, on_after
from DayBetes_food.components.food.foods import CreateCatalogPage, CreateManualPage, CreateRecipePage
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


def _filtered_entries(connection, search: str = "", filter_value: str = "all"):
    user_id = get_default_user_id(connection)
    query = (search or "").strip().lower()

    catalog_items = get_all_catalog(connection, search=search or None)
    manual_items = get_all_manual_intakes(connection, users_id=user_id, search=search or None) if user_id else []
    recipes = get_all_recipes(connection, users_id=user_id) if user_id else []
    if query:
        recipes = [recipe for recipe in recipes if query in (recipe.get("name") or "").lower()]

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


def _success_msg(text: str):
    return P(text, cls="text-xs text-green-700")


def _error_msg(text: str):
    return P(text, cls="text-xs text-red-700")


def setup_food_routes(rt):
    
    @rt("/food")
    def get(request):
        return render_page(request, food_main)

    @rt("/food/create/catalog/form")
    def get(request: Request):
        return render_page(request, lambda _: CreateCatalogPage())

    @rt("/food/create/manual/form")
    def get(request: Request):
        return render_page(request, lambda _: CreateManualPage())

    @rt("/food/create/recipe/form")
    def get(request: Request):
        return render_page(request, lambda _: CreateRecipePage())
    
    @rt("/food/list")
    def get(request: Request, search: str = "", filter: str = "all"):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            entries = _filtered_entries(connection, search=search, filter_value=filter)
        if not entries:
            return H2("No items", cls="text-gray-600")
        return tuple(FoodSectionsContent(entries))

    @rt("/search_food")
    def get(request: Request, search: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        with get_connection() as connection:
            entries = _filtered_entries(connection, search=search, filter_value="all")
        if not entries:
            return H2("No items", cls="text-gray-600")
        return tuple(FoodSectionsContent(entries))

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
                            strictly_weighed=row.get("strictly_weighed"),
                            macros_quality=row.get("macros_quality"),
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
                            strictly_weighed=row.get("strictly_weighed"),
                            macros_quality=row.get("macros_quality"),
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

            return FavoriteButton(entry_type, entry_id, bool(current.get("favorite")))

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
        if not name or not category or not subtype:
            return _error_msg("Name, category and subtype are required.")

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            payload = {
                "created_by": user_id,
                "name": name.strip(),
                "brand": brand.strip() or None,
                "category": category.strip(),
                "subtype": subtype.strip(),
                "initial_state": initial_state.strip() or None,
                "nutriscore": nutriscore.strip() or None,
                "nova": _to_int(nova),
                "yuka": _to_int(yuka),
                "default_portion": _to_int(default_portion),
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
                return _error_msg("Catalog item could not be created.")
            return _success_msg("Catalog item created.")

    @rt("/food/create/manual")
    def post(
        request: Request,
        name: str = "",
        description: str = "",
        subtype: str = "",
        origin: str = "",
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
        if not name or not subtype or not amount_g:
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

            payload = {
                "created_by": user_id,
                "name": name.strip(),
                "description": description.strip() or None,
                "subtype": subtype.strip(),
                "origin": origin.strip() or None,
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
                return _error_msg("Manual intake could not be created.")
            return _success_msg("Manual intake created.")

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
        if not name:
            return _error_msg("Recipe name is required.")

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return _error_msg("No users found.")
            created_id = add_recipe(
                connection,
                users_id=user_id,
                name=name.strip(),
                meal_type=meal_type.strip() or None,
                notes=notes.strip() or None,
                favorite=_to_bool(favorite),
            )
            if not created_id:
                return _error_msg("Recipe could not be created.")
            return _success_msg("Recipe created.")
    
    @rt("/meal_selector_input")
    def get(request: Request, intake_event_id: str):
        if intake_event_id != "0":
            return ""
        
        return Div(
            Input(
                placeholder="Meal name",
                name="meal_name",
                id="meal_name_input_text",
                autofocus=True,
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
            )

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
