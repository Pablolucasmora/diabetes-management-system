"""Bootstrap of the meals: intake_event, portion_detail and its plates, and the fridge."""

import logging
from psycopg import sql
from DayBetes_food.database.schema import fridge_check_constraints
from DayBetes_food.domain.constants import (
    IntakeEventState,
    MealType,
    ConservationMethod,
    CookingMethod,
    FoodPhysicalState,
    AmountMethod,
    FractionMethod,
    FridgeCloseReason,
    Ripeness,
    sql_in_list,
)
from DayBetes_food.database.bootstrap.helpers import (
    _check_lacks_values,
    _column_data_type,
    _constraint_exists,
    _create_index_once,
    _create_unique_index_once,
    _has_column,
    _index_exists,
    _replace_boolean_with_list,
)

logger = logging.getLogger(__name__)


# Columns of the table as it was created before the decision of 2026-11-07. No code
# ever wrote them (measurement_conventions.md 4.8.1).
_FRIDGE_LEGACY_COLUMNS = ("tupper_name", "entry_date", "is_compound", "total_tupper_weight")

_FRIDGE_CONSTRAINT_RENAMES = {
    "fridge_pkey": "pk_fridge",
    "fridge_users_id_fkey": "fk_fridge_users_id_users",
}


def _ensure_fridge_schema(cursor):
    """`fridge`, `fridge_move` and `portion_detail.source_fridge_id` (code §11.2.6,
    measurement §4.8). Idempotent.

    The old table had no writer, so it is reshaped in place only while it is empty.
    If it has rows, the migration stops: what to do with them is a data decision
    (§12.4, §12.7), not something to infer here.
    """
    legacy = [column for column in _FRIDGE_LEGACY_COLUMNS if _has_column(cursor, "fridge", column)]
    if legacy:
        cursor.execute("SELECT count(*) AS total FROM fridge;")
        total = cursor.fetchone()["total"]
        if total:
            raise RuntimeError(
                f"fridge has {total} rows with the pre-2026-11-07 columns {legacy}; "
                "they cannot be reshaped without an explicit data decision (code_conventions.md 12.7)."
            )
        for column in legacy:
            cursor.execute(sql.SQL("ALTER TABLE fridge DROP COLUMN {};").format(sql.Identifier(column)))

    # The table is empty here or already has these columns, so NOT NULL without a
    # default is safe: stored_at and expires_at are always given by the app.
    new_columns = (
        ("name", "VARCHAR(255)"),
        ("location", "VARCHAR(20) NOT NULL"),
        ("stored_at", "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ("expires_at", "TIMESTAMPTZ NOT NULL"),
        ("content_weight", "REAL"),
        ("closed_at", "TIMESTAMPTZ"),
        ("closed_reason", "VARCHAR(20)"),
        ("created_at", "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ("updated_at", "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"),
    )
    for column, definition in new_columns:
        if not _has_column(cursor, "fridge", column):
            # The definitions are code constants, not request data (§11.9).
            cursor.execute(
                sql.SQL("ALTER TABLE fridge ADD COLUMN {} " + definition + ";").format(sql.Identifier(column))
            )
    cursor.execute(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'fridge' AND column_name = 'users_id';"
    )
    if cursor.fetchone()["is_nullable"] == "YES":
        # Fails on its own if a container has no owner.
        cursor.execute("ALTER TABLE fridge ALTER COLUMN users_id SET NOT NULL;")

    for old_name, new_name in _FRIDGE_CONSTRAINT_RENAMES.items():
        if _constraint_exists(cursor, "fridge", old_name) and not _constraint_exists(cursor, "fridge", new_name):
            cursor.execute(
                sql.SQL("ALTER TABLE fridge RENAME CONSTRAINT {} TO {};").format(
                    sql.Identifier(old_name), sql.Identifier(new_name)
                )
            )
    # Technical backfill (§12.7): until 2026-11-07 discarding was the only way a
    # container was closed, so a closed one without a reason was discarded.
    cursor.execute(
        "UPDATE fridge SET closed_reason = %(reason)s WHERE closed_at IS NOT NULL AND closed_reason IS NULL;",
        {"reason": FridgeCloseReason.DISCARDED.value},
    )
    for name, expression in fridge_check_constraints().items():
        if not _constraint_exists(cursor, "fridge", name):
            cursor.execute(
                sql.SQL("ALTER TABLE fridge ADD CONSTRAINT {} CHECK ({});").format(
                    sql.Identifier(name), sql.SQL(expression)
                )
            )
    # The fridge page lists the open containers of a user, the soonest to expire first.
    _create_index_once(
        cursor, "idx_fridge_users_id_open", "ON fridge (users_id, expires_at) WHERE closed_at IS NULL"
    )
    # Place history of a container, in order (measurement §4.8.4); also serves the CASCADE.
    _create_index_once(cursor, "idx_fridge_move_fridge_id", "ON fridge_move (fridge_id, moved_at)")

    # The column itself is added by _ensure_portion_detail_schema: it is part of
    # the uniqueness key of §4.6.4.
    # Deferred NO ACTION, not RESTRICT (§11.8): RESTRICT, and a non-deferred NO
    # ACTION, are checked inside each cascade, so deleting a user failed when the
    # cascade reached the container before the event portion that references it.
    # Checked at commit, it still blocks discarding a container something was eaten
    # from. A first version of this FK with another action is replaced.
    cursor.execute(
        "SELECT confdeltype, condeferrable, condeferred FROM pg_constraint "
        "WHERE conrelid = 'public.portion_detail'::regclass "
        "AND conname = 'fk_portion_detail_source_fridge_id_fridge';"
    )
    existing_fk = cursor.fetchone()
    if existing_fk is not None and not (
        existing_fk["confdeltype"] == "a" and existing_fk["condeferrable"] and existing_fk["condeferred"]
    ):
        cursor.execute("ALTER TABLE portion_detail DROP CONSTRAINT fk_portion_detail_source_fridge_id_fridge;")
        existing_fk = None
    if existing_fk is None:
        cursor.execute(
            "ALTER TABLE portion_detail ADD CONSTRAINT fk_portion_detail_source_fridge_id_fridge "
            "FOREIGN KEY (source_fridge_id) REFERENCES fridge(id) "
            "ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;"
        )
    if not _constraint_exists(cursor, "portion_detail", "ck_portion_detail_source_fridge_only_for_event"):
        cursor.execute(
            "ALTER TABLE portion_detail ADD CONSTRAINT ck_portion_detail_source_fridge_only_for_event "
            "CHECK (source_fridge_id IS NULL OR intake_event_id IS NOT NULL);"
        )
    # The content of a container is read by fridge_id, which is also the target of its
    # ON DELETE CASCADE. source_fridge_id is checked at commit by its deferred foreign
    # key when a container is deleted, and is NULL in almost every row, hence
    # partial (§11.7).
    _create_index_once(cursor, "idx_portion_detail_fridge_id", "ON portion_detail (fridge_id) WHERE fridge_id IS NOT NULL")
    _create_index_once(
        cursor,
        "idx_portion_detail_source_fridge_id",
        "ON portion_detail (source_fridge_id) WHERE source_fridge_id IS NOT NULL",
    )


# Renames of inherited constraints to the canonical names of §11.6.
# They only rename: the CHECK definition does not change.
_INTAKE_EVENT_CONSTRAINT_RENAMES = {
    "intake_event_users_id_fkey": "fk_intake_event_users_id_users",
    "intake_event_amount_confidence_check": "ck_intake_event_amount_confidence",
}


# Event metrics that depend on the food and are computed live (§6.9.4).
# These are the old column names: the live metrics are now *_coverage
# (= 1 - *_uncertainty, measurement_conventions.md §6.1).
_INTAKE_EVENT_LIVE_METRIC_COLUMNS = (
    "quality_confidence",
    "carbs_uncertainty",
    "sugars_uncertainty",
    "fats_uncertainty",
    "saturated_uncertainty",
    "proteins_uncertainty",
    "fiber_uncertainty",
)


def _ensure_intake_event_schema(cursor):
    """intake_event: timestamps, soft-delete, TIMESTAMPTZ, NOT NULL, constraints and index.

    Closes findings 3 (deleted_at), 4, 7, 8 and 9 of
    audit/audit_intake_event.md. Idempotent (§12.2).
    """
    state_list = sql_in_list(IntakeEventState)
    meal_type_list = sql_in_list(MealType)

    # ---- H4 / H3: audit and soft-delete columns (nullable first) ----
    cursor.execute("ALTER TABLE intake_event ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;")
    cursor.execute("ALTER TABLE intake_event ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;")
    cursor.execute("ALTER TABLE intake_event ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;")
    cursor.execute("ALTER TABLE intake_event ADD COLUMN IF NOT EXISTS timezone_at_event TEXT;")

    # ---- H7: meal_time TIMESTAMP naive-UTC -> TIMESTAMPTZ (§10.5) ----
    # The DEFAULT is dropped before ALTER TYPE: PostgreSQL cannot automatically
    # convert a timestamp default to timestamptz and would abort.
    data_type = (_column_data_type(cursor, "intake_event", "meal_time") or "").lower()
    if data_type == "timestamp without time zone":
        cursor.execute("ALTER TABLE intake_event ALTER COLUMN meal_time DROP DEFAULT;")
        cursor.execute(
            "ALTER TABLE intake_event "
            "ALTER COLUMN meal_time TYPE TIMESTAMPTZ USING meal_time AT TIME ZONE 'UTC';"
        )
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN meal_time SET DEFAULT CURRENT_TIMESTAMP;")

    # ---- Technical backfill of the new columns ----
    # It changes no existing data: it only fills columns that did not exist
    # before (decision 2026-09-08 about historical data).
    cursor.execute(
        "UPDATE intake_event "
        "SET created_at = COALESCE(created_at, meal_time, CURRENT_TIMESTAMP);"
    )
    cursor.execute("UPDATE intake_event SET updated_at = COALESCE(updated_at, created_at);")
    cursor.execute(
        "UPDATE intake_event SET timezone_at_event = COALESCE(timezone_at_event, 'Europe/Madrid');"
    )

    # ---- Defaults and NOT NULL ----
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN created_at SET NOT NULL;")
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN updated_at SET NOT NULL;")
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN timezone_at_event SET DEFAULT 'Europe/Madrid';")
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN timezone_at_event SET NOT NULL;")
    # deleted_at stays nullable: NULL = active (§11.3).

    # ---- H8: users_id NOT NULL ----
    # Verified on 2026-09-08: 0 rows with users_id NULL. If any appeared, this
    # ALTER would fail and abort the whole bootstrap (§12.5), which is correct.
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN users_id SET NOT NULL;")

    # ---- H8: canonical names (§11.6) ----
    for old_name, new_name in _INTAKE_EVENT_CONSTRAINT_RENAMES.items():
        if _constraint_exists(cursor, "intake_event", old_name) and not _constraint_exists(
            cursor, "intake_event", new_name
        ):
            cursor.execute(
                sql.SQL("ALTER TABLE intake_event RENAME CONSTRAINT {} TO {};").format(
                    sql.Identifier(old_name), sql.Identifier(new_name)
                )
            )

    # state and meal_type are not renamed: they are regenerated from the enums (§4.4).
    cursor.execute("ALTER TABLE intake_event DROP CONSTRAINT IF EXISTS intake_event_state_check;")
    cursor.execute("ALTER TABLE intake_event DROP CONSTRAINT IF EXISTS ck_intake_event_state;")
    cursor.execute(
        f"ALTER TABLE intake_event ADD CONSTRAINT ck_intake_event_state "
        f"CHECK (state IN ({state_list}));"
    )
    cursor.execute("ALTER TABLE intake_event DROP CONSTRAINT IF EXISTS intake_event_meal_type_check;")
    cursor.execute("ALTER TABLE intake_event DROP CONSTRAINT IF EXISTS ck_intake_event_meal_type;")
    cursor.execute(
        f"ALTER TABLE intake_event ADD CONSTRAINT ck_intake_event_meal_type "
        f"CHECK (meal_type IS NULL OR meal_type IN ({meal_type_list}));"
    )

    # ---- H9: partial index for the real filter of every list (§11.7) ----
    cursor.execute("DROP INDEX IF EXISTS idx_intake_event_users_id_state_meal_time;")
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_intake_event_users_id_state_meal_time
        ON intake_event (users_id, state, meal_time DESC, id DESC)
        WHERE deleted_at IS NULL;
        """
    )

    # ---- total_amount is no longer persisted: it is computed live (decision 2026-09-10) ----
    cursor.execute("ALTER TABLE intake_event DROP COLUMN IF EXISTS total_amount;")

    # ---- quality_confidence and *_uncertainty are no longer persisted: they depend
    # on the food, so they are computed live (measurement_conventions.md §6.9.4,
    # finding 18 of audit_manual_intake.md). Destructive migration approved on
    # 2026-10-09 (§12.4); dropping a column drops its CHECK too. Recovery: CSV
    # export of the local values taken before dropping them and the nightly
    # production pg_dump (infra_conventions.md). ----
    for column in _INTAKE_EVENT_LIVE_METRIC_COLUMNS:
        cursor.execute(
            sql.SQL("ALTER TABLE intake_event DROP COLUMN IF EXISTS {};").format(
                sql.Identifier(column)
            )
        )

    # ---- H32/H35: ingested_amount with sanity limits (measurement_conventions.md
    # §6.9.2, decision 2026-09-10). Verified on 2026-09-09: 0 rows negative or out
    # of range; if any appeared, this ALTER would fail and abort the bootstrap,
    # which is correct (§12.5). ----
    cursor.execute("ALTER TABLE intake_event DROP CONSTRAINT IF EXISTS ck_intake_event_ingested_amount;")
    cursor.execute(
        "ALTER TABLE intake_event ADD CONSTRAINT ck_intake_event_ingested_amount "
        "CHECK (ingested_amount IS NULL OR (ingested_amount >= 0 AND ingested_amount <= 100000));"
    )


def _ensure_portion_detail_schema(cursor):
    """portion_detail: evolutionary table hook (§12.1).

    It was the only large table without its own hook, so the DDL applied by hand
    to the existing database stayed out of the code (finding 16 of
    audit/audit_portion_detail.md). Idempotent (§12.2).
    """
    # ---- H16: split_group_id was hand-applied DDL that never returned to code ----
    # varchar(64), 0 rows with a value, 0 references in the code, 0 commits. The
    # plates design (decision 2026-09-19) relies on intake_plate, not here.
    if _has_column(cursor, "portion_detail", "split_group_id"):
        cursor.execute("ALTER TABLE portion_detail DROP COLUMN split_group_id;")

    # ---- T1.2: blocking pre-checks before writing the new CHECKs (decision 2026-09-22) ----
    # The amount check can only run while amount_g still exists; after T1.3 the
    # column is unreachable. Both checks abort the bootstrap instead of cleaning
    # data (§12.5, §12.7): a pre-existing row that violates the new rule is a data
    # decision, not something a migration may silently rewrite.
    if _column_data_type(cursor, "portion_detail", "amount_g") is not None:
        cursor.execute(
            """
            SELECT count(*) AS zero_rows
            FROM portion_detail
            WHERE COALESCE(plate_amount, amount_g) = 0;
            """
        )
        zero_rows = cursor.fetchone()["zero_rows"]
        if zero_rows:
            raise RuntimeError(
                f"{zero_rows} portion_detail rows have amount 0; the new "
                "ck_portion_detail_amount_range (amount > 0) cannot be created. "
                "This needs an explicit data decision (code_conventions.md 12.7)."
            )

    cursor.execute(
        """
        SELECT count(*) AS out_of_range
        FROM portion_detail
        WHERE offset_minutes IS NOT NULL
          AND (offset_minutes < -300 OR offset_minutes > 300);
        """
    )
    out_of_range = cursor.fetchone()["out_of_range"]
    if out_of_range:
        raise RuntimeError(
            f"{out_of_range} portion_detail rows have offset_minutes outside -300..300; "
            "ck_portion_detail_offset_minutes cannot be created."
        )

    # ---- Plates (servings) inside an event (decision 2026-09-19) ----
    # The column is born nullable on purpose: existing rows do not have a plate
    # yet and the CHECK that requires one is added at the end, after the data
    # migration.
    cursor.execute("ALTER TABLE portion_detail ADD COLUMN IF NOT EXISTS plate_id INTEGER;")

    if not _constraint_exists(cursor, "portion_detail", "fk_portion_detail_plate_id_intake_plate"):
        cursor.execute(
            "ALTER TABLE portion_detail "
            "ADD CONSTRAINT fk_portion_detail_plate_id_intake_plate "
            "FOREIGN KEY (plate_id) REFERENCES intake_plate(id) ON DELETE RESTRICT;"
        )

    # Migration (measurement_conventions.md §4.6.6): one plate per event having
    # portions without one, with name NULL —the name is derived from its
    # ingredients— and the smallest offset of its rows. Idempotent: it only looks
    # at event portions that do not belong to a plate yet.
    cursor.execute(
        """
        INSERT INTO intake_plate (intake_event_id, name, offset_minutes)
        SELECT pd.intake_event_id, NULL, MIN(pd.offset_minutes)
        FROM portion_detail pd
        WHERE pd.intake_event_id IS NOT NULL AND pd.plate_id IS NULL
        GROUP BY pd.intake_event_id;
        """
    )
    cursor.execute(
        """
        UPDATE portion_detail pd
        SET plate_id = ip.id
        FROM intake_plate ip
        WHERE pd.intake_event_id = ip.intake_event_id
          AND pd.plate_id IS NULL;
        """
    )

    # Migration postcondition before declaring it in the database (§12.5): a
    # single mismatched row would make the CHECK fail halfway and leave the
    # bootstrap in a worse state than the initial one.
    cursor.execute(
        """
        SELECT count(*) AS pending
        FROM portion_detail
        WHERE (intake_event_id IS NULL) <> (plate_id IS NULL);
        """
    )
    pending = cursor.fetchone()["pending"]
    if pending:
        raise RuntimeError(
            f"Incomplete plate migration: {pending} portion_detail rows without "
            "a matching pair of intake_event_id and plate_id."
        )

    if not _constraint_exists(cursor, "portion_detail", "ck_portion_detail_plate_only_for_event"):
        cursor.execute(
            "ALTER TABLE portion_detail "
            "ADD CONSTRAINT ck_portion_detail_plate_only_for_event "
            "CHECK ((intake_event_id IS NULL) = (plate_id IS NULL));"
        )

    # Indexes for the two new foreign keys (§11.7): the cart reads portions by
    # plate and plates by event on every render.
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_portion_detail_plate_id ON portion_detail (plate_id);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_intake_plate_intake_event_id "
        "ON intake_plate (intake_event_id);"
    )

    # ---- T1.4: offset_minutes range CHECK (finding 9) ----
    # Same name and rule as ck_intake_plate_offset_minutes, already present: the
    # template cannot accept values that the row would reject (measurement
    # conventions.md 4.6.2).
    if not _constraint_exists(cursor, "portion_detail", "ck_portion_detail_offset_minutes"):
        cursor.execute(
            "ALTER TABLE portion_detail ADD CONSTRAINT ck_portion_detail_offset_minutes "
            "CHECK (offset_minutes IS NULL OR (offset_minutes >= -300 AND offset_minutes <= 300));"
        )

    # ---- T1.5: created_at / updated_at (finding 11, decision 2026-09-22) ----
    # Technical backfill (§12.7): the event date is the closest thing to "when
    # this portion was added". Recipe portions have no source and get the
    # migration instant. No actor column (decision 2026-09-22).
    cursor.execute("ALTER TABLE portion_detail ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;")
    cursor.execute("ALTER TABLE portion_detail ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;")
    cursor.execute(
        """
        UPDATE portion_detail pd
        SET created_at = COALESCE(pd.created_at, ie.meal_time, ie.created_at, CURRENT_TIMESTAMP)
        FROM intake_event ie
        WHERE ie.id = pd.intake_event_id AND pd.created_at IS NULL;
        """
    )
    cursor.execute("UPDATE portion_detail SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL;")
    cursor.execute("UPDATE portion_detail SET updated_at = created_at WHERE updated_at IS NULL;")
    cursor.execute("ALTER TABLE portion_detail ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE portion_detail ALTER COLUMN created_at SET NOT NULL;")
    cursor.execute("ALTER TABLE portion_detail ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE portion_detail ALTER COLUMN updated_at SET NOT NULL;")

    # ---- T1.3: single amount column (findings 2, 14, 26; decisions 2026-09-18 and 2026-09-22) ----
    # amount = COALESCE(plate_amount, amount_g) is exactly what every read already
    # computed (portion_intake_amount, the COALESCE of scale_event_portion_amounts,
    # group_portions): it asserts nothing new about historical meals, it freezes in
    # the data what the code already did. The rename breaks any unmigrated read on
    # purpose (decision 2026-09-18), which is why T2/T3 must ship in the same cycle.
    # This must run before the duplicate consolidation below, which from now on
    # sums `amount`. Destructive migration (§12.4): the two columns are dropped in
    # the same transaction as the backfill, all or nothing.
    if _column_data_type(cursor, "portion_detail", "amount") is None:
        cursor.execute("ALTER TABLE portion_detail ADD COLUMN amount REAL;")
    if _column_data_type(cursor, "portion_detail", "amount_g") is not None:
        cursor.execute(
            "UPDATE portion_detail SET amount = COALESCE(plate_amount, amount_g) "
            "WHERE amount IS NULL;"
        )
        cursor.execute("ALTER TABLE portion_detail DROP COLUMN plate_amount;")
        cursor.execute("ALTER TABLE portion_detail DROP COLUMN amount_g;")
    cursor.execute("ALTER TABLE portion_detail ALTER COLUMN amount SET NOT NULL;")

    # ---- Uniqueness of a food inside a plate (measurement §4.6.4) ----
    # Prior consolidation of historical duplicates (§4.6.6, §12.7): the constraint
    # cannot be created over data that already violates it. Same merge rule the
    # insert will apply: amounts are summed and the rest of the fields are those
    # of the oldest row of the group.
    # Part of the uniqueness key since 2026-11-07 (§4.6.4), so it must exist before
    # the duplicates below are grouped. Its FK and CHECK are in _ensure_fridge_schema.
    if not _has_column(cursor, "portion_detail", "source_fridge_id"):
        cursor.execute("ALTER TABLE portion_detail ADD COLUMN source_fridge_id INTEGER;")
    # Part of the key since 2026-11-12 (§4.6.4). New column: no row has a value,
    # so no data predates its rule (§12.7). Its CHECKs are added below.
    if not _has_column(cursor, "portion_detail", "ripeness"):
        cursor.execute("ALTER TABLE portion_detail ADD COLUMN ripeness VARCHAR(50);")
    # U2 (study §6.3, 2026-11-12): strictly_weighed became amount_method. Its
    # CHECK is added below, with the ripeness ones.
    _replace_boolean_with_list(
        cursor, "portion_detail", "strictly_weighed", "amount_method", AmountMethod.KITCHEN_SCALE.value
    )

    _DUPLICATE_PORTION_GROUPS = """
        WITH dup AS (
            SELECT
                min(id) AS keep_id,
                array_agg(id) AS ids,
                sum(amount) AS total_amount
            FROM portion_detail
            WHERE plate_id IS NOT NULL
            GROUP BY plate_id, catalog_id, manual_intake_id, cooking, conservation, final_state, is_cooked_weight,
                     source_fridge_id, ripeness
            HAVING count(*) > 1
        )
    """
    cursor.execute(
        _DUPLICATE_PORTION_GROUPS
        + """
        UPDATE portion_detail pd
        SET amount = dup.total_amount
        FROM dup
        WHERE pd.id = dup.keep_id;
        """
    )
    cursor.execute(
        _DUPLICATE_PORTION_GROUPS
        + """
        DELETE FROM portion_detail pd
        USING dup
        WHERE pd.id = ANY(dup.ids) AND pd.id <> dup.keep_id;
        """
    )

    # PARTIAL unique index, not a table constraint: plate_id is NULL in recipe
    # and fridge portions, and with NULLS NOT DISTINCT those nulls would be
    # considered equal to each other, so the same food with the same preparation
    # in two different recipes would clash as a false duplicate. Uniqueness is
    # inside the plate (§4.6.4). is_cooked_weight is part of the key since
    # 2026-09-23: the same grams weighed raw and weighed cooked are different
    # amounts of food, so they are separate rows. source_fridge_id is part of it
    # since 2026-11-07: what was taken from a container goes back to it when the
    # planned meal is deleted, so it is never merged with the same food from
    # elsewhere (measurement §4.8.6). ripeness is part of it since 2026-11-12: the
    # same fruit at two ripeness levels is what the field compares (study §6.3).
    # The new index is created before the older ones are dropped, so the plate is
    # never left without its key. Each older index is dropped, otherwise it would
    # keep rejecting the pairs the new key allows.
    _create_unique_index_once(
        cursor,
        "uq_portion_detail_plate_origin_preparation_ripeness",
        "ON portion_detail (plate_id, catalog_id, manual_intake_id, cooking, conservation, final_state, "
        "is_cooked_weight, source_fridge_id, ripeness) NULLS NOT DISTINCT WHERE plate_id IS NOT NULL",
    )
    for old_index in (
        "uq_portion_detail_plate_origin_preparation",
        "uq_portion_detail_plate_origin_preparation_cooked",
        "uq_portion_detail_plate_origin_preparation_source",
    ):
        if _index_exists(cursor, old_index):
            cursor.execute(sql.SQL("DROP INDEX {};").format(sql.Identifier(old_index)))

    # ---- T1.3: amount range CHECK, after the consolidation above ----
    # NaN and Infinity are rejected by this same CHECK: in PostgreSQL NaN is
    # greater than any value in real, so NaN <= 100000 is false, and Infinity is
    # not finite either. No separate amount <> 'NaN'::real is needed.
    if not _constraint_exists(cursor, "portion_detail", "ck_portion_detail_amount_range"):
        cursor.execute(
            "ALTER TABLE portion_detail ADD CONSTRAINT ck_portion_detail_amount_range "
            "CHECK (amount > 0 AND amount <= 100000);"
        )

    # ---- T1.6: canonical constraint names (§11.6, finding 17) ----
    # The audit list predates the plates work and finding 2, so the rule is
    # derived from the live schema by reading each constraint definition instead
    # of trusting that list. Constraints whose name does not start with
    # portion_detail_ (those born with the plates work or created by T1.3/T1.4)
    # are already canonical and never enter the loop.
    _PORTION_DETAIL_CONSTRAINT_RULES = (
        ("num_nonnulls(catalog_id, manual_intake_id)", "ck_portion_detail_single_origin"),
        ("num_nonnulls(intake_event_id, fridge_id, recipe_id)", "ck_portion_detail_single_destination"),
        ("offset_minutes IS NULL", "ck_portion_detail_offset_only_for_event"),
    )
    _PORTION_DETAIL_FK_RENAMES = {
        "portion_detail_catalog_id_fkey": "fk_portion_detail_catalog_id_catalog",
        "portion_detail_manual_intake_id_fkey": "fk_portion_detail_manual_intake_id_manual_intake",
        "portion_detail_intake_event_id_fkey": "fk_portion_detail_intake_event_id_intake_event",
        "portion_detail_recipe_id_fkey": "fk_portion_detail_recipe_id_recipe",
        "portion_detail_fridge_id_fkey": "fk_portion_detail_fridge_id_fridge",
        "portion_detail_pkey": "pk_portion_detail",
    }
    cursor.execute(
        """
        SELECT conname, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE conrelid = 'public.portion_detail'::regclass
          AND (conname LIKE 'portion\\_detail\\_%' ESCAPE '\\');
        """
    )
    for row in cursor.fetchall() or []:
        old_name = row["conname"]
        definition = row["definition"] or ""
        new_name = _PORTION_DETAIL_FK_RENAMES.get(old_name)
        if new_name is None:
            for needle, candidate in _PORTION_DETAIL_CONSTRAINT_RULES:
                if needle in definition:
                    new_name = candidate
                    break
        if not new_name:
            # Renaming blindly a rule that has not been identified is worse than
            # leaving it: register it and move on.
            logger.warning(
                "portion_detail: constraint %s does not match any rename rule; "
                "left as is. definition=%s",
                old_name,
                definition,
            )
            continue
        if _constraint_exists(cursor, "portion_detail", new_name):
            continue
        cursor.execute(
            sql.SQL("ALTER TABLE portion_detail RENAME CONSTRAINT {} TO {};").format(
                sql.Identifier(old_name), sql.Identifier(new_name)
            )
        )

    # ---- T1.7: FK indexes (finding 18) ----
    # The four are needed: intake_event_id filters the two list reads and is the
    # target of the event ON DELETE CASCADE; recipe_id filters recipe reads;
    # catalog_id and manual_intake_id are checked by RESTRICT on every food
    # delete, and the partial unique index does not serve them because plate_id
    # comes first.
    for column in ("intake_event_id", "recipe_id", "catalog_id", "manual_intake_id"):
        cursor.execute(
            sql.SQL("CREATE INDEX IF NOT EXISTS {} ON portion_detail ({});").format(
                sql.Identifier(f"idx_portion_detail_{column}"), sql.Identifier(column)
            )
        )
    # Redundant with uq_portion_detail_plate_origin_preparation_cooked, whose first
    # column is plate_id: same prefix, same use (§11.7). The index is created
    # earlier in this same hook and dropped here.
    cursor.execute("DROP INDEX IF EXISTS idx_portion_detail_plate_id;")

    # ---- Preparation fields as closed sets (H12, decision 2026-09-25) ----
    # Blocking pre-check (feedback 12: fail, never correct). The values come from
    # the code enums, not from a request (sql_in_list, §11.9).
    for column, enum_cls in (
        ("cooking", CookingMethod),
        ("conservation", ConservationMethod),
        ("final_state", FoodPhysicalState),
    ):
        name = f"ck_portion_detail_{column}"
        values = sql_in_list(enum_cls)
        cursor.execute(
            sql.SQL(
                "SELECT count(*) AS bad FROM portion_detail "
                "WHERE {column} IS NOT NULL AND {column} NOT IN (" + values + ");"
            ).format(column=sql.Identifier(column))
        )
        if cursor.fetchone()["bad"]:
            raise RuntimeError(
                f"portion_detail.{column} has values outside {enum_cls.__name__}; "
                f"{name} cannot be created (code_conventions.md 12.7)."
            )
        cursor.execute(
            sql.SQL("ALTER TABLE portion_detail DROP CONSTRAINT IF EXISTS {};").format(
                sql.Identifier(name)
            )
        )
        cursor.execute(
            sql.SQL(
                "ALTER TABLE portion_detail ADD CONSTRAINT {} "
                "CHECK ({column} IS NULL OR {column} IN (" + values + "));"
            ).format(sql.Identifier(name), column=sql.Identifier(column))
        )

    # ---- Ripeness of a fruit (study §6.3, 2026-11-12) ----
    # Checked before altering (§12.2): an up-to-date database takes no lock here.
    # The CHECK is regenerated only if Ripeness gains a value (§4.4).
    if _check_lacks_values(cursor, "portion_detail", "ck_portion_detail_ripeness", [r.value for r in Ripeness]):
        cursor.execute("ALTER TABLE portion_detail DROP CONSTRAINT ck_portion_detail_ripeness;")
    if not _constraint_exists(cursor, "portion_detail", "ck_portion_detail_ripeness"):
        cursor.execute(
            "ALTER TABLE portion_detail ADD CONSTRAINT ck_portion_detail_ripeness "
            "CHECK (ripeness IS NULL OR ripeness IN (" + sql_in_list(Ripeness) + "));"
        )
    # ---- How the amount was obtained (U2, study §6.3, 2026-11-12) ----
    if _check_lacks_values(
        cursor, "portion_detail", "ck_portion_detail_amount_method", [m.value for m in AmountMethod]
    ):
        cursor.execute("ALTER TABLE portion_detail DROP CONSTRAINT ck_portion_detail_amount_method;")
    if not _constraint_exists(cursor, "portion_detail", "ck_portion_detail_amount_method"):
        cursor.execute(
            "ALTER TABLE portion_detail ADD CONSTRAINT ck_portion_detail_amount_method "
            "CHECK (amount_method IS NULL OR amount_method IN (" + sql_in_list(AmountMethod) + "));"
        )
    if not _constraint_exists(cursor, "portion_detail", "ck_portion_detail_ripeness_event"):
        cursor.execute(
            "ALTER TABLE portion_detail ADD CONSTRAINT ck_portion_detail_ripeness_event "
            "CHECK (ripeness IS NULL OR intake_event_id IS NOT NULL);"
        )
    # ---- Exact time of the offset (measurement §4.5.1, decision 2026-11-15) ----
    # NULL in every existing row: they were all written in minutes.
    cursor.execute("ALTER TABLE intake_plate ADD COLUMN IF NOT EXISTS eaten_at TIMESTAMPTZ;")
    # ---- Fraction eaten of each plate (study §6.3, decision 2026-11-17) ----
    # NULL in every existing row: the fraction of past confirms was not kept.
    cursor.execute("ALTER TABLE intake_plate ADD COLUMN IF NOT EXISTS eaten_fraction REAL;")
    if not _constraint_exists(cursor, "intake_plate", "ck_intake_plate_eaten_fraction"):
        cursor.execute(
            "ALTER TABLE intake_plate ADD CONSTRAINT ck_intake_plate_eaten_fraction "
            "CHECK (eaten_fraction IS NULL OR (eaten_fraction > 0 AND eaten_fraction <= 1));"
        )
    # ---- How a fraction was obtained (study §6.3, decision 2026-11-21) ----
    # NULL in every existing row: how past fractions were obtained is unknown.
    cursor.execute("ALTER TABLE intake_plate ADD COLUMN IF NOT EXISTS eaten_fraction_method VARCHAR(50);")
    if not _constraint_exists(cursor, "intake_plate", "ck_intake_plate_eaten_fraction_method"):
        cursor.execute(
            "ALTER TABLE intake_plate ADD CONSTRAINT ck_intake_plate_eaten_fraction_method "
            "CHECK (eaten_fraction_method IS NULL OR eaten_fraction_method IN (" + sql_in_list(FractionMethod) + "));"
        )
    cursor.execute("ALTER TABLE portion_detail ADD COLUMN IF NOT EXISTS split_method VARCHAR(50);")
    if not _constraint_exists(cursor, "portion_detail", "ck_portion_detail_split_method"):
        cursor.execute(
            "ALTER TABLE portion_detail ADD CONSTRAINT ck_portion_detail_split_method "
            "CHECK (split_method IS NULL OR split_method IN (" + sql_in_list(FractionMethod) + "));"
        )
    cursor.execute("ALTER TABLE portion_detail ADD COLUMN IF NOT EXISTS eaten_at TIMESTAMPTZ;")
    if not _constraint_exists(cursor, "portion_detail", "ck_portion_detail_eaten_at_only_for_event"):
        cursor.execute(
            "ALTER TABLE portion_detail ADD CONSTRAINT ck_portion_detail_eaten_at_only_for_event "
            "CHECK (eaten_at IS NULL OR intake_event_id IS NOT NULL);"
        )
