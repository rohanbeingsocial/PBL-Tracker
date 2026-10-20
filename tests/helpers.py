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


def new_project(conn: psycopg.Connection, title: str, subject: str, year: str, status: str = "submitted") -> int:
    return conn.execute(
        """INSERT INTO pbl.projects (title, abstract, subject_id, faculty_id, academic_year, project_type, status, decided_at)
           SELECT %s, 'A test project used only inside one test transaction.', subject_id,
                  (SELECT user_id FROM pbl.users WHERE email = 'akulkarni@mitwpu.edu.in'), %s, 'software', %s,
                  CASE WHEN %s = 'submitted' THEN NULL ELSE now() END
           FROM pbl.subjects WHERE code = %s
           RETURNING project_id""",
        (title, year, status, status, subject),
    ).fetchone()["project_id"]
