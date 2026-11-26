"""Putting food in a meal or in the fridge: add to the cart, log, rescue and the fridge actions (measurement_conventions.md §4.8, frontend_conventions.md §9.6)."""

from fasthtml.common import *
from datetime import datetime
from datetime import date
import json
from DayBetes_food.routes.navigation import hx_location
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.ui import render_fragment
from DayBetes_food.http_errors import app_error_response
from DayBetes_food.services.fridge import (
    create_fridge_container,
    list_fridge_items,
    store_in_fridge,
    store_recipe_in_fridge,
    take_from_fridge,
)
from DayBetes_food.services.intake_event import (
    confirm_planned_event,
    default_meal_type_now,
    new_plate_offset_minutes,
    resolve_event_plate,
    resolve_target_event,
)
from DayBetes_food.database.queries import (
    create_portion_detail,
    get_catalog_item,
    get_manual_intake,
    get_recipe,
    get_rescue_entries_suggestions,
    update_intake_event,
    create_intake_event,
    get_intake_event,
    create_intake_plate,
    get_fridge,
)
from DayBetes_food.domain.constants import (
    PathId,
    AmountInputUnit,
    FractionMethod,
    AmountMethod,
    ConservationMethod,
    CookingMethod,
    FoodPhysicalState,
    PortionDestination,
    FoodEntryType,
    PortionOrigin,
    Ripeness,
    StorageLocation,
    parse_enum,
    parse_optional_id,
)
from DayBetes_food.domain.food import INITIAL_AMOUNT_WITHOUT_SERVING_G
from DayBetes_food.domain.portion_detail import (
    PortionDetailCreate,
    amount_to_grams,
    parse_amount_grams,
    one_click_portion_defaults,
    portion_defaults,
)
from DayBetes_food.components.food.fridge import FridgeListOob
from DayBetes_food.components.modal import ModalFormError
from DayBetes_food.components.food.rescue import RescueForm, RescueLine, RescueOptions
from DayBetes_food.database.connection import get_connection
from DayBetes_food.domain.constants import IntakeEventState, MealType, SystemTag
from DayBetes_food.domain.intake_event import IntakeEventCreate, IntakeEventUpdate
from DayBetes_food.domain.intake_plate import IntakePlateCreate
from DayBetes_food.services.recipe import add_recipe_to_meal
from DayBetes_food.domain.fridge import FridgeContent, FridgeStoreCommand
from DayBetes_food.time_utils import local_naive_to_utc_aware, local_now, utc_now
from DayBetes_food.errors import AuthenticationError, ConflictError, NotFoundError, ValidationError
from DayBetes_food.routes.food.helpers import (
    _MEAL_CONFIRMED,
    _PLATE_DISPLAY_TOLERANCE_G,
    _RECIPE_WITHOUT_INGREDIENTS,
    _UNKNOWN_ENTRY_TYPE,
    _detail_origin,
    _error_msg,
    _get_rescue_food,
    _is_fruit,
    _meal_created_event,
    _parse_food_entry_type,
    _parse_hhmm,
    _parse_recipe_add_request,
    _parse_strict_bool,
    _parse_typed_amount,
    _rescue_error,
    _store_error,
    _to_float,
    _to_int,
)


