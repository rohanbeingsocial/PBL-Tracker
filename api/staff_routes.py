"""Faculty and admin pages: review submissions and give marks, people, subjects.

A faculty member can only decide on and mark the projects assigned to them; every
UPDATE below has faculty_id = the signed-in user in its WHERE clause. The marks
range and the order of status changes are checked by the database triggers.
"""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api import session
from finder import db
from finder.embeddings import embed, project_text

router = APIRouter(prefix="/api")


# Review submissions and give marks ---------------------------------------------------

@router.get("/review")
def review(account: db.Account = session.faculty) -> dict:
    with session.transaction(account) as conn:
        waiting = conn.execute(
            """SELECT c.project_id, c.title, c.subject, c.members, c.created_at,
                      q.closest_title, q.closest_year, q.similarity, q.band
               FROM pbl.review_queue q
               JOIN pbl.project_cards c ON c.project_id = q.project_id
               WHERE q.faculty_id = %s
               ORDER BY q.created_at""", (account.user_id,)).fetchall()
        decided = conn.execute(
            """SELECT c.project_id, c.title, c.subject, c.academic_year, c.members, c.status, c.decided_at,
                      p.marks::float8, s.max_marks::float8
               FROM pbl.project_cards c
               JOIN pbl.projects p ON p.project_id = c.project_id
               JOIN pbl.subjects s ON s.subject_id = p.subject_id
               WHERE c.faculty_id = %s AND c.status <> 'submitted'
               ORDER BY c.status, p.marks IS NOT NULL, c.academic_year DESC, c.title""",
            (account.user_id,)).fetchall()
    return {"waiting": waiting, "decided": decided}


class DecisionBody(BaseModel):
    status: Literal["approved", "rejected"]
    note: str = Field("", max_length=1000)
    marks: float | None = Field(None, ge=0)      # can be given with the approval, or later


@router.post("/projects/{project_id}/decision")
def decide(project_id: int, body: DecisionBody, account: db.Account = session.faculty) -> dict:
    marks = body.marks if body.status == "approved" else None
    with session.transaction(account) as conn:
        changed = conn.execute(
            """UPDATE pbl.projects SET status = %s, review_note = nullif(btrim(%s), ''), marks = %s
               WHERE project_id = %s AND faculty_id = %s AND status = 'submitted'""",
            (body.status, body.note, marks, project_id, account.user_id)).rowcount
    if changed == 0:
        raise HTTPException(409, "Nothing changed. It isn't one of your projects, or it was decided already.")
    return {"status": body.status}


class MarksBody(BaseModel):
    marks: float | None = Field(None, ge=0)     # None clears the marks


@router.put("/marks/{project_id}")
def save_marks(project_id: int, body: MarksBody, account: db.Account = session.faculty) -> dict:
    with session.transaction(account) as conn:
        changed = conn.execute(
            "UPDATE pbl.projects SET marks = %s WHERE project_id = %s AND faculty_id = %s",
            (body.marks, project_id, account.user_id)).rowcount
    if changed == 0:
        raise HTTPException(404, "This isn't one of your projects.")
    return {"marks": body.marks}


# People -----------------------------------------------------------------------------

@router.get("/people")
def people(account: db.Account = session.admin) -> dict:
    with session.transaction(account) as conn:
        rows = conn.execute(
            """SELECT u.user_id, u.name, coalesce(u.prn, u.email) AS login, u.email, u.role, u.is_admin,
                      u.is_active, u.must_change_password,
                      (SELECT count(*) FROM pbl.project_members pm WHERE pm.user_id = u.user_id)
                    + (SELECT count(*) FROM pbl.projects p WHERE p.faculty_id = u.user_id) AS projects
               FROM pbl.users u ORDER BY u.role = 'student', u.name""").fetchall()
    return {"people": rows, "me": account.user_id}


class PersonAction(BaseModel):
    action: Literal["reset", "switch_off", "switch_on", "make_admin", "remove_admin"]


