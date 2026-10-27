"""Every page and action of the site in a real browser (Playwright), as each kind of user:
signing in and out, the demo switcher, the theme, every dashboard, search, trends,
submission links from making one to the marks export, submitting through a link, the
project page with its report, links and files, review and marks, who sees what, people
and subjects.

Runs only when E2E_URL points at a running server that serves the built app (python -m
api after npm run build, so http://127.0.0.1:8000), with ADMIN_DATABASE_URL and the
storage settings of the same database. Use a scratch copy of the sample data: the tests
add a submission link, two projects, a subject, a tag and two people, and remove them
again at the end. The tests depend on each other and run in file order.

    pip install playwright==1.61.0 && playwright install chromium
    E2E_URL=http://127.0.0.1:8000 pytest tests/test_browser.py -v

E2E_HEADED=1 shows the browser while it runs.
"""
import csv
import io
import os
import re
import secrets
from datetime import date
from pathlib import Path

import psycopg
import pytest

URL = os.environ.get("E2E_URL", "").rstrip("/")
if not URL:
    pytest.skip("E2E_URL isn't set, so there is no server to open.", allow_module_level=True)
sync_api = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from finder import storage  # noqa: E402
from finder.config import require  # noqa: E402
from scripts import sample_reports  # noqa: E402

expect.set_options(timeout=15_000)

ROHAN, KRISHNA = "1262241783", "1262241766"
TEAMMATES = "1032240105, 1032240106"
LAUNDRY_TEAM = "1032240107, 1032240108"     # Rohan's teammates; the link takes teams of 3
RAO, IYER, ADMIN = "srao@mitwpu.edu.in", "riyer@mitwpu.edu.in", "admin@mitwpu.edu.in"
CLASS = "TY ECE Div E2E"
LAST_DATE = f"{date.today().year + 1}-03-31T17:30"        # typed into the link's last date box
LAST_DATE_SHOWN = f"31 Mar {date.today().year + 1}, 17:30"

# Very close to a sample project, so approving it needs a note.
CCTV = "Attendance from classroom CCTV"
CCTV_ABSTRACT = ("Recognise student faces from the CCTV camera in each classroom and mark "
                 "attendance automatically during the first ten minutes.")
LAUNDRY_ABSTRACT = "Students book a washing machine slot in the hostel laundry and get a reminder."

NAV = {
    ROHAN: ["Dashboard", "Search projects", "Submit a project", "Trends"],
    RAO: ["Dashboard", "Search projects", "Trends", "Submission links"],
    ADMIN: ["Dashboard", "Search projects", "Trends", "Submission links", "People", "Subjects"],
}
HOME = {ROHAN: "Hello, Rohan", RAO: "Hello, Prof. S. Rao", ADMIN: "Overview"}
OUTSIDE = {ROHAN: ["/links", "/people", "/subjects"], RAO: ["/submit", "/people", "/subjects"], ADMIN: ["/submit"]}


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        launched = p.chromium.launch(headless=os.environ.get("E2E_HEADED") != "1")
        yield launched
        launched.close()


@pytest.fixture(scope="module")
def made():
    """What the tests add, shared between them and removed at the end (as the owner;
    the app's login can't delete any of it)."""
    stamp = secrets.token_hex(3)
    things = {
        "purpose": f"E2E check {stamp}",
        "tag": f"E2E-{stamp}",
        "subject": f"E2E-{stamp.upper()}",
        "prn": f"1039{secrets.randbelow(10**6):06d}",
        "student": f"e2e.student.{stamp}@mitwpu.edu.in",
        "faculty": f"e2e.faculty.{stamp}@mitwpu.edu.in",
        "stamp": stamp,
    }
    yield things
    with psycopg.connect(require("ADMIN_DATABASE_URL")) as conn:
        links = [r[0] for r in conn.execute(
            "SELECT submission_link_id FROM pbl.submission_links WHERE purpose LIKE %s",
            (f"E2E check {stamp}%",))]
        paths = [r[0] for r in conn.execute(
            """SELECT f.storage_path FROM pbl.project_files f JOIN pbl.projects p USING (project_id)
               WHERE p.submission_link_id = ANY(%s)""", (links,))]
        conn.execute("DELETE FROM pbl.projects WHERE submission_link_id = ANY(%s)", (links,))
        conn.execute("DELETE FROM pbl.submission_links WHERE submission_link_id = ANY(%s)", (links,))
        conn.execute("DELETE FROM pbl.tags WHERE name = %s", (things["tag"],))
        conn.execute("DELETE FROM pbl.subjects WHERE code = %s", (things["subject"],))
        conn.execute("DELETE FROM pbl.users WHERE email IN (%s, %s)", (things["student"], things["faculty"]))
    for path in paths:
        storage.delete(path)


@pytest.fixture(scope="module")
def files(tmp_path_factory) -> dict[str, Path]:
    folder = tmp_path_factory.mktemp("files")
    contents = {
        "report.pdf": sample_reports.report(CCTV, "2026-27", "ML-PBL", "Prof. S. Rao", ["Krishna Bhand"], CCTV_ABSTRACT),
        "report-v2.pdf": sample_reports.report(f"{CCTV}, second version", "2026-27", "ML-PBL", "Prof. S. Rao",
                                               ["Krishna Bhand"], CCTV_ABSTRACT),
        "laundry.pdf": sample_reports.report("Hostel Laundry Slot Booking", "2026-27", "ML-PBL", "Prof. S. Rao",
                                             ["Rohan Deogaonkar"], LAUNDRY_ABSTRACT),
        "slides.pptx": b"PK\x03\x04 slides for the review",
        "notes.txt": b"plain text, not a report",
    }
    for name, data in contents.items():
        (folder / name).write_bytes(data)
    return {name: folder / name for name in contents}


