"""Browsing Food: the page, its list, the detail of an entry, its actions, tags and favorite, and the meal and plate selectors (frontend_conventions.md §9.3, §9.4)."""

from fasthtml.common import *
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.food.food_main import food_main
from DayBetes_food.services.plate_selector import plate_selector_options
from DayBetes_food.components.ui import render_fragment, render_page
from DayBetes_food.http_errors import app_error_response
from DayBetes_food.services.fridge import list_fridge_items
from DayBetes_food.services.intake_event import default_meal_type_now, preparation_suggestions
from DayBetes_food.domain.portion_detail import PREPARATION_TO_CONFIRM_FIELDS, PreparationFood
from DayBetes_food.database.queries import (
    list_recipes,
    get_catalog_item,
    get_manual_intake,
    get_recipe,
    list_recipe_plates,
    list_viewable_recipe_portions,
    get_user_favorite_access,
    set_user_favorite,
    set_entry_tag,
    create_intake_event,
    get_planned_intake_event,
    list_planned_intake_events,
    count_needs_review,
    search_menu_items,
    list_needs_review,
)
from DayBetes_food.components.food.menus import FoodMenuResults
from DayBetes_food.domain.constants import PathId, PortionOrigin, PrefillSource, FoodEntryType, parse_optional_id
from DayBetes_food.domain.menu import MENU_FOOD_SEARCH_ROWS
from DayBetes_food.components.data_sources import ciqual_attribution, off_attribution
from DayBetes_food.components.food.food_widgets import on_after
from DayBetes_food.components.food.food_list import (
    FoodView,
    FoodSectionsContent,
    FoodCard,
    FavoriteButton,
    ReviewListContent,
)
from DayBetes_food.components.food.food_actions import (
    FOOD_ACTIONS_BODY_ID,
    FoodActionsStore,
    FoodActionsCopyConfirm,
    FoodActionsFavoriteConfirm,
    FoodActionsMenu,
    FoodActionsRecipes,
    FoodActionsRecipePlates,
    food_card_id,
)
from DayBetes_food.components.food.fridge import FridgeListContent
from DayBetes_food.components.food.entry_views import (
    catalog_entry_view,
    manual_intake_entry_view,
    recipe_entry_view,
)
from DayBetes_food.components.food.food_list import (
    ExternalFoodSection,
    PlateSelector,
)
from DayBetes_food.components.food.food_detail import FoodDetailPage
from DayBetes_food.database.connection import get_connection
from DayBetes_food.domain.constants import IntakeEventState
from DayBetes_food.domain.tag import parse_tag_name
from DayBetes_food.domain.intake_event import INTAKE_EVENT_NAME_MAX_LENGTH, IntakeEventCreate
from DayBetes_food.domain.intake_plate import derive_plate_name
from DayBetes_food.domain.recipe import parse_recipe_meal_types
from DayBetes_food.time_utils import utc_now
from DayBetes_food.errors import AuthenticationError, ConflictError, NotFoundError, ValidationError
from DayBetes_food.routes.food.helpers import (
    LIST_PAGE_SIZE,
    SEARCH_PAGE_SIZE,
    _FAVORITE_MESSAGES,
    _UNKNOWN_ENTRY_TYPE,
    _catalog_detail_summary,
    _community_entries,
    _community_sections_content,
    _editable_recipe,
    _entry_tags_block,
    _external_page,
    _filtered_entries,
    _food_entry_summary,
    _food_view,
    _manual_intake_detail_summary,
    _parse_food_entry_type,
    _parse_strict_bool,
    _recipe_query,
    _recipe_summary,
    _recipes_entries,
    _recommended_entries,
    _search_load_more_node,
    _tag_id_for_name,
)


def _detail_preparation(connection, user_id, food: PreparationFood) -> dict[str, tuple[str, ...]]:
    """The values offered for the preparation to confirm of a food page
    (frontend_conventions.md §9.4); none without a session."""
    if not user_id:
        return {}
    return preparation_suggestions(connection, int(user_id), [food], PREPARATION_TO_CONFIRM_FIELDS).get(
        (food.origin, food.origin_id), {}
    )


