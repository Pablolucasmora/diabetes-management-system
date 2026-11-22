"""Queries for `assistant_conversation`, `assistant_message` and `assistant_photo`
(code_conventions.md §8.12, §11.2.9, §11.2.10).

Both are private: the owner travels in the SQL of every statement (§5.3), so
another user's conversation and one that does not exist give the same result
(§5.4). A conversation is linked only to a planned meal of its owner, checked
in the same statement that writes it. Messages are insert-only: a
conversation is replayed to the model from them, in order. Photos are
insert-only too, and their owner is the one of their message's conversation.
"""

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from DayBetes_food.database.mappers import (
    assistant_conversation_read_from_row,
    assistant_message_read_from_row,
    assistant_turn_read_from_row,
)
from DayBetes_food.database.queries.crud import _execute_query, _execute_query_many
from DayBetes_food.domain.assistant import (
    AssistantConversationRead,
    AssistantPhoto,
    AssistantMessageCreate,
    AssistantMessageRead,
    AssistantTurnRead,
    ChatSummary,
    PastChat,
    chat_preview,
)
from DayBetes_food.domain.constants import (
    ASSISTANT_TURN_PENDING,
    AssistantRole,
    AssistantTurnStatus,
    IntakeEventState,
)
from DayBetes_food.errors import ConflictError, NotFoundError

_CONVERSATION_COLUMNS = "c.id, c.users_id, c.intake_event_id, c.model, c.without_meal, c.created_at"
# A meal the conversation may write to: planned and of the same user.
_OWN_PLANNED_EVENT = """
    EXISTS (
        SELECT 1 FROM intake_event ie
        WHERE ie.id = %(event_id)s
          AND ie.users_id = %(user_id)s
          AND ie.state = %(planned)s
    )
"""


def create_assistant_conversation(
    connection, user_id: int, model: str, event_id: int | None, *, without_meal: bool = False, commit: bool = True
) -> int:
    """A new conversation, linked to `event_id` when given, or one that never has a
    meal (`without_meal`, §8.12).

    Raises:
        NotFoundError: the meal is not a planned meal of the user.
    """
    row = _execute_query(
        connection,
        f"""
        INSERT INTO assistant_conversation (users_id, intake_event_id, model, without_meal)
        SELECT %(user_id)s, %(event_id)s, %(model)s, %(without_meal)s
        WHERE %(event_id)s::int IS NULL OR {_OWN_PLANNED_EVENT}
        RETURNING id;
        """,
        {
            "user_id": user_id,
            "event_id": event_id,
            "model": model,
            "without_meal": without_meal,
            "planned": IntakeEventState.PLANNED.value,
        },
        commit=commit,
    )
    if row is None:
        raise NotFoundError("Meal not found.")
    return int(row["id"])


def get_assistant_conversation(connection, user_id: int, conversation_id: int) -> AssistantConversationRead | None:
    row = _execute_query(
        connection,
        f"""
        SELECT {_CONVERSATION_COLUMNS}
        FROM assistant_conversation c
        WHERE c.id = %(conversation_id)s AND c.users_id = %(user_id)s;
        """,
        {"conversation_id": conversation_id, "user_id": user_id},
        commit=False,
    )
    return assistant_conversation_read_from_row(row) if row else None


def get_latest_assistant_conversation(connection, user_id: int, event_id: int) -> AssistantConversationRead | None:
    """The conversation of a meal (§8.12: one per meal): the latest, if a meal
    ever had more than one."""
    row = _execute_query(
        connection,
        f"""
        SELECT {_CONVERSATION_COLUMNS}
        FROM assistant_conversation c
        WHERE c.users_id = %(user_id)s AND c.intake_event_id = %(event_id)s
        ORDER BY c.id DESC
        LIMIT 1;
        """,
        {"user_id": user_id, "event_id": event_id},
        commit=False,
    )
    return assistant_conversation_read_from_row(row) if row else None


