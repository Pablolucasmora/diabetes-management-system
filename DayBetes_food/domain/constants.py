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


def sql_in_list(enum_cls) -> str:
    """Lista de valores del enum para un CHECK: "'rapid', 'basal'".

    Los valores son constantes de código, no datos de una petición: la regla de
    parametrización de code_conventions.md 11.9 se refiere a valores dinámicos.
    Generarla aquí garantiza que el CHECK coincida siempre con el enum (4.4).
    """
    return ", ".join(f"'{member.value}'" for member in enum_cls)
