import psycopg
from psycopg.rows import dict_row

from DayBetes_food.config import DATABASE_URL, MIGRATIONS_DATABASE_URL


def get_connection():
    # DATABASE_URL ya se valida una sola vez, al arrancar, en config.py.
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def get_migrations_connection():
    """Bootstrap/DDL only (code_conventions.md 12.6). No usar desde routes/services/queries."""
    if not MIGRATIONS_DATABASE_URL:
        raise RuntimeError("MIGRATIONS_DATABASE_URL is not configured")
    return psycopg.connect(MIGRATIONS_DATABASE_URL, row_factory=dict_row)

