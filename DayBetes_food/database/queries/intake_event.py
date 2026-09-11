"""Queries para la tabla `intake_event`, incluyendo las operaciones de
inyección de insulina asociadas (H1, H2):

- create_injection_for_event (H1): crea automáticamente inyección al confirmar evento
- set_injection_zone (H2): registra zona de inyección en el borrador del evento
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
    _execute_query_many,
)
from DayBetes_food.database.queries.insulin_injections import create_insulin_injection
from DayBetes_food.domain.constants import IntakeEventState, InsulinType, InjectionZone, MealType
from DayBetes_food.domain.intake_event import IntakeEventCreate, IntakeEventRead, IntakeEventUpdate
from DayBetes_food.domain.insulin import InsulinInjectionCreate
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
    quality_confidence,
    carbs_uncertainty,
    sugars_uncertainty,
    fats_uncertainty,
    saturated_uncertainty,
    proteins_uncertainty,
    fiber_uncertainty,
    notes,
    created_at,
    updated_at,
    deleted_at
"""


def set_injection_zone(
    connection,
    user_id: int,
    intake_event_id: int,
    zone: InjectionZone,
    *,
    commit: bool = True,
) -> bool:
    """Registra zona de inyección en un evento (borrador).

    Filtra por user_id, event_id e insulin_dose=TRUE.
    Lanza NotFoundError si el evento no existe o no es del usuario.
    Lanza ConflictError si el evento no lleva insulina.

    Args:
        connection: conexión a BD
        user_id: id del usuario (filtro de ownership)
        intake_event_id: id del evento
        zone: InjectionZone a registrar
        commit: si True, confirma la transacción

    Returns:
        True si se actualizó

    Raises:
        NotFoundError: evento no existe o no es del usuario
        ConflictError: evento no lleva insulina (insulin_dose = FALSE)
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
            # Verificar cuál fue la razón del fallo
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


def create_injection_for_event(
    connection,
    user_id: int,
    intake_event_id: int,
    *,
    commit: bool = True,
) -> int | None:
    """Crea automáticamente una inyección al confirmar un evento.

    Contrato: si insulin_dose es TRUE se crea SIEMPRE una fila; la zona es opcional.
    Si insulin_dose es FALSE devuelve None sin hacer nada.

    Flujo:
    1. Verifica que el evento existe y es del usuario
    2. Si insulin_dose=FALSE, devuelve None
    3. Si insulin_dose=TRUE:
       - Extrae zona del evento (puede ser NULL)
       - Crea inyección con tipo RAPID, units=None, zona opcional
       - Devuelve id de la inyección creada

    Args:
        connection: conexión a BD
        user_id: id del usuario (filtro de ownership)
        intake_event_id: id del evento confirmado
        commit: si True, confirma la transacción

    Returns:
        id de la inyección creada, o None si el evento no lleva insulina

    Raises:
        NotFoundError: evento no existe o no es del usuario
        ValidationError: zona inválida en base de datos
        InfrastructureError: otros errores
    """
    query = """
        SELECT id, users_id AS user_id, insulin_dose, injection_zone,
               meal_time, timezone_at_event
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

        # Procesar zona (puede ser NULL)
        raw_zone = (row.get("injection_zone") or "").strip()
        zone = None
        if raw_zone:
            try:
                zone = InjectionZone(raw_zone)
            except ValueError as exc:
                raise ValidationError("Invalid injection zone stored in intake event") from exc

        # Crear inyección (rápida, sin dosis, zona opcional)
        injection_payload = InsulinInjectionCreate(
            user_id=row["user_id"],
            intake_event_id=intake_event_id,
            shot_time=row["meal_time"] or utc_now(),
            timezone_at_event=row["timezone_at_event"] or APP_TIMEZONE.key,
            insulin_type=InsulinType.RAPID,
            units=None,
            injection_zone=zone,
        )

        # No revalidamos porque insulin_type=RAPID y units=None es válido
        injection_id = create_insulin_injection(
            connection,
            injection_payload,
            commit=commit,
        )
        return injection_id

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
    """Transiciona un evento planned -> consumed. Ownership e idempotencia en el UPDATE.

    Devuelve el id confirmado.
    Raises:
        NotFoundError: el evento no existe o no es del usuario.
        ConflictError: existe y es del usuario, pero ya no está en 'planned'.
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
            # Comprobación protegida por ownership (§6.7): distingue 404 de 409
            # sin revelar eventos ajenos.
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
    """Crea un evento y devuelve su id (§3.3, §3.4).

    timezone_at_event se fija a la zona de la aplicación: es la zona en que se
    interpretó meal_time (§10.4).

    Raises:
        InfrastructureError: si el INSERT no devuelve fila.
    """
    query = """
        INSERT INTO intake_event
            (users_id, state, meal_type, name, meal_time, timezone_at_event)
        VALUES
            (%(user_id)s, %(state)s, %(meal_type)s, %(name)s,
             COALESCE(%(meal_time)s, CURRENT_TIMESTAMP), %(timezone_at_event)s)
        RETURNING id;
    """
    params = {
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
    """Lectura privada de un evento activo. None si no existe, no es del usuario
    o está archivado (§5.3, §5.4, §11.3)."""
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
    """Eventos en 'planned' (el carrito) del usuario, orden estable (§11.9)."""
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
    """Eventos consumidos de un día natural local del usuario."""
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
    """Todos los eventos consumidos del usuario, orden estable (§11.9)."""
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
    """Actualiza campos de un evento activo del usuario. Ownership en el SQL (§5.3).

    data: IntakeEventUpdate (§3.1); solo los campos que representan realmente
    los editables de la entidad. Los campos en None se ignoran (comportamiento
    de _build_update_query); para poner name a NULL existe
    update_intake_event_name. La traducción de dataclass a columnas físicas
    (incluida la extracción de .value de los enums) ocurre en este único punto,
    en vez de en cada ruta.

    NO filtra por state: un evento 'consumed' sigue siendo editable en todos sus
    campos (decisión 2026-09-08) y la ruta /confirm actualiza el evento cuando ya
    está en 'consumed'. Sí excluye archivados (deleted_at IS NULL, §11.3).

    Raises:
        NotFoundError: el evento no existe, no es del usuario o está archivado.
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
    """Actualiza el nombre de un evento activo del usuario."""
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
    """Actualiza las notas de un evento activo del usuario.

    Función propia, igual que update_intake_event_name y por el mismo motivo:
    IntakeEventUpdate interpreta None como "no tocar", así que borrar una nota
    (cadena vacía -> NULL, §7.3) no puede hacerse por esa vía.
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
    """Borrado FÍSICO de un evento en 'planned' del usuario.

    'planned' es no archivable (decisión 2026-09-08): descartar un carrito es un
    borrado legítimo. Un evento 'consumed' es archivable y NO puede borrarse por
    esta vía: usa archive_intake_event.

    Si el evento borrado tenía una inyección asociada, la FK
    insulin_injections.intake_event_id (ON DELETE SET NULL) la conserva
    desasociada. Es el comportamiento elegido, no un efecto colateral.

    Raises:
        NotFoundError: no existe o no es del usuario.
        ConflictError: existe y es del usuario, pero no está en 'planned'.
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
            # Comprobación protegida por ownership (§5.4): distingue 404 de 409
            # sin revelar eventos ajenos.
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
    """Soft-delete de un evento 'consumed' del usuario (§11.3).

    Archivar es un UPDATE, no un DELETE: la FK ON DELETE SET NULL de
    insulin_injections NO se activa y la inyección conserva su contexto de comida
    (decisión 2026-09-08).

    Raises:
        NotFoundError: no existe o no es del usuario.
        ConflictError: no está en 'consumed', o ya estaba archivado.
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
            # Comprobación protegida por ownership
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
    """Deshace el archivado (§11.3). No hay unicidad que revalidar en esta tabla.

    Raises:
        NotFoundError: no existe o no es del usuario.
        ConflictError: no estaba archivado.
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
            # Comprobación protegida por ownership
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
    """Valida que el evento existe, es del usuario, está activo y sigue en 'planned'.

    Devuelve el id del evento. Ownership y estado van dentro del SQL (§5.3).

    Raises:
        NotFoundError: no existe, no es del usuario o está archivado.
        ConflictError: es del usuario pero ya no está en 'planned'.
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
