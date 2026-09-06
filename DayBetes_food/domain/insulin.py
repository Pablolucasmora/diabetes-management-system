"""Dataclasses de dominio para insulin_injections (conventions/code_conventions.md §3.6).

Este módulo no importa psycopg, rutas ni componentes. La conversión de fila
SQL a estas dataclasses vive en DayBetes_food/database/mappers.py, no aquí.
"""

from dataclasses import dataclass
from datetime import datetime

from DayBetes_food.domain.constants import InjectionZone, InsulinType


@dataclass(frozen=True)
class InsulinInjectionRead:
    id: int
    user_id: int
    intake_event_id: int | None
    shot_time: datetime
    insulin_type: InsulinType | None
    units: float | None
    injection_zone: InjectionZone | None
    notes: str | None
    needle_leak: bool | None
    skin_pinch: bool | None
