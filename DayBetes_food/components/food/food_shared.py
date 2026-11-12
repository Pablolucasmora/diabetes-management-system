"""Presentation pieces shared by the Food components (foods.py, food_actions.py,
fridge.py), kept apart so that none of them has to import another just for these
(code_conventions.md §3.6: labels live in components)."""

from fasthtml.common import Div, Input, Label, Select

from DayBetes_food.domain.constants import AmountMethod, MacrosSource, StorageLocation

# The look of every field of the forms: a comfortable touch height and text-sm
# (frontend_conventions.md §2, §8). FORM_FIELD_CLS adds the full width.
_FIELD_LOOK_CLS = "web_input rounded-lg border border-line px-3 py-2 text-sm"
FORM_FIELD_CLS = f"{_FIELD_LOOK_CLS} w-full"
# The same look for a field that sits next to its label and keeps its own width.
INLINE_FIELD_CLS = f"{_FIELD_LOOK_CLS} w-auto min-w-0"

# Where a food can be saved instead of a meal (frontend_conventions.md §9.4).
STORAGE_LABELS = {StorageLocation.FRIDGE: "Fridge", StorageLocation.FREEZER: "Freezer"}

# U1 and U2 (study_conventions.md §6.3), in the food forms, the food page and the cart.
MACROS_SOURCE_LABELS = {
    MacrosSource.LABEL: "Package label",
    MacrosSource.OFFICIAL: "Menu or official website",
    MacrosSource.OPEN_FOOD_FACTS: "Open Food Facts",
    MacrosSource.REFERENCE_DB: "Food composition table",
    MacrosSource.INGREDIENTS: "Calculated from its ingredients",
    MacrosSource.AI_ESTIMATE: "AI estimate",
    MacrosSource.OWN_ESTIMATE: "My estimate",
}
AMOUNT_METHOD_LABELS = {
    AmountMethod.KITCHEN_SCALE: "Kitchen scale",
    AmountMethod.POCKET_SCALE: "Pocket scale",
    AmountMethod.PACKAGE: "Package weight",
    AmountMethod.HOUSEHOLD: "Household measure",
    AmountMethod.EYEBALL: "By eye",
    AmountMethod.AI_ESTIMATE: "AI estimate",
}
# Empty option of a U1/U2 selector of a portion: "not given", a state of its own.
NOT_GIVEN_LABEL = "- Not given"


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
