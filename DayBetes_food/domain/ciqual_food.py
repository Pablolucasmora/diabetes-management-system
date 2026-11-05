"""Dataclass of `ciqual_food`, the local copy of Ciqual
(measurement_conventions.md §12.3). Read-only reference data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CiqualFoodRead:
    code: int
    name_es: str
    name_en: str
    category_hint: str | None
    subtype: str | None
    calories_100g: float | None
    carbs_100g: float
    sugars_100g: float | None
    fats_100g: float
    saturated_100g: float | None
    proteins_100g: float
    fiber_100g: float | None
    alcohol: float | None
    carbs_confidence: str | None
    fats_confidence: str | None
    proteins_confidence: str | None
    value_notes: str | None
