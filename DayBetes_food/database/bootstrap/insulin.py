"""Bootstrap of insulin pens, injections and the history of injections."""

from psycopg import sql
from DayBetes_food.database.schema import (
    insulin_brand_check_constraints,
    insulin_pen_check_constraints,
)
from DayBetes_food.domain.constants import InsulinType, InjectionZone, sql_in_list
from DayBetes_food.database.bootstrap.helpers import (
    _column_data_type,
    _constraint_exists,
    _create_index_once,
    _create_unique_index_once,
    _has_column,
)


def _ensure_insulin_pen_schema(cursor):
    """`insulin_brand`, `insulin_pen` and the pen columns of `insulin_injections` and
    `intake_event` (code §11.2.7, measurement §8.4). Idempotent: every step checks
    first (§12.2). Existing injections keep insulin_pen_id NULL (§12.7)."""
    for table, checks in (
        ("insulin_brand", insulin_brand_check_constraints()),
        ("insulin_pen", insulin_pen_check_constraints()),
    ):
        for name, expression in checks.items():
            if not _constraint_exists(cursor, table, name):
                cursor.execute(
                    sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} CHECK ({});").format(
                        sql.Identifier(table), sql.Identifier(name), sql.SQL(expression)
                    )
                )

    if not _has_column(cursor, "insulin_injections", "insulin_pen_id"):
        cursor.execute("ALTER TABLE insulin_injections ADD COLUMN insulin_pen_id INTEGER;")
    if not _constraint_exists(cursor, "insulin_injections", "fk_insulin_injections_insulin_pen_id_insulin_pen"):
        # Deferred NO ACTION, like fridge (§11.2.6): checked at commit, so deleting
        # a user does not depend on the order of its cascades.
        cursor.execute(
            "ALTER TABLE insulin_injections ADD CONSTRAINT fk_insulin_injections_insulin_pen_id_insulin_pen "
            "FOREIGN KEY (insulin_pen_id) REFERENCES insulin_pen(id) "
            "ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;"
        )

    if not _has_column(cursor, "intake_event", "insulin_pen_id"):
        cursor.execute("ALTER TABLE intake_event ADD COLUMN insulin_pen_id INTEGER;")
    if not _constraint_exists(cursor, "intake_event", "fk_intake_event_insulin_pen_id_insulin_pen"):
        cursor.execute(
            "ALTER TABLE intake_event ADD CONSTRAINT fk_intake_event_insulin_pen_id_insulin_pen "
            "FOREIGN KEY (insulin_pen_id) REFERENCES insulin_pen(id) ON DELETE SET NULL;"
        )
    if not _has_column(cursor, "intake_event", "insulin_units"):
        cursor.execute("ALTER TABLE intake_event ADD COLUMN insulin_units REAL;")
    if not _constraint_exists(cursor, "intake_event", "ck_intake_event_insulin_units"):
        cursor.execute(
            "ALTER TABLE intake_event ADD CONSTRAINT ck_intake_event_insulin_units CHECK "
            "(insulin_units IS NULL OR (insulin_units > 0 AND (insulin_units * 2) = floor(insulin_units * 2)));"
        )

    # One active brand per name and user, ignoring case (§11.5).
    _create_unique_index_once(
        cursor,
        "uq_insulin_brand_users_id_name",
        "ON insulin_brand (users_id, lower(name)) WHERE deleted_at IS NULL",
    )
    # The open pens of a user, the soonest to expire first (selectors and settings).
    _create_index_once(
        cursor, "idx_insulin_pen_users_id_open", "ON insulin_pen (users_id, expires_at) WHERE closed_at IS NULL"
    )
    # Whether a brand has pens (archive or delete, type change) and its deferred FK.
    _create_index_once(cursor, "idx_insulin_pen_insulin_brand_id", "ON insulin_pen (insulin_brand_id)")
    # What is left in a pen sums its injections; also its deferred FK. NULL in old rows.
    _create_index_once(
        cursor,
        "idx_insulin_injections_insulin_pen_id",
        "ON insulin_injections (insulin_pen_id, shot_time) WHERE insulin_pen_id IS NOT NULL",
    )
    # ON DELETE SET NULL from a deleted pen, and the planned meals of a closed pen.
    _create_index_once(
        cursor,
        "idx_intake_event_insulin_pen_id",
        "ON intake_event (insulin_pen_id) WHERE insulin_pen_id IS NOT NULL",
    )


