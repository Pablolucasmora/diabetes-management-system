"""Dishes read from restaurant menus (code_conventions.md §8.12, "Cartas";
§11.2.10): pure logic of domain/menu.py, no database."""

from datetime import datetime, timezone

import pytest

from DayBetes_food.domain.constants import MenuSection
from DayBetes_food.domain.menu import (
    MENU_ITEMS_PER_SAVE,
    MenuItemRead,
    menu_sections,
    parse_menu_items,
    parse_menu_place,
    parse_menu_price,
)
from DayBetes_food.errors import ValidationError


def test_place_is_normalized_and_required():
    assert parse_menu_place("  La   Tasca ") == "La Tasca"
    with pytest.raises(ValidationError):
        parse_menu_place("   ")


def test_items_keep_the_last_of_a_repeated_name():
    items = parse_menu_items(
        [
            {"name": "Patatas bravas", "description": None, "section": "starter", "price": None},
            {"name": "patatas  bravas", "description": "potato, spicy sauce", "section": "starter", "price": 6},
        ]
    )
    assert len(items) == 1
    assert items[0].name == "patatas bravas"
    assert items[0].description == "potato, spicy sauce"
    assert items[0].price == 6.0


@pytest.mark.parametrize(
    "raw",
    [
        [],
        [{"name": "", "description": None, "section": "main", "price": None}],
        [{"name": "Arroz", "description": None, "section": "brunch", "price": None}],
        [{"name": "Arroz", "description": None, "section": "main", "price": -1}],
        [{"name": "Arroz", "description": "x" * 301, "section": "main", "price": None}],
        [{"name": f"Dish {i}", "description": None, "section": "main", "price": None} for i in range(MENU_ITEMS_PER_SAVE + 1)],
    ],
)
def test_items_reject_what_the_table_would(raw):
    with pytest.raises(ValidationError):
        parse_menu_items(raw)


def test_price_rejects_booleans_and_rounds():
    with pytest.raises(ValidationError):
        parse_menu_price(True)
    assert parse_menu_price(12.345) == 12.35


def test_sections_follow_the_page_order():
    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    items = [
        MenuItemRead(1, "La Tasca", "Flan", None, MenuSection.DESSERT, None, now),
        MenuItemRead(2, "La Tasca", "Bravas", None, MenuSection.STARTER, None, now),
        MenuItemRead(3, "La Tasca", "Arroz", None, MenuSection.MAIN, None, now),
    ]
    assert [section for section, _ in menu_sections(items)] == [MenuSection.STARTER, MenuSection.MAIN, MenuSection.DESSERT]
