"""Provisional foods, repetitions and +1 buttons as the conversation stores them
(code_conventions.md §8.12): pure logic of domain/, no database."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from DayBetes_food.domain.assistant import (
    TOOL_RESULT_ADDED,
    TOOL_RESULT_PROVISIONAL,
    TOOL_RESULT_REPEAT,
    parse_plus_step,
    plus_one_units,
    turn_views,
)
from DayBetes_food.domain.constants import AssistantRole
from DayBetes_food.errors import ValidationError


def _message(message_id, role, content):
    return SimpleNamespace(
        id=message_id, role=role, content=content, created_at=datetime(2026, 11, 21, tzinfo=timezone.utc)
    )


def _conversation(*results):
    """One message of the user whose tool calls returned `results`, in order."""
    calls = [{"type": "tool_use", "id": f"t{i}", "name": "tool", "input": {}} for i in range(len(results))]
    answers = [
        {"type": "tool_result", "tool_use_id": f"t{i}", "content": json.dumps(result)}
        for i, result in enumerate(results)
    ]
    return [
        _message(1, AssistantRole.USER, [{"type": "text", "text": "two croquetas and bravas"}]),
        _message(2, AssistantRole.ASSISTANT, calls),
        _message(3, AssistantRole.USER, answers),
    ]


def test_a_provisional_food_gets_its_own_card_and_not_an_added_line():
    turn = turn_views(
        _conversation(
            {
                TOOL_RESULT_ADDED: {"name": "Croqueta", "grams": 60, "carbs_g": 13.2, "food_id": 7, "servings": 2},
                TOOL_RESULT_PROVISIONAL: {
                    "entry_type": "catalog",
                    "id": 31,
                    "carbs_100g": 22,
                    "macros_source": "open_food_facts",
                },
            }
        )
    )[0]
    assert turn.added == []
    [card] = turn.provisional
    assert (card.entry_type, card.entry_id, card.name, card.grams) == ("catalog", 31, "Croqueta", 60)


def test_a_repeated_quick_add_is_offered_to_be_saved_and_still_listed_as_added():
    turn = turn_views(
        _conversation(
            {
                TOOL_RESULT_ADDED: {"name": "Menu of the day", "grams": 400, "kind": "estimate", "food_id": 9},
                TOOL_RESULT_REPEAT: {"quick_add_id": 44, "count": 3, "save_as": "dish"},
            }
        )
    )[0]
    assert [card.name for card in turn.added] == ["Menu of the day"]
    [repeat] = turn.repeats
    assert (repeat.quick_add_id, repeat.count, repeat.save_as) == (44, 3, "dish")


def test_the_unit_of_a_plus_one_is_one_serving_or_the_grams_of_that_add():
    turns = turn_views(
        _conversation(
            {TOOL_RESULT_ADDED: {"name": "Croqueta", "grams": 60, "food_id": 7, "servings": 2}},
            {TOOL_RESULT_ADDED: {"name": "Bread", "grams": 40, "food_id": 8}},
        )
    )
    units = {unit.portion_id: unit.unit_g for unit in plus_one_units(turns)}
    assert units == {7: 30, 8: 40}


def test_counted_pieces_make_the_unit_one_piece_even_in_servings():
    turns = turn_views(
        _conversation(
            # The serving of this food is two croquetas: 2 pieces are 1 serving.
            {TOOL_RESULT_ADDED: {"name": "Croqueta", "grams": 60, "food_id": 7, "servings": 1, "pieces": 2}},
            {TOOL_RESULT_ADDED: {"name": "Galleta", "grams": 24, "food_id": 8, "pieces": 3}},
        )
    )
    assert {unit.portion_id: unit.unit_g for unit in plus_one_units(turns)} == {7: 30, 8: 8}


def test_the_last_added_row_comes_first_and_keeps_its_latest_unit():
    turns = turn_views(
        _conversation(
            {TOOL_RESULT_ADDED: {"name": "Croqueta", "grams": 30, "food_id": 7}},
            {TOOL_RESULT_ADDED: {"name": "Bread", "grams": 40, "food_id": 8}},
            {TOOL_RESULT_ADDED: {"name": "Croqueta", "grams": 35, "food_id": 7}},
        )
    )
    assert [(unit.portion_id, unit.unit_g) for unit in plus_one_units(turns)] == [(7, 35), (8, 40)]


def test_a_recipe_or_an_old_result_has_no_plus_one():
    turns = turn_views(
        _conversation(
            {TOOL_RESULT_ADDED: {"name": "Lentils", "servings": 1, "kind": "recipe"}},
            {TOOL_RESULT_ADDED: {"name": "Rice", "grams": 80}},
        )
    )
    assert plus_one_units(turns) == []


@pytest.mark.parametrize("raw, step", [("1", 1.0), ("0.5", 0.5), ("2", 2.0), ("-1", -1.0)])
def test_the_plus_steps_are_the_menu_ones(raw, step):
    assert parse_plus_step(raw) == step


@pytest.mark.parametrize("raw", ["3", "-2", "", "abc", "nan"])
def test_any_other_plus_step_is_rejected(raw):
    with pytest.raises(ValidationError):
        parse_plus_step(raw)