@pytest.fixture
def open_as(browser):
    """open_as(login, path): a new browser window signed in as that sample account (or
    signed out for None), on that page. Fails the test if a page throws an error."""
    contexts, errors = [], []

    def open_as(login: str | None, path: str = "/", width: int = 1440, height: int = 900):
        context = browser.new_context(viewport={"width": width, "height": height}, accept_downloads=True)
        contexts.append(context)
        if login:
            signed_in = context.request.post(f"{URL}/api/sign-in",
                                             data={"login": login, "password": require("SEED_PASSWORD")})
            assert signed_in.ok, signed_in.text()
        page = context.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL + path)
        return page

    yield open_as
    for context in contexts:
        context.close()
    assert not errors, errors


def heading(page, text: str):
    return page.locator("h1").filter(has_text=text)


def toast(page, text: str):
    return expect(page.locator(".toast")).to_contain_text(text)


def alert(page, text: str):
    return expect(page.get_by_role("alert")).to_contain_text(text)


def current_year(page) -> str:
    return page.request.get(f"{URL}/api/reference").json()["current_year"]


def sign_in(page, login: str, password: str):
    page.get_by_label("PRN or college email").fill(login)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Sign in", exact=True).click()


# Signing in, the demo switcher, pages for each role, theme, layout -----------------------

def test_signing_in_with_a_password_and_out_again(open_as):
    page = open_as(None)
    expect(heading(page, "Sign in")).to_be_visible()
    page.get_by_role("button", name="Sign in", exact=True).click()
    alert(page, "Enter your PRN or email and your password.")
    sign_in(page, ROHAN, "not the password")
    alert(page, "That PRN or email and password don't match.")
    sign_in(page, ROHAN, require("SEED_PASSWORD"))
    expect(heading(page, "Hello, Rohan")).to_be_visible()
    page.get_by_role("button", name="Sign out").click()
    expect(heading(page, "Sign in")).to_be_visible()
    sign_in(page, RAO, require("SEED_PASSWORD"))        # an email works as well as a PRN
    expect(heading(page, "Hello, Prof. S. Rao")).to_be_visible()


def test_sample_accounts_and_the_demo_switcher(open_as):
    page = open_as(None)
    page.get_by_role("button", name=re.compile("^Krishna Bhand")).click()
    expect(heading(page, "Hello, Krishna")).to_be_visible()
    page.get_by_label("Switch account (demo)").select_option(ROHAN)
    expect(heading(page, "Hello, Rohan")).to_be_visible()


@pytest.mark.parametrize("login", [ROHAN, RAO, ADMIN])
def test_each_role_has_its_own_pages(open_as, login):
    page = open_as(login)
    expect(heading(page, HOME[login])).to_be_visible()
    nav = page.get_by_role("navigation", name="Pages").get_by_role("button")
    assert [re.sub(r"\d+$", "", t).strip() for t in nav.all_inner_texts()] == NAV[login]
    for label in NAV[login][1:]:
        nav.filter(has_text=label).click()
        expect(heading(page, label)).to_be_visible()
    page.get_by_role("button", name="Account", exact=True).click()
    expect(heading(page, "Your account")).to_be_visible()
    # Another role's page, or a page that doesn't exist, opens the dashboard.
    for path in OUTSIDE[login] + ["/nowhere"]:
        page.goto(URL + path)
        expect(heading(page, HOME[login])).to_be_visible()
        expect(page).to_have_url(URL + "/")


def test_the_theme_is_remembered(open_as):
    page = open_as(ROHAN)
    page.get_by_role("radio", name="Dark").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.get_by_role("radio", name="Light").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")


def test_a_wide_screen_is_filled(open_as):
    page = open_as(ROHAN, "/trends", width=2006, height=1028)
    expect(heading(page, "Trends")).to_be_visible()
    main, content = page.locator(".main").bounding_box(), page.locator(".page").bounding_box()
    assert content["width"] >= 1500
    left = content["x"] - main["x"]
    right = main["x"] + main["width"] - content["x"] - content["width"]
    assert abs(left - right) <= 2
    # The theme buttons fill their box, and the sidebar shows only the name.
    theme = page.get_by_role("radiogroup", name="Theme")
    box, last = theme.bounding_box(), theme.get_by_role("radio").last.bounding_box()
    assert box["x"] + box["width"] - last["x"] - last["width"] <= 4
    expect(page.locator(".brand")).to_have_text("PBL Tracker")


# Student pages, search and trends --------------------------------------------------------

def test_student_dashboard(open_as):
    page = open_as(ROHAN)
    expect(heading(page, "Hello, Rohan")).to_be_visible()
    for tile in ["Your projects", "Approved", "Waiting for review"]:
        expect(page.locator(".tiles").get_by_text(tile, exact=True)).to_be_visible()
    for panel in [f"This year · {current_year(page)}", "Recently approved", "Your projects by status", "Popular stacks"]:
        expect(page.get_by_text(panel, exact=True)).to_be_visible()
    tile = page.locator("a.project-tile").first
    expect(tile.locator(".steps")).to_contain_text("Submitted")
    tile.click()
    expect(page).to_have_url(re.compile(r"/projects/\d+$"))
    expect(page.get_by_role("link", name="← Dashboard")).to_be_visible()


