"""The business rules from 01_tables.sql and 04_triggers.sql, run as the table owner."""
from tests.helpers import error_of, new_link, new_project, project_id, set_embedding, unit_vector, user_id

ROHAN, OM, YASH = "1032240101", "1032230011", "1032230013"
KULKARNI = "akulkarni@mitwpu.edu.in"


def add_member(conn, project, login):
    conn.execute("INSERT INTO pbl.project_members (project_id, user_id) VALUES (%s, %s)",
                 (project, user_id(conn, login)))


def give_marks(conn, project, login, marks):
    conn.execute("UPDATE pbl.project_members SET marks = %s WHERE project_id = %s AND user_id = %s",
                 (marks, project, user_id(conn, login)))


def test_a_team_can_have_any_number_of_members(db):
    lab = project_id(db, "ECE Lab Component Tracker")          # Om and Neha already
    for prn in ("1032240102", "1032240103", "1032240104", "1032240105"):
        add_member(db, lab, prn)
    count = db.execute("SELECT count(*) AS n FROM pbl.project_members WHERE project_id = %s", (lab,)).fetchone()
    assert count["n"] == 6


def test_a_student_can_be_in_several_projects_in_one_year(db):
    for title in ("Hostel Complaint Tracker", "Hostel Room Swap Board", "Hostel Visitor Log"):
        add_member(db, new_project(db, title, "DBMS-PBL", "2026-27"), ROHAN)


def test_one_live_project_per_student_per_link(db):
    link = new_link(db, "DBMS-PBL", "2026-27", "LCA 1")
    first = new_project(db, "Hostel Complaint Tracker", "DBMS-PBL", "2026-27", link=link)
    second = new_project(db, "Hostel Room Swap Board", "DBMS-PBL", "2026-27", link=link)
    add_member(db, first, ROHAN)
    err = error_of(db, "INSERT INTO pbl.project_members (project_id, user_id) VALUES (%s, %s)", (second, user_id(db, ROHAN)))
    assert err.diag.message_primary == f"PRN {ROHAN} already has a project in this submission link"
    set_embedding(db, first, unit_vector(12))
    db.execute("UPDATE pbl.projects SET status = 'rejected' WHERE project_id = %s", (first,))
    add_member(db, second, ROHAN)                    # a rejected project doesn't count


def test_only_students_can_be_team_members(db):
    lab = project_id(db, "ECE Lab Component Tracker")
    err = error_of(db, "INSERT INTO pbl.project_members (project_id, user_id) VALUES (%s, %s)",
                   (lab, user_id(db, KULKARNI)))
    assert err.diag.message_primary == "Only students can be team members"


def test_one_leader_per_team(db):
    lab = project_id(db, "ECE Lab Component Tracker")
    err = error_of(db, "INSERT INTO pbl.project_members VALUES (%s, %s, true)", (lab, user_id(db, YASH)))
    assert err.diag.constraint_name == "project_members_one_leader"


def test_a_submission_link_belongs_to_a_faculty_member(db):
    err = error_of(db, "UPDATE pbl.submission_links SET faculty_id = %s WHERE submission_link_id = %s",
                   (user_id(db, OM), new_link(db, "DBMS-PBL", "2026-27", "LCA 1")))
    assert err.diag.message_primary == "A submission link has to belong to a faculty user"


def test_link_codes_are_random_and_unique(db):
    codes = [db.execute("SELECT code FROM pbl.submission_links WHERE submission_link_id = %s",
                        (new_link(db, "DBMS-PBL", "2026-27", f"LCA {n}"),)).fetchone()["code"] for n in range(3)]
    assert len(set(codes)) == 3 and all(len(c) == 12 for c in codes)
    err = error_of(db, "INSERT INTO pbl.submission_links (faculty_id, subject_id, academic_year, class_name, purpose) "
                       "SELECT faculty_id, subject_id, academic_year, class_name, purpose FROM pbl.submission_links LIMIT 1")
    assert err.diag.constraint_name == "submission_links_once"


