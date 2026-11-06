"""Dataclass of `ciqual_food`, the local copy of Ciqual
(measurement_conventions.md §12.3). Read-only reference data."""

import re
from dataclasses import dataclass

from DayBetes_food.errors import ValidationError

_CODE_RE = re.compile(r"[0-9]{1,10}")


def parse_ciqual_code(raw) -> int | None:
    """The code of a URL (code_conventions.md §7.8). '' -> None; malformed -> 422."""
    text = str(raw or "").strip()
    if not text:
        return None
    if not _CODE_RE.fullmatch(text):
        raise ValidationError("Invalid Ciqual code.", fields={"ciqual": "format"})
    return int(text)


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
