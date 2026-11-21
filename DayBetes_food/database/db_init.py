"""Schema bootstrap (code_conventions.md §12): creates the tables of schema.py
and runs the idempotent `_ensure_*` steps of database/bootstrap/ in order, then
grants the runtime role its privileges. Run as `python -m DayBetes_food.database.db_init`
with the migrations identity (§12.6)."""

import logging
from psycopg import sql
from DayBetes_food.config import DB_RUNTIME_ROLE
from DayBetes_food.database.connection import get_migrations_connection
from DayBetes_food.database.schema import DBSchema
from DayBetes_food.database.bootstrap.users import (
    _ensure_auth_rate_limits_schema,
    _ensure_auth_sessions_schema,
    _ensure_default_user,
    _ensure_users_schema,
    _remove_legacy_user_columns,
    _remove_legacy_user_hidden_catalog,
    _remove_legacy_user_sessions,
)
from DayBetes_food.database.bootstrap.foods import (
    _ensure_catalog_schema,
    _ensure_copy_origin_schema,
    _ensure_food_brands_schema,
    _ensure_food_filter_indexes,
    _ensure_food_publication_schema,
    _ensure_food_search_indexes,
    _ensure_manual_intake_schema,
    _ensure_manual_intake_timestamptz,
    _ensure_off_product_schema,
    _ensure_recipe_plate_schema,
    _ensure_recipe_schema,
    _ensure_tags_schema,
    _ensure_trgm_search,
    _ensure_user_favorites_schema,
)
from DayBetes_food.database.bootstrap.meals import (
    _ensure_fridge_schema,
    _ensure_intake_event_schema,
    _ensure_portion_detail_schema,
)
from DayBetes_food.database.bootstrap.insulin import (
    _ensure_insulin_injection_history,
    _ensure_insulin_injections_schema,
    _ensure_insulin_pen_schema,
)
from DayBetes_food.database.bootstrap.assistant import (
    _ensure_assistant_schema,
)

logger = logging.getLogger(__name__)


def init_db():
    conn = get_migrations_connection()
    cur = conn.cursor()
    try:
        # Transactional advisory lock (§12.5): avoids race conditions on
        # concurrent startups with DB_INIT_ON_STARTUP=true.
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (742001,))
        tables = [
            DBSchema.users,
            DBSchema.auth_sessions,
            DBSchema.auth_rate_limits,
            DBSchema.food_brands,
            DBSchema.catalog(),
            DBSchema.manual_intake(),
            DBSchema.off_product(),
            DBSchema.ciqual_food(),
            DBSchema.fridge(),
            DBSchema.fridge_move,
            # Before intake_event and insulin_injections: both reference insulin_pen.
            DBSchema.insulin_brand(),
            DBSchema.insulin_pen(),
            DBSchema.tags(),
            DBSchema.recipe(),
            DBSchema.user_favorites,
            DBSchema.linked_tags,
            DBSchema.intake_event(),
            DBSchema.insulin_injections(),
            DBSchema.insulin_injection_history,
            DBSchema.meal_type_schedule(),
            DBSchema.intake_plate,
            DBSchema.recipe_plate,
            DBSchema.portion_detail,
            # After intake_event, which a conversation references.
            DBSchema.assistant_conversation,
            DBSchema.assistant_message(),
            DBSchema.assistant_photo(),
            DBSchema.assistant_turn,
        ]

        for table_sql in tables:
            cur.execute(table_sql)

        _ensure_food_brands_schema(cur)
        _ensure_trgm_search(cur)
        _ensure_user_favorites_schema(cur)
        _ensure_copy_origin_schema(cur)
        _ensure_food_publication_schema(cur)
        _ensure_food_filter_indexes(cur)
        # After the publication step: its unique index filters on is_published.
        _ensure_recipe_schema(cur)
        _ensure_catalog_schema(cur)
        _ensure_off_product_schema(cur)
        _ensure_food_search_indexes(cur)
        # After the publication and copy-origin steps: its indexes use
        # is_published and origin_root_id, which they create on old installs.
        _ensure_manual_intake_schema(cur)
        _ensure_manual_intake_timestamptz(cur)
        _ensure_users_schema(cur)
        _ensure_auth_sessions_schema(cur)
        _ensure_auth_rate_limits_schema(cur)
        _ensure_intake_event_schema(cur)
        _ensure_insulin_injections_schema(cur)
        # After the injections schema: its own migrations must not be logged as
        # changes made by someone.
        _ensure_insulin_injection_history(cur)
        _ensure_insulin_pen_schema(cur)
        # After recipe, catalog and manual_intake: the one-off migration reads their owners.
        _ensure_tags_schema(cur)
        # After intake_event: portion_detail plates depend on it through a
        # foreign key, so their DDL cannot run earlier (§12.3).
        _ensure_portion_detail_schema(cur)
        _ensure_recipe_plate_schema(cur)
        # After portion_detail: it adds source_fridge_id there.
        _ensure_fridge_schema(cur)
        _ensure_assistant_schema(cur)
        _remove_legacy_user_sessions(cur)
        _remove_legacy_user_hidden_catalog(cur)
        _remove_legacy_user_columns(cur)
        _ensure_default_user(cur)

        # Grant DML to the runtime role (§12.6): created objects are owned by the
        # migrations identity, so the runtime would be left without permissions.
        role = sql.Identifier(DB_RUNTIME_ROLE)
        cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
        cur.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(role))
        cur.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(role))
        cur.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}").format(role))
        cur.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {}").format(role))
        # Reference data: only the load script writes it (measurement §12.2).
        cur.execute(sql.SQL("REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON off_product FROM {}").format(role))
        cur.execute(sql.SQL("REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ciqual_food FROM {}").format(role))
        # Insert-only history (code §11.2.6): the runtime adds moves and reads them,
        # never changes or removes one. The CASCADE from fridge still deletes them,
        # because referential actions run as the owner of the table.
        cur.execute(sql.SQL("REVOKE UPDATE, DELETE, TRUNCATE ON fridge_move FROM {}").format(role))
        # Insert-only history (code §11.2.9): a conversation is replayed from its
        # messages, so the runtime never changes or removes one. They go with
        # their conversation (CASCADE), which runs as the owner of the table.
        cur.execute(sql.SQL("REVOKE UPDATE, DELETE, TRUNCATE ON assistant_message FROM {}").format(role))
        # Insert-only (code §11.2.10): a photo is what the model saw, so it never
        # changes; it goes with its message (CASCADE, run as the owner).
        cur.execute(sql.SQL("REVOKE UPDATE, DELETE, TRUNCATE ON assistant_photo FROM {}").format(role))
        # History of injections (code §11.10): only its trigger writes it, as the
        # owner of the table, so the runtime can read it and nothing else.
        cur.execute(sql.SQL("REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON insulin_injection_history FROM {}").format(role))

        conn.commit()
        logger.info("Database initialized successfully.")
    except Exception as e:
        conn.rollback()
        # Startup failure (section 12.5 of code_conventions.md): a failed
        # mandatory migration aborts startup, it does not continue as if the
        # schema were correct.
        logger.critical("Error initializing database: %s", e, exc_info=True)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    init_db()
