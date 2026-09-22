"""Queries para la tabla `intake_plate` (tandas o platos de un evento).

Modelo y reglas: conventions/measurement_conventions.md §4.6
(decisión 2026-09-19).
"""

from dataclasses import fields as dataclass_fields

from psycopg.errors import ForeignKeyViolation

from DayBetes_food.database.mappers import intake_plate_read_from_row
from DayBetes_food.database.queries.crud import (
    RawSQL,
    _build_update_query,
    _execute_query,
    _execute_query_many,
    logger,
)
from DayBetes_food.domain.intake_plate import IntakePlateCreate, IntakePlateRead, IntakePlateUpdate
from DayBetes_food.errors import ConflictError, InfrastructureError, NotFoundError

# Columnas de lectura de la tabla. Lista explícita, nunca `SELECT *` (§3.2):
# añadir una columna no debe cambiar el contrato de lectura sin tocar el código
# que lo consume.
_INTAKE_PLATE_COLUMNS = """
    ip.id,
    ip.intake_event_id,
    ip.name,
    ip.offset_minutes,
    ip.created_at,
    ip.updated_at
"""

# Orden de las tandas dentro de un evento (§4.6.1): cronológico por el offset
# de la tanda, y a igualdad de offset, por orden de creación. Se escribe aquí
# una sola vez; ningún componente reordena por su cuenta.
_INTAKE_PLATE_ORDER = "ORDER BY ip.offset_minutes NULLS LAST, ip.id"


def create_intake_plate(connection, payload: IntakePlateCreate, *, commit: bool = True) -> int:
    """Crea una tanda dentro de un evento y devuelve su id."""
    query = """
        INSERT INTO intake_plate (intake_event_id, name, offset_minutes)
        VALUES (%(intake_event_id)s, %(name)s, %(offset_minutes)s)
        RETURNING id;
    """
    row = _execute_query(
        connection,
        query,
        {
            "intake_event_id": payload.intake_event_id,
            "name": payload.name,
            "offset_minutes": payload.offset_minutes,
        },
        commit=commit,
        rollback_on_error=commit,
    )
    if row is None:
        raise InfrastructureError("Intake plate INSERT returned no row")
    return int(row["id"])


def list_intake_plates(connection, event_id: int) -> list[IntakePlateRead]:
    """Tandas de un evento, en el orden de §4.6.1."""
    query = f"""
        SELECT {_INTAKE_PLATE_COLUMNS}
        FROM intake_plate ip
        WHERE ip.intake_event_id = %(event_id)s
        {_INTAKE_PLATE_ORDER};
    """
    rows = _execute_query_many(connection, query, {"event_id": event_id}, commit=False)
    return [intake_plate_read_from_row(row) for row in rows]


def list_intake_plates_by_events(connection, event_ids: list[int]) -> list[IntakePlateRead]:
    """Tandas de varios eventos en una sola consulta (§6.9: sin N+1 en la lista del carrito).

    El orden es por evento y, dentro de cada uno, el de §4.6.1. Quien la use
    reparte las tandas por `intake_event_id` sin reordenarlas.
    """
    if not event_ids:
        return []
    query = f"""
        SELECT {_INTAKE_PLATE_COLUMNS}
        FROM intake_plate ip
        WHERE ip.intake_event_id = ANY(%(event_ids)s)
        ORDER BY ip.intake_event_id, ip.offset_minutes NULLS LAST, ip.id;
    """
    rows = _execute_query_many(connection, query, {"event_ids": list(event_ids)}, commit=False)
    return [intake_plate_read_from_row(row) for row in rows]


def get_intake_plate(connection, user_id: int, plate_id: int) -> IntakePlateRead:
    """Lee una tanda comprobando la propiedad dentro del SQL (§5.3).

    La pertenencia tanda -> evento -> usuario se resuelve en la consulta: una
    ruta nunca puede fiarse del `event_id` que venga en la URL. No exige estado
    'planned': las tandas de un evento ya consumido también se editan
    (measurement_conventions.md §6.9.3).

    Raises:
        NotFoundError: no existe, no es del usuario o su evento está archivado.
    """
    query = f"""
        SELECT {_INTAKE_PLATE_COLUMNS}
        FROM intake_plate ip
        JOIN intake_event ie ON ie.id = ip.intake_event_id
        WHERE ip.id = %(plate_id)s
          AND ie.users_id = %(user_id)s
          AND ie.deleted_at IS NULL;
    """
    row = _execute_query(connection, query, {"plate_id": plate_id, "user_id": user_id}, commit=False)
    if row is None:
        raise NotFoundError(
            f"Intake plate {plate_id} not found or not owned by user {user_id}"
        )
    return intake_plate_read_from_row(row)