def setup_adding_routes(rt):

    @rt("/food/rescue/form")
    def get(request: Request, kind: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            tab = parse_enum(SystemTag, kind, field="kind") or SystemTag.RESCUE
        except ValidationError as error:
            return app_error_response(request, error, str(error))
        # The initial food list travels with the form: a single response,
        # so the pop-up opens complete instead of growing twice (§9.6).
        with get_connection() as connection:
            rows = get_rescue_entries_suggestions(connection, int(user_id), tab, search="", limit=30)
        now = local_now()
        return render_fragment(RescueForm(now.strftime("%Y-%m-%d"), now.strftime("%H:%M"), rows, tab))

    @rt("/food/rescue/options")
    def get(request: Request, q: str = "", kind: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            tab = parse_enum(SystemTag, kind, field="kind") or SystemTag.RESCUE
        except ValidationError as error:
            return app_error_response(request, error, str(error))
        search = (q or "").strip()
        with get_connection() as connection:
            rows = get_rescue_entries_suggestions(connection, int(user_id), tab, search=search, limit=30)
        return render_fragment(RescueOptions(rows, searching=bool(search), kind=tab))

    @rt("/food/rescue/line/{entry_type}/{entry_id}")
    def get(request: Request, entry_type: str, entry_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            origin = PortionOrigin(entry_type)
        except ValueError:
            # Value outside the closed set of the URL: validation_error (§7.7).
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        with get_connection() as connection:
            item = _get_rescue_food(connection, int(user_id), origin, entry_id)
        if item is None:
            return app_error_response(request, NotFoundError, "Food not found.")
        return render_fragment(
            RescueLine(origin.value, int(item.id), item.name, item.default_portion, is_fruit=_is_fruit(item))
        )

    @rt("/food/rescue/log")
    async def post(request: Request):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        form = await request.form()
        entry_types = form.getlist("entry_type")
        entry_ids = form.getlist("entry_id")
        amount_values = form.getlist("amount_value")
        amount_units = form.getlist("amount_unit")
        # One per line, empty when it is not a fruit (RescueLine, study §6.3). A form
        # without the field at all (opened before it existed) gives none: "not given".
        ripeness_values = form.getlist("ripeness") or [""] * len(entry_types)
        if not entry_types:
            return _rescue_error("Choose at least one food.")
        if not (
            len(entry_types) == len(entry_ids) == len(amount_values) == len(amount_units) == len(ripeness_values)
        ):
            return _rescue_error("The rescue lines are incomplete.")

        meal_t = _parse_hhmm(str(form.get("meal_hour") or ""))
        try:
            meal_d = date.fromisoformat(str(form.get("meal_date") or "").strip())
        except ValueError:
            meal_d = None
        if meal_t is None or meal_d is None:
            return _rescue_error("Choose a valid date and time.")
        # Any moment is accepted, also a future one (§9.6, decision 2026-09-06).
        meal_time = local_naive_to_utc_aware(datetime.combine(meal_d, meal_t))
        # Rescue by default; any other type for what is not a rescue (§9.6).
        try:
            meal_type = parse_enum(MealType, str(form.get("meal_type") or ""), field="meal_type")
        except ValidationError:
            return _rescue_error("That meal type does not exist.")
        if meal_type is None:
            return _rescue_error("Choose the meal type.")

        # HTTP payload validation that does not depend on the database (§7.1).
        lines = []
        for raw_type, raw_id, raw_value, raw_unit, raw_ripeness in zip(
            entry_types, entry_ids, amount_values, amount_units, ripeness_values
        ):
            try:
                origin = PortionOrigin(str(raw_type).strip())
                unit = AmountInputUnit(str(raw_unit).strip())
                ripeness = parse_enum(Ripeness, str(raw_ripeness), field="ripeness")
            except (ValueError, ValidationError):
                return _rescue_error("A rescue line is not valid.")
            origin_id = _to_int(str(raw_id))
            value = _to_float(str(raw_value))
            if not origin_id:
                return _rescue_error("A rescue line is not valid.")
            if unit is AmountInputUnit.PERCENT:
                return _rescue_error("Use grams, servings, lb or oz.")
            if value is None:
                return _rescue_error("Enter an amount for every food.")
            lines.append((origin, int(origin_id), value, unit, ripeness))

        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            # The foods are read with the SQL visibility rule, and the serving
            # comes from the database, never from the form (§7.13).
            portions = []
            for origin, origin_id, value, unit, ripeness in lines:
                item = _get_rescue_food(connection, int(user_id), origin, origin_id)
                if item is None:
                    return app_error_response(request, NotFoundError, "Rescue food not found.")
                if ripeness is not None and not _is_fruit(item):
                    return _rescue_error(f"{item.name} is not a fruit: it has no ripeness.")
                try:
                    grams = parse_amount_grams(amount_to_grams(value, unit, item.default_portion))
                except ValidationError:
                    if unit is AmountInputUnit.PORTION and item.default_portion is None:
                        return _rescue_error(f"{item.name} has no serving. Use grams, lb or oz.")
                    return _rescue_error("Each amount must be greater than 0 g and at most 100000 g.")
                portions.append((origin, origin_id, grams, {**portion_defaults(item), "ripeness": ripeness}))

            try:
                with connection.transaction():
                    event_id = create_intake_event(
                        connection,
                        IntakeEventCreate(
                            user_id=int(user_id),
                            state=IntakeEventState.PLANNED,
                            meal_type=meal_type,
                            meal_time=meal_time,
                        ),
                        commit=False,
                    )
                    # This pop-up never logs insulin, whatever the meal type (§9.6): without this the
                    # column DEFAULT TRUE would create an automatic injection.
                    update_intake_event(
                        connection,
                        user_id=int(user_id),
                        event_id=int(event_id),
                        data=IntakeEventUpdate(insulin_dose=False),
                        commit=False,
                    )
                    # A single plate with offset 0 (measurement_conventions.md §4.6.1).
                    plate_id = create_intake_plate(
                        connection,
                        IntakePlateCreate(intake_event_id=int(event_id), offset_minutes=0),
                        commit=False,
                    )
                    for origin, origin_id, grams, defaults in portions:
                        # A repeated food with the same preparation is merged (§4.6.4).
                        create_portion_detail(
                            connection,
                            int(user_id),
                            PortionDetailCreate(
                                origin=origin,
                                origin_id=origin_id,
                                destination=PortionDestination.INTAKE_EVENT,
                                destination_id=int(event_id),
                                amount=grams,
                                offset_minutes=0,
                                plate_id=plate_id,
                                **defaults,
                            ),
                            commit=False,
                        )
                    # Same confirm as the cart, at 100 % (§6.9.1).
                    confirm_planned_event(connection, int(user_id), int(event_id))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Rescue food not found.")
            except ConflictError:
                return app_error_response(request, ConflictError, "The rescue could not be registered.")
            except ValidationError:
                return _rescue_error("The total amount must be at most 100000 g.")
        return HTMLResponse("", headers={"HX-Trigger": json.dumps({"rescueRegistered": {"meal_type": meal_type.value}})})

    @rt("/food/log/{entry_type}/{entry_id}")
    def post(
        request: Request,
        entry_type: str,
        entry_id: PathId,
        amount_value: str = "",
        amount_unit: str = AmountInputUnit.PORTION.value,
        plate_value: str = "",
        plate_unit: str = AmountInputUnit.PERCENT.value,
        intake_event_id: str = "",
        plate_id: str = "",
        cooking: str = "",
        final_state: str = "",
        conservation: str = "",
        ripeness: str = "",
        is_cooked_weight: str = "",
        amount_method: str | None = None,
    ):
        """Add a food or a recipe from its page to a planned event.

        The form sends what the user typed, value + unit, and the server
        converts it (measurement_conventions.md 11, decision 2026-09-22):
        `amount_value`/`amount_unit` is the cooked total (`portion`, `g`, `lb`,
        `oz`) and `plate_value`/`plate_unit` the part of it that is plated
        (`%` of the total or `g`). Only the plated amount is persisted; the
        cooked total is used to bound it and is not stored (decision
        2026-09-18). The JavaScript only repaints the numbers.

        `amount_method` is the `Amount from` select of the page (U2, study
        §6.3), which starts on the food's default (measurement_conventions.md
        §6.11): what it sends is what the portion is born with, and empty is
        "not given". Absent (a request without the control), the food's
        default applies as on every other path.
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)

        try:
            cooked_weight = _parse_strict_bool(is_cooked_weight)
        except ValidationError:
            return app_error_response(request, ValidationError, "The 'Cooked weight' checkbox could not be read.")
        try:
            chosen_amount_method = parse_enum(AmountMethod, amount_method, field="amount_method")
        except ValidationError:
            return app_error_response(request, ValidationError, "The 'Amount from' value could not be read.")
        try:
            unit = AmountInputUnit((amount_unit or "").strip())
            plated_unit = AmountInputUnit((plate_unit or "").strip())
        except ValueError:
            return render_fragment(P("Choose a valid unit.", cls="text-red-700"))
        if unit is AmountInputUnit.PERCENT or plated_unit not in (AmountInputUnit.PERCENT, AmountInputUnit.GRAMS):
            return render_fragment(P("Choose a valid unit.", cls="text-red-700"))
        typed_amount = _parse_typed_amount(amount_value)
        typed_plate = _parse_typed_amount(plate_value)
        if typed_amount is None or typed_plate is None:
            return render_fragment(P("Amount must be a number.", cls="text-red-700"))
        try:
            parsed_cooking = parse_enum(CookingMethod, cooking, field="cooking")
            parsed_final_state = parse_enum(FoodPhysicalState, final_state, field="final_state")
            parsed_conservation = parse_enum(ConservationMethod, conservation, field="conservation")
            parsed_ripeness = parse_enum(Ripeness, ripeness, field="ripeness")
        except ValidationError as error:
            return render_fragment(P(str(error), cls="text-red-700"))

        if kind is FoodEntryType.RECIPE:
            # A recipe goes through its own step (POST /add_recipe, frontend §9.7).
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)

        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                # Defence in depth: the middleware already covers these routes
                # (finding 26 of audit_intake_event).
                return app_error_response(request, AuthenticationError, "Your session has expired.")
            try:
                origin_item = _detail_origin(connection, int(user_id), kind, entry_id, cooked_weight, unit)
            except NotFoundError as error:
                return app_error_response(request, NotFoundError, str(error))
            except ValidationError as error:
                return _error_msg(str(error))
            serving_grams = origin_item.default_portion
            # The page's `Final state` control already shows the food's default and
            # sends what the portion is born with (measurement §6.11).
            log_defaults = {"amount_method": origin_item.default_amount_method}
            try:
                total_grams = parse_amount_grams(amount_to_grams(typed_amount, unit, serving_grams))
                if plated_unit is AmountInputUnit.PERCENT:
                    if not (0.0 < typed_plate <= 100.0):
                        raise ValidationError("plate_percent_out_of_range")
                    plated_grams = total_grams * typed_plate / 100.0
                else:
                    # The page shows the plated grams with one decimal, so
                    # "all of it" can exceed the total by that rounding.
                    if not (0.0 < typed_plate <= total_grams + _PLATE_DISPLAY_TOLERANCE_G):
                        raise ValidationError("plate_grams_out_of_range")
                    plated_grams = min(typed_plate, total_grams)
                plated_grams = parse_amount_grams(plated_grams)
            except ValidationError:
                # Form validation: 200 + fragment inside the form (9.5).
                return render_fragment(
                    P(
                        "The amount must be greater than 0 g and at most 100000 g, and the "
                        "amount to plate must be between 0 and the total.",
                        cls="text-red-700",
                    )
                )

            try:
                with connection.transaction():
                    event_id, _ = resolve_target_event(connection, int(user_id), parse_optional_id(intake_event_id, "meal"))
                    event_data = get_intake_event(connection, int(user_id), event_id)
                    offset_minutes = new_plate_offset_minutes(event_data)

                    if amount_method is not None:
                        log_defaults["amount_method"] = chosen_amount_method
                    target_plate_id = resolve_event_plate(
                        connection, int(user_id), event_id, parse_optional_id(plate_id, "plate"), offset_minutes
                    )
                    # What was cooked and not plated goes into a new container in the
                    # fridge, as the page says (measurement §4.8.5). The split is
                    # weighed when the plate was given in grams, by eye in % (study §6.3).
                    leftover_grams = total_grams - plated_grams
                    split_method = (
                        None
                        if leftover_grams <= _PLATE_DISPLAY_TOLERANCE_G
                        else FractionMethod.EYEBALL
                        if plated_unit is AmountInputUnit.PERCENT
                        else FractionMethod.WEIGHED
                    )
                    create_portion_detail(
                        connection,
                        int(user_id),
                        PortionDetailCreate(
                            origin=PortionOrigin(entry_type),
                            origin_id=entry_id,
                            destination=PortionDestination.INTAKE_EVENT,
                            destination_id=event_id,
                            plate_id=target_plate_id,
                            amount=plated_grams,
                            split_method=split_method,
                            cooking=parsed_cooking,
                            final_state=parsed_final_state,
                            conservation=parsed_conservation,
                            # A fruit only (study §6.3); the leftovers' container gets none.
                            ripeness=parsed_ripeness,
                            is_cooked_weight=(cooked_weight if kind is FoodEntryType.CATALOG else False),
                            **log_defaults,
                        ),
                        commit=False,
                    )
                    if split_method is not None:
                        create_fridge_container(
                            connection,
                            FridgeStoreCommand(
                                user_id=int(user_id),
                                location=StorageLocation.FRIDGE,
                                contents=(
                                    FridgeContent(
                                        origin=PortionOrigin(entry_type),
                                        origin_id=entry_id,
                                        amount=leftover_grams,
                                        cooking=parsed_cooking,
                                        final_state=parsed_final_state,
                                        amount_method=log_defaults["amount_method"],
                                        split_method=split_method,
                                        is_cooked_weight=(cooked_weight if kind is FoodEntryType.CATALOG else False),
                                    ),
                                ),
                            ),
                        )
            except NotFoundError:
                # Another user's or an archived intake_event_id: a nonexistent
                # resource (§5.4), not a server failure (finding 23).
                return app_error_response(request, NotFoundError, "That meal no longer exists.")
            except ConflictError:
                # The event is no longer 'planned'.
                return app_error_response(request, ConflictError, "That meal has already been confirmed.")
            except ValidationError as error:
                if "ripeness" in error.fields:
                    return render_fragment(P(str(error), cls="text-red-700"))
                return render_fragment(P("Could not log this food: check the amounts.", cls="text-red-700"))
            return HTMLResponse("", headers=hx_location("/food"))

    @rt("/food/fridge/store/{entry_type}/{entry_id}")
    def post(
        request: Request,
        entry_type: str,
        entry_id: PathId,
        location: str = "",
        amount_value: str = "",
        amount_unit: str = AmountInputUnit.PORTION.value,
        cooking: str = "",
        final_state: str = "",
        is_cooked_weight: str = "",
        amount_method: str | None = None,
    ):
        """Save an amount of a food or a dish from its page as a new container in
        the fridge or the freezer (measurement_conventions.md §4.8.5, frontend §9.4).

        Same fields as /food/log without the plate: the whole amount goes into the
        container, and its conservation is the container's place (§4.8.4).
        Repeating it stores a second container (§9.6). Form validation answers
        200 + message (§9.5); on success an empty body and `fridgeStored`, which
        static/js/fridge.js turns into a notice (the page stays where it is).
        Also used by the actions pop-up of a Food row (frontend §9.3.1).
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        kind = _parse_food_entry_type(entry_type)
        if kind is None or kind is FoodEntryType.RECIPE:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        try:
            storage = parse_enum(StorageLocation, location, field="location")
            cooked_weight = _parse_strict_bool(is_cooked_weight)
            chosen_amount_method = parse_enum(AmountMethod, amount_method, field="amount_method")
            parsed_cooking = parse_enum(CookingMethod, cooking, field="cooking")
            parsed_final_state = parse_enum(FoodPhysicalState, final_state, field="final_state")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        if storage is None:
            return app_error_response(request, ValidationError, "Choose the fridge or the freezer.")
        try:
            unit = AmountInputUnit((amount_unit or "").strip())
        except ValueError:
            return _store_error(request, "Choose a valid unit.")
        if unit is AmountInputUnit.PERCENT:
            return _store_error(request, "Choose a valid unit.")
        typed_amount = _parse_typed_amount(amount_value)
        if typed_amount is None:
            return _store_error(request, "Amount must be a number.")

        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            try:
                origin_item = _detail_origin(connection, int(user_id), kind, entry_id, cooked_weight, unit)
                grams = parse_amount_grams(amount_to_grams(typed_amount, unit, origin_item.default_portion))
            except NotFoundError as error:
                return app_error_response(request, NotFoundError, str(error))
            except ValidationError as error:
                return _store_error(request, str(error))
            method = chosen_amount_method if amount_method is not None else origin_item.default_amount_method
            try:
                store_in_fridge(
                    connection,
                    FridgeStoreCommand(
                        user_id=int(user_id),
                        location=storage,
                        contents=(
                            FridgeContent(
                                origin=PortionOrigin(kind.value),
                                origin_id=entry_id,
                                amount=grams,
                                cooking=parsed_cooking,
                                final_state=parsed_final_state,
                                amount_method=method,
                                is_cooked_weight=cooked_weight,
                            ),
                        ),
                    ),
                )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Item not found.")
            except ValidationError as error:
                return _store_error(request, str(error))
        return HTMLResponse("", headers={"HX-Trigger": json.dumps({"fridgeStored": {"location": storage.value}})})

    @rt("/add_food/{food_id}")
    def post(request: Request, food_id: PathId, intake_event_id: str = "", plate_id: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                return app_error_response(request, AuthenticationError, "Your session has expired.")
            catalog_item = get_catalog_item(connection, int(user_id), food_id)
            if catalog_item is None:
                return app_error_response(request, NotFoundError, "Food not found.")
            # R3: no serving -> 100 g initial amount for a one-click add.
            portion_amount = (
                catalog_item.default_portion
                if catalog_item.default_portion is not None
                else INITIAL_AMOUNT_WITHOUT_SERVING_G
            )
            try:
                with connection.transaction():
                    event_id, meal_created = resolve_target_event(connection, int(user_id), parse_optional_id(intake_event_id, "meal"))
                    event_data = get_intake_event(connection, int(user_id), event_id)
                    offset_minutes = new_plate_offset_minutes(event_data)
                    target_plate_id = resolve_event_plate(
                        connection, int(user_id), event_id, parse_optional_id(plate_id, "plate"), offset_minutes
                    )
                    create_portion_detail(
                        connection,
                        int(user_id),
                        PortionDetailCreate(
                            origin=PortionOrigin.CATALOG,
                            origin_id=food_id,
                            destination=PortionDestination.INTAKE_EVENT,
                            destination_id=event_id,
                            plate_id=target_plate_id,
                            amount=portion_amount,
                            **one_click_portion_defaults(catalog_item),  # measurement §6.11
                        ),
                        commit=False,
                    )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That meal no longer exists.")
            except ConflictError:
                return app_error_response(request, ConflictError, "That meal has already been confirmed.")
            except ValidationError as error:
                return app_error_response(request, ValidationError, str(error))
            trigger = {"addSuccess": True}
            if meal_created:
                trigger.update(_meal_created_event(connection, int(user_id), event_id))
            return HTMLResponse("", headers={"HX-Trigger": json.dumps(trigger)})

    @rt("/add_manual_intake/{manual_intake_id}")
    def post(request: Request, manual_intake_id: PathId, intake_event_id: str = "", plate_id: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                return app_error_response(request, AuthenticationError, "Your session has expired.")
            manual_intake = get_manual_intake(connection, int(user_id), manual_intake_id)
            if manual_intake is None:
                return app_error_response(request, NotFoundError, "Dish not found.")
            # R3, same as catalog: no serving -> 100 g initial amount for a one-click add.
            portion_amount = (
                manual_intake.default_portion
                if manual_intake.default_portion is not None
                else INITIAL_AMOUNT_WITHOUT_SERVING_G
            )
            try:
                with connection.transaction():
                    event_id, meal_created = resolve_target_event(connection, int(user_id), parse_optional_id(intake_event_id, "meal"))
                    event_data = get_intake_event(connection, int(user_id), event_id)
                    offset_minutes = new_plate_offset_minutes(event_data)
                    target_plate_id = resolve_event_plate(
                        connection, int(user_id), event_id, parse_optional_id(plate_id, "plate"), offset_minutes
                    )
                    create_portion_detail(
                        connection,
                        int(user_id),
                        PortionDetailCreate(
                            origin=PortionOrigin.MANUAL_INTAKE,
                            origin_id=manual_intake_id,
                            destination=PortionDestination.INTAKE_EVENT,
                            destination_id=event_id,
                            plate_id=target_plate_id,
                            amount=portion_amount,
                            **one_click_portion_defaults(manual_intake),
                        ),
                        commit=False,
                    )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That meal no longer exists.")
            except ConflictError:
                return app_error_response(request, ConflictError, "That meal has already been confirmed.")
            except ValidationError as error:
                return app_error_response(request, ValidationError, str(error))
            trigger = {"addSuccess": True}
            if meal_created:
                trigger.update(_meal_created_event(connection, int(user_id), event_id))
            return HTMLResponse("", headers={"HX-Trigger": json.dumps(trigger)})

    @rt("/food/fridge/{fridge_id}/take")
    def post(
        request: Request,
        fridge_id: PathId,
        amount_value: str = "",
        amount_unit: str = AmountInputUnit.PERCENT.value,
        intake_event_id: str = "",
        plate_id: str = "",
    ):
        """Take a part of a container into the meal and plate of the Food header
        (measurement_conventions.md §4.8.3, frontend §9.8). It is discounted now and
        goes back if the planned meal or the ingredient is deleted (§4.8.6).

        Repeating it takes another part, as a second helping would (§9.6). A
        validation error is a message inside the pop-up (200, §9.5); on success the
        message is emptied, the list is swapped out of band and `fridgeChanged` and
        `fridgeTaken` close the pop-up and give the notice.
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            unit = AmountInputUnit((amount_unit or "").strip())
        except ValueError:
            return render_fragment(ModalFormError("Take it in % or in grams."))
        with get_connection() as connection:
            if get_fridge(connection, int(user_id), fridge_id) is None:
                return app_error_response(request, NotFoundError, "That container is no longer in your fridge.")
            try:
                with connection.transaction():
                    event_id, meal_created = resolve_target_event(connection, int(user_id), parse_optional_id(intake_event_id, "meal"))
                    offset_minutes = new_plate_offset_minutes(get_intake_event(connection, int(user_id), event_id))
                    target_plate_id = resolve_event_plate(
                        connection, int(user_id), event_id, parse_optional_id(plate_id, "plate"), offset_minutes
                    )
                    take_from_fridge(
                        connection, int(user_id), fridge_id, amount_value, unit, event_id, target_plate_id
                    )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That meal or container is no longer available.")
            except ConflictError:
                return app_error_response(request, ConflictError, "That meal has already been confirmed.")
            except ValidationError as error:
                return render_fragment(ModalFormError(str(error)))
            items = list_fridge_items(connection, int(user_id))
            trigger = {"fridgeChanged": True, "fridgeTaken": True}
            if meal_created:
                trigger.update(_meal_created_event(connection, int(user_id), event_id))
        response = render_fragment(FridgeListOob(items, utc_now()))
        response.headers["HX-Trigger"] = json.dumps(trigger)
        return response

    @rt("/add_recipe/{recipe_id}")
    async def post(request: Request, recipe_id: PathId):
        """Add a recipe to a meal (frontend §9.7). Repeating it adds it again: another
        serving, not a duplicate (§9.6). Form validation answers 200 + fragment (§9.5)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        form = await request.form()
        with get_connection() as connection:
            recipe = get_recipe(connection, int(user_id), recipe_id)
            if recipe is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            try:
                add_request = _parse_recipe_add_request(form, recipe)
                event_id = add_recipe_to_meal(
                    connection,
                    int(user_id),
                    recipe_id,
                    add_request,
                    default_meal_type=default_meal_type_now(connection, int(user_id)),
                )
            except ValidationError as error:
                return _error_msg(str(error))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That meal or plate no longer exists.")
            except ConflictError as error:
                message = _RECIPE_WITHOUT_INGREDIENTS if str(error) == "recipe_without_ingredients" else _MEAL_CONFIRMED
                return app_error_response(request, ConflictError, message)
            trigger = {"recipeAdded": {"event_id": event_id}}
            if add_request.event_id is None:
                trigger.update(_meal_created_event(connection, int(user_id), event_id))
        return HTMLResponse("", headers={"HX-Trigger": json.dumps(trigger)})

    @rt("/food/fridge/store_recipe/{recipe_id}")
    async def post(request: Request, recipe_id: PathId):
        """Save a recipe into a new container from its step before adding, with its
        servings and preparation (measurement §4.8.5, frontend §9.7). The meal and
        plate of the form do not apply. Repeating it stores another container (§9.6).
        Form validation answers 200 + fragment (§9.5); on success `fridgeStored`."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        form = await request.form()
        try:
            storage = parse_enum(StorageLocation, str(form.get("location") or ""), field="location")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        if storage is None:
            return app_error_response(request, ValidationError, "Choose the fridge or the freezer.")
        with get_connection() as connection:
            recipe = get_recipe(connection, int(user_id), recipe_id)
            if recipe is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            try:
                store_recipe_in_fridge(
                    connection, int(user_id), recipe_id, storage, _parse_recipe_add_request(form, recipe)
                )
            except ValidationError as error:
                return _error_msg(str(error))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            except ConflictError:
                return app_error_response(request, ConflictError, _RECIPE_WITHOUT_INGREDIENTS)
        return HTMLResponse("", headers={"HX-Trigger": json.dumps({"fridgeStored": {"location": storage.value}})})