def test_each_students_marks_stay_within_the_links_maximum(db):
    lab = project_id(db, "ECE Lab Component Tracker")           # DBMS-PBL link, out of 33
    err = error_of(db, "UPDATE pbl.project_members SET marks = 33.5 WHERE project_id = %s", (lab,))
    assert err.diag.message_primary == "Marks 33.5 are more than the maximum 33.0 for this submission"
    give_marks(db, lab, OM, 33)
    assert error_of(db, "UPDATE pbl.project_members SET marks = -1 WHERE project_id = %s", (lab,)).sqlstate == "23514"


def test_a_link_starts_with_its_subjects_maximum_and_can_change_it(db):
    link = new_link(db, "CN-TH", "2026-27", "Mini project")                  # CN-TH is out of 5
    assert db.execute("SELECT max_marks FROM pbl.submission_links WHERE submission_link_id = %s",
                      (link,)).fetchone()["max_marks"] == 5
    theory = new_project(db, "Packet Loss Visualiser", "CN-TH", "2026-27", status="approved", link=link)
    add_member(db, theory, ROHAN)
    assert "maximum 5.0" in error_of(db, "UPDATE pbl.project_members SET marks = 6 WHERE project_id = %s",
                                     (theory,)).diag.message_primary
    db.execute("UPDATE pbl.submission_links SET max_marks = 10 WHERE submission_link_id = %s", (link,))
    give_marks(db, theory, ROHAN, 6)
    err = error_of(db, "UPDATE pbl.submission_links SET max_marks = 5 WHERE submission_link_id = %s", (link,))
    assert err.diag.message_primary.startswith("A student in this link already has 6.0 marks")


def test_only_approved_projects_can_be_marked(db):
    mess = project_id(db, "Mess Meal Pre-Booking and Feedback")              # still waiting for review
    err = error_of(db, "UPDATE pbl.project_members SET marks = 10 WHERE project_id = %s", (mess,))
    assert err.diag.message_primary == "Only approved projects can be marked (this one is submitted)"


def test_team_score_is_the_average_once_everyone_has_marks(db):
    lab = project_id(db, "ECE Lab Component Tracker")           # Om and Neha
    db.execute("UPDATE pbl.project_members SET marks = NULL WHERE project_id = %s", (lab,))
    score = "SELECT graded, team_score, percent FROM pbl.team_marks WHERE project_id = %s"
    give_marks(db, lab, OM, 30)
    assert db.execute(score, (lab,)).fetchone() == {"graded": 1, "team_score": None, "percent": None}
    db.execute("UPDATE pbl.project_members SET marks = 25 WHERE project_id = %s AND user_id <> %s", (lab, user_id(db, OM)))
    row = db.execute(score, (lab,)).fetchone()
    assert row["graded"] == 2 and float(row["team_score"]) == 27.5 and float(row["percent"]) == 83.3


def test_accounts_need_a_college_email(db):
    insert = """INSERT INTO pbl.users (name, email, role, password_hash) VALUES ('Outsider', %s, 'faculty', '$2a$11$x')"""
    assert error_of(db, insert, ("someone@gmail.com",)).diag.constraint_name == "college_email"
    db.execute(insert, ("new.faculty@mitwpu.edu.in",))


def test_academic_year_format_and_sequence(db):
    insert = """INSERT INTO pbl.submission_links (faculty_id, subject_id, academic_year, class_name, purpose)
                VALUES (%s, 1, %s, 'TY ECE Div A', 'Year check')"""
    faculty = user_id(db, KULKARNI)
    assert error_of(db, insert, (faculty, "2026")).diag.constraint_name == "academic_year_format"
    assert error_of(db, insert, (faculty, "2026-28")).diag.constraint_name == "academic_year_sequence"
    db.execute(insert, (faculty, "2099-00"))     # wraps around the century correctly


def test_project_type_and_link_format(db):
    lab = project_id(db, "ECE Lab Component Tracker")
    assert error_of(db, "UPDATE pbl.projects SET project_type = 'firmware' WHERE project_id = %s", (lab,)).sqlstate == "23514"
    err = error_of(db, "INSERT INTO pbl.project_links (project_id, label, url) VALUES (%s, 'GitHub', 'github.com/x')", (lab,))
    assert err.sqlstate == "23514"
    db.execute("INSERT INTO pbl.project_links (project_id, label, url) VALUES (%s, 'GitHub', 'https://github.com/x/y')", (lab,))


