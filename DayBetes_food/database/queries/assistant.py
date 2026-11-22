"""Queries for `assistant_conversation` and `assistant_message`
(code_conventions.md §8.12, §11.2.9).

Both are private: the owner travels in the SQL of every statement (§5.3), so
another user's conversation and one that does not exist give the same result
(§5.4). A conversation is linked only to a planned meal of its owner, checked
in the same statement that writes it. Messages are insert-only: a
conversation is replayed to the model from them, in order.
"""

from psycopg.types.json import Jsonb

from DayBetes_food.database.mappers import (
    assistant_conversation_read_from_row,
    assistant_message_read_from_row,
)
from DayBetes_food.database.queries.crud import _execute_query, _execute_query_many
from DayBetes_food.domain.assistant import (
    AssistantConversationRead,
    AssistantMessageCreate,
    AssistantMessageRead,
    ChatSummary,
    PastChat,
    chat_preview,
)
from DayBetes_food.domain.constants import AssistantRole, IntakeEventState
from DayBetes_food.errors import NotFoundError

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
