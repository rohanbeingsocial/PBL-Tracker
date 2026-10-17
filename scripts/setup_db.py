"""Builds the database: schema, tables, indexes, functions, triggers, views, the app's
login and reference data, in one transaction. If any file fails, nothing is kept.

    python -m scripts.setup_db            first time
    python -m scripts.setup_db --reset    drop the pbl schema and build it again (deletes all data)

Uses ADMIN_DATABASE_URL and PBL_APP_PASSWORD from .env.
"""
import argparse
import sys
from pathlib import Path

import psycopg
from psycopg import sql

from finder.config import require

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
FILES = [
    "01_tables.sql",
    "02_indexes.sql",
    "03_functions.sql",
    "04_triggers.sql",
    "05_views.sql",
    "06_security.sql",
    "07_reference_data.sql",
]


def set_app_password(conn: psycopg.Connection) -> None:
    password = require("PBL_APP_PASSWORD")
    if len(password) < 12:
        sys.exit("PBL_APP_PASSWORD must be at least 12 characters.")
    # Hash it here, the way psql's \password does, so the plain password is never
    # sent to the server and can't end up in its logs.
    hashed = conn.pgconn.encrypt_password(password.encode(), b"pbl_app", b"scram-sha-256")
    conn.execute(sql.SQL("ALTER ROLE pbl_app PASSWORD {}").format(sql.Literal(hashed.decode())))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="drop the pbl schema first (deletes all data)")
    parser.add_argument("--yes", action="store_true", help="don't ask before --reset")
    args = parser.parse_args()

    if args.reset and not args.yes:
        answer = input("This deletes every user, project and mark in the pbl schema. Type 'reset' to go on: ")
        if answer.strip() != "reset":
            sys.exit("Nothing changed.")

    with psycopg.connect(require("ADMIN_DATABASE_URL"), connect_timeout=10) as conn:
        if args.reset:
            conn.execute("DROP SCHEMA IF EXISTS pbl CASCADE")
        try:
            for name in FILES:
                print(f"  {name}")
                conn.execute((SQL_DIR / name).read_text(encoding="utf-8"))
        except psycopg.errors.DuplicateSchema:
            sys.exit("The pbl schema already exists. Run with --reset to rebuild it (this deletes its data).")
        set_app_password(conn)
    print("Database ready. Next: python -m scripts.load_data")


if __name__ == "__main__":
    main()