def search(page, action) -> list[dict]:
    """Do something that changes the search, and return the rows the server sent back
    once they are on the page."""
    with page.expect_response(lambda r: "/api/search?" in r.url) as response:
        action()
    data = response.value.json()
    rows = data["rows"]
    expect(page.locator(".loading-bar")).to_have_count(0)
    expect(page.locator(".meta").filter(has_text=re.compile(r"(best matches|newest first)$"))).to_have_text(
        f"{len(rows)} best matches" if data["ranked"] else f"{len(rows)} projects, newest first")
    return rows


def test_search_by_words_meaning_and_filters(open_as):
    page = open_as(ROHAN, "/search")
    total = page.locator(".meta").filter(has_text=re.compile(r"newest first$"))
    expect(total).to_be_visible()
    count = int(total.inner_text().split()[0])
    cards = page.locator("a.card.row-link")
    expect(cards).to_have_count(min(20, count))
    if count > 20:
        page.get_by_role("button", name=re.compile(r"^Show \d+ more$")).click()
        expect(cards).to_have_count(min(40, count))

    box = page.get_by_label("Search")
    assert search(page, lambda: box.fill("attendance"))
    search(page, lambda: page.get_by_role("radio", name="Exact words").click())
    expect(cards.first.locator("mark").first).to_have_text(re.compile("attendance", re.I))
    rows = search(page, lambda: page.get_by_role("radio", name="Idea only").click())
    assert "attendance" in rows[0]["title"].lower()
    rows = search(page, lambda: box.fill("taking the register with the classroom camera"))
    assert any("attendance" in r["title"].lower() for r in rows[:3])     # no shared words needed
    search(page, lambda: page.get_by_role("radio", name="Exact words").click())
    assert search(page, lambda: box.fill("zzqx nothing like this")) == []
    expect(page.get_by_text("No projects match.")).to_be_visible()

    search(page, lambda: page.get_by_role("radio", name="Name and idea").click())
    search(page, lambda: box.fill(""))
    rows = search(page, lambda: page.get_by_role("button", name="IOT-PBL", exact=True).click())
    assert rows and all(r["subject"] == "IOT-PBL" for r in rows)
    rows = search(page, lambda: page.get_by_role("button", name="Hardware", exact=True).click())
    assert rows and all(r["project_type"] == "hardware" for r in rows)
    stack = rows[0]["tags"][0]
    rows = search(page, lambda: page.get_by_role("button", name=stack, exact=True).click())
    assert rows and all(stack in r["tags"] for r in rows)
    for card in cards.all():
        expect(card).to_contain_text(stack)
    search(page, lambda: page.get_by_role("button", name="Clear").click())
    year = page.get_by_label("To year").locator("option").first.inner_text()     # the first year only
    rows = search(page, lambda: page.get_by_label("To year").select_option(year))
    assert rows and all(r["academic_year"] == year for r in rows)
    search(page, lambda: page.get_by_role("button", name="Clear").click())
    expect(total).to_have_text(f"{count} projects, newest first")
    cards.first.click()
    expect(page.get_by_role("link", name="← Search")).to_be_visible()


def test_trends(open_as):
    page = open_as(ROHAN, "/trends")
    for label in ["Approved projects", "Academic years", "Very close pairs", "Hardware projects"]:
        expect(page.locator(".metric-label").filter(has_text=label)).to_be_visible()
    expect(page.get_by_role("table", name="Projects per stack tag per year").get_by_role("row").nth(1)).to_be_visible()
    for title in ["Most used stacks per year", "Ideas that keep coming back", "Most used stack"]:
        expect(page.get_by_text(title, exact=True)).to_be_visible()
    expect(page.get_by_text(re.compile(r"^Faculty load in \d{4}-\d{2}$"))).to_be_visible()
    pairs = page.locator("table.table").first.locator("tbody tr")
    expect(pairs.first).to_contain_text("(")


# A submission link, from making it to the marks export -----------------------------------

def test_faculty_make_a_submission_link(open_as, made):
    page = open_as(RAO, "/links")
    expect(heading(page, "Submission links")).to_be_visible()
    expect(page.get_by_text(f"This year · {current_year(page)}")).to_be_visible()
    make = page.get_by_role("button", name="Make the link")
    make.click()
    alert(page, "Choose the subject.")
    ml = next(s for s in page.request.get(f"{URL}/api/reference").json()["subjects"] if s["code"] == "ML-PBL")
    page.get_by_role("combobox", name=re.compile("^Subject")).select_option(str(ml["subject_id"]))
    page.get_by_label("Year of study").fill("TY")
    make.click()
    alert(page, "Write the branch")
    page.get_by_label("Branch").fill("ECE")
    page.get_by_label("Division").fill("E2E")             # joined into CLASS
    page.get_by_label("What it is for").fill("x")
    make.click()
    alert(page, "Write what the submission is for")
    page.get_by_label("What it is for").fill(made["purpose"])
    out_of = page.get_by_label("Each student out of")
    expect(out_of).to_have_attribute("placeholder", f"{ml['max_marks']:g}")
    out_of.fill("0")
    make.click()                                    # the browser itself refuses 0
    assert out_of.evaluate("e => !e.validity.valid")
    out_of.fill("10")
    page.get_by_label("Fewest students in a team").fill("3")
    page.get_by_label("Most students in a team").fill("2")
    make.click()
    alert(page, "The most students in a team can't be fewer than the fewest.")
    page.get_by_label("Most students in a team").fill("3")         # Krishna and the two TEAMMATES
    make.click()
    alert(page, "Choose the last date and time to submit.")
    page.get_by_label("Last date to submit").fill(f"{date.today().year - 1}-03-31T17:30")
    make.click()
    alert(page, "The last date to submit has to be later than now.")
    page.get_by_label("Last date to submit").fill(LAST_DATE)
    make.click()
    toast(page, "Link made. Copy it and send it to the class.")
    expect(page).to_have_url(re.compile(r"/links/\d+$"))
    made["link_id"] = int(page.url.rsplit("/", 1)[1])
    expect(heading(page, f"ML-PBL · {CLASS}")).to_be_visible()
    expect(page.locator(".head p")).to_have_text(
        f"{made['purpose']} · {current_year(page)} · each student out of 10 · teams of 3 students · last date {LAST_DATE_SHOWN}")
    expect(page.get_by_text(f"Nothing submitted yet. Copy the link and send it to {CLASS}.")).to_be_visible()

    shown = page.locator(".mono.small.grow")
    expect(shown).to_have_text(re.compile(rf"^{re.escape(URL)}/s/[a-z0-9]{{12}}$"))
    made["url"] = shown.inner_text()
    made["code"] = made["url"].rsplit("/", 1)[1]
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=URL)
    page.get_by_role("button", name="Copy link").click()
    toast(page, "Link copied. Send it to the class.")
    assert page.evaluate("navigator.clipboard.readText()") == made["url"]

    # The same link twice is refused; the first one is in the list.
    page.get_by_role("link", name="← Submission links").click()
    page.get_by_role("combobox", name=re.compile("^Subject")).select_option(str(ml["subject_id"]))
    page.get_by_label("Year of study").fill("ty")
    page.get_by_label("Branch").fill("ECE")
    page.get_by_label("Division").fill("Div E2E")         # same class: "Div" isn't doubled, case is ignored
    page.get_by_label("What it is for").fill(made["purpose"])
    page.get_by_label("Last date to submit").fill(LAST_DATE)
    make.click()
    expect(page.get_by_role("alert")).to_be_visible()
    expect(page).to_have_url(URL + "/links")
    expect(page.get_by_role("row").filter(has_text=made["purpose"])).to_contain_text(LAST_DATE_SHOWN)
    page.get_by_role("row").filter(has_text=made["purpose"]).click()
    expect(page).to_have_url(f"{URL}/links/{made['link_id']}")


