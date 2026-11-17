"""Recipes: create, edit, delete, and their plates and ingredients (code_conventions.md §11.2.4, measurement_conventions.md §4.7)."""

from fasthtml.common import *
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.ui import render_fragment, render_page
from DayBetes_food.http_errors import app_error_response
from DayBetes_food.config import ASSISTANT_ENABLED
from DayBetes_food.database.queries import (
    create_recipe,
    get_catalog_item,
    get_manual_intake,
    get_recipe,
    get_portion_detail,
    create_recipe_plate,
    delete_recipe_plate,
    get_recipe_plate,
    move_portion_to_recipe_plate,
    swap_recipe_plate_position,
    update_portion_flag,
    update_recipe_plate_name,
    list_viewable_recipe_portions,
    set_user_favorite,
    update_recipe,
    delete_recipe,
    update_portion_amount,
    update_portion_detail_fields,
    delete_portion_detail,
)
from DayBetes_food.domain.constants import (
    CLEAR,
    PathId,
    AmountInputUnit,
    ConservationMethod,
    CookingMethod,
    FoodPhysicalState,
    FoodEntryType,
    PortionOrigin,
    parse_enum,
    parse_optional_id,
)
from DayBetes_food.domain.portion_detail import (
    PortionDetailUpdate,
    amount_to_grams,
    parse_amount_grams,
)
from DayBetes_food.components.food.entry_views import recipe_entry_view
from DayBetes_food.components.food.food_forms import CreateRecipePage
from DayBetes_food.components.food.food_detail import (
    RecipeIngredientPickerPage,
    RecipeSummaryOob,
)
from DayBetes_food.database.connection import get_connection
from DayBetes_food.domain.recipe import RecipeCreate, RecipeUpdate
from DayBetes_food.services.recipe import create_recipe_from_draft, recipe_plates_with_portions
from DayBetes_food.domain.recipe_plate import parse_recipe_plate_name
from DayBetes_food.components.food.recipe_add import RecipeAddForm
from DayBetes_food.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from DayBetes_food.routes.food.helpers import (
    _RECIPE_WITHOUT_INGREDIENTS,
    _add_ingredient,
    _assistant_recipe_draft,
    _editable_recipe,
    _error_msg,
    _parse_recipe_request,
    _parse_strict_bool,
    _parse_typed_amount,
    _recipe_block_response,
    _recipe_draft_form,
    _recipe_ingredient_nodes,
    _recipe_portion,
    _recipe_summary,
)


