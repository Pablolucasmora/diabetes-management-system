"""Queries para la tabla `intake_event`, incluyendo las operaciones de
inyección de insulina asociadas (H1, H2):

- create_injection_for_event (H1): crea automáticamente inyección al confirmar evento
- set_injection_zone (H2): registra zona de inyección en el borrador del evento
"""

from typing import Optional

from DayBetes_food.database.queries.crud import APP_TIMEZONE_SQL, _build_update_query, _execute_query, _execute_query_many
from DayBetes_food.database.queries.insulin_injections import create_insulin_injection
from DayBetes_food.domain.constants import InjectionZone, InsulinType
from DayBetes_food.domain.insulin import InsulinInjectionCreate
from DayBetes_food.errors import ConflictError, InfrastructureError, NotFoundError, ValidationError
from DayBetes_food.time_utils import local_today, utc_now, APP_TIMEZONE


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
        SET injection_zone = %(zone)s
        WHERE id = %(intake_event_id)s
          AND users_id = %(user_id)s
          AND insulin_dose = TRUE
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
                    "SELECT id, insulin_dose FROM intake_event WHERE id = %(id)s AND users_id = %(user_id)s;",
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
               meal_time AT TIME ZONE 'UTC' AS meal_time_utc
        FROM intake_event
        WHERE id = %(intake_event_id)s AND users_id = %(user_id)s;
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
            shot_time=row["meal_time_utc"] or utc_now(),
            timezone_at_event=APP_TIMEZONE.key,
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
        SET state = 'consumed'
        WHERE id = %(event_id)s
          AND users_id = %(user_id)s
          AND state = 'planned'
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, {"event_id": event_id, "user_id": user_id})
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


def get_injection_zone_for_event(connection, user_id: int, intake_event_id: int) -> InjectionZone | None:
    """Zona en borrador de un evento del usuario. None si no hay o el evento no es suyo.

    Lectura de presentación: no distingue "no existe" de "sin zona" (§5.4).
    """
    query = """
        SELECT injection_zone
        FROM intake_event
        WHERE id = %(intake_event_id)s
          AND users_id = %(user_id)s;
    """
    with connection.cursor() as cursor:
        cursor.execute(query, {"intake_event_id": intake_event_id, "user_id": user_id})
        row = cursor.fetchone()
    if row is None or not row["injection_zone"]:
        return None
    try:
        return InjectionZone(row["injection_zone"])
    except ValueError as exc:
        raise InfrastructureError(
            f"Invalid injection_zone '{row['injection_zone']}' in intake_event {intake_event_id}"
        ) from exc


# ============================================
# CRUD base (movido desde crud.py)
# ============================================

def add_intake_event(connection, users_id: int, state: str, meal_type: str = None, name: str = None,
                       meal_time=None, eating_out: bool = False, insulin_dose: bool = True,
                       total_amount: float = None, ingested_amount: float = None,
                       amount_confidence: float = None, quality_confidence: float = None,
                     notes: str = None, commit: bool = True, **kwargs) -> Optional[int]:
    """Creates a new intake event."""

    data = {
        "users_id": users_id,
        "state": state,
        "eating_out": eating_out,
        "insulin_dose": insulin_dose,
    }

    optional = {
        "meal_type": meal_type,
        "name": name,
        "meal_time": meal_time,
        "total_amount": total_amount,
        "ingested_amount": ingested_amount,
        "amount_confidence": amount_confidence,
        "quality_confidence": quality_confidence,
        "notes": notes,
        "carbs_uncertainty": kwargs.get("carbs_uncertainty"),
        "sugars_uncertainty": kwargs.get("sugars_uncertainty"),
        "fats_uncertainty": kwargs.get("fats_uncertainty"),
        "saturated_uncertainty": kwargs.get("saturated_uncertainty"),
        "proteins_uncertainty": kwargs.get("proteins_uncertainty"),
        "fiber_uncertainty": kwargs.get("fiber_uncertainty"),
    }

    data.update({k: v for k, v in optional.items() if v is not None})

    columns = ", ".join(data.keys())
    values = ", ".join(f"%({k})s" for k in data.keys())

    query = f"""
        INSERT INTO intake_event ({columns})
        VALUES ({values})
        RETURNING id;
    """

    result = _execute_query(connection, query, data, commit=commit, rollback_on_error=commit)
    return result["id"] if result else None


def get_intake_event(connection, event_id: int) -> Optional[dict]:
    """Gets an intake event by ID."""
    query = "SELECT * FROM intake_event WHERE id = %(id)s;"
    return _execute_query(connection, query, {"id": event_id}, commit=False)


def get_cart_events(connection, users_id: int) -> list:
    """Gets the events in 'planned' state (cart) for a users."""
    query = """
        SELECT * FROM intake_event 
        WHERE users_id = %(users_id)s AND state = 'planned' 
        ORDER BY meal_time DESC;
    """
    return _execute_query_many(connection, query, {"users_id": users_id}, commit=False)


def get_consumed_events_for_day(connection, users_id: int, day=None) -> list:
    """Gets events in 'consumed' state for a specific calendar day."""
    if day is None:
        day = local_today()
    query = """
        SELECT *
        FROM intake_event
        WHERE users_id = %(users_id)s
          AND state = 'consumed'
          AND DATE((meal_time AT TIME ZONE 'UTC' AT TIME ZONE %(app_timezone)s)) = %(day)s
        ORDER BY meal_time ASC, id ASC;
    """
    return _execute_query_many(
        connection,
        query,
        {"users_id": users_id, "day": day, "app_timezone": APP_TIMEZONE_SQL},
        commit=False,
    )


def get_consumed_events(connection, users_id: int) -> list:
    """Gets all events in 'consumed' state for a users."""
    query = """
        SELECT *
        FROM intake_event
        WHERE users_id = %(users_id)s
          AND state = 'consumed'
        ORDER BY meal_time ASC, id ASC;
    """
    return _execute_query_many(connection, query, {"users_id": users_id}, commit=False)


def update_intake_event(connection, event_id: int, data: dict, commit: bool = True) -> bool:
    """Updates an intake event."""
    if not data:
        return False
    
    params = {**data, "id": event_id}
    query = _build_update_query("intake_event", params)
    
    if not query:
        return False
        
    result = _execute_query(connection, query, params, commit=commit, rollback_on_error=commit)
    return result is not None


def change_event_status(connection, event_id: int, new_state: str, commit: bool = True) -> bool:
    """Changes the status of an intake event (planned -> consumed)."""
    if new_state not in ("planned", "consumed"):
        raise ValueError("Invalid state. Must be 'planned' or 'consumed'")
    
    query = "UPDATE intake_event SET state = %(state)s WHERE id = %(id)s RETURNING id;"
    result = _execute_query(
        connection, query, {"id": event_id, "state": new_state}, commit=commit, rollback_on_error=commit
    )
    return result is not None


def delete_intake_event(connection, event_id: int, commit: bool = True) -> bool:
    """Deletes an intake event."""
    query = "DELETE FROM intake_event WHERE id = %(id)s RETURNING id;"
    result = _execute_query(
        connection, query, {"id": event_id}, commit=commit, rollback_on_error=commit
    )
    return result is not None


def update_intake_event_name(connection, event_id: int, name: Optional[str], commit: bool = True) -> bool:
    """Updates intake event name."""
    query = """
        UPDATE intake_event
        SET name = %(name)s
        WHERE id = %(id)s
        RETURNING id;
    """
    result = _execute_query(
        connection, query, {"id": event_id, "name": name}, commit=commit, rollback_on_error=commit
    )
    return result is not None
