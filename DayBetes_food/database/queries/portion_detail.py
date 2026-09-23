"""Queries for the `portion_detail` table.

Rewritten in T2 of `audit/plan.md` (option A, decision 2026-09-22): the unit of
edition is the row (`portion_id`), not a "group". The unique index of
`measurement_conventions.md` 4.6.4 already guarantees one row per
`(plate, origin, preparation)`, so the old group helpers existed only to repair
duplicates the insert no longer creates.

Every function receives `user_id` and enforces ownership inside the SQL
(code_conventions.md 5.3, 6.9): the row is not read and then filtered in
Python. A row that does not exist or does not belong to the user raises
`NotFoundError`.
"""

from psycopg import sql

from DayBetes_food.database.mappers import portion_detail_read_from_row
from DayBetes_food.database.queries.crud import (
    RawSQL,
    _build_update_query,
    _execute_query,
    _execute_query_many,
)
from DayBetes_food.domain.constants import CLEAR, PortionDestination, PortionOrigin
from DayBetes_food.domain.portion_detail import (
    PORTION_DETAIL_OFFSET_MAX_MINUTES,
    PORTION_DETAIL_OFFSET_MIN_MINUTES,
    PortionDetailCreate,
    PortionDetailRead,
    PortionDetailUpdate,
    parse_amount_grams,
    validate_preparation_choice,
)
from DayBetes_food.errors import NotFoundError, ValidationError


_PREPARATION_FIELDS = ("cooking", "conservation", "final_state")
_FLAG_FIELDS = ("strictly_weighed", "macros_quality", "is_cooked_weight")

# Enum-keyed (T2.1): dynamic column composition uses `sql.Identifier` with
# this whitelist, never an f-string built from caller input.
_PORTION_ORIGIN_COLUMNS = {
    PortionOrigin.CATALOG: "catalog_id",
    PortionOrigin.MANUAL_INTAKE: "manual_intake_id",
}

_DESTINATION_TABLE = {
    PortionDestination.INTAKE_EVENT: "intake_event",
    PortionDestination.RECIPE: "recipe",
    PortionDestination.FRIDGE: "fridge",
}

# Explicit column list: the read contract is declared, not inherited from the
# physical table (finding 13).
_PORTION_COLUMNS = """
    pd.id,
    pd.catalog_id,
    pd.manual_intake_id,
    pd.intake_event_id,
    pd.recipe_id,
    pd.fridge_id,
    pd.plate_id,
    pd.amount,
    pd.cooking,
    pd.conservation,
    pd.final_state,
    pd.strictly_weighed,
    pd.macros_quality,
    pd.is_cooked_weight,
    pd.offset_minutes,
    pd.created_at,
    pd.updated_at,
    COALESCE(c.name, im.name) AS source_name,
    COALESCE(c.default_portion, im.amount_g) AS source_unit_g,
    c.category AS source_category,
    im.subtype AS source_subtype,
    c.cooking_factor AS source_cooking_factor,
    COALESCE(c.calories_100g, im.calories_100g) AS source_calories_100g,
    COALESCE(c.carbs_100g, im.carbs_100g) AS source_carbs_100g,
    COALESCE(c.sugars_100g, im.sugars_100g) AS source_sugars_100g,
    COALESCE(c.fats_100g, im.fats_100g) AS source_fats_100g,
    COALESCE(c.saturated_100g, im.saturated_100g) AS source_saturated_100g,
    COALESCE(c.proteins_100g, im.proteins_100g) AS source_proteins_100g,
    COALESCE(c.fiber_100g, im.fiber_100g) AS source_fiber_100g
"""
_PORTION_FROM = """
    FROM portion_detail pd
    LEFT JOIN catalog c ON pd.catalog_id = c.id
    LEFT JOIN manual_intake im ON pd.manual_intake_id = im.id
"""