# Constraints that this bootstrap declares as canonical for insulin_injections
# (§11.6). Any CHECK or FK of the table that is not here is dropped in
# _ensure_insulin_injections_schema: the bootstrap is the only source of the
# schema (§12.1).
_CANONICAL_INJECTION_CONSTRAINTS = (
    "fk_insulin_injections_users_id_users",
    "fk_insulin_injections_intake_event_id_intake_event",
    "ck_insulin_injections_insulin_type",
    "ck_insulin_injections_injection_zone",
    "ck_insulin_injections_units_by_type",     # H5: coherence rule by type
    "ck_insulin_injections_units_step",        # H5: multiples of 0.5 U
)


def _ensure_insulin_injection_history(cursor):
    """History of insulin_injections (code_conventions.md §11.10, decision 2026-11-17).

    A trigger keeps the previous row on every UPDATE that changes something and
    on every DELETE, whoever makes it: the app, the assistant or SQL by hand. The
    function is SECURITY DEFINER, so it writes as the owner of the table while
    the runtime role can only read it (grants in init_db). search_path is fixed,
    as a definer function needs.
    """
    cursor.execute(
        """
        CREATE OR REPLACE FUNCTION log_insulin_injection_change()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
        BEGIN
            IF TG_OP = 'UPDATE'
               AND to_jsonb(OLD) - 'updated_at' = to_jsonb(NEW) - 'updated_at' THEN
                RETURN NULL;
            END IF;
            INSERT INTO insulin_injection_history
                (insulin_injection_id, users_id, operation, old_row, changed_by_role)
            VALUES
                (OLD.id, OLD.users_id, lower(TG_OP), to_jsonb(OLD), session_user);
            RETURN NULL;
        END;
        $$;
        """
    )
    cursor.execute("DROP TRIGGER IF EXISTS trg_insulin_injections_history ON insulin_injections;")
    cursor.execute(
        "CREATE TRIGGER trg_insulin_injections_history "
        "AFTER UPDATE OR DELETE ON insulin_injections "
        "FOR EACH ROW EXECUTE FUNCTION log_insulin_injection_change();"
    )
    _create_index_once(
        cursor,
        "idx_insulin_injection_history_injection_id",
        "ON insulin_injection_history (insulin_injection_id, changed_at)",
    )


