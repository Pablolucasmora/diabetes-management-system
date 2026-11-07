"""Presentation constants shared by the Food components (foods.py, food_actions.py,
fridge.py), kept apart so that none of them has to import another just for these
(code_conventions.md §3.6: labels live in components)."""

from DayBetes_food.domain.constants import StorageLocation

# One style for every field of the create and edit forms: full width, a
# comfortable touch height and text-sm (frontend_conventions.md §2, §8).
FORM_FIELD_CLS = "web_input w-full rounded-lg border border-line px-3 py-2 text-sm"

# Where a food can be saved instead of a meal (frontend_conventions.md §9.4).
STORAGE_LABELS = {StorageLocation.FRIDGE: "Fridge", StorageLocation.FREEZER: "Freezer"}
