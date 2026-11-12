"""Mappers from SQL rows to domain dataclasses (conventions/code_conventions.md §3.6).

These mappers know physical column names (`users_id` -> `user_id`, see
§3.5) that the domain must not know. The dataclasses in
DayBetes_food/domain/ are not built from a SQL row anywhere else in the
code.
"""

from DayBetes_food.domain.catalog import CatalogItemRead
from DayBetes_food.domain.ciqual_food import CiqualFoodRead
from DayBetes_food.domain.constants import (
    PenCloseReason,
    PenFormat,
    ConservationMethod,
    CookingMethod,
    FoodCategory,
    FoodPhysicalState,
    FridgeCloseReason,
    GlycemicIndex,
    InjectionZone,
    IntakeEventState,
    InsulinType,
    MealType,
    Nutriscore,
    PortionDestination,
    PortionOrigin,
    Ripeness,
    StorageLocation,
    SystemTag,
)
from DayBetes_food.domain.fridge import FridgeMoveRead, FridgeRead
from DayBetes_food.domain.insulin import InsulinInjectionRead
from DayBetes_food.domain.insulin_pen import InsulinBrandRead, InsulinPenRead
from DayBetes_food.domain.intake_event import IntakeEventRead
from DayBetes_food.domain.intake_plate import IntakePlateRead
from DayBetes_food.domain.manual_intake import ManualIntakeRead
from DayBetes_food.domain.off_product import OffProductRead
from DayBetes_food.domain.recipe import RecipeRead
from DayBetes_food.domain.recipe_plate import RecipePlateRead
from DayBetes_food.domain.tag import TagRead
from DayBetes_food.domain.portion_detail import PortionDetailRead, PortionSourceRead
from DayBetes_food.domain.user_favorite import UserFavoriteAccess
from DayBetes_food.errors import InfrastructureError


def _enum_from_row(row: dict, key: str, enum_cls):
    raw = row.get(key)
    if raw is None:
        return None
    try:
        return enum_cls(raw)
    except ValueError as exc:
        raise InfrastructureError(
            f"Invalid {key} '{raw}' in database row"
        ) from exc


