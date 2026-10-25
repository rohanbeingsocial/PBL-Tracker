"""Faculty and admin pages: submission links, reviewing what came in and giving each
student marks, exporting a class's marks, people, subjects.

A faculty member can only see, change and grade their own links and the projects
that came in through them; every query below has faculty_id = the signed-in user in
its WHERE clause. The marks range and the order of status changes are checked by
the database triggers.
"""
import csv
import io
import re
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from api import session
from finder import db
from finder.embeddings import embed, project_text

router = APIRouter(prefix="/api")


# Submission links ---------------------------------------------------------------------

LINK_COLUMNS = """submission_link_id, code, subject, subject_name, academic_year, class_name, purpose,
                  max_marks::float8, is_open, created_at, waiting, approved, rejected, graded, students"""


def own_link(conn, link_id: int, account: db.Account) -> dict:
    link = conn.execute(f"SELECT {LINK_COLUMNS} FROM pbl.link_progress WHERE submission_link_id = %s AND faculty_id = %s",
                        (link_id, account.user_id)).fetchone()
    if link is None:
        raise HTTPException(404, "This isn't one of your submission links.")
    return link


@router.get("/links")
def links(account: db.Account = session.faculty) -> dict:
    with session.transaction(account) as conn:
        rows = conn.execute(
            f"""SELECT {LINK_COLUMNS} FROM pbl.link_progress WHERE faculty_id = %s
                ORDER BY academic_year DESC, is_open DESC, subject, class_name, purpose""",
            (account.user_id,)).fetchall()
    return {"links": rows, "waiting": sum(r["waiting"] for r in rows)}


class LinkBody(BaseModel):
    subject_id: int
    class_name: str = Field(min_length=2, max_length=80)
    purpose: str = Field(min_length=2, max_length=100)
    max_marks: float | None = Field(None, gt=0, le=1000)    # empty: the subject's usual total


@router.post("/links")
def add_link(body: LinkBody, account: db.Account = session.faculty) -> dict:
    with session.transaction(account) as conn:
        link = conn.execute(
            """INSERT INTO pbl.submission_links (faculty_id, subject_id, academic_year, class_name, purpose, max_marks)
               VALUES (%s, %s, pbl.current_academic_year(), btrim(%s), btrim(%s), %s)
               RETURNING submission_link_id, code""",
            (account.user_id, body.subject_id, body.class_name, body.purpose, body.max_marks)).fetchone()
    return link


class LinkChange(BaseModel):
    class_name: str = Field(min_length=2, max_length=80)
    purpose: str = Field(min_length=2, max_length=100)
    max_marks: float = Field(gt=0, le=1000)
    is_open: bool


@router.put("/links/{link_id}")
def change_link(link_id: int, body: LinkChange, account: db.Account = session.faculty) -> dict:
    with session.transaction(account) as conn:
        changed = conn.execute(
            """UPDATE pbl.submission_links SET class_name = btrim(%s), purpose = btrim(%s), max_marks = %s, is_open = %s
               WHERE submission_link_id = %s AND faculty_id = %s""",
            (body.class_name, body.purpose, body.max_marks, body.is_open, link_id, account.user_id)).rowcount
    if changed == 0:
        raise HTTPException(404, "This isn't one of your submission links.")
    return {}


def class_list(conn, link_id: int) -> list[dict]:
    """Every student in every project of the link, with their marks and the team's."""
    return conn.execute(
        """SELECT c.project_id, c.title, c.status, c.created_at, u.user_id, u.prn, u.name, pm.is_leader,
                  pm.marks::float8, t.team_score::float8
           FROM pbl.project_cards c
           JOIN pbl.project_members pm ON pm.project_id = c.project_id
           JOIN pbl.users u            ON u.user_id = pm.user_id
           JOIN pbl.team_marks t       ON t.project_id = c.project_id
           WHERE c.submission_link_id = %s
           ORDER BY c.status = 'rejected', c.title, pm.is_leader DESC, u.name""", (link_id,)).fetchall()


@router.get("/links/{link_id}")
def link_page(link_id: int, account: db.Account = session.faculty) -> dict:
    with session.transaction(account) as conn:
        link = own_link(conn, link_id, account)
        rows = class_list(conn, link_id)
        closest = {r["project_id"]: r for r in conn.execute(
            """SELECT q.project_id, q.closest_title, q.similarity, q.band FROM pbl.review_queue q
               JOIN pbl.projects p USING (project_id) WHERE p.submission_link_id = %s""", (link_id,))}
    projects: dict[int, dict] = {}
    for r in rows:
        project = projects.setdefault(r["project_id"], {
            "project_id": r["project_id"], "title": r["title"], "status": r["status"], "created_at": r["created_at"],
            "team_score": r["team_score"], "closest": closest.get(r["project_id"]), "students": []})
        project["students"].append({k: r[k] for k in ("user_id", "prn", "name", "is_leader", "marks")})
    return {**link, "projects": list(projects.values())}


