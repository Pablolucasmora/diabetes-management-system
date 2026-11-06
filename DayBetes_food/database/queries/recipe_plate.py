"""Queries for the `recipe_plate` table (measurement_conventions.md §4.7).

Ownership travels inside the SQL (§5.3). A plate has no meaning outside its recipe,
so reads follow the recipe's visibility and writes require its owner.
"""

from psycopg.errors import ForeignKeyViolation

from DayBetes_food.database.mappers import recipe_plate_read_from_row
from DayBetes_food.database.queries.crud import _execute_query, _execute_query_many
from DayBetes_food.domain.recipe_plate import RecipePlateRead
from DayBetes_food.errors import ConflictError, NotFoundError

_COLUMNS = "rp.id, rp.recipe_id, rp.position, rp.name, rp.created_at, rp.updated_at"


def _lock_owned_recipe(connection, user_id: int, recipe_id: int) -> None:
    """Lock the user's recipe, so the writes on its plates queue instead of colliding
    on their positions or racing with its deletion (§6.6).

    Raises:
        NotFoundError: it does not exist or is not the user's.
    """
    row = _execute_query(
        connection,
        "SELECT r.id FROM recipe r WHERE r.id = %(recipe_id)s AND r.users_id = %(user_id)s FOR UPDATE;",
        {"recipe_id": recipe_id, "user_id": user_id},
        commit=False,
    )
    if row is None:
        raise NotFoundError("Recipe not found.")


def _insert_recipe_plate(connection, recipe_id: int, name: str | None, commit: bool) -> int:
    row = _execute_query(
        connection,
        """
        INSERT INTO recipe_plate (recipe_id, position, name)
        SELECT %(recipe_id)s, COALESCE(MAX(rp.position), 0) + 1, %(name)s
        FROM recipe_plate rp
        WHERE rp.recipe_id = %(recipe_id)s
        RETURNING id;
        """,
        {"recipe_id": recipe_id, "name": name},
        commit=commit,
    )
    return int(row["id"])


def create_recipe_plate(
    connection, user_id: int, recipe_id: int, *, name: str | None = None, commit: bool = True
) -> int:
    """Add a plate at the end of one of the user's recipes.

    Raises:
        NotFoundError: the recipe does not exist or is not the user's.
    """
    _lock_owned_recipe(connection, user_id, recipe_id)
    return _insert_recipe_plate(connection, recipe_id, name, commit)


def ensure_default_recipe_plate(connection, user_id: int, recipe_id: int, commit: bool = True) -> int:
    """The last plate of one of the user's recipes or, if it has none, a first one
    created implicitly (measurement_conventions.md §4.7).

    Raises:
        NotFoundError: the recipe does not exist or is not the user's.
    """
    _lock_owned_recipe(connection, user_id, recipe_id)
    row = _execute_query(
        connection,
        "SELECT rp.id FROM recipe_plate rp WHERE rp.recipe_id = %(recipe_id)s ORDER BY rp.position DESC LIMIT 1;",
        {"recipe_id": recipe_id},
        commit=False,
    )
    return int(row["id"]) if row else _insert_recipe_plate(connection, recipe_id, None, commit)


def get_recipe_plate(connection, user_id: int, plate_id: int) -> RecipePlateRead:
    """A plate of one of the user's recipes.

    Raises:
        NotFoundError: it does not exist or its recipe is not the user's.
    """
    row = _execute_query(
        connection,
        f"""
        SELECT {_COLUMNS}
        FROM recipe_plate rp
        JOIN recipe r ON r.id = rp.recipe_id
        WHERE rp.id = %(plate_id)s AND r.users_id = %(user_id)s;
        """,
        {"plate_id": plate_id, "user_id": user_id},
        commit=False,
    )
    if row is None:
        raise NotFoundError("Plate not found.")
    return recipe_plate_read_from_row(row)


