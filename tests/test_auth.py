"""Sign-in and passwords (sql/03_functions.sql). Needs the users that
scripts/load_data.py makes with SEED_PASSWORD."""
import pytest

from finder.config import require
from tests.helpers import error_of, user_id

STUDENT, STUDENT_EMAIL = "1262241783", "rohan.deogaonkar@mitwpu.edu.in"
FACULTY, LEFT_COLLEGE, ADMIN = "akulkarni@mitwpu.edu.in", "kmenon@mitwpu.edu.in", "admin@mitwpu.edu.in"


@pytest.fixture(scope="module")
def password() -> str:
    return require("SEED_PASSWORD")


def sign_in(conn, login: str, password: str) -> dict:
    return conn.execute("SELECT * FROM pbl.sign_in(%s, %s)", (login, password)).fetchone()


def test_students_sign_in_with_prn_or_email_and_faculty_with_email(app_db, password):
    by_prn = sign_in(app_db, STUDENT, password)
    assert (by_prn["status"], by_prn["role"], by_prn["login"]) == ("ok", "student", STUDENT)
    assert by_prn["name"] == "Rohan Deogaonkar" and by_prn["is_admin"] is False

    by_email = sign_in(app_db, f"  {STUDENT_EMAIL.upper()} ", password)     # spaces and case don't matter
    assert by_email["user_id"] == by_prn["user_id"]
    copied = STUDENT_EMAIL.replace("@", "@⁠")                     # with a word joiner, as copied from a web page
    assert sign_in(app_db, copied, password)["user_id"] == by_prn["user_id"]

    faculty = sign_in(app_db, FACULTY, password)
    assert (faculty["status"], faculty["role"], faculty["prn"]) == ("ok", "faculty", None)
    assert sign_in(app_db, ADMIN, password)["is_admin"] is True


def test_unknown_login_and_wrong_password_get_the_same_answer(app_db, password):
    wrong = sign_in(app_db, STUDENT, password + "x")
    unknown = sign_in(app_db, "nobody@mitwpu.edu.in", password)
    assert wrong == unknown
    assert wrong["status"] == "wrong" and all(v is None for k, v in wrong.items() if k != "status")


def test_switched_off_user_is_told_only_after_the_right_password(app_db, password):
    assert sign_in(app_db, LEFT_COLLEGE, password)["status"] == "disabled"
    assert sign_in(app_db, LEFT_COLLEGE, "not-the-password")["status"] == "wrong"


def test_passwords_are_stored_as_bcrypt_hashes(db, password):
    stored = db.execute("SELECT password_hash FROM pbl.users WHERE prn = %s", (STUDENT,)).fetchone()["password_hash"]
    assert stored.startswith("$2a$11$") and password not in stored


def test_change_password_needs_the_current_one(app_db, password):
    me = sign_in(app_db, STUDENT, password)["user_id"]
    assert app_db.execute("SELECT pbl.change_password(%s, 'wrong-current', 'a new password')",
                          (me,)).fetchone()["change_password"] is None
    changed = app_db.execute("SELECT pbl.change_password(%s, %s, 'a new password 2026')",
                             (me, password)).fetchone()["change_password"]
    assert changed is not None
    assert sign_in(app_db, STUDENT, "a new password 2026")["status"] == "ok"
    assert sign_in(app_db, STUDENT, password)["status"] == "wrong"


def test_new_password_must_be_8_to_72_characters(app_db, password):
    me = sign_in(app_db, STUDENT, password)["user_id"]
    assert error_of(app_db, "SELECT pbl.change_password(%s, %s, 'short')", (me, password)).sqlstate == "23514"
    assert error_of(app_db, "SELECT pbl.change_password(%s, %s, %s)", (me, password, "x" * 73)).sqlstate == "23514"


def test_create_user_hands_out_a_temporary_password(app_db):
    temporary = app_db.execute(
        "SELECT pbl.create_user('Tanvi Joshi', 'Tanvi.Joshi@mitwpu.edu.in', '1032249999', 'student', false) AS t"
    ).fetchone()["t"]
    first = sign_in(app_db, "tanvi.joshi@mitwpu.edu.in", temporary)
    assert first["status"] == "ok" and first["must_change_password"] is True


def test_create_user_only_takes_college_emails(app_db):
    err = error_of(app_db, "SELECT pbl.create_user('Outsider', 'someone@gmail.com', '', 'faculty', false)")
    assert err.diag.constraint_name == "college_email"


def test_create_user_checks_role_and_prn(app_db):
    no_prn = error_of(app_db, "SELECT pbl.create_user('New Student', 'new.student@mitwpu.edu.in', '', 'student', false)")
    assert no_prn.diag.constraint_name == "students_have_a_prn"
    admin_student = error_of(app_db, "SELECT pbl.create_user('Odd', 'odd@mitwpu.edu.in', '1032249998', 'student', true)")
    assert admin_student.diag.constraint_name == "only_faculty_are_admins"
    taken = error_of(app_db, "SELECT pbl.create_user('Copy', %s, '', 'faculty', false)", (FACULTY,))
    assert taken.sqlstate == "23505"


def test_reset_password_replaces_the_old_one(app_db, db, password):
    temporary = app_db.execute("SELECT pbl.reset_password(%s) AS t", (user_id(db, FACULTY),)).fetchone()["t"]
    assert sign_in(app_db, FACULTY, password)["status"] == "wrong"
    assert sign_in(app_db, FACULTY, temporary)["must_change_password"] is True
