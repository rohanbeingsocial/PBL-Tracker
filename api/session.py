"""Who is signed in, for each browser.

After sign_in() succeeds the account is kept here, in the server's memory, under a
random token. The browser only gets that token, in an HttpOnly cookie that scripts
can't read and that is never sent with requests from other sites (SameSite=Strict).
Restarting the server signs everyone out.
"""
import secrets
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import psycopg
from fastapi import Depends, HTTPException, Request, Response
from psycopg_pool import ConnectionPool

from finder import db
from finder.config import require

COOKIE = "pbl_session"
IDLE_MINUTES = 30


@dataclass
class _Entry:
    account: db.Account
    last_seen: float


_sessions: dict[str, _Entry] = {}
_lock = threading.Lock()
_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    with _lock:
        if _pool is None:
            _pool = db.make_pool(require("DATABASE_URL"))
        return _pool


def start(response: Response, request: Request, account: db.Account) -> None:
    """Remember a fresh sign-in. Any session this browser already had is dropped first."""
    end(request, response)
    token = secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = _Entry(account, time.monotonic())
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/",
                        secure=request.url.scheme == "https")


def replace(request: Request, account: db.Account) -> None:
    """Same session, updated account (after a password change)."""
    token = request.cookies.get(COOKIE)
    with _lock:
        if token in _sessions:
            _sessions[token].account = account


def end(request: Request, response: Response | None = None) -> None:
    token = request.cookies.get(COOKIE)
    with _lock:
        _sessions.pop(token, None)
    if response is not None:
        response.delete_cookie(COOKIE, path="/")


def current(request: Request) -> db.Account | None:
    """The signed-in account, or None. A session idle for IDLE_MINUTES ends, for lab
    computers that get left open."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    now = time.monotonic()
    with _lock:
        entry = _sessions.get(token)
        if entry is None:
            return None
        if now - entry.last_seen > IDLE_MINUTES * 60:
            del _sessions[token]
            return None
        entry.last_seen = now
        return entry.account


def signed_in(request: Request) -> db.Account:
    account = current(request)
    if account is None:
        raise HTTPException(401, "Please sign in.")
    if account.must_change_password:
        # Until they choose their own password, a temporary one opens nothing else.
        if request.url.path not in ("/api/me", "/api/password", "/api/sign-out"):
            raise HTTPException(403, "Choose a new password first.")
    return account


def _student(account: db.Account = Depends(signed_in)) -> db.Account:
    if account.role != "student":
        raise HTTPException(403, "Only students can do this.")
    return account


def _faculty(account: db.Account = Depends(signed_in)) -> db.Account:
    if account.role != "faculty":
        raise HTTPException(403, "Only faculty can open this.")
    return account


def _admin(account: db.Account = Depends(signed_in)) -> db.Account:
    if not account.is_admin:
        raise HTTPException(403, "Only the PBL coordinator can open this.")
    return account


student = Depends(_student)
faculty = Depends(_faculty)
admin = Depends(_admin)
anyone = Depends(signed_in)


@contextmanager
def transaction(account: db.Account | None) -> Iterator[psycopg.Connection]:
    """One transaction for this request (finder.db)."""
    with db.transaction(pool(), account) as conn:
        yield conn