def test_tag_names_are_unique_ignoring_case(db):
    err = error_of(db, "INSERT INTO pbl.tags (name) VALUES ('postgresql')")
    assert err.diag.constraint_name == "tags_name_key"


def test_deleting_a_project_removes_its_members_links_tags_and_files(db):
    lab = project_id(db, "ECE Lab Component Tracker")
    db.execute("INSERT INTO pbl.project_links (project_id, label, url) VALUES (%s, 'Demo', 'https://example.com/demo')", (lab,))
    db.execute("""INSERT INTO pbl.project_files (project_id, kind, file_name, storage_path, size_bytes, uploaded_by)
                  VALUES (%s, 'ppt', 'slides.pptx', 'test/slides.pptx', 1000, %s)""", (lab, user_id(db, OM)))
    db.execute("DELETE FROM pbl.projects WHERE project_id = %s", (lab,))    # the report goes too, with the project
    for table in ("project_members", "project_links", "project_tags", "project_files"):
        left = db.execute(f"SELECT count(*) AS n FROM pbl.{table} WHERE project_id = %s", (lab,)).fetchone()
        assert left["n"] == 0, table


def test_a_user_still_in_a_team_cannot_be_deleted(db):
    assert error_of(db, "DELETE FROM pbl.users WHERE prn = %s", (ROHAN,)).sqlstate == "23503"


def test_a_decision_is_made_once_and_dated(db):
    library = project_id(db, "College Library Management")
    err = error_of(db, "UPDATE pbl.projects SET status = 'submitted' WHERE project_id = %s", (library,))
    assert err.diag.message_primary == "Status cannot change from approved to submitted"
    err = error_of(db, "UPDATE pbl.projects SET status = 'rejected' WHERE project_id = %s", (library,))
    assert err.diag.message_primary == "Status cannot change from approved to rejected"

    mess = project_id(db, "Mess Meal Pre-Booking and Feedback")
    set_embedding(db, mess, unit_vector(11))
    db.execute("UPDATE pbl.projects SET status = 'rejected' WHERE project_id = %s", (mess,))
    row = db.execute("SELECT decided_at FROM pbl.projects WHERE project_id = %s", (mess,)).fetchone()
    assert row["decided_at"] is not None                                    # set by the trigger


def test_a_decided_project_has_a_decision_date(db):
    err = error_of(db, "UPDATE pbl.projects SET decided_at = NULL WHERE title = 'College Library Management'")
    assert err.diag.constraint_name == "decided_once_reviewed"


def test_one_report_per_project_and_it_must_be_a_pdf(db):
    lab = project_id(db, "ECE Lab Component Tracker")                     # has its sample report
    insert = """INSERT INTO pbl.project_files (project_id, kind, file_name, storage_path, size_bytes, uploaded_by)
                VALUES (%s, %s, %s, %s, 1000, %s)"""
    om = user_id(db, OM)
    assert error_of(db, insert, (lab, "report", "second.pdf", "test/second.pdf", om)).diag.constraint_name == "one_file_of_each_kind"
    db.execute("DELETE FROM pbl.project_files WHERE project_id = %s AND kind = 'ppt'", (lab,))
    db.execute(insert, (lab, "ppt", "slides.pptx", "test/slides.pptx", om))
    err = error_of(db, "UPDATE pbl.project_files SET storage_path = 'test/report.docx' WHERE project_id = %s AND kind = 'report'", (lab,))
    assert err.diag.constraint_name == "reports_are_pdf"


def test_a_report_can_be_replaced_but_not_removed(db):
    lab = project_id(db, "ECE Lab Component Tracker")
    err = error_of(db, "DELETE FROM pbl.project_files WHERE project_id = %s AND kind = 'report'", (lab,))
    assert err.diag.message_primary == "A project's report can be replaced but not removed"
    db.execute("""UPDATE pbl.project_files SET file_name = 'Final report.pdf', storage_path = 'test/final.pdf'
                  WHERE project_id = %s AND kind = 'report'""", (lab,))


