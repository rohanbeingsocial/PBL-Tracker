"""Pages everyone has after signing in: home, search, a project's own page, a
submission link as students open it, submitting a project through it, trends, and
the links and files of a project."""
import re
import secrets
from functools import lru_cache
from pathlib import PurePath
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi import Path as PathParam
from fastapi.concurrency import run_in_threadpool
from psycopg import sql
from pydantic import BaseModel, Field

from api import session
from finder import db, storage
from finder.embeddings import embed, project_text

router = APIRouter(prefix="/api")


@lru_cache(maxsize=500)
def _embed_cached(text: str) -> tuple[float, ...]:
    return tuple(embed([text])[0])


def embed_text(text: str) -> list[float]:
    return list(_embed_cached(text))


@router.get("/reference")
def reference(account: db.Account = session.anyone) -> dict:
    with session.transaction(account) as conn:
        return {
            "subjects": conn.execute(
                "SELECT subject_id, code, name, max_marks::float8 FROM pbl.subjects ORDER BY code").fetchall(),
            "faculty": conn.execute(
                "SELECT user_id, name FROM pbl.users WHERE role = 'faculty' AND is_active ORDER BY name").fetchall(),
            "tags": conn.execute("SELECT tag_id, name FROM pbl.tags ORDER BY lower(name)").fetchall(),
            "years": [r["academic_year"] for r in
                      conn.execute("SELECT DISTINCT academic_year FROM pbl.submission_links ORDER BY 1")],
            "current_year": conn.execute("SELECT pbl.current_academic_year() AS y").fetchone()["y"],
        }


def access(conn, project_id: int, account: db.Account) -> dict:
    """Who this person is to the project. Approved projects are open to everyone signed
    in; a project still waiting, or rejected, only to its team, its faculty member and
    the PBL coordinator. Anyone else gets 404, as if it didn't exist."""
    project = conn.execute(
        """SELECT p.project_id, l.faculty_id, p.status, p.marks_public,
                  EXISTS (SELECT 1 FROM pbl.project_members pm
                          WHERE pm.project_id = p.project_id AND pm.user_id = %s) AS is_member
           FROM pbl.projects p JOIN pbl.submission_links l USING (submission_link_id)
           WHERE p.project_id = %s""",
        (account.user_id, project_id)).fetchone()
    if project is None:
        raise HTTPException(404, "No such project.")
    project["is_faculty"] = project["faculty_id"] == account.user_id
    project["involved"] = project["is_member"] or project["is_faculty"] or account.is_admin
    if project["status"] != "approved" and not project["involved"]:
        raise HTTPException(404, "No such project.")
    return project


def can_change(conn, project_id: int, account: db.Account) -> dict:
    """The project, if this person may add or remove its links and files: a team
    member, the project's faculty member, or an admin."""
    project = access(conn, project_id, account)
    if not project["involved"]:
        raise HTTPException(403, "Only the team, its faculty member or the PBL coordinator can change this project.")
    return project


# Home ---------------------------------------------------------------------------

def student_home(conn, account: db.Account) -> dict:
    # marks are this student's own; team_score is the team's average.
    mine = conn.execute(
        """SELECT c.*, pm.marks::float8, t.team_score::float8, t.max_marks::float8, pm.is_leader
           FROM pbl.project_members pm
           JOIN pbl.project_cards c ON c.project_id = pm.project_id
           JOIN pbl.team_marks t    ON t.project_id = pm.project_id
           WHERE pm.user_id = %s
           ORDER BY c.academic_year DESC, c.created_at DESC""", (account.user_id,)).fetchall()
    # The stacks approved projects used in the last two years, for the "what's popular" chart.
    popular = conn.execute(
        """SELECT tag, sum(project_count)::int AS projects FROM pbl.tag_trends
           WHERE academic_year IN (SELECT DISTINCT academic_year FROM pbl.tag_trends
                                   ORDER BY academic_year DESC LIMIT 2)
           GROUP BY tag ORDER BY projects DESC, tag LIMIT 6""").fetchall()
    approved = conn.execute(
        """SELECT project_id, title, subject, academic_year, faculty, members, decided_at
           FROM pbl.project_cards WHERE status = 'approved'
           ORDER BY decided_at DESC, project_id DESC LIMIT 5""").fetchall()
    return {"projects": mine, "popular": popular, "approved": approved}


