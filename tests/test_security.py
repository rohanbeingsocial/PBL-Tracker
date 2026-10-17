"""What the web app's database login (pbl_app) may and may not do, and
submit_project(), tested through that same login."""
from tests.helpers import error_of, project_id, unit_vector, user_id

ROHAN, AKASH = "1032240101", "1032240102"
KULKARNI = "akulkarni@example.edu"


def submit(conn, leader, title="Hostel Laundry Slot Booking", prns=(), tags=("Flask", "PostgreSQL"),
           labels=("GitHub",), urls=("https://github.com/example/laundry",), faculty=None, project_type="software"):
    return conn.execute(
        "SELECT pbl.submit_project(%s, %s, %s, 1, %s, %s, %s, %s, %s, %s, %s) AS id",
        (leader, title, "Students book a washing machine slot in the hostel laundry and get a reminder.",
         faculty, list(prns), project_type, list(tags), list(labels), list(urls), unit_vector(9)),
    ).fetchone()["id"]


def test_app_reads_users_but_not_password_hashes(app_db):
    app_db.execute("SELECT user_id, name, email, prn, role, is_admin FROM pbl.users")
    assert error_of(app_db, "SELECT password_hash FROM pbl.users").sqlstate == "42501"
    assert error_of(app_db, "SELECT * FROM pbl.users").sqlstate == "42501"


def test_app_cannot_delete_projects_or_users(app_db):
    assert error_of(app_db, "DELETE FROM pbl.projects").sqlstate == "42501"
    assert error_of(app_db, "DELETE FROM pbl.users").sqlstate == "42501"
    assert error_of(app_db, "TRUNCATE pbl.project_members").sqlstate == "42501"


def test_app_cannot_insert_projects_or_users_directly(app_db):
    err = error_of(app_db, """INSERT INTO pbl.projects (title, abstract, subject_id, faculty_id, academic_year, project_type)
                              VALUES ('Sneaky project', 'Trying to skip submit_project entirely.', 1, 1, '2026-27', 'software')""")
    assert err.sqlstate == "42501"
    err = error_of(app_db, """INSERT INTO pbl.users (name, email, role, password_hash)
                              VALUES ('Sneaky', 'sneaky@example.edu', 'faculty', '$2a$11$x')""")
    assert err.sqlstate == "42501"


def test_app_changes_only_the_review_and_marks_columns(app_db, db):
    lab = project_id(db, "ECE Lab Component Tracker")
    app_db.execute("UPDATE pbl.projects SET marks = 25 WHERE project_id = %s", (lab,))
    for column in ("title = 'Renamed'", "faculty_id = 1", "subject_id = 2", "academic_year = '2020-21'"):
        assert error_of(app_db, f"UPDATE pbl.projects SET {column} WHERE project_id = %s", (lab,)).sqlstate == "42501", column


def test_app_cannot_make_itself_a_password(app_db):
    assert error_of(app_db, "UPDATE pbl.users SET password_hash = 'x'").sqlstate == "42501"
    assert error_of(app_db, "SELECT pbl.hash_password('a long password')").sqlstate == "42501"


def test_app_cannot_become_the_owner(app_db):
    err = error_of(app_db, "SET ROLE postgres")
    assert "permission denied to set role" in err.diag.message_primary


def test_submit_project_saves_everything_in_one_go(app_db, db):
    new_id = submit(app_db, user_id(db, ROHAN), prns=[AKASH], faculty=user_id(db, KULKARNI),
                    tags=["Flask", "postgresql", "Razorpay"])
    card = app_db.execute("SELECT * FROM pbl.project_cards WHERE project_id = %s", (new_id,)).fetchone()
    assert card["status"] == "proposed" and card["members"] == "Rohan Deogaonkar, Akash Mane"
    assert card["tags"] == ["Flask", "PostgreSQL", "Razorpay"]     # existing tags matched ignoring case, a new one added
    assert card["links"][0]["url"] == "https://github.com/example/laundry"
    leader = app_db.execute("SELECT is_leader FROM pbl.project_members WHERE project_id = %s AND user_id = %s",
                            (new_id, user_id(db, ROHAN))).fetchone()
    assert leader["is_leader"] is True


def test_submit_project_saves_nothing_if_one_prn_is_wrong(app_db, db):
    before = app_db.execute("SELECT count(*) AS n FROM pbl.projects").fetchone()["n"]
    err = error_of(app_db, "SELECT pbl.submit_project(%s, 'Hostel Laundry Slot Booking', %s, 1, %s, %s, 'software', "
                           "'{}', '{}', '{}', NULL)",
                   (user_id(db, ROHAN), "Students book a washing machine slot in the hostel laundry.",
                    user_id(db, KULKARNI), ["1032240102", "9999999999"]))
    assert err.diag.message_primary == "No student with PRN 9999999999"
    assert app_db.execute("SELECT count(*) AS n FROM pbl.projects").fetchone()["n"] == before


def test_submit_project_refuses_faculty_as_leader_and_students_as_faculty(app_db, db):
    err = error_of(app_db, "SELECT pbl.submit_project(%s, 'Hostel Laundry Slot Booking', %s, 1, %s, '{}', 'software', "
                           "'{}', '{}', '{}', NULL)",
                   (user_id(db, KULKARNI), "Students book a washing machine slot in the hostel laundry.", user_id(db, KULKARNI)))
    assert err.diag.message_primary == "Only a student can submit a project"
    err = error_of(app_db, "SELECT pbl.submit_project(%s, 'Hostel Laundry Slot Booking', %s, 1, %s, '{}', 'software', "
                           "'{}', '{}', '{}', NULL)",
                   (user_id(db, ROHAN), "Students book a washing machine slot in the hostel laundry.", user_id(db, AKASH)))
    assert err.diag.message_primary == "Choose a faculty member from the current list"


def test_submit_project_always_starts_as_a_proposal_this_year(app_db, db):
    new_id = submit(app_db, user_id(db, ROHAN), faculty=user_id(db, KULKARNI))
    row = app_db.execute("SELECT status, academic_year, pbl.current_academic_year() AS now FROM pbl.projects "
                         "WHERE project_id = %s", (new_id,)).fetchone()
    assert row["status"] == "proposed" and row["academic_year"] == row["now"]
