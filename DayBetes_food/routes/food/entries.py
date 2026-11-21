"""Foods and dishes of the user (`catalog`, `manual_intake`): create, edit, copy, archive, publish and quick add (code_conventions.md §11.2.2, §11.2.3)."""

from fasthtml.common import *
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.services.plate_selector import plate_selector_options
from DayBetes_food.components.ui import render_page
from DayBetes_food.http_errors import app_error_response, request_id
from DayBetes_food.config import ASSISTANT_ENABLED
from DayBetes_food.domain.assistant import DRAFT_MACROS_SOURCE
from DayBetes_food.services.intake_event import add_quick_add_to_meal, resolve_target_event
from DayBetes_food.database.queries import (
    create_catalog_item,
    get_off_product_by_code,
    get_ciqual_food,
    archive_catalog_item,
    publish_catalog_item,
    unpublish_catalog_item,
    next_catalog_copy_name,
    create_manual_intake,
    archive_manual_intake,
    publish_manual_intake,
    unpublish_manual_intake,
    next_manual_intake_copy_name,
    get_catalog_item,
    get_catalog_item_by_barcode,
    get_manual_intake,
    get_recipe,
    update_catalog_item,
    set_user_favorite,
    update_manual_intake,
    get_food_brand_suggestions,
    get_subtype_suggestions,
    get_manual_origin_suggestions,
    list_planned_intake_events,
)
from DayBetes_food.domain.constants import (
    PathId,
    PrefillSource,
    FoodEntryType,
    PortionOrigin,
    parse_optional_id,
)
from DayBetes_food.domain.nutrition import NutrientValues
from DayBetes_food.domain.catalog import CatalogItemCreate, parse_barcode
from DayBetes_food.domain.manual_intake import ManualIntakeCreate
from DayBetes_food.domain.ciqual_food import parse_ciqual_code
from DayBetes_food.integrations.ciqual import prefill_from_ciqual_food, reliability_note
from DayBetes_food.integrations.open_food_facts import (
    fetch_product_prefill,
    prefill_from_off_product,
)
from DayBetes_food.components.food.entry_views import (
    catalog_entry_view,
    manual_intake_entry_view,
    recipe_entry_view,
)
from DayBetes_food.components.food.food_forms import (
    CreateCatalogPage,
    CreateManualPage,
    EditCatalogPage,
    EditManualPage,
    EditRecipePage,
    QuickAddPage,
)
from DayBetes_food.database.connection import get_connection
from DayBetes_food.domain.constants import AssistantDraftSource
from DayBetes_food.services.recipe import copy_recipe
from DayBetes_food.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from DayBetes_food.routes.food.helpers import (
    _ASSISTANT_DRAFT_NOTES,
    _UNKNOWN_ENTRY_TYPE,
    _add_ingredient,
    _apply_draft_extras,
    _assistant_food_draft,
    _catalog_create,
    _catalog_update,
    _closest_option,
    _editable_recipe,
    _error_msg,
    _manual_draft_prefill,
    _manual_intake_create,
    _manual_intake_update,
    _parse_catalog_item_request,
    _parse_food_entry_type,
    _parse_manual_intake_request,
    _parse_quick_add_request,
    _prefill_view,
    _resolve_catalog_refs,
    _resolve_manual_subtype,
    logger,
)