def get_latest_meal_free_conversation(connection, user_id: int) -> AssistantConversationRead | None:
    """The user's latest `No meal` conversation not deleted from the list (§8.12,
    frontend §9.11): it reopens until they start a new chat."""
    row = _execute_query(
        connection,
        f"""
        SELECT {_CONVERSATION_COLUMNS}
        FROM assistant_conversation c
        WHERE c.users_id = %(user_id)s AND c.without_meal AND c.hidden_at IS NULL
        ORDER BY c.id DESC
        LIMIT 1;
        """,
        {"user_id": user_id},
        commit=False,
    )
    return assistant_conversation_read_from_row(row) if row else None


def list_meal_free_conversations(connection, user_id: int, limit: int) -> list[ChatSummary]:
    """The user's latest `No meal` chats, the last written first, each with what
    the user wrote first (frontend §9.11, list of chats)."""
    rows = _execute_query_many(
        connection,
        """
        SELECT c.id, c.updated_at, first_message.content
        FROM assistant_conversation c
        LEFT JOIN LATERAL (
            SELECT m.content
            FROM assistant_message m
            WHERE m.conversation_id = c.id AND m.role = %(user_role)s
            ORDER BY m.position
            LIMIT 1
        ) first_message ON TRUE
        WHERE c.users_id = %(user_id)s AND c.without_meal AND c.hidden_at IS NULL
        ORDER BY c.updated_at DESC, c.id DESC
        LIMIT %(limit)s;
        """,
        {"user_id": user_id, "user_role": AssistantRole.USER.value, "limit": limit},
        commit=False,
    )
    return [ChatSummary(int(row["id"]), row["updated_at"], chat_preview(row["content"])) for row in rows]


def list_past_conversations(connection, user_id: int, limit: int) -> list[PastChat]:
    """The past chats (frontend §9.11): the conversation of each confirmed meal (its
    latest, as §8.12 reopens it) and every `No meal` chat, hidden ones included,
    the latest first: a meal by its time, a chat without one by its last message."""
    rows = _execute_query_many(
        connection,
        """
        SELECT c.id, c.intake_event_id, c.updated_at, c.hidden_at, first_message.content
        FROM assistant_conversation c
        LEFT JOIN intake_event ie ON ie.id = c.intake_event_id AND ie.users_id = c.users_id
        LEFT JOIN LATERAL (
            SELECT m.content
            FROM assistant_message m
            WHERE m.conversation_id = c.id AND m.role = %(user_role)s
            ORDER BY m.position
            LIMIT 1
        ) first_message ON TRUE
        WHERE c.users_id = %(user_id)s
          AND (
              c.without_meal
              OR (
                  ie.state <> %(planned)s
                  AND ie.deleted_at IS NULL
                  AND c.id = (
                      SELECT MAX(other.id) FROM assistant_conversation other
                      WHERE other.users_id = c.users_id AND other.intake_event_id = c.intake_event_id
                  )
              )
          )
        ORDER BY COALESCE(ie.meal_time, c.updated_at) DESC, c.id DESC
        LIMIT %(limit)s;
        """,
        {
            "user_id": user_id,
            "planned": IntakeEventState.PLANNED.value,
            "user_role": AssistantRole.USER.value,
            "limit": limit,
        },
        commit=False,
    )
    return [
        PastChat(
            conversation_id=int(row["id"]),
            event_id=int(row["intake_event_id"]) if row["intake_event_id"] is not None else None,
            updated_at=row["updated_at"],
            preview=chat_preview(row["content"]),
            hidden=row["hidden_at"] is not None,
        )
        for row in rows
    ]


