"""Mappers de fila SQL a dataclass de dominio (conventions/code_conventions.md §3.6).

Estos mappers conocen nombres físicos de columna (`users_id` -> `user_id`,
ver §3.5) que el dominio no debe conocer. Las dataclasses en
DayBetes_food/domain/ no se construyen desde una fila SQL en ningún otro
punto del código.
"""

from DayBetes_food.domain.catalog import CatalogItemRead
from DayBetes_food.domain.constants import (
    ConservationMethod,
    CookingMethod,
    FoodCategory,
    FoodPhysicalState,
    InjectionZone,
    IntakeEventState,
    InsulinType,
    MealType,
    Nutriscore,
    PortionDestination,
    PortionOrigin,
)
from DayBetes_food.domain.insulin import InsulinInjectionRead
from DayBetes_food.domain.intake_event import IntakeEventRead
from DayBetes_food.domain.intake_plate import IntakePlateRead
from DayBetes_food.domain.portion_detail import PortionDetailRead, PortionSourceRead
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
            is_published=bool(row["is_published"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row.get("deleted_at"),
            is_favorite=bool(row.get("is_favorite")),
            can_edit=bool(row.get("can_edit")),
            is_listable=bool(row.get("is_listable")),
        )
    except ValueError as exc:
        raise InfrastructureError(f"Invalid catalog category in database row: {exc}") from exc
    except KeyError as exc:
        raise InfrastructureError(f"Missing required field {exc} in catalog row") from exc


def insulin_injection_read_from_row(row: dict) -> InsulinInjectionRead:
    """Convierte fila SQL a InsulinInjectionRead.

    Columnas obligatorias: id, users_id, shot_time, insulin_type, created_at, updated_at, timezone_at_event.
    Columnas nullables: intake_event_id, units, injection_zone, notes, needle_leak, skin_pinch.
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
    )


def intake_event_read_from_row(row: dict) -> IntakeEventRead:
    """Convierte fila SQL a IntakeEventRead.

    La fila debe venir de _INTAKE_EVENT_COLUMNS (queries/intake_event.py), que
    ya expone users_id con el alias user_id (§3.5).
    Columnas obligatorias: id, user_id, state, timezone_at_event, eating_out,
    insulin_dose, created_at, updated_at. El resto son nullables.
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
        quality_confidence=row.get("quality_confidence"),
        carbs_uncertainty=row.get("carbs_uncertainty"),
        sugars_uncertainty=row.get("sugars_uncertainty"),
        fats_uncertainty=row.get("fats_uncertainty"),
        saturated_uncertainty=row.get("saturated_uncertainty"),
        proteins_uncertainty=row.get("proteins_uncertainty"),
        fiber_uncertainty=row.get("fiber_uncertainty"),
        notes=row.get("notes"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row.get("deleted_at"),
    )


def intake_plate_read_from_row(row: dict) -> IntakePlateRead:
    """Convierte fila SQL a IntakePlateRead.

    Columnas obligatorias: id, intake_event_id, created_at, updated_at.
    Columnas nullables: name (NULL = nombre derivado, measurement §4.6.3) y
    offset_minutes (NULL = la tanda todavía no tiene plantilla de offset).
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
            cooking_factor=row.get("source_cooking_factor"),
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
            amount=float(row["amount"]),
            cooking=_enum_from_row(row, "cooking", CookingMethod),
            conservation=_enum_from_row(row, "conservation", ConservationMethod),
            final_state=_enum_from_row(row, "final_state", FoodPhysicalState),
            strictly_weighed=row.get("strictly_weighed"),
            macros_quality=row.get("macros_quality"),
            is_cooked_weight=bool(row.get("is_cooked_weight")),
            offset_minutes=row.get("offset_minutes"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            source=source,
        )
    except KeyError as exc:
        raise InfrastructureError(f"Missing required field {exc} in portion_detail row") from exc
