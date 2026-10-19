"""Pages everyone has after signing in: home, search, check an idea, trends, and the
links and files of a project."""
import re
import secrets
from functools import lru_cache
from pathlib import PurePath
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request, Response
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
                      conn.execute("SELECT DISTINCT academic_year FROM pbl.projects ORDER BY 1")],
            "current_year": conn.execute("SELECT pbl.current_academic_year() AS y").fetchone()["y"],
        }


def can_change(conn, project_id: int, account: db.Account) -> dict:
    """The project, if this person may add or remove its links and files: a team
    member, the project's faculty member, or an admin."""
    project = conn.execute(
        """SELECT p.project_id, p.faculty_id,
                  EXISTS (SELECT 1 FROM pbl.project_members pm
                          WHERE pm.project_id = p.project_id AND pm.user_id = %s) AS is_member
           FROM pbl.projects p WHERE p.project_id = %s""",
        (account.user_id, project_id)).fetchone()
    if project is None:
        raise HTTPException(404, "No such project.")
    if not (project["is_member"] or project["faculty_id"] == account.user_id or account.is_admin):
        raise HTTPException(403, "Only the team, its faculty member or the PBL coordinator can change this project.")
    return project


# Home ---------------------------------------------------------------------------

def student_home(conn, account: db.Account) -> dict:
    mine = conn.execute(
        """SELECT c.*, p.marks::float8, s.max_marks::float8, pm.is_leader,
                  q.closest_title, q.closest_year, q.similarity, q.band, cl.abstract AS closest_abstract
           FROM pbl.project_members pm
           JOIN pbl.project_cards c ON c.project_id = pm.project_id
           JOIN pbl.projects p      ON p.project_id = pm.project_id
           JOIN pbl.subjects s      ON s.subject_id = p.subject_id
           LEFT JOIN pbl.review_queue q ON q.project_id = pm.project_id
           LEFT JOIN pbl.projects cl    ON cl.project_id = q.closest_id
           WHERE pm.user_id = %s
           ORDER BY c.academic_year DESC, c.title""", (account.user_id,)).fetchall()
    return {"projects": mine}


def faculty_home(conn, account: db.Account) -> dict:
    waiting = conn.execute(
        """SELECT project_id, title, subject, created_at, closest_title, closest_year, similarity, band
           FROM pbl.review_queue WHERE faculty_id = %s ORDER BY created_at""",
        (account.user_id,)).fetchall()
    counts = conn.execute(
        """SELECT count(*) FILTER (WHERE status = 'approved') AS running,
                  count(*) FILTER (WHERE status <> 'rejected') AS guided
           FROM pbl.projects WHERE faculty_id = %s""", (account.user_id,)).fetchone()
    to_mark = conn.execute(
        """SELECT p.project_id, p.title, p.academic_year, s.code AS subject, s.max_marks::float8
           FROM pbl.projects p JOIN pbl.subjects s ON s.subject_id = p.subject_id
           WHERE p.faculty_id = %s AND p.status IN ('approved', 'completed') AND p.marks IS NULL
           ORDER BY p.academic_year DESC, p.title""", (account.user_id,)).fetchall()
    return {"waiting": waiting, "running": counts["running"], "guided": counts["guided"], "to_mark": to_mark}


def admin_home(conn, account: db.Account) -> dict:
    projects = conn.execute(
        """SELECT count(*) FILTER (WHERE status <> 'rejected') AS on_record,
                  count(*) FILTER (WHERE status = 'proposed')  AS waiting,
                  count(*) FILTER (WHERE embedding IS NULL)    AS unembedded
           FROM pbl.projects""").fetchone()
    users = conn.execute(
        """SELECT count(*) FILTER (WHERE is_active AND role = 'student') AS students,
                  count(*) FILTER (WHERE is_active AND role = 'faculty') AS faculty
           FROM pbl.users""").fetchone()
    per_year = conn.execute(
        """SELECT academic_year,
                  count(*) FILTER (WHERE status = 'completed') AS completed,
                  count(*) FILTER (WHERE status = 'approved')  AS approved,
                  count(*) FILTER (WHERE status = 'proposed')  AS proposed
           FROM pbl.projects GROUP BY academic_year ORDER BY academic_year""").fetchall()
    recent = conn.execute(
        """SELECT project_id, title, subject, faculty, status, created_at
           FROM pbl.project_cards ORDER BY created_at DESC, project_id DESC LIMIT 6""").fetchall()
    return {**projects, **users, "per_year": per_year, "recent": recent}


