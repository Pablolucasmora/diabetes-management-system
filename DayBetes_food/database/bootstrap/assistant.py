"""Bootstrap of the assistant's conversations and messages."""


from DayBetes_food.database.bootstrap.helpers import (
    _constraint_exists,
    _create_index_once,
)


def _ensure_assistant_schema(cursor):
    """Indexes and later columns of the assistant's tables (code_conventions.md §11.2.9)."""
    # `No meal` conversations (2026-11-13): a chat that never gets a meal (§8.12).
    cursor.execute(
        "ALTER TABLE assistant_conversation ADD COLUMN IF NOT EXISTS without_meal BOOLEAN NOT NULL DEFAULT FALSE;"
    )
    if not _constraint_exists(cursor, "assistant_conversation", "ck_assistant_conversation_without_meal"):
        cursor.execute(
            "ALTER TABLE assistant_conversation ADD CONSTRAINT ck_assistant_conversation_without_meal "
            "CHECK (NOT (without_meal AND intake_event_id IS NOT NULL));"
        )
    # The latest conversation of a meal (§8.12: one conversation per meal).
    _create_index_once(
        cursor,
        "ix_assistant_conversation_users_id_intake_event_id",
        "ON assistant_conversation (users_id, intake_event_id, id DESC)",
    )
    # The latest `No meal` conversation of a user (§8.12).
    _create_index_once(
        cursor,
        "ix_assistant_conversation_users_id_without_meal",
        "ON assistant_conversation (users_id, id DESC) WHERE without_meal",
    )
    # The FK to intake_event is SET NULL on delete: without this index, deleting
    # a meal would scan the whole table (§11.8).
    _create_index_once(
        cursor,
        "ix_assistant_conversation_intake_event_id",
        "ON assistant_conversation (intake_event_id) WHERE intake_event_id IS NOT NULL",
    )
