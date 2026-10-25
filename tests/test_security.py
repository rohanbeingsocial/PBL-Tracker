"""What the web app's database login (pbl_app) may and may not do, and
submit_project(), tested through that same login."""
from tests.helpers import error_of, new_link, project_id, unit_vector, user_id

ROHAN, KRISHNA = "1262241783", "1262241766"
KULKARNI = "akulkarni@mitwpu.edu.in"


ABSTRACT = "Students book a washing machine slot in the hostel laundry and get a reminder."


def open_link(conn, purpose="LCA 1") -> str:
    """A new submission link for this year, made through the app's login like the
    Submission links page does, and its code."""
    year = conn.execute("SELECT pbl.current_academic_year() AS y").fetchone()["y"]
    link = new_link(conn, "DBMS-PBL", year, purpose, faculty=KULKARNI)
    return conn.execute("SELECT code FROM pbl.submission_links WHERE submission_link_id = %s", (link,)).fetchone()["code"]


def submit(conn, leader, code, title="Hostel Laundry Slot Booking", prns=(), tags=("Flask", "PostgreSQL"),
           labels=("GitHub",), urls=("https://github.com/example/laundry",), project_type="software",
           report=("Laundry report.pdf", "new/1/laundry.pdf", 52000), ppt=(None, None, None)):
    return conn.execute(
        "SELECT pbl.submit_project(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) AS id",
        (leader, title, ABSTRACT, code, list(prns), project_type, list(tags), list(labels), list(urls),
         unit_vector(9), *report, *ppt),
    ).fetchone()["id"]


CALL = ("SELECT pbl.submit_project(%s, 'Hostel Laundry Slot Booking', %s, %s, %s, 'software', "
        "'{}', '{}', '{}', NULL, %s, %s, %s)")


def test_app_reads_users_but_not_password_hashes(app_db):
    app_db.execute("SELECT user_id, name, email, prn, role, is_admin FROM pbl.users")
    assert error_of(app_db, "SELECT password_hash FROM pbl.users").sqlstate == "42501"
    assert error_of(app_db, "SELECT * FROM pbl.users").sqlstate == "42501"


def test_app_cannot_delete_projects_or_users(app_db):
    assert error_of(app_db, "DELETE FROM pbl.projects").sqlstate == "42501"
    assert error_of(app_db, "DELETE FROM pbl.users").sqlstate == "42501"
    assert error_of(app_db, "TRUNCATE pbl.project_members").sqlstate == "42501"


def test_app_cannot_insert_projects_or_users_directly(app_db):
    err = error_of(app_db, """INSERT INTO pbl.projects (submission_link_id, title, abstract, project_type)
                              VALUES (1, 'Sneaky project', 'Trying to skip submit_project entirely.', 'software')""")
    assert err.sqlstate == "42501"
    err = error_of(app_db, """INSERT INTO pbl.users (name, email, role, password_hash)
                              VALUES ('Sneaky', 'sneaky@mitwpu.edu.in', 'faculty', '$2a$11$x')""")
    assert err.sqlstate == "42501"


def test_app_changes_only_the_review_and_marks_columns(app_db, db):
    lab = project_id(db, "ECE Lab Component Tracker")
    app_db.execute("UPDATE pbl.projects SET marks_public = true WHERE project_id = %s", (lab,))
    app_db.execute("UPDATE pbl.project_members SET marks = 25 WHERE project_id = %s", (lab,))
    for column in ("title = 'Renamed'", "submission_link_id = 1", "decided_at = now()"):
        assert error_of(app_db, f"UPDATE pbl.projects SET {column} WHERE project_id = %s", (lab,)).sqlstate == "42501", column
    for column in ("user_id = 1", "is_leader = false"):
        assert error_of(app_db, f"UPDATE pbl.project_members SET {column} WHERE project_id = %s",
                        (lab,)).sqlstate == "42501", column


def test_app_opens_links_but_cannot_choose_their_code(app_db):
    code = open_link(app_db)
    assert len(code) == 12
    app_db.execute("UPDATE pbl.submission_links SET is_open = false, max_marks = 20 WHERE code = %s", (code,))
    for column in ("code = 'easy123'", "faculty_id = 1", "subject_id = 2", "academic_year = '2020-21'"):
        assert error_of(app_db, f"UPDATE pbl.submission_links SET {column} WHERE code = %s",
                        (code,)).sqlstate == "42501", column
    err = error_of(app_db, """INSERT INTO pbl.submission_links (code, faculty_id, subject_id, academic_year, class_name, purpose)
                              SELECT 'easy123', faculty_id, subject_id, academic_year, class_name, 'Mine'
                              FROM pbl.submission_links WHERE code = %s""", (code,))
    assert err.sqlstate == "42501"