def recipe_read_from_row(row: dict) -> RecipeRead:
    """Convert a SQL row from _RECIPE_COLUMNS to RecipeRead (§3.2). An unknown
    meal_type raises InfrastructureError (§4.3); is_favorite and can_edit come from
    the query."""
    try:
        return RecipeRead(
            id=row["id"],
            user_id=row["users_id"],
            origin_root_id=row.get("origin_root_id"),
            name=row["name"],
            meal_type=MealType(row["meal_type"]) if row.get("meal_type") else None,
            extra_meal_types=tuple(MealType(value) for value in row["extra_meal_types"]),
            notes=row.get("notes"),
            servings=row.get("servings"),
            is_published=row["is_published"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            is_favorite=row["is_favorite"],
            can_edit=row["can_edit"],
        )
    except (KeyError, ValueError) as exc:
        raise InfrastructureError(f"Invalid recipe row: {exc}") from exc


def recipe_plate_read_from_row(row: dict) -> RecipePlateRead:
    try:
        return RecipePlateRead(
            id=row["id"],
            recipe_id=row["recipe_id"],
            position=row["position"],
            name=row.get("name"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    except KeyError as exc:
        raise InfrastructureError(f"Missing required field {exc} in recipe_plate row") from exc


def ciqual_food_read_from_row(row: dict) -> CiqualFoodRead:
    try:
        return CiqualFoodRead(
            code=row["code"],
            name_es=row["name_es"],
            name_en=row["name_en"],
            category_hint=row.get("category_hint"),
            subtype=row.get("subtype"),
            calories_100g=row.get("calories_100g"),
            carbs_100g=row["carbs_100g"],
            sugars_100g=row.get("sugars_100g"),
            fats_100g=row["fats_100g"],
            saturated_100g=row.get("saturated_100g"),
            proteins_100g=row["proteins_100g"],
            fiber_100g=row.get("fiber_100g"),
            alcohol=row.get("alcohol"),
            carbs_confidence=row.get("carbs_confidence"),
            fats_confidence=row.get("fats_confidence"),
            proteins_confidence=row.get("proteins_confidence"),
            value_notes=row.get("value_notes"),
        )
    except KeyError as exc:
        raise InfrastructureError(f"Missing required field {exc} in ciqual_food row") from exc


def off_product_read_from_row(row: dict) -> OffProductRead:
    try:
        return OffProductRead(
            code=row["code"],
            name=row["name"],
            brand=row.get("brand"),
            categories=row.get("categories"),
            calories_100g=row.get("calories_100g"),
            carbs_100g=row["carbs_100g"],
            sugars_100g=row.get("sugars_100g"),
            fats_100g=row["fats_100g"],
            saturated_100g=row.get("saturated_100g"),
            proteins_100g=row["proteins_100g"],
            fiber_100g=row.get("fiber_100g"),
            caffeine=row.get("caffeine"),
            alcohol_vol=row.get("alcohol_vol"),
            default_portion=row.get("default_portion"),
            nutriscore=row.get("nutriscore"),
            nova=row.get("nova"),
        )
    except KeyError as exc:
        raise InfrastructureError(f"Missing required field {exc} in off_product row") from exc


def catalog_item_read_from_row(row: dict) -> CatalogItemRead:
    """Convert a SQL row from _CATALOG_COLUMNS to CatalogItemRead.

    Required columns: id, created_by, name, category, subtype, is_published,
    created_at, updated_at. Nullables are read with `row.get` (§3.2); the
    computed flags (is_favorite, can_edit, is_listable) come from the query.
    """
    try:
        return CatalogItemRead(
            id=int(row["id"]),
            created_by=row.get("created_by"),
            origin_root_id=row.get("origin_root_id"),
            name=row["name"],
            brand_id=row.get("brand_id"),
            brand=row.get("brand"),
            category=FoodCategory(row["category"]),
            subtype=row["subtype"],
            initial_state=_enum_from_row(row, "initial_state", FoodPhysicalState),
            nutriscore=_enum_from_row(row, "nutriscore", Nutriscore),
            nova=row.get("nova"),
            yuka=row.get("yuka"),
            default_portion=row.get("default_portion"),
            calories_100g=row.get("calories_100g"),
            carbs_100g=row.get("carbs_100g"),
            sugars_100g=row.get("sugars_100g"),
            fats_100g=row.get("fats_100g"),
            saturated_100g=row.get("saturated_100g"),
            proteins_100g=row.get("proteins_100g"),
            fiber_100g=row.get("fiber_100g"),
            caffeine=row.get("caffeine"),
            alcohol=row.get("alcohol"),
            barcode=row.get("barcode"),
            cooking_factor=row.get("cooking_factor"),
            macros_quality=row.get("macros_quality"),
            default_strictly_weighed=row.get("default_strictly_weighed"),
            macros_confidence=row.get("macros_confidence"),
            is_published=bool(row["is_published"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row.get("deleted_at"),
            is_favorite=bool(row["is_favorite"]),
            can_edit=bool(row["can_edit"]),
            is_listable=bool(row["is_listable"]),
        )
    except ValueError as exc:
        raise InfrastructureError(f"Invalid catalog category in database row: {exc}") from exc
    except KeyError as exc:
        raise InfrastructureError(f"Missing required field {exc} in catalog row") from exc


def manual_intake_read_from_row(row: dict) -> ManualIntakeRead:
    """Convert a SQL row from _MANUAL_INTAKE_COLUMNS to ManualIntakeRead.

    Required columns: id, created_by, name, carbs_100g, is_quick_add,
    is_published, created_at, updated_at. Nullables are read with `row.get`
    (§3.2); an unknown glycemic_index code raises InfrastructureError (§4.3);
    the computed flags (is_favorite, can_edit, is_listable) come from the query.
    """
    try:
        return ManualIntakeRead(
            id=int(row["id"]),
            created_by=int(row["created_by"]),
            origin_root_id=row.get("origin_root_id"),
            name=row["name"],
            description=row.get("description"),
            subtype=row.get("subtype"),
            origin=row.get("origin"),
            default_portion=row.get("default_portion"),
            calories_100g=row.get("calories_100g"),
            carbs_100g=float(row["carbs_100g"]),
            sugars_100g=row.get("sugars_100g"),
            fats_100g=row.get("fats_100g"),
            saturated_100g=row.get("saturated_100g"),
            proteins_100g=row.get("proteins_100g"),
            fiber_100g=row.get("fiber_100g"),
            caffeine=row.get("caffeine"),
            alcohol=row.get("alcohol"),
            glycemic_index=_enum_from_row(row, "glycemic_index", GlycemicIndex),
            ig_confidence=row.get("ig_confidence"),
            macros_confidence=row.get("macros_confidence"),
            macros_quality=row.get("macros_quality"),
            default_strictly_weighed=row.get("default_strictly_weighed"),
            is_quick_add=bool(row["is_quick_add"]),
            is_published=bool(row["is_published"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row.get("deleted_at"),
            is_favorite=bool(row["is_favorite"]),
            can_edit=bool(row["can_edit"]),
            is_listable=bool(row["is_listable"]),
        )
    except (KeyError, TypeError) as exc:
        raise InfrastructureError(f"Missing required field {exc} in manual_intake row") from exc


def user_favorite_access_from_row(row: dict) -> UserFavoriteAccess:
    try:
        return UserFavoriteAccess(
            is_favorite=bool(row["is_favorite"]),
            is_only_access=bool(row["is_only_access"]),
        )
    except KeyError as exc:
        raise InfrastructureError(f"Missing required field {exc} in user_favorites row") from exc


def insulin_injection_read_from_row(row: dict) -> InsulinInjectionRead:
    """Convert a SQL row to InsulinInjectionRead.

    Required columns: id, users_id, shot_time, insulin_type, created_at, updated_at, timezone_at_event.
    Nullable columns: intake_event_id, units, injection_zone, notes, needle_leak, skin_pinch.
    """
    try:
        insulin_type = InsulinType(row["insulin_type"])
    except ValueError as exc:
        raise InfrastructureError(
            f"Invalid insulin_type '{row['insulin_type']}' in database row"
        ) from exc
    except KeyError as exc:
        raise InfrastructureError(f"Missing required field {exc} in insulin injection row") from exc

    injection_zone_raw = row.get("injection_zone")
    injection_zone = None
    if injection_zone_raw:
        try:
            injection_zone = InjectionZone(injection_zone_raw)
        except ValueError as exc:
            raise InfrastructureError(
                f"Invalid injection_zone '{injection_zone_raw}' in database row"
            ) from exc

    return InsulinInjectionRead(
        id=int(row["id"]),
        user_id=int(row["users_id"]),
        intake_event_id=row.get("intake_event_id"),
        shot_time=row["shot_time"],
        timezone_at_event=row["timezone_at_event"],
        insulin_type=insulin_type,
        units=row.get("units"),
        injection_zone=injection_zone,
        notes=row.get("notes"),
        needle_leak=row.get("needle_leak"),
        skin_pinch=row.get("skin_pinch"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        insulin_pen_id=row.get("insulin_pen_id"),
    )


def intake_event_read_from_row(row: dict) -> IntakeEventRead:
    """Convert a SQL row to IntakeEventRead.

    The row must come from _INTAKE_EVENT_COLUMNS (queries/intake_event.py),
    which already exposes users_id with the alias user_id (§3.5).
    Required columns: id, user_id, state, timezone_at_event, eating_out,
    insulin_dose, created_at, updated_at. The rest are nullable.
    """
    try:
        state = IntakeEventState(row["state"])
    except ValueError as exc:
        raise InfrastructureError(
            f"Invalid state '{row['state']}' in intake_event row"
        ) from exc
    except KeyError as exc:
        raise InfrastructureError(f"Missing required field {exc} in intake_event row") from exc

    meal_type_raw = row.get("meal_type")
    meal_type = None
    if meal_type_raw:
        try:
            meal_type = MealType(meal_type_raw)
        except ValueError as exc:
            raise InfrastructureError(
                f"Invalid meal_type '{meal_type_raw}' in intake_event row"
            ) from exc

    injection_zone_raw = row.get("injection_zone")
    injection_zone = None
    if injection_zone_raw:
        try:
            injection_zone = InjectionZone(injection_zone_raw)
        except ValueError as exc:
            raise InfrastructureError(
                f"Invalid injection_zone '{injection_zone_raw}' in intake_event row"
            ) from exc

    return IntakeEventRead(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        state=state,
        meal_type=meal_type,
        name=row.get("name"),
        meal_time=row.get("meal_time"),
        timezone_at_event=row["timezone_at_event"],
        eating_out=bool(row["eating_out"]),
        insulin_dose=bool(row["insulin_dose"]),
        injection_zone=injection_zone,
        ingested_amount=row.get("ingested_amount"),
        amount_confidence=row.get("amount_confidence"),
        notes=row.get("notes"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row.get("deleted_at"),
        insulin_pen_id=row.get("insulin_pen_id"),
        insulin_units=float(row["insulin_units"]) if row.get("insulin_units") is not None else None,
    )


def intake_plate_read_from_row(row: dict) -> IntakePlateRead:
    """Convert a SQL row to IntakePlateRead.

    Required columns: id, intake_event_id, created_at, updated_at.
    Nullable columns: name (NULL = derived name, measurement §4.6.3) and
    offset_minutes (NULL = the plate has no offset template yet).
    """
    try:
        return IntakePlateRead(
            id=int(row["id"]),
            intake_event_id=int(row["intake_event_id"]),
            name=row.get("name"),
            offset_minutes=row.get("offset_minutes"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    except KeyError as exc:
        raise InfrastructureError(f"Missing required field {exc} in intake plate row") from exc


def fridge_read_from_row(row: dict) -> FridgeRead:
    """Convert a SQL row from _FRIDGE_COLUMNS (queries/fridge.py) to FridgeRead.

    Nullable columns: name (NULL = derived name), content_weight (NULL = not
    weighed), closed_at and closed_reason (NULL = still stored). An unknown value raises
    InfrastructureError (§4.3).
    """
    try:
        content_weight = row.get("content_weight")
        return FridgeRead(
            id=int(row["id"]),
            user_id=int(row["users_id"]),
            name=row.get("name"),
            location=StorageLocation(row["location"]),
            stored_at=row["stored_at"],
            expires_at=row["expires_at"],
            content_weight=float(content_weight) if content_weight is not None else None,
            closed_at=row.get("closed_at"),
            closed_reason=FridgeCloseReason(row["closed_reason"]) if row.get("closed_reason") else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    except (KeyError, ValueError) as exc:
        raise InfrastructureError(f"Invalid fridge row: {exc}") from exc


def fridge_move_read_from_row(row: dict) -> FridgeMoveRead:
    """Convert a SQL row of `fridge_move` to FridgeMoveRead (all columns required)."""
    try:
        return FridgeMoveRead(
            from_location=StorageLocation(row["from_location"]),
            to_location=StorageLocation(row["to_location"]),
            moved_at=row["moved_at"],
        )
    except (KeyError, ValueError) as exc:
        raise InfrastructureError(f"Invalid fridge_move row: {exc}") from exc


def _single_arc_column(row: dict, columns: tuple[str, ...], arc: str) -> str:
    present = [column for column in columns if row.get(column) is not None]
    if len(present) != 1:
        raise InfrastructureError(
            f"portion_detail row has {len(present)} {arc} columns set (expected exactly 1)"
        )
    return present[0]


def portion_detail_read_from_row(row: dict) -> PortionDetailRead:
    """Convert a SQL row to PortionDetailRead.

    The row must come from _PORTION_COLUMNS (queries/portion_detail.py). The
    origin/destination are derived from which arc column is not null; the CHECK
    guarantees exactly one, so a different count is corruption, not a silent
    `None`. Source columns come prefixed with `source_`.
    """
    try:
        origin_column = _single_arc_column(row, ("catalog_id", "manual_intake_id"), "origin")
        destination_column = _single_arc_column(
            row, ("intake_event_id", "recipe_id", "fridge_id"), "destination"
        )
        origin = PortionOrigin.CATALOG if origin_column == "catalog_id" else PortionOrigin.MANUAL_INTAKE
        destination = PortionDestination(destination_column.removesuffix("_id"))
        source_unit_g = row.get("source_unit_g")
        source = PortionSourceRead(
            name=row.get("source_name"),
            unit_g=(float(source_unit_g) if source_unit_g is not None else None),
            category=row.get("source_category"),
            subtype=row.get("source_subtype"),
            is_quick_add=bool(row["source_is_quick_add"]),
            cooking_factor=row.get("source_cooking_factor"),
            macros_quality=row.get("source_macros_quality"),
            calories_100g=row.get("source_calories_100g"),
            carbs_100g=row.get("source_carbs_100g"),
            sugars_100g=row.get("source_sugars_100g"),
            fats_100g=row.get("source_fats_100g"),
            saturated_100g=row.get("source_saturated_100g"),
            proteins_100g=row.get("source_proteins_100g"),
            fiber_100g=row.get("source_fiber_100g"),
        )
        return PortionDetailRead(
            id=int(row["id"]),
            origin=origin,
            origin_id=int(row[origin_column]),
            destination=destination,
            destination_id=int(row[destination_column]),
            plate_id=row.get("plate_id"),
            recipe_plate_id=row.get("recipe_plate_id"),
            amount=float(row["amount"]),
            cooking=_enum_from_row(row, "cooking", CookingMethod),
            conservation=_enum_from_row(row, "conservation", ConservationMethod),
            final_state=_enum_from_row(row, "final_state", FoodPhysicalState),
            ripeness=_enum_from_row(row, "ripeness", Ripeness),
            strictly_weighed=row.get("strictly_weighed"),
            is_cooked_weight=bool(row.get("is_cooked_weight")),
            offset_minutes=row.get("offset_minutes"),
            source_fridge_id=row.get("source_fridge_id"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            source=source,
        )
    except KeyError as exc:
        raise InfrastructureError(f"Missing required field {exc} in portion_detail row") from exc


def tag_read_from_row(row: dict) -> TagRead:
    """Convert a SQL row of `tags` (queries/tags.py, queries/linked_tags.py).
    Nullable: users_id (system tag) and system_key (personal tag). An unknown
    system_key raises InfrastructureError (§4.3)."""
    try:
        system_key = row.get("system_key")
        user_id = row.get("users_id")
        return TagRead(
            id=int(row["id"]),
            user_id=int(user_id) if user_id is not None else None,
            system_key=SystemTag(system_key) if system_key is not None else None,
            name=row["name"],
            color=row["color"],
        )
    except (KeyError, ValueError) as exc:
        raise InfrastructureError(f"Invalid tags row: {exc}") from exc


def insulin_brand_read_from_row(row: dict) -> InsulinBrandRead:
    """Convert a SQL row from _BRAND_COLUMNS (queries/insulin_brand.py). Every column
    is required; an unknown insulin_type raises InfrastructureError (§4.3)."""
    try:
        return InsulinBrandRead(
            id=int(row["id"]),
            user_id=int(row["users_id"]),
            name=row["name"],
            insulin_type=InsulinType(row["insulin_type"]),
            in_use_days=int(row["in_use_days"]),
            pen_units=float(row["pen_units"]),
            pen_count=int(row["pen_count"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    except (KeyError, ValueError) as exc:
        raise InfrastructureError(f"Invalid insulin_brand row: {exc}") from exc


def insulin_pen_read_from_row(row: dict) -> InsulinPenRead:
    """Convert a SQL row from _PEN_SELECT (queries/insulin_pen.py). Nullable columns:
    closed_at and closed_reason (NULL = in use). The usage columns are aggregates
    of its injections (measurement §8.4)."""
    try:
        return InsulinPenRead(
            id=int(row["id"]),
            user_id=int(row["users_id"]),
            brand_id=int(row["insulin_brand_id"]),
            brand_name=row["brand_name"],
            insulin_type=InsulinType(row["insulin_type"]),
            format=PenFormat(row["format"]),
            opened_at=row["opened_at"],
            expires_at=row["expires_at"],
            capacity_units=float(row["capacity_units"]),
            closed_at=row.get("closed_at"),
            closed_reason=PenCloseReason(row["closed_reason"]) if row.get("closed_reason") else None,
            injection_count=int(row["injection_count"]),
            dosed_units=float(row["dosed_units"]),
            undosed_count=int(row["undosed_count"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    except (KeyError, ValueError) as exc:
        raise InfrastructureError(f"Invalid insulin_pen row: {exc}") from exc
