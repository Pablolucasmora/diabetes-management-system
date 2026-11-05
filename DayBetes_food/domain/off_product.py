"""Dataclass of `off_product`, the local copy of Open Food Facts
(measurement_conventions.md §12.2).

Read-only reference data: the app never writes it. The values are checked
again when they prefill a form (integrations/open_food_facts.py).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class OffProductRead:
    code: str
    name: str
    brand: str | None
    categories: str | None
    calories_100g: float | None
    carbs_100g: float
    sugars_100g: float | None
    fats_100g: float
    saturated_100g: float | None
    proteins_100g: float
    fiber_100g: float | None
    caffeine: float | None  # mg/100 g
    alcohol_vol: float | None  # % vol, as OFF declares it; converted on prefill
    default_portion: float | None
    nutriscore: str | None
    nova: int | None
