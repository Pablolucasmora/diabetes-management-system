"""Dataclasses de dominio para intake_event (conventions/code_conventions.md §3.6).

Este módulo no importa psycopg, rutas ni componentes. La conversión de fila
SQL a estas dataclasses vive en DayBetes_food/database/mappers.py, no aquí.
"""

from dataclasses import dataclass
from datetime import datetime

from DayBetes_food.domain.constants import (
    AmountInputUnit,
    InjectionZone,
    IntakeEventState,
    MealType,
)


# Longitud máxima de intake_event.name, igual al VARCHAR(255) de la columna
# (database/schema.py). §7.3 exige declarar la longitud máxima por campo y
# rechazar el exceso en el boundary en vez de truncarlo (decisión 2026-09-09).
INTAKE_EVENT_NAME_MAX_LENGTH = 255

# Longitud máxima de intake_event.notes. La columna es TEXT (sin límite
# físico), así que el límite es de dominio: §7.3 exige declarar una longitud
# máxima por campo y rechazar el exceso en el boundary con 422, sin truncar.
# 500 caracteres cubren una nota de contexto de la comida ("comí fuera, ración
# estimada") sin convertir el campo en texto libre ilimitado
# (decisión 2026-09-10, hallazgo 44 de audit/audit_intake_event.md).
INTAKE_EVENT_NOTES_MAX_LENGTH = 500

# Límite superior de cordura para ingested_amount (y, aunque no sea columna,
# para el total_amount calculado en vivo y la fracción derivada de él, §6.9.1):
# 100000 g = 100 kg, muy por encima de cualquier comida humana real. No es un
# límite clínico ni nutricional, solo evita guardar un valor corrupto o
# manipulado como si fuera plausible. Igual al CHECK
# ck_intake_event_ingested_amount de database/schema.py (measurement_conventions.md
# §6.9.2, decisión 2026-09-10).
INTAKE_EVENT_INGESTED_AMOUNT_MAX_G = 100000

# Unidades admitidas para la cantidad ingerida que se envía al confirmar un
# evento: gramos absolutos del plato servido o porcentaje de ese plato. Son
# los dos miembros de AmountInputUnit (domain/constants.py), el enum central
# de unidades de measurement_conventions.md §11; aquí solo se declara cuáles
# de ellos acepta este boundary concreto, sin duplicar sus códigos.
# Cualquier otro valor se rechaza con 422 (§7.7: sin fallback silencioso),
# porque interpretarlo como gramos escribe una cantidad clínica falsa e
# irreversible (hallazgo 47 de audit/audit_intake_event.md).
INTAKE_EVENT_INGESTED_UNITS = (AmountInputUnit.GRAMS, AmountInputUnit.PERCENT)


@dataclass(frozen=True)
class IntakeEventRead:
    """Lectura completa de un evento de comida.

    meal_time, created_at, updated_at y deleted_at son datetime aware en UTC
    (columnas TIMESTAMPTZ). timezone_at_event guarda la zona en que el usuario
    introdujo meal_time, igual que en insulin_injections.
    deleted_at no NULL significa evento archivado (§11.3); solo puede ocurrir
    en estado 'consumed' (decisión 2026-09-08).
    ingested_amount es el único snapshot de cantidad total del evento: se
    calcula una vez en confirm_intake_event y equivale a la suma de
    portion_detail.plate_amount tras escalarlas por la fracción realmente
    consumida. No existe total_amount como columna: se calcula en vivo con
    SUM(plate_amount) cuando haga falta (decisión 2026-09-10,
    measurement_conventions.md §4.4/§6.9.1).
    """
    id: int
    user_id: int
    state: IntakeEventState
    meal_type: MealType | None
    name: str | None
    meal_time: datetime | None
    timezone_at_event: str
    eating_out: bool
    insulin_dose: bool
    injection_zone: InjectionZone | None
    ingested_amount: float | None
    amount_confidence: float | None
    quality_confidence: float | None
    carbs_uncertainty: float | None
    sugars_uncertainty: float | None
    fats_uncertainty: float | None
    saturated_uncertainty: float | None
    proteins_uncertainty: float | None
    fiber_uncertainty: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class IntakeEventCreate:
    """Payload para crear un evento. El user_id viene del contexto autenticado."""
    user_id: int
    state: IntakeEventState = IntakeEventState.PLANNED
    meal_type: MealType | None = None
    name: str | None = None
    meal_time: datetime | None = None


@dataclass(frozen=True)
class IntakeEventUpdate:
    """Payload para actualizar un evento activo (§3.1). Solo campos modificables.

    Todos son opcionales: un campo en None significa "no se toca", igual que el
    `dict` que sustituye (comportamiento de `_build_update_query`). No sirve para
    poner `name` a NULL explícitamente; para eso sigue existiendo
    `update_intake_event_name`.
    """
    meal_type: MealType | None = None
    name: str | None = None
    meal_time: datetime | None = None
    timezone_at_event: str | None = None
    eating_out: bool | None = None
    insulin_dose: bool | None = None
    injection_zone: InjectionZone | None = None
    ingested_amount: float | None = None
    amount_confidence: float | None = None
    quality_confidence: float | None = None
    carbs_uncertainty: float | None = None
    sugars_uncertainty: float | None = None
    fats_uncertainty: float | None = None
    saturated_uncertainty: float | None = None
    proteins_uncertainty: float | None = None
    fiber_uncertainty: float | None = None
    notes: str | None = None
