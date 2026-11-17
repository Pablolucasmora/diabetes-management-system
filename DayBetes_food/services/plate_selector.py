"""Plates offered by the plate selector when a food is added to a meal
(frontend_conventions.md §7.7). The routes call it and pass the result to the
components, which never read the database (code_conventions.md §1.4)."""

from DayBetes_food.database.queries import list_intake_plates, list_portions_by_event
from DayBetes_food.domain.intake_plate import plate_label


def plate_selector_options(connection, user_id: int, event_id: int) -> tuple[list[tuple[int, str]], int | None]:
    """Plates of an event as `(id, label)` pairs for the selector (§7.7), and the
    plate to preselect.

    A plate's visible name can be derived from its ingredients
    (measurement_conventions.md §4.6.3), so they have to be read.

    The plate to preselect is the one of the last portion added and, if none
    has ingredients yet, the most recently created one. It is exactly the same
    criterion `ensure_default_plate` applies when the request carries no
    `plate_id`, so that what the selector shows is what would really happen
    (frontend_conventions.md §6).
    """
    plates = list_intake_plates(connection, user_id, event_id)
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

    options = [(plate.id, plate_label(plate, portions_by_plate.get(plate.id, []))) for plate in plates]
    return options, default_plate_id
