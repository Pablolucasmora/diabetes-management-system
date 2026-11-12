import json
from datetime import datetime

from fasthtml.common import *
from DayBetes_food.components.modal import ModalFormError
from DayBetes_food.components.settings.settings_main import (
    settings_main,
    injections_settings_page,
    injections_settings_chunk,
    meal_type_schedule_settings_page,
    meal_type_schedule_row,
)
from DayBetes_food.components.food.tags import system_tag_for_label
from DayBetes_food.components.settings.tags_settings import tag_settings_row, tags_settings_list, tags_settings_page
from DayBetes_food.components.ui import render_page, render_fragment
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries import (
    create_tag,
    delete_tag,
    get_tag,
    list_tags,
    update_tag,
    list_insulin_injections,
    get_injection_shot_time_at_offset,
    update_insulin_injection,
    delete_insulin_injection,
    get_insulin_injection,
    get_insulin_pen,
    list_insulin_pens_by_ids,
    list_open_insulin_pens,
    get_meal_type_schedule,
    upsert_meal_type_window,
    delete_meal_type_window,
)
from DayBetes_food.domain.constants import InsulinType, InjectionZone, MealType, parse_enum, parse_optional_id
from DayBetes_food.domain.insulin import InsulinInjectionUpdate, parse_insulin_units, parse_shot_local
from DayBetes_food.domain.meal_type_schedule import (
    AUTO_ASSIGNABLE_MEAL_TYPES,
    resolve_meal_type_window,
)
from DayBetes_food.domain.tag import (
    TAG_NAME_TAKEN,
    TagCreate,
    TagUpdate,
    parse_tag_color,
    parse_tag_name,
    tag_color_from_name,
)
from DayBetes_food.errors import AuthenticationError, AuthorizationError, ConflictError, NotFoundError, ValidationError
from DayBetes_food.http_errors import app_error_response
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.time_utils import local_naive_to_utc_aware, APP_TIMEZONE


INJECTIONS_PAGE_SIZE = 15
_NOT_HTMX = "This action only works from the app."
_NO_SESSION = "Your session has expired."
_INJECTION_GONE = "That injection no longer exists."


def _injection_updated(modal_id: str) -> HTMLResponse:
    """Empty body and `injectionUpdated`: static/js/insulin_pens.js closes the pop-up
    and repaints the injection log."""
    return HTMLResponse("", headers={"HX-Trigger": json.dumps({"injectionUpdated": {"modal": modal_id}})})


def _injection_pens(connection, user_id: int, rows) -> tuple[list, dict]:
    """Open pens for the edit selectors and the pen of each row, open or closed."""
    open_pens = list_open_insulin_pens(connection, user_id)
    row_pen_ids = {row.insulin_pen_id for row in rows if row.insulin_pen_id is not None}
    pens_by_id = {pen.id: pen for pen in open_pens}
    missing = sorted(row_pen_ids - pens_by_id.keys())
    pens_by_id.update({pen.id: pen for pen in list_insulin_pens_by_ids(connection, user_id, missing)})
    return open_pens, pens_by_id


