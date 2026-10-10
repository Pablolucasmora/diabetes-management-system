from fasthtml.common import *
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.cart.cart_components import plate_display_name
from DayBetes_food.components.food.foods import (
    Filters,
    MealSelector,
    QuickCreateButtons,
    SearchInput,
)
from DayBetes_food.database.queries import (
    list_intake_plates,
    list_planned_intake_events,
    list_portions_by_event,
)


def plate_selector_options(connection, user_id: int, event_id: int):
    """Plates of an event as `(id, label)` pairs for the selector (§7.7).

    A plate's visible name can be derived from its ingredients
    (measurement_conventions.md §4.6.3), so they have to be read: the
    component cannot resolve it on its own (§1.4).

    It also returns the plate to preselect: the one of the last portion added
    and, if none has ingredients yet, the most recently created one. It is
    exactly the same criterion `ensure_default_plate` applies when the
    request carries no `plate_id`, so that what the selector shows is what
    would really happen (frontend_conventions.md §6).
    """
    plates = list_intake_plates(connection, event_id)
    if not plates:
        return [], None

    portions_by_plate = {}
    last_portion_id = -1
    default_plate_id = max(plate.id for plate in plates)
    for portion in list_portions_by_event(connection, user_id, event_id):
        plate_id = portion.plate_id
        if plate_id is None:
            continue
        portions_by_plate.setdefault(plate_id, []).append(portion)
        if int(portion.id) > last_portion_id:
            last_portion_id = int(portion.id)
            default_plate_id = int(plate_id)

    options = [
        (plate.id, plate_display_name(plate, portions_by_plate.get(plate.id, [])))
        for plate in plates
    ]
    return options, default_plate_id


def food_main(connection):
    user_id = get_current_user_id()
    events = list_planned_intake_events(connection, int(user_id)) if user_id else []

    # The browser shows the meal selector's first option when none carries
    # `selected`, so the plates listed must be that same event's: what is
    # shown and what would be saved match (frontend_conventions.md §6).
    selected_event_id = events[0].id if events else None
    plate_options, last_used_plate = (
        plate_selector_options(connection, int(user_id), selected_event_id)
        if selected_event_id
        else ([], None)
    )

    return Div(
        # Blurs the whole page behind an open menu of the header
        # (static/js/food_quick_create.js). It is a single fixed layer with
        # backdrop-filter, instead of `filter: blur()` on each element: Safari
        # and Chrome paint coloured seams on blurred layers inside the glass
        # header (frontend_conventions.md §8).
        Div(
            id="food_menu_scrim",
            cls="fixed inset-0 z-[1] backdrop-blur-[1px] opacity-0 invisible transition-opacity duration-200",
        ),
        QuickCreateButtons(),
        SearchInput(),
        Filters(),
        MealSelector(
            events,
            selected_id=selected_event_id,
            plate_options=plate_options,
            selected_plate_id=last_used_plate,
        ),
        id="food_top_bar",
        cls="""
            flex flex-col items-center
            justify-between lg:gap-3 md:gap-3 gap-2.5 md:w-2xl lg:w-2xl w-full
            sticky mx-auto
            top-0 pt-2 md:pt-7 lg:pt-7 pb-2
            z-[600]
            web_glass_strong rounded-b-3xl
        """,
    ), Div(
        Div(
            "Loading...",
            id="food-list",
            hx_get="/food/list?filter=all&search_mode=recommended&page=1",
            hx_trigger="load",
            hx_swap="innerHTML",
            data_skip_page_loading="true",
            cls="flex flex-col items-center md:gap-3 lg:gap-3 gap-2 mt-4 transition-all duration-150 ease-out",
        ),
        id="food_list_wrapper",
        cls="""md:mb-50 lg:mb-50 mb-36""",
    )