def test_a_student_submits_through_the_link(open_as, made, files):
    page = open_as(KRISHNA, "/submit")
    expect(heading(page, "Submit a project")).to_be_visible()
    pasted = page.get_by_label("Submission link")
    pasted.fill("the link from the class group!")
    page.get_by_role("button", name="Open").click()
    alert(page, "Paste the whole link your faculty member sent")
    page.goto(URL + "/s/zzzz99999999")
    expect(page.get_by_text("No submission link with this code.")).to_be_visible()
    page.goto(URL + "/submit")
    page.get_by_label("Submission link").fill(made["url"])
    page.get_by_role("button", name="Open").click()
    expect(page).to_have_url(f"{URL}/s/{made['code']}")
    expect(heading(page, f"{made['purpose']} · ML-PBL")).to_be_visible()
    expect(page.locator(".head p")).to_contain_text(f"{CLASS} · Prof. S. Rao")

    submit = page.get_by_role("button", name="Submit project")
    steps = [
        (lambda: None, "Give the project a title of at least five characters."),
        (lambda: page.get_by_label("Project title").fill(CCTV), "The abstract needs at least 30 characters."),
        (lambda: (page.get_by_label("Abstract").fill(CCTV_ABSTRACT), page.get_by_label("Teammates' PRNs").fill("12345")),
         "Enter each teammate's 10-digit PRN, separated by commas."),
        (lambda: page.get_by_label("Teammates' PRNs").fill(TEAMMATES.split(", ")[0]),
         "This submission link takes teams of 3 students; yours has 2."),
        (lambda: page.get_by_label("Teammates' PRNs").fill(TEAMMATES), "Attach the project report (PDF)."),
        (lambda: page.get_by_label("Report (PDF)").set_input_files(files["notes.txt"]), "The report has to be a PDF."),
        (lambda: (page.get_by_label("Report (PDF)").set_input_files(files["report.pdf"]),
                  page.get_by_label("GitHub link").fill("github.com/example/attendance")),
         "A link has to start with https:// or http://."),
    ]
    for change, refusal in steps:
        change()
        submit.click()
        alert(page, refusal)
    # The side panel finds the sample project it is very close to.
    expect(page.get_by_text("Very close to an earlier project.")).to_be_visible(timeout=60_000)
    expect(page.locator(".sticky").get_by_text(re.compile(r"^Very close \(\d\.\d\d\)$")).first).to_be_visible()

    page.get_by_role("radiogroup", name="Project type").get_by_role("radio", name="Both").click()
    for stack in ["Python", "OpenCV"]:
        page.get_by_role("button", name=stack, exact=True).click()
        expect(page.get_by_role("button", name=stack, exact=True)).to_have_attribute("aria-pressed", "true")
    page.get_by_label("New technology").fill(made["tag"])
    page.get_by_label("New technology").press("Enter")
    expect(page.get_by_role("button", name=made["tag"], exact=True)).to_have_attribute("aria-pressed", "true")
    page.get_by_label("Presentation").set_input_files(files["slides.pptx"])
    page.get_by_label("GitHub link").fill("https://github.com/example/attendance")
    page.get_by_label("Working demo link").fill("https://example.com/attendance")
    submit.click()
    expect(page).to_have_url(re.compile(r"/projects/\d+$"), timeout=30_000)
    toast(page, "Submitted to Prof. S. Rao.")
    made["cctv"] = int(page.url.rsplit("/", 1)[1])
    expect(heading(page, CCTV)).to_be_visible()
    details = page.locator(".details")
    expect(details.locator(".status")).to_have_text("Waiting for review")
    expect(details.locator(".facts")).to_contain_text("Krishna Bhand")
    expect(details.locator(".facts")).to_contain_text(made["tag"])
    expect(details.get_by_role("link", name="GitHub")).to_have_attribute("href", "https://github.com/example/attendance")
    expect(page.locator(".project canvas").first).to_be_visible(timeout=20_000)     # the report, drawn by pdf.js

    page.goto(f"{URL}/s/{made['code']}")
    expect(page.get_by_text("Your team has submitted")).to_be_visible()
    expect(page.get_by_role("button", name="Submit project")).to_have_count(0)


