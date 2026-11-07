"""Queries for the `intake_event` table, including the associated insulin
injection operations (H1, H2):

- create_injection_for_event (H1): automatically creates an injection when an event is confirmed
- set_injection_zone (H2): records the injection zone in the event draft
- set_event_insulin_pen / set_event_insulin_units: the pen and dose of the bolus
  in the draft (measurement §8.4), with set_event_default_pen and
  reassign_planned_events_pen for its default
"""

from dataclasses import fields as dataclass_fields
from datetime import date
from enum import Enum
from typing import Optional

from psycopg import sql

from DayBetes_food.database.mappers import intake_event_read_from_row
from DayBetes_food.database.queries.crud import (
    RawSQL,
    _build_update_query,
    _execute_query,
    _execute_query_many,
)
from DayBetes_food.database.queries.insulin_injections import create_insulin_injection
from DayBetes_food.database.queries.insulin_pen import DEFAULT_RAPID_PEN_SQL
from DayBetes_food.domain.constants import IntakeEventState, InsulinType, InjectionZone, MealType
from DayBetes_food.domain.intake_event import IntakeEventCreate, IntakeEventRead, IntakeEventUpdate
from DayBetes_food.domain.insulin import InsulinInjectionCreate, validate_insulin_dose
from DayBetes_food.errors import ConflictError, InfrastructureError, NotFoundError, ValidationError
from DayBetes_food.time_utils import local_today, utc_now, APP_TIMEZONE


_INTAKE_EVENT_COLUMNS = """
    id,
    users_id AS user_id,
    state,
    meal_type,
    name,
    meal_time,
    timezone_at_event,
    eating_out,
    insulin_dose,
    injection_zone,
    ingested_amount,
    amount_confidence,
    notes,
    created_at,
    updated_at,
    deleted_at,
    insulin_pen_id,
    insulin_units
"""


