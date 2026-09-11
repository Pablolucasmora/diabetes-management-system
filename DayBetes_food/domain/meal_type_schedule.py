"""Dominio del horario de asignación automática de `meal_type` (conventions/code_conventions.md §3.6).

Este módulo no importa psycopg, rutas ni componentes. Es puro: recibe las
franjas ya leídas de la base (o ninguna) y decide qué `MealType` corresponde
a una hora local dada.

Contexto (decisión 2026-09-11): un `intake_event` creado automáticamente
(añadir un alimento sin carrito abierto) nacía con `meal_type=None`, pero el
`<select>` del carrito (`components/cart/cart_components.py::EventHeader`)
pinta la primera opción del enum como elegida en cuanto ningún `<option>`
lleva `selected` — el usuario ve "breakfast" aunque la base tenga `NULL`, y
como el guardado es autosave-on-change, si no toca el control nunca se
persiste. La corrección de fondo no es solo visual: el evento debe nacer ya
con el `meal_type` que la interfaz va a mostrar, calculado por franja
horaria, para que "lo que se ve" y "lo que hay en la base" sean siempre el
mismo valor desde el instante de creación (principio general, ver
code_conventions.md §7.14).
"""

from dataclasses import dataclass
from datetime import time

from DayBetes_food.domain.constants import MealType

# Meal types que pueden asignarse automáticamente por franja horaria. `snack`
# y `rescue` quedan fuera a propósito: son elecciones manuales del usuario
# (`rescue`, además, nace siempre así en food_routes.py, ver
# audit/deuda_pendiente.md), nunca un default por hora (decisión 2026-09-11).
AUTO_ASSIGNABLE_MEAL_TYPES: tuple[MealType, ...] = (
    MealType.BREAKFAST,
    MealType.BRUNCH,
    MealType.LUNCH,
    MealType.AFTERNOON_SNACK,
    MealType.DINNER,
)

# Franjas por defecto (hora local), usadas para cualquier meal_type que el
# usuario no haya personalizado todavía en /settings/meal_type_schedule.
# `DINNER` envuelve medianoche: termina en 00:00 exclusive, no sigue cubriendo
# la madrugada (decisión 2026-09-11, acordada con el usuario).
DEFAULT_MEAL_TYPE_WINDOWS: dict[MealType, tuple[time, time]] = {
    MealType.BREAKFAST: (time(5, 0), time(11, 0)),
    MealType.BRUNCH: (time(11, 0), time(13, 30)),
    MealType.LUNCH: (time(13, 30), time(17, 0)),
    MealType.AFTERNOON_SNACK: (time(17, 0), time(19, 30)),
    MealType.DINNER: (time(19, 30), time(0, 0)),
}


@dataclass(frozen=True)
class MealTypeWindow:
    """Una franja horaria personalizada por el usuario para un meal_type."""
    meal_type: MealType
    start_time: time
    end_time: time


def resolve_meal_type_window(
    meal_type: MealType, overrides: dict[MealType, tuple[time, time]]
) -> tuple[time, time]:
    """Franja efectiva de un meal_type: la del usuario si existe, si no el default."""
    return overrides.get(meal_type) or DEFAULT_MEAL_TYPE_WINDOWS[meal_type]


def resolve_meal_type_for_time(
    local_time: time,
    overrides: dict[MealType, tuple[time, time]] | None = None,
) -> MealType | None:
    """
    Determina el `meal_type` automático para una hora local, mezclando las
    franjas personalizadas del usuario con los defaults para las que no haya
    tocado. Si ninguna franja cubre la hora (hueco entre el fin de `dinner` y
    el inicio de `breakfast`, p. ej. 02:00, o un hueco que el propio usuario
    haya dejado al personalizar sus franjas), devuelve `None`: no se inventa
    un `meal_type` fuera de las franjas declaradas, el usuario lo elige a
    mano (decisión 2026-09-11, mismo criterio que `snack`/`rescue`).
    """
    overrides = overrides or {}
    for meal_type in AUTO_ASSIGNABLE_MEAL_TYPES:
        start, end = resolve_meal_type_window(meal_type, overrides)
        if _time_in_window(local_time, start, end):
            return meal_type
    return None


def _time_in_window(value: time, start: time, end: time) -> bool:
    if start == end:
        # Franja degenerada (no debería persistirse, ver validación de la
        # ruta de settings): no cubre ninguna hora en vez de cubrirlas todas.
        return False
    if start < end:
        return start <= value < end
    # Envuelve medianoche (p. ej. dinner 19:30-00:00): cubre desde start hasta
    # el final del día y desde el principio del día hasta end, exclusive.
    return value >= start or value < end
