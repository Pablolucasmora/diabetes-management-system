"""History sent back to the model (code_conventions.md §8.12, cost)."""

from types import SimpleNamespace

from DayBetes_food.domain.assistant import (
    ASSISTANT_HISTORY_CUT_STEP,
    ASSISTANT_HISTORY_MAX_TURNS,
    history_window,
    starts_turn,
)
from DayBetes_food.domain.constants import AssistantRole


def _turn(index):
    """One message of the user with a tool call, its result and the answer."""
    return [
        SimpleNamespace(role=AssistantRole.USER, content=[{"type": "text", "text": f"message {index}"}]),
        SimpleNamespace(role=AssistantRole.ASSISTANT, content=[{"type": "tool_use", "id": f"t{index}"}]),
        SimpleNamespace(role=AssistantRole.USER, content=[{"type": "tool_result", "tool_use_id": f"t{index}"}]),
        SimpleNamespace(role=AssistantRole.ASSISTANT, content=[{"type": "text", "text": "ok"}]),
    ]


def _conversation(turns):
    return [message for index in range(turns) for message in _turn(index)]


def _turns(messages):
    return sum(1 for message in messages if starts_turn(message))


def test_a_short_conversation_is_sent_whole():
    messages = _conversation(ASSISTANT_HISTORY_MAX_TURNS)
    assert history_window(messages) == messages


def test_a_long_conversation_is_cut_at_the_start_of_a_turn():
    messages = _conversation(ASSISTANT_HISTORY_MAX_TURNS + 1)
    window = history_window(messages)
    assert starts_turn(window[0])
    assert _turns(window) <= ASSISTANT_HISTORY_MAX_TURNS
    # Every tool call keeps its result.
    calls = {block["id"] for message in window for block in message.content if block.get("type") == "tool_use"}
    results = {block["tool_use_id"] for message in window for block in message.content if block.get("type") == "tool_result"}
    assert calls == results


def test_the_cut_moves_in_steps_so_the_cached_prefix_stays():
    first = history_window(_conversation(ASSISTANT_HISTORY_MAX_TURNS + 1))
    later = history_window(_conversation(ASSISTANT_HISTORY_MAX_TURNS + ASSISTANT_HISTORY_CUT_STEP - 1))
    assert first[0].content == later[0].content
