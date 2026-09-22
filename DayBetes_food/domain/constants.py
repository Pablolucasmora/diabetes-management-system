"""Enums de dominio (conventions/code_conventions.md §3.6 y §4.1).

Este módulo no importa psycopg, rutas ni componentes. Cada concepto tiene
un único enum aquí; no se crean listas paralelas del mismo concepto en
routes/, components/, crud.py o schema.py.
"""

from enum import Enum, unique


@unique
class InsulinType(str, Enum):
    RAPID = "rapid"
    BASAL = "basal"


@unique
class InjectionZone(str, Enum):
    RIGHT_ARM = "right_arm"
    LEFT_ARM = "left_arm"
    RIGHT_THIGH = "right_thigh"
    LEFT_THIGH = "left_thigh"
    ABDOMEN = "abdomen"
    RIGHT_GLUTEUS = "right_gluteus"
    LEFT_GLUTEUS = "left_gluteus"


@unique
class MealType(str, Enum):
    BREAKFAST = "breakfast"
    BRUNCH = "brunch"
    LUNCH = "lunch"
    AFTERNOON_SNACK = "afternoon_snack"
    DINNER = "dinner"
    SNACK = "snack"
    RESCUE = "rescue"


@unique
class IntakeEventState(str, Enum):
    PLANNED = "planned"
    CONSUMED = "consumed"


@unique
class AmountInputUnit(str, Enum):
    """Unidades de entrada de cantidad que la interfaz puede emitir.

    Es el enum central de unidades que exige measurement_conventions.md §11:
    el código interno de una unidad cerrada vive aquí y no se escribe como
    texto libre en rutas ni componentes. Los valores son los códigos estables
    de §4.2 de ese mismo documento.

    Solo están los dos que hoy emite algún control real (el selector de
    cantidad ingerida del `confirm` del carrito). Los demás de §4.2
    (`portion`, `lb`, `oz`) se añaden aquí, junto con su factor de conversión
    a gramos, cuando exista la interfaz que los use; no se declaran antes para
    no publicar unidades que ningún boundary sabe convertir.

    Ninguna de estas unidades se persiste: deciden cómo se interpreta la
    cantidad recibida antes de convertirla a la unidad canónica (gramos).
    """
    GRAMS = "g"
    PERCENT = "%"


@unique
class PortionOrigin(str, Enum):
    """Where the food of a portion comes from (`portion_detail` origin arc)."""
    CATALOG = "catalog"
    MANUAL_INTAKE = "manual_intake"


@unique
class PortionDestination(str, Enum):
    """Where a portion is assigned (`portion_detail` destination arc).

    FRIDGE has no writer yet: the enum describes the model, not the interface
    (decision 2026-09-22).
    """
    INTAKE_EVENT = "intake_event"
    RECIPE = "recipe"
    FRIDGE = "fridge"


# Sanity ceiling for every mass in grams shared by more than one table
# (measurement_conventions.md 6.9.2): 100000 g = 100 kg. It is not a clinical
# limit, only a ceiling so a corrupt or manipulated value is not stored as if
# it were plausible. Declared once (4.7) and reused by `intake_event` and
# `portion_detail`.
MASS_SANITY_MAX_G = 100000


# Technical whitelists (4.6) for the food-state fields that still have no
# catalog table (4.5). They are provisional: once those tables exist their
# rows replace these lists. They live in `domain/` because the persistence
# layer has to validate against them, and a presentation module cannot be the
# source of a persistence rule (decision 2026-09-22).
INITIAL_STATE_OPTIONS = ["solid", "mashed/creamy", "liquid", "gel"]
COOKING_OPTIONS = [
    "steam",
    "boiled-al-dente",
    "boiled-soft",
    "fried",
    "raw",
    "oven",
    "airfryer",
    "toaster",
    "griddle",
]
CONSERVATION_OPTIONS = ["freshly-made", "fridge", "freezer", "pre-cooked"]


class Clear:
    """Sentinel for a partial update: "present but empty", write NULL (7.4).

    A field left out of the payload is `None` ("do not touch"); an explicit
    clearing is the `CLEAR` singleton. The two states cannot share a value.
    """

    def __repr__(self) -> str:
        return "CLEAR"


CLEAR = Clear()


def sql_in_list(enum_cls) -> str:
    """Lista de valores del enum para un CHECK: "'rapid', 'basal'".

    Los valores son constantes de código, no datos de una petición: la regla de
    parametrización de code_conventions.md 11.9 se refiere a valores dinámicos.
    Generarla aquí garantiza que el CHECK coincida siempre con el enum (4.4).
    """
    return ", ".join(f"'{member.value}'" for member in enum_cls)