def update_intake_plate(
    connection,
    plate_id: int,
    data: IntakePlateUpdate,
    *,
    commit: bool = True,
) -> None:
    """Actualiza campos de una tanda (§3.1).

    Los campos en None se ignoran (comportamiento de `_build_update_query`);
    para poner `name` a NULL —devolver la tanda a su nombre derivado— existe
    `update_intake_plate_name`, igual que en intake_event.

    El ownership no se comprueba aquí: la ruta ya ha resuelto la tanda con
    `get_intake_plate`, que hace el JOIN al evento y al usuario (§5.3).

    Raises:
        NotFoundError: la tanda no existe.
    """
    payload = {
        field.name: getattr(data, field.name)
        for field in dataclass_fields(data)
        if getattr(data, field.name) is not None
    }
    if not payload:
        return None

    params = {**payload, "id": plate_id}
    query = _build_update_query("intake_plate", params, raw_fields={"updated_at": RawSQL.NOW})
    if query is None:
        return None

    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError(f"Intake plate {plate_id} not found")
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise


def update_intake_plate_name(
    connection, plate_id: int, name: str | None, *, commit: bool = True
) -> None:
    """Escribe el nombre propio de una tanda, o lo borra con `name=None`.

    Función propia, igual que `update_intake_event_name` y por el mismo motivo:
    `IntakePlateUpdate` interpreta None como "no tocar", así que borrar el
    nombre —y volver al derivado de §4.6.3— no puede hacerse por esa vía.

    Raises:
        NotFoundError: la tanda no existe.
    """
    query = """
        UPDATE intake_plate
        SET name = %(name)s,
            updated_at = NOW()
        WHERE id = %(plate_id)s
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, {"plate_id": plate_id, "name": name})
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError(f"Intake plate {plate_id} not found")
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise


def apply_plate_offset_to_portions(
    connection,
    plate_id: int,
    offset_minutes: int,
    *,
    commit: bool = True,
) -> bool:
    """`Apply all`: fija el offset de la tanda y lo propaga a todas sus porciones.

    Las dos escrituras son una sola operación (§2.3): si falla la propagación,
    la tanda tampoco se queda con el valor nuevo. Es la única forma de que el
    offset de la tanda toque las filas ya existentes; cambiarlo por separado
    solo afecta a las porciones que se añadan después (§4.6.2).
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE intake_plate
                SET offset_minutes = %(offset_minutes)s,
                    updated_at = NOW()
                WHERE id = %(plate_id)s;
                """,
                {"offset_minutes": offset_minutes, "plate_id": plate_id},
            )
            if cursor.rowcount != 1:
                if commit:
                    connection.rollback()
                return False
            cursor.execute(
                """
                UPDATE portion_detail
                SET offset_minutes = %(offset_minutes)s,
                    updated_at = NOW()
                WHERE plate_id = %(plate_id)s;
                """,
                {"offset_minutes": offset_minutes, "plate_id": plate_id},
            )
        if commit:
            connection.commit()
        return True
    except Exception as e:
        if commit:
            connection.rollback()
            logger.error("Error in query: %s", e, exc_info=True)
            return False
        raise


def delete_intake_plate(connection, plate_id: int, *, commit: bool = True) -> None:
    """Borra una tanda vacía.

    Una tanda con porciones no se borra: la FK es `ON DELETE RESTRICT` a
    propósito (§4.6.5), para que un click no se lleve por delante media comida.
    La violación de integridad se traduce a ConflictError, no a un 500.

    Raises:
        NotFoundError: la tanda no existe.
        ConflictError: la tanda todavía tiene ingredientes.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM intake_plate WHERE id = %(id)s;", {"id": plate_id})
            deleted = cursor.rowcount
        if deleted != 1:
            if commit:
                connection.rollback()
            raise NotFoundError(f"Intake plate {plate_id} not found")
        if commit:
            connection.commit()
    except ForeignKeyViolation as exc:
        if commit:
            connection.rollback()
        raise ConflictError("Intake plate still has portions") from exc
    except NotFoundError:
        raise
    except Exception:
        if commit:
            connection.rollback()
        raise


def ensure_default_plate(connection, event_id: int, *, offset_minutes: int = None, commit: bool = True) -> int:
    """Devuelve la tanda a la que debe ir un alimento añadido sin elegir tanda.

    Es la tanda de la **última porción añadida** al evento —la que el usuario
    está montando ahora mismo— y, si ninguna tiene ingredientes todavía, la
    creada más recientemente. Si el evento no tiene ninguna tanda, la crea
    implícitamente con el offset dado (§4.6.1, §7.7).

    El selector de tanda preselecciona esta misma tanda: lo que la interfaz
    muestra y lo que ocurre cuando no se envía `plate_id` tienen que coincidir
    (frontend_conventions.md §6).
    """
    row = _execute_query(
        connection,
        """
        SELECT ip.id
        FROM intake_plate ip
        LEFT JOIN (
            SELECT plate_id, MAX(id) AS last_portion_id
            FROM portion_detail
            WHERE plate_id IS NOT NULL
            GROUP BY plate_id
        ) last_portion ON last_portion.plate_id = ip.id
        WHERE ip.intake_event_id = %(event_id)s
        ORDER BY last_portion.last_portion_id DESC NULLS LAST, ip.id DESC
        LIMIT 1;
        """,
        {"event_id": event_id},
        commit=False,
    )
    if row is not None:
        return int(row["id"])
    return create_intake_plate(
        connection,
        IntakePlateCreate(intake_event_id=event_id, offset_minutes=offset_minutes),
        commit=commit,
    )