def test_near_duplicate_needs_a_review_note(db):
    old = project_id(db, "Smart Attendance Using Face Recognition")
    cctv = project_id(db, "Automatic Classroom Attendance from CCTV Footage")
    set_embedding(db, old, unit_vector(0))
    set_embedding(db, cctv, unit_vector(0))       # identical meaning

    err = error_of(db, "UPDATE pbl.projects SET status = 'approved' WHERE project_id = %s", (cctv,))
    assert err.diag.message_primary.startswith(
        'This project is very close to "Smart Attendance Using Face Recognition"')
    assert "review note" in err.diag.message_hint

    db.execute("""UPDATE pbl.projects SET status = 'approved',
                  review_note = 'Uses existing CCTV, no extra camera; extends the 2025-26 project.'
                  WHERE project_id = %s""", (cctv,))


def test_a_new_idea_is_approved_without_a_note(db):
    submitted = project_id(db, "Predicting Students at Risk of Failing")
    set_embedding(db, submitted, unit_vector(7))   # unlike anything else
    db.execute("UPDATE pbl.projects SET status = 'approved' WHERE project_id = %s", (submitted,))


def test_editing_the_abstract_clears_the_stale_embedding(db):
    library = project_id(db, "College Library Management")
    set_embedding(db, library, unit_vector(1))
    db.execute("UPDATE pbl.projects SET abstract = abstract || ' Now with barcode scanning.' "
               "WHERE project_id = %s", (library,))
    row = db.execute("SELECT embedding FROM pbl.projects WHERE project_id = %s", (library,)).fetchone()
    assert row["embedding"] is None


def test_keyword_search_matches_words_only(db):
    titles = [r["title"] for r in db.execute("SELECT title FROM pbl.keyword_search('heart disease')")]
    assert titles == ["Heart Disease Prediction System"]          # the cardiac project never says "heart"
    assert db.execute("SELECT count(*) AS n FROM pbl.keyword_search('heart attack risk')").fetchone()["n"] == 0
    # Malformed input is not an error with websearch_to_tsquery.
    db.execute("SELECT * FROM pbl.keyword_search(%s)", ("'heart & (\" or",))


def test_hybrid_search_puts_projects_found_both_ways_first(db):
    heart = project_id(db, "Heart Disease Prediction System")
    cardiac = project_id(db, "Cardiac Risk Estimation from Patient Vitals")
    db.execute("UPDATE pbl.projects SET embedding = NULL")
    set_embedding(db, heart, unit_vector(5))
    set_embedding(db, cardiac, unit_vector(5))
    rows = db.execute("SELECT * FROM pbl.hybrid_search('heart disease', %s, 5)", (unit_vector(5),)).fetchall()
    assert [r["project_id"] for r in rows[:2]] == [heart, cardiac]     # words + meaning, then meaning only
    assert rows[0]["keyword_rank"] == 1 and rows[1]["keyword_rank"] is None


def test_similar_projects_ranks_by_cosine_similarity(db):
    library = project_id(db, "College Library Management")
    db.execute("UPDATE pbl.projects SET embedding = NULL")
    set_embedding(db, library, unit_vector(2))
    top = db.execute("SELECT * FROM pbl.similar_projects(%s, 1)", (unit_vector(2),)).fetchone()
    assert top["project_id"] == library
    assert abs(top["similarity"] - 1.0) < 1e-6 and top["band"] == "near duplicate"

    err = error_of(db, "SELECT * FROM pbl.similar_projects(%s)", ([0.1] * 383,))
    assert "expected 384 dimensions" in err.diag.message_primary


def test_project_cards_has_one_row_per_project(db):
    counts = db.execute("SELECT (SELECT count(*) FROM pbl.project_cards) AS cards,"
                        "       (SELECT count(*) FROM pbl.projects) AS projects").fetchone()
    assert counts["cards"] == counts["projects"]
    lab = db.execute("SELECT * FROM pbl.project_cards WHERE title = 'ECE Lab Component Tracker'").fetchone()
    assert lab["members"] == "Om Pawar, Neha Karve" and lab["subject"] == "DBMS-PBL"
    assert lab["purpose"] == "Semester PBL" and lab["class_name"].startswith("TY ECE Div")
