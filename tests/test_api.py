"""The web server through FastAPI's test client (no browser needed): signing in and
out, sessions, every page's data for every kind of user, what each is refused, and
links, files and marks. Skipped where FastAPI isn't installed. The tests that add
links, files or marks remove them again at the end."""
import secrets
import time
from dataclasses import replace
from datetime import timedelta

import pytest

testclient = pytest.importorskip("fastapi.testclient")
from api import auth_routes, session  # noqa: E402  (needs fastapi)
from api.app import app  # noqa: E402
from finder import auth, db, storage  # noqa: E402
from finder.config import require  # noqa: E402

LOGINS = {"student": "1032240101", "faculty": "srao@example.edu", "iyer": "riyer@example.edu",
          "admin": "nshaikh@example.edu"}
PAGES = {
    "student": ["/home", "/reference", "/search", "/trends"],
    "faculty": ["/home", "/reference", "/search", "/trends", "/review", "/marks"],
    "admin": ["/home", "/reference", "/search", "/trends", "/review", "/marks", "/people", "/subjects"],
}


@pytest.fixture(scope="module")
def accounts() -> dict[str, db.Account]:
    return {who: auth.sign_in(session.pool(), login, require("SEED_PASSWORD")).account
            for who, login in LOGINS.items()}


@pytest.fixture
def files_here(tmp_path, monkeypatch):
    """Uploaded files go to a temporary folder instead of uploads/."""
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


def water_tank(account: db.Account) -> dict:
    """Rohan's approved IoT project, guided by Prof. Iyer."""
    projects = client_as(account).get("/api/home").json()["projects"]
    return next(p for p in projects if p["title"] == "Smart Water Tank Level Controller")


def test_nothing_before_signing_in():
    client = client_as(None)
    assert client.get("/api/me").json() == {"account": None}
    for path in ["/api/home", "/api/search", "/api/review", "/api/people", "/api/files/1"]:
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
    ("student", ["/review", "/marks", "/people", "/subjects"]),
    ("faculty", ["/people", "/subjects"]),
])
def test_pages_outside_the_role_are_refused(accounts, who, paths):
    client = client_as(accounts[who])
    for path in paths:
        assert client.get(f"/api{path}").status_code == 403, path


def test_student_home_shows_the_near_duplicate_proposal(accounts):
    projects = client_as(accounts["student"]).get("/api/home").json()["projects"]
    cctv = next(p for p in projects if p["title"].startswith("Automatic Classroom Attendance"))
    assert cctv["band"] == "near duplicate" and cctv["closest_abstract"]


def test_faculty_queue_holds_only_their_own_proposals(accounts):
    waiting = client_as(accounts["faculty"]).get("/api/review").json()["waiting"]
    assert waiting and {p["faculty"] for p in waiting} == {"Prof. S. Rao"}


def test_faculty_cannot_decide_on_someone_elses_project(accounts):
    tank = water_tank(accounts["student"])
    response = client_as(accounts["faculty"]).post(f"/api/projects/{tank['project_id']}/decision",
                                                   json={"status": "completed"})
    assert response.status_code == 409


def test_marks_are_entered_by_the_assigned_faculty_only(accounts):
    tank = water_tank(accounts["student"])
    path = f"/api/marks/{tank['project_id']}"
    assert client_as(accounts["faculty"]).put(path, json={"marks": 20}).status_code == 404     # Prof. Rao

    iyer = client_as(accounts["iyer"])
    too_many = iyer.put(path, json={"marks": 34})
    assert too_many.status_code == 400 and "maximum 33.0" in too_many.json()["detail"]
    try:
        assert iyer.put(path, json={"marks": 27.5}).status_code == 200
        assert water_tank(accounts["student"])["marks"] == 27.5
    finally:
        iyer.put(path, json={"marks": None})


def test_only_students_submit_proposals(accounts):
    response = client_as(accounts["faculty"]).post("/api/proposals", json={
        "title": "Faculty trying to submit", "abstract": "x" * 40, "subject_id": 1, "faculty_id": 1,
        "project_type": "software"})
    assert response.status_code == 403


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


def test_reports_upload_download_and_delete(accounts, files_here):
    student = client_as(accounts["student"])
    tank = water_tank(accounts["student"])
    content = b"%PDF-1.4 smart water tank report"
    uploaded = student.post(f"/api/projects/{tank['project_id']}/files",
                            params={"kind": "report", "name": "Water tank report.pdf"}, content=content)
    assert uploaded.status_code == 200
    file_id = uploaded.json()["file_id"]
    try:
        assert len(list(files_here.rglob("*.pdf"))) == 1          # the bytes are in storage, not the database
        download = client_as(accounts["faculty"]).get(f"/api/files/{file_id}")     # any signed-in user can read
        assert download.content == content
        assert "Water%20tank%20report.pdf" in download.headers["content-disposition"]
        assert client_as(accounts["faculty"]).delete(f"/api/files/{file_id}").status_code == 403
    finally:
        assert student.delete(f"/api/files/{file_id}").status_code == 200
    assert not list(files_here.rglob("*.pdf"))


def test_only_reports_and_presentations_are_accepted(accounts, files_here):
    student = client_as(accounts["student"])
    tank = water_tank(accounts["student"])
    for kind, name in [("report", "notes.txt"), ("ppt", "slides.docx"), ("report", "run.exe")]:
        response = student.post(f"/api/projects/{tank['project_id']}/files", params={"kind": kind, "name": name},
                                content=b"x")
        assert response.status_code == 422, name
    assert not list(files_here.rglob("*"))


def test_each_subject_lists_its_own_maximum(accounts):
    subjects = {s["code"]: s["max_marks"] for s in client_as(accounts["admin"]).get("/api/subjects").json()["subjects"]}
    assert subjects["DBMS-PBL"] == 33 and subjects["CN-TH"] == 5


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
    assert client.post("/api/demo/sign-in", json={"login": "pjoshi@example.edu"}).status_code == 404
    response = client.post("/api/demo/sign-in", json={"login": LOGINS["faculty"]})
    assert response.status_code == 200 and response.json()["role"] == "faculty"


def test_meaning_search_finds_projects_that_share_no_words(accounts):
    pytest.importorskip("sentence_transformers")
    rows = client_as(accounts["student"]).get(
        "/api/search", params={"q": "predict heart attack risk from patient data", "mode": "Meaning"}).json()["rows"]
    assert rows[0]["title"] == "Cardiac Risk Estimation from Patient Vitals"


def test_search_filters_by_subject_type_and_stack(accounts):
    client = client_as(accounts["student"])
    rows = client.get("/api/search", params={"subject": "IOT-PBL", "kind": "hardware", "tag": "ESP32"}).json()["rows"]
    assert rows and all(r["subject"] == "IOT-PBL" and r["project_type"] == "hardware" and "ESP32" in r["tags"]
                        for r in rows)