def setup_entries_routes(rt):

    @rt("/food/create/catalog/form")
    def get(
        request: Request,
        barcode: str = "",
        existing_id: str = "",
        ciqual: str = "",
        add_to_recipe: str = "",
        recipe_plate_id: str = "",
        assistant_message: str = "",
        assistant_tool: str = "",
        return_to_assistant: str = "",
    ):
        clean = (barcode or "").strip()
        target_recipe_id = parse_optional_id(add_to_recipe, "recipe")
        target_plate_id = parse_optional_id(recipe_plate_id, "plate")
        # A draft of the assistant (§8.12, frontend §9.11): only while it exists.
        assistant_conversation_id = (
            parse_optional_id(return_to_assistant, "conversation") if ASSISTANT_ENABLED else None
        )
        food_draft = None
        draft_message_id = parse_optional_id(assistant_message, "draft") if ASSISTANT_ENABLED else None
        if draft_message_id:
            food_draft = _assistant_food_draft(int(get_current_user_id() or 0), draft_message_id, assistant_tool)
            # The draft says where it comes from, not the URL (§7.13).
            ciqual = food_draft.code if food_draft.source is AssistantDraftSource.CIQUAL else ""
            barcode = food_draft.code if food_draft.source is AssistantDraftSource.OPEN_FOOD_FACTS else ""
            clean = barcode
        label_prefill = food_draft.prefill if food_draft else None
        ciqual_food = None
        ciqual_code = parse_ciqual_code(ciqual)
        if ciqual_code is not None:
            with get_connection() as connection:
                ciqual_food = get_ciqual_food(connection, ciqual_code)
            if ciqual_food is None:
                raise NotFoundError("Ciqual food not found.")
        try:
            valid_barcode = parse_barcode(clean) if clean else None
            barcode_notice = None
        except ValidationError:
            valid_barcode, barcode_notice = None, "Invalid barcode: it must contain only digits (8 to 48)."
        prefill, off_notice, prefill_source_id = None, None, None
        local_product = None
        if valid_barcode:
            with get_connection() as connection:
                local_product = get_off_product_by_code(connection, valid_barcode)
        if local_product:
            prefill = prefill_from_off_product(valid_barcode, local_product)
            prefill_source_id = local_product.code
        elif valid_barcode:
            # Not in the local copy, which has a date and a scope: the API may
            # still know it (measurement §12.2).
            try:
                prefill = fetch_product_prefill(valid_barcode)
                prefill_source_id = valid_barcode
            except ExternalServiceError as error:
                # str(error) is the adapter's internal reason (off_network_error,
                # off_status...), never user data (error_conventions.md §10.3).
                logger.warning(
                    "Open Food Facts lookup failed",
                    exc_info=error,
                    extra={
                        "error_code": error.code,
                        "reason": str(error),
                        "request_id": request_id(request),
                    },
                )
                off_notice = "Product data could not be loaded. You can fill the form by hand."
        existing_item_id = parse_optional_id(existing_id, "food")
        user_id = get_current_user_id()
        # A barcode the assistant read on a label: only to warn of a food that has it.
        check_barcode = valid_barcode or (label_prefill.barcode if label_prefill else None)
        with get_connection() as connection:
            if check_barcode and not existing_item_id and user_id:
                existing = get_catalog_item_by_barcode(connection, int(user_id), check_barcode)
                existing_item_id = existing.id if existing else None
            # Autocomplete only; validation is SQL (F4.1).
            brands = get_food_brand_suggestions(connection, search="", limit=500)
            subtypes = get_subtype_suggestions(connection, search="", limit=500)
        if valid_barcode and prefill is None and off_notice is None and not existing_item_id:
            off_notice = "Product not found. You can fill the form by hand."
        prefill_view = _prefill_view(prefill, valid_barcode, prefill_source_id) if prefill else {"barcode": clean}
        if ciqual_food:
            prefill = prefill_from_ciqual_food(ciqual_food)
            prefill_view = _prefill_view(prefill, "", str(ciqual_food.code), PrefillSource.CIQUAL)
        elif label_prefill:
            # Written by the assistant and reviewed here: its U1 is the draft's (study §6.3).
            prefill = label_prefill
            prefill_view = _prefill_view(
                prefill, prefill.barcode or "", "", None, DRAFT_MACROS_SOURCE[food_draft.source]
            )
        if food_draft:
            _apply_draft_extras(prefill_view, food_draft.extras)
        subtype_prefill = (prefill_view.get("subtype") or "").strip()
        if subtype_prefill:
            prefill_view["subtype"] = _closest_option(subtype_prefill, subtypes)
            # A value the prefill brought counts as added: the user reviews it
            # before saving, and without this the form rejects it (measurement §12.2).
            prefill_view["subtype_is_new"] = prefill_view["subtype"] not in subtypes
        brand_prefill = (prefill_view.get("brand") or "").strip()
        if brand_prefill:
            prefill_view["brand"] = _closest_option(brand_prefill, brands)
            prefill_view["brand_is_new"] = prefill_view["brand"] not in brands
        return render_page(
            request,
            CreateCatalogPage(
                brand_options=brands,
                subtype_options=subtypes,
                prefill=prefill_view,
                existing_item_id=existing_item_id,
                off_notice=off_notice,
                barcode_notice=barcode_notice,
                alcohol_source_note=prefill.alcohol_source_note if prefill else None,
                off_prefill_barcode=valid_barcode if prefill and not ciqual_food else None,
                ciqual_note=reliability_note(ciqual_food) if ciqual_food else None,
                add_to_recipe=(target_recipe_id, target_plate_id) if target_recipe_id else None,
                return_to_assistant=assistant_conversation_id,
                assistant_note=_ASSISTANT_DRAFT_NOTES.get(food_draft.source) if food_draft else None,
                # Its own browser draft, so the form does not bring back what was
                # typed in another create form (frontend §9.11).
                draft_key=f"assistant_{draft_message_id}_{assistant_tool}" if food_draft else None,
            ),
            show_cart=False,
        )

    @rt("/food/create/manual_intake/form")
    def get(request: Request, assistant_message: str = "", assistant_tool: str = "", return_to_assistant: str = ""):
        user_id = get_current_user_id()
        if not user_id:
            raise AuthenticationError("Your session has expired.")
        # A dish draft of the assistant (§8.12, frontend §9.11): only while it exists.
        draft_message_id = parse_optional_id(assistant_message, "draft") if ASSISTANT_ENABLED else None
        conversation_id = parse_optional_id(return_to_assistant, "conversation") if draft_message_id else None
        with get_connection() as connection:
            prefill = (
                _manual_draft_prefill(connection, int(user_id), draft_message_id, assistant_tool)
                if draft_message_id
                else None
            )
            subtypes = get_subtype_suggestions(connection, search="", limit=500)
            origins = get_manual_origin_suggestions(connection, int(user_id), limit=500)
        if prefill and prefill.get("subtype"):
            prefill["subtype"] = _closest_option(prefill["subtype"], subtypes)
            prefill["subtype_is_new"] = prefill["subtype"] not in subtypes
        return render_page(
            request,
            CreateManualPage(
                subtype_options=subtypes,
                origin_options=origins,
                prefill=prefill,
                return_to_assistant=conversation_id,
                draft_key=f"assistant_{draft_message_id}_{assistant_tool}" if prefill else None,
            ),
            show_cart=False,
        )

    def _copy_catalog_item(request: Request, user_id: int, catalog_id: int):
        with get_connection() as connection:
            source = get_catalog_item(connection, user_id, catalog_id)
            if source is None:
                return app_error_response(request, NotFoundError, "Food not found.")
            name = next_catalog_copy_name(connection, user_id, source.name, source.brand_id)
            root = source.origin_root_id or source.id
            try:
                with connection.transaction():
                    created_id = create_catalog_item(
                        connection,
                        CatalogItemCreate(
                            created_by=user_id,
                            origin_root_id=root,
                            name=name,
                            brand_id=source.brand_id,
                            category=source.category,
                            subtype=source.subtype,
                            initial_state=source.initial_state,
                            nutriscore=source.nutriscore,
                            nova=source.nova,
                            yuka=source.yuka,
                            default_portion=source.default_portion,
                            nutrients=NutrientValues(
                                calories_100g=source.calories_100g,
                                carbs_100g=source.carbs_100g,
                                sugars_100g=source.sugars_100g,
                                fats_100g=source.fats_100g,
                                saturated_100g=source.saturated_100g,
                                proteins_100g=source.proteins_100g,
                                fiber_100g=source.fiber_100g,
                                caffeine=source.caffeine,
                                alcohol=source.alcohol,
                            ),
                            barcode=source.barcode,
                            cooking_factor=source.cooking_factor,
                            macros_source=source.macros_source,
                            default_amount_method=source.default_amount_method,
                            serving_method=source.serving_method,
                            macros_confidence=source.macros_confidence,
                        ),
                        commit=False,
                    )
                    set_user_favorite(connection, user_id, FoodEntryType.CATALOG, int(created_id), True, commit=False)
            except ConflictError as error:
                return app_error_response(request, ConflictError, str(error))
            except ValidationError as error:
                return app_error_response(request, error, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/edit/catalog/{created_id}/form"})

    def _copy_manual_intake(request: Request, user_id: int, manual_intake_id: int):
        """Editable copy of a visible dish (H16, §11.2.3): a new personal row in
        the family of the original, with every field copied. The owner can
        copy their own dish too (decision 2026-10-27)."""
        with get_connection() as connection:
            source = get_manual_intake(connection, user_id, manual_intake_id)
            if source is None:
                return app_error_response(request, NotFoundError, "Dish not found.")
            name = next_manual_intake_copy_name(connection, user_id, source.name, source.origin)
            root = source.origin_root_id or source.id
            try:
                with connection.transaction():
                    created_id = create_manual_intake(
                        connection,
                        ManualIntakeCreate(
                            created_by=user_id,
                            origin_root_id=root,
                            name=name,
                            description=source.description,
                            subtype=source.subtype,
                            origin=source.origin,
                            default_portion=source.default_portion,
                            nutrients=NutrientValues(
                                calories_100g=source.calories_100g,
                                carbs_100g=source.carbs_100g,
                                sugars_100g=source.sugars_100g,
                                fats_100g=source.fats_100g,
                                saturated_100g=source.saturated_100g,
                                proteins_100g=source.proteins_100g,
                                fiber_100g=source.fiber_100g,
                                caffeine=source.caffeine,
                                alcohol=source.alcohol,
                            ),
                            glycemic_index=source.glycemic_index,
                            ig_confidence=source.ig_confidence,
                            macros_confidence=source.macros_confidence,
                            macros_source=source.macros_source,
                            default_amount_method=source.default_amount_method,
                            serving_method=source.serving_method,
                        ),
                        commit=False,
                    )
                    set_user_favorite(connection, user_id, FoodEntryType.MANUAL_INTAKE, int(created_id), True, commit=False)
            except ConflictError as error:
                return app_error_response(request, ConflictError, str(error))
            except ValidationError as error:
                return app_error_response(request, error, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/edit/manual_intake/{created_id}/form"})

    @rt("/food/copy/{entry_type}/{entry_id}")
    def post(request: Request, entry_type: str, entry_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        if kind is FoodEntryType.CATALOG:
            return _copy_catalog_item(request, int(user_id), entry_id)
        if kind is FoodEntryType.MANUAL_INTAKE:
            return _copy_manual_intake(request, int(user_id), entry_id)

        with get_connection() as connection:
            try:
                created_id = copy_recipe(connection, int(user_id), entry_id)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Item not found.")
            except ConflictError as error:
                # uq_recipe_personal_name: only if another request took the copy's
                # name between next_recipe_copy_name and the insert.
                return app_error_response(request, error, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/edit/recipe/{created_id}/form"})

    @rt("/food/edit/{entry_type}/{entry_id}/form")
    def get(request: Request, entry_type: str, entry_id: PathId):
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            raise ValidationError(_UNKNOWN_ENTRY_TYPE, fields={"entry_type": "invalid"})
        with get_connection() as connection:
            user_id = get_current_user_id()
            entry = None
            if kind is FoodEntryType.CATALOG:
                item = get_catalog_item(connection, int(user_id), entry_id) if user_id else None
                if item is None:
                    raise NotFoundError("Food not found.")
                if not item.can_edit:
                    raise AuthorizationError(
                        "Only the owner can edit this food. Create a copy to edit it."
                    )
                brands = get_food_brand_suggestions(connection, search="", limit=500)
                subtypes = get_subtype_suggestions(connection, search="", limit=500)
                return render_page(
                    request,
                    EditCatalogPage(
                        entry=catalog_entry_view(item),
                        brand_options=brands,
                        subtype_options=subtypes,
                    ),
                    show_cart=False,
                )
            if kind is FoodEntryType.MANUAL_INTAKE:
                # None also for another user's personal dish or a quick add (§5.4, §11.2.3).
                manual_item = get_manual_intake(connection, int(user_id), entry_id) if user_id else None
                if manual_item is None:
                    raise NotFoundError("Dish not found.")
                if not manual_item.can_edit:
                    raise AuthorizationError(
                        "Only the owner can edit this dish. Create a copy to edit it."
                    )
                subtypes = get_subtype_suggestions(connection, search="", limit=500)
                origins = get_manual_origin_suggestions(connection, int(user_id), limit=500)
                return render_page(
                    request,
                    EditManualPage(
                        entry=manual_intake_entry_view(manual_item),
                        subtype_options=subtypes,
                        origin_options=origins,
                    ),
                    show_cart=False,
                )
            recipe = get_recipe(connection, int(user_id), entry_id) if user_id else None
            if recipe is None:
                raise NotFoundError("Recipe not found.")
            if not recipe.can_edit:
                raise AuthorizationError("Only the owner can edit this recipe. Create a copy to edit it.")
            entry = recipe_entry_view(recipe)
            return render_page(
                request,
                EditRecipePage(
                    entry=entry,
                ),
                show_cart=False,
            )

    def _archive_catalog_item(request: Request, user_id: int, catalog_id: int):
        with get_connection() as connection:
            try:
                with connection.transaction():
                    # False = already archived: idempotent no-op (§9.6).
                    archive_catalog_item(connection, user_id, catalog_id, commit=False)
                    set_user_favorite(connection, user_id, FoodEntryType.CATALOG, catalog_id, False, commit=False)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Food not found.")
        return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/archive/catalog/{catalog_id}")
    def post(request: Request, catalog_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        return _archive_catalog_item(request, int(user_id), catalog_id)

    @rt("/food/publish/catalog/{catalog_id}")
    def post(request: Request, catalog_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            try:
                publish_catalog_item(connection, int(user_id), catalog_id, commit=True)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Food not found.")
            except ConflictError as error:
                return app_error_response(request, ConflictError, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/item/catalog/{catalog_id}"})

    @rt("/food/unpublish/catalog/{catalog_id}")
    def post(request: Request, catalog_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            try:
                unpublish_catalog_item(connection, int(user_id), catalog_id, commit=True)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Food not found.")
            except ConflictError as error:
                return app_error_response(request, ConflictError, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/item/catalog/{catalog_id}"})

    def _archive_manual_intake(request: Request, user_id: int, manual_intake_id: int):
        """Archive with the catalog contract (§11.2.3): the route owns the
        transaction (§2.3), and the dish leaves the owner's favorites in it."""
        with get_connection() as connection:
            try:
                with connection.transaction():
                    # False = already archived: idempotent no-op (§9.6).
                    archive_manual_intake(connection, user_id, manual_intake_id, commit=False)
                    set_user_favorite(
                        connection, user_id, FoodEntryType.MANUAL_INTAKE, manual_intake_id, False, commit=False
                    )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Dish not found.")
        return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/archive/manual_intake/{manual_intake_id}")
    def post(request: Request, manual_intake_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        return _archive_manual_intake(request, int(user_id), manual_intake_id)

    @rt("/food/publish/manual_intake/{manual_intake_id}")
    def post(request: Request, manual_intake_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            try:
                publish_manual_intake(connection, int(user_id), manual_intake_id, commit=True)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Dish not found.")
            except ConflictError as error:
                return app_error_response(request, ConflictError, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/item/manual_intake/{manual_intake_id}"})

    @rt("/food/unpublish/manual_intake/{manual_intake_id}")
    def post(request: Request, manual_intake_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            try:
                unpublish_manual_intake(connection, int(user_id), manual_intake_id, commit=True)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Dish not found.")
            except ConflictError as error:
                return app_error_response(request, ConflictError, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/item/manual_intake/{manual_intake_id}"})

    @rt("/food/edit/catalog/{entry_id}")
    def post(
        request: Request,
        entry_id: PathId,
        name: str = "",
        brand: str = "",
        brand__added: str = "",
        category: str = "",
        subtype: str = "",
        subtype__added: str = "",
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
        macros_source: str = "",
        default_amount_method: str = "",
        serving_method: str = "",
        macros_confidence: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            req = _parse_catalog_item_request(
                nutrients_source="fields",
                name=name,
                brand=brand,
                brand__added=brand__added,
                category=category,
                subtype=subtype,
                subtype__added=subtype__added,
                initial_state=initial_state,
                nutriscore=nutriscore,
                nova=nova,
                yuka=yuka,
                default_portion=default_portion,
                caffeine=caffeine,
                alcohol=alcohol,
                barcode=barcode,
                cooking_factor=cooking_factor,
                macros_source=macros_source,
                default_amount_method=default_amount_method,
                serving_method=serving_method,
                macros_confidence=macros_confidence,
                calories_100g=calories_100g,
                carbs_100g=carbs_100g,
                sugars_100g=sugars_100g,
                fats_100g=fats_100g,
                saturated_100g=saturated_100g,
                proteins_100g=proteins_100g,
                fiber_100g=fiber_100g,
            )
        except ValidationError as error:
            return _error_msg(str(error))

        with get_connection() as connection:
            try:
                with connection.transaction():
                    brand_id, subtype = _resolve_catalog_refs(connection, int(user_id), req)
                    update_catalog_item(
                        connection,
                        int(user_id),
                        entry_id,
                        _catalog_update(req, brand_id, subtype),
                        commit=False,
                    )
            except ValidationError as error:
                return _error_msg(str(error))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Food not found or no longer editable.")
            except ConflictError as error:
                return app_error_response(request, error, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/item/catalog/{entry_id}"})

    @rt("/food/edit/manual_intake/{manual_intake_id}")
    def post(
        request: Request,
        manual_intake_id: PathId,
        name: str = "",
        description: str = "",
        subtype: str = "",
        subtype__added: str = "",
        source_origin: str = "",
        default_portion: str = "",
        nutrient_mode: str = "",
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
        macros_confidence: str = "",
        macros_source: str = "",
        default_amount_method: str = "",
        serving_method: str = "",
    ):
        """Full replacement of a reusable dish (H1): an empty optional field is
        stored as NULL. Publishing is the detail page's action, not a field here."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            req = _parse_manual_intake_request(
                name=name,
                description=description,
                subtype=subtype,
                subtype__added=subtype__added,
                origin=source_origin,
                default_portion=default_portion,
                nutrient_mode=nutrient_mode,
                glycemic_index=glycemic_index,
                ig_confidence=ig_confidence,
                macros_confidence=macros_confidence,
                macros_source=macros_source,
                default_amount_method=default_amount_method,
                serving_method=serving_method,
                calories_100g=calories_100g,
                carbs_100g=carbs_100g,
                sugars_100g=sugars_100g,
                fats_100g=fats_100g,
                saturated_100g=saturated_100g,
                proteins_100g=proteins_100g,
                fiber_100g=fiber_100g,
                caffeine=caffeine,
                alcohol=alcohol,
            )
        except ValidationError as error:
            return _error_msg(str(error))

        with get_connection() as connection:
            try:
                with connection.transaction():
                    subtype_value = _resolve_manual_subtype(connection, req)
                    update_manual_intake(
                        connection,
                        int(user_id),
                        manual_intake_id,
                        _manual_intake_update(req, subtype_value),
                        commit=False,
                    )
            except ValidationError as error:
                return _error_msg(str(error))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Dish not found or no longer editable.")
            except ConflictError as error:
                return app_error_response(request, error, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/item/manual_intake/{manual_intake_id}"})

    @rt("/food/create/catalog")
    def post(
        request: Request,
        name: str = "",
        brand: str = "",
        brand__added: str = "",
        category: str = "",
        subtype: str = "",
        subtype__added: str = "",
        initial_state: str = "",
        nutriscore: str = "",
        nova: str = "",
        yuka: str = "",
        default_portion: str = "",
        caffeine: str = "",
        alcohol: str = "",
        barcode: str = "",
        cooking_factor: str = "",
        macros_source: str = "",
        default_amount_method: str = "",
        serving_method: str = "",
        macros_confidence: str = "",
        favorite: str = "",
        catalog_smart_macros_raw: str = "",
        prefill_source: str = "",
        prefill_source_id: str = "",
        add_to_recipe: str = "",
        add_to_recipe_plate: str = "",
        return_to_assistant: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            req = _parse_catalog_item_request(
                nutrients_source="smart",
                name=name,
                brand=brand,
                brand__added=brand__added,
                category=category,
                subtype=subtype,
                subtype__added=subtype__added,
                initial_state=initial_state,
                nutriscore=nutriscore,
                nova=nova,
                yuka=yuka,
                default_portion=default_portion,
                caffeine=caffeine,
                alcohol=alcohol,
                barcode=barcode,
                cooking_factor=cooking_factor,
                macros_source=macros_source,
                default_amount_method=default_amount_method,
                serving_method=serving_method,
                macros_confidence=macros_confidence,
                favorite=favorite,
                smart_raw=catalog_smart_macros_raw,
                prefill_source=prefill_source,
                prefill_source_id=prefill_source_id,
            )
            target_recipe_id = parse_optional_id(add_to_recipe, "recipe")
            target_plate_id = parse_optional_id(add_to_recipe_plate, "plate")
            assistant_conversation_id = (
                parse_optional_id(return_to_assistant, "conversation") if ASSISTANT_ENABLED else None
            )
        except ValidationError as error:
            return _error_msg(str(error))

        with get_connection() as connection:
            try:
                with connection.transaction():
                    brand_id, subtype = _resolve_catalog_refs(connection, int(user_id), req)
                    created_id = create_catalog_item(
                        connection,
                        _catalog_create(req, int(user_id), brand_id, subtype),
                        commit=False,
                    )
                    # The food is born personal (R5). The favorite is user data.
                    set_user_favorite(
                        connection, int(user_id), FoodEntryType.CATALOG, created_id, bool(req.favorite), commit=False
                    )
                    if target_recipe_id is not None:
                        # Chosen from a recipe's ingredient search (frontend §9.7).
                        if _editable_recipe(connection, user_id, target_recipe_id) is None:
                            raise NotFoundError("Recipe not found.")
                        _add_ingredient(
                            connection,
                            int(user_id),
                            target_recipe_id,
                            target_plate_id,
                            PortionOrigin.CATALOG,
                            get_catalog_item(connection, int(user_id), created_id),
                        )
            except ValidationError as error:
                return _error_msg(str(error))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            except ConflictError as error:
                return app_error_response(request, error, str(error))
        if target_recipe_id is not None:
            query = f"?recipe_plate_id={target_plate_id}" if target_plate_id else ""
            return HTMLResponse(
                "", headers={"HX-Redirect": f"/food/recipe/{target_recipe_id}/ingredients/form{query}"}
            )
        if assistant_conversation_id:
            # Back to the conversation that drafted it (frontend §9.11).
            return HTMLResponse(
                "", headers={"HX-Redirect": f"/assistant?conversation_id={assistant_conversation_id}"}
            )
        return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/create/manual_intake")
    def post(
        request: Request,
        name: str = "",
        description: str = "",
        subtype: str = "",
        subtype__added: str = "",
        source_origin: str = "",
        default_portion: str = "",
        nutrient_mode: str = "",
        caffeine: str = "",
        alcohol: str = "",
        glycemic_index: str = "",
        ig_confidence: str = "",
        macros_confidence: str = "",
        macros_source: str = "",
        default_amount_method: str = "",
        serving_method: str = "",
        favorite: str = "",
        manual_smart_macros_raw: str = "",
        return_to_assistant: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            # Server-side smart macros; the hidden fields are ignored (§7.13).
            req = _parse_manual_intake_request(
                name=name,
                description=description,
                subtype=subtype,
                subtype__added=subtype__added,
                origin=source_origin,
                default_portion=default_portion,
                nutrient_mode=nutrient_mode,
                glycemic_index=glycemic_index,
                ig_confidence=ig_confidence,
                macros_confidence=macros_confidence,
                macros_source=macros_source,
                default_amount_method=default_amount_method,
                serving_method=serving_method,
                favorite=favorite,
                smart_raw=manual_smart_macros_raw,
                caffeine=caffeine,
                alcohol=alcohol,
            )
            assistant_conversation_id = (
                parse_optional_id(return_to_assistant, "conversation") if ASSISTANT_ENABLED else None
            )
        except ValidationError as error:
            return _error_msg(str(error))

        with get_connection() as connection:
            try:
                with connection.transaction():
                    subtype_value = _resolve_manual_subtype(connection, req)
                    created_id = create_manual_intake(
                        connection,
                        _manual_intake_create(req, int(user_id), subtype_value),
                        commit=False,
                    )
                    # The dish is born personal (§11.4.1). The favorite is user data.
                    set_user_favorite(
                        connection, int(user_id), FoodEntryType.MANUAL_INTAKE, created_id, bool(req.favorite), commit=False
                    )
            except ValidationError as error:
                return _error_msg(str(error))
            except ConflictError as error:
                return app_error_response(request, error, str(error))
        if assistant_conversation_id:
            # Back to the conversation that drafted it (frontend §9.11).
            return HTMLResponse(
                "", headers={"HX-Redirect": f"/assistant?conversation_id={assistant_conversation_id}"}
            )
        return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/quick_add/form")
    def get(request: Request):
        """Quick add (§11.2.3): meal and plate selector on top, then name,
        estimated weight, total smart macros and notes."""
        user_id = get_current_user_id()
        if not user_id:
            raise AuthenticationError("Your session has expired.")
        with get_connection() as connection:
            events = list_planned_intake_events(connection, int(user_id))
            plate_options, selected_plate_id = (
                plate_selector_options(connection, int(user_id), events[0].id) if events else ([], None)
            )
        return render_page(
            request,
            QuickAddPage(events, plate_options, selected_plate_id),
            show_cart=False,
        )

    @rt("/food/quick_add")
    def post(
        request: Request,
        name: str = "",
        default_portion: str = "",
        quick_smart_macros_raw: str = "",
        description: str = "",
        macros_source: str = "",
        amount_method: str = "",
        intake_event_id: str = "",
        plate_id: str = "",
    ):
        """Create the quick-add row and its portion in one transaction (§11.2.3).

        Repeating the submit creates another quick add and another portion:
        each submit is a new row, never merged with the previous one (§9.6).
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            req = _parse_quick_add_request(
                name=name,
                weight_g=default_portion,
                smart_raw=quick_smart_macros_raw,
                notes=description,
                macros_source=macros_source,
                amount_method=amount_method,
            )
        except ValidationError as error:
            return _error_msg(str(error))

        with get_connection() as connection:
            try:
                with connection.transaction():  # row + portion, all or nothing (§2.3)
                    event_id, _ = resolve_target_event(connection, int(user_id), parse_optional_id(intake_event_id, "meal"))
                    add_quick_add_to_meal(
                        connection, int(user_id), req, event_id, parse_optional_id(plate_id, "plate")
                    )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That meal no longer exists.")
            except ConflictError:
                return app_error_response(request, ConflictError, "That meal has already been confirmed.")
            except ValidationError as error:
                return app_error_response(request, ValidationError, str(error))
        # Same pattern as "Log food" (§9.5).
        return HTMLResponse("", headers={"HX-Redirect": "/food"})
