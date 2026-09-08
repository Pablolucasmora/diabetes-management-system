"""CRUD para insulin_injections (code_conventions.md §3.3, §3.4, §3.5).

Funciones públicas:
- create_insulin_injection: inserta y devuelve id
- list_insulin_injections: lista con paginación
- get_insulin_injection: obtiene una inyección
- get_injection_shot_time_at_offset: helper para paginación backwards
- update_insulin_injection: actualización por user_id + injection_id
- delete_insulin_injection: borrado por user_id + injection_id

Contratos (code_conventions.md §3.4):
- create_*: devuelve id, fallo de infraestructura lanza excepción
- update_*/delete_*: lanzan NotFoundError si no existe o no es del usuario
- Nunca devuelven False; None indica "no encontrado"
"""

from datetime import datetime

from DayBetes_food.database.mappers import insulin_injection_read_from_row
from DayBetes_food.domain.insulin import (
    InsulinInjectionCreate,
    InsulinInjectionRead,
    InsulinInjectionUpdate,
    validate_insulin_dose,
)
from DayBetes_food.errors import InfrastructureError, NotFoundError


def create_insulin_injection(
    connection,
    payload: InsulinInjectionCreate,
    *,
    commit: bool = True,
) -> int:
    """Crea una inyección de insulina.

    Args:
        connection: conexión a BD
        payload: InsulinInjectionCreate con todos los campos
        commit: si True, confirma la transacción

    Returns:
        id de la fila creada

    Raises:
        ValidationError: si insulin_type/units no son coherentes
        InfrastructureError: si falla la inserción
    """
    # Validar antes de pasar a BD
    validate_insulin_dose(payload.insulin_type, payload.units)

    query = """
        INSERT INTO insulin_injections (
            users_id, intake_event_id, shot_time, insulin_type, units, injection_zone,
            notes, needle_leak, skin_pinch, timezone_at_event
        )
        VALUES (
            %(user_id)s, %(intake_event_id)s, %(shot_time)s, %(insulin_type)s, %(units)s, %(injection_zone)s,
            %(notes)s, %(needle_leak)s, %(skin_pinch)s, %(timezone_at_event)s
        )
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "user_id": payload.user_id,
                    "intake_event_id": payload.intake_event_id,
                    "shot_time": payload.shot_time,
                    "insulin_type": payload.insulin_type.value,
                    "units": payload.units,
                    "injection_zone": payload.injection_zone.value if payload.injection_zone else None,
                    "notes": payload.notes,
                    "needle_leak": payload.needle_leak,
                    "skin_pinch": payload.skin_pinch,
                    "timezone_at_event": payload.timezone_at_event,
                },
            )
            row = cursor.fetchone()
        if row is None:
            raise InfrastructureError("Insulin injection INSERT returned no row")
        injection_id = int(row["id"])
        if commit:
            connection.commit()
        return injection_id
    except Exception:
        if commit:
            connection.rollback()
        raise


def list_insulin_injections(
    connection,
    user_id: int,
    *,
    limit: int = 15,
    offset: int = 0,
) -> list[InsulinInjectionRead]:
    """Lista inyecciones del usuario con paginación.

    Orden: shot_time DESC, id DESC (índice: idx_insulin_injections_users_id_shot_time).

    Args:
        connection: conexión a BD
        user_id: id del usuario propietario
        limit: máximo de filas por página
        offset: filas a saltar

    Returns:
        lista de InsulinInjectionRead (vacía si no hay filas)
    """
    query = """
        SELECT
            id, users_id, intake_event_id, shot_time, insulin_type, units, injection_zone,
            notes, needle_leak, skin_pinch, timezone_at_event, created_at, updated_at
        FROM insulin_injections
        WHERE users_id = %(user_id)s
        ORDER BY shot_time DESC, id DESC
        LIMIT %(limit)s OFFSET %(offset)s;
    """
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            {"user_id": user_id, "limit": limit, "offset": offset},
        )
        rows = cursor.fetchall()
    return [insulin_injection_read_from_row(row) for row in rows]


def get_insulin_injection(
    connection,
    user_id: int,
    injection_id: int,
) -> InsulinInjectionRead | None:
    """Obtiene una inyección por id, verificando propietario.

    Args:
        connection: conexión a BD
        user_id: id del usuario (filtro de ownership)
        injection_id: id de la inyección

    Returns:
        InsulinInjectionRead si existe y es del usuario, None en caso contrario
    """
    query = """
        SELECT
            id, users_id, intake_event_id, shot_time, insulin_type, units, injection_zone,
            notes, needle_leak, skin_pinch, timezone_at_event, created_at, updated_at
        FROM insulin_injections
        WHERE id = %(injection_id)s AND users_id = %(user_id)s;
    """
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            {"injection_id": injection_id, "user_id": user_id},
        )
        row = cursor.fetchone()
    return insulin_injection_read_from_row(row) if row else None


def get_injection_shot_time_at_offset(
    connection,
    user_id: int,
    offset: int,
) -> datetime | None:
    """Obtiene el shot_time de la inyección en una posición de paginación.

    Usado para mostrar la fecha de cambio en la paginación (e.g. "Previous: 2026-09-06").

    Args:
        connection: conexión a BD
        user_id: id del usuario
        offset: posición en la lista ordenada

    Returns:
        datetime (aware UTC) si existe, None en caso contrario
    """
    query = """
        SELECT shot_time
        FROM insulin_injections
        WHERE users_id = %(user_id)s
        ORDER BY shot_time DESC, id DESC
        LIMIT 1 OFFSET %(offset)s;
    """
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            {"user_id": user_id, "offset": offset},
        )
        row = cursor.fetchone()
    return row["shot_time"] if row else None


def update_insulin_injection(
    connection,
    user_id: int,
    injection_id: int,
    payload: InsulinInjectionUpdate,
    *,
    commit: bool = True,
) -> None:
    """Actualiza una inyección existente.

    Campos actualizables: insulin_type, shot_time, injection_zone, units.
    updated_at se actualiza automáticamente por DEFAULT CURRENT_TIMESTAMP en BD.

    Args:
        connection: conexión a BD
        user_id: id del usuario (filtro de ownership)
        injection_id: id de la inyección
        payload: InsulinInjectionUpdate con nuevos valores
        commit: si True, confirma la transacción

    Returns:
        None. Lanza NotFoundError si la fila no existe o no es del usuario.

    Raises:
        ValidationError: si insulin_type/units no son coherentes
        NotFoundError: si la fila no existe o no es del usuario
    """
    # Validar antes de pasar a BD
    validate_insulin_dose(payload.insulin_type, payload.units)

    query = """
        UPDATE insulin_injections
        SET
            insulin_type = %(insulin_type)s,
            shot_time = %(shot_time)s,
            injection_zone = %(injection_zone)s,
            units = %(units)s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %(injection_id)s AND users_id = %(user_id)s
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "injection_id": injection_id,
                    "user_id": user_id,
                    "insulin_type": payload.insulin_type.value,
                    "shot_time": payload.shot_time,
                    "injection_zone": payload.injection_zone.value if payload.injection_zone else None,
                    "units": payload.units,
                },
            )
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError(f"Insulin injection {injection_id} not found or not owned by user {user_id}")
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise


def delete_insulin_injection(
    connection,
    user_id: int,
    injection_id: int,
    *,
    commit: bool = True,
) -> None:
    """Borra una inyección existente.

    Args:
        connection: conexión a BD
        user_id: id del usuario (filtro de ownership)
        injection_id: id de la inyección
        commit: si True, confirma la transacción

    Returns:
        None. Lanza NotFoundError si la fila no existe o no es del usuario.

    Raises:
        NotFoundError: si la fila no existe o no es del usuario
    """
    query = """
        DELETE FROM insulin_injections
        WHERE id = %(injection_id)s AND users_id = %(user_id)s
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"injection_id": injection_id, "user_id": user_id},
            )
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError(f"Insulin injection {injection_id} not found or not owned by user {user_id}")
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise
