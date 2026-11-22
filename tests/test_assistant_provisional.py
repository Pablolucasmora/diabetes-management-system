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


def test_offered_preparation_values_keep_known_values_once_and_at_most_three():
    from DayBetes_food.domain.assistant import parse_preparation_options

    assert parse_preparation_options("cooking", ["fried", "oven", "fried", "boiled", "griddle", "steam"]) == (
        "fried",
        "oven",
        "griddle",
    )
    assert parse_preparation_options("conservation", ["fridge", "fried"]) == ("fridge",)
    assert parse_preparation_options("ripeness", ["ripe"]) == ()
    assert parse_preparation_options("cooking", None) == ()


def test_the_latest_preparation_values_offered_win_for_each_row_and_field():
    from DayBetes_food.domain.assistant import preparation_choices

    def added(food_id, offered):
        return {TOOL_RESULT_ADDED: {"name": "Rice", "grams": 150, "food_id": food_id, "preparation_options": offered}}

    turns = turn_views(
        _conversation(
            added(7, {"cooking": ["boiled-soft"], "conservation": ["fridge", "freshly-made"]}),
            added(7, {"cooking": ["fried", "oven"]}),
            {TOOL_RESULT_ADDED: {"name": "Bread", "grams": 40, "food_id": 8}},
        )
    )
    assert preparation_choices(turns) == {7: {"cooking": ("fried", "oven"), "conservation": ("fridge", "freshly-made")}}


def test_quick_replies_are_shown_from_their_tool_result():
    from DayBetes_food.domain.assistant import TOOL_RESULT_REPLIES

    [turn] = turn_views(_conversation({TOOL_RESULT_REPLIES: ["Homemade", "Restaurant"]}))
    assert turn.quick_replies == ["Homemade", "Restaurant"]


@pytest.mark.parametrize("raw", [["Only one"], ["a", "b", "c", "d", "e"], ["ok", ""], "Homemade", ["x" * 41, "y"]])
def test_quick_replies_outside_the_rules_are_rejected(raw):
    from DayBetes_food.domain.assistant import parse_quick_replies

    with pytest.raises(ValidationError):
        parse_quick_replies(raw)


def test_a_chat_preview_is_the_user_text_without_the_context_or_photos():
    from DayBetes_food.domain.assistant import ASSISTANT_CONTEXT_TAG, ASSISTANT_PHOTO_PLACEHOLDER, chat_preview

    content = [
        {"type": "text", "text": ASSISTANT_CONTEXT_TAG + "\nLocal time"},
        {"type": "text", "text": ASSISTANT_PHOTO_PLACEHOLDER},
        {"type": "text", "text": "  lentejas   de mi abuela "},
    ]
    assert chat_preview(content) == "lentejas de mi abuela"
    assert chat_preview([{"type": "text", "text": ASSISTANT_PHOTO_PLACEHOLDER}]) == "Photo"
    assert chat_preview(None) == "Empty chat"
    assert chat_preview([{"type": "text", "text": "a" * 100}]).endswith("…")


def _two_turns(first_result, second_result):
    """Two messages of the user, each with one tool call and its result."""
    rows = []
    for index, result in enumerate((first_result, second_result)):
        base = index * 4
        rows += [
            _message(base + 1, AssistantRole.USER, [{"type": "text", "text": f"message {index}"}]),
            _message(base + 2, AssistantRole.ASSISTANT, [{"type": "tool_use", "id": f"t{index}", "name": "tool", "input": {}}]),
            _message(base + 3, AssistantRole.USER, [{"type": "tool_result", "tool_use_id": f"t{index}", "content": json.dumps(result)}]),
            _message(base + 4, AssistantRole.ASSISTANT, [{"type": "text", "text": f"answer {index}"}]),
        ]
    return rows


def test_a_question_about_the_guide_is_folded_and_never_sent_back():
    from DayBetes_food.domain.assistant import TOOL_RESULT_GUIDE, without_guide_questions

    messages = _two_turns(
        {TOOL_RESULT_GUIDE: "amount_method", "text": "..."},
        {TOOL_RESULT_ADDED: {"name": "Bread", "grams": 40, "food_id": 8}},
    )
    question, meal = turn_views(messages)
    assert question.is_guide_question and not meal.is_guide_question
    assert [m.id for m in without_guide_questions(messages)] == [5, 6, 7, 8]