def test_a_waiting_project_is_seen_only_by_its_team_and_faculty(open_as, made):
    project = f"/projects/{made['cctv']}"
    for login in [ROHAN, IYER]:
        expect(open_as(login, project).get_by_text("No such project.")).to_be_visible()
    for login in [RAO, ADMIN]:
        expect(heading(open_as(login, project), CCTV)).to_be_visible()

    link = f"/s/{made['code']}"
    rohan = open_as(ROHAN, link)
    expect(rohan.get_by_text("1 more waiting for review")).to_be_visible()
    expect(rohan.get_by_role("button", name="Submit project")).to_be_visible()
    expect(rohan.get_by_text(CCTV)).to_have_count(0)
    # Or the team starts from one of its projects in another link.
    rohan.get_by_role("radio", name="Submit a saved project").click()
    rohan.get_by_role("radio", name=re.compile("^Smart Water Tank Level Controller")).click()
    expect(rohan.get_by_label("Project title")).to_have_value("Smart Water Tank Level Controller")
    expect(rohan.get_by_text("The saved report, Smart Water Tank Level Controller.pdf, goes with it.")).to_be_visible()
    rohan.get_by_role("radio", name="Submit a new project").click()
    expect(rohan.get_by_label("Project title")).to_have_value("")
    expect(open_as(IYER, link).get_by_text(f"Students of {CLASS} submit their projects here.")).to_be_visible()
    rao = open_as(RAO, link)
    expect(rao.get_by_text("This is your link.")).to_be_visible()
    rao.get_by_role("button", name="Review and grade its projects").click()
    expect(rao).to_have_url(f"{URL}/links/{made['link_id']}")


def test_the_team_changes_its_links_and_files(open_as, made, files):
    page = open_as(KRISHNA, f"/projects/{made['cctv']}")
    page.get_by_role("button", name="Add or change links and files").click()
    page.get_by_label("Link label").fill("Docs")
    page.get_by_label("Link URL").fill("docs.example.com")
    page.get_by_role("button", name="Add link").click()
    alert(page, "A link has to start with https:// or http://.")
    page.get_by_label("Link URL").fill("https://docs.example.com/attendance")
    page.get_by_role("button", name="Add link").click()
    toast(page, "Link added.")
    expect(page.get_by_role("link", name="Docs")).to_have_attribute("href", "https://docs.example.com/attendance")
    page.locator("div.row.small").filter(has_text="Docs: https://docs.example.com/attendance") \
        .get_by_role("button", name="Remove").click()
    toast(page, "Link removed.")
    expect(page.get_by_role("link", name="Docs")).to_have_count(0)

    report_picker = page.locator('input[type=file][accept=".pdf"]')
    report_picker.set_input_files(files["notes.txt"])
    alert(page, "The report has to be a .pdf file.")
    report_picker.set_input_files(files["report-v2.pdf"])
    toast(page, "Report uploaded.")
    report_row = page.locator("div.row.small").filter(has_text="Report: report-v2.pdf")
    expect(report_row).to_be_visible()
    expect(report_row.get_by_role("button", name="Remove")).to_have_count(0)    # a report is only replaced
    page.locator('input[type=file][accept=".pptx,.pdf"]').set_input_files(files["slides.pptx"])
    toast(page, "Presentation uploaded.")
    page.locator("div.row.small").filter(has_text="Presentation: slides.pptx").get_by_role("button", name="Remove").click()
    toast(page, "Presentation removed.")
    expect(page.get_by_role("button", name="Upload presentation")).to_be_visible()
    page.get_by_role("button", name="Done").click()

    href = page.get_by_role("link", name="Download the report").get_attribute("href")
    report = page.request.get(URL + href)
    assert report.ok and report.headers["content-type"] == "application/pdf"
    assert report.body().startswith(b"%PDF-") and b"second version" in report.body()