def setup_recipes_routes(rt):

    @rt("/food/create/recipe/form")
    def get(request: Request, assistant_message: str = "", assistant_tool: str = "", return_to_assistant: str = ""):
        # A recipe draft of the assistant (§8.12, frontend §9.11): only while it exists.
        draft_message_id = parse_optional_id(assistant_message, "draft") if ASSISTANT_ENABLED else None
        if not draft_message_id:
            return render_page(request, CreateRecipePage(), show_cart=False)
        user_id = get_current_user_id()
        if not user_id:
            raise AuthenticationError("Your session has expired.")
        conversation_id = parse_optional_id(return_to_assistant, "conversation")
        with get_connection() as connection:
            draft = _recipe_draft_form(connection, int(user_id), draft_message_id, assistant_tool)
        return render_page(
            request, CreateRecipePage(draft, return_to_assistant=conversation_id), show_cart=False
        )

    @rt("/food/recipe/{recipe_id}/ingredients/form")
    def get(request: Request, recipe_id: PathId, recipe_plate_id: str = ""):
        target_plate_id = parse_optional_id(recipe_plate_id, "plate")
        with get_connection() as connection:
            user_id = get_current_user_id()
            recipe = _editable_recipe(connection, user_id, recipe_id)
            if recipe is None:
                raise NotFoundError("Recipe not found.")
            nodes = _recipe_ingredient_nodes(
                connection, int(user_id), recipe, search="", filter_value="food", page=1, recipe_plate_id=target_plate_id
            )
        return render_page(
            request,
            RecipeIngredientPickerPage(recipe_entry_view(recipe), nodes, target_plate_id),
            show_cart=False,
        )

    @rt("/food/recipe/{recipe_id}/ingredients/list")
    def get(
        request: Request, recipe_id: PathId, search: str = "", filter: str = "food", recipe_plate_id: str = "", page: int = 1
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        if filter not in ("food", "favs"):
            return app_error_response(request, ValidationError, "Unknown filter.")
        try:
            target_plate_id = parse_optional_id(recipe_plate_id, "plate")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        with get_connection() as connection:
            user_id = get_current_user_id()
            recipe = _editable_recipe(connection, user_id, recipe_id)
            if recipe is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            nodes = _recipe_ingredient_nodes(
                connection,
                int(user_id),
                recipe,
                search=(search or "").strip(),
                filter_value=filter,
                page=max(1, page),
                recipe_plate_id=target_plate_id,
            )
        return render_fragment(tuple(nodes))

    @rt("/food/recipe/{recipe_id}/ingredients/add/{entry_type}/{entry_id}")
    def post(request: Request, recipe_id: PathId, entry_type: str, entry_id: PathId, recipe_plate_id: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            target_plate_id = parse_optional_id(recipe_plate_id, "plate")
            origin = PortionOrigin(entry_type)
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        except ValueError:
            # Value outside the closed set of the URL: validation_error (7.7).
            return app_error_response(request, ValidationError, "Unknown ingredient type.")

        with get_connection() as connection:
            user_id = get_current_user_id()
            if _editable_recipe(connection, user_id, recipe_id) is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")

            item = (
                get_catalog_item(connection, int(user_id), entry_id)
                if origin is PortionOrigin.CATALOG
                else get_manual_intake(connection, int(user_id), entry_id)
            )
            if item is None:
                return app_error_response(request, NotFoundError, "Food not found.")
            try:
                with connection.transaction():
                    _add_ingredient(connection, int(user_id), recipe_id, target_plate_id, origin, item)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            except ValidationError:
                return app_error_response(
                    request, ValidationError, "The ingredient amount would exceed 100000 g."
                )

        return HTMLResponse("", headers={"HX-Trigger": "addSuccess"})

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/amount")
    def post(
        request: Request,
        recipe_id: PathId,
        portion_id: PathId,
        amount_value: str = "",
        amount_unit: str = AmountInputUnit.PORTION.value,
    ):
        """Set the amount of a recipe ingredient from value + unit (11, decision 2026-09-22)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            unit = AmountInputUnit((amount_unit or "").strip())
        except ValueError:
            return app_error_response(request, ValidationError, "Unknown amount unit.")
        typed_amount = _parse_typed_amount(amount_value)

        with get_connection() as connection:
            user_id = get_current_user_id()
            if _editable_recipe(connection, user_id, recipe_id) is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            portion = _recipe_portion(connection, int(user_id), recipe_id, portion_id)
            if portion is None:
                return app_error_response(request, NotFoundError, "Ingredient not found.")
            try:
                # Serving read from the food in the database (7.13). With no
                # serving, amount_to_grams rejects the `portion` unit (H15).
                parsed_amount = parse_amount_grams(
                    amount_to_grams(typed_amount, unit, portion.source.unit_g)
                    if typed_amount is not None
                    else None
                )
            except ValidationError:
                return app_error_response(
                    request, ValidationError, "The amount must be greater than 0 g and at most 100000 g."
                )
            update_portion_amount(connection, int(user_id), portion_id, parsed_amount)
            recipe = get_recipe(connection, int(user_id), recipe_id)
            summary = _recipe_summary(
                recipe_entry_view(recipe), list_viewable_recipe_portions(connection, int(user_id), recipe_id)
            )
        return render_fragment((P("Saved", cls="text-green-700"), *RecipeSummaryOob(recipe_id, summary)))

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/advanced")
    def post(
        request: Request,
        recipe_id: PathId,
        portion_id: PathId,
        cooking: str = "",
        final_state: str = "",
        conservation: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            parsed_cooking = parse_enum(CookingMethod, cooking, field="cooking")
            parsed_final_state = parse_enum(FoodPhysicalState, final_state, field="final_state")
            parsed_conservation = parse_enum(ConservationMethod, conservation, field="conservation")
        except ValidationError as error:
            # A control that saves itself has no form to show it in (error_conventions.md §7.1).
            return app_error_response(request, ValidationError, str(error))

        with get_connection() as connection:
            user_id = get_current_user_id()
            if _editable_recipe(connection, user_id, recipe_id) is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            portion = _recipe_portion(connection, int(user_id), recipe_id, portion_id)
            if portion is None:
                return app_error_response(request, NotFoundError, "Ingredient not found.")
            try:
                update_portion_detail_fields(
                    connection,
                    int(user_id),
                    portion_id,
                    PortionDetailUpdate(
                        cooking=(CLEAR if parsed_cooking is None else parsed_cooking),
                        final_state=(CLEAR if parsed_final_state is None else parsed_final_state),
                        conservation=(CLEAR if parsed_conservation is None else parsed_conservation),
                    ),
                )
            except ValidationError as error:
                # A merge over the limit (measurement §4.6.4).
                return app_error_response(request, ValidationError, str(error))

            try:
                get_portion_detail(connection, int(user_id), portion_id)
            except NotFoundError:
                # It merged with another row of the plate (measurement §4.6.4): the row
                # on screen no longer exists, so the whole block is repainted.
                response = _recipe_block_response(connection, int(user_id), recipe_id)
                response.headers["HX-Retarget"] = f"#recipe_ingredients_{recipe_id}"
                response.headers["HX-Reswap"] = "outerHTML"
                return response
        return render_fragment(P("Saved", cls="text-green-700"))

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/delete")
    def post(request: Request, recipe_id: PathId, portion_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_current_user_id()
            if _editable_recipe(connection, user_id, recipe_id) is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            portion = _recipe_portion(connection, int(user_id), recipe_id, portion_id)
            if portion is None:
                return app_error_response(request, NotFoundError, "Ingredient not found.")
            delete_portion_detail(connection, int(user_id), portion_id)
            return _recipe_block_response(connection, int(user_id), recipe_id)

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/cooked")
    def post(request: Request, recipe_id: PathId, portion_id: PathId, is_cooked_weight: str = ""):
        """`Weighed cooked` of an ingredient. It can make it equal to another row of the
        plate, and then they merge (measurement §4.6.4). `Strictly weighted` is set in the
        cart, not here (§4.7)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            marked = _parse_strict_bool(is_cooked_weight)
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        with get_connection() as connection:
            user_id = get_current_user_id()
            if _editable_recipe(connection, user_id, recipe_id) is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            portion = _recipe_portion(connection, int(user_id), recipe_id, portion_id)
            if portion is None:
                return app_error_response(request, NotFoundError, "Ingredient not found.")
            if marked and (portion.origin is not PortionOrigin.CATALOG or portion.source.cooking_factor is None):
                return app_error_response(
                    request, ValidationError, "This food has no cooking factor, so it cannot be weighed cooked."
                )
            try:
                with connection.transaction():
                    update_portion_flag(connection, int(user_id), portion_id, "is_cooked_weight", marked, commit=False)
            except ValidationError as error:
                # A merge over the limit (measurement §4.6.4).
                return app_error_response(request, ValidationError, str(error))
            return _recipe_block_response(connection, int(user_id), recipe_id)

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/plate")
    def post(request: Request, recipe_id: PathId, portion_id: PathId, recipe_plate_id: str = ""):
        """Move an ingredient to another plate of the recipe; same key -> they merge (§4.7)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            target = parse_optional_id(recipe_plate_id, "plate")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        if target is None:
            return app_error_response(request, ValidationError, "Invalid plate.")
        with get_connection() as connection:
            user_id = get_current_user_id()
            if _editable_recipe(connection, user_id, recipe_id) is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            try:
                if _recipe_portion(connection, int(user_id), recipe_id, portion_id) is None:
                    raise NotFoundError("portion_not_found")
                with connection.transaction():
                    move_portion_to_recipe_plate(connection, int(user_id), portion_id, target, commit=False)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Ingredient or plate not found.")
            except ValidationError as error:
                # A merge over the limit (measurement §4.6.4).
                return app_error_response(request, ValidationError, str(error))
            return _recipe_block_response(connection, int(user_id), recipe_id)

    @rt("/food/recipe/{recipe_id}/plate")
    def post(request: Request, recipe_id: PathId):
        """A new empty plate at the end. Repeating it adds another (§9.6)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        with get_connection() as connection:
            user_id = get_current_user_id()
            if _editable_recipe(connection, user_id, recipe_id) is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            with connection.transaction():
                create_recipe_plate(connection, int(user_id), recipe_id, commit=False)
            return _recipe_block_response(connection, int(user_id), recipe_id)

    def _change_recipe_plate(request: Request, plate_id: int, change):
        """Common contract of the actions on a plate: owner only, repaints the block."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            try:
                recipe_id = get_recipe_plate(connection, int(user_id), plate_id).recipe_id
                with connection.transaction():
                    change(connection, int(user_id))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Plate not found.")
            except ConflictError as error:
                return app_error_response(request, error, str(error))
            return _recipe_block_response(connection, int(user_id), recipe_id)

    @rt("/food/recipe/plate/{plate_id}/name")
    def post(request: Request, plate_id: PathId, name: str = ""):
        """Empty returns the plate to its derived name (measurement §4.6.3)."""
        try:
            parsed = parse_recipe_plate_name(name)
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        return _change_recipe_plate(
            request,
            plate_id,
            lambda connection, user_id: update_recipe_plate_name(connection, user_id, plate_id, parsed, commit=False),
        )

    @rt("/food/recipe/plate/{plate_id}/up")
    def post(request: Request, plate_id: PathId):
        return _change_recipe_plate(
            request,
            plate_id,
            lambda connection, user_id: swap_recipe_plate_position(connection, user_id, plate_id, up=True, commit=False),
        )

    @rt("/food/recipe/plate/{plate_id}/down")
    def post(request: Request, plate_id: PathId):
        return _change_recipe_plate(
            request,
            plate_id,
            lambda connection, user_id: swap_recipe_plate_position(connection, user_id, plate_id, up=False, commit=False),
        )

    @rt("/food/recipe/plate/{plate_id}/delete")
    def post(request: Request, plate_id: PathId):
        """With ingredients it answers 409 (measurement §4.7)."""
        return _change_recipe_plate(
            request,
            plate_id,
            lambda connection, user_id: delete_recipe_plate(connection, user_id, plate_id, commit=False),
        )

    @rt("/food/recipe/{recipe_id}/add/form")
    def get(request: Request, recipe_id: PathId, intake_event_id: str = "", plate_id: str = ""):
        """The step before adding a recipe to a meal (frontend §9.7)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            recipe = get_recipe(connection, int(user_id), recipe_id)
            if recipe is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            groups = recipe_plates_with_portions(connection, int(user_id), recipe_id)
        if not groups:
            return app_error_response(request, ConflictError, _RECIPE_WITHOUT_INGREDIENTS)
        return render_fragment(RecipeAddForm(recipe, groups, intake_event_id, plate_id))

    @rt("/food/delete/recipe/{recipe_id}")
    def post(request: Request, recipe_id: PathId):
        """Physical delete of a recipe. `catalog` and `manual_intake` are
        archived, never deleted (`/food/archive/...`, §11.2)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")

        with get_connection() as connection:
            current = get_recipe(connection, int(user_id), recipe_id)
            if current is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            if not current.can_edit:
                return app_error_response(request, AuthorizationError, "Only the owner can delete this item.")
            try:
                delete_recipe(connection, int(user_id), recipe_id)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/edit/recipe/{recipe_id}")
    def post(
        request: Request,
        recipe_id: PathId,
        name: str = "",
        meal_type: str = "",
        extra_meal_types: list[str] | None = None,
        notes: str = "",
        servings: str = "",
    ):
        """Full replacement (§3.4): an empty optional field is stored as NULL. There
        is no way to publish from here until phase 2 (§11.4.1)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            req = _parse_recipe_request(
                name=name,
                meal_type=meal_type,
                extra_meal_types=extra_meal_types,
                notes=notes,
                servings=servings,
            )
        except ValidationError as error:
            # Form validation: 200 + fragment inside the form (§9.5).
            return _error_msg(str(error))
        with get_connection() as connection:
            current = get_recipe(connection, int(user_id), recipe_id)
            if current is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            if not current.can_edit:
                return app_error_response(request, AuthorizationError, "Only the owner can edit this recipe.")
            try:
                with connection.transaction():
                    update_recipe(
                        connection,
                        int(user_id),
                        recipe_id,
                        RecipeUpdate(
                            name=req.name,
                            meal_type=req.meal_type,
                            extra_meal_types=req.extra_meal_types,
                            notes=req.notes,
                            servings=req.servings,
                        ),
                        commit=False,
                    )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            except ConflictError as error:
                return app_error_response(request, error, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/item/recipe/{recipe_id}"})

    @rt("/food/create/recipe")
    def post(
        request: Request,
        name: str = "",
        meal_type: str = "",
        extra_meal_types: list[str] | None = None,
        notes: str = "",
        servings: str = "",
        favorite: str = "",
        assistant_message: str = "",
        assistant_tool: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            req = _parse_recipe_request(
                name=name,
                meal_type=meal_type,
                extra_meal_types=extra_meal_types,
                notes=notes,
                servings=servings,
                favorite=favorite,
            )
            draft_message_id = parse_optional_id(assistant_message, "draft") if ASSISTANT_ENABLED else None
        except ValidationError as error:
            return _error_msg(str(error))
        header = RecipeCreate(
            user_id=int(user_id),
            origin_root_id=None,
            name=req.name,
            meal_type=req.meal_type,
            extra_meal_types=req.extra_meal_types,
            notes=req.notes,
            servings=req.servings,
        )
        with get_connection() as connection:
            try:
                if draft_message_id:
                    # The ingredients come from the stored draft, never from the form (§7.13).
                    try:
                        draft = _assistant_recipe_draft(connection, int(user_id), draft_message_id, assistant_tool)
                        created_id = create_recipe_from_draft(
                            connection, int(user_id), draft, header, bool(req.favorite)
                        )
                    except NotFoundError:
                        return _error_msg("An ingredient is no longer available. Ask the assistant again.")
                    except ValidationError as error:
                        return _error_msg(str(error))
                else:
                    with connection.transaction():
                        created_id = create_recipe(connection, header, commit=False)
                        set_user_favorite(
                            connection, int(user_id), FoodEntryType.RECIPE, created_id, bool(req.favorite), commit=False
                        )
            except ConflictError as error:
                return app_error_response(request, error, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/item/recipe/{created_id}"})
