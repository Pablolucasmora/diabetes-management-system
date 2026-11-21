"""Messages to the assistant answered in the background (code_conventions.md §8.12,
"Turno en segundo plano", decision 2026-11-21).

The route stores a queued `assistant_turn` and returns at once; a thread of this
process asks the model and stores the answer (`send_assistant_message`, unchanged)
while the page polls the turn. Leaving the page does not cut it: the request that
sent it has already finished.

The photos travel to the thread in memory, never through the database before the
answer stores them: a turn that a restart cuts is failed at startup and the user
sends it again (`fail_interrupted_turns`).
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries import (
    create_assistant_turn,
    fail_assistant_turn,
    fail_interrupted_assistant_turns,
    finish_assistant_turn,
    start_assistant_turn,
)
from DayBetes_food.domain.assistant import AssistantTurnRequest
from DayBetes_food.errors import ConflictError, ExternalServiceError, NotFoundError
from DayBetes_food.services.assistant import send_assistant_message

logger = logging.getLogger(__name__)

# One user today (§8.12, "Límite de uso"), and one pending turn per user: two
# threads leave room for a second user without queueing behind the first.
ASSISTANT_TURN_WORKERS = 2

TURN_MEAL_GONE = "That meal was confirmed or deleted. Choose another meal."
TURN_UNAVAILABLE = "The assistant is not available right now. Try again in a moment."
TURN_INTERRUPTED = "The server restarted before the assistant answered. Send it again."
TURN_FAILED = "Something went wrong while the assistant answered. Send it again."

_executor = ThreadPoolExecutor(max_workers=ASSISTANT_TURN_WORKERS, thread_name_prefix="assistant-turn")


def submit_assistant_turn(
    connection,
    user_id: int,
    *,
    conversation_id: int | None,
    event_id: int | None,
    without_meal: bool,
    request: AssistantTurnRequest,
) -> int:
    """Queue one message and start answering it in a thread. Commits the turn
    before the thread starts, so the thread and the page can read it.

    Raises:
        ConflictError: the user already has a message being answered.
        NotFoundError: the conversation is not the user's.
    """
    turn_id = create_assistant_turn(
        connection, user_id, conversation_id, request.text or "", len(request.photos), commit=True
    )
    _executor.submit(_run_turn, turn_id, user_id, conversation_id, event_id, without_meal, request)
    return turn_id


def _run_turn(
    turn_id: int,
    user_id: int,
    conversation_id: int | None,
    event_id: int | None,
    without_meal: bool,
    request: AssistantTurnRequest,
) -> None:
    """The thread: the same answer as before, its outcome written on the turn.
    Nothing raises out of here: an executor would keep the exception unseen."""
    try:
        with get_connection() as connection:
            if not start_assistant_turn(connection, turn_id):
                return
            try:
                result = send_assistant_message(
                    connection,
                    user_id,
                    conversation_id=conversation_id,
                    event_id=event_id,
                    request=request,
                    without_meal=without_meal,
                )
            except (NotFoundError, ConflictError):
                connection.rollback()
                fail_assistant_turn(connection, turn_id, TURN_MEAL_GONE)
                return
            except ExternalServiceError as error:
                # Logged once here, with the adapter's internal reason (§8.3, §8.6).
                connection.rollback()
                logger.warning(
                    "Assistant call failed",
                    exc_info=error,
                    extra={"error_code": error.code, "reason": str(error), "assistant_turn_id": turn_id},
                )
                fail_assistant_turn(connection, turn_id, TURN_UNAVAILABLE)
                return
            finish_assistant_turn(
                connection,
                turn_id,
                conversation_id=result.conversation_id,
                intake_event_id=result.event_id,
                meal_created=result.meal_created,
                notices=list(result.notices),
            )
    except Exception:
        logger.exception("Assistant turn failed", extra={"assistant_turn_id": turn_id})
        try:
            with get_connection() as connection:
                fail_assistant_turn(connection, turn_id, TURN_FAILED)
        except Exception:
            logger.exception("Could not mark the assistant turn as failed", extra={"assistant_turn_id": turn_id})


def fail_interrupted_turns() -> None:
    """At startup, before serving: the turns a restart cut are failed, never run
    again, because a round may already have written to the cart (§8.12)."""
    with get_connection() as connection:
        count = fail_interrupted_assistant_turns(connection, TURN_INTERRUPTED)
    if count:
        logger.warning("Assistant turns cut by a restart", extra={"count": count})


def shutdown_assistant_turns() -> None:
    """At shutdown: running turns are not waited for (they fail at the next start)."""
    _executor.shutdown(wait=False, cancel_futures=True)
