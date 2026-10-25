import psycopg
import pytest


def error_of(conn: psycopg.Connection, query: str, params=None) -> psycopg.Error:
    """Run a statement that is expected to fail and return the error. The savepoint
    from conn.transaction() keeps the surrounding test transaction usable."""
    with pytest.raises(psycopg.Error) as info, conn.transaction():
        conn.execute(query, params)
    return info.value


def project_id(conn: psycopg.Connection, title: str) -> int:
    return conn.execute("SELECT project_id FROM pbl.projects WHERE title = %s", (title,)).fetchone()["project_id"]


def user_id(conn: psycopg.Connection, login: str) -> int:
    """By PRN or email."""
    return conn.execute("SELECT user_id FROM pbl.users WHERE prn = %s OR email = %s",
                        (login, login)).fetchone()["user_id"]


def unit_vector(position: int) -> list[float]:
    """A 384-number vector pointing along one axis. Two of them are either identical
    (similarity 1) or completely unrelated (similarity 0)."""
    vector = [0.0] * 384
    vector[position] = 1.0
    return vector


def set_embedding(conn: psycopg.Connection, project: int, vector: list[float]) -> None:
    conn.execute("UPDATE pbl.projects SET embedding = %s WHERE project_id = %s", (vector, project))


def new_link(conn: psycopg.Connection, subject: str, year: str, purpose: str,
             faculty: str = "akulkarni@mitwpu.edu.in", max_marks: float | None = None) -> int:
    """A submission link of its own, so tests don't run into the one-project-per-link rule."""
    return conn.execute(
        """INSERT INTO pbl.submission_links (faculty_id, subject_id, academic_year, class_name, purpose, max_marks)
           SELECT (SELECT user_id FROM pbl.users WHERE email = %s), subject_id, %s, 'Test class', %s, %s
           FROM pbl.subjects WHERE code = %s
           RETURNING submission_link_id""",
        (faculty, year, purpose, max_marks, subject),
    ).fetchone()["submission_link_id"]


def new_project(conn: psycopg.Connection, title: str, subject: str, year: str, status: str = "submitted",
                link: int | None = None) -> int:
    return conn.execute(
        """INSERT INTO pbl.projects (submission_link_id, title, abstract, project_type, status, decided_at)
           VALUES (%s, %s, 'A test project used only inside one test transaction.', 'software', %s,
                   CASE WHEN %s = 'submitted' THEN NULL ELSE now() END)
           RETURNING project_id""",
        (link or new_link(conn, subject, year, f"Test: {title}"), title, status, status),
    ).fetchone()["project_id"]


def link_code(conn: psycopg.Connection, project: int) -> str:
    """The code of the submission link a project came in through."""
    return conn.execute(
        """SELECT l.code FROM pbl.submission_links l JOIN pbl.projects p USING (submission_link_id)
           WHERE p.project_id = %s""", (project,)).fetchone()["code"]