@router.get("/home")
def home(account: db.Account = session.anyone) -> dict:
    with session.transaction(account) as conn:
        if account.is_admin:
            return admin_home(conn, account)
        return student_home(conn, account) if account.role == "student" else faculty_home(conn, account)


# Search -------------------------------------------------------------------------

@router.get("/search")
def search(q: str = Query("", max_length=200),
           mode: Literal["Both", "Meaning", "Keywords"] = "Both",
           subject: list[str] = Query([]),
           tag: list[str] = Query([]),
           kind: list[str] = Query([]),
           year_from: str | None = None,
           year_to: str | None = None,
           include_all: bool = False,
           account: db.Account = session.anyone) -> dict:
    query = q.strip()
    # Filters are added as SQL pieces with placeholders, never by pasting values in.
    conditions: list[sql.Composable] = []
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
    if not include_all:
        conditions.append(sql.SQL("c.status IN ('approved', 'completed')"))
    where = sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("true")

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


# Check an idea and submit it --------------------------------------------------------

class IdeaBody(BaseModel):
    title: str = Field(max_length=200)
    abstract: str = Field("", max_length=1500)


@router.post("/check")
def check_idea(body: IdeaBody, account: db.Account = session.anyone) -> dict:
    if len(body.title.strip()) < 5:
        raise HTTPException(422, "Give the project a title of at least five characters.")
    vector = embed_text(project_text(body.title, body.abstract))
    with session.transaction(account) as conn:
        matches = conn.execute(
            """SELECT c.*, s.similarity, s.band
               FROM pbl.similar_projects(%s, 5) s
               JOIN pbl.project_cards c ON c.project_id = s.project_id
               ORDER BY s.similarity DESC""",
            (vector,)).fetchall()
    return {"matches": matches}


