"""Dataclasses de dominio para insulin_injections (conventions/code_conventions.md §3.6).

Este módulo no importa psycopg, rutas ni componentes. La conversión de fila
SQL a estas dataclasses vive en DayBetes_food/database/mappers.py, no aquí.
"""

from dataclasses import dataclass
from datetime import datetime

from DayBetes_food.domain.constants import InjectionZone, InsulinType
from DayBetes_food.errors import ValidationError


@dataclass(frozen=True)
class InsulinInjectionRead:
    """Lectura de una inyección de insulina con todos sus campos.

    shot_time, created_at, updated_at son aware en UTC (measurement_conventions.md §9.3).
    needle_leak y skin_pinch pueden ser None = no observado (measurement_conventions.md §2).
    """
    id: int
    user_id: int
    intake_event_id: int | None
    shot_time: datetime
    timezone_at_event: str
    insulin_type: InsulinType
    units: float | None
    injection_zone: InjectionZone | None
    notes: str | None
    needle_leak: bool | None
    skin_pinch: bool | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class InsulinInjectionCreate:
    """Payload para crear una inyección de insulina.

    Todos los parámetros opcionales tienen defaults None.
    El user_id viene del contexto de autenticación, no del payload.
    """
    user_id: int
    insulin_type: InsulinType
    shot_time: datetime
    timezone_at_event: str
    injection_zone: InjectionZone | None = None
    units: float | None = None
    intake_event_id: int | None = None
    notes: str | None = None
    needle_leak: bool | None = None
    skin_pinch: bool | None = None


@dataclass(frozen=True)
class InsulinInjectionUpdate:
    """Payload para actualizar una inyección de insulina.

    Sustitución completa de los campos editables por el formulario de ajustes.
    No es un update parcial: el formulario envía siempre los cuatro campos, así que
    no aplica la distinción ausente/None/CLEAR de code_conventions.md §3.4.
    """
    insulin_type: InsulinType
    shot_time: datetime
    injection_zone: InjectionZone | None
    units: float | None


def validate_insulin_dose(insulin_type: InsulinType, units: float | None) -> None:
    """Valida coherencia entre tipo de insulina y dosis.

    Lanza ValidationError si la combinación no es válida (code_conventions.md §4.3).

    Reglas:
    - Basal requiere dosis (units > 0)
    - Rápida puede no llevar dosis (units es opcional)
    - Si hay dosis, debe ser positiva y múltiplo de 0.5 U
    """
    if insulin_type is InsulinType.BASAL and units is None:
        raise ValidationError("Basal insulin requires a dose", fields={"units": "required"})

    if units is not None:
        if units <= 0:
            raise ValidationError("Insulin dose must be positive", fields={"units": "positive"})
        # Validar que sea múltiplo de 0.5: (units * 2) debe ser un entero
        if abs((units * 2) - round(units * 2)) > 1e-8:
            raise ValidationError("Insulin dose must be a multiple of 0.5 U", fields={"units": "step"})
