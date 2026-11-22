"""Turning a provisional food into a dish, or a dish into a food (code_conventions.md
§8.12, "Alimentos provisionales"; decision of the user, 2026-11-21).

DiaBot can pick the wrong kind. While the entry is still to review only its owner
uses it, so it can change kind: a new entry of the other kind with the same data,
still to review, takes its portions, favorites and tags, and the old one is
deleted. One transaction (§2.3). A reviewed entry never changes kind: it may be in
recipes, favorites or published.
"""

from dataclasses import fields

from DayBetes_food.database.queries import (
    count_cooked_weight_portions,
    create_catalog_item,
    create_food_brand,
    create_manual_intake,
    delete_provisional_entry,
    get_catalog_item,
    get_food_brand_id_by_label,
    get_manual_intake,
    list_entry_portions,
    move_entry_references,
    point_portion_at_dish,
)
from DayBetes_food.domain.catalog import CatalogItemCreate
from DayBetes_food.domain.constants import AmountMethod, FoodCategory, FoodEntryType
from DayBetes_food.domain.manual_intake import ManualIntakeCreate
from DayBetes_food.domain.nutrition import NutrientValues
from DayBetes_food.errors import ConflictError, NotFoundError, ValidationError


def _nutrients(item) -> NutrientValues:
    return NutrientValues(**{field.name: getattr(item, field.name) for field in fields(NutrientValues)})


def _provisional(connection, user_id: int, entry_type: FoodEntryType, entry_id: int):
    if entry_type is FoodEntryType.CATALOG:
        item = get_catalog_item(connection, user_id, entry_id)
    else:
        item = get_manual_intake(connection, user_id, entry_id)
    if item is None or not item.can_edit:
        raise NotFoundError("Food not found.")
    if not item.needs_review:
        raise ConflictError("Only a food to review can change between food and dish.")
    return item


def convert_provisional(
    connection, user_id: int, entry_type: FoodEntryType, entry_id: int, category: FoodCategory | None = None
) -> tuple[FoodEntryType, int]:
    """Change a provisional entry to the other kind; returns the new one. A food
    needs a category, which a dish does not have: the user gives it."""
    with connection.transaction():
        item = _provisional(connection, user_id, entry_type, entry_id)
        if entry_type is FoodEntryType.CATALOG:
            if count_cooked_weight_portions(connection, entry_type, entry_id):
                # A dish has no cooking factor: those grams would count wrong.
                raise ConflictError("It was weighed cooked in a meal: a dish cannot keep that. Edit it as a food.")
            target_type = FoodEntryType.MANUAL_INTAKE
            try:
                target_id = create_manual_intake(
                    connection,
                    ManualIntakeCreate(
                        created_by=user_id,
                        origin_root_id=None,
                        name=item.name,
                        description=None,
                        subtype=item.subtype,
                        # The brand is who made it: the dish's origin.
                        origin=item.brand,
                        default_portion=item.default_portion,
                        nutrients=_nutrients(item),
                        glycemic_index=None,
                        ig_confidence=None,
                        macros_confidence=item.macros_confidence,
                        macros_source=item.macros_source,
                        default_amount_method=item.default_amount_method,
                        serving_method=item.serving_method,
                        needs_review=True,
                    ),
                    commit=False,
                )
            except ConflictError as error:
                raise ConflictError("You already have a dish with this name and origin.") from error
        else:
            if category is None:
                raise ValidationError("Choose the category of the food.", fields={"category": "required"})
            target_type = FoodEntryType.CATALOG
            brand_id = None
            if item.origin:
                brand_id = get_food_brand_id_by_label(connection, item.origin) or create_food_brand(
                    connection, item.origin, commit=False
                )
            try:
                target_id = create_catalog_item(
                    connection,
                    CatalogItemCreate(
                        created_by=user_id,
                        origin_root_id=None,
                        name=item.name,
                        brand_id=brand_id,
                        category=category,
                        subtype=item.subtype or category.value,
                        initial_state=None,
                        nutriscore=None,
                        nova=None,
                        yuka=None,
                        default_portion=item.default_portion,
                        nutrients=_nutrients(item),
                        barcode=None,
                        cooking_factor=None,
                        macros_source=item.macros_source,
                        default_amount_method=item.default_amount_method,
                        serving_method=item.serving_method,
                        macros_confidence=item.macros_confidence,
                        needs_review=True,
                    ),
                    commit=False,
                )
            except ConflictError as error:
                raise ConflictError("You already have a food with this name and brand.") from error
        move_entry_references(connection, user_id, (entry_type, entry_id), (target_type, target_id))
        if not delete_provisional_entry(connection, user_id, entry_type, entry_id):
            raise ConflictError("Only a food to review can change between food and dish.")
    return target_type, target_id


def make_quick_add(connection, user_id: int, entry_type: FoodEntryType, entry_id: int) -> int:
    """A provisional entry the user does not want to keep (decision of the user,
    2026-11-22): each of its portions in a meal becomes a quick add of its own
    (a quick add only exists through its portion, §11.2.3), with its name, its
    origin (a food's brand), its macros and the grams of that portion, and the
    entry is deleted with its favorites and tags. Returns how many quick adds
    were made; none when nothing used it, and it is only deleted.

    Raises:
        NotFoundError: not one of the user's entries.
        ConflictError: no longer to review; or in a recipe or a tupper, where a
            quick add cannot be; or weighed cooked, which a dish cannot keep.
    """
    with connection.transaction():
        item = _provisional(connection, user_id, entry_type, entry_id)
        portions = list_entry_portions(connection, entry_type, entry_id)
        if any(portion["intake_event_id"] is None for portion in portions):
            raise ConflictError("It is in a recipe or a tupper, where a quick add cannot be. Review it instead.")
        if any(portion["is_cooked_weight"] for portion in portions):
            raise ConflictError("It was weighed cooked in a meal: a quick add cannot keep that. Review it instead.")
        origin = item.brand if entry_type is FoodEntryType.CATALOG else item.origin
        for portion in portions:
            quick_add_id = create_manual_intake(
                connection,
                ManualIntakeCreate(
                    created_by=user_id,
                    origin_root_id=None,
                    name=item.name,
                    description=None,
                    subtype=None,
                    origin=origin,
                    default_portion=float(portion["amount"]),
                    nutrients=_nutrients(item),
                    glycemic_index=None,
                    ig_confidence=None,
                    macros_confidence=None,
                    macros_source=item.macros_source,
                    default_amount_method=(
                        AmountMethod(portion["amount_method"]) if portion["amount_method"] else None
                    ),
                    serving_method=None,
                    is_quick_add=True,
                ),
                commit=False,
            )
            point_portion_at_dish(connection, portion["id"], entry_type, quick_add_id)
        if not delete_provisional_entry(connection, user_id, entry_type, entry_id):
            raise ConflictError("Only a food to review can become a quick add.")
    return len(portions)
