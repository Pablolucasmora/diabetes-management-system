"""Presentation pieces shared by the Food components (foods.py, food_actions.py,
fridge.py), kept apart so that none of them has to import another just for these
(code_conventions.md §3.6: labels live in components)."""

from fasthtml.common import Div, Input, Label, Select

from DayBetes_food.domain.constants import StorageLocation

# The look of every field of the forms: a comfortable touch height and text-sm
# (frontend_conventions.md §2, §8). FORM_FIELD_CLS adds the full width.
_FIELD_LOOK_CLS = "web_input rounded-lg border border-line px-3 py-2 text-sm"
FORM_FIELD_CLS = f"{_FIELD_LOOK_CLS} w-full"

# Where a food can be saved instead of a meal (frontend_conventions.md §9.4).
STORAGE_LABELS = {StorageLocation.FRIDGE: "Fridge", StorageLocation.FREEZER: "Freezer"}


def AmountUnitField(input_id: str, value: str, unit_options: list):
    """An amount and its unit on one row, inside a pop-up: the amount takes the
    room, so what is typed shows, and the unit only what its text needs."""
    return Div(
        Label("Amount", cls="text-xs text-gray-700", **{"for": input_id}),
        Div(
            Input(
                type="text",
                id=input_id,
                name="amount_value",
                value=value,
                inputmode="decimal",
                onclick="this.select()",
                cls=f"{_FIELD_LOOK_CLS} flex-1 min-w-0",
            ),
            Select(*unit_options, name="amount_unit", aria_label="Unit", cls=f"{_FIELD_LOOK_CLS} shrink-0 max-w-[55%]"),
            cls="flex items-center gap-2",
        ),
        cls="flex flex-col gap-1",
    )