def hide_assistant_conversation(connection, user_id: int, conversation_id: int, *, commit: bool = True) -> None:
    """Hide a chat from the list of chats (frontend §9.11): it is kept for the study
    and still shows in the past chats. Repeating it keeps the first time (§6.3).

    Raises:
        NotFoundError: the conversation is not the user's.
    """
    row = _execute_query(
        connection,
        """
        UPDATE assistant_conversation c
        SET hidden_at = COALESCE(c.hidden_at, CURRENT_TIMESTAMP)
        WHERE c.id = %(conversation_id)s AND c.users_id = %(user_id)s
        RETURNING c.id;
        """,
        {"conversation_id": conversation_id, "user_id": user_id},
        commit=commit,
    )
    if row is None:
        raise NotFoundError("Chat not found.")


def link_assistant_conversation_event(
    connection, user_id: int, conversation_id: int, event_id: int, *, commit: bool = True
) -> None:
    """Link a conversation to the meal its first add created. Repeating it with the
    same meal leaves the same row (§6.3).

    Raises:
        NotFoundError: the conversation or the planned meal is not the user's.
    """
    row = _execute_query(
        connection,
        f"""
        UPDATE assistant_conversation c
        SET intake_event_id = %(event_id)s, updated_at = CURRENT_TIMESTAMP
        WHERE c.id = %(conversation_id)s
          AND c.users_id = %(user_id)s
          AND {_OWN_PLANNED_EVENT}
        RETURNING c.id;
        """,
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "event_id": event_id,
            "planned": IntakeEventState.PLANNED.value,
        },
        commit=commit,
    )
    if row is None:
        raise NotFoundError("Conversation not found.")


def list_assistant_messages(connection, user_id: int, conversation_id: int) -> list[AssistantMessageRead]:
    """Every message of one of the user's conversations, in order."""
    rows = _execute_query_many(
        connection,
        """
        SELECT m.id, m.conversation_id, m.position, m.role, m.content, m.created_at
        FROM assistant_message m
        INNER JOIN assistant_conversation c ON c.id = m.conversation_id
        WHERE m.conversation_id = %(conversation_id)s AND c.users_id = %(user_id)s
        ORDER BY m.position;
        """,
        {"conversation_id": conversation_id, "user_id": user_id},
        commit=False,
    )
    return [assistant_message_read_from_row(row) for row in rows]


def get_assistant_message(connection, user_id: int, message_id: int) -> AssistantMessageRead | None:
    """One message of one of the user's conversations (the draft of a new food
    is read from it, frontend_conventions.md §9.11)."""
    row = _execute_query(
        connection,
        """
        SELECT m.id, m.conversation_id, m.position, m.role, m.content, m.created_at
        FROM assistant_message m
        INNER JOIN assistant_conversation c ON c.id = m.conversation_id
        WHERE m.id = %(message_id)s AND c.users_id = %(user_id)s;
        """,
        {"message_id": message_id, "user_id": user_id},
        commit=False,
    )
    return assistant_message_read_from_row(row) if row else None


def append_assistant_messages(
    connection, user_id: int, conversation_id: int, messages: list[AssistantMessageCreate]
) -> list[int]:
    """Append messages at the end of one of the user's conversations, in order.
    Several statements: it runs inside the caller's transaction (§2.3) and never
    commits.

    The conversation row is locked first (§6.8): two sends of the same
    conversation take consecutive positions instead of colliding on
    uq_assistant_message_conversation_id_position.

    Returns:
        The ids of the new rows, in the same order.

    Raises:
        NotFoundError: the conversation is not the user's.
    """
    locked = _execute_query(
        connection,
        """
        UPDATE assistant_conversation c
        SET updated_at = CURRENT_TIMESTAMP
        WHERE c.id = %(conversation_id)s AND c.users_id = %(user_id)s
        RETURNING (SELECT COALESCE(MAX(m.position), 0) FROM assistant_message m
                   WHERE m.conversation_id = c.id) AS last_position;
        """,
        {"conversation_id": conversation_id, "user_id": user_id},
        commit=False,
    )
    if locked is None:
        raise NotFoundError("Conversation not found.")
    position = int(locked["last_position"])
    ids: list[int] = []
    for message in messages:
        position += 1
        usage = message.usage
        row = _execute_query(
            connection,
            """
            INSERT INTO assistant_message (
                conversation_id, position, role, content,
                input_tokens, cache_creation_input_tokens, cache_read_input_tokens,
                output_tokens, duration_ms, stop_reason
            )
            VALUES (
                %(conversation_id)s, %(position)s, %(role)s, %(content)s,
                %(input_tokens)s, %(cache_creation_input_tokens)s, %(cache_read_input_tokens)s,
                %(output_tokens)s, %(duration_ms)s, %(stop_reason)s
            )
            RETURNING id;
            """,
            {
                "conversation_id": conversation_id,
                "position": position,
                "role": message.role.value,
                "content": Jsonb(message.content),
                "input_tokens": usage.input_tokens if usage else None,
                "cache_creation_input_tokens": usage.cache_creation_input_tokens if usage else None,
                "cache_read_input_tokens": usage.cache_read_input_tokens if usage else None,
                "output_tokens": usage.output_tokens if usage else None,
                "duration_ms": usage.duration_ms if usage else None,
                "stop_reason": usage.stop_reason if usage else None,
            },
            commit=False,
        )
        ids.append(int(row["id"]))
    return ids