def faculty_home(conn, account: db.Account) -> dict:
    waiting = conn.execute(
        """SELECT q.project_id, q.title, q.subject, c.class_name, q.created_at,
                  q.closest_title, q.closest_year, q.similarity, q.band
           FROM pbl.review_queue q JOIN pbl.project_cards c USING (project_id)
           WHERE q.faculty_id = %s ORDER BY q.created_at""",
        (account.user_id,)).fetchall()
    counts = conn.execute(
        """SELECT count(*) FILTER (WHERE c.status = 'approved') AS approved,
                  count(*) FILTER (WHERE c.status = 'rejected') AS rejected,
                  count(t.team_score)                        AS graded
           FROM pbl.project_cards c LEFT JOIN pbl.team_marks t USING (project_id)
           WHERE c.faculty_id = %s""", (account.user_id,)).fetchone()
    to_grade = conn.execute(
        """SELECT c.project_id, c.title, c.academic_year, c.subject, c.class_name, c.purpose,
                  t.max_marks::float8, t.graded, t.members
           FROM pbl.project_cards c JOIN pbl.team_marks t USING (project_id)
           WHERE c.faculty_id = %s AND c.status = 'approved' AND t.team_score IS NULL
           ORDER BY c.academic_year DESC, c.title""", (account.user_id,)).fetchall()
    by_subject = conn.execute(
        """SELECT c.subject,
                  count(*) FILTER (WHERE c.status = 'approved')  AS approved,
                  count(*) FILTER (WHERE c.status = 'submitted') AS waiting,
                  round(avg(t.percent))::int                     AS average_percent
           FROM pbl.project_cards c LEFT JOIN pbl.team_marks t USING (project_id)
           WHERE c.faculty_id = %s
           GROUP BY c.subject ORDER BY c.subject""", (account.user_id,)).fetchall()
    percents = [r["percent"] for r in conn.execute(
        """SELECT t.percent::float8 AS percent
           FROM pbl.project_cards c JOIN pbl.team_marks t USING (project_id)
           WHERE c.faculty_id = %s AND t.percent IS NOT NULL""", (account.user_id,))]
    links = conn.execute(
        """SELECT submission_link_id, subject, class_name, purpose, waiting, approved, graded
           FROM pbl.link_progress
           WHERE faculty_id = %s AND is_open
           ORDER BY academic_year DESC, subject, class_name""", (account.user_id,)).fetchall()
    return {"waiting": waiting, **counts, "to_grade": to_grade, "by_subject": by_subject, "percents": percents,
            "links": links}


def admin_home(conn, account: db.Account) -> dict:
    projects = conn.execute(
        """SELECT count(*) FILTER (WHERE status = 'approved')  AS approved,
                  count(*) FILTER (WHERE status = 'submitted') AS waiting,
                  count(*) FILTER (WHERE embedding IS NULL)    AS unembedded
           FROM pbl.projects""").fetchone()
    users = conn.execute(
        """SELECT count(*) FILTER (WHERE is_active AND role = 'student') AS students,
                  count(*) FILTER (WHERE is_active AND role = 'faculty') AS faculty
           FROM pbl.users""").fetchone()
    per_year = conn.execute(
        """SELECT academic_year,
                  count(*) FILTER (WHERE status = 'approved')  AS approved,
                  count(*) FILTER (WHERE status = 'submitted') AS submitted,
                  count(*) FILTER (WHERE status = 'rejected')  AS rejected
           FROM pbl.project_cards GROUP BY academic_year ORDER BY academic_year""").fetchall()
    by_subject = conn.execute(
        """SELECT s.code AS subject, count(c.project_id) AS projects
           FROM pbl.subjects s LEFT JOIN pbl.project_cards c ON c.subject = s.code AND c.status <> 'rejected'
           GROUP BY s.code ORDER BY projects DESC, s.code""").fetchall()
    load = conn.execute(
        """SELECT faculty, sum(waiting)::int AS waiting, sum(approved)::int AS approved
           FROM pbl.link_progress
           WHERE academic_year = pbl.current_academic_year()
           GROUP BY faculty ORDER BY waiting DESC, approved DESC, faculty""").fetchall()
    recent = conn.execute(
        """SELECT project_id, title, subject, faculty, status, created_at
           FROM pbl.project_cards ORDER BY created_at DESC, project_id DESC LIMIT 6""").fetchall()
    return {**projects, **users, "rejected": sum(y["rejected"] for y in per_year), "per_year": per_year,
            "by_subject": by_subject, "load": load, "recent": recent}


