"""Catalog queries and idempotent DDL helpers shared by the schema bootstrap (code_conventions.md §12.2)."""

from psycopg import sql


def _has_column(cursor, table: str, column: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %(table)s AND column_name = %(column)s;
        """,
        {"table": table, "column": column},
    )
    return cursor.fetchone() is not None


def _replace_boolean_with_list(cursor, table: str, old_column: str, new_column: str, true_value: str) -> None:
    """U1/U2 (study_conventions.md §6.3, 2026-11-12): a yes/no column becomes a
    closed list. Adds `new_column`, copies TRUE as `true_value` and drops the old
    column; FALSE and NULL stay empty, nothing else is inferred. Idempotent: once
    the old column is gone it only checks that the new one exists. Approved
    destructive step (§12.4): the local values were exported before applying it
    (audit/backups/u1_u2_before_2026-11-12.csv); production has its nightly copies.
    The CHECK of the new column is added with the rest of the table's CHECKs."""
    if not _has_column(cursor, table, new_column):
        cursor.execute(
            sql.SQL("ALTER TABLE {} ADD COLUMN {} VARCHAR(50);").format(
                sql.Identifier(table), sql.Identifier(new_column)
            )
        )
    if _has_column(cursor, table, old_column):
        cursor.execute(
            sql.SQL("UPDATE {table} SET {new} = %(value)s WHERE {old} IS TRUE AND {new} IS NULL;").format(
                table=sql.Identifier(table), new=sql.Identifier(new_column), old=sql.Identifier(old_column)
            ),
            {"value": true_value},
        )
        cursor.execute(
            sql.SQL("ALTER TABLE {} DROP COLUMN {};").format(sql.Identifier(table), sql.Identifier(old_column))
        )


def _column_data_type(cursor, table: str, column: str):
    cursor.execute(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_name = %(table)s AND column_name = %(column)s
        LIMIT 1;
        """,
        {"table": table, "column": column},
    )
    row = cursor.fetchone()
    return row["data_type"] if row else None


def _column_default(cursor, table: str, column: str):
    cursor.execute(
        """
        SELECT column_default
        FROM information_schema.columns
        WHERE table_name = %(table)s AND column_name = %(column)s
        LIMIT 1;
        """,
        {"table": table, "column": column},
    )
    row = cursor.fetchone()
    return row["column_default"] if row else None


def _create_index_once(cursor, name: str, definition: str) -> None:
    """Checked first: CREATE INDEX IF NOT EXISTS takes a lock that blocks writes until the
    bootstrap commits, even with nothing to do (§12.2). The arguments are constants."""
    if not _index_exists(cursor, name):
        cursor.execute(f"CREATE INDEX {name} {definition};")


def _create_unique_index_once(cursor, name: str, definition: str) -> None:
    """Same as `_create_index_once`, for a unique index. The arguments are constants."""
    if not _index_exists(cursor, name):
        cursor.execute(f"CREATE UNIQUE INDEX {name} {definition};")


def _index_exists(cursor, name: str) -> bool:
    cursor.execute(
        "SELECT 1 AS ok FROM pg_indexes WHERE schemaname = 'public' AND indexname = %(name)s;",
        {"name": name},
    )
    return cursor.fetchone() is not None


def _check_lacks_values(cursor, table: str, name: str, values) -> bool:
    """Whether the CHECK `name` exists and leaves out a value of its enum: a value
    added to the enum must reach the constraint (§4.4). The values are constants."""
    cursor.execute(
        "SELECT pg_get_constraintdef(oid) AS definition FROM pg_constraint "
        "WHERE conrelid = %(table)s::regclass AND conname = %(name)s;",
        {"table": f"public.{table}", "name": name},
    )
    row = cursor.fetchone()
    if row is None:
        return False
    return any(f"'{value}'" not in row["definition"] for value in values)


def _column_is_nullable(cursor, table: str, column: str) -> bool:
    cursor.execute(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %(table)s AND column_name = %(column)s;",
        {"table": table, "column": column},
    )
    row = cursor.fetchone()
    return row is not None and row["is_nullable"] == "YES"


def _constraint_exists(cursor, table: str, name: str) -> bool:
    cursor.execute(
        "SELECT 1 AS ok FROM pg_constraint "
        "WHERE conrelid = %(table)s::regclass AND conname = %(name)s;",
        {"table": f"public.{table}", "name": name},
    )
    return cursor.fetchone() is not None
