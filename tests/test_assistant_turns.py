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
