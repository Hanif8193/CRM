"""
PostgreSQL connection pool.

Usage:
    from database.connection import get_conn, is_db_available

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
"""

import os
from contextlib import contextmanager
from typing import Generator

try:
    import psycopg2
    from psycopg2 import pool as pg_pool
    _PSYCOPG2_AVAILABLE = True
except ImportError:
    _PSYCOPG2_AVAILABLE = False

# ── Module-level pool (initialised by init_db()) ──────────────────────────────

_pool: "pg_pool.ThreadedConnectionPool | None" = None

# ── Public API ────────────────────────────────────────────────────────────────

def init_db() -> None:
    """
    Open the connection pool.  Call once at application startup.
    Reads DATABASE_URL from the environment (falls back to localhost defaults).
    Silently skips if psycopg2 is not installed or the DB is unreachable.
    """
    global _pool
    if not _PSYCOPG2_AVAILABLE:
        print("[DB] psycopg2 not installed — running without database")
        return

    dsn = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/crm_db",
    )
    try:
        _pool = pg_pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=dsn)
        print("[DB] connection pool ready")
    except Exception as exc:
        print(f"[DB] could not connect — running without database: {exc}")
        _pool = None


def close_db() -> None:
    """Close all connections in the pool.  Call at application shutdown."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        print("[DB] connection pool closed")


def is_db_available() -> bool:
    """Return True when the pool is open and healthy."""
    return _pool is not None


@contextmanager
def get_conn() -> Generator:
    """
    Context manager that checks out a connection from the pool and returns it
    when the block exits.  Rolls back automatically on exception.

    Raises RuntimeError when the pool is not available so callers can decide
    whether to skip DB work or surface the error.
    """
    if _pool is None:
        raise RuntimeError("Database pool is not available")

    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)
