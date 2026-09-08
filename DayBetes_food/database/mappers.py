"""Mappers de fila SQL a dataclass de dominio (conventions/code_conventions.md §3.6).

Estos mappers conocen nombres físicos de columna (`users_id` -> `user_id`,
ver §3.5) que el dominio no debe conocer. Las dataclasses en
DayBetes_food/domain/ no se construyen desde una fila SQL en ningún otro
punto del código.
"""

from DayBetes_food.domain.constants import InjectionZone, InsulinType
from DayBetes_food.domain.insulin import InsulinInjectionRead
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
