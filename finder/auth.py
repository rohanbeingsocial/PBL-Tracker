"""Signing in and changing passwords. The checks themselves are SQL functions in
sql/03_functions.sql; this module calls them and turns the answer into an Account."""
from dataclasses import dataclass, replace

from psycopg_pool import ConnectionPool

from finder.db import Account, transaction


@dataclass(frozen=True)
class SignIn:
    status: str                        # 'ok', 'wrong' or 'disabled'
    account: Account | None = None     # only for 'ok'


def sign_in(pool: ConnectionPool, login: str, password: str) -> SignIn:
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM pbl.sign_in(%s, %s)", (login, password)).fetchone()
    if row["status"] != "ok":
        return SignIn(row["status"])
    return SignIn("ok", Account(
        user_id=row["user_id"],
        role=row["role"],
        is_admin=row["is_admin"],
        name=row["name"],
        login=row["login"],
        prn=row["prn"],
        signed_in_at=row["signed_in_at"],
        must_change_password=row["must_change_password"],
    ))


def change_password(pool: ConnectionPool, account: Account, current: str, new: str) -> Account | None:
    """The same account with the change time as its new sign-in time, so this session
    stays valid while every other one ends. None if `current` was wrong."""
    with transaction(pool, account) as conn:
        changed_at = conn.execute("SELECT pbl.change_password(%s, %s, %s) AS changed_at",
                                  (account.user_id, current, new)).fetchone()["changed_at"]
    if changed_at is None:
        return None
    return replace(account, signed_in_at=changed_at, must_change_password=False)