# Ownership of the destination arc (5.3, 6.9). Written once: every read and
# mutation appends it to its WHERE. The `fridge` branch is included although it
# has no writer yet: it is a condition of the model, and omitting it would make
# fridge portions invisible to their own owner the day the branch exists.
_PORTION_OWNED_BY_USER = """
    AND (
        EXISTS (
            SELECT 1 FROM intake_event ie
            WHERE ie.id = pd.intake_event_id
              AND ie.users_id = %(user_id)s
              AND ie.deleted_at IS NULL
        )
        OR EXISTS (
            SELECT 1 FROM recipe r
            WHERE r.id = pd.recipe_id AND r.users_id = %(user_id)s
        )
        OR EXISTS (
            SELECT 1 FROM fridge f
            WHERE f.id = pd.fridge_id AND f.users_id = %(user_id)s
        )
    )
"""

# Visibility of a recipe portion for reading it (5.4): a public recipe
# (is_private = FALSE) is readable by anyone, but only its owner may mutate it.
# This fragment is used by list_viewable_recipe_portions and never by a
# mutation.
_PORTION_VISIBLE_RECIPE = """
    AND EXISTS (
        SELECT 1 FROM recipe r
        WHERE r.id = pd.recipe_id
          AND (r.users_id = %(user_id)s OR r.is_private = FALSE)
    )
"""


def _rows_to_reads(rows) -> list[PortionDetailRead]:
    return [portion_detail_read_from_row(row) for row in (rows or [])]


def _execute_write(connection, query, params: dict, commit: bool):
    """Run one write and propagate any SQL failure (error_conventions.md 11).

    The generic helper, in owner mode (`commit=True`), rolls back and returns
    `None`; the callers here read `None` as "no row matched" and would turn an
    infrastructure failure into a `NotFoundError` (a 404 for a server fault,
    finding 5). Here the owner rolls back and the exception propagates; in
    caller-owned mode (`commit=False`) it propagates without rollback (2.4).
    """
    try:
        return _execute_query(connection, query, params, commit=commit, rollback_on_error=False)
    except Exception:
        if commit:
            connection.rollback()
        raise


def _ensure_destination_owned(connection, user_id: int, destination: PortionDestination, destination_id: int) -> None:
    table = _DESTINATION_TABLE.get(destination)
    if table is None:
        raise ValidationError("invalid_destination")
    archived = " AND deleted_at IS NULL" if destination is PortionDestination.INTAKE_EVENT else ""
    query = sql.SQL(
        "SELECT 1 AS ok FROM {} WHERE id = %(id)s AND users_id = %(user_id)s" + archived + ";"
    ).format(sql.Identifier(table))
    row = _execute_query(
        connection, query, {"id": destination_id, "user_id": user_id}, commit=False
    )
    if not row:
        raise NotFoundError("portion_destination_not_found")


def _plate_row(connection, plate_id: int):
    return _execute_query(
        connection,
        "SELECT intake_event_id, offset_minutes FROM intake_plate WHERE id = %(plate_id)s;",
        {"plate_id": plate_id},
        commit=False,
    )