def list_recipe_plates(connection, user_id: int, recipe_id: int) -> list[RecipePlateRead]:
    """The plates of a recipe the viewer may see, in order."""
    rows = _execute_query_many(
        connection,
        f"""
        SELECT {_COLUMNS}
        FROM recipe_plate rp
        JOIN recipe r ON r.id = rp.recipe_id
        WHERE rp.recipe_id = %(recipe_id)s AND (r.is_published OR r.users_id = %(user_id)s)
        ORDER BY rp.position;
        """,
        {"recipe_id": recipe_id, "user_id": user_id},
        commit=False,
    )
    return [recipe_plate_read_from_row(row) for row in rows]


def update_recipe_plate_name(connection, user_id: int, plate_id: int, name: str | None, commit: bool = True) -> None:
    """Write the plate's own name, or clear it to go back to the derived one.

    Raises:
        NotFoundError: it does not exist or its recipe is not the user's.
    """
    row = _execute_query(
        connection,
        """
        UPDATE recipe_plate rp
        SET name = %(name)s, updated_at = NOW()
        FROM recipe r
        WHERE r.id = rp.recipe_id AND rp.id = %(plate_id)s AND r.users_id = %(user_id)s
        RETURNING rp.id;
        """,
        {"plate_id": plate_id, "user_id": user_id, "name": name},
        commit=commit,
    )
    if row is None:
        raise NotFoundError("Plate not found.")


def swap_recipe_plate_position(connection, user_id: int, plate_id: int, *, up: bool, commit: bool = True) -> None:
    """Exchange a plate's position with its neighbour. At the edge it does nothing.

    One statement: uq_recipe_plate_recipe_id_position is deferrable, so it is checked
    when the statement ends and not row by row.

    Raises:
        NotFoundError: it does not exist or its recipe is not the user's.
    """
    recipe_id = get_recipe_plate(connection, user_id, plate_id).recipe_id
    _lock_owned_recipe(connection, user_id, recipe_id)
    # Read after the lock: another request may have just moved it.
    plate = get_recipe_plate(connection, user_id, plate_id)
    neighbour = _execute_query(
        connection,
        f"""
        SELECT rp.id, rp.position
        FROM recipe_plate rp
        WHERE rp.recipe_id = %(recipe_id)s AND rp.position {"<" if up else ">"} %(position)s
        ORDER BY rp.position {"DESC" if up else "ASC"}
        LIMIT 1;
        """,
        {"recipe_id": plate.recipe_id, "position": plate.position},
        commit=False,
    )
    if neighbour is None:
        return
    _execute_query(
        connection,
        """
        UPDATE recipe_plate rp
        SET position = CASE rp.id WHEN %(plate_id)s THEN %(neighbour_position)s ELSE %(position)s END,
            updated_at = NOW()
        WHERE rp.id IN (%(plate_id)s, %(neighbour_id)s)
        RETURNING rp.id;
        """,
        {
            "plate_id": plate.id,
            "position": plate.position,
            "neighbour_id": neighbour["id"],
            "neighbour_position": neighbour["position"],
        },
        commit=commit,
    )


def delete_recipe_plate(connection, user_id: int, plate_id: int, commit: bool = True) -> None:
    """Delete an empty plate. With ingredients inside it is blocked (§4.7).

    Raises:
        NotFoundError: it does not exist or its recipe is not the user's.
        ConflictError: it still has ingredients (ON DELETE RESTRICT).
    """
    try:
        row = _execute_query(
            connection,
            """
            DELETE FROM recipe_plate rp
            USING recipe r
            WHERE r.id = rp.recipe_id AND rp.id = %(plate_id)s AND r.users_id = %(user_id)s
            RETURNING rp.id;
            """,
            {"plate_id": plate_id, "user_id": user_id},
            commit=commit,
        )
    except ForeignKeyViolation as exc:
        raise ConflictError("Move or delete the ingredients of this plate first.") from exc
    if row is None:
        raise NotFoundError("Plate not found.")
