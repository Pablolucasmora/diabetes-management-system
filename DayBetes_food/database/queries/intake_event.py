"""Queries para intake_event con operaciones de inyección (H1, H2).

- create_injection_for_event (H1): crea automáticamente inyección al confirmar evento
- set_injection_zone (H2): registra zona de inyección en el borrador del evento
"""

from DayBetes_food.database.queries.insulin_injections import create_insulin_injection
from DayBetes_food.domain.constants import InjectionZone, InsulinType
from DayBetes_food.domain.insulin import InsulinInjectionCreate
from DayBetes_food.errors import ConflictError, InfrastructureError, NotFoundError, ValidationError
from DayBetes_food.time_utils import utc_now, APP_TIMEZONE


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
