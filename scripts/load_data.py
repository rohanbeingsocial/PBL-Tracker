"""Loads data/faculty.csv, data/students.csv and data/projects.csv into the database.

projects.csv is laid out like the sheet a department keeps today: one row per
project, with members, tags and links packed into single cells separated by ';'.
This script splits those cells into project_members, project_tags and
project_links, which is the 1NF step from docs/design.md done in code.

Every user gets the password in SEED_PASSWORD (sample data only, see data/README.md).

Everything runs in one transaction, and the triggers check every row on the way in.
Running it twice is safe: rows that already exist are skipped.

    python -m scripts.load_data
"""
import csv
import sys
from datetime import date
from pathlib import Path

import psycopg

from finder.config import require

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def read_csv(name: str) -> list[dict]:
    with open(DATA_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def split(cell: str) -> list[str]:
    return [part.strip() for part in cell.split(";") if part.strip()]


def lookup(conn: psycopg.Connection, query: str) -> dict:
    return {key: value for key, value in conn.execute(query).fetchall()}


def load_users(conn: psycopg.Connection) -> int:
    """Everyone shares SEED_PASSWORD and doesn't have to change it, so the sample data
    can be shown straight away. Real users are added on the People page, which hands
    out a temporary password instead."""
    password = require("SEED_PASSWORD")
    if len(password) < 12:
        sys.exit("SEED_PASSWORD must be at least 12 characters.")
    before = conn.execute("SELECT count(*) FROM pbl.users").fetchone()[0]
    # hash_password() runs bcrypt once per row, each with its own salt (~80 ms each).
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO pbl.users (name, email, role, is_admin, is_active, password_hash, must_change_password)
               VALUES (%s, %s, 'faculty', %s, %s, pbl.hash_password(%s), false)
               ON CONFLICT (email) DO NOTHING""",
            [(r["name"], r["email"].lower(), r["is_admin"] == "true", r["is_active"] == "true", password)
             for r in read_csv("faculty.csv")],
        )
        cur.executemany(
            """INSERT INTO pbl.users (name, email, prn, role, password_hash, must_change_password)
               VALUES (%s, %s, %s, 'student', pbl.hash_password(%s), false)
               ON CONFLICT (email) DO NOTHING""",
            [(r["name"], r["email"].lower(), r["prn"], password) for r in read_csv("students.csv")],
        )
    return conn.execute("SELECT count(*) FROM pbl.users").fetchone()[0] - before


def load_projects(conn: psycopg.Connection) -> int:
    rows = read_csv("projects.csv")
    subjects = lookup(conn, "SELECT code, subject_id FROM pbl.subjects")
    faculty = lookup(conn, "SELECT email, user_id FROM pbl.users WHERE role = 'faculty'")
    students = lookup(conn, "SELECT prn, user_id FROM pbl.users WHERE role = 'student'")

    unknown = {r["subject"] for r in rows} - subjects.keys()
    if unknown:
        sys.exit("Not in the subjects list (add them to sql/07_reference_data.sql first): " + ", ".join(sorted(unknown)))

    added = 0
    for row in rows:
        year = row["academic_year"]
        new = conn.execute(
            """INSERT INTO pbl.projects (title, abstract, subject_id, faculty_id, academic_year,
                                         project_type, status, review_note, marks, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (subject_id, academic_year, lower(title)) DO NOTHING
               RETURNING project_id""",
            (row["title"], row["abstract"], subjects[row["subject"]], faculty[row["faculty_email"].lower()],
             year, row["type"], row["status"], row["review_note"] or None, row["marks"] or None,
             date(int(year[:4]), 8, 1)),  # the sheet has no dates; use the start of term
        ).fetchone()
        if new is None:
            continue
        project_id = new[0]
        added += 1

        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO pbl.project_members (project_id, user_id, is_leader) VALUES (%s, %s, %s)",
                [(project_id, students[prn], i == 0) for i, prn in enumerate(split(row["members"]))],  # first PRN leads
            )
            cur.executemany(
                """INSERT INTO pbl.tags (name) VALUES (%s) ON CONFLICT ((lower(name))) DO NOTHING""",
                [(tag,) for tag in split(row["tags"])],
            )
            cur.executemany(
                """INSERT INTO pbl.project_tags (project_id, tag_id)
                   SELECT %s, tag_id FROM pbl.tags WHERE lower(name) = lower(%s)""",
                [(project_id, tag) for tag in split(row["tags"])],
            )
            cur.executemany(
                "INSERT INTO pbl.project_links (project_id, label, url) VALUES (%s, %s, %s)",
                [(project_id, *link.split("|", 1)) for link in split(row["links"])],   # 'GitHub|https://...'
            )
    return added


def main() -> None:
    with psycopg.connect(require("ADMIN_DATABASE_URL"), connect_timeout=10) as conn:
        print("  adding users (bcrypt, about 10 seconds) ...")
        users = load_users(conn)
        added = load_projects(conn)
    print(f"Loaded {users} new users and {added} new projects. Next: python -m scripts.embed_projects")


if __name__ == "__main__":
    main()