class LinkBody(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    url: str = Field(max_length=300)


def check_url(url: str) -> str:
    url = url.strip()
    if not re.fullmatch(r"https?://\S+", url):
        raise HTTPException(422, "A link has to start with https:// or http://.")
    return url


class ProposalBody(IdeaBody):
    subject_id: int
    faculty_id: int
    project_type: Literal["software", "hardware", "both"]
    teammates: list[str] = Field([], max_length=12)
    tags: list[str] = Field([], max_length=12)
    links: list[LinkBody] = Field([], max_length=6)


@router.post("/proposals")
def submit_proposal(body: ProposalBody, account: db.Account = session.student) -> dict:
    title, abstract = body.title.strip(), body.abstract.strip()
    if len(title) < 5:
        raise HTTPException(422, "Give the project a title of at least five characters.")
    if len(abstract) < 30:
        raise HTTPException(422, "A proposal needs an abstract of at least 30 characters.")
    mates = [p for p in dict.fromkeys(m.strip() for m in body.teammates) if p and p != account.prn]
    if not all(re.fullmatch(r"[0-9]{10}", p) for p in mates):
        raise HTTPException(422, "Enter each teammate's 10-digit PRN, separated by commas.")
    tags = [t.strip()[:60] for t in body.tags if t.strip()]
    links = [(link.label.strip(), check_url(link.url)) for link in body.links]
    vector = embed_text(project_text(title, abstract))
    with session.transaction(account) as conn:
        new_id = conn.execute(
            "SELECT pbl.submit_project(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) AS id",
            (account.user_id, title, abstract, body.subject_id, body.faculty_id, mates, body.project_type,
             tags, [label for label, _ in links], [url for _, url in links], vector),
        ).fetchone()["id"]
        faculty = conn.execute("SELECT name FROM pbl.users WHERE user_id = %s", (body.faculty_id,)).fetchone()
    return {"id": new_id, "faculty": faculty["name"]}


# Links and files ------------------------------------------------------------------

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


MAX_BYTES = 20 * 1024 * 1024
FILE_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
ALLOWED = {"report": {".pdf", ".docx"}, "ppt": {".pptx", ".pdf"}}


def _store_file(project_id: int, kind: str, name: str, data: bytes, account: db.Account) -> dict:
    ext = PurePath(name).suffix.lower()
    path = f"{project_id}/{secrets.token_hex(8)}{ext}"   # the user's file name never becomes a path
    with session.transaction(account) as conn:
        can_change(conn, project_id, account)
    storage.save(path, data, FILE_TYPES[ext])
    try:
        with session.transaction(account) as conn:
            file_id = conn.execute(
                """INSERT INTO pbl.project_files (project_id, kind, file_name, storage_path, size_bytes, uploaded_by)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING file_id""",
                (project_id, kind, name, path, len(data), account.user_id)).fetchone()["file_id"]
    except Exception:
        storage.delete(path)
        raise
    return {"file_id": file_id}


@router.post("/projects/{project_id}/files")
async def upload_file(project_id: int, request: Request, kind: Literal["report", "ppt"],
                      name: str = Query(min_length=1, max_length=200),
                      account: db.Account = session.anyone) -> dict:
    """The file is the request body itself, with its name and kind in the query."""
    name = PurePath(name.replace("\\", "/")).name.strip()
    ext = PurePath(name).suffix.lower()
    if ext not in ALLOWED[kind]:
        allowed = " or ".join(sorted(ALLOWED[kind]))
        raise HTTPException(422, f"A {'report' if kind == 'report' else 'presentation'} has to be a {allowed} file.")
    if int(request.headers.get("content-length") or 0) > MAX_BYTES:
        raise HTTPException(413, "Files can be at most 20 MB.")
    data = await request.body()
    if not data:
        raise HTTPException(422, "The file is empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Files can be at most 20 MB.")
    return await run_in_threadpool(_store_file, project_id, kind, name, data, account)


@router.get("/files/{file_id}")
def download_file(file_id: int, account: db.Account = session.anyone) -> Response:
    with session.transaction(account) as conn:
        row = conn.execute("SELECT file_name, storage_path FROM pbl.project_files WHERE file_id = %s",
                           (file_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "No such file.")
    ext = PurePath(row["storage_path"]).suffix
    return Response(storage.load(row["storage_path"]), media_type=FILE_TYPES.get(ext, "application/octet-stream"),
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(row['file_name'])}"})


@router.delete("/files/{file_id}")
def remove_file(file_id: int, account: db.Account = session.anyone) -> dict:
    with session.transaction(account) as conn:
        row = conn.execute("SELECT project_id, storage_path FROM pbl.project_files WHERE file_id = %s",
                           (file_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "No such file.")
        can_change(conn, row["project_id"], account)
        conn.execute("DELETE FROM pbl.project_files WHERE file_id = %s", (file_id,))
    storage.delete(row["storage_path"])
    return {}


# Trends -------------------------------------------------------------------------

@router.get("/trends")
def trends(account: db.Account = session.anyone) -> dict:
    with session.transaction(account) as conn:
        year = conn.execute("SELECT pbl.current_academic_year() AS y").fetchone()["y"]
        totals = conn.execute(
            """SELECT count(*) FILTER (WHERE status <> 'rejected') AS projects,
                      count(DISTINCT academic_year)               AS years,
                      count(*) FILTER (WHERE status = 'proposed') AS waiting
               FROM pbl.projects""").fetchone()
        types = conn.execute(
            """SELECT project_type, count(*) AS projects FROM pbl.projects
               WHERE status <> 'rejected' GROUP BY project_type ORDER BY projects DESC""").fetchall()
        pairs = conn.execute(
            """SELECT first_title, first_year, second_title, second_year, similarity, band
               FROM pbl.repeated_ideas ORDER BY similarity DESC""").fetchall()
        # The heatmap shows the 12 most used tags; the rest would be mostly empty rows.
        tags = conn.execute(
            """SELECT tag, academic_year, project_count FROM pbl.tag_trends
               WHERE tag IN (SELECT tag FROM pbl.tag_trends GROUP BY tag
                             ORDER BY sum(project_count) DESC, tag LIMIT 12)""").fetchall()
        load = conn.execute(
            """SELECT u.name AS faculty,
                      count(*) AS projects,
                      count(*) FILTER (WHERE p.status = 'proposed') AS waiting
               FROM pbl.projects p JOIN pbl.users u ON u.user_id = p.faculty_id
               WHERE p.academic_year = %s AND p.status <> 'rejected'
               GROUP BY u.name ORDER BY projects DESC, u.name""", (year,)).fetchall()
    return {"year": year, "totals": totals, "types": types, "pairs": pairs, "tags": tags, "load": load}
