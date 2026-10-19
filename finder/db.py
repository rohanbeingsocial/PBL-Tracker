"""Database access for the app: a small connection pool, the signed-in user, and
one transaction per request."""
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Account:
    """Who is signed in. The web server keeps it in memory (api/session.py); the
    browser only holds a random session token."""
    user_id: int
    role: str                    # 'student' or 'faculty'
    is_admin: bool
    name: str
    login: str                   # PRN for students, email for faculty
    prn: str | None
    signed_in_at: datetime       # database clock, compared with password_changed_at
    must_change_password: bool = False


class SessionEnded(Exception):
    """The user was switched off, or their password changed after this sign-in."""


def make_pool(conninfo: str) -> ConnectionPool:
    return ConnectionPool(
        conninfo,
        min_size=1,
        max_size=4,
        kwargs={
            "autocommit": True,           # transactions are opened explicitly in transaction()
            "row_factory": dict_row,
            "prepare_threshold": None,    # Supabase's transaction pooler can't keep prepared statements
            "application_name": "pbl-tracker",
            "connect_timeout": 10,
        },
        check=ConnectionPool.check_connection,
        open=True,
    )


@contextmanager
def transaction(pool: ConnectionPool, account: Account | None) -> Iterator[psycopg.Connection]:
    """Run one transaction for a request.

    For a signed-in account it first checks that the user is still switched on and
    hasn't had their password changed since signing in (by themselves on another
    computer, or reset by an admin). If either happened, SessionEnded is raised and
    the app signs them out, so the change takes effect on the next click.
    """
    with pool.connection() as conn, conn.transaction():
        if account is not None:
            still_valid = conn.execute(
                """SELECT 1 FROM pbl.users
                   WHERE user_id = %s AND is_active AND password_changed_at <= %s""",
                (account.user_id, account.signed_in_at),
            ).fetchone()
            if still_valid is None:
                raise SessionEnded
        yield conn


def user_message(exc: psycopg.Error) -> str:
    """Text that is safe and useful to show on screen for a database error.

    Rule violations (our trigger messages, CHECK/UNIQUE/foreign key failures, bad
    input, permission denied) are written for people, so they are shown as they are.
    Anything else could leak connection details, so it gets a generic message and
    the real error goes to the log.
    """
    state = exc.sqlstate or ""
    if state.startswith(("22", "23")) or state in ("42501", "P0001"):
        text = exc.diag.message_primary or str(exc)
        if exc.diag.message_hint:
            text = f"{text}. {exc.diag.message_hint}"
        return text
    log.exception("database error")
    return "Could not reach the database or the query failed. Try again in a minute."
