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
