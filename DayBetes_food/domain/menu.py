"""Dishes read from restaurant menus (code_conventions.md §8.12, "Cartas"; §11.2.12).

What DiaBot keeps of a menu: the place, and for each dish its name, its main
ingredients in DiaBot's own words, its section and its price. Never the photo,
the menu's literal text or macros. Pure logic: no database.
"""

import math
from dataclasses import dataclass
from datetime import datetime

from DayBetes_food.domain.constants import MenuSection
from DayBetes_food.domain.food import normalize_food_text
from DayBetes_food.domain.manual_intake import MANUAL_INTAKE_ORIGIN_MAX_LENGTH
from DayBetes_food.errors import ValidationError

# The place is a dish's origin (§11.2.3): same form and length.
MENU_PLACE_MAX_LENGTH = MANUAL_INTAKE_ORIGIN_MAX_LENGTH
MENU_ITEM_NAME_MAX_LENGTH = 255  # = VARCHAR(255)
MENU_ITEM_DESCRIPTION_MAX_LENGTH = 300  # = VARCHAR(300)
MENU_PRICE_MAX = 999999.99  # = NUMERIC(8,2)
# Dishes one save_menu call may carry, and dishes search_menu returns (§8.12).
MENU_ITEMS_PER_SAVE = 60
MENU_SEARCH_RESULTS_MAX = 8
# Rows the Menus page reads at most, and dishes of each place it shows under All
# places (frontend §9.13); dishes that Food's search shows before `See all`.
MENU_PAGE_ROWS_MAX = 500
MENU_PLACE_PREVIEW = 4
MENU_FOOD_SEARCH_ROWS = 3

# Order and headings of the sections on the Menus page (frontend §9.13).
MENU_SECTION_LABELS = {
    MenuSection.STARTER: "Starters",
    MenuSection.MAIN: "Mains",
    MenuSection.SIDE: "Sides",
    MenuSection.DESSERT: "Desserts",
    MenuSection.DRINK: "Drinks",
    MenuSection.OTHER: "Other",
}


@dataclass(frozen=True)
class MenuItemCreate:
    name: str
    description: str | None
    section: MenuSection
    price: float | None


@dataclass(frozen=True)
class MenuItemRead:
    id: int
    place: str
    name: str
    description: str | None
    section: MenuSection
    price: float | None
    updated_at: datetime


@dataclass(frozen=True)
class MenuPlace:
    """One place of the Menus page: its name, how many dishes and when last saved."""
    place: str
    item_count: int
    updated_at: datetime


def _text(raw, field: str, max_length: int, *, required: bool) -> str | None:
    if raw is None:
        if required:
            raise ValidationError(f"{field} is required.", fields={field: "required"})
        return None
    if not isinstance(raw, str):
        raise ValidationError(f"{field} must be text.", fields={field: "invalid"})
    text = normalize_food_text(raw)
    if not text:
        if required:
            raise ValidationError(f"{field} is required.", fields={field: "required"})
        return None
    if len(text) > max_length:
        raise ValidationError(f"{field} can have at most {max_length} characters.", fields={field: "too_long"})
    return text


def parse_menu_place(raw) -> str:
    """The place of a menu, normalized like a dish's origin; required."""
    return _text(raw, "place", MENU_PLACE_MAX_LENGTH, required=True)


def parse_menu_price(raw) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValidationError("price must be a number.", fields={"price": "invalid"})
    price = float(raw)
    if not math.isfinite(price) or price < 0 or price > MENU_PRICE_MAX:
        raise ValidationError(f"price must be between 0 and {MENU_PRICE_MAX}.", fields={"price": "out_of_range"})
    return round(price, 2)


def parse_menu_items(raw) -> list[MenuItemCreate]:
    """The dishes of a save_menu call, validated. The same name twice (ignoring
    case) keeps the last one, as the unique index would."""
    if not isinstance(raw, list) or not raw:
        raise ValidationError("items must be a list of dishes.", fields={"items": "required"})
    if len(raw) > MENU_ITEMS_PER_SAVE:
        raise ValidationError(
            f"At most {MENU_ITEMS_PER_SAVE} dishes per call: save the rest in another call.",
            fields={"items": "too_many"},
        )
    items: dict[str, MenuItemCreate] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValidationError("Each dish must be an object.", fields={"items": "invalid"})
        try:
            section = MenuSection(entry.get("section"))
        except ValueError as error:
            raise ValidationError("section is not a known section.", fields={"section": "invalid"}) from error
        item = MenuItemCreate(
            name=_text(entry.get("name"), "name", MENU_ITEM_NAME_MAX_LENGTH, required=True),
            description=_text(
                entry.get("description"), "description", MENU_ITEM_DESCRIPTION_MAX_LENGTH, required=False
            ),
            section=section,
            price=parse_menu_price(entry.get("price")),
        )
        items.pop(item.name.lower(), None)
        items[item.name.lower()] = item
    return list(items.values())


def menu_sections(items: list[MenuItemRead]) -> list[tuple[MenuSection, list[MenuItemRead]]]:
    """The dishes of one place by section, in the order of MENU_SECTION_LABELS."""
    by_section: dict[MenuSection, list[MenuItemRead]] = {}
    for item in items:
        by_section.setdefault(item.section, []).append(item)
    return [(section, by_section[section]) for section in MENU_SECTION_LABELS if section in by_section]