def test_app_cannot_make_itself_a_password(app_db):
    assert error_of(app_db, "UPDATE pbl.users SET password_hash = 'x'").sqlstate == "42501"
    assert error_of(app_db, "SELECT pbl.hash_password('a long password')").sqlstate == "42501"


def test_app_cannot_become_the_owner(app_db):
    err = error_of(app_db, "SET ROLE postgres")
    assert "permission denied to set role" in err.diag.message_primary


def test_submit_project_saves_everything_in_one_go(app_db, db):
    new_id = submit(app_db, user_id(db, ROHAN), open_link(app_db), prns=[KRISHNA],
                    tags=["Flask", "postgresql", "Razorpay"], ppt=("Slides.pptx", "new/1/slides.pptx", 90000))
    card = app_db.execute("SELECT * FROM pbl.project_cards WHERE project_id = %s", (new_id,)).fetchone()
    assert card["status"] == "submitted" and card["members"] == "Rohan Deogaonkar, Krishna Bhand"
    assert sorted(f["kind"] for f in card["files"]) == ["ppt", "report"]
    assert card["tags"] == ["Flask", "PostgreSQL", "Razorpay"]     # existing tags matched ignoring case, a new one added
    assert card["links"][0]["url"] == "https://github.com/example/laundry"
    leader = app_db.execute("SELECT is_leader FROM pbl.project_members WHERE project_id = %s AND user_id = %s",
                            (new_id, user_id(db, ROHAN))).fetchone()
    assert leader["is_leader"] is True


def test_submit_project_saves_nothing_if_one_prn_is_wrong(app_db, db):
    before = app_db.execute("SELECT count(*) AS n FROM pbl.projects").fetchone()["n"]
    err = error_of(app_db, CALL, (user_id(db, ROHAN), ABSTRACT, open_link(app_db), ["1262241766", "9999999999"],
                                  "r.pdf", "new/1/r.pdf", 100))
    assert err.diag.message_primary == "No student with PRN 9999999999"
    assert app_db.execute("SELECT count(*) AS n FROM pbl.projects").fetchone()["n"] == before


def test_submit_project_needs_a_student_and_an_open_link(app_db, db):
    code = open_link(app_db)
    err = error_of(app_db, CALL, (user_id(db, KULKARNI), ABSTRACT, code, [], "r.pdf", "new/1/r.pdf", 100))
    assert err.diag.message_primary == "Only a student can submit a project"
    err = error_of(app_db, CALL, (user_id(db, ROHAN), ABSTRACT, "000000000000", [], "r.pdf", "new/1/r.pdf", 100))
    assert err.diag.message_primary == "No submission link with this code"
    app_db.execute("UPDATE pbl.submission_links SET is_open = false WHERE code = %s", (code,))
    err = error_of(app_db, CALL, (user_id(db, ROHAN), ABSTRACT, code, [], "r.pdf", "new/1/r.pdf", 100))
    assert err.diag.message_primary == "This submission link is closed. Ask your faculty member."


def test_submit_project_lands_in_the_links_class_as_submitted(app_db, db):
    code = open_link(app_db, "Semester PBL retest")
    new_id = submit(app_db, user_id(db, ROHAN), code, title="Hostel Washing Machine Booking")
    row = app_db.execute("""SELECT c.status, c.decided_at, c.academic_year, c.faculty, c.purpose, l.code
                            FROM pbl.project_cards c JOIN pbl.submission_links l USING (submission_link_id)
                            WHERE c.project_id = %s""", (new_id,)).fetchone()
    assert row["status"] == "submitted" and row["decided_at"] is None and row["code"] == code
    assert row["faculty"] == "Prof. A. Kulkarni" and row["purpose"] == "Semester PBL retest"
    err = error_of(app_db, CALL, (user_id(db, KRISHNA), ABSTRACT, code, [ROHAN],
                                  "r.pdf", "new/1/r.pdf", 100))    # Rohan is already in a project here
    assert err.diag.message_primary == f"PRN {ROHAN} already has a project in this submission link"


def test_submit_project_needs_a_pdf_report(app_db, db):
    code = open_link(app_db)
    err = error_of(app_db, CALL, (user_id(db, ROHAN), ABSTRACT, code, [], None, None, None))
    assert err.diag.message_primary == "A project can only be submitted with its report"
    err = error_of(app_db, CALL, (user_id(db, ROHAN), ABSTRACT, code, [], "report.docx", "new/1/report.docx", 100))
    assert err.diag.constraint_name == "reports_are_pdf"
