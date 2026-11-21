"""View models of a food, a dish or a recipe for the Food pages, built from their read models."""

from DayBetes_food.domain.catalog import CatalogItemRead
from DayBetes_food.domain.recipe import RecipeRead
from DayBetes_food.domain.manual_intake import ManualIntakeRead


def catalog_entry_view(item: CatalogItemRead) -> dict:
    """The only adapter from CatalogItemRead to the dict the shared food
    components expect (debt: they will become dataclasses when manual_intake and
    recipe have theirs)."""
    return {
        "entry_type": "catalog",
        "id": item.id,
        "name": item.name,
        "brand": item.brand,
        "brand_id": item.brand_id,
        "category": item.category.value,
        "initial_state": item.initial_state.value if item.initial_state else None,
        "nutriscore": item.nutriscore.value if item.nutriscore else None,
        "subtype": item.subtype,
        "nova": item.nova,
        "yuka": item.yuka,
        "default_portion": item.default_portion,
        "calories_100g": item.calories_100g,
        "carbs_100g": item.carbs_100g,
        "sugars_100g": item.sugars_100g,
        "fats_100g": item.fats_100g,
        "saturated_100g": item.saturated_100g,
        "proteins_100g": item.proteins_100g,
        "fiber_100g": item.fiber_100g,
        "caffeine": item.caffeine,
        "alcohol": item.alcohol,
        "barcode": item.barcode,
        "cooking_factor": item.cooking_factor,
        "macros_source": item.macros_source.value if item.macros_source else None,
        "default_amount_method": item.default_amount_method.value if item.default_amount_method else None,
        "serving_method": item.serving_method.value if item.serving_method else None,
        "macros_confidence": item.macros_confidence,
        "is_published": item.is_published,
        "created_by": item.created_by,
        "origin_root_id": item.origin_root_id,
        "deleted_at": item.deleted_at,
        "favorite": item.is_favorite,
        "can_edit": item.can_edit,
        "is_listable": item.is_listable,
    }


def manual_intake_entry_view(item: ManualIntakeRead) -> dict:
    """The only adapter from ManualIntakeRead to the dict the shared food
    components expect (same debt as catalog_entry_view)."""
    return {
        "entry_type": "manual_intake",
        "id": item.id,
        "name": item.name,
        "origin": item.origin,
        "description": item.description,
        "subtype": item.subtype,
        "default_portion": item.default_portion,
        "calories_100g": item.calories_100g,
        "carbs_100g": item.carbs_100g,
        "sugars_100g": item.sugars_100g,
        "fats_100g": item.fats_100g,
        "saturated_100g": item.saturated_100g,
        "proteins_100g": item.proteins_100g,
        "fiber_100g": item.fiber_100g,
        "caffeine": item.caffeine,
        "alcohol": item.alcohol,
        "glycemic_index": item.glycemic_index.value if item.glycemic_index else None,
        "ig_confidence": item.ig_confidence,
        "macros_confidence": item.macros_confidence,
        "macros_source": item.macros_source.value if item.macros_source else None,
        "default_amount_method": item.default_amount_method.value if item.default_amount_method else None,
        "serving_method": item.serving_method.value if item.serving_method else None,
        "is_published": item.is_published,
        "created_by": item.created_by,
        "origin_root_id": item.origin_root_id,
        "deleted_at": item.deleted_at,
        "favorite": item.is_favorite,
        "can_edit": item.can_edit,
        "is_listable": item.is_listable,
    }


def recipe_entry_view(item: RecipeRead) -> dict:
    """The only adapter from RecipeRead to the dict the shared food components
    expect (same debt as catalog_entry_view)."""
    return {
        "entry_type": "recipe",
        "id": item.id,
        "created_by": item.user_id,
        "origin_root_id": item.origin_root_id,
        "name": item.name,
        "meal_type": item.meal_type.value if item.meal_type else None,
        "extra_meal_types": [meal_type.value for meal_type in item.extra_meal_types],
        "notes": item.notes,
        "servings": item.servings,
        "is_published": item.is_published,
        "favorite": item.is_favorite,
        "can_edit": item.can_edit,
    }