def test_a_turn_that_read_the_guide_and_added_food_is_kept():
    from DayBetes_food.domain.assistant import TOOL_RESULT_GUIDE, without_guide_questions

    messages = _two_turns(
        {TOOL_RESULT_GUIDE: "cooking", TOOL_RESULT_ADDED: {"name": "Rice", "grams": 150, "food_id": 7}},
        {TOOL_RESULT_ADDED: {"name": "Bread", "grams": 40, "food_id": 8}},
    )
    assert len(without_guide_questions(messages)) == len(messages)


def _portion(origin_id, amount, *, carbs_100g=50.0, amount_method=None, macros_source=None, cooking=None):
    from DayBetes_food.domain.constants import PortionOrigin

    source = SimpleNamespace(
        name=f"Food {origin_id}", carbs_100g=carbs_100g, macros_source=macros_source, cooking_factor=None
    )
    return SimpleNamespace(
        origin=PortionOrigin.CATALOG,
        origin_id=origin_id,
        amount=amount,
        amount_method=amount_method,
        is_cooked_weight=False,
        source=source,
        cooking=cooking,
        final_state=None,
        conservation=None,
    )


def test_the_carbs_range_widens_with_how_each_food_was_obtained():
    from DayBetes_food.domain.constants import AmountMethod, MacrosSource
    from DayBetes_food.domain.portion_detail import carbs_range

    weighed = _portion(1, 100, amount_method=AmountMethod.KITCHEN_SCALE, macros_source=MacrosSource.LABEL)
    guessed = _portion(2, 100, amount_method=AmountMethod.EYEBALL, macros_source=MacrosSource.AI_ESTIMATE)
    low, high = carbs_range([weighed])
    assert (round(low, 1), round(high, 1)) == (45.0, 55.0)  # 50 g ± 10 %
    low, high = carbs_range([weighed, guessed])
    assert (round(low, 1), round(high, 1)) == (65.0, 135.0)  # + 50 g ± 60 %


def test_a_usual_meal_is_the_same_foods_three_times_around_this_time():
    from DayBetes_food.domain.assistant import usual_meals

    def meal(minute, amounts):
        return minute, [_portion(food_id, grams) for food_id, grams in amounts]

    meals = [
        meal(8 * 60, [(1, 200), (2, 40)]),
        meal(8 * 60 + 30, [(1, 250), (2, 40)]),
        meal(7 * 60 + 45, [(1, 220), (2, 50)]),
        meal(14 * 60, [(1, 200), (2, 40)]),  # lunch: too far from now
        meal(8 * 60, [(1, 200)]),  # not the same foods
    ]
    [found] = usual_meals(meals, now_minute=8 * 60 + 10)
    assert found.times == 3
    assert [(food.entry_id, food.grams) for food in found.foods] == [(1, 220), (2, 40)]
    assert usual_meals(meals[:2], now_minute=8 * 60) == []


def test_without_unanswered_calls_drops_a_cut_call_and_keeps_the_rest():
    from DayBetes_food.domain.assistant import AssistantMessageRead, without_unanswered_calls

    def row(position, role, content):
        return AssistantMessageRead(position, 23, position, role, content, datetime(2026, 11, 21, tzinfo=timezone.utc))

    call = {"type": "tool_use", "id": "a", "name": "search_my_foods", "input": {}}
    cut = {"type": "tool_use", "id": "b", "name": "add_new_food", "input": {}}
    messages = [
        row(1, AssistantRole.USER, [{"type": "text", "text": "rice"}]),
        row(2, AssistantRole.ASSISTANT, [call]),
        row(3, AssistantRole.USER, [{"type": "tool_result", "tool_use_id": "a", "content": "{}"}]),
        row(4, AssistantRole.USER, [{"type": "text", "text": "and a cake"}]),
        row(5, AssistantRole.ASSISTANT, [{"type": "thinking", "thinking": "", "signature": "s"}, cut]),
        row(6, AssistantRole.USER, [{"type": "tool_result", "tool_use_id": "zzz", "content": "{}"}]),
    ]
    kept = without_unanswered_calls(messages)
    assert [m.position for m in kept] == [1, 2, 3, 4]


