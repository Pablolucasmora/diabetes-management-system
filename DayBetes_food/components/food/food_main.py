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
    get_portion_detail_by_event,
    list_intake_plates,
    list_planned_intake_events,
)


def plate_selector_options(connection, event_id: int):
    """Tandas de un evento como pares `(id, etiqueta)` para el selector (§7.7).

    El nombre visible de una tanda puede ser derivado de sus ingredientes
    (measurement_conventions.md §4.6.3), así que hace falta leerlos: el
    componente no puede resolverlo solo (§1.4).

    Devuelve además la tanda a preseleccionar: la de la última porción añadida
    y, si ninguna tiene ingredientes todavía, la creada más recientemente. Es
    exactamente el mismo criterio que aplica `ensure_default_plate` cuando la
    petición no trae `plate_id`, para que lo que el selector muestra sea lo que
    de verdad ocurriría (frontend_conventions.md §6).
    """
    plates = list_intake_plates(connection, event_id)
    if not plates:
        return [], None

    portions_by_plate = {}
    last_portion_id = -1
    default_plate_id = max(plate.id for plate in plates)
    for portion in get_portion_detail_by_event(connection, event_id):
        plate_id = portion.get("plate_id")
        if plate_id is None:
            continue
        portions_by_plate.setdefault(plate_id, []).append(portion)
        if int(portion["id"]) > last_portion_id:
            last_portion_id = int(portion["id"])
            default_plate_id = int(plate_id)

    options = [
        (plate.id, plate_display_name(plate, portions_by_plate.get(plate.id, [])))
        for plate in plates
    ]
    return options, default_plate_id


def food_main(connection):
    user_id = get_current_user_id()
    events = list_planned_intake_events(connection, int(user_id)) if user_id else []

    # El navegador muestra la primera opción del selector de comida cuando
    # ninguna lleva `selected`, así que las tandas que se listan tienen que ser
    # las de ese mismo evento: lo que se ve y lo que se guardaría coinciden
    # (frontend_conventions.md §6).
    selected_event_id = events[0].id if events else None
    plate_options, last_used_plate = (
        plate_selector_options(connection, selected_event_id)
        if selected_event_id
        else ([], None)
    )

    return Div(
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
            justify-between lg:gap-4 md:gap-4 gap-3 md:w-lg lg:w-lg w-sm
            fixed inset-x-0 mx-auto
            top-0 pt-2 md:pt-7 lg:pt-7
            z-[600]
            bg-[#f6f2eb] border-b-[1px] border-white
        """,
        style=(
            "transform: translateZ(0);"
            "-webkit-transform: translateZ(0);"
            "backface-visibility: hidden;"
            "-webkit-backface-visibility: hidden;"
        ),
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
        cls="""md:pt-[240px] lg:pt-[240px]
               pt-[170px]
               md:mb-50 lg:mb-50 mb-36
        """,
    )