def create_portion_detail(connection, user_id: int, payload: PortionDetailCreate, commit: bool = True) -> int:
    """Insert one portion, merging into an existing row when the key matches (4.6.4).

    The key includes `is_cooked_weight` (decision 2026-09-23). The existing
    row wins: its data quality flags and offset are kept, only `amount` is
    summed (decision 2026-09-19).
    """
    amount = parse_amount_grams(payload.amount)
    cooking = validate_preparation_choice("cooking", payload.cooking)
    conservation = validate_preparation_choice("conservation", payload.conservation)
    final_state = validate_preparation_choice("final_state", payload.final_state)

    origin = PortionOrigin(payload.origin)
    destination = PortionDestination(payload.destination)
    is_event = destination is PortionDestination.INTAKE_EVENT

    if is_event and payload.plate_id is None:
        raise ValidationError("plate_required")
    if not is_event and payload.plate_id is not None:
        raise ValidationError("plate_only_for_event")
    if payload.offset_minutes is not None and not is_event:
        raise ValidationError("offset_only_for_event")

    _ensure_destination_owned(connection, user_id, destination, payload.destination_id)

    offset_minutes = payload.offset_minutes
    if is_event:
        plate = _plate_row(connection, payload.plate_id)
        if not plate or int(plate["intake_event_id"]) != int(payload.destination_id):
            raise NotFoundError("portion_plate_not_found")
        if offset_minutes is None:
            offset_minutes = plate["offset_minutes"]

    data = {
        "amount": amount,
        "catalog_id": payload.origin_id if origin is PortionOrigin.CATALOG else None,
        "manual_intake_id": payload.origin_id if origin is PortionOrigin.MANUAL_INTAKE else None,
        "intake_event_id": payload.destination_id if is_event else None,
        "recipe_id": payload.destination_id if destination is PortionDestination.RECIPE else None,
        "fridge_id": payload.destination_id if destination is PortionDestination.FRIDGE else None,
        "plate_id": payload.plate_id,
        "cooking": cooking,
        "conservation": conservation,
        "final_state": final_state,
        "strictly_weighed": payload.strictly_weighed,
        "macros_quality": payload.macros_quality,
        "is_cooked_weight": bool(payload.is_cooked_weight),
        "offset_minutes": offset_minutes,
    }

    # ON CONFLICT over the partial unique index of 4.6.4: the inference needs to
    # repeat its WHERE. Recipe and fridge portions have plate_id NULL, do not
    # enter the index and therefore never merge.
    query = """
        INSERT INTO portion_detail (
            amount, catalog_id, manual_intake_id,
            intake_event_id, recipe_id, fridge_id, plate_id,
            cooking, conservation, final_state,
            strictly_weighed, macros_quality,
            is_cooked_weight, offset_minutes
        )
        VALUES (
            %(amount)s, %(catalog_id)s, %(manual_intake_id)s,
            %(intake_event_id)s, %(recipe_id)s, %(fridge_id)s, %(plate_id)s,
            %(cooking)s, %(conservation)s, %(final_state)s,
            %(strictly_weighed)s, %(macros_quality)s,
            %(is_cooked_weight)s, %(offset_minutes)s
        )
        ON CONFLICT (plate_id, catalog_id, manual_intake_id, cooking, conservation, final_state, is_cooked_weight)
        WHERE plate_id IS NOT NULL
        DO UPDATE SET
            amount = portion_detail.amount + EXCLUDED.amount,
            updated_at = NOW()
        RETURNING id;
    """
    result = _execute_write(connection, query, data, commit)
    if not result:
        raise NotFoundError("portion_not_found")
    return int(result["id"])


def get_portion_detail(connection, user_id: int, portion_id: int) -> PortionDetailRead:
    query = f"""
        SELECT {_PORTION_COLUMNS}
        {_PORTION_FROM}
        WHERE pd.id = %(portion_id)s
        {_PORTION_OWNED_BY_USER};
    """
    row = _execute_query(
        connection, query, {"portion_id": portion_id, "user_id": user_id}, commit=False
    )
    if not row:
        raise NotFoundError("portion_not_found")
    return portion_detail_read_from_row(row)


def list_portions_by_event(connection, user_id: int, event_id: int) -> list[PortionDetailRead]:
    query = f"""
        SELECT {_PORTION_COLUMNS}
        {_PORTION_FROM}
        WHERE pd.intake_event_id = %(event_id)s
        {_PORTION_OWNED_BY_USER}
        ORDER BY pd.id;
    """
    rows = _execute_query_many(
        connection, query, {"event_id": event_id, "user_id": user_id}, commit=False
    )
    return _rows_to_reads(rows)


def list_portions_by_events(connection, user_id: int, event_ids: list[int]) -> list[PortionDetailRead]:
    if not event_ids:
        return []
    query = f"""
        SELECT {_PORTION_COLUMNS}
        {_PORTION_FROM}
        WHERE pd.intake_event_id = ANY(%(event_ids)s)
        {_PORTION_OWNED_BY_USER}
        ORDER BY pd.intake_event_id, pd.id;
    """
    rows = _execute_query_many(
        connection, query, {"event_ids": event_ids, "user_id": user_id}, commit=False
    )
    return _rows_to_reads(rows)


def list_portions_by_recipe(connection, user_id: int, recipe_id: int) -> list[PortionDetailRead]:
    query = f"""
        SELECT {_PORTION_COLUMNS}
        {_PORTION_FROM}
        WHERE pd.recipe_id = %(recipe_id)s
        {_PORTION_OWNED_BY_USER}
        ORDER BY pd.id;
    """
    rows = _execute_query_many(
        connection, query, {"recipe_id": recipe_id, "user_id": user_id}, commit=False
    )
    return _rows_to_reads(rows)