@router.get("/home")
def home(account: db.Account = session.anyone) -> dict:
    with session.transaction(account) as conn:
        if account.is_admin:
            return admin_home(conn, account)
        return student_home(conn, account) if account.role == "student" else faculty_home(conn, account)


# One project --------------------------------------------------------------------

@router.get("/projects/{project_id}")
def project_page(project_id: int, account: db.Account = session.anyone) -> dict:
    with session.transaction(account) as conn:
        who = access(conn, project_id, account)
        card = conn.execute("SELECT * FROM pbl.project_cards WHERE project_id = %s", (project_id,)).fetchone()
        team = conn.execute(
            "SELECT team_score::float8, max_marks::float8, graded, members FROM pbl.team_marks WHERE project_id = %s",
            (project_id,)).fetchone()
        students = conn.execute(
            """SELECT pm.user_id, u.name, u.prn, pm.is_leader, pm.marks::float8
               FROM pbl.project_members pm JOIN pbl.users u USING (user_id)
               WHERE pm.project_id = %s ORDER BY pm.is_leader DESC, u.name""", (project_id,)).fetchall()
        closest = None
        if card["status"] == "submitted":
            closest = conn.execute(
                """SELECT q.closest_id, q.closest_title, q.closest_year, q.similarity, q.band
                   FROM pbl.review_queue q WHERE q.project_id = %s""", (project_id,)).fetchone()
    # The team score: the team, the faculty member and the coordinator always; others
    # only if the team has chosen to show it. Each student's own marks: that student,
    # the faculty member and the coordinator; teammates don't see each other's.
    show_score = who["involved"] or card["marks_public"]
    sees_everyone = who["is_faculty"] or account.is_admin
    mine = next((s["marks"] for s in students if s["user_id"] == account.user_id), None)
    return {
        **card,
        "team_score": team["team_score"] if show_score else None,
        "marks_hidden": not show_score and team["team_score"] is not None,
        "max_marks": team["max_marks"],
        "graded": team["graded"] if sees_everyone else None,
        "my_marks": mine,
        "students": students if sees_everyone else None,
        "is_member": who["is_member"],
        "is_faculty": who["is_faculty"],
        "can_change": who["involved"],
        "closest": closest,
    }


class MarksPublicBody(BaseModel):
    public: bool


@router.put("/projects/{project_id}/marks-public")
def set_marks_public(project_id: int, body: MarksPublicBody, account: db.Account = session.anyone) -> dict:
    with session.transaction(account) as conn:
        if not access(conn, project_id, account)["is_member"]:
            raise HTTPException(403, "Only the team decides whether its marks are shown to everyone.")
        conn.execute("UPDATE pbl.projects SET marks_public = %s WHERE project_id = %s", (body.public, project_id))
    return {"public": body.public}


# Search -------------------------------------------------------------------------