def _food_list_content(connection, view: FoodView, recipe_meal_types, *, search: str = "", page: int = 1) -> tuple:
    """One page of the list of Food as `view` shows it: the first one comes inside
    the page, the rest from /food/list (frontend_conventions.md §9.3).

    Raises:
        AuthenticationError: the review and fridge lists need a session.
    """
    clean_search = (search or "").strip()
    page = max(1, int(page or 1))
    food_mode_norm = (view.food_mode or "catalog").strip().lower()
    if food_mode_norm not in ("catalog", "manual"):
        food_mode_norm = "catalog"
    if view.filter == "review":
        # The provisional foods and dishes, without search or pages (§9.3).
        user_id = get_current_user_id()
        if not user_id:
            raise AuthenticationError("Your session has expired.")
        return (ReviewListContent(list_needs_review(connection, int(user_id))),)
    if view.filter == "fridge":
        # The user's containers, without search or pages: there are never
        # many (frontend_conventions.md §9.8).
        user_id = get_current_user_id()
        if not user_id:
            raise AuthenticationError("Your session has expired.")
        return tuple(FridgeListContent(list_fridge_items(connection, int(user_id)), utc_now()))
    favs_mode_norm = (view.favs_mode or "catalog").strip().lower()
    if favs_mode_norm not in ("catalog", "manual", "recipes"):
        favs_mode_norm = "catalog"
    recipes_mode_norm = (view.recipes_mode or "mine").strip().lower()
    if recipes_mode_norm not in ("mine", "discover"):
        recipes_mode_norm = "mine"
    if view.filter == "all":
        mode = (view.search_mode or "recommended").strip().lower()
        if mode == "global":
            entries = _community_entries(connection, search=clean_search)
        else:
            mode = "recommended"
            entries = _recommended_entries(connection, search=clean_search, days=60)
    elif view.filter == "recipes":
        mode = (view.search_mode or "recommended").strip().lower()
        entries = _recipes_entries(
            connection, search=clean_search, recipes_mode=recipes_mode_norm, meal_types=recipe_meal_types
        )
    else:
        mode = (view.search_mode or "recommended").strip().lower()
        selected_entry_type = None
        if view.filter == "food":
            selected_entry_type = "catalog" if food_mode_norm == "catalog" else "manual_intake"
        elif view.filter == "favs":
            selected_entry_type = {
                "catalog": "catalog",
                "manual": "manual_intake",
                "recipes": "recipe",
            }[favs_mode_norm]
        entries = _filtered_entries(
            connection,
            search=clean_search,
            filter_value=view.filter,
            entry_type=selected_entry_type,
        )
    # Only with the first page, after its load-more node: the user's next
    # pages replace that node, so they stay above this section (§12.2).
    off_nodes = []
    user_id = get_current_user_id()
    if (
        page == 1
        and clean_search
        and user_id
        and (view.filter == "all" or (view.filter == "food" and food_mode_norm == "catalog"))
    ):
        # The user's menus, after their own results (frontend §9.13): a few
        # rows, the rest in Menus.
        menu_items = (
            search_menu_items(connection, int(user_id), clean_search, None, MENU_FOOD_SEARCH_ROWS + 1)
            if view.filter == "all"
            else []
        )
        off_nodes = [
            *FoodMenuResults(
                menu_items[:MENU_FOOD_SEARCH_ROWS], clean_search, len(menu_items) > MENU_FOOD_SEARCH_ROWS
            ),
            *ExternalFoodSection(
                "From Ciqual",
                *_external_page(connection, int(user_id), PrefillSource.CIQUAL, clean_search, 1),
                ciqual_attribution(),
            ),
            *ExternalFoodSection(
                "From Open Food Facts",
                *_external_page(connection, int(user_id), PrefillSource.OPEN_FOOD_FACTS, clean_search, 1),
                off_attribution(),
            ),
        ]

    if not entries and not off_nodes:
        return (H2("No items", cls="text-gray-600"),)

    page_size = SEARCH_PAGE_SIZE if clean_search else LIST_PAGE_SIZE
    start = (page - 1) * page_size
    end = start + page_size
    chunk = entries[start:end]
    has_more = end < len(entries)

    if page > 1 or (view.filter == "all" and mode == "recommended"):
        nodes = [FoodCard(item) for item in chunk]
    elif view.filter == "all":
        nodes = list(_community_sections_content(chunk))
    else:
        nodes = list(FoodSectionsContent(chunk))
    if has_more:
        nodes.append(
            _search_load_more_node(
                clean_search,
                view.filter,
                mode,
                food_mode_norm,
                favs_mode_norm,
                recipes_mode_norm,
                view.meal_type,
                page + 1,
            )
        )
    return tuple(nodes + off_nodes)


