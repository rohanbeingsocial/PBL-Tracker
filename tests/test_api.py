"""The web server through FastAPI's test client (no browser needed): signing in and
out, sessions, every page's data for every kind of user, what each is refused,
submitting a project with its report, the project page, marks and who sees them, and
links and files. Skipped where FastAPI isn't installed. Tests that add or change
anything put it back at the end."""
import secrets
import time
from dataclasses import replace
from datetime import timedelta

import psycopg
import pytest

testclient = pytest.importorskip("fastapi.testclient")
from api import auth_routes, session  # noqa: E402  (needs fastapi)
from api.app import app  # noqa: E402
from finder import auth, db, storage  # noqa: E402
from finder.config import require  # noqa: E402

LOGINS = {"student": "1032240101", "akash": "1032240102", "faculty": "srao@mitwpu.edu.in",
          "iyer": "riyer@mitwpu.edu.in", "admin": "nshaikh@mitwpu.edu.in"}
PAGES = {
    "student": ["/home", "/reference", "/search", "/trends"],
    "faculty": ["/home", "/reference", "/search", "/trends", "/review"],
    "admin": ["/home", "/reference", "/search", "/trends", "/review", "/people", "/subjects"],
}
PDF = b"%PDF-1.4 a small test report"


@pytest.fixture(scope="module")
def accounts() -> dict[str, db.Account]:
    return {who: auth.sign_in(session.pool(), login, require("SEED_PASSWORD")).account
            for who, login in LOGINS.items()}


@pytest.fixture
def files_here(tmp_path, monkeypatch):
    """Uploaded files go to a temporary folder instead of the bucket."""
    monkeypatch.setattr(storage, "LOCAL_DIR", tmp_path)
    monkeypatch.delenv("B2_BUCKET", raising=False)
    return tmp_path


def client_as(account: db.Account | None, last_seen: float | None = None):
    """A client that is already signed in, the way /api/sign-in leaves it."""
    client = testclient.TestClient(app)
    if account is not None:
        token = secrets.token_urlsafe(32)
        session._sessions[token] = session._Entry(account, last_seen or time.monotonic())
        client.cookies.set(session.COOKIE, token)
    return client


def find(account: db.Account, title: str) -> dict:
    projects = client_as(account).get("/api/home").json()["projects"]
    return next(p for p in projects if p["title"] == title)


def water_tank(account: db.Account) -> dict:
    """Rohan's approved IoT project, guided by Prof. Iyer, not graded yet."""
    return find(account, "Smart Water Tank Level Controller")


def delete_project(project_id: int) -> None:
    """The app's login can't delete projects; tests clean up as the owner."""
    with psycopg.connect(require("ADMIN_DATABASE_URL")) as conn:
        conn.execute("DELETE FROM pbl.projects WHERE project_id = %s", (project_id,))


def submission(**changes) -> dict:
    form = {"title": "Hostel Laundry Slot Booking", "subject_id": "1", "project_type": "software",
            "abstract": "Students book a washing machine slot in the hostel laundry and get a reminder.",
            "teammates": "1032240102", "github": "https://github.com/example/laundry", "demo": ""}
    form.update(changes)
    return form


# Signing in -------------------------------------------------------------------------

def test_nothing_before_signing_in():
    client = client_as(None)
    assert client.get("/api/me").json() == {"account": None}
    for path in ["/api/home", "/api/search", "/api/review", "/api/people", "/api/projects/1", "/api/files/1"]:
        assert client.get(path).status_code == 401


def test_signing_in_sets_an_httponly_cookie():
    client = client_as(None)
    response = client.post("/api/sign-in", json={"login": LOGINS["student"], "password": require("SEED_PASSWORD")})
    assert response.status_code == 200
    assert response.json()["name"] == "Rohan Deogaonkar"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/me").json()["account"]["role"] == "student"


def test_wrong_password_is_refused():
    response = client_as(None).post("/api/sign-in", json={"login": LOGINS["student"], "password": "not the password"})
    assert response.status_code == 401
    assert "don't match" in response.json()["detail"]


@pytest.mark.parametrize("who", PAGES)
def test_every_page_loads(accounts, who):
    client = client_as(accounts[who])
    for path in PAGES[who]:
        assert client.get(f"/api{path}").status_code == 200, path


@pytest.mark.parametrize("who, paths", [
    ("student", ["/review", "/people", "/subjects"]),
    ("faculty", ["/people", "/subjects"]),
])
def test_pages_outside_the_role_are_refused(accounts, who, paths):
    client = client_as(accounts[who])
    for path in paths:
        assert client.get(f"/api{path}").status_code == 403, path


