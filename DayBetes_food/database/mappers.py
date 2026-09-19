"""Mappers de fila SQL a dataclass de dominio (conventions/code_conventions.md §3.6).

Estos mappers conocen nombres físicos de columna (`users_id` -> `user_id`,
ver §3.5) que el dominio no debe conocer. Las dataclasses en
DayBetes_food/domain/ no se construyen desde una fila SQL en ningún otro
punto del código.
"""

from DayBetes_food.domain.constants import InjectionZone, IntakeEventState, InsulinType, MealType
from DayBetes_food.domain.insulin import InsulinInjectionRead
from DayBetes_food.domain.intake_event import IntakeEventRead
from DayBetes_food.domain.intake_plate import IntakePlateRead
from DayBetes_food.errors import InfrastructureError


def insulin_injection_read_from_row(row: dict) -> InsulinInjectionRead:
    """Convierte fila SQL a InsulinInjectionRead.

    Columnas obligatorias: id, users_id, shot_time, insulin_type, created_at, updated_at, timezone_at_event.
    Columnas nullables: intake_event_id, units, injection_zone, notes, needle_leak, skin_pinch.
    """
    try:
        insulin_type = InsulinType(row["insulin_type"])
    except ValueError as exc:
        raise InfrastructureError(
            f"Invalid insulin_type '{row['insulin_type']}' in database row"
        ) from exc
    except KeyError as exc:
        raise InfrastructureError(f"Missing required field {exc} in insulin injection row") from exc

    injection_zone_raw = row.get("injection_zone")
    injection_zone = None
    if injection_zone_raw:
        try:
            injection_zone = InjectionZone(injection_zone_raw)
        except ValueError as exc:
            raise InfrastructureError(
                f"Invalid injection_zone '{injection_zone_raw}' in database row"
            ) from exc

    return InsulinInjectionRead(
        id=int(row["id"]),
        user_id=int(row["users_id"]),
        intake_event_id=row.get("intake_event_id"),
        shot_time=row["shot_time"],
        timezone_at_event=row["timezone_at_event"],
        insulin_type=insulin_type,
        units=row.get("units"),
        injection_zone=injection_zone,
        notes=row.get("notes"),
        needle_leak=row.get("needle_leak"),
        skin_pinch=row.get("skin_pinch"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def intake_event_read_from_row(row: dict) -> IntakeEventRead:
    """Convierte fila SQL a IntakeEventRead.

    La fila debe venir de _INTAKE_EVENT_COLUMNS (queries/intake_event.py), que
    ya expone users_id con el alias user_id (§3.5).
    Columnas obligatorias: id, user_id, state, timezone_at_event, eating_out,
    insulin_dose, created_at, updated_at. El resto son nullables.
    """
    try:
        state = IntakeEventState(row["state"])
    except ValueError as exc:
        raise InfrastructureError(
            f"Invalid state '{row['state']}' in intake_event row"
        ) from exc
    except KeyError as exc:
        raise InfrastructureError(f"Missing required field {exc} in intake_event row") from exc

    meal_type_raw = row.get("meal_type")
    meal_type = None
    if meal_type_raw:
        try:
            meal_type = MealType(meal_type_raw)
        except ValueError as exc:
            raise InfrastructureError(
                f"Invalid meal_type '{meal_type_raw}' in intake_event row"
            ) from exc

    injection_zone_raw = row.get("injection_zone")
    injection_zone = None
    if injection_zone_raw:
        try:
            injection_zone = InjectionZone(injection_zone_raw)
        except ValueError as exc:
            raise InfrastructureError(
                f"Invalid injection_zone '{injection_zone_raw}' in intake_event row"
            ) from exc

    return IntakeEventRead(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        state=state,
        meal_type=meal_type,
        name=row.get("name"),
        meal_time=row.get("meal_time"),
        timezone_at_event=row["timezone_at_event"],
        eating_out=bool(row["eating_out"]),
        insulin_dose=bool(row["insulin_dose"]),
        injection_zone=injection_zone,
        ingested_amount=row.get("ingested_amount"),
        amount_confidence=row.get("amount_confidence"),
        quality_confidence=row.get("quality_confidence"),
        carbs_uncertainty=row.get("carbs_uncertainty"),
        sugars_uncertainty=row.get("sugars_uncertainty"),
        fats_uncertainty=row.get("fats_uncertainty"),
        saturated_uncertainty=row.get("saturated_uncertainty"),
        proteins_uncertainty=row.get("proteins_uncertainty"),
        fiber_uncertainty=row.get("fiber_uncertainty"),
        notes=row.get("notes"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row.get("deleted_at"),
    )


def intake_plate_read_from_row(row: dict) -> IntakePlateRead:
    """Convierte fila SQL a IntakePlateRead.

    Columnas obligatorias: id, intake_event_id, created_at, updated_at.
    Columnas nullables: name (NULL = nombre derivado, measurement §4.6.3) y
    offset_minutes (NULL = la tanda todavía no tiene plantilla de offset).
    """
    try:
        return IntakePlateRead(
            id=int(row["id"]),
            intake_event_id=int(row["intake_event_id"]),
            name=row.get("name"),
            offset_minutes=row.get("offset_minutes"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    except KeyError as exc:
        raise InfrastructureError(f"Missing required field {exc} in intake plate row") from exc