@router.get("/search")
def search(q: str = Query("", max_length=200),
           mode: Literal["Both", "Meaning", "Keywords"] = "Both",
           subject: list[str] = Query([]),
           tag: list[str] = Query([]),
           kind: list[str] = Query([]),
           year_from: str | None = None,
           year_to: str | None = None,
           account: db.Account = session.anyone) -> dict:
    query = q.strip()
    # Only approved projects are searchable. Filters are added as SQL pieces with
    # placeholders, never by pasting values in.
    conditions: list[sql.Composable] = [sql.SQL("c.status = 'approved'")]
    params: list = []
    if year_from and year_to:
        conditions.append(sql.SQL("c.academic_year BETWEEN %s AND %s"))
        params += [year_from, year_to]
    if subject:
        conditions.append(sql.SQL("c.subject = ANY(%s)"))
        params.append(subject)
    if tag:
        conditions.append(sql.SQL("c.tags && %s::text[]"))
        params.append(tag)
    if kind:
        conditions.append(sql.SQL("c.project_type = ANY(%s)"))
        params.append(kind)
    where = sql.SQL(" AND ").join(conditions)

    if not query:
        statement = sql.SQL("""SELECT c.*, NULL AS snippet, NULL::float8 AS similarity, NULL AS band
                               FROM pbl.project_cards c WHERE {}
                               ORDER BY c.academic_year DESC, c.title LIMIT 200""").format(where)
        args = params
    elif mode == "Keywords":
        statement = sql.SQL("""SELECT c.*, k.snippet, NULL::float8 AS similarity, NULL AS band
                               FROM pbl.keyword_search(%s, 50) k
                               JOIN pbl.project_cards c ON c.project_id = k.project_id
                               WHERE {} ORDER BY k.rank DESC LIMIT 20""").format(where)
        args = [query, *params]
    elif mode == "Meaning":
        statement = sql.SQL("""SELECT c.*, NULL AS snippet, s.similarity, s.band
                               FROM pbl.similar_projects(%s, 50) s
                               JOIN pbl.project_cards c ON c.project_id = s.project_id
                               WHERE s.band <> 'different' AND {}
                               ORDER BY s.similarity DESC LIMIT 20""").format(where)
        args = [embed_text(query), *params]
    else:
        statement = sql.SQL("""SELECT c.*, NULL AS snippet, h.similarity, h.band
                               FROM pbl.hybrid_search(%s, %s, 50) h
                               JOIN pbl.project_cards c ON c.project_id = h.project_id
                               WHERE {} ORDER BY h.score DESC LIMIT 20""").format(where)
        args = [query, embed_text(query), *params]

    with session.transaction(account) as conn:
        rows = conn.execute(statement, args).fetchall()
    return {"rows": rows, "ranked": bool(query)}


# Similar past projects, shown while a team fills in the submit form ------------------

class IdeaBody(BaseModel):
    title: str = Field(max_length=200)
    abstract: str = Field("", max_length=3000)


@router.post("/check")
def check_idea(body: IdeaBody, account: db.Account = session.anyone) -> dict:
    if len(body.title.strip()) < 5:
        raise HTTPException(422, "Give the project a title of at least five characters.")
    vector = embed_text(project_text(body.title, body.abstract))
    with session.transaction(account) as conn:
        matches = conn.execute(
            """SELECT s.project_id, s.title, s.academic_year, s.subject, s.similarity, s.band
               FROM pbl.similar_projects(%s, 5) s
               WHERE s.status = 'approved' AND s.band <> 'different'
               ORDER BY s.similarity DESC""",
            (vector,)).fetchall()
    return {"matches": matches}


# Files --------------------------------------------------------------------------------

MAX_BYTES = 20 * 1024 * 1024
FILE_TYPES = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
ALLOWED = {"report": {".pdf"}, "ppt": {".pptx", ".pdf"}}
KIND_NAME = {"report": "report", "ppt": "presentation"}