def list_recipe_portions_by_origin(
    connection, user_id: int, recipe_id: int, origin: PortionOrigin, origin_id: int
) -> list[PortionDetailRead]:
    origin = PortionOrigin(origin)
    origin_column = _PORTION_ORIGIN_COLUMNS[origin]
    query = sql.SQL(
        """
        SELECT {columns}
        {from_clause}
        WHERE pd.recipe_id = %(recipe_id)s AND pd.{origin_column} = %(origin_id)s
        {owned}
        ORDER BY pd.id;
        """
    ).format(
        columns=sql.SQL(_PORTION_COLUMNS),
        from_clause=sql.SQL(_PORTION_FROM),
        origin_column=sql.Identifier(origin_column),
        owned=sql.SQL(_PORTION_OWNED_BY_USER),
    )
    rows = _execute_query_many(
        connection,
        query,
        {"recipe_id": recipe_id, "origin_id": origin_id, "user_id": user_id},
        commit=False,
    )
    return _rows_to_reads(rows)


def list_viewable_recipe_portions(connection, user_id: int, recipe_id: int) -> list[PortionDetailRead]:
    """Portions of a recipe the user may view, owned or public (5.4).

    A recipe can be public (`is_private = FALSE`) and therefore not owned by
    the user: showing it, computing its macros, logging it or copying it
    requires viewability, not ownership. `list_portions_by_recipe` stays for
    the owner-only flows (editing the recipe). Every write still goes through
    a function that checks ownership, so this read cannot mutate anything.
    """
    query = f"""
        SELECT {_PORTION_COLUMNS}
        {_PORTION_FROM}
        WHERE pd.recipe_id = %(recipe_id)s
        {_PORTION_VISIBLE_RECIPE}
        ORDER BY pd.id;
    """
    rows = _execute_query_many(
        connection, query, {"recipe_id": recipe_id, "user_id": user_id}, commit=False
    )
    return _rows_to_reads(rows)


def update_portion_amount(connection, user_id: int, portion_id: int, amount: float, commit: bool = True) -> None:
    grams = parse_amount_grams(amount)
    query = f"""
        UPDATE portion_detail pd
        SET amount = %(amount)s, updated_at = NOW()
        WHERE pd.id = %(portion_id)s
        {_PORTION_OWNED_BY_USER}
        RETURNING pd.id;
    """
    result = _execute_write(
        connection,
        query,
        {"amount": grams, "portion_id": portion_id, "user_id": user_id},
        commit,
    )
    if not result:
        raise NotFoundError("portion_not_found")


def update_portion_offset(connection, user_id: int, portion_id: int, offset_minutes, commit: bool = True) -> None:
    if offset_minutes is not None and not (
        PORTION_DETAIL_OFFSET_MIN_MINUTES <= offset_minutes <= PORTION_DETAIL_OFFSET_MAX_MINUTES
    ):
        raise ValidationError("offset_out_of_range")
    query = f"""
        UPDATE portion_detail pd
        SET offset_minutes = %(offset_minutes)s, updated_at = NOW()
        WHERE pd.id = %(portion_id)s
        {_PORTION_OWNED_BY_USER}
        RETURNING pd.id;
    """
    result = _execute_write(
        connection,
        query,
        {"offset_minutes": offset_minutes, "portion_id": portion_id, "user_id": user_id},
        commit,
    )
    if not result:
        raise NotFoundError("portion_not_found")