def setup_settings_routes(rt):
    @rt("/settings")
    def get(req):
        return render_page(
            req,
            lambda connection: settings_main(connection, current_user=req.state.user),
            show_cart=True,
        )

    # Settings Tags (frontend_conventions.md §9.10).

    @rt("/settings/tags")
    def get(req):
        user_id = get_current_user_id()
        if not user_id:
            raise AuthenticationError("Your session has expired.")
        return render_page(
            req, lambda connection: tags_settings_page(list_tags(connection, int(user_id))), show_cart=False
        )

    @rt("/settings/tags/list")
    def get(req, q: str = ""):
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(req, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            tags = list_tags(connection, int(user_id), search=q)
        return render_fragment(tags_settings_list(tags, searching=bool((q or "").strip())))

    @rt("/settings/tags")
    def post(req: Request, name: str = ""):
        """Creates a personal tag and answers with the whole list."""
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(req, AuthenticationError, "Your session has expired.")
        try:
            clean_name = parse_tag_name(name)
        except ValidationError as error:
            return app_error_response(req, error, str(error))
        if system_tag_for_label(clean_name) is not None:
            return app_error_response(req, ConflictError, TAG_NAME_TAKEN)
        with get_connection() as connection:
            try:
                create_tag(
                    connection,
                    TagCreate(user_id=int(user_id), name=clean_name, color=tag_color_from_name(clean_name)),
                )
            except ConflictError as error:
                return app_error_response(req, error, str(error))
            tags = list_tags(connection, int(user_id))
        return render_fragment(tags_settings_list(tags))

    @rt("/settings/tags/{tag_id}/update")
    def post(req: Request, tag_id: int, name: str = "", color: str = ""):
        """Renames or recolors one of the user's tags; the row is read again by id."""
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(req, AuthenticationError, "Your session has expired.")
        try:
            payload = TagUpdate(name=parse_tag_name(name), color=parse_tag_color(color))
        except ValidationError as error:
            return app_error_response(req, error, str(error))
        if system_tag_for_label(payload.name) is not None:
            return app_error_response(req, ConflictError, TAG_NAME_TAKEN)
        with get_connection() as connection:
            try:
                update_tag(connection, int(user_id), tag_id, payload)
            except NotFoundError:
                return app_error_response(req, NotFoundError, "Tag not found.")
            except ConflictError as error:
                return app_error_response(req, error, str(error))
            tag = get_tag(connection, int(user_id), tag_id)
        if tag is None:
            return app_error_response(req, NotFoundError, "Tag not found.")
        return render_fragment(tag_settings_row(tag))

    @rt("/settings/tags/{tag_id}/delete")
    def post(req: Request, tag_id: int):
        """Deletes one of the user's tags and its links (§11.2.8); the row goes away."""
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(req, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            try:
                delete_tag(connection, int(user_id), tag_id)
            except NotFoundError:
                return app_error_response(req, NotFoundError, "Tag not found.")
        return HTMLResponse("")

    @rt("/settings/meal_type_schedule")
    def get(req):
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        return render_page(
            req,
            lambda connection: meal_type_schedule_settings_page(connection, int(user_id)),
            show_cart=False,
        )

    @rt("/settings/meal_type_schedule/update")
    def post(req: Request, meal_type: str = "", start_time: str = "", end_time: str = ""):
        """
        Autosave of a time slot (start_time and end_time always together, see
        the meal_type_schedule_row docstring). meal_type is restricted to
        AUTO_ASSIGNABLE_MEAL_TYPES: snack/rescue never have a slot here
        (decision 2026-09-11).
        """
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        try:
            parsed_meal_type = MealType(meal_type)
        except ValueError:
            return HTMLResponse(status_code=422)
        if parsed_meal_type not in AUTO_ASSIGNABLE_MEAL_TYPES:
            return HTMLResponse(status_code=422)
        try:
            parsed_start = datetime.strptime((start_time or "").strip(), "%H:%M").time()
            parsed_end = datetime.strptime((end_time or "").strip(), "%H:%M").time()
        except ValueError:
            return HTMLResponse(status_code=422)
        with get_connection() as connection:
            try:
                upsert_meal_type_window(
                    connection,
                    user_id=int(user_id),
                    meal_type=parsed_meal_type,
                    start_time=parsed_start,
                    end_time=parsed_end,
                )
            except ValidationError:
                return HTMLResponse(status_code=422)
            overrides = get_meal_type_schedule(connection, int(user_id))
        return render_fragment(
            meal_type_schedule_row(
                parsed_meal_type,
                *resolve_meal_type_window(parsed_meal_type, overrides),
                is_default=parsed_meal_type not in overrides,
            )
        )

    @rt("/settings/meal_type_schedule/reset")
    def post(req: Request, meal_type: str = ""):
        """Delete the customized slot: the row goes back to showing (and using) the code default."""
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        try:
            parsed_meal_type = MealType(meal_type)
        except ValueError:
            return HTMLResponse(status_code=422)
        if parsed_meal_type not in AUTO_ASSIGNABLE_MEAL_TYPES:
            return HTMLResponse(status_code=422)
        with get_connection() as connection:
            delete_meal_type_window(connection, user_id=int(user_id), meal_type=parsed_meal_type)
            overrides = get_meal_type_schedule(connection, int(user_id))
        return render_fragment(
            meal_type_schedule_row(
                parsed_meal_type,
                *resolve_meal_type_window(parsed_meal_type, overrides),
                is_default=True,
            )
        )

    @rt("/settings/injections")
    def get(req):
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        with get_connection() as connection:
            rows = list_insulin_injections(
                connection,
                user_id=int(user_id),
                limit=INJECTIONS_PAGE_SIZE,
                offset=0,
            )
            open_pens, pens_by_id = _injection_pens(connection, int(user_id), rows)
        first_chunk = injections_settings_chunk(
            rows=rows,
            offset=0,
            page_size=INJECTIONS_PAGE_SIZE,
            previous_day=None,
            open_pens=open_pens,
            pens_by_id=pens_by_id,
        )
        return render_page(req, lambda _: injections_settings_page(first_chunk), show_cart=False)

    @rt("/settings/injections/list")
    def get(req, offset: int = 0):
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        clean_offset = max(0, int(offset or 0))
        with get_connection() as connection:
            rows = list_insulin_injections(
                connection,
                user_id=int(user_id),
                limit=INJECTIONS_PAGE_SIZE,
                offset=clean_offset,
            )
            previous_shot = get_injection_shot_time_at_offset(
                connection,
                user_id=int(user_id),
                offset=clean_offset,
            )
            open_pens, pens_by_id = _injection_pens(connection, int(user_id), rows)
        previous_day = previous_shot.date() if previous_shot else None
        return injections_settings_chunk(
            rows=rows,
            offset=clean_offset,
            page_size=INJECTIONS_PAGE_SIZE,
            previous_day=previous_day,
            open_pens=open_pens,
            pens_by_id=pens_by_id,
        )

    @rt("/settings/injections/{injection_id}/delete")
    def post(req: Request, injection_id: int):
        """Delete an injection. Errors go through the visible error channel
        (error_conventions.md §7.1); success is `injectionUpdated`, which closes the
        pop-up and repaints the log."""
        if req.headers.get("HX-Request") != "true":
            return app_error_response(req, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(req, AuthenticationError, _NO_SESSION)
        with get_connection() as connection:
            try:
                delete_insulin_injection(connection, user_id=int(user_id), injection_id=int(injection_id))
            except NotFoundError:
                return app_error_response(req, NotFoundError, _INJECTION_GONE)
        return _injection_updated(f"settings_injection_delete_{injection_id}")

    @rt("/settings/injections/{injection_id}/update")
    def post(
        req: Request,
        injection_id: int,
        insulin_pen_id: str = "",
        units: str = "",
        zone: str = "",
        shot_hour: str = "",
        shot_date: str = "",
    ):
        """Edit an injection (frontend_conventions.md §9.9). A form error is 200 +
        message inside the pop-up (code §9.5); success is `injectionUpdated`."""
        if req.headers.get("HX-Request") != "true":
            return app_error_response(req, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(req, AuthenticationError, _NO_SESSION)
        # The pen ('' = keep an old injection without one), the zone, required in
        # this form, and the dose: optional for rapid, required for basal (§8.1).
        try:
            shot_time = local_naive_to_utc_aware(parse_shot_local(shot_hour, shot_date))
            pen_id = parse_optional_id(insulin_pen_id, "insulin_pen_id")
            injection_zone = parse_enum(InjectionZone, zone, field="zone", normalize=str.lower)
            if injection_zone is None:
                raise ValidationError("Choose the injection zone.", fields={"zone": "required"})
            units_value = parse_insulin_units(units)
        except ValidationError as error:
            return render_fragment(ModalFormError(str(error)))

        with get_connection() as connection:
            # The type is the one of the pen's brand (measurement §8.4); without a
            # pen, the injection keeps its own. The UPDATE checks the pen fits.
            current = get_insulin_injection(connection, int(user_id), int(injection_id))
            if current is None:
                return app_error_response(req, NotFoundError, _INJECTION_GONE)
            if pen_id is None:
                parsed_insulin_type = current.insulin_type
            else:
                pen = get_insulin_pen(connection, int(user_id), pen_id)
                if pen is None:
                    return app_error_response(req, NotFoundError, "That pen no longer exists.")
                parsed_insulin_type = pen.insulin_type
            payload = InsulinInjectionUpdate(
                insulin_type=parsed_insulin_type,
                shot_time=shot_time,
                injection_zone=injection_zone,
                units=units_value,
                insulin_pen_id=pen_id,
            )
            try:
                update_insulin_injection(
                    connection,
                    user_id=int(user_id),
                    injection_id=int(injection_id),
                    payload=payload,
                )
            except ValidationError as error:
                return render_fragment(ModalFormError(str(error)))
            except NotFoundError:
                # The row is there (read above): the chosen pen does not fit it.
                return render_fragment(ModalFormError("That pen is no longer in use. Choose another one."))
        return _injection_updated(f"settings_injection_edit_{injection_id}")
