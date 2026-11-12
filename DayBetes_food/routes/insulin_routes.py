"""Insulin pens and brands (code_conventions.md §11.2.7 and its HTMX contract in
§9.5, measurement_conventions.md §8.4, frontend_conventions.md §9.9)."""

import json

from fasthtml.common import *

from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.insulin_pen import NEW_OPTION_VALUE, pen_label
from DayBetes_food.components.modal import ModalFormError
from DayBetes_food.components.settings.insulin_settings import (
    insulin_brands_body,
    insulin_brands_page,
    insulin_menu_page,
    insulin_pens_body,
    insulin_pens_page,
)
from DayBetes_food.components.ui import render_fragment, render_page
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries import (
    create_insulin_brand,
    get_insulin_pen,
    list_insulin_brands,
    list_open_insulin_pens,
    update_insulin_brand,
    update_insulin_pen,
)
from DayBetes_food.domain.constants import InsulinType, PathId, PenFormat, parse_enum, parse_optional_id
from DayBetes_food.domain.insulin_pen import (
    InsulinBrandCreate,
    InsulinBrandUpdate,
    InsulinPenUpdate,
    expires_from_local_date,
    opened_at_from_local_date,
    parse_in_use_days,
    parse_insulin_brand_name,
    parse_pen_date,
    parse_pen_units,
)
from DayBetes_food.errors import AuthenticationError, AuthorizationError, ConflictError, NotFoundError, ValidationError
from DayBetes_food.http_errors import app_error_response
from DayBetes_food.services.insulin_pen import discard_insulin_pen, open_insulin_pen, remove_insulin_brand
from DayBetes_food.time_utils import local_naive_to_utc_aware, local_now, utc_now

_NOT_HTMX = "This action only works from the app."
_NO_SESSION = "Your session has expired."


def _required_enum(enum_cls, raw, field: str, message: str):
    value = parse_enum(enum_cls, raw, field=field)
    if value is None:
        raise ValidationError(message, fields={field: "required"})
    return value


def _brand_fields(name, insulin_type, in_use_days, pen_units) -> tuple:
    return (
        parse_insulin_brand_name(name),
        _required_enum(InsulinType, insulin_type, "insulin_type", "Choose the insulin type."),
        parse_in_use_days(in_use_days),
        parse_pen_units(pen_units),
    )


def _changed(modal_id: str | None = None) -> HTMLResponse:
    """Empty body and `insulinChanged`: the pop-up closes and the list is repainted."""
    detail = {"modal": modal_id} if modal_id else True
    return HTMLResponse("", headers={"HX-Trigger": json.dumps({"insulinChanged": detail})})


