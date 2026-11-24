"""Preparation buttons shared by DiaBot (frontend_conventions.md §9.11) and the
preparation to confirm of the cart and the food page (§7.1, §9.4)."""

from fasthtml.common import *

from DayBetes_food.domain.constants import ConservationMethod, CookingMethod, FoodPhysicalState

# How each preparation value reads on its button, per field (§9.11).
PREPARATION_LABELS = {
    "cooking": {
        CookingMethod.STEAM.value: "Steamed",
        CookingMethod.BOILED_AL_DENTE.value: "Al dente",
        CookingMethod.BOILED_SOFT.value: "Boiled",
        CookingMethod.FRIED.value: "Fried",
        CookingMethod.RAW.value: "Raw",
        CookingMethod.OVEN.value: "Oven",
        CookingMethod.AIRFRYER.value: "Air fryer",
        CookingMethod.TOASTER.value: "Toasted",
        CookingMethod.GRIDDLE.value: "Griddle",
    },
    "final_state": {
        FoodPhysicalState.SOLID.value: "Solid",
        FoodPhysicalState.MASHED_CREAMY.value: "Mashed",
        FoodPhysicalState.LIQUID.value: "Liquid",
        FoodPhysicalState.GEL.value: "Gel",
    },
    "conservation": {
        ConservationMethod.FRESHLY_MADE.value: "Fresh",
        ConservationMethod.FRIDGE.value: "Fridge",
        ConservationMethod.FREEZER.value: "Frozen",
        ConservationMethod.PRE_COOKED.value: "Pre-cooked",
    },
}
PREPARATION_FIELD_LABELS = {"cooking": "Cooked", "final_state": "Texture", "conservation": "Kept"}

# A chosen pill is dark, the others `control` (§9.11).
PILL_BASE_CLS = "rounded-full px-2.5 py-1 text-xs font-medium transition cursor-pointer active:scale-95 "
PILL_CHOSEN_CLS = "bg-ink text-white border border-ink hover:opacity-80"
PILL_IDLE_CLS = "bg-control border border-line text-gray-800 hover:bg-white"


def pill_cls(chosen: bool) -> str:
    return PILL_BASE_CLS + (PILL_CHOSEN_CLS if chosen else PILL_IDLE_CLS)


def PreparationToConfirm(
    options: dict,
    food_name: str,
    *,
    hx_post: str | None = None,
    hx_target: str | None = None,
    scope_id: str | None = None,
    dismiss_key: str | None = None,
):
    """The preparation to confirm (frontend_conventions.md §7.1, §9.4): per
    missing field, its offered values with the first chosen beforehand, and a
    tick. Choosing is local (static/js/preparation_confirm.js). With `hx_post`
    (the cart) the tick saves the chosen fields; without it (the food page) it
    copies them to the `Preparation` fields inside the element `scope_id`. Either
    way the block folds away. `Dismiss` removes it without saving; with
    `dismiss_key` (the cart) the browser remembers it.
    """
    rows = []
    inputs = []
    for field_name, values in options.items():
        labels = PREPARATION_LABELS[field_name]
        chosen = values[0] if values else ""
        # The cart's tick sends them; on the food page they have no name, so the
        # page's own form keeps sending only its `Preparation` fields.
        if hx_post:
            inputs.append(Input(type="hidden", name=field_name, value=chosen, data_prep_input=field_name))
        rows.append(
            Div(
                Span(PREPARATION_FIELD_LABELS[field_name], cls="w-14 shrink-0 web_section_label"),
                Div(
                    *[
                        Button(
                            labels.get(value, value),
                            type="button",
                            aria_pressed="true" if value == chosen else "false",
                            data_prep_pill=field_name,
                            data_prep_value=value,
                            cls=pill_cls(value == chosen),
                        )
                        for value in values
                    ],
                    cls="flex flex-wrap gap-1.5",
                ),
                role="group",
                aria_label=PREPARATION_FIELD_LABELS[field_name],
                cls="flex items-center gap-2",
            )
        )
    tick_attrs = (
        {"hx_post": hx_post, "hx_include": "closest form", "hx_target": hx_target, "hx_swap": "outerHTML"}
        if hx_post
        else {}
    )
    container = Form if hx_post else Div
    return container(
        *inputs,
        # Top right of the block, away from the tick (frontend §7.1).
        Button(
            Img(src="/images/content/dismiss.svg", alt="", cls="w-5 h-5"),
            type="button",
            aria_label=f"Dismiss the suggested preparation of {food_name}",
            title="Dismiss",
            data_prep_dismiss="true",
            cls="absolute top-1 right-1 w-8 h-8 rounded-full flex items-center justify-center bg-transparent "
            "hover:bg-control cursor-pointer transition-colors active:scale-95",
        ),
        *rows,
        Button(
            "✓",
            type="button",
            aria_label=f"Confirm preparation of {food_name}",
            title="Confirm preparation",
            data_prep_tick="save" if hx_post else "copy",
            cls="self-start rounded-full w-8 h-8 flex items-center justify-center text-sm font-semibold "
            "bg-ink text-white cursor-pointer hover:opacity-80 active:scale-95",
            **tick_attrs,
        ),
        data_prep_confirm="true",
        data_prep_mode="save" if hx_post else "copy",
        data_prep_scope=scope_id,
        data_prep_key=dismiss_key,
        data_chosen_cls=PILL_CHOSEN_CLS,
        data_idle_cls=PILL_IDLE_CLS,
        cls="relative flex flex-col gap-1.5 rounded-xl border border-dashed border-line pl-2.5 pr-10 py-2",
    )
