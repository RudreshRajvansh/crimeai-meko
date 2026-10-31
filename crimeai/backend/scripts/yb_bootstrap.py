#!/usr/bin/env python3
"""
Prepare a YugabyteDB cluster for CrimeAI: the application role, its databases and the extensions the
migrations use. Idempotent; run it before `alembic upgrade head`.

  python scripts/yb_bootstrap.py

Reads DATABASE_URL_SYNC for the role, password and database to create, and connects as YugabyteDB's
built-in admin through YB_ADMIN_URL (default: the yugabyte user on the same host). Extra databases, such
as the integration-test database, come from YB_EXTRA_DATABASES (comma separated).
"""
from __future__ import annotations

import os
import sys
import time
from urllib.parse import urlparse, urlunparse

import psycopg2
from psycopg2 import sql

EXTENSIONS = ("vector", "pg_trgm", "uuid-ossp")


def _connect(url: str, attempts: int = 90):
    for attempt in range(1, attempts + 1):
        try:
            conn = psycopg2.connect(url, connect_timeout=5)
            conn.autocommit = True
            return conn
        except psycopg2.OperationalError as exc:
            if attempt == attempts:
                raise
            if attempt % 10 == 1:
                print(f"waiting for YugabyteDB ({exc.__class__.__name__}: {str(exc).strip()[:80]})", flush=True)
            time.sleep(2)
    raise RuntimeError("unreachable")


def _with_db(url: str, database: str) -> str:
    parts = urlparse(url)
    return urlunparse(parts._replace(path=f"/{database}"))


def main() -> int:
    app = urlparse(os.environ["DATABASE_URL_SYNC"])
    role, password, database = app.username, app.password or "", app.path.lstrip("/")
    admin_url = os.environ.get("YB_ADMIN_URL") or urlunparse(
        app._replace(netloc=f"yugabyte:yugabyte@{app.hostname}:{app.port or 5433}", path="/yugabyte")
    )
    superuser = os.environ.get("YB_APP_ROLE_SUPERUSER", "false").lower() == "true"
    databases = [database] + [d.strip() for d in os.environ.get("YB_EXTRA_DATABASES", "").split(",") if d.strip()]

    # Plain connections, not `with conn:` blocks: psycopg2 opens a transaction there even in autocommit mode,
    # and CREATE DATABASE refuses to run inside one.
    admin = _connect(admin_url)
    try:
        cur = admin.cursor()
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        verb = "ALTER" if cur.fetchone() else "CREATE"
        cur.execute(sql.SQL("{} ROLE {} WITH LOGIN {} PASSWORD %s").format(
            sql.SQL(verb), sql.Identifier(role), sql.SQL("SUPERUSER" if superuser else "NOSUPERUSER")), (password,))
        print(f"role {role}: {'created' if verb == 'CREATE' else 'updated'}{' (superuser)' if superuser else ''}")
        for db in databases:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,))
            if not cur.fetchone():
                cur.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(db), sql.Identifier(role)))
                print(f"database {db}: created")
            else:
                cur.execute(sql.SQL("ALTER DATABASE {} OWNER TO {}").format(sql.Identifier(db), sql.Identifier(role)))
                print(f"database {db}: exists")
    finally:
        admin.close()

    for db in databases:
        conn = _connect(_with_db(admin_url, db), attempts=10)
        try:
            cur = conn.cursor()
            for ext in EXTENSIONS:
                cur.execute(sql.SQL("CREATE EXTENSION IF NOT EXISTS {}").format(sql.Identifier(ext)))
            cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = ANY(%s)", (list(EXTENSIONS),))
            print(f"database {db}: extensions " + ", ".join(f"{n} {v}" for n, v in sorted(cur.fetchall())))
        finally:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