def list_estimate_rows(connection, user_id: int, days: int) -> list[tuple[int, list[dict], bool]]:
    """The `user` rows of the conversations of the user's confirmed meals of the
    last `days` days that matter to learn from corrections (§8.12): the turn
    starts (whether a photo came) and the tool results with an estimated amount.
    In order, as (conversation_id, content, eating_out)."""
    rows = _execute_query_many(
        connection,
        """
        SELECT m.conversation_id, m.content, coalesce(ie.eating_out, FALSE) AS eating_out
        FROM assistant_message m
        JOIN assistant_conversation c ON c.id = m.conversation_id
        JOIN intake_event ie ON ie.id = c.intake_event_id
        WHERE c.users_id = %(user_id)s
          AND ie.users_id = %(user_id)s
          AND ie.state = %(state)s
          AND ie.deleted_at IS NULL
          AND ie.meal_time >= CURRENT_TIMESTAMP - (%(days)s * INTERVAL '1 day')
          AND m.role = %(role)s
          AND (
              NOT m.content @> '[{"type": "tool_result"}]'::jsonb
              OR m.content::text LIKE '%%ai_estimate%%'
          )
        ORDER BY m.conversation_id, m.position;
        """,
        {
            "user_id": user_id,
            "state": IntakeEventState.CONSUMED.value,
            "role": AssistantRole.USER.value,
            "days": max(1, int(days)),
        },
        commit=False,
    )
    return [(int(row["conversation_id"]), row["content"], bool(row["eating_out"])) for row in rows]


def get_calibration_portions(connection, user_id: int, portion_ids: list[int]) -> list[dict]:
    """How the rows of the user's confirmed meals ended: what was served and, for
    a quick add, its carbs per 100 g now."""
    if not portion_ids:
        return []
    return _execute_query_many(
        connection,
        """
        SELECT pd.id,
               pd.amount / coalesce(ip.eaten_fraction, 1) AS served_g,
               CASE WHEN mi.is_quick_add THEN mi.carbs_100g END AS carbs_100g
        FROM portion_detail pd
        JOIN intake_event ie ON ie.id = pd.intake_event_id
        LEFT JOIN intake_plate ip ON ip.id = pd.plate_id
        LEFT JOIN manual_intake mi ON mi.id = pd.manual_intake_id
        WHERE pd.id = ANY(%(ids)s) AND ie.users_id = %(user_id)s AND ie.state = %(state)s;
        """,
        {"ids": portion_ids, "user_id": user_id, "state": IntakeEventState.CONSUMED.value},
        commit=False,
    )