def test_faculty_review_grade_change_close_and_export(open_as, made):
    page = open_as(RAO)
    # Only the row titled so: the sample project's row names it as its closest project.
    waiting = page.locator("a.row-link").filter(has=page.locator(".title").get_by_text(CCTV, exact=True))
    expect(waiting).to_contain_text(CLASS)
    expect(waiting).to_contain_text("Very close")
    expect(page.locator(".nav-count")).to_have_text(re.compile(r"^[1-9]\d*$"))
    page.goto(f"{URL}/links/{made['link_id']}")
    expect(page.get_by_text("Waiting for review (1)")).to_be_visible()
    page.get_by_role("link", name=CCTV).click()

    expect(page.get_by_text("Your review")).to_be_visible()
    expect(page.get_by_text("Closest earlier project:")).to_be_visible()
    page.get_by_role("button", name="Approve").click()
    alert(page, "This project is very close to")
    page.get_by_label("Note to the team").fill(
        "Uses the classroom's own CCTV feed and marks only the first ten minutes.")
    page.get_by_role("button", name="Approve").click()
    toast(page, "Approved. You can give the marks now.")
    expect(page.locator(".details .status")).to_have_text("Approved")

    expect(page.get_by_text("Marks, out of 10 each")).to_be_visible()
    boxes = page.get_by_label(re.compile("^Marks for "))
    expect(boxes).to_have_count(3)
    krishna = page.get_by_label("Marks for Krishna Bhand")
    others = [b for b in boxes.all() if b.get_attribute("aria-label") != "Marks for Krishna Bhand"]
    save = page.get_by_role("button", name="Save marks")
    krishna.fill("11")
    save.click()
    alert(page, "more than the maximum 10.0 for this submission")
    krishna.fill("8")
    save.click()
    toast(page, "Marks saved.")
    expect(page.get_by_text("1 of 3 students graded.")).to_be_visible()
    others[0].fill("7")
    others[1].fill("9")
    save.click()
    toast(page, "Team score 8")
    expect(page.locator(".marks-big")).to_have_text(re.compile(r"^8(\.0)? / 10$"))

    page.get_by_role("link", name=re.compile(f"^← {made['purpose']}")).click()
    expect(page.get_by_text("Approved (1)")).to_be_visible()
    expect(page.get_by_text("team score", exact=True)).to_be_visible()
    expect(page.locator(".metric").filter(has_text="Graded")).to_contain_text("1 of 1")

    # Lowering the maximum below marks already given is refused; a new purpose is saved.
    page.get_by_role("button", name="Change class, purpose, marks, team size or last date").click()
    page.get_by_label("Each student out of").fill("5")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("alert")).to_be_visible()
    page.get_by_role("button", name="Cancel").click()
    page.get_by_role("button", name="Change class, purpose, marks, team size or last date").click()
    expect(page.get_by_label("Year of study")).to_have_value("TY")      # the class comes back in its three parts
    expect(page.get_by_label("Branch")).to_have_value("ECE")
    expect(page.get_by_label("Division")).to_have_value("E2E")
    expect(page.get_by_label("Fewest students in a team")).to_have_value("3")
    expect(page.get_by_label("Last date to submit")).to_have_value(LAST_DATE)
    page.get_by_label("Fewest students in a team").fill("1")
    page.get_by_label("Most students in a team").fill("2")
    page.get_by_role("button", name="Save").click()
    alert(page, "A team in this link already has 3 students")        # the approved team of three
    page.get_by_label("Fewest students in a team").fill("3")
    page.get_by_label("Most students in a team").fill("3")
    made["purpose"] += " renamed"
    page.get_by_label("What it is for").fill(made["purpose"])
    page.get_by_role("button", name="Save").click()
    toast(page, "Saved.")
    expect(page.locator(".head p")).to_contain_text(made["purpose"])

    page.get_by_role("button", name="Close the link").click()
    toast(page, "Link closed. It takes no new projects.")
    expect(page.locator(".card .status").first).to_have_text("Closed")
    expect(open_as(ROHAN, f"/s/{made['code']}").get_by_text("This link is closed")).to_be_visible()
    page.get_by_role("button", name="Open it again").click()
    toast(page, "The link takes projects again.")
    expect(page.locator(".card .status").first).to_have_text("Open")
    expect(page.locator(".head p")).to_contain_text("teams of 3 students")     # closing and opening keeps the team size

    with page.expect_download() as download:
        page.get_by_role("link", name="Download marks").click()
    assert download.value.suggested_filename.startswith("ML-PBL-TY-ECE-Div-E2E")
    rows = list(csv.reader(io.StringIO(Path(download.value.path()).read_text(encoding="utf-8-sig"))))
    assert rows[0] == ["PRN", "Student", "Project", "Status", "Marks", "Team score", "Out of"]
    sheet = {r[0]: r for r in rows[1:]}
    assert sorted(float(sheet[prn][4]) for prn in [KRISHNA, *TEAMMATES.split(", ")]) == [7, 8, 9]
    assert float(sheet[KRISHNA][4]) == 8 and float(sheet[KRISHNA][5]) == 8 and float(sheet[KRISHNA][6]) == 10
    assert sheet[KRISHNA][2] == CCTV and sheet[KRISHNA][3] == "approved"


def test_a_rejected_team_can_submit_again(open_as, made, files):
    rohan = open_as(ROHAN, f"/s/{made['code']}")
    title = f"Hostel Laundry Slot Booking {made['stamp']}"
    rohan.get_by_label("Project title").fill(title)
    rohan.get_by_label("Abstract").fill(LAUNDRY_ABSTRACT)
    rohan.get_by_label("Teammates' PRNs").fill(LAUNDRY_TEAM)
    rohan.get_by_label("Report (PDF)").set_input_files(files["laundry.pdf"])
    rohan.get_by_role("button", name="Submit project").click()
    expect(rohan).to_have_url(re.compile(r"/projects/\d+$"), timeout=30_000)
    made["laundry"] = int(rohan.url.rsplit("/", 1)[1])

    rao = open_as(RAO, f"/projects/{made['laundry']}")
    rao.get_by_label("Note to the team").fill("Needs a clearer scope: which hostels, and how slots are shared.")
    rao.get_by_role("button", name="Reject").click()
    toast(rao, "Rejected.")
    expect(rao.locator(".details .status")).to_have_text("Rejected")

    rohan.reload()
    expect(rohan.locator(".details .status")).to_have_text("Rejected")
    expect(rohan.get_by_text("Note from Prof. S. Rao")).to_be_visible()
    expect(rohan.get_by_text("Needs a clearer scope")).to_be_visible()
    rohan.goto(f"{URL}/s/{made['code']}")
    expect(rohan.get_by_role("button", name="Submit project")).to_be_visible()     # a rejected project doesn't count
    rao.goto(f"{URL}/links/{made['link_id']}")
    expect(rao.get_by_text("Rejected (1)")).to_be_visible()


