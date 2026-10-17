"""The business rules from 01_tables.sql and 04_triggers.sql, run as the table owner."""
from tests.helpers import error_of, new_project, project_id, set_embedding, unit_vector, user_id

ROHAN, OM, YASH = "1032240101", "1032230011", "1032230013"
KULKARNI = "akulkarni@example.edu"


def add_member(conn, project, login):
    conn.execute("INSERT INTO pbl.project_members (project_id, user_id) VALUES (%s, %s)",
                 (project, user_id(conn, login)))


def test_a_team_can_have_any_number_of_members(db):
    lab = project_id(db, "ECE Lab Component Tracker")          # Om and Neha already
    for prn in ("1032240102", "1032240103", "1032240104", "1032240105"):
        add_member(db, lab, prn)
    count = db.execute("SELECT count(*) AS n FROM pbl.project_members WHERE project_id = %s", (lab,)).fetchone()
    assert count["n"] == 6


def test_a_student_can_be_in_several_projects_in_one_year(db):
    for title in ("Hostel Complaint Tracker", "Hostel Room Swap Board", "Hostel Visitor Log"):
        add_member(db, new_project(db, title, "DBMS-PBL", "2026-27"), ROHAN)


def test_only_students_can_be_team_members(db):
    lab = project_id(db, "ECE Lab Component Tracker")
    err = error_of(db, "INSERT INTO pbl.project_members (project_id, user_id) VALUES (%s, %s)",
                   (lab, user_id(db, KULKARNI)))
    assert err.diag.message_primary == "Only students can be team members"


def test_one_leader_per_team(db):
    lab = project_id(db, "ECE Lab Component Tracker")
    err = error_of(db, "INSERT INTO pbl.project_members VALUES (%s, %s, true)", (lab, user_id(db, YASH)))
    assert err.diag.constraint_name == "project_members_one_leader"


def test_assigned_faculty_must_be_faculty(db):
    lab = project_id(db, "ECE Lab Component Tracker")
    err = error_of(db, "UPDATE pbl.projects SET faculty_id = %s WHERE project_id = %s", (user_id(db, OM), lab))
    assert err.diag.message_primary == "The assigned faculty member has to be a faculty user"


def test_marks_cannot_go_above_the_subjects_maximum(db):
    lab = project_id(db, "ECE Lab Component Tracker")           # DBMS-PBL, out of 33
    err = error_of(db, "UPDATE pbl.projects SET marks = 33.5 WHERE project_id = %s", (lab,))
    assert err.diag.message_primary == "Marks 33.5 are more than the maximum 33.0 for this subject"
    db.execute("UPDATE pbl.projects SET marks = 33 WHERE project_id = %s", (lab,))


def test_each_subject_has_its_own_maximum(db):
    theory = new_project(db, "Packet Loss Visualiser", "CN-TH", "2026-27", status="approved")   # out of 5
    err = error_of(db, "UPDATE pbl.projects SET marks = 6 WHERE project_id = %s", (theory,))
    assert "maximum 5.0" in err.diag.message_primary
    db.execute("UPDATE pbl.projects SET marks = 4.5 WHERE project_id = %s", (theory,))
    assert error_of(db, "UPDATE pbl.projects SET marks = -1 WHERE project_id = %s", (theory,)).sqlstate == "23514"


def test_proposals_cannot_be_marked(db):
    mess = project_id(db, "Mess Meal Pre-Booking and Feedback")
    err = error_of(db, "UPDATE pbl.projects SET marks = 10 WHERE project_id = %s", (mess,))
    assert err.diag.message_primary == "Only approved or completed projects can be marked (this one is proposed)"


def test_academic_year_format_and_sequence(db):
    insert = """INSERT INTO pbl.projects (title, abstract, subject_id, faculty_id, academic_year, project_type)
                VALUES ('Year check project', 'Only here to test the academic year constraints.', 1, %s, %s, 'software')"""
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
                  VALUES (%s, 'report', 'report.pdf', 'test/report.pdf', 1000, %s)""", (lab, user_id(db, OM)))
    db.execute("DELETE FROM pbl.projects WHERE project_id = %s", (lab,))
    for table in ("project_members", "project_links", "project_tags", "project_files"):
        left = db.execute(f"SELECT count(*) AS n FROM pbl.{table} WHERE project_id = %s", (lab,)).fetchone()
        assert left["n"] == 0, table


def test_a_user_still_in_a_team_cannot_be_deleted(db):
    assert error_of(db, "DELETE FROM pbl.users WHERE prn = %s", (ROHAN,)).sqlstate == "23503"


def test_status_only_moves_forward(db):
    library = project_id(db, "College Library Management")
    err = error_of(db, "UPDATE pbl.projects SET status = 'proposed' WHERE project_id = %s", (library,))
    assert err.diag.message_primary == "Status cannot change from completed to proposed"


def test_near_duplicate_needs_a_review_note(db):
    old = project_id(db, "Smart Attendance Using Face Recognition")
    cctv = project_id(db, "Automatic Classroom Attendance from CCTV Footage")
    set_embedding(db, old, unit_vector(0))
    set_embedding(db, cctv, unit_vector(0))       # identical meaning

    err = error_of(db, "UPDATE pbl.projects SET status = 'approved' WHERE project_id = %s", (cctv,))
    assert err.diag.message_primary.startswith(
        'This proposal is very close to "Smart Attendance Using Face Recognition"')
    assert "review note" in err.diag.message_hint

    db.execute("""UPDATE pbl.projects SET status = 'approved',
                  review_note = 'Uses existing CCTV, no extra camera; extends the 2025-26 project.'
                  WHERE project_id = %s""", (cctv,))


def test_a_new_idea_is_approved_without_a_note(db):
    proposal = project_id(db, "Predicting Students at Risk of Failing")
    set_embedding(db, proposal, unit_vector(7))   # unlike anything else
    db.execute("UPDATE pbl.projects SET status = 'approved' WHERE project_id = %s", (proposal,))


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