def _cell(value) -> str:
    """Titles and names are typed by users. A cell starting with = + - @ would run as a
    formula when the sheet is opened in Excel, so it gets a leading apostrophe."""
    text = "" if value is None else f"{value:g}" if isinstance(value, float) else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


@router.get("/links/{link_id}/marks.csv")
def export_marks(link_id: int, account: db.Account = session.faculty) -> Response:
    with session.transaction(account) as conn:
        link = own_link(conn, link_id, account)
        rows = class_list(conn, link_id)
    out = io.StringIO()
    sheet = csv.writer(out)
    sheet.writerow(["PRN", "Student", "Project", "Status", "Marks", "Team score", "Out of"])
    for r in rows:
        sheet.writerow([_cell(v) for v in (r["prn"], r["name"], r["title"], r["status"], r["marks"],
                                           r["team_score"], link["max_marks"])])
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"{link['subject']} {link['class_name']} {link['purpose']} marks").strip("-")
    # The byte-order mark makes Excel read the file as UTF-8, so names with accents survive.
    return Response("﻿" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}.csv"})


# Reviewing and marking a project ----------------------------------------------------------

@router.get("/review")
def review(account: db.Account = session.faculty) -> dict:
    """Submissions waiting for this faculty member, across all their links."""
    with session.transaction(account) as conn:
        waiting = conn.execute(
            """SELECT c.project_id, c.title, c.subject, c.class_name, c.purpose, c.members, c.created_at,
                      q.closest_title, q.closest_year, q.similarity, q.band
               FROM pbl.review_queue q
               JOIN pbl.project_cards c ON c.project_id = q.project_id
               WHERE q.faculty_id = %s
               ORDER BY q.created_at""", (account.user_id,)).fetchall()
    return {"waiting": waiting}


class DecisionBody(BaseModel):
    status: Literal["approved", "rejected"]
    note: str = Field("", max_length=1000)


@router.post("/projects/{project_id}/decision")
def decide(project_id: int, body: DecisionBody, account: db.Account = session.faculty) -> dict:
    with session.transaction(account) as conn:
        changed = conn.execute(
            """UPDATE pbl.projects p SET status = %s, review_note = nullif(btrim(%s), '')
               FROM pbl.submission_links l
               WHERE p.project_id = %s AND p.status = 'submitted'
                 AND l.submission_link_id = p.submission_link_id AND l.faculty_id = %s""",
            (body.status, body.note, project_id, account.user_id)).rowcount
    if changed == 0:
        raise HTTPException(409, "Nothing changed. It isn't one of your projects, or it was decided already.")
    return {"status": body.status}


class StudentMarks(BaseModel):
    user_id: int
    marks: float | None = Field(None, ge=0)     # None clears them


class MarksBody(BaseModel):
    marks: list[StudentMarks] = Field(min_length=1, max_length=20)


@router.put("/marks/{project_id}")
def save_marks(project_id: int, body: MarksBody, account: db.Account = session.faculty) -> dict:
    with session.transaction(account) as conn, conn.cursor() as cur:
        mine = cur.execute(
            """SELECT 1 FROM pbl.projects p JOIN pbl.submission_links l USING (submission_link_id)
               WHERE p.project_id = %s AND l.faculty_id = %s""", (project_id, account.user_id)).fetchone()
        if mine is None:
            raise HTTPException(404, "This isn't one of your projects.")
        for entry in body.marks:
            if cur.execute("UPDATE pbl.project_members SET marks = %s WHERE project_id = %s AND user_id = %s",
                           (entry.marks, project_id, entry.user_id)).rowcount == 0:
                raise HTTPException(422, "Marks can only be given to the project's own team.")
        team = cur.execute("SELECT team_score::float8 FROM pbl.team_marks WHERE project_id = %s",
                           (project_id,)).fetchone()
    return {"team_score": team["team_score"]}


# People -----------------------------------------------------------------------------

@router.get("/people")
def people(account: db.Account = session.admin) -> dict:
    with session.transaction(account) as conn:
        rows = conn.execute(
            """SELECT u.user_id, u.name, coalesce(u.prn, u.email) AS login, u.email, u.role, u.is_admin,
                      u.is_active, u.must_change_password,
                      (SELECT count(*) FROM pbl.project_members pm WHERE pm.user_id = u.user_id)
                    + (SELECT count(*) FROM pbl.project_cards c WHERE c.faculty_id = u.user_id) AS projects
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
                      count(c.project_id) AS projects,
                      count(t.team_score) AS marked
               FROM pbl.subjects s
               LEFT JOIN pbl.project_cards c ON c.subject = s.code
               LEFT JOIN pbl.team_marks t    ON t.project_id = c.project_id
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
    # max_marks is only where new submission links start; links already made keep theirs.
    with session.transaction(account) as conn:
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