def insert_assistant_photos(
    connection, user_id: int, message_id: int, photos: tuple[AssistantPhoto, ...]
) -> None:
    """Store the photos of one `user` message of the user's, in order (§11.2.10).
    Runs inside the caller's transaction (§2.3) and never commits.

    The owner is checked in the same statement that writes: the message must be
    a `user` row of one of the user's conversations.

    Raises:
        NotFoundError: the message is not a `user` message of the user's.
    """
    for order, photo in enumerate(photos, start=1):
        row = _execute_query(
            connection,
            """
            INSERT INTO assistant_photo (assistant_message_id, photo_order, image, size_bytes)
            SELECT m.id, %(photo_order)s, %(image)s, %(size_bytes)s
            FROM assistant_message m
            JOIN assistant_conversation c ON c.id = m.conversation_id
            WHERE m.id = %(message_id)s
              AND m.role = %(user_role)s
              AND c.users_id = %(user_id)s
            RETURNING id;
            """,
            {
                "message_id": message_id,
                "photo_order": order,
                "image": photo.data,
                "size_bytes": len(photo.data),
                "user_role": AssistantRole.USER.value,
                "user_id": user_id,
            },
            commit=False,
        )
        if row is None:
            raise NotFoundError("Message not found.")


# ---- Turns answered in the background (§8.12, §11.2.11) ----

_TURN_COLUMNS = """
    t.id, t.users_id, t.conversation_id, t.intake_event_id, t.meal_created, t.status,
    t.user_text, t.photo_count, t.notices, t.error_message,
    t.created_at, t.finished_at, t.seen_at
"""


def create_assistant_turn(
    connection, user_id: int, conversation_id: int | None, user_text: str, photo_count: int, *, commit: bool = True
) -> int:
    """A new turn, queued. `conversation_id`, when given, must be the user's.

    Raises:
        ConflictError: the user already has a turn being answered (one at a time,
            enforced by uq_assistant_turn_users_id_pending).
        NotFoundError: the conversation is not the user's.
    """
    try:
        row = _execute_query(
            connection,
            """
            INSERT INTO assistant_turn (users_id, conversation_id, status, user_text, photo_count)
            SELECT %(user_id)s, %(conversation_id)s, %(status)s, %(user_text)s, %(photo_count)s
            WHERE %(conversation_id)s::int IS NULL OR EXISTS (
                SELECT 1 FROM assistant_conversation c
                WHERE c.id = %(conversation_id)s AND c.users_id = %(user_id)s
            )
            RETURNING id;
            """,
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "status": AssistantTurnStatus.QUEUED.value,
                "user_text": user_text,
                "photo_count": photo_count,
            },
            commit=commit,
        )
    except UniqueViolation as exc:
        raise ConflictError("assistant_turn_pending") from exc
    if row is None:
        raise NotFoundError("Conversation not found.")
    return int(row["id"])


def get_assistant_turn(connection, user_id: int, turn_id: int) -> AssistantTurnRead | None:
    row = _execute_query(
        connection,
        f"SELECT {_TURN_COLUMNS} FROM assistant_turn t WHERE t.id = %(turn_id)s AND t.users_id = %(user_id)s;",
        {"turn_id": turn_id, "user_id": user_id},
        commit=False,
    )
    return assistant_turn_read_from_row(row) if row else None


def get_pending_assistant_turn(connection, user_id: int) -> AssistantTurnRead | None:
    """The turn of the user still being answered, if any (one at a time)."""
    row = _execute_query(
        connection,
        f"""
        SELECT {_TURN_COLUMNS} FROM assistant_turn t
        WHERE t.users_id = %(user_id)s AND t.status = ANY(%(pending)s)
        ORDER BY t.id DESC LIMIT 1;
        """,
        {"user_id": user_id, "pending": [status.value for status in ASSISTANT_TURN_PENDING]},
        commit=False,
    )
    return assistant_turn_read_from_row(row) if row else None