@router.post("/people/{user_id}")
def change_person(user_id: int, body: PersonAction, account: db.Account = session.admin) -> dict:
    if user_id == account.user_id and body.action in ("switch_off", "remove_admin"):
        raise HTTPException(422, "You can't switch off your own account or take away your own admin rights.")
    statements = {
        "reset": "SELECT pbl.reset_password(%s) AS temporary",
        "switch_off": "UPDATE pbl.users SET is_active = false WHERE user_id = %s",
        "switch_on": "UPDATE pbl.users SET is_active = true WHERE user_id = %s",
        "make_admin": "UPDATE pbl.users SET is_admin = true WHERE user_id = %s",
        "remove_admin": "UPDATE pbl.users SET is_admin = false WHERE user_id = %s",
    }
    with session.transaction(account) as conn:
        cur = conn.execute(statements[body.action], (user_id,))
        row = cur.fetchone() if cur.description else None
    return {"temporary": row["temporary"] if row else None}


class NewPerson(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(max_length=120)
    prn: str = Field("", max_length=10)
    role: Literal["student", "faculty"]
    is_admin: bool = False


@router.post("/people")
def add_person(body: NewPerson, account: db.Account = session.admin) -> dict:
    if not body.email.strip().lower().endswith("@mitwpu.edu.in"):
        raise HTTPException(422, "Use the person's college email, ending in @mitwpu.edu.in.")
    with session.transaction(account) as conn:
        temporary = conn.execute(
            "SELECT pbl.create_user(%s, %s, %s, %s, %s) AS temporary",
            (body.name, body.email, body.prn if body.role == "student" else "", body.role,
             body.is_admin and body.role == "faculty")).fetchone()["temporary"]
    return {"temporary": temporary}


# Subjects ---------------------------------------------------------------------------

@router.get("/subjects")
def subjects(account: db.Account = session.admin) -> dict:
    with session.transaction(account) as conn:
        rows = conn.execute(
            """SELECT s.subject_id, s.code, s.name, s.max_marks::float8,
                      count(p.project_id) AS projects,
                      count(p.marks) AS marked
               FROM pbl.subjects s LEFT JOIN pbl.projects p ON p.subject_id = s.subject_id
               GROUP BY s.subject_id ORDER BY s.code""").fetchall()
    return {"subjects": rows}


class SubjectBody(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=100)
    max_marks: float = Field(gt=0, le=1000)


@router.post("/subjects")
def add_subject(body: SubjectBody, account: db.Account = session.admin) -> dict:
    with session.transaction(account) as conn:
        subject_id = conn.execute(
            "INSERT INTO pbl.subjects (code, name, max_marks) VALUES (upper(btrim(%s)), btrim(%s), %s) RETURNING subject_id",
            (body.code, body.name, body.max_marks)).fetchone()["subject_id"]
    return {"subject_id": subject_id}


@router.put("/subjects/{subject_id}")
def edit_subject(subject_id: int, body: SubjectBody, account: db.Account = session.admin) -> dict:
    with session.transaction(account) as conn:
        highest = conn.execute("SELECT max(marks) AS m FROM pbl.projects WHERE subject_id = %s",
                               (subject_id,)).fetchone()["m"]
        if highest is not None and body.max_marks < float(highest):
            raise HTTPException(422, f"A project in this subject already has {float(highest):g} marks. "
                                     "The maximum can't go below that.")
        changed = conn.execute(
            "UPDATE pbl.subjects SET code = upper(btrim(%s)), name = btrim(%s), max_marks = %s WHERE subject_id = %s",
            (body.code, body.name, body.max_marks, subject_id)).rowcount
    if changed == 0:
        raise HTTPException(404, "No such subject.")
    return {}


# Embeddings -------------------------------------------------------------------------

@router.post("/embeddings")
def create_embeddings(account: db.Account = session.admin) -> dict:
    with session.transaction(account) as conn:
        missing = conn.execute(
            "SELECT project_id, title, abstract FROM pbl.projects WHERE embedding IS NULL ORDER BY project_id").fetchall()
    if not missing:
        return {"created": 0}
    vectors = embed([project_text(m["title"], m["abstract"]) for m in missing])
    with session.transaction(account) as conn, conn.cursor() as cur:
        cur.executemany("UPDATE pbl.projects SET embedding = %s WHERE project_id = %s AND embedding IS NULL",
                        [(v, m["project_id"]) for m, v in zip(missing, vectors, strict=True)])
    return {"created": len(missing)}