def check_file(kind: str, name: str, data: bytes) -> tuple[str, str]:
    """The clean file name and the path it will have in storage. The user's file name
    never becomes part of the path."""
    name = PurePath(name.replace("\\", "/")).name.strip()[:200]
    ext = PurePath(name).suffix.lower()
    if ext not in ALLOWED[kind]:
        raise HTTPException(422, f"The {KIND_NAME[kind]} has to be a {' or '.join(sorted(ALLOWED[kind]))} file.")
    if not data:
        raise HTTPException(422, f"The {KIND_NAME[kind]} file is empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Files can be at most 20 MB.")
    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        raise HTTPException(422, f"The {KIND_NAME[kind]} isn't a PDF file.")
    return name, f"{secrets.token_hex(8)}{ext}"


def _store_file(project_id: int, kind: str, name: str, data: bytes, account: db.Account) -> dict:
    name, filename = check_file(kind, name, data)
    path = f"{project_id}/{filename}"
    with session.transaction(account) as conn:
        can_change(conn, project_id, account)
    storage.save(path, data, FILE_TYPES[PurePath(path).suffix])
    try:
        with session.transaction(account) as conn:
            # One report and one presentation per project: a new one replaces the old.
            old = conn.execute("SELECT file_id, storage_path FROM pbl.project_files WHERE project_id = %s AND kind = %s",
                               (project_id, kind)).fetchone()
            if old:
                conn.execute(
                    """UPDATE pbl.project_files SET file_name = %s, storage_path = %s, size_bytes = %s,
                              uploaded_by = %s, uploaded_at = now()
                       WHERE file_id = %s""",
                    (name, path, len(data), account.user_id, old["file_id"]))
                file_id = old["file_id"]
            else:
                file_id = conn.execute(
                    """INSERT INTO pbl.project_files (project_id, kind, file_name, storage_path, size_bytes, uploaded_by)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING file_id""",
                    (project_id, kind, name, path, len(data), account.user_id)).fetchone()["file_id"]
    except Exception:
        storage.delete(path)
        raise
    if old:
        storage.delete(old["storage_path"])
    return {"file_id": file_id}


@router.post("/projects/{project_id}/files")
async def upload_file(project_id: int, request: Request, kind: Literal["report", "ppt"],
                      name: str = Query(min_length=1, max_length=200),
                      account: db.Account = session.anyone) -> dict:
    """The file is the request body itself, with its name and kind in the query."""
    if int(request.headers.get("content-length") or 0) > MAX_BYTES:
        raise HTTPException(413, "Files can be at most 20 MB.")
    data = await request.body()
    return await run_in_threadpool(_store_file, project_id, kind, name, data, account)