def get_latest_unseen_assistant_turn(connection, user_id: int) -> AssistantTurnRead | None:
    """The user's latest turn if it finished and the page never showed it: the
    answer of a message sent before leaving the page (§8.12)."""
    row = _execute_query(
        connection,
        f"""
        SELECT {_TURN_COLUMNS} FROM assistant_turn t
        WHERE t.users_id = %(user_id)s
        ORDER BY t.id DESC LIMIT 1;
        """,
        {"user_id": user_id},
        commit=False,
    )
    if row is None:
        return None
    turn = assistant_turn_read_from_row(row)
    return turn if not turn.pending and turn.seen_at is None else None


def start_assistant_turn(connection, turn_id: int, *, commit: bool = True) -> bool:
    """Queued -> running. False if it is no longer queued (failed at startup)."""
    row = _execute_query(
        connection,
        """
        UPDATE assistant_turn SET status = %(running)s, started_at = NOW()
        WHERE id = %(turn_id)s AND status = %(queued)s
        RETURNING id;
        """,
        {
            "turn_id": turn_id,
            "running": AssistantTurnStatus.RUNNING.value,
            "queued": AssistantTurnStatus.QUEUED.value,
        },
        commit=commit,
    )
    return row is not None


def finish_assistant_turn(
    connection,
    turn_id: int,
    *,
    conversation_id: int | None,
    intake_event_id: int | None,
    meal_created: bool,
    notices: list[str],
    commit: bool = True,
) -> None:
    """Running -> done, with where the answer ended up."""
    _execute_query(
        connection,
        """
        UPDATE assistant_turn
        SET status = %(done)s, conversation_id = %(conversation_id)s, intake_event_id = %(event_id)s,
            meal_created = %(meal_created)s, notices = %(notices)s, finished_at = NOW()
        WHERE id = %(turn_id)s AND status = %(running)s
        RETURNING id;
        """,
        {
            "turn_id": turn_id,
            "done": AssistantTurnStatus.DONE.value,
            "running": AssistantTurnStatus.RUNNING.value,
            "conversation_id": conversation_id,
            "event_id": intake_event_id,
            "meal_created": meal_created,
            "notices": Jsonb(list(notices)),
        },
        commit=commit,
    )


def fail_assistant_turn(connection, turn_id: int, error_message: str, *, commit: bool = True) -> None:
    """A pending turn -> failed, with the reason the user sees."""
    _execute_query(
        connection,
        """
        UPDATE assistant_turn
        SET status = %(failed)s, error_message = %(error_message)s, finished_at = NOW()
        WHERE id = %(turn_id)s AND status = ANY(%(pending)s)
        RETURNING id;
        """,
        {
            "turn_id": turn_id,
            "failed": AssistantTurnStatus.FAILED.value,
            "error_message": error_message[:200],
            "pending": [status.value for status in ASSISTANT_TURN_PENDING],
        },
        commit=commit,
    )


def fail_interrupted_assistant_turns(connection, error_message: str, *, commit: bool = True) -> int:
    """At startup: every turn still pending was cut by the restart of the server.
    They are failed, never run again, because a round may already have written
    to the cart (§8.12). Returns how many."""
    rows = _execute_query_many(
        connection,
        """
        UPDATE assistant_turn
        SET status = %(failed)s, error_message = %(error_message)s, finished_at = NOW()
        WHERE status = ANY(%(pending)s)
        RETURNING id;
        """,
        {
            "failed": AssistantTurnStatus.FAILED.value,
            "error_message": error_message[:200],
            "pending": [status.value for status in ASSISTANT_TURN_PENDING],
        },
        commit=commit,
    )
    return len(rows or [])


def mark_assistant_turn_seen(connection, user_id: int, turn_id: int, *, commit: bool = True) -> None:
    """The page showed the outcome of this turn: it is not reopened on coming back."""
    _execute_query(
        connection,
        """
        UPDATE assistant_turn SET seen_at = NOW()
        WHERE id = %(turn_id)s AND users_id = %(user_id)s AND seen_at IS NULL
        RETURNING id;
        """,
        {"turn_id": turn_id, "user_id": user_id},
        commit=commit,
    )
