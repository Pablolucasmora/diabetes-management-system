"""Dataclasses y reglas puras de la tanda (plato) de un evento.

Ver conventions/code_conventions.md §3.6 y
conventions/measurement_conventions.md §4.6 (decisión 2026-09-19).

Este módulo no importa psycopg, rutas ni componentes. La conversión de fila
SQL a estas dataclasses vive en DayBetes_food/database/mappers.py, no aquí.

Una tanda subdivide un `intake_event` en los platos que se comieron en
momentos distintos, sin partir la comida en varios eventos: todos los offsets
siguen midiéndose contra el mismo `meal_time` (§4.6).
"""

from dataclasses import dataclass
from datetime import datetime

# Longitud máxima de intake_plate.name, igual al VARCHAR(255) de la columna
# (database/schema.py). §7.3 exige declarar la longitud máxima por campo y
# rechazar el exceso en el boundary con 422, sin truncar.
INTAKE_PLATE_NAME_MAX_LENGTH = 255

# Cota de cordura del offset de la tanda, idéntica a la de
# portion_detail.offset_minutes (measurement_conventions.md §4.5): la
# plantilla no puede admitir valores que la fila rechazaría. Igual al CHECK
# ck_intake_plate_offset_minutes de database/schema.py.
INTAKE_PLATE_OFFSET_MIN_MINUTES = -300
INTAKE_PLATE_OFFSET_MAX_MINUTES = 300

# Nombre mostrado cuando la tanda no tiene nombre propio ni ingredientes de
# los que derivarlo (measurement_conventions.md §4.6.3). Es interfaz, y la
# interfaz está en inglés (frontend_conventions.md §7.12).
#
# No es un ordinal ("First"): una tanda vacía puede ser la segunda o la
# tercera del evento, y llamarla "First" sería sencillamente falso. Describe
# el estado —sin ingredientes todavía—, que es lo único que se sabe de ella.
INTAKE_PLATE_EMPTY_NAME = "Empty plate"

# Cuántos ingredientes participan en el nombre derivado.
INTAKE_PLATE_NAME_INGREDIENTS = 2


@dataclass(frozen=True)
class IntakePlateRead:
    """Lectura completa de una tanda.

    `name` a None significa que el nombre se deriva de sus ingredientes
    (§4.6.3): no es un nombre vacío, es la ausencia de nombre propio.
    `offset_minutes` es la plantilla que heredan las porciones al insertarse,
    no un dato clínico: el valor autoritativo es el de cada
    portion_detail.offset_minutes (§4.6.2).
    created_at y updated_at son datetime aware en UTC (TIMESTAMPTZ).
    """
    id: int
    intake_event_id: int
    name: str | None
    offset_minutes: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class IntakePlateCreate:
    """Payload para crear una tanda dentro de un evento."""
    intake_event_id: int
    name: str | None = None
    offset_minutes: int | None = None


@dataclass(frozen=True)
class IntakePlateUpdate:
    """Payload para actualizar una tanda (§3.1). Solo campos modificables.

    Un campo en None significa "no se toca", igual que el resto de payloads de
    actualización del proyecto. Para borrar el nombre propio y devolver la
    tanda a su nombre derivado existe `update_intake_plate_name`, por el mismo
    motivo que `update_intake_event_name` (§7.4).
    """
    name: str | None = None
    offset_minutes: int | None = None


def derive_plate_name(ingredient_names: list[str]) -> str:
    """Nombre mostrado de una tanda sin nombre propio (§4.6.3).

    Toma la primera palabra del nombre de los dos primeros ingredientes, por
    orden de inserción, separadas por coma ("Arroz basmati Hacendado" +
    "Pechuga de pollo" -> "Arroz, Pechuga"). Con un solo ingrediente, esa única
    palabra; sin ingredientes, INTAKE_PLATE_EMPTY_NAME.

    Es un valor derivado que no se guarda: cambia al añadir, borrar o mover
    ingredientes, y deja de usarse en cuanto la tanda tiene nombre propio.
    """
    first_words = []
    for name in ingredient_names:
        word = (name or "").strip().split(" ")[0].strip()
        if word:
            first_words.append(word)
        if len(first_words) == INTAKE_PLATE_NAME_INGREDIENTS:
            break

    if not first_words:
        return INTAKE_PLATE_EMPTY_NAME
    return ", ".join(first_words)
