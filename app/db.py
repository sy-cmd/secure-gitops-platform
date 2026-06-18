"""Database access.

Credentials are read from the environment at call time — NOT baked into the
image or a manifest. In Phase 4, Vault's agent injector writes short-lived
Postgres credentials into the pod's environment, and this module picks them up
with zero code changes. That separation is the whole point.
"""
import os

import psycopg


def _conninfo() -> str:
    """Build a libpq conninfo string from discrete env vars.

    Discrete vars (PGUSER/PGPASSWORD/...) map cleanly onto what Vault's
    database secrets engine hands out. Falls back to DATABASE_URL for local dev.
    """
    if url := os.getenv("DATABASE_URL"):
        return url
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    user = os.getenv("PGUSER", "postgres")
    password = os.getenv("PGPASSWORD", "postgres")
    dbname = os.getenv("PGDATABASE", "appdb")
    return f"host={host} port={port} user={user} password={password} dbname={dbname}"


def ping() -> bool:
    """Return True if the database answers a trivial query."""
    try:
        with psycopg.connect(_conninfo(), connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True
    except Exception:
        return False


def list_items() -> list[dict]:
    """Return rows from the items table, creating it on first use."""
    with psycopg.connect(_conninfo(), connect_timeout=3) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS items "
                "(id SERIAL PRIMARY KEY, name TEXT NOT NULL)"
            )
            cur.execute("SELECT id, name FROM items ORDER BY id")
            rows = cur.fetchall()
            conn.commit()
    return [{"id": r[0], "name": r[1]} for r in rows]