# The project page and who sees what -----------------------------------------------------

def test_a_waiting_project_is_seen_only_by_its_team_and_faculty(accounts):
    cctv = find(accounts["student"], "Automatic Classroom Attendance from CCTV Footage")
    path = f"/api/projects/{cctv['project_id']}"
    own = client_as(accounts["student"]).get(path).json()
    assert own["status"] == "submitted" and own["closest"]["band"] == "near duplicate"
    assert client_as(accounts["faculty"]).get(path).json()["is_faculty"] is True          # Prof. Rao reviews it
    assert client_as(accounts["akash"]).get(path).status_code == 404
    assert client_as(accounts["iyer"]).get(path).status_code == 404


def test_project_page_shows_team_subject_faculty_and_dates(accounts):
    tank = client_as(accounts["akash"]).get(f"/api/projects/{water_tank(accounts['student'])['project_id']}").json()
    assert tank["members"].startswith("Rohan Deogaonkar") and tank["faculty"] == "Prof. R. Iyer"
    assert tank["subject"] == "IOT-PBL" and tank["decided_at"] and tank["created_at"]
    assert [f["kind"] for f in tank["files"]] == ["report"]
    assert tank["can_change"] is False


def test_marks_are_private_until_the_team_shows_them(accounts):
    tank = water_tank(accounts["student"])
    page = f"/api/projects/{tank['project_id']}"
    iyer, rohan, akash = client_as(accounts["iyer"]), client_as(accounts["student"]), client_as(accounts["akash"])
    try:
        assert iyer.put(f"/api/marks/{tank['project_id']}", json={"marks": 27.5}).status_code == 200
        assert rohan.get(page).json()["marks"] == 27.5
        seen = akash.get(page).json()
        assert seen["marks"] is None and seen["marks_hidden"] is True

        switch = f"{page}/marks-public"
        assert akash.put(switch, json={"public": True}).status_code == 403                # not their project
        assert iyer.put(switch, json={"public": True}).status_code == 403                 # only the team decides
        assert rohan.put(switch, json={"public": True}).status_code == 200
        assert akash.get(page).json()["marks"] == 27.5
    finally:
        rohan.put(f"{page}/marks-public", json={"public": False})
        iyer.put(f"/api/marks/{tank['project_id']}", json={"marks": None})


def test_marks_are_entered_by_the_assigned_faculty_only(accounts):
    tank = water_tank(accounts["student"])
    path = f"/api/marks/{tank['project_id']}"
    assert client_as(accounts["faculty"]).put(path, json={"marks": 20}).status_code == 404     # Prof. Rao
    too_many = client_as(accounts["iyer"]).put(path, json={"marks": 34})
    assert too_many.status_code == 400 and "maximum 33.0" in too_many.json()["detail"]


def test_faculty_cannot_decide_on_someone_elses_project(accounts):
    tank = water_tank(accounts["student"])
    response = client_as(accounts["faculty"]).post(f"/api/projects/{tank['project_id']}/decision",
                                                   json={"status": "rejected"})
    assert response.status_code == 409


# Submitting ---------------------------------------------------------------------------

def test_submitting_a_project_with_its_report(accounts, files_here):
    rohan, rao = client_as(accounts["student"]), client_as(accounts["faculty"])
    sent = rohan.post("/api/submissions", data=submission(faculty_id=str(accounts["faculty"].user_id), tags=["Flask"]),
                      files={"report": ("Laundry report.pdf", PDF, "application/pdf"),
                             "ppt": ("Laundry.pptx", b"PK fake slides", "application/octet-stream")})
    assert sent.status_code == 200, sent.text
    project_id = sent.json()["id"]
    try:
        assert sent.json()["faculty"] == "Prof. S. Rao"
        assert len(list(files_here.rglob("*.pdf"))) == 1 and len(list(files_here.rglob("*.pptx"))) == 1
        page = rohan.get(f"/api/projects/{project_id}").json()
        assert page["status"] == "submitted" and page["members"] == "Rohan Deogaonkar, Akash Mane"
        assert page["links"][0]["label"] == "GitHub"
        assert project_id in [p["project_id"] for p in rao.get("/api/review").json()["waiting"]]

        # Approved and graded in one step by the faculty member it was sent to.
        decided = rao.post(f"/api/projects/{project_id}/decision", json={"status": "approved", "marks": 30})
        assert decided.status_code == 200, decided.text
        page = rohan.get(f"/api/projects/{project_id}").json()
        assert page["status"] == "approved" and page["marks"] == 30 and page["decided_at"]
    finally:
        delete_project(project_id)