def _ensure_insulin_injections_schema(cursor):
    cursor.execute(
        """
        DO $$
        BEGIN
            -- Prefer direct rename when old table exists and new one does not.
            IF to_regclass('public.insulin_injections') IS NULL AND to_regclass('public.injection_zones') IS NOT NULL THEN
                ALTER TABLE injection_zones RENAME TO insulin_injections;
            ELSIF to_regclass('public.insulin_injections') IS NULL AND to_regclass('public.injection_zone') IS NOT NULL THEN
                ALTER TABLE injection_zone RENAME TO insulin_injections;
            END IF;
        END $$;
        """
    )

    insulin_type_list = sql_in_list(InsulinType)
    injection_zone_list = sql_in_list(InjectionZone)

    cursor.execute(
        """
        ALTER TABLE intake_event
        ADD COLUMN IF NOT EXISTS injection_zone VARCHAR(50);
        """
    )
    cursor.execute(
        f"""
        ALTER TABLE intake_event DROP CONSTRAINT IF EXISTS ck_intake_event_injection_zone;
        ALTER TABLE intake_event
        ADD CONSTRAINT ck_intake_event_injection_zone
        CHECK (injection_zone IS NULL OR injection_zone IN ({injection_zone_list}));
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS insulin_injections (
            id SERIAL PRIMARY KEY,
            users_id INTEGER,
            intake_event_id INTEGER,
            shot_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            insulin_type VARCHAR(20),
            units REAL,
            injection_zone VARCHAR(50),
            notes TEXT,
            needle_leak BOOLEAN,
            skin_pinch BOOLEAN,
            created_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ,
            timezone_at_event TEXT,
            CONSTRAINT fk_insulin_injections_users_id_users
                FOREIGN KEY (users_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_insulin_injections_intake_event_id_intake_event
                FOREIGN KEY (intake_event_id) REFERENCES intake_event(id) ON DELETE SET NULL,
            CONSTRAINT ck_insulin_injections_insulin_type
                CHECK (insulin_type IN ({insulin_type_list})),
            CONSTRAINT ck_insulin_injections_units_by_type
                CHECK (
                    (insulin_type = 'basal' AND units IS NOT NULL AND units > 0)
                    OR (insulin_type = 'rapid' AND (units IS NULL OR units > 0))
                ),
            CONSTRAINT ck_insulin_injections_units_step
                CHECK (units IS NULL OR (units * 2) = floor(units * 2)),
            CONSTRAINT ck_insulin_injections_injection_zone
                CHECK (injection_zone IS NULL OR injection_zone IN ({injection_zone_list}))
        );
        """
    )

    # Merge of the legacy tables (§12.2). It runs right after CREATE TABLE and
    # before H4/H5 so that the migrated rows receive the same timestamp backfill
    # and are validated by the canonical constraints like any other row.
    # The physical name of the dose column depends on each database's history:
    # legacy table -> basal_units; table created by this bootstrap -> units.
    for legacy_table in ("injection_zone", "injection_zones"):
        cursor.execute("SELECT to_regclass(%s) AS reg;", (f"public.{legacy_table}",))
        if (cursor.fetchone() or {}).get("reg") is None:
            continue
        source_units = "basal_units" if _has_column(cursor, legacy_table, "basal_units") else "units"
        target_units = "basal_units" if _has_column(cursor, "insulin_injections", "basal_units") else "units"
        cursor.execute(
            sql.SQL(
                """
                INSERT INTO insulin_injections
                    (id, users_id, intake_event_id, shot_time, insulin_type, {target}, injection_zone)
                SELECT id, users_id, intake_event_id, shot_time, insulin_type, {source}, injection_zone
                FROM {legacy}
                ON CONFLICT (id) DO NOTHING;
                """
            ).format(
                target=sql.Identifier(target_units),
                source=sql.Identifier(source_units),
                legacy=sql.Identifier(legacy_table),
            )
        )
        cursor.execute(
            "SELECT setval('insulin_injections_id_seq', "
            "COALESCE((SELECT MAX(id) FROM insulin_injections), 1), true);"
        )
        cursor.execute(sql.SQL("DROP TABLE {};").format(sql.Identifier(legacy_table)))

    # ========== H4: TIMESTAMPTZ and audit timestamps ==========
    # 1) New columns (nullable first)
    cursor.execute("ALTER TABLE insulin_injections ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;")
    cursor.execute("ALTER TABLE insulin_injections ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;")
    cursor.execute("ALTER TABLE insulin_injections ADD COLUMN IF NOT EXISTS timezone_at_event TEXT;")

    # 2) Convert shot_time to TIMESTAMPTZ (only if it is still naive)
    data_type = (_column_data_type(cursor, "insulin_injections", "shot_time") or "").lower()
    if data_type == "timestamp without time zone":
        cursor.execute(
            "ALTER TABLE insulin_injections "
            "ALTER COLUMN shot_time TYPE TIMESTAMPTZ USING shot_time AT TIME ZONE 'UTC';"
        )

    # 3) Timestamp backfill, only of the rows still missing it. Rewriting every row
    # on each run queued the deferred check of `insulin_pen_id` for the rows with a
    # pen (rows written in this transaction are always checked), and the ALTERs
    # below then failed with "pending trigger events".
    cursor.execute(
        "UPDATE insulin_injections SET created_at = COALESCE(shot_time, CURRENT_TIMESTAMP) WHERE created_at IS NULL;"
    )
    cursor.execute("UPDATE insulin_injections SET updated_at = created_at WHERE updated_at IS NULL;")
    cursor.execute("UPDATE insulin_injections SET timezone_at_event = 'Europe/Madrid' WHERE timezone_at_event IS NULL;")

    # 4) Defaults and NOT NULL
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN created_at SET NOT NULL;")
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN updated_at SET NOT NULL;")
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN timezone_at_event SET DEFAULT 'Europe/Madrid';")
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN timezone_at_event SET NOT NULL;")

    # ========== H5: rename basal_units -> units, add NOT NULL ==========
    # Rename the column
    if _has_column(cursor, "insulin_injections", "basal_units") and not _has_column(cursor, "insulin_injections", "units"):
        cursor.execute("ALTER TABLE insulin_injections RENAME COLUMN basal_units TO units;")

    # NOT NULL on users_id and insulin_type
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN users_id SET NOT NULL;")
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN insulin_type SET NOT NULL;")

    # Constraint convergence (§12.2): any CHECK or FK of the table whose name is
    # not canonical is dropped — both those inherited from
    # injection_zone/injection_zones and those auto-generated by PostgreSQL in
    # earlier clean installs (insulin_injections_*_check, *_fkey). PRIMARY KEY and
    # UNIQUE ('p', 'u') are excluded; they are handled by rename further below.
    cursor.execute(
        """
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'public.insulin_injections'::regclass
          AND contype IN ('c', 'f')
          AND conname <> ALL(%(canonical)s)
        """,
        {"canonical": list(_CANONICAL_INJECTION_CONSTRAINTS)},
    )
    for row in cursor.fetchall():
        cursor.execute(
            sql.SQL("ALTER TABLE insulin_injections DROP CONSTRAINT IF EXISTS {}").format(
                sql.Identifier(row["conname"])
            )
        )

    # Rename PK and sequence to canonical names if they exist under inherited names (§12.2)
    cursor.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'injection_zone_pkey') THEN
                ALTER TABLE insulin_injections RENAME CONSTRAINT injection_zone_pkey TO insulin_injections_pkey;
            END IF;
            IF to_regclass('public.injection_zone_id_seq') IS NOT NULL
               AND to_regclass('public.insulin_injections_id_seq') IS NULL THEN
                ALTER SEQUENCE injection_zone_id_seq RENAME TO insulin_injections_id_seq;
            END IF;
        END $$;
        """
    )

    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_insulin_injections_intake_event_id_intake_event'
            ) THEN
                ALTER TABLE insulin_injections
                ADD CONSTRAINT fk_insulin_injections_intake_event_id_intake_event
                FOREIGN KEY (intake_event_id) REFERENCES intake_event(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_insulin_injections_users_id_users'
            ) THEN
                ALTER TABLE insulin_injections
                ADD CONSTRAINT fk_insulin_injections_users_id_users
                FOREIGN KEY (users_id) REFERENCES users(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """
    )
    cursor.execute(
        f"""
        ALTER TABLE insulin_injections DROP CONSTRAINT IF EXISTS ck_insulin_injections_insulin_type;
        ALTER TABLE insulin_injections
        ADD CONSTRAINT ck_insulin_injections_insulin_type
        CHECK (insulin_type IN ({insulin_type_list}));
        """
    )
    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_insulin_injections_units_by_type'
            ) THEN
                ALTER TABLE insulin_injections
                ADD CONSTRAINT ck_insulin_injections_units_by_type
                CHECK (
                    (insulin_type = 'basal' AND units IS NOT NULL AND units > 0)
                    OR (insulin_type = 'rapid' AND (units IS NULL OR units > 0))
                );
            END IF;
        END $$;
        """
    )
    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_insulin_injections_units_step'
            ) THEN
                ALTER TABLE insulin_injections
                ADD CONSTRAINT ck_insulin_injections_units_step
                CHECK (units IS NULL OR (units * 2) = floor(units * 2));
            END IF;
        END $$;
        """
    )
    cursor.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_insulin_injections_injection_zone'
            ) THEN
                ALTER TABLE insulin_injections
                ADD CONSTRAINT ck_insulin_injections_injection_zone
                CHECK (injection_zone IS NULL OR injection_zone IN ({injection_zone_list}));
            END IF;
        END $$;
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_insulin_injections_intake_event_id_shot_time
        ON insulin_injections (intake_event_id, shot_time DESC, id DESC);
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_insulin_injections_users_id_shot_time
        ON insulin_injections (users_id, shot_time DESC, id DESC);
        """
    )