def set_injection_zone(
    connection,
    user_id: int,
    intake_event_id: int,
    zone: InjectionZone,
    *,
    commit: bool = True,
) -> bool:
    """Record the injection zone of an event (draft).

    Filters by user_id, event_id and insulin_dose=TRUE.
    Raises NotFoundError if the event does not exist or is not the user's.
    Raises ConflictError if the event carries no insulin.

    Args:
        connection: DB connection
        user_id: id of the user (ownership filter)
        intake_event_id: id of the event
        zone: InjectionZone to record
        commit: if True, commits the transaction

    Returns:
        True if it was updated

    Raises:
        NotFoundError: the event does not exist or is not the user's
        ConflictError: the event carries no insulin (insulin_dose = FALSE)
    """
    query = """
        UPDATE intake_event
        SET injection_zone = %(zone)s,
            updated_at = NOW()
        WHERE id = %(intake_event_id)s
          AND users_id = %(user_id)s
          AND insulin_dose = TRUE
          AND deleted_at IS NULL
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "intake_event_id": intake_event_id,
                    "user_id": user_id,
                    "zone": zone.value,
                },
            )
            row = cursor.fetchone()

        if row is None:
            # Find out why it failed
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, insulin_dose FROM intake_event WHERE id = %(id)s AND users_id = %(user_id)s AND deleted_at IS NULL;",
                    {"id": intake_event_id, "user_id": user_id},
                )
                check_row = cursor.fetchone()

            if check_row is None:
                raise NotFoundError(f"Intake event {intake_event_id} not found or not owned by user {user_id}")
            elif not check_row["insulin_dose"]:
                raise ConflictError("Event does not require insulin")
            else:
                raise InfrastructureError("Could not update intake event injection zone")

        if commit:
            connection.commit()
        return True

    except (NotFoundError, ConflictError):
        if commit:
            connection.rollback()
        raise
    except Exception:
        if commit:
            connection.rollback()
        raise


def _set_planned_insulin_draft(
    connection, user_id: int, intake_event_id: int, assignment: str, params: dict, *, commit: bool
) -> None:
    """UPDATE one field of the bolus draft of a planned event with insulin.

    Raises:
        NotFoundError: the event does not exist or is not the user's.
        ConflictError: it is not planned, or it carries no insulin.
    """
    query = f"""
        UPDATE intake_event
        SET {assignment},
            updated_at = NOW()
        WHERE id = %(intake_event_id)s
          AND users_id = %(user_id)s
          AND state = '{IntakeEventState.PLANNED.value}'
          AND insulin_dose = TRUE
          AND deleted_at IS NULL
        RETURNING id;
    """
    row = _execute_query(
        connection, query, {**params, "intake_event_id": intake_event_id, "user_id": user_id}, commit=commit
    )
    if row is None:
        event = get_intake_event(connection, user_id, intake_event_id)
        if event is None:
            raise NotFoundError(f"Intake event {intake_event_id} not found or not owned by user {user_id}")
        raise ConflictError("Event is not planned or does not carry insulin")


def set_event_insulin_pen(
    connection, user_id: int, intake_event_id: int, pen_id: int, *, commit: bool = True
) -> None:
    """Choose the pen of the bolus (measurement §8.4): an open rapid pen of the user,
    checked in the same UPDATE.

    Raises:
        NotFoundError: the event is not the user's, or the pen is not an open
            rapid pen of the user.
        ConflictError: the event is not planned or carries no insulin.
    """
    if get_open_rapid_pen_id(connection, user_id, pen_id) is None:
        raise NotFoundError("Pen not found.")
    _set_planned_insulin_draft(
        connection,
        user_id,
        intake_event_id,
        f"""insulin_pen_id = (
            SELECT p.id FROM insulin_pen p JOIN insulin_brand b ON b.id = p.insulin_brand_id
            WHERE p.id = %(pen_id)s AND p.users_id = %(user_id)s AND p.closed_at IS NULL
              AND b.insulin_type = '{InsulinType.RAPID.value}'
        )""",
        {"pen_id": pen_id},
        commit=commit,
    )


def get_open_rapid_pen_id(connection, user_id: int, pen_id: int) -> int | None:
    row = _execute_query(
        connection,
        f"""
        SELECT p.id FROM insulin_pen p JOIN insulin_brand b ON b.id = p.insulin_brand_id
        WHERE p.id = %(pen_id)s AND p.users_id = %(user_id)s AND p.closed_at IS NULL
          AND b.insulin_type = '{InsulinType.RAPID.value}';
        """,
        {"pen_id": pen_id, "user_id": user_id},
        commit=False,
    )
    return int(row["id"]) if row else None


def set_event_insulin_units(
    connection, user_id: int, intake_event_id: int, units: float | None, *, commit: bool = True
) -> None:
    """Dose of the bolus in U, or None for "not recorded" (measurement §8.1).

    Raises:
        ValidationError: not positive or not a multiple of 0.5 U.
        NotFoundError / ConflictError: as `_set_planned_insulin_draft`.
    """
    validate_insulin_dose(InsulinType.RAPID, units)
    _set_planned_insulin_draft(
        connection, user_id, intake_event_id, "insulin_units = %(units)s", {"units": units}, commit=commit
    )


def set_event_default_pen(connection, user_id: int, intake_event_id: int, *, commit: bool = True) -> None:
    """Give a planned event with insulin the default pen when it has none, e.g. when
    `insulin_dose` is turned on (measurement §8.4). A no-op otherwise."""
    _execute_query(
        connection,
        f"""
        UPDATE intake_event
        SET insulin_pen_id = {DEFAULT_RAPID_PEN_SQL},
            updated_at = NOW()
        WHERE id = %(intake_event_id)s
          AND users_id = %(user_id)s
          AND state = '{IntakeEventState.PLANNED.value}'
          AND insulin_dose = TRUE
          AND insulin_pen_id IS NULL
          AND deleted_at IS NULL
        RETURNING id;
        """,
        {"intake_event_id": intake_event_id, "user_id": user_id, "exclude_pen_id": None},
        commit=commit,
    )


def reassign_planned_events_pen(connection, user_id: int, pen_id: int, *, commit: bool = True) -> None:
    """Planned events of the user with `pen_id` go to the default pen without it,
    before the pen is closed or deleted (code §11.2.7)."""
    _execute_query_many(
        connection,
        f"""
        UPDATE intake_event
        SET insulin_pen_id = {DEFAULT_RAPID_PEN_SQL},
            updated_at = NOW()
        WHERE users_id = %(user_id)s
          AND insulin_pen_id = %(exclude_pen_id)s
          AND state = '{IntakeEventState.PLANNED.value}'
        RETURNING id;
        """,
        {"user_id": user_id, "exclude_pen_id": pen_id},
        commit=commit,
    )


def create_injection_for_event(
    connection,
    user_id: int,
    intake_event_id: int,
    *,
    commit: bool = True,
) -> int | None:
    """Automatically create an injection when an event is confirmed.

    Contract: if insulin_dose is TRUE a row is ALWAYS created; the zone is optional.
    If insulin_dose is FALSE it returns None and does nothing.

    Flow:
    1. Checks that the event exists and belongs to the user
    2. If insulin_dose=FALSE, returns None
    3. If insulin_dose=TRUE:
       - Takes the zone (it can be NULL), the pen and the dose from the event
       - Creates a RAPID injection; without a pen it raises ValidationError
       - Returns the id of the created injection

    Args:
        connection: DB connection
        user_id: id of the user (ownership filter)
        intake_event_id: id of the confirmed event
        commit: if True, commits the transaction

    Returns:
        id of the created injection, or None if the event carries no insulin

    Raises:
        NotFoundError: the event does not exist or is not the user's
        ValidationError: invalid zone in the database
        InfrastructureError: other errors
    """
    query = """
        SELECT id, users_id AS user_id, insulin_dose, injection_zone,
               meal_time, timezone_at_event, insulin_pen_id, insulin_units
        FROM intake_event
        WHERE id = %(intake_event_id)s
          AND users_id = %(user_id)s
          AND deleted_at IS NULL;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"intake_event_id": intake_event_id, "user_id": user_id},
            )
            row = cursor.fetchone()

        if row is None:
            raise NotFoundError(f"Intake event {intake_event_id} not found or not owned by user {user_id}")

        if not row["insulin_dose"]:
            return None

        # Process the zone (it can be NULL)
        raw_zone = (row.get("injection_zone") or "").strip()
        zone = None
        if raw_zone:
            try:
                zone = InjectionZone(raw_zone)
            except ValueError as exc:
                raise ValidationError("Invalid injection zone stored in intake event") from exc

        # Create the injection: rapid, with the pen and dose of the draft (§8.4).
        # Without an open pen of the user it cannot be logged: 422 for the cart.
        if row.get("insulin_pen_id") is None:
            raise ValidationError("Choose the pen you injected with.", fields={"insulin_pen_id": "required"})
        injection_payload = InsulinInjectionCreate(
            user_id=row["user_id"],
            intake_event_id=intake_event_id,
            shot_time=row["meal_time"] or utc_now(),
            timezone_at_event=row["timezone_at_event"] or APP_TIMEZONE.key,
            insulin_type=InsulinType.RAPID,
            units=row.get("insulin_units"),
            injection_zone=zone,
            insulin_pen_id=row["insulin_pen_id"],
        )
        try:
            return create_insulin_injection(connection, injection_payload, commit=commit)
        except NotFoundError as exc:
            # The pen of the draft was closed in the meantime.
            raise ValidationError(
                "That pen is no longer in use. Choose another one.", fields={"insulin_pen_id": "closed"}
            ) from exc

    except (NotFoundError, ValidationError):
        if commit:
            connection.rollback()
        raise
    except Exception:
        if commit:
            connection.rollback()
        raise