def setup_insulin_routes(rt):
    @rt("/settings/insulin")
    def get(req):
        """Menu of `Insulin pens`: Pens and Brands (frontend §9.9)."""
        return render_page(req, lambda _connection: insulin_menu_page(), show_cart=False)

    @rt("/settings/insulin/pens")
    def get(req):
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)

        def content(connection):
            return insulin_pens_page(
                list_open_insulin_pens(connection, int(user_id)),
                list_insulin_brands(connection, int(user_id)),
                utc_now(),
                local_now().date().isoformat(),
            )

        return render_page(req, content, show_cart=False)

    @rt("/settings/insulin/brands")
    def get(req):
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        return render_page(
            req, lambda connection: insulin_brands_page(list_insulin_brands(connection, int(user_id))), show_cart=False
        )

    @rt("/settings/insulin/pens/list")
    def get(request: Request):
        if request.headers.get("HX-Request") != "true":
            return app_error_response(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, _NO_SESSION)
        with get_connection() as connection:
            return render_fragment(
                insulin_pens_body(
                    list_open_insulin_pens(connection, int(user_id)),
                    list_insulin_brands(connection, int(user_id)),
                    utc_now(),
                    local_now().date().isoformat(),
                )
            )

    @rt("/settings/insulin/brands/list")
    def get(request: Request):
        if request.headers.get("HX-Request") != "true":
            return app_error_response(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, _NO_SESSION)
        with get_connection() as connection:
            return render_fragment(insulin_brands_body(list_insulin_brands(connection, int(user_id))))

    @rt("/insulin/pens")
    def post(
        request: Request,
        insulin_brand_id: str = "",
        brand_name: str = "",
        brand_insulin_type: str = "",
        brand_in_use_days: str = "",
        brand_pen_units: str = "",
        format: str = "",
        opened_date: str = "",
    ):
        """Open a pen, of an existing brand or a new one (frontend §9.9). Validation:
        200 + message in the pop-up; success: `penCreated`."""
        if request.headers.get("HX-Request") != "true":
            return app_error_response(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, _NO_SESSION)
        try:
            if (insulin_brand_id or "").strip() == NEW_OPTION_VALUE:
                name, insulin_type, days, units = _brand_fields(
                    brand_name, brand_insulin_type, brand_in_use_days, brand_pen_units
                )
                brand = InsulinBrandCreate(
                    user_id=int(user_id), name=name, insulin_type=insulin_type, in_use_days=days, pen_units=units
                )
            else:
                brand = parse_optional_id(insulin_brand_id, "insulin_brand_id")
                if brand is None:
                    raise ValidationError("Choose the brand.", fields={"insulin_brand_id": "required"})
            pen_format = _required_enum(PenFormat, format, "format", "Choose the format.")
            opened_local = opened_at_from_local_date(parse_pen_date(opened_date, "opened_date"), local_now())
        except ValidationError as error:
            return render_fragment(ModalFormError(str(error)))
        with get_connection() as connection:
            try:
                with connection.transaction():
                    pen_id = open_insulin_pen(
                        connection, int(user_id), brand, pen_format, local_naive_to_utc_aware(opened_local)
                    )
            except ValidationError as error:
                return render_fragment(ModalFormError(str(error)))
            except ConflictError as error:
                return render_fragment(ModalFormError(str(error)))
            except NotFoundError:
                return render_fragment(ModalFormError("That brand is no longer available."))
            pen = get_insulin_pen(connection, int(user_id), pen_id)
        trigger = {"penCreated": {"id": pen.id, "label": pen_label(pen), "insulin_type": pen.insulin_type.value}}
        return HTMLResponse("", headers={"HX-Trigger": json.dumps(trigger)})

    @rt("/insulin/pens/{pen_id}/update")
    def post(request: Request, pen_id: PathId, format: str = "", expires_date: str = "", capacity_units: str = ""):
        if request.headers.get("HX-Request") != "true":
            return app_error_response(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, _NO_SESSION)
        try:
            payload = InsulinPenUpdate(
                format=_required_enum(PenFormat, format, "format", "Choose the format."),
                expires_at=local_naive_to_utc_aware(
                    expires_from_local_date(parse_pen_date(expires_date, "expires_date"))
                ),
                capacity_units=parse_pen_units(capacity_units, "capacity_units"),
            )
        except ValidationError as error:
            return render_fragment(ModalFormError(str(error)))
        with get_connection() as connection:
            try:
                update_insulin_pen(connection, int(user_id), pen_id, payload)
            except ValidationError as error:
                return render_fragment(ModalFormError(str(error)))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That pen is no longer in use.")
        return _changed(f"insulin_pen_edit_{pen_id}")

    @rt("/insulin/pens/{pen_id}/discard")
    def post(request: Request, pen_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return app_error_response(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, _NO_SESSION)
        with get_connection() as connection:
            try:
                with connection.transaction():
                    discard_insulin_pen(connection, int(user_id), pen_id)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That pen is no longer in use.")
        return _changed(f"insulin_pen_discard_{pen_id}")

    @rt("/insulin/brands")
    def post(request: Request, name: str = "", insulin_type: str = "", in_use_days: str = "", pen_units: str = ""):
        if request.headers.get("HX-Request") != "true":
            return app_error_response(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, _NO_SESSION)
        try:
            name, parsed_type, days, units = _brand_fields(name, insulin_type, in_use_days, pen_units)
        except ValidationError as error:
            return render_fragment(ModalFormError(str(error)))
        with get_connection() as connection:
            try:
                create_insulin_brand(
                    connection,
                    InsulinBrandCreate(
                        user_id=int(user_id), name=name, insulin_type=parsed_type, in_use_days=days, pen_units=units
                    ),
                )
            except ConflictError as error:
                return render_fragment(ModalFormError(str(error)))
        return _changed("insulin_brand_new")

    @rt("/insulin/brands/{brand_id}/update")
    def post(
        request: Request, brand_id: PathId, name: str = "", insulin_type: str = "", in_use_days: str = "", pen_units: str = ""
    ):
        if request.headers.get("HX-Request") != "true":
            return app_error_response(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, _NO_SESSION)
        try:
            name, parsed_type, days, units = _brand_fields(name, insulin_type, in_use_days, pen_units)
        except ValidationError as error:
            return render_fragment(ModalFormError(str(error)))
        with get_connection() as connection:
            try:
                update_insulin_brand(
                    connection,
                    int(user_id),
                    brand_id,
                    InsulinBrandUpdate(name=name, insulin_type=parsed_type, in_use_days=days, pen_units=units),
                )
            except ConflictError as error:
                return render_fragment(ModalFormError(str(error)))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That brand no longer exists.")
        return _changed(f"insulin_brand_edit_{brand_id}")

    @rt("/insulin/brands/{brand_id}/delete")
    def post(request: Request, brand_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return app_error_response(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, _NO_SESSION)
        with get_connection() as connection:
            try:
                with connection.transaction():
                    remove_insulin_brand(connection, int(user_id), brand_id)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That brand no longer exists.")
        return _changed(f"insulin_brand_delete_{brand_id}")
