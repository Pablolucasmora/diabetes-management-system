"""Read dataclasses of an entry of the Food list (a food, a dish or a recipe)
that do not belong to a single entity.

This module imports no psycopg, routes or components (code_conventions.md
§3.6).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FoodEntrySummary:
    """What the actions pop-up of a Food row shows and allows
    (frontend_conventions.md §9.3.1): its name, the line under it (brand,
    origin or "Recipe") and whether the viewer can edit it."""
    name: str
    subtitle: str
    can_edit: bool