def confirm_intake_event(
    connection,
    user_id: int,
    event_id: int,
    *,
    commit: bool = True,
) -> int:
    """Move an event from planned to consumed. Ownership and idempotency live in the UPDATE.

    Returns the confirmed id.
    Raises:
        NotFoundError: the event does not exist or is not the user's.
        ConflictError: it exists and is the user's, but is no longer 'planned'.
    """
    query = """
        UPDATE intake_event
        SET state = %(new_state)s,
            updated_at = NOW()
        WHERE id = %(event_id)s
          AND users_id = %(user_id)s
          AND state = %(current_state)s
          AND deleted_at IS NULL
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "event_id": event_id,
                    "user_id": user_id,
                    "new_state": IntakeEventState.CONSUMED.value,
                    "current_state": IntakeEventState.PLANNED.value,
                },
            )
            row = cursor.fetchone()
        if row is None:
            # Ownership-protected check (§6.7): tells 404 from 409 without
            # revealing other users' events.
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM intake_event WHERE id = %(event_id)s AND users_id = %(user_id)s;",
                    {"event_id": event_id, "user_id": user_id},
                )
                owned = cursor.fetchone()
            if owned is None:
                raise NotFoundError(f"Intake event {event_id} not found or not owned by user {user_id}")
            raise ConflictError("Intake event is not in 'planned' state")
        if commit:
            connection.commit()
        return int(row["id"])
    except Exception:
        if commit:
            connection.rollback()
        raise


# ============================================
# CRUD operations (§3.3, §3.4, §5.3)
# ============================================

def create_intake_event(connection, payload: IntakeEventCreate, *, commit: bool = True) -> int:
    """Create an event and return its id (§3.3, §3.4).

    timezone_at_event is set to the application's zone: it is the zone in
    which meal_time was interpreted (§10.4).

    Raises:
        InfrastructureError: if the INSERT returns no row.
    """
    # The default pen of the bolus is written with the row, never guessed when
    # it is drawn (code §7.14, measurement §8.4).
    query = f"""
        INSERT INTO intake_event
            (users_id, state, meal_type, name, meal_time, timezone_at_event, insulin_pen_id)
        VALUES
            (%(user_id)s, %(state)s, %(meal_type)s, %(name)s,
             COALESCE(%(meal_time)s, CURRENT_TIMESTAMP), %(timezone_at_event)s, {DEFAULT_RAPID_PEN_SQL})
        RETURNING id;
    """
    params = {
        "exclude_pen_id": None,
        "user_id": payload.user_id,
        "state": payload.state.value,
        "meal_type": payload.meal_type.value if payload.meal_type else None,
        "name": payload.name,
        "meal_time": payload.meal_time,
        "timezone_at_event": APP_TIMEZONE.key,
    }
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        if row is None:
            raise InfrastructureError("Could not create intake event")
        if commit:
            connection.commit()
        return int(row["id"])
    except Exception:
        if commit:
            connection.rollback()
        raise


def get_intake_event(connection, user_id: int, event_id: int) -> IntakeEventRead | None:
    """Private read of an active event. None if it does not exist, is not the
    user's or is archived (§5.3, §5.4, §11.3)."""
    query = f"""
        SELECT {_INTAKE_EVENT_COLUMNS}
        FROM intake_event
        WHERE id = %(event_id)s
          AND users_id = %(user_id)s
          AND deleted_at IS NULL;
    """
    with connection.cursor() as cursor:
        cursor.execute(query, {"event_id": event_id, "user_id": user_id})
        row = cursor.fetchone()
    return intake_event_read_from_row(row) if row else None