def update_portion_flag(connection, user_id: int, portion_id: int, field: str, value, commit: bool = True) -> None:
    """Write one data quality flag of a portion.

    `is_cooked_weight` is part of the uniqueness key (4.6.4, decision
    2026-09-23): if the new value makes the row equal to another one of the
    same plate, the amounts are summed there instead of writing the flag.
    """
    if field not in _FLAG_FIELDS:
        raise ValidationError("invalid_portion_flag")
    if field == "is_cooked_weight":
        current = get_portion_detail(connection, user_id, portion_id)
        if current.plate_id is not None:
            sibling_id = _find_preparation_sibling(
                connection,
                user_id,
                current,
                current.plate_id,
                current.cooking,
                current.conservation,
                current.final_state,
                bool(value),
            )
            if sibling_id is not None:
                _merge_into_sibling(connection, user_id, portion_id, sibling_id, commit)
                return
    query = sql.SQL(
        """
        UPDATE portion_detail pd
        SET {field} = %(value)s, updated_at = NOW()
        WHERE pd.id = %(portion_id)s
        {owned}
        RETURNING pd.id;
        """
    ).format(
        field=sql.Identifier(field),
        owned=sql.SQL(_PORTION_OWNED_BY_USER),
    )
    result = _execute_write(
        connection,
        query,
        {"value": value, "portion_id": portion_id, "user_id": user_id},
        commit,
    )
    if not result:
        raise NotFoundError("portion_not_found")


def _find_preparation_sibling(
    connection,
    user_id: int,
    portion: PortionDetailRead,
    plate_id: int,
    cooking,
    conservation,
    final_state,
    is_cooked_weight: bool,
):
    query = f"""
        SELECT pd.id
        {_PORTION_FROM}
        WHERE pd.plate_id = %(plate_id)s
          AND pd.id <> %(portion_id)s
          AND pd.catalog_id IS NOT DISTINCT FROM %(catalog_id)s
          AND pd.manual_intake_id IS NOT DISTINCT FROM %(manual_intake_id)s
          AND pd.cooking IS NOT DISTINCT FROM %(cooking)s
          AND pd.conservation IS NOT DISTINCT FROM %(conservation)s
          AND pd.final_state IS NOT DISTINCT FROM %(final_state)s
          AND pd.is_cooked_weight IS NOT DISTINCT FROM %(is_cooked_weight)s
        {_PORTION_OWNED_BY_USER}
        LIMIT 1;
    """
    params = {
        "plate_id": plate_id,
        "portion_id": portion.id,
        "catalog_id": portion.origin_id if portion.origin is PortionOrigin.CATALOG else None,
        "manual_intake_id": portion.origin_id if portion.origin is PortionOrigin.MANUAL_INTAKE else None,
        "cooking": cooking,
        "conservation": conservation,
        "final_state": final_state,
        "is_cooked_weight": bool(is_cooked_weight),
        "user_id": user_id,
    }
    row = _execute_query(connection, query, params, commit=False)
    return int(row["id"]) if row else None


def _merge_into_sibling(connection, user_id: int, portion_id: int, sibling_id: int, commit: bool) -> None:
    """Sum `amount` into the sibling and delete the edited row (decision 2026-09-20).

    Both statements are one operation (2.3): in owner mode they are committed
    together or rolled back together. Ownership is in the SQL of both (5.3),
    although the caller already resolved the two rows through it.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE portion_detail pd
                SET amount = pd.amount + a.amount,
                    updated_at = NOW()
                FROM portion_detail a
                WHERE pd.id = %(sibling_id)s AND a.id = %(portion_id)s
                {_PORTION_OWNED_BY_USER};
                """,
                {"sibling_id": sibling_id, "portion_id": portion_id, "user_id": user_id},
            )
            if cursor.rowcount != 1:
                raise NotFoundError("portion_not_found")
            cursor.execute(
                f"""
                DELETE FROM portion_detail pd
                WHERE pd.id = %(portion_id)s
                {_PORTION_OWNED_BY_USER};
                """,
                {"portion_id": portion_id, "user_id": user_id},
            )
            if cursor.rowcount != 1:
                raise NotFoundError("portion_not_found")
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise


def update_portion_detail_fields(
    connection, user_id: int, portion_id: int, data: PortionDetailUpdate, commit: bool = True
) -> bool:
    """Partial update of the three preparation fields (findings 15).

    `None` means "absent, do not touch"; `CLEAR` means "present but empty,
    write NULL" (7.4). Returns `False` only for the idempotent no-op "there was
    nothing to update", never for an error (3.4).
    """
    params = {"id": portion_id}
    null_fields = set()
    resolved = {}
    for field in _PREPARATION_FIELDS:
        value = getattr(data, field)
        if value is None:
            continue
        if value is CLEAR:
            params[field] = None
            null_fields.add(field)
            resolved[field] = None
        else:
            params[field] = validate_preparation_choice(field, value)
            resolved[field] = params[field]
    if len(params) == 1:
        return False

    current = get_portion_detail(connection, user_id, portion_id)
    if current.plate_id is not None:
        sibling_id = _find_preparation_sibling(
            connection,
            user_id,
            current,
            current.plate_id,
            resolved.get("cooking", current.cooking),
            resolved.get("conservation", current.conservation),
            resolved.get("final_state", current.final_state),
            current.is_cooked_weight,
        )
        if sibling_id is not None:
            _merge_into_sibling(connection, user_id, portion_id, sibling_id, commit)
            return True

    query = _build_update_query(
        "portion_detail",
        params,
        null_fields=null_fields,
        raw_fields={"updated_at": RawSQL.NOW},
        extra_where=sql.SQL(_PORTION_OWNED_BY_USER),
    )
    if query is None:
        return False
    params["user_id"] = user_id
    result = _execute_write(connection, query, params, commit)
    if not result:
        raise NotFoundError("portion_not_found")
    return True


def move_portion_to_plate(connection, user_id: int, portion_id: int, target_plate_id: int, commit: bool = True) -> None:
    """Move one portion to another plate of the same event (4.6.5).

    If the target plate already contains that food with the same preparation,
    the amounts are summed in the existing row (4.6.4). `offset_minutes` is not
    touched: the offset the portion inherited stays.
    """
    current = get_portion_detail(connection, user_id, portion_id)
    if current.plate_id is None:
        raise ValidationError("portion_without_plate")
    if int(target_plate_id) == int(current.plate_id):
        return
    target = _plate_row(connection, target_plate_id)
    if not target or int(target["intake_event_id"]) != int(current.destination_id):
        raise NotFoundError("portion_plate_not_found")

    sibling_id = _find_preparation_sibling(
        connection,
        user_id,
        current,
        target_plate_id,
        current.cooking,
        current.conservation,
        current.final_state,
        current.is_cooked_weight,
    )
    if sibling_id is not None:
        _merge_into_sibling(connection, user_id, portion_id, sibling_id, commit)
        return

    query = f"""
        UPDATE portion_detail pd
        SET plate_id = %(target_plate_id)s, updated_at = NOW()
        WHERE pd.id = %(portion_id)s
        {_PORTION_OWNED_BY_USER}
        RETURNING pd.id;
    """
    result = _execute_write(
        connection,
        query,
        {"target_plate_id": target_plate_id, "portion_id": portion_id, "user_id": user_id},
        commit,
    )
    if not result:
        raise NotFoundError("portion_not_found")


def delete_portion_detail(connection, user_id: int, portion_id: int, commit: bool = True) -> None:
    query = f"""
        DELETE FROM portion_detail pd
        WHERE pd.id = %(portion_id)s
        {_PORTION_OWNED_BY_USER}
        RETURNING pd.id;
    """
    result = _execute_write(
        connection, query, {"portion_id": portion_id, "user_id": user_id}, commit
    )
    if not result:
        raise NotFoundError("portion_not_found")


def scale_event_portion_amounts(connection, user_id: int, event_id: int, fraction: float, commit: bool = True) -> bool:
    """Scale every portion of an event by `fraction` (confirm flow, 4.4/6.9.1).

    Single SQL statement over all portions, not a Python loop. `fraction` is in
    (0, 1] since decision 2026-09-22: a confirm that ate nothing is rejected
    with 422 before reaching here. The ownership filter is inside the SQL.
    """
    if not (0.0 < fraction <= 1.0):
        raise ValidationError("invalid_fraction")
    query = """
        UPDATE portion_detail pd
        SET amount = pd.amount * %(fraction)s,
            updated_at = NOW()
        WHERE pd.intake_event_id = %(event_id)s
          AND EXISTS (
              SELECT 1 FROM intake_event ie
              WHERE ie.id = pd.intake_event_id AND ie.users_id = %(user_id)s
          );
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, {"fraction": fraction, "event_id": event_id, "user_id": user_id})
            updated = cursor.rowcount
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise
    return updated > 0
