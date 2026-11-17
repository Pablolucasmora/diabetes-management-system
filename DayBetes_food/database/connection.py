import logging
import threading

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from DayBetes_food.config import (
    DATABASE_URL,
    DB_POOL_MAX_SIZE,
    DB_POOL_MIN_SIZE,
    DB_POOL_TIMEOUT_SECONDS,
    MIGRATIONS_DATABASE_URL,
)

logger = logging.getLogger(__name__)

# One pool per process for the runtime identity (code_conventions.md §2.1):
# connections are reused instead of opened for each unit of work. It is opened
# on first use and closed when the app stops.
_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                pool = ConnectionPool(
                    # DATABASE_URL is validated once, at startup, in config.py.
                    DATABASE_URL,
                    min_size=DB_POOL_MIN_SIZE,
                    max_size=DB_POOL_MAX_SIZE,
                    timeout=DB_POOL_TIMEOUT_SECONDS,
                    kwargs={"row_factory": dict_row},
                    # A connection the server closed (restart, idle timeout) is
                    # detected before it is handed out.
                    check=ConnectionPool.check_connection,
                    open=False,
                    name="daybetes",
                )
                pool.open()
                _pool = pool
    return _pool


def get_connection():
    """A connection of the pool for one unit of work, used as `with get_connection()
    as connection:`. As with a plain psycopg connection, leaving the block commits
    a transaction left open, rolls it back on an exception, and returns the
    connection to the pool instead of closing it."""
    return _get_pool().connection()


def close_pool() -> None:
    """Close the pool when the app stops (lifespan of main.py)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


def get_migrations_connection():
    """Bootstrap/DDL only (code_conventions.md 12.6). Never use it from routes/services/queries."""
    if not MIGRATIONS_DATABASE_URL:
        raise RuntimeError("MIGRATIONS_DATABASE_URL is not configured")
    return psycopg.connect(MIGRATIONS_DATABASE_URL, row_factory=dict_row)