def list_planned_intake_events(connection, user_id: int) -> list[IntakeEventRead]:
    """The user's 'planned' events (the cart), in a stable order (§11.9)."""
    query = f"""
        SELECT {_INTAKE_EVENT_COLUMNS}
        FROM intake_event
        WHERE users_id = %(user_id)s
          AND state = %(state)s
          AND deleted_at IS NULL
        ORDER BY meal_time DESC, id DESC;
    """
    rows = _execute_query_many(
        connection,
        query,
        {"user_id": user_id, "state": IntakeEventState.PLANNED.value},
        commit=False,
    )
    return [intake_event_read_from_row(row) for row in rows]


def list_consumed_intake_events_for_day(
    connection, user_id: int, day: date | None = None
) -> list[IntakeEventRead]:
    """Consumed events of one local calendar day of the user."""
    if day is None:
        day = local_today()
    query = f"""
        SELECT {_INTAKE_EVENT_COLUMNS}
        FROM intake_event
        WHERE users_id = %(user_id)s
          AND state = %(state)s
          AND deleted_at IS NULL
          AND DATE(meal_time AT TIME ZONE %(app_timezone)s) = %(day)s
        ORDER BY meal_time ASC, id ASC;
    """
    rows = _execute_query_many(
        connection,
        query,
        {
            "user_id": user_id,
            "state": IntakeEventState.CONSUMED.value,
            "day": day,
            "app_timezone": APP_TIMEZONE.key,
        },
        commit=False,
    )
    return [intake_event_read_from_row(row) for row in rows]