def test_students_see_their_own_marks_and_choose_to_share_the_team_score(open_as, made):
    project = f"/projects/{made['cctv']}"
    krishna, rohan = open_as(KRISHNA, project), open_as(ROHAN, project)
    score = re.compile(r"^8(\.0)? / 10$")
    expect(krishna.get_by_text("Your marks")).to_be_visible()
    expect(krishna.locator(".marks-big")).to_have_count(2)
    for big in krishna.locator(".marks-big").all():
        expect(big).to_have_text(score)
    expect(rohan.get_by_text("Your marks")).to_have_count(0)
    expect(rohan.get_by_text("Only the team and their faculty member can see the marks.")).to_be_visible()

    share = krishna.get_by_role("switch", name="Show our team score to everyone")
    expect(share).to_have_attribute("aria-checked", "false")
    share.click()
    toast(krishna, "The team score is now shown to everyone.")
    expect(share).to_have_attribute("aria-checked", "true")
    rohan.reload()
    expect(rohan.locator(".marks-big")).to_have_text(score)
    share.click()
    toast(krishna, "The team score is now shown only to the team and faculty.")
    rohan.reload()
    expect(rohan.get_by_text("Only the team and their faculty member can see the marks.")).to_be_visible()

    krishna.goto(URL + "/")
    tile = krishna.locator("a.project-tile").filter(has_text=CCTV)
    expect(tile).to_contain_text("8 / 10")
    expect(tile.locator(".step.done")).to_have_count(3)


def test_faculty_see_only_their_own_links(open_as, made):
    page = open_as(IYER, f"/links/{made['link_id']}")
    expect(page.get_by_text("This isn't one of your submission links.")).to_be_visible()
    page.goto(URL + "/links")
    expect(heading(page, "Submission links")).to_be_visible()
    expect(page.get_by_text(made["purpose"])).to_have_count(0)
    page.goto(f"{URL}/projects/{made['cctv']}")
    expect(heading(page, CCTV)).to_be_visible()
    for text in ["Marks, out of", "Your review", "Add or change links and files"]:
        expect(page.get_by_text(text)).to_have_count(0)


# Admin -----------------------------------------------------------------------------------

def test_admin_overview_and_the_missing_embeddings(open_as, made):
    with psycopg.connect(require("ADMIN_DATABASE_URL")) as conn:
        conn.execute("UPDATE pbl.projects SET embedding = NULL WHERE project_id = %s", (made["cctv"],))
    page = open_as(ADMIN)
    expect(heading(page, "Overview")).to_be_visible()
    for tile in ["Approved projects", "Waiting for review", "Students", "Faculty"]:
        expect(page.locator(".tiles").get_by_text(tile, exact=True)).to_be_visible()
    expect(page.get_by_text("Latest submissions")).to_be_visible()
    expect(page.locator("a.row-link").filter(has_text=f"Hostel Laundry Slot Booking {made['stamp']}")).to_be_visible()
    expect(page.get_by_text(re.compile(r"^\d+ projects can't be found by meaning search yet\."))).to_be_visible()
    page.get_by_role("button", name="Fix it now").click()
    toast(page, "Made 1 embeddings.")
    expect(page.get_by_role("button", name="Fix it now")).to_have_count(0)

    page.goto(f"{URL}/projects/{made['cctv']}")
    marks = page.locator(".card").filter(has_text="Team score")
    expect(marks).to_contain_text("Krishna Bhand")
    expect(marks.locator(".row")).to_have_count(3)


def test_admin_manage_people(open_as, made):
    page = open_as(ADMIN, "/people")
    expect(heading(page, "People")).to_be_visible()
    for label in ["Students", "Faculty", "Admins", "Switched off"]:
        expect(page.locator(".metric-label").filter(has_text=label)).to_be_visible()
    find = page.get_by_label("Find a person")
    rows = page.locator("tbody tr")
    find.fill("Rohan")
    expect(rows.filter(has_text="Rohan Deogaonkar")).to_be_visible()
    find.fill("")
    page.get_by_role("radiogroup", name="Role").first.get_by_role("radio", name="Faculty", exact=True).click()
    for role in rows.locator("td:nth-child(3)").all_inner_texts():
        assert role.startswith("faculty")
    page.get_by_role("radio", name="All", exact=True).click()

    add = page.locator(".card").filter(has=page.get_by_text("Add a person", exact=True))
    button = add.get_by_role("button", name="Add and make a temporary password")
    add.get_by_label("Name", exact=True).fill(f"E2E Student {made['stamp']}")
    add.get_by_label("College email").fill(made["student"].replace("@mitwpu.edu.in", "@gmail.com"))
    add.get_by_label("PRN").fill("123")
    button.click()
    alert(page, "A student needs a 10-digit PRN.")
    add.get_by_label("PRN").fill(made["prn"])
    button.click()
    alert(page, "Use the person's college email, ending in @mitwpu.edu.in.")
    add.get_by_label("College email").fill(made["student"])
    button.click()
    expect(page.get_by_text(f"Temporary password for E2E Student {made['stamp']}")).to_be_visible()
    made["student_password"] = page.locator("code.secret").inner_text()
    page.get_by_role("button", name="Done").click()

    add.get_by_role("radio", name="faculty", exact=True).click()
    add.get_by_label("Name", exact=True).fill(f"E2E Faculty {made['stamp']}")
    add.get_by_label("College email").fill(made["faculty"])
    button.click()
    expect(page.get_by_text(f"Temporary password for E2E Faculty {made['stamp']}")).to_be_visible()
    first_password = page.locator("code.secret").inner_text()
    page.get_by_role("button", name="Done").click()

    who = f"E2E Faculty {made['stamp']}"
    find.fill(who)
    rows.filter(has_text=who).click()
    panel = page.locator(".narrow .card").first
    expect(panel).to_contain_text(who)
    panel.get_by_role("button", name="Make admin").click()
    toast(page, f"{who} is now an admin")
    expect(rows.filter(has_text=who)).to_contain_text("faculty, admin")
    panel.get_by_role("button", name="Remove admin rights").click()
    toast(page, f"{who} is no longer an admin")
    panel.get_by_role("button", name="Switch off").click()
    toast(page, f"Switched off {who}")
    expect(rows.filter(has_text=who)).to_contain_text("Switched off")
    other = open_as(None)
    sign_in(other, made["faculty"], first_password)
    alert(other, "This account is switched off. Ask the PBL coordinator.")
    panel.get_by_role("button", name="Switch on").click()
    toast(page, f"Switched on {who}")
    panel.get_by_role("button", name="Give a temporary password").click()
    expect(page.get_by_text(f"Temporary password for {who}")).to_be_visible()
    assert page.locator("code.secret").inner_text() != first_password
    page.get_by_role("button", name="Done").click()

    # Nobody can switch themselves off.
    find.fill("admin@mitwpu.edu.in")
    rows.filter(has_text="admin@mitwpu.edu.in").click()
    expect(panel.get_by_role("button", name="Switch off")).to_be_disabled()
    expect(panel.get_by_role("button", name=re.compile("admin"))).to_have_count(0)


