"""Messages answered in the background (code_conventions.md §8.12)."""

from datetime import datetime, timezone

from fasthtml.common import to_xml

from DayBetes_food.components.assistant.assistant_page import FailedTurnBlock, PendingTurnBlock
from DayBetes_food.domain.assistant import AssistantTurnRead
from DayBetes_food.domain.constants import AssistantTurnStatus


def _turn(status, **fields):
    values = dict(
        id=9,
        user_id=1,
        status=status,
        conversation_id=None,
        intake_event_id=None,
        meal_created=False,
        user_text="two eggs",
        photo_count=1,
        notices=(),
        error_message=None,
        created_at=datetime.now(timezone.utc),
        finished_at=None,
        seen_at=None,
    )
    values.update(fields)
    return AssistantTurnRead(**values)


def test_only_queued_and_running_are_pending():
    assert _turn(AssistantTurnStatus.QUEUED).pending
    assert _turn(AssistantTurnStatus.RUNNING).pending
    assert not _turn(AssistantTurnStatus.DONE).pending
    assert not _turn(AssistantTurnStatus.FAILED).pending


def test_a_pending_turn_asks_for_its_answer_every_two_seconds():
    html = to_xml(PendingTurnBlock(_turn(AssistantTurnStatus.RUNNING)))
    assert 'hx-get="/assistant/turn/9"' in html
    assert 'hx-trigger="every 2s"' in html
    assert 'hx-swap="outerHTML"' in html
    assert "two eggs" in html and "Photo" in html


def test_a_failed_turn_gives_its_text_back_and_says_why():
    html = to_xml(FailedTurnBlock(_turn(AssistantTurnStatus.FAILED, error_message="Send it again.")))
    assert 'data-assistant-failed-text="two eggs"' in html
    assert "Send it again." in html
    assert "hx-get" not in html


def test_a_preload_lists_a_failed_turn_instead_of_marking_it_seen(monkeypatch):
    """code_conventions.md §9.2: a preload writes nothing; the page marks it once shown."""
    from DayBetes_food.routes import assistant_routes

    marked = []
    monkeypatch.setattr(assistant_routes, "mark_assistant_turn_seen", lambda c, u, t: marked.append(t))
    monkeypatch.setattr(assistant_routes, "get_pending_assistant_turn", lambda c, u: None)
    failed = _turn(AssistantTurnStatus.FAILED, conversation_id=4, error_message="x")

    deferred = []
    tail = assistant_routes._turn_tail(None, 1, 4, failed, deferred)
    assert len(tail) == 1 and deferred == [9] and marked == []

    tail = assistant_routes._turn_tail(None, 1, 4, failed)
    assert len(tail) == 1 and marked == [9]


def test_a_preloaded_page_carries_the_turns_to_mark_seen():
    from fasthtml.common import Div

    from DayBetes_food.components.assistant.assistant_page import AssistantPage

    html = to_xml(AssistantPage(None, [], None, [], Div(), mark_seen=(9, 12)))
    assert 'data-mark-seen="9,12"' in html
    assert "data-mark-seen" not in to_xml(AssistantPage(None, [], None, [], Div()))