def test_a_submission_needs_a_pdf_report(accounts, files_here):
    rohan = client_as(accounts["student"])
    form = submission(faculty_id=str(accounts["faculty"].user_id))
    missing = rohan.post("/api/submissions", data=form, files={"ppt": ("slides.pptx", b"PK", "application/octet-stream")})
    assert missing.status_code == 422
    word = rohan.post("/api/submissions", data=form, files={"report": ("report.docx", b"PK", "application/octet-stream")})
    assert word.status_code == 422 and "pdf" in word.json()["detail"].lower()
    fake = rohan.post("/api/submissions", data=form, files={"report": ("report.pdf", b"not a pdf", "application/pdf")})
    assert fake.status_code == 422
    assert not list(files_here.rglob("*"))


def test_only_students_submit(accounts, files_here):
    response = client_as(accounts["faculty"]).post(
        "/api/submissions", data=submission(faculty_id=str(accounts["faculty"].user_id)),
        files={"report": ("report.pdf", PDF, "application/pdf")})
    assert response.status_code == 403


def test_a_failed_submission_leaves_no_files_behind(accounts, files_here):
    response = client_as(accounts["student"]).post(
        "/api/submissions", data=submission(faculty_id=str(accounts["faculty"].user_id), teammates="9999999999"),
        files={"report": ("report.pdf", PDF, "application/pdf")})
    assert response.status_code == 400 and "9999999999" in response.json()["detail"]
    assert not list(files_here.rglob("*.pdf"))


# Files and links --------------------------------------------------------------------

def test_the_report_can_be_read_in_the_browser(accounts):
    tank = water_tank(accounts["student"])
    report = next(f for f in tank["files"] if f["kind"] == "report")
    client = client_as(accounts["akash"])
    inline = client.get(f"/api/files/{report['file_id']}", params={"inline": "true"})
    assert inline.content.startswith(b"%PDF")
    assert inline.headers["content-disposition"].startswith("inline")
    assert inline.headers["content-security-policy"] == "frame-ancestors 'none'"
    download = client.get(f"/api/files/{report['file_id']}")
    assert download.headers["content-disposition"].startswith("attachment")


def test_report_is_replaced_not_added_and_cannot_be_removed(accounts, files_here):
    student = client_as(accounts["student"])
    tank = water_tank(accounts["student"])
    report = next(f for f in tank["files"] if f["kind"] == "report")
    path = f"/api/projects/{tank['project_id']}/files"
    with psycopg.connect(require("ADMIN_DATABASE_URL")) as conn:
        original = conn.execute("SELECT file_name, storage_path, size_bytes FROM pbl.project_files WHERE file_id = %s",
                                (report["file_id"],)).fetchone()
    try:
        new = student.post(path, params={"kind": "report", "name": "Final report.pdf"}, content=PDF)
        assert new.status_code == 200 and new.json()["file_id"] == report["file_id"]
        reports = [f for f in water_tank(accounts["student"])["files"] if f["kind"] == "report"]
        assert [f["file_name"] for f in reports] == ["Final report.pdf"]
        refused = student.delete(f"/api/files/{report['file_id']}")
        assert refused.status_code == 400 and "not removed" in refused.json()["detail"]
    finally:
        with psycopg.connect(require("ADMIN_DATABASE_URL")) as conn:
            conn.execute("UPDATE pbl.project_files SET file_name = %s, storage_path = %s, size_bytes = %s WHERE file_id = %s",
                         (*original, report["file_id"]))


def test_presentation_upload_download_and_delete(accounts, files_here):
    student = client_as(accounts["student"])
    tank = water_tank(accounts["student"])
    uploaded = student.post(f"/api/projects/{tank['project_id']}/files",
                            params={"kind": "ppt", "name": "Water tank.pptx"}, content=b"PK slides")
    assert uploaded.status_code == 200
    file_id = uploaded.json()["file_id"]
    try:
        assert len(list(files_here.rglob("*.pptx"))) == 1          # the bytes are in storage, not the database
        download = client_as(accounts["akash"]).get(f"/api/files/{file_id}")     # anyone signed in can read it
        assert download.content == b"PK slides"
        assert client_as(accounts["akash"]).delete(f"/api/files/{file_id}").status_code == 403
    finally:
        assert student.delete(f"/api/files/{file_id}").status_code == 200
    assert not list(files_here.rglob("*.pptx"))