def setup_browse_routes(rt):
    @rt("/food")
    def get(
        request,
        filter: str = "",
        search_mode: str = "",
        food_mode: str = "",
        favs_mode: str = "",
        recipes_mode: str = "",
        meal_type: str = "",
    ):
        """The page opened on the view of its URL (frontend §5): `filter=fridge` is the
        From fridge button of the home page (§9.2), the rest is what Back comes back
        to. An unknown value is a 422 (code_conventions §7.7)."""
        view = _food_view(filter, search_mode, food_mode, favs_mode, recipes_mode, meal_type)
        user_id = get_current_user_id()
        events, plate_options, last_used_plate, review_count, list_content = [], [], None, 0, ()
        if user_id:
            with get_connection() as connection:
                events = list_planned_intake_events(connection, int(user_id))
                review_count = count_needs_review(connection, int(user_id))
                # The selector shows the first meal chosen, so its plates are the
                # ones listed (frontend_conventions.md §6).
                if events:
                    plate_options, last_used_plate = plate_selector_options(connection, int(user_id), events[0].id)
                list_content = _food_list_content(connection, view, parse_recipe_meal_types(view.meal_type))
        return render_page(
            request, food_main(view, events, plate_options, last_used_plate, review_count, list_content)
        )

    # Tags of a food, dish or recipe on its detail page (frontend_conventions.md §9.4.1).

    @rt("/food/tags/{entry_type}/{entry_id}")
    def post(request: Request, entry_type: str, entry_id: PathId, tag_id: str = "", linked: str = "", open: str = ""):
        """Leaves the tag on the entry as asked: repeating it is a no-op (§6.3)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        # Required: an empty value would read as False and take the tag off (§7.4, §7.6).
        if not linked.strip():
            return app_error_response(request, ValidationError, "Say whether to add or remove the tag.")
        try:
            parsed_tag_id = parse_optional_id(tag_id, "tag_id")
            wanted = _parse_strict_bool(linked)
            keep_open = _parse_strict_bool(open)
        except ValidationError as error:
            return app_error_response(request, error, str(error))
        if parsed_tag_id is None:
            return app_error_response(request, ValidationError, "Choose a tag.")
        with get_connection() as connection:
            try:
                set_entry_tag(connection, int(user_id), kind, entry_id, parsed_tag_id, wanted)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That food or tag is not available.")
            return render_fragment(_entry_tags_block(connection, int(user_id), kind, entry_id, keep_open))

    @rt("/food/tags/{entry_type}/{entry_id}/new")
    def post(request: Request, entry_type: str, entry_id: PathId, name: str = ""):
        """Puts a tag on the entry by its name: a system tag or one of the user's is
        reused, otherwise a personal tag is created. Repeating it is a no-op (§6.3)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        try:
            clean_name = parse_tag_name(name)
        except ValidationError as error:
            return app_error_response(request, error, str(error))
        with get_connection() as connection:
            try:
                with connection.transaction():
                    tag_id = _tag_id_for_name(connection, int(user_id), clean_name)
                    set_entry_tag(connection, int(user_id), kind, entry_id, tag_id, True, commit=False)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That food is not available.")
            return render_fragment(_entry_tags_block(connection, int(user_id), kind, entry_id, True))

    @rt("/food/actions/{entry_type}/{entry_id}")
    def get(request: Request, entry_type: str, entry_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        with get_connection() as connection:
            entry = _food_entry_summary(connection, int(user_id), kind, entry_id)
        if entry is None:
            return app_error_response(request, NotFoundError, "Food not found.")
        return render_fragment(FoodActionsMenu(kind, entry_id, entry))

    @rt("/food/actions/{entry_type}/{entry_id}/recipes")
    def get(request: Request, entry_type: str, entry_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        if kind is FoodEntryType.RECIPE:
            return app_error_response(request, ValidationError, "A recipe cannot be an ingredient of another recipe.")
        with get_connection() as connection:
            entry = _food_entry_summary(connection, int(user_id), kind, entry_id)
            if entry is None:
                return app_error_response(request, NotFoundError, "Food not found.")
            # Only the user's own recipes: the only ones they can edit.
            recipes = list_recipes(connection, int(user_id), owned_only=True)
            several_plates = {
                recipe.id for recipe in recipes if len(list_recipe_plates(connection, int(user_id), recipe.id)) > 1
            }
        return render_fragment(FoodActionsRecipes(kind, entry_id, entry, recipes, several_plates))

    @rt("/food/actions/{entry_type}/{entry_id}/recipes/{recipe_id}/plates")
    def get(request: Request, entry_type: str, entry_id: PathId, recipe_id: PathId):
        """Which plate, for a recipe with several (frontend §9.3.1)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None or kind is FoodEntryType.RECIPE:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        with get_connection() as connection:
            entry = _food_entry_summary(connection, int(user_id), kind, entry_id)
            recipe = _editable_recipe(connection, user_id, recipe_id)
            if entry is None or recipe is None:
                return app_error_response(request, NotFoundError, "Food not found.")
            portions = list_viewable_recipe_portions(connection, int(user_id), recipe_id)
            plates = [
                (
                    plate.id,
                    plate.name or derive_plate_name(
                        [row.source.name for row in portions if row.recipe_plate_id == plate.id]
                    ),
                )
                for plate in list_recipe_plates(connection, int(user_id), recipe_id)
            ]
        return render_fragment(FoodActionsRecipePlates(kind, entry_id, entry, recipe, plates))

    @rt("/food/actions/{entry_type}/{entry_id}/fridge")
    def get(request: Request, entry_type: str, entry_id: PathId):
        """Save a food or a dish into a new container from its row (frontend §9.3.1)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None or kind is FoodEntryType.RECIPE:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        with get_connection() as connection:
            entry = _food_entry_summary(connection, int(user_id), kind, entry_id)
        if entry is None:
            return app_error_response(request, NotFoundError, "Food not found.")
        return render_fragment(FoodActionsStore(kind, entry_id, entry))

    @rt("/food/actions/{entry_type}/{entry_id}/copy")
    def get(request: Request, entry_type: str, entry_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        with get_connection() as connection:
            entry = _food_entry_summary(connection, int(user_id), kind, entry_id)
        if entry is None:
            return app_error_response(request, NotFoundError, "Food not found.")
        return render_fragment(FoodActionsCopyConfirm(kind, entry_id, entry))

    @rt("/food/item/{entry_type}/{entry_id}")
    def get(request: Request, entry_type: str, entry_id: PathId):
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            raise ValidationError(_UNKNOWN_ENTRY_TYPE, fields={"entry_type": "invalid"})
        with get_connection() as connection:
            user_id = get_current_user_id()
            if kind is FoodEntryType.CATALOG:
                item = get_catalog_item(connection, int(user_id), entry_id) if user_id else None
                if item is None:
                    raise NotFoundError("Food not found.")
                summary = _catalog_detail_summary(item)
                tags_block = _entry_tags_block(connection, int(user_id), kind, entry_id) if user_id else ""
                events = list_planned_intake_events(connection, int(user_id)) if user_id else []
                plate_options, selected_plate_id = (
                    plate_selector_options(connection, int(user_id), events[0].id) if events else ([], None)
                )
                return render_page(
                    request,
                    FoodDetailPage(
                        user_id=user_id or 0,
                        entry_type="catalog",
                        entry=catalog_entry_view(item),
                        summary=summary,
                        recipe_portions=None,
                        events=events,
                        plate_options=plate_options,
                        selected_plate_id=selected_plate_id,
                        can_edit=item.can_edit,
                        can_archive=item.can_edit,
                        can_publish=item.can_edit,
                        is_published=item.is_published,
                        is_archived=item.is_archived,
                        is_library=item.is_library,
                        has_serving=item.default_portion is not None,
                        cooking_factor=item.cooking_factor,
                        tags_block=tags_block,
                        preparation=_detail_preparation(
                            connection,
                            user_id,
                            PreparationFood(PortionOrigin.CATALOG, item.id, item.subtype, item.category.value),
                        ),
                    ),
                    show_cart=False,
                )
            if kind is FoodEntryType.MANUAL_INTAKE:
                # None also for another user's personal dish or a quick add (§5.4, §11.2.3).
                manual_item = get_manual_intake(connection, int(user_id), entry_id) if user_id else None
                if manual_item is None:
                    raise NotFoundError("Dish not found.")
                summary = _manual_intake_detail_summary(manual_item)
                tags_block = _entry_tags_block(connection, int(user_id), kind, entry_id)
                events = list_planned_intake_events(connection, int(user_id))
                plate_options, selected_plate_id = (
                    plate_selector_options(connection, int(user_id), events[0].id) if events else ([], None)
                )
                return render_page(
                    request,
                    FoodDetailPage(
                        user_id=user_id,
                        entry_type="manual_intake",
                        entry=manual_intake_entry_view(manual_item),
                        summary=summary,
                        recipe_portions=None,
                        events=events,
                        plate_options=plate_options,
                        selected_plate_id=selected_plate_id,
                        can_edit=manual_item.can_edit,
                        can_archive=manual_item.can_edit,
                        can_publish=manual_item.can_edit,
                        is_published=manual_item.is_published,
                        is_archived=manual_item.is_archived,
                        has_serving=manual_item.default_portion is not None,
                        cooking_factor=None,
                        tags_block=tags_block,
                        preparation=_detail_preparation(
                            connection,
                            user_id,
                            PreparationFood(PortionOrigin.MANUAL_INTAKE, manual_item.id, manual_item.subtype, None),
                        ),
                    ),
                    show_cart=False,
                )
            recipe = get_recipe(connection, int(user_id), entry_id)
            if recipe is None:
                raise NotFoundError("Recipe not found.")
            entry = recipe_entry_view(recipe)
            recipe_portions = list_viewable_recipe_portions(connection, int(user_id), entry_id)
            recipe_plates = list_recipe_plates(connection, int(user_id), entry_id)
            summary = _recipe_summary(entry, recipe_portions)
            tags_block = _entry_tags_block(connection, int(user_id), kind, entry_id)
            can_edit = recipe.can_edit
            can_delete = can_edit
            events = list_planned_intake_events(connection, int(user_id)) if user_id else []
            # The event's plates the selector will show as selected (§7.7):
            # without this the plate selector would be born empty and would
            # only fill in when the meal changed.
            plate_options, selected_plate_id = (
                plate_selector_options(connection, int(user_id), events[0].id) if events else ([], None)
            )
        return render_page(
            request,
            FoodDetailPage(
                user_id=user_id or 0,
                entry_type=entry_type,
                entry=entry,
                summary=summary,
                recipe_portions=recipe_portions,
                recipe_plates=recipe_plates,
                events=events,
                plate_options=plate_options,
                selected_plate_id=selected_plate_id,
                can_edit=can_edit,
                can_delete=can_delete,
                is_archived=False,
                tags_block=tags_block,
            ),
            show_cart=False,
        )

    @rt("/food/list")
    def get(
        request: Request,
        search: str = "",
        filter: str = "all",
        search_mode: str = "recommended",
        food_mode: str = "catalog",
        favs_mode: str = "catalog",
        recipes_mode: str = "mine",
        meal_type: str = "",
        page: int = 1,
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            recipe_meal_types = parse_recipe_meal_types(meal_type)
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))

        with get_connection() as connection:
            view = FoodView(filter, search_mode, food_mode, favs_mode, recipes_mode, meal_type)
            return render_fragment(_food_list_content(connection, view, recipe_meal_types, search=search, page=page))

    @rt("/food/list/external")
    def get(
        request: Request, source: str = "", search: str = "", page: int = 1, add_to_recipe: str = "", recipe_plate_id: str = ""
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            prefill_source = PrefillSource(source)
        except ValueError:
            return app_error_response(request, ValidationError, "Unknown food source.")
        with get_connection() as connection:
            try:
                recipe_query = _recipe_query(
                    parse_optional_id(add_to_recipe, "recipe"), parse_optional_id(recipe_plate_id, "plate")
                )
            except ValidationError as error:
                return app_error_response(request, ValidationError, str(error))
            cards, load_more = _external_page(
                connection, int(user_id), prefill_source, (search or "").strip(), max(1, page), recipe_query
            )
        return render_fragment(tuple(cards + ([load_more] if load_more is not None else [])))

    @rt("/food/favorite/{entry_type}/{entry_id}")
    def post(request: Request, entry_type: str, entry_id: PathId, favorite: str = "", confirmed: str = ""):
        """Sets the favorite to what the star asked for (frontend §9.3.2)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        # Required: the strict parser reads an empty value as False, and a request
        # without the field must not remove the favorite (§7.4, §7.6).
        if not favorite.strip():
            return app_error_response(request, ValidationError, "Say whether to add or remove the favorite.")
        try:
            wanted = _parse_strict_bool(favorite)
            removal_confirmed = _parse_strict_bool(confirmed)
        except ValidationError as error:
            return app_error_response(request, error, str(error))

        not_found, not_addable = _FAVORITE_MESSAGES[kind]
        with get_connection() as connection:
            if not wanted and not removal_confirmed:
                access = get_user_favorite_access(connection, int(user_id), kind, entry_id)
                entry = (
                    _food_entry_summary(connection, int(user_id), kind, entry_id)
                    if access is not None and access.is_only_access
                    else None
                )
                if entry is not None:
                    response = render_fragment(FoodActionsFavoriteConfirm(kind, entry_id, entry))
                    response.headers["HX-Retarget"] = f"#{FOOD_ACTIONS_BODY_ID}"
                    response.headers["HX-Reswap"] = "innerHTML"
                    return response
            try:
                set_user_favorite(connection, int(user_id), kind, entry_id, wanted)
            except NotFoundError:
                return app_error_response(request, NotFoundError, not_found)
            except ConflictError:
                return app_error_response(request, ConflictError, not_addable)
            access = get_user_favorite_access(connection, int(user_id), kind, entry_id)

        if access is None:
            # The row was the access to this food: its card has nothing left to show.
            response = HTMLResponse("")
            response.headers["HX-Retarget"] = f"#{food_card_id(kind, entry_id)}"
            response.headers["HX-Reswap"] = "outerHTML"
            return response
        return render_fragment(FavoriteButton(kind, entry_id, access.is_favorite))

    @rt("/meal_selector_input")
    def get(request: Request, intake_event_id: str):
        if intake_event_id != "0":
            return render_fragment("")
        
        return render_fragment(Div(
            Input(
                placeholder="Meal name",
                name="meal_name",
                id="meal_name_input_text",
                maxlength=str(INTAKE_EVENT_NAME_MAX_LENGTH),
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
                hx_push_url="false",
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
                hx_push_url="false",
                hx_include="#meal_name_input_text",
                **on_after()
            ),
            cls="flex gap-2 w-full"        
            ))

    @rt("/food/plate_selector")
    def get(request: Request, intake_event_id: str = ""):
        """Plate selector for the event chosen in the meal selector (§7.7).

        It returns empty only when there is no event to list plates from (none
        selected, `New Meal`, or an event no longer in the cart).
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        try:
            chosen_event_id = parse_optional_id(intake_event_id, "meal")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        if not chosen_event_id:
            return render_fragment(PlateSelector([]))

        with get_connection() as connection:
            try:
                event_id = get_planned_intake_event(connection, int(user_id), chosen_event_id)
            except (NotFoundError, ConflictError):
                return render_fragment(PlateSelector([]))
            # The last plate something was added to is preselected: when putting
            # together the second dish, several foods are added to it in a row (§7.7).
            options, last_used = plate_selector_options(connection, int(user_id), event_id)
            return render_fragment(PlateSelector(options, selected_id=last_used))

    @rt("/create_named_event")
    def post(request: Request, meal_name: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        clean_name = (meal_name or "").strip()
        if len(clean_name) > INTAKE_EVENT_NAME_MAX_LENGTH:
            # §7.3: never truncate silently; anything beyond the VARCHAR(255)
            # is rejected at the boundary (decision 2026-09-09, finding 24).
            return HTMLResponse(status_code=422)

        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                # No session: 401 (error_conventions.md §3.3). Defense in
                # depth; the middleware already covers these routes (finding 26).
                return HTMLResponse(status_code=401)

            event_id = create_intake_event(
                connection,
                IntakeEventCreate(
                    user_id=int(user_id),
                    state=IntakeEventState.PLANNED,
                    name=clean_name or None,
                    meal_type=default_meal_type_now(connection, int(user_id)),
                ),
            )

            headers = {"HX-Trigger": "addSuccess" if event_id else "addError"}
            return HTMLResponse("", headers=headers)