def test_with_usual_first_moves_or_adds_the_usual_value():
    from DayBetes_food.domain.assistant import with_usual_first

    assert with_usual_first(("boiled", "griddle"), None) == ("boiled", "griddle")
    assert with_usual_first(("boiled", "griddle"), "griddle") == ("griddle", "boiled")
    assert with_usual_first(("boiled", "griddle", "fried"), "baked") == ("baked", "boiled", "griddle")


@pytest.mark.parametrize(
    "text, quick",
    [
        ("arroz 150, pollo 120, pan 40", True),
        ("150 g de arroz\n2 huevos", True),
        ("pechuga 120g y ensalada 80 gr", True),
        ("croquetas 3", True),
        ("paella en casa de mi madre sobre las 9", False),
        ("¿arroz 150?", False),
        ("lo de siempre", False),
        ("he comido arroz", False),
    ],
)
def test_is_quick_list(text, quick):
    from DayBetes_food.domain.assistant import is_quick_list

    assert is_quick_list(text) is quick
    assert is_quick_list(text, has_photo=True) is False


def test_effort_marker_round_trip():
    from DayBetes_food.domain.assistant import AssistantMessageRead, api_message, current_effort, effort_marker

    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    rows = [
        AssistantMessageRead(1, 1, 1, AssistantRole.USER, [{"type": "text", "text": "arroz 150"}], now),
        AssistantMessageRead(2, 1, 2, AssistantRole.SYSTEM, effort_marker("low"), now),
    ]
    assert current_effort(rows[:1], "high") == "high"
    assert current_effort(rows, "high") == "low"
    assert api_message(AssistantRole.SYSTEM, effort_marker("low")) == {
        "role": "system",
        "content": [],
        "output_config": {"effort": "low"},
    }
    assert turn_views(rows)[0].user_text == "arroz 150"


def _estimate_result(portion_id, grams, carbs, kind=None):
    added = {"name": "x", "grams": grams, "carbs_g": carbs, "amount_method": "ai_estimate", "food_id": portion_id}
    if kind:
        added["kind"] = kind
    return {"type": "tool_result", "tool_use_id": f"t{portion_id}", "content": json.dumps({TOOL_RESULT_ADDED: added})}


def test_calibration_needs_enough_samples_and_a_real_shift():
    from DayBetes_food.domain.assistant import (
        ASSISTANT_PHOTO_PLACEHOLDER,
        CalibrationPortion,
        calibration_lines,
        estimate_samples,
    )

    text = [{"type": "text", "text": "una paella"}]
    photo = [{"type": "text", "text": ASSISTANT_PHOTO_PLACEHOLDER}]
    rows = []
    for i in range(1, 6):  # five meals out, each estimated 200 g and served 160 g
        rows.append((i, text, True))
        rows.append((i, [_estimate_result(i, 200, 40, kind="estimate")], True))
    rows.append((9, photo, False))
    rows.append((9, [_estimate_result(9, 100, 20)], False))
    samples = estimate_samples(rows)
    assert [s.group.value for s in samples] == ["out"] * 5 + ["photo"]
    portions = {i: CalibrationPortion(i, 160.0, 24.0) for i in range(1, 6)}  # carbs 0.20 -> 0.24 per g
    portions[9] = CalibrationPortion(9, 50.0, None)
    lines = calibration_lines(samples, portions)
    assert len(lines) == 2
    assert "eating out" in lines[0] and "x0.80" in lines[0] and "−20 %" in lines[0]
    assert "quick add" in lines[1] and "x1.20" in lines[1]
    # Four samples are not enough, and a 5 % shift changes nothing.
    assert calibration_lines(samples[:4], portions) == []
    assert calibration_lines(samples[:5], {i: CalibrationPortion(i, 210.0, 20.0) for i in range(1, 6)}) == []


def test_strict_tools_stay_within_the_api_union_limit():
    """The API rejects every request when the strict tools have more than 16
    nullable or union parameters in all (§8.12): the assistant stops working."""
    from DayBetes_food.services.assistant_tools import TOOL_DEFINITIONS

    def unions(schema):
        if isinstance(schema, dict):
            own = 1 if isinstance(schema.get("type"), list) or "anyOf" in schema else 0
            return own + sum(unions(value) for value in schema.values())
        if isinstance(schema, list):
            return sum(unions(value) for value in schema)
        return 0

    assert sum(unions(tool["input_schema"]) for tool in TOOL_DEFINITIONS if tool["strict"]) <= 16