@router.get("/files/{file_id}")
def download_file(file_id: int, inline: bool = False, account: db.Account = session.anyone) -> Response:
    with session.transaction(account) as conn:
        row = conn.execute("SELECT project_id, file_name, storage_path FROM pbl.project_files WHERE file_id = %s",
                           (file_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "No such file.")
        access(conn, row["project_id"], account)
    ext = PurePath(row["storage_path"]).suffix
    # Only PDFs open inside the page (the report viewer); everything else downloads.
    disposition = "inline" if inline and ext == ".pdf" else "attachment"
    return Response(storage.load(row["storage_path"]), media_type=FILE_TYPES.get(ext, "application/octet-stream"),
                    headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(row['file_name'])}"})


@router.delete("/files/{file_id}")
def remove_file(file_id: int, account: db.Account = session.anyone) -> dict:
    with session.transaction(account) as conn:
        row = conn.execute("SELECT project_id, storage_path FROM pbl.project_files WHERE file_id = %s",
                           (file_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "No such file.")
        can_change(conn, row["project_id"], account)
        conn.execute("DELETE FROM pbl.project_files WHERE file_id = %s", (file_id,))   # a report is refused (trigger)
    storage.delete(row["storage_path"])
    return {}


# Links ----------------------------------------------------------------------------------

class LinkBody(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    url: str = Field(max_length=300)


def check_url(url: str) -> str:
    url = url.strip()
    if not re.fullmatch(r"https?://\S+", url):
        raise HTTPException(422, "A link has to start with https:// or http://.")
    return url


@router.post("/projects/{project_id}/links")
def add_link(project_id: int, body: LinkBody, account: db.Account = session.anyone) -> dict:
    url = check_url(body.url)
    with session.transaction(account) as conn:
        can_change(conn, project_id, account)
        link_id = conn.execute(
            "INSERT INTO pbl.project_links (project_id, label, url) VALUES (%s, %s, %s) RETURNING link_id",
            (project_id, body.label.strip(), url)).fetchone()["link_id"]
    return {"link_id": link_id}


@router.delete("/links/{link_id}")
def remove_link(link_id: int, account: db.Account = session.anyone) -> dict:
    with session.transaction(account) as conn:
        link = conn.execute("SELECT project_id FROM pbl.project_links WHERE link_id = %s", (link_id,)).fetchone()
        if link is None:
            raise HTTPException(404, "No such link.")
        can_change(conn, link["project_id"], account)
        conn.execute("DELETE FROM pbl.project_links WHERE link_id = %s", (link_id,))
    return {}


# A submission link, as a student opens it ------------------------------------------------

LINK_CODE = r"^[a-z0-9]{6,16}$"


def find_link(conn, code: str) -> dict:
    link = conn.execute(
        """SELECT submission_link_id, code, faculty_id, faculty, subject, subject_name, academic_year,
                  class_name, purpose, max_marks::float8, is_open, waiting, approved
           FROM pbl.link_progress WHERE code = %s""", (code,)).fetchone()
    if link is None:
        raise HTTPException(404, "No submission link with this code. Check the link your faculty member sent.")
    return link


def open_link(conn, code: str) -> dict:
    link = find_link(conn, code)
    if not link["is_open"]:
        raise HTTPException(422, "This submission link is closed. Ask your faculty member.")
    return link


@router.get("/s/{code}")
def submission_link(code: str = PathParam(pattern=LINK_CODE), account: db.Account = session.anyone) -> dict:
    with session.transaction(account) as conn:
        link = find_link(conn, code)
        is_owner = link["faculty_id"] == account.user_id
        # The class's approved projects are open to everyone, as everywhere else; a
        # student's own project shows whatever its status.
        projects = conn.execute(
            """SELECT c.project_id, c.title, c.members, c.status, c.project_type, c.tags, c.created_at,
                      %s = ANY(c.member_ids) AS mine
               FROM pbl.project_cards c
               WHERE c.submission_link_id = %s AND (c.status = 'approved' OR %s = ANY(c.member_ids) OR %s)
               ORDER BY mine DESC, c.title""",
            (account.user_id, link["submission_link_id"], account.user_id, is_owner or account.is_admin)).fetchall()
    live = next((p["project_id"] for p in projects if p["mine"] and p["status"] != "rejected"), None)
    return {**link, "projects": projects, "my_project": live, "is_owner": is_owner}


# Submitting a project -------------------------------------------------------------------

def _submit(account: db.Account, code: str, title: str, abstract: str, project_type: str,
            teammates: str, tags: list[str], github: str, demo: str,
            report: tuple[str, bytes], ppt: tuple[str, bytes] | None) -> dict:
    title, abstract = title.strip(), abstract.strip()
    if len(title) < 5:
        raise HTTPException(422, "Give the project a title of at least five characters.")
    if len(abstract) < 30:
        raise HTTPException(422, "The abstract needs at least 30 characters.")
    mates = [p for p in dict.fromkeys(re.split(r"[,\s]+", teammates)) if p and p != account.prn]
    if len(mates) > 12 or not all(re.fullmatch(r"[0-9]{10}", p) for p in mates):
        raise HTTPException(422, "Enter each teammate's 10-digit PRN, separated by commas.")
    tags = list(dict.fromkeys(t.strip()[:60] for t in tags if t.strip()))[:12]
    links = [(label, check_url(url)) for label, url in (("GitHub", github), ("Working demo", demo)) if url.strip()]
    report_name, report_file = check_file("report", *report)
    ppt_name, ppt_file = check_file("ppt", *ppt) if ppt else (None, None)
    # submit_project() checks the link again; this only saves uploading the files for nothing.
    with session.transaction(account) as conn:
        open_link(conn, code)

    vector = embed_text(project_text(title, abstract))
    # The files go to storage first, under a folder for the submitting student; the
    # database row that points to them is written by submit_project() in one go.
    folder = f"new/{account.user_id}"
    stored = [(f"{folder}/{report_file}", report[1])] + ([(f"{folder}/{ppt_file}", ppt[1])] if ppt else [])
    for path, data in stored:
        storage.save(path, data, FILE_TYPES[PurePath(path).suffix])
    try:
        with session.transaction(account) as conn:
            new_id = conn.execute(
                """SELECT pbl.submit_project(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                             %s, %s, %s, %s, %s, %s) AS id""",
                (account.user_id, title, abstract, code, mates, project_type, tags,
                 [label for label, _ in links], [url for _, url in links], vector,
                 report_name, stored[0][0], len(report[1]),
                 ppt_name, stored[1][0] if ppt else None, len(ppt[1]) if ppt else None),
            ).fetchone()["id"]
            faculty = conn.execute("SELECT faculty FROM pbl.project_cards WHERE project_id = %s", (new_id,)).fetchone()
    except Exception:
        for path, _ in stored:
            storage.delete(path)
        raise
    return {"id": new_id, "faculty": faculty["faculty"]}


@router.post("/submissions")
async def submit_project(code: str = Form(max_length=16),
                         title: str = Form(max_length=200),
                         abstract: str = Form(max_length=3000),
                         project_type: Literal["software", "hardware", "both"] = Form(),
                         teammates: str = Form("", max_length=300),
                         tags: list[str] = Form([]),
                         github: str = Form("", max_length=300),
                         demo: str = Form("", max_length=300),
                         report: UploadFile = File(),
                         ppt: UploadFile | None = File(None),
                         account: db.Account = session.student) -> dict:
    files = {}
    for kind, upload in (("report", report), ("ppt", ppt)):
        if upload is not None and upload.filename:
            data = await upload.read(MAX_BYTES + 1)
            files[kind] = (upload.filename, data)
    if "report" not in files:
        raise HTTPException(422, "Attach the project report (PDF).")
    return await run_in_threadpool(_submit, account, code, title, abstract, project_type,
                                   teammates, tags, github, demo, files["report"], files.get("ppt"))


# Trends -------------------------------------------------------------------------

@router.get("/trends")
def trends(account: db.Account = session.anyone) -> dict:
    with session.transaction(account) as conn:
        year = conn.execute("SELECT pbl.current_academic_year() AS y").fetchone()["y"]
        totals = conn.execute(
            """SELECT count(*) FILTER (WHERE status = 'approved')  AS projects,
                      count(DISTINCT academic_year)                AS years,
                      count(*) FILTER (WHERE status = 'submitted') AS waiting
               FROM pbl.project_cards""").fetchone()
        types = conn.execute(
            """SELECT project_type, count(*) AS projects FROM pbl.projects
               WHERE status = 'approved' GROUP BY project_type ORDER BY projects DESC""").fetchall()
        pairs = conn.execute(
            """SELECT first_title, first_year, second_title, second_year, similarity, band
               FROM pbl.repeated_ideas ORDER BY similarity DESC""").fetchall()
        # The heatmap shows the 12 most used tags; the rest would be mostly empty rows.
        tags = conn.execute(
            """SELECT tag, academic_year, project_count FROM pbl.tag_trends
               WHERE tag IN (SELECT tag FROM pbl.tag_trends GROUP BY tag
                             ORDER BY sum(project_count) DESC, tag LIMIT 12)""").fetchall()
        load = conn.execute(
            """SELECT faculty,
                      count(*) AS projects,
                      count(*) FILTER (WHERE status = 'submitted') AS waiting
               FROM pbl.project_cards
               WHERE academic_year = %s AND status <> 'rejected'
               GROUP BY faculty ORDER BY projects DESC, faculty""", (year,)).fetchall()
    return {"year": year, "totals": totals, "types": types, "pairs": pairs, "tags": tags, "load": load}