def test_first_sign_in_with_a_temporary_password(open_as, made):
    page = open_as(None)
    sign_in(page, made["student"], made["student_password"])
    expect(heading(page, "Choose a new password")).to_be_visible()
    current, fresh, again = (page.locator("input[type=password]").nth(i) for i in range(3))
    save = page.get_by_role("button", name="Save new password")
    first, second = secrets.token_urlsafe(12), secrets.token_urlsafe(12)
    for values, refusal in [((made["student_password"], "short", "short"), "Use at least 8 characters."),
                            ((made["student_password"], first, second), "The two new passwords are different."),
                            (("not the temporary one", first, first), "The current password is wrong.")]:
        for box, value in zip((current, fresh, again), values):
            box.fill(value)
        save.click()
        alert(page, refusal)
    for box, value in zip((current, fresh, again), (made["student_password"], first, first)):
        box.fill(value)
    save.click()
    expect(heading(page, "Hello, E2E")).to_be_visible()
    expect(page.get_by_text(f"You haven't submitted a project for {current_year(page)} yet.")).to_be_visible()

    page.get_by_role("button", name="Account", exact=True).click()
    expect(heading(page, "Your account")).to_be_visible()
    expect(page.locator(".meta")).to_contain_text(made["prn"])
    for box, value in zip((current, fresh, again), ("not my password", second, second)):
        box.fill(value)
    save.click()
    alert(page, "The current password is wrong.")
    current.fill(first)
    save.click()
    expect(page.get_by_text("Password changed.")).to_be_visible()
    page.get_by_role("button", name="Sign out").click()
    sign_in(page, made["prn"], second)
    expect(page.locator(".me-name")).to_have_text(f"E2E Student {made['stamp']}")   # back on the same page
    expect(heading(page, "Your account")).to_be_visible()


def test_admin_manage_subjects(open_as, made):
    page = open_as(ADMIN, "/subjects")
    expect(heading(page, "Subjects")).to_be_visible()
    table = page.locator("table")
    expect(table.get_by_role("row").filter(has_text="CN-TH")).to_contain_text("5")
    add = page.locator(".card").filter(has=page.get_by_text("Add a subject", exact=True))
    add.get_by_label("Code").fill(made["subject"].lower())
    expect(add.get_by_label("Code")).to_have_value(made["subject"])
    add.get_by_label("Name", exact=True).fill("Browser Test Subject")
    add.get_by_label("Maximum marks").fill("0")
    add.get_by_role("button", name="Add subject").click()
    alert(page, "The maximum marks have to be more than 0.")
    add.get_by_label("Maximum marks").fill("12")
    add.get_by_role("button", name="Add subject").click()
    toast(page, f"Added {made['subject']}.")
    row = table.get_by_role("row").filter(has_text=made["subject"])
    expect(row).to_contain_text("12")
    for box, value in [("Code", made["subject"]), ("Name", "Browser Test Subject"), ("Maximum marks", "12")]:
        add.get_by_label(box, exact=True).fill(value)
    add.get_by_role("button", name="Add subject").click()
    expect(add.get_by_role("alert")).to_be_visible()                                  # the code is taken

    row.get_by_role("button", name="Edit").click()
    table.get_by_label("Maximum marks").fill("15")
    table.get_by_role("button", name="Save").click()
    toast(page, f"Saved {made['subject']}.")
    expect(row).to_contain_text("15")
    row.get_by_role("button", name="Edit").click()
    table.get_by_role("button", name="Cancel").click()
    expect(row.get_by_role("button", name="Edit")).to_be_visible()

    rao = open_as(RAO, "/links")
    expect(rao.get_by_role("combobox", name=re.compile("^Subject")).locator("option").filter(has_text=f"{made['subject']} - Browser Test Subject")) \
        .to_have_count(1)


def test_a_link_opened_before_signing_in_opens_after_it(open_as, made):
    page = open_as(None, f"/s/{made['code']}")
    expect(page.get_by_text("Sign in with your college account to open the submission link.")).to_be_visible()
    page.get_by_role("button", name=re.compile("^Rohan Deogaonkar")).click()
    expect(heading(page, made["purpose"])).to_be_visible()
    expect(page).to_have_url(f"{URL}/s/{made['code']}")