def test_links_can_be_added_and_removed_by_the_team(accounts):
    student = client_as(accounts["student"])
    tank = water_tank(accounts["student"])
    bad = student.post(f"/api/projects/{tank['project_id']}/links", json={"label": "GitHub", "url": "github.com/x"})
    assert bad.status_code == 422

    added = student.post(f"/api/projects/{tank['project_id']}/links",
                         json={"label": "Demo video", "url": "https://example.com/tank-demo"})
    link_id = added.json()["link_id"]
    try:
        assert any(link["link_id"] == link_id for link in water_tank(accounts["student"])["links"])
        assert client_as(accounts["faculty"]).delete(f"/api/links/{link_id}").status_code == 403   # not their project
    finally:
        assert student.delete(f"/api/links/{link_id}").status_code == 200


# Search, admin pages, sessions -----------------------------------------------------------

def test_search_shows_only_approved_projects(accounts):
    rows = client_as(accounts["student"]).get("/api/search", params={"q": "classroom attendance", "mode": "Keywords"}).json()["rows"]
    assert rows and all(r["status"] == "approved" for r in rows)
    assert "Automatic Classroom Attendance from CCTV Footage" not in [r["title"] for r in rows]


def test_search_filters_by_subject_type_and_stack(accounts):
    client = client_as(accounts["student"])
    rows = client.get("/api/search", params={"subject": "IOT-PBL", "kind": "hardware", "tag": "ESP32"}).json()["rows"]
    assert rows and all(r["subject"] == "IOT-PBL" and r["project_type"] == "hardware" and "ESP32" in r["tags"]
                        for r in rows)
    assert all("marks" not in r for r in rows)


def test_meaning_search_finds_projects_that_share_no_words(accounts):
    pytest.importorskip("sentence_transformers")
    rows = client_as(accounts["student"]).get(
        "/api/search", params={"q": "predict heart attack risk from patient data", "mode": "Meaning"}).json()["rows"]
    assert rows[0]["title"] == "Cardiac Risk Estimation from Patient Vitals"


def test_each_subject_lists_its_own_maximum(accounts):
    subjects = {s["code"]: s["max_marks"] for s in client_as(accounts["admin"]).get("/api/subjects").json()["subjects"]}
    assert subjects["DBMS-PBL"] == 33 and subjects["CN-TH"] == 5


def test_new_people_need_a_college_email(accounts):
    response = client_as(accounts["admin"]).post("/api/people", json={
        "name": "Outside Person", "email": "someone@gmail.com", "prn": "1032249990", "role": "student"})
    assert response.status_code == 422 and "@mitwpu.edu.in" in response.json()["detail"]


def test_sign_out_ends_the_session(accounts):
    client = client_as(accounts["faculty"])
    client.post("/api/sign-out")
    assert client.get("/api/home").status_code == 401


def test_idle_session_ends(accounts):
    client = client_as(accounts["student"], last_seen=time.monotonic() - 31 * 60)
    assert client.get("/api/home").status_code == 401


def test_session_ends_after_a_password_change_elsewhere(accounts):
    # A sign-in from before the user's last password change (or reset) is no longer valid.
    stale = replace(accounts["student"], signed_in_at=accounts["student"].signed_in_at - timedelta(days=3650))
    client = client_as(stale)
    response = client.get("/api/home")
    assert response.status_code == 401
    assert "session has ended" in response.json()["detail"]
    assert client.get("/api/me").json() == {"account": None}


def test_temporary_password_opens_nothing_else(accounts):
    client = client_as(replace(accounts["student"], must_change_password=True))
    assert client.get("/api/me").json()["account"]["must_change_password"] is True
    assert client.get("/api/home").status_code == 403


def test_demo_switcher_is_off_unless_turned_on(monkeypatch):
    monkeypatch.setattr(auth_routes, "DEMO_ON", False)
    client = client_as(None)
    assert client.get("/api/demo").json() == {"enabled": False, "accounts": []}
    assert client.post("/api/demo/sign-in", json={"login": LOGINS["admin"]}).status_code == 404


def test_demo_switcher_only_signs_in_listed_accounts(monkeypatch):
    monkeypatch.setattr(auth_routes, "DEMO_ON", True)
    client = client_as(None)
    assert client.post("/api/demo/sign-in", json={"login": "pjoshi@mitwpu.edu.in"}).status_code == 404
    response = client.post("/api/demo/sign-in", json={"login": LOGINS["faculty"]})
    assert response.status_code == 200 and response.json()["role"] == "faculty"
