"""Mappers de fila SQL a dataclass de dominio (conventions/code_conventions.md §3.6).

Estos mappers conocen nombres físicos de columna (`users_id` -> `user_id`,
ver §3.5) que el dominio no debe conocer. Las dataclasses en
DayBetes_food/domain/ no se construyen desde una fila SQL en ningún otro
punto del código.
"""

from DayBetes_food.domain.constants import InjectionZone, InsulinType
from DayBetes_food.domain.insulin import InsulinInjectionRead


def insulin_injection_read_from_row(row: dict) -> InsulinInjectionRead:
    insulin_type = row.get("insulin_type")
    injection_zone = row.get("injection_zone")
    # NOTA (conventions/decisions.md, 2026-09-06 "basal_units pasa a llamarse
    # units"): la columna física sigue llamándose basal_units hasta que se
    # aplique la migración de renombrado; este mapper ya expone el nombre de
    # dominio decidido (`units`) para que el resto del código no dependa del
    # nombre físico antiguo.
    return InsulinInjectionRead(
        id=int(row["id"]),
        user_id=int(row["users_id"]),
        intake_event_id=row.get("intake_event_id"),
        shot_time=row["shot_time"],
        insulin_type=InsulinType(insulin_type) if insulin_type else None,
        units=row.get("basal_units"),
        injection_zone=InjectionZone(injection_zone) if injection_zone else None,
        notes=row.get("notes"),
        needle_leak=row.get("needle_leak"),
        skin_pinch=row.get("skin_pinch"),
    )