def list_consumed_intake_events(connection, user_id: int) -> list[IntakeEventRead]:
    """All the user's consumed events, in a stable order (§11.9)."""
    query = f"""
        SELECT {_INTAKE_EVENT_COLUMNS}
        FROM intake_event
        WHERE users_id = %(user_id)s
          AND state = %(state)s
          AND deleted_at IS NULL
        ORDER BY meal_time ASC, id ASC;
    """
    rows = _execute_query_many(
        connection,
        query,
        {"user_id": user_id, "state": IntakeEventState.CONSUMED.value},
        commit=False,
    )
    return [intake_event_read_from_row(row) for row in rows]


def update_intake_event(
    connection,
    user_id: int,
    event_id: int,
    data: IntakeEventUpdate,
    *,
    commit: bool = True,
) -> None:
    """Update fields of an active event of the user. Ownership lives in the SQL (§5.3).

    data: IntakeEventUpdate (§3.1); only the fields that really are the
    entity's editable ones. Fields set to None are ignored (behaviour of
    _build_update_query); update_intake_event_name exists to set name to
    NULL. The translation from dataclass to physical columns (including
    taking .value from the enums) happens at this single point instead of in
    every route.

    It does NOT filter by state: a 'consumed' event stays editable in all its
    fields (decision 2026-09-08), and the /confirm route updates the event
    when it is already 'consumed'. It does exclude archived ones
    (deleted_at IS NULL, §11.3).

    Raises:
        NotFoundError: the event does not exist, is not the user's or is archived.
    """
    payload = {}
    for field in dataclass_fields(data):
        value = getattr(data, field.name)
        if value is None:
            continue
        if isinstance(value, Enum):
            value = value.value
        payload[field.name] = value
    if not payload:
        return None

    params = {**payload, "id": event_id}
    query = _build_update_query(
        "intake_event",
        params,
        raw_fields={"updated_at": RawSQL.NOW},
        extra_where=sql.SQL("users_id = %(owner_user_id)s AND deleted_at IS NULL"),
    )
    if query is None:
        return None

    try:
        with connection.cursor() as cursor:
            cursor.execute(query, {**params, "owner_user_id": user_id})
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError(
                f"Intake event {event_id} not found or not owned by user {user_id}"
            )
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise


def update_intake_event_name(
    connection, user_id: int, event_id: int, name: str | None, *, commit: bool = True
) -> None:
    """Update the name of an active event of the user."""
    query = """
        UPDATE intake_event
        SET name = %(name)s,
            updated_at = NOW()
        WHERE id = %(event_id)s
          AND users_id = %(user_id)s
          AND deleted_at IS NULL
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"event_id": event_id, "user_id": user_id, "name": name},
            )
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError(
                f"Intake event {event_id} not found or not owned by user {user_id}"
            )
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise


def update_intake_event_notes(
    connection, user_id: int, event_id: int, notes: str | None, *, commit: bool = True
) -> None:
    """Update the notes of an active event of the user.

    A dedicated function, like update_intake_event_name and for the same
    reason: IntakeEventUpdate reads None as "leave untouched", so clearing a
    note (empty string -> NULL, §7.3) cannot be done that way.
    """
    query = """
        UPDATE intake_event
        SET notes = %(notes)s,
            updated_at = NOW()
        WHERE id = %(event_id)s
          AND users_id = %(user_id)s
          AND deleted_at IS NULL
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"event_id": event_id, "user_id": user_id, "notes": notes},
            )
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError(
                f"Intake event {event_id} not found or not owned by user {user_id}"
            )
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise


def delete_intake_event(connection, user_id: int, event_id: int, *, commit: bool = True) -> None:
    """PHYSICAL delete of a 'planned' event of the user.

    'planned' cannot be archived (decision 2026-09-08): discarding a cart is a
    legitimate delete. A 'consumed' event can be archived and can NOT be
    deleted this way: use archive_intake_event.

    If the deleted event had an associated injection, the FK
    insulin_injections.intake_event_id (ON DELETE SET NULL) keeps it,
    detached. That is the chosen behaviour, not a side effect.

    Raises:
        NotFoundError: it does not exist or is not the user's.
        ConflictError: it exists and is the user's, but is not 'planned'.
    """
    query = """
        DELETE FROM intake_event
        WHERE id = %(event_id)s
          AND users_id = %(user_id)s
          AND state = %(state)s
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "event_id": event_id,
                    "user_id": user_id,
                    "state": IntakeEventState.PLANNED.value,
                },
            )
            row = cursor.fetchone()
        if row is None:
            # Ownership-protected check (§5.4): tells 404 from 409 without
            # revealing other users' events.
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM intake_event "
                    "WHERE id = %(event_id)s AND users_id = %(user_id)s;",
                    {"event_id": event_id, "user_id": user_id},
                )
                owned = cursor.fetchone()
            if owned is None:
                raise NotFoundError(
                    f"Intake event {event_id} not found or not owned by user {user_id}"
                )
            raise ConflictError("Only planned intake events can be deleted; archive it instead")
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise


def archive_intake_event(connection, user_id: int, event_id: int, *, commit: bool = True) -> None:
    """Soft delete of a 'consumed' event of the user (§11.3).

    Archiving is an UPDATE, not a DELETE: the ON DELETE SET NULL FK of
    insulin_injections is NOT triggered and the injection keeps its meal
    context (decision 2026-09-08).

    Raises:
        NotFoundError: it does not exist or is not the user's.
        ConflictError: it is not 'consumed', or it was already archived.
    """
    query = """
        UPDATE intake_event
        SET deleted_at = NOW(),
            updated_at = NOW()
        WHERE id = %(event_id)s
          AND users_id = %(user_id)s
          AND state = %(state)s
          AND deleted_at IS NULL
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "event_id": event_id,
                    "user_id": user_id,
                    "state": IntakeEventState.CONSUMED.value,
                },
            )
            row = cursor.fetchone()
        if row is None:
            # Ownership-protected check
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM intake_event "
                    "WHERE id = %(event_id)s AND users_id = %(user_id)s;",
                    {"event_id": event_id, "user_id": user_id},
                )
                owned = cursor.fetchone()
            if owned is None:
                raise NotFoundError(
                    f"Intake event {event_id} not found or not owned by user {user_id}"
                )
            raise ConflictError("Intake event is not consumed or is already archived")
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise


def restore_intake_event(connection, user_id: int, event_id: int, *, commit: bool = True) -> None:
    """Undo the archiving (§11.3). There is no uniqueness to revalidate in this table.

    Raises:
        NotFoundError: it does not exist or is not the user's.
        ConflictError: it was not archived.
    """
    query = """
        UPDATE intake_event
        SET deleted_at = NULL,
            updated_at = NOW()
        WHERE id = %(event_id)s
          AND users_id = %(user_id)s
          AND deleted_at IS NOT NULL
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"event_id": event_id, "user_id": user_id},
            )
            row = cursor.fetchone()
        if row is None:
            # Ownership-protected check
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM intake_event "
                    "WHERE id = %(event_id)s AND users_id = %(user_id)s;",
                    {"event_id": event_id, "user_id": user_id},
                )
                owned = cursor.fetchone()
            if owned is None:
                raise NotFoundError(
                    f"Intake event {event_id} not found or not owned by user {user_id}"
                )
            raise ConflictError("Intake event is not archived")
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise


def get_planned_intake_event(connection, user_id: int, event_id: int) -> int:
    """Check that the event exists, is the user's, is active and is still 'planned'.

    Returns the event id. Ownership and state live inside the SQL (§5.3).

    Raises:
        NotFoundError: it does not exist, is not the user's or is archived.
        ConflictError: it is the user's but is no longer 'planned'.
    """
    query = """
        SELECT id, state
        FROM intake_event
        WHERE id = %(event_id)s
          AND users_id = %(user_id)s
          AND deleted_at IS NULL;
    """
    with connection.cursor() as cursor:
        cursor.execute(query, {"event_id": event_id, "user_id": user_id})
        row = cursor.fetchone()
    if row is None:
        raise NotFoundError(
            f"Intake event {event_id} not found or not owned by user {user_id}"
        )
    if row["state"] != IntakeEventState.PLANNED.value:
        raise ConflictError("Intake event is not in 'planned' state")
    return int(row["id"])
