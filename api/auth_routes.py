"""Signing in and out, changing passwords, and the demo account switcher."""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from api import session
from finder import auth, db
from finder.config import optional, require

router = APIRouter(prefix="/api")

# The demo switcher signs in with SEED_PASSWORD through the same sign_in() as the
# form, so the password check and switched-off users still apply. It is off unless
# DEMO_SWITCHER is set: with it on, anyone who can open the app can become the
# admin, so it is only for the sample data on your own laptop.
DEMO_ON = optional("DEMO_SWITCHER").lower() in {"1", "true", "on", "yes"}
DEMO_ACCOUNTS = [
    {"login": "1262241783", "name": "Rohan Deogaonkar", "role": "student",
     "shows": "CCTV attendance project waiting for review, and the Smart Water Tank project"},
    {"login": "1262241766", "name": "Krishna Bhand", "role": "student",
     "shows": "No project this year yet: open a submission link to submit one"},
    {"login": "srao@mitwpu.edu.in", "name": "Prof. S. Rao", "role": "faculty",
     "shows": "ML-PBL submission link for TY ECE Div B; reviews Rohan's CCTV attendance project"},
    {"login": "riyer@mitwpu.edu.in", "name": "Prof. R. Iyer", "role": "faculty",
     "shows": "Rohan's Smart Water Tank project, approved, students not graded yet"},
    {"login": "nshaikh@mitwpu.edu.in", "name": "Dr. N. Shaikh", "role": "admin",
     "shows": "PBL coordinator: people, subjects, whole department"},
]


def account_json(account: db.Account) -> dict:
    return {
        "user_id": account.user_id,
        "role": account.role,
        "is_admin": account.is_admin,
        "name": account.name,
        "login": account.login,
        "prn": account.prn,
        "must_change_password": account.must_change_password,
    }


class SignInBody(BaseModel):
    login: str = Field(max_length=120)
    password: str = Field(max_length=72)


def finish_sign_in(result: auth.SignIn, request: Request, response: Response) -> dict:
    if result.status == "ok":
        session.start(response, request, result.account)
        return account_json(result.account)
    messages = {
        "disabled": "This account is switched off. Ask the PBL coordinator.",
        "wrong": "That PRN or email and password don't match.",
    }
    raise HTTPException(401, messages[result.status])


@router.post("/sign-in")
def sign_in(body: SignInBody, request: Request, response: Response) -> dict:
    if not body.login.strip() or not body.password:
        raise HTTPException(422, "Enter your PRN or email and your password.")
    return finish_sign_in(auth.sign_in(session.pool(), body.login, body.password), request, response)


@router.post("/sign-out")
def sign_out(request: Request, response: Response) -> dict:
    session.end(request, response)
    return {}


@router.get("/me")
def me(request: Request) -> dict:
    account = session.current(request)
    return {"account": account_json(account) if account else None}


class PasswordBody(BaseModel):
    current: str = Field(max_length=72)
    new: str = Field(min_length=8, max_length=72)


@router.post("/password")
def change_password(body: PasswordBody, request: Request, account: db.Account = session.anyone) -> dict:
    changed = auth.change_password(session.pool(), account, body.current, body.new)
    if changed is None:
        raise HTTPException(400, "The current password is wrong.")
    # This session carries the change time as its sign-in time, so it stays valid
    # while every other one ends.
    session.replace(request, changed)
    return account_json(changed)


@router.get("/demo")
def demo() -> dict:
    return {"enabled": DEMO_ON, "accounts": DEMO_ACCOUNTS if DEMO_ON else []}


class DemoBody(BaseModel):
    login: str


@router.post("/demo/sign-in")
def demo_sign_in(body: DemoBody, request: Request, response: Response) -> dict:
    if not DEMO_ON or body.login not in {a["login"] for a in DEMO_ACCOUNTS}:
        raise HTTPException(404, "The demo switcher is off.")
    result = auth.sign_in(session.pool(), body.login, require("SEED_PASSWORD"))
    if result.status == "wrong":
        raise HTTPException(401, "SEED_PASSWORD no longer works for this account: its password was "
                                 "changed or reset. Rebuild the sample data to get it back.")
    return finish_sign_in(result, request, response)
