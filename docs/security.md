# Security

## What we protect, and from whom

- **Personal data**: names, PRNs and emails of students and faculty.
- **Accounts**: passwords, and who is allowed to act as whom.
- **Marks**: only the faculty member who made the submission link should be able to enter
  or change the marks of the projects that came in through it. A student's own marks are
  seen only by that student, that faculty member and the coordinator; the team score by
  the team too, and by everyone once the team makes it public.
- **Submission links**: only their faculty member should see a link's list of projects
  and marks, change it or close it, and nobody should be able to guess a link they weren't
  sent.
- **Work in progress**: a project waiting for review, or rejected, is seen only by its team,
  its faculty member and the coordinator.
- **Decisions**: only the link's faculty member should approve or reject a project.
- **Reports and presentations**: only the team, its faculty member or the admin should be able to replace or remove them.
- **The database itself**: the app should never be able to do more than it needs, even if its code has a bug.

The realistic attackers are a curious student with the app open, someone on the same
Wi-Fi, and anyone who finds a leaked password.

## Layers

### In the database

| Measure | Where | What it stops |
|---|---|---|
| Separate `pbl` schema; `REVOKE ALL ... FROM PUBLIC` | `01_tables.sql`, `06_security.sql` | Supabase's automatic REST API (anon key) can't see the tables; other database users can't either |
| The app logs in as `pbl_app`, never as the owner | `06_security.sql` | A bug in the app can only do what `pbl_app` is allowed to do |
| `pbl_app` can read every column of `users` except `password_hash` | column-level `GRANT SELECT` | The hashes can't leave the database, even through a bug or an injected query |
| `pbl_app` can't delete projects or users, or insert them directly | no DELETE or INSERT grant | Projects come in only through `submit_project()`, users only through `create_user()` |
| `pbl_app` can only update a project's status, review note, `marks_public` and embedding, and a team member's marks | column-level `GRANT UPDATE` | The app can't rename a project, move it to another link, or change who is in a team |
| `pbl_app` can create a submission link but never set or change its `code`, and can change only its class, purpose, maximum and whether it is open | column-level `GRANT INSERT` and `GRANT UPDATE` | Link codes are always the database's random ones (`gen_random_bytes(6)`, 2^48 possibilities), and a link can't be handed to another faculty member, subject or year |
| Passwords hashed with bcrypt (pgcrypto `crypt()`, cost 11, about 80 ms a check) | `hash_password()` in `03_functions.sql` | A stolen copy of the table gives no passwords, and guessing them is slow |
| Passwords are checked inside the database | `sign_in()`, `SECURITY DEFINER` | The app sends a login and a password and gets back the account or "wrong"; it never sees a hash |
| Same answer for an unknown login and a wrong password, with the same bcrypt delay | `sign_in()` | The form can't be used to find out which PRNs or emails exist |
| A switched-off account is only told so after the right password | `sign_in()` | Guessing can't find out who has left |
| Temporary passwords are random (72 bits), shown once, and must be changed at the next sign-in | `temporary_password()`, `create_user()`, `reset_password()` | The coordinator never chooses or keeps anyone's real password |
| `hash_password()` and `temporary_password()` can't be called by `pbl_app` | not in the EXECUTE list | Only the functions that need them can use them |
| `submit_project()` is `SECURITY DEFINER` | `03_functions.sql` | It checks the leader is a student, the link exists and is open, every PRN exists and the report is there, forces status `submitted`, and saves nothing if any check fails |
| One live project per student per link, under an advisory lock | `check_member` trigger | Two submits at the same moment can't both slip past the check |
| Every function pins `search_path` | all functions | Nobody can make a function pick up a look-alike table or operator from another schema |
| Only `@mitwpu.edu.in` emails | `college_email` CHECK on `users` | Nobody from outside the college can be given an account, whichever way it is added |
| A decision is made once, and the report stays | `check_project` and `keep_report` triggers | A decided project can't be quietly flipped back, and a project can't lose its report |
| Business-rule triggers and CHECKs | `01_tables.sql`, `04_triggers.sql` | Bad data is refused whichever client sends it, including someone typing SQL |
| `statement_timeout = 5s`, `idle_in_transaction_session_timeout = 30s`, connection limit 20 | `06_security.sql` | A runaway query or stuck transaction can't hold locks or connections for long |

### The connection

- The app's password is hashed with SCRAM-SHA-256 **on your machine** by `setup_db.py`
  (the same thing psql's `\password` does), so the plain password never reaches the
  server or its logs.
- Supabase connections use TLS (`sslmode=require` in `.env.example`).
- The app and the scripts use different logins. Only the scripts get the owner login
  (`ADMIN_DATABASE_URL`), and only on the machine that runs them.

### In the app

- **Nothing without signing in.** Every `/api` endpoint apart from sign-in needs a session.
- **Who may do what is checked before anything runs.** Students can't open Submission
  links, People or Subjects (403). Only students can submit a project, and only through
  an open link. A faculty member sees, changes, exports and grades only their own links:
  every query joins `submission_links` and has `WHERE faculty_id = <me>`, so another
  faculty member's link or project is not found (404). Marks can only be given to the
  project's own team (422). Links and files can be added or removed by the team, the
  link's faculty member or the admin, and nobody else (403).
- **A link code is only a way in, not a permission.** Opening `/s/<code>` still needs a
  college sign-in. The page shows the link's approved projects and the student's own;
  other teams' waiting projects are only counted. The code is checked against a strict
  pattern before it reaches the database.
- **The sign-in lives on the server.** After `sign_in()` succeeds, the account is kept in
  the server's memory under a random 256-bit token. The browser only gets that token, in
  a cookie that is `HttpOnly` (page scripts can't read it) and `SameSite=Strict` (other
  sites can't make the browser send it, which is what stops cross-site request forgery).
  30 idle minutes, signing out, or restarting the server ends the session.
- **Every transaction checks the sign-in is still valid.** If the account was switched
  off, or its password changed or was reset after this sign-in, the request gets 401 and
  the cookie is removed. So switching someone off works on their next click.
- **A temporary password opens nothing else.** Until the person chooses their own, every
  endpoint except "who am I", "change password" and "sign out" answers 403.
- **Changing a password needs the current one.** The change time becomes this session's
  sign-in time, so every other session of that account ends.
- **Marks and unfinished work stay with the team.** The project page sends a student
  their own marks and the team score; everyone's marks go only to the link's faculty
  member and the coordinator. Other people get the team score only when the team has
  switched `marks_public` on; only team members can switch it. A project that is waiting
  or was rejected answers 404 to everyone else, and search only lists approved projects.
- **The marks export can't run formulas.** Names and titles are typed by users, so a cell
  starting with `=`, `+`, `-` or `@` gets a leading apostrophe before it goes in the CSV,
  and Excel shows it as text instead of running it.
- **Uploads.** The report has to be a `.pdf`, the presentation a `.pptx` or `.pdf`, at most
  20 MB, and a PDF has to start with `%PDF-`. This is checked before the file is stored.
  The stored name is `<project id>/<random hex><extension>`; the name the user gave is
  only kept as text in `project_files`, so it can't be used to write somewhere else.
  Presentations download as attachments. The project page draws the report with PDF.js
  (from the app's own files, no outside scripts); "Open" shows the PDF in its own tab,
  and nothing may frame it.
- **The storage key stays on the server.** The B2 application key is read from `.env`
  by `finder/storage.py`. It works on one bucket only, the browser never talks to B2,
  and the bucket is private.
- **Security headers.** A Content Security Policy that only allows the app's own scripts,
  styles and fonts, no framing, `nosniff`, and `no-store` on every API answer.
- **Demo account switcher.** Off unless `DEMO_SWITCHER` is set. It only signs in the five
  listed sample users, through `sign_in()` with `SEED_PASSWORD`, so it can't get past a
  switched-off account or a changed password. With it on, anyone who can open the app
  can become the admin, so it is for a laptop demo only.
- **No SQL is built from user input.** Every value is a bound parameter. The search page
  adds filters with `psycopg.sql` pieces that still carry placeholders.
- **Text people typed is shown as text.** React escapes everything it puts on the page,
  and no component uses `dangerouslySetInnerHTML`. Links must start with `http://` or
  `https://` (checked by the server and by a CHECK constraint), so a `javascript:` link
  can't be saved.
- **Error messages don't leak internals.** Rule violations show the database's own
  message (for example "Marks 34.0 are more than the maximum 33.0 for this submission").
  Anything else shows a generic message; the details go to the terminal log. The server
  has no interactive API docs page.
- **The server only listens on 127.0.0.1** (`python -m api`), so nobody else on the
  Wi-Fi can open it.
- **Input limits**: every text box has a maximum length, and the database has matching
  CHECKs. Passwords are capped at 72 characters because bcrypt ignores anything after 72 bytes.
- **The model is pinned** to one commit of its Hugging Face repo.

### In the repository

- `.env` is git-ignored; `.env.example` has placeholders only.
- The CI job uses a throwaway database with no password and generates a one-off app
  password and seed password per run.
- All sample people are invented, with made-up `@mitwpu.edu.in` emails. Their accounts share
  `SEED_PASSWORD` from `.env`, which is never committed.

## Who can do what

| | student | faculty | admin |
|---|---|---|---|
| Search approved projects, see trends | yes | yes | yes |
| Open an approved project: report, team, tags, links and files | yes | yes | yes |
| Open a waiting or rejected project | own projects | own projects | any project |
| See a student's own marks | their own | own links | any project |
| See a team score | own projects, or when the team made it public | own links, or public | any project |
| Make the team score public or private | own projects | no | no |
| Open a submission link they were sent | yes | yes | yes |
| Submit a project with its report | through an open link, once per link | no | no |
| Make, change, close a submission link; download its marks | no | own links | own links |
| Add or remove links, upload or remove files | own projects | own links | any project |
| Approve or reject a submission | no | own links | own links |
| Enter each student's marks | no | own links | own links |
| Add people, reset passwords, switch accounts off, make admins | no | no | yes |
| Add subjects and set their maximum marks | no | no | yes |
| Change own password (needs the current one) | yes | yes | yes |

The admin is a faculty member with `is_admin` set, so they make links, review and mark
like anyone else; being admin lets them see every project and its marks, but not mark
or decide on someone else's.

## Tested

`tests/test_security.py` runs as `pbl_app` and checks it can't read password hashes,
delete projects or users, insert projects or users directly, change anything on a
project except the review and marks columns, choose a link's code, call
`hash_password()`, or become the owner; that `submit_project()` saves nothing when one
PRN is wrong, needs an open link and a student, and needs a PDF report.
`tests/test_auth.py` covers sign-in by PRN or email, the same answer for unknown logins
and wrong passwords, switched-off accounts, bcrypt storage, and password changes and
resets. `tests/test_api.py` checks the same from the app's side: nothing before sign-in,
other roles' pages refused, a faculty member unable to see or change another's links or
decide on or mark their projects, closed and unknown links refused, waiting projects
hidden from outsiders, each student's marks private and the team score hidden until the
team makes it public, export cells that can't run as formulas, links and files refused
to outsiders, only PDF reports accepted, college emails only,
sign-out, idle sessions, and a session ending after a password change.

## Known limits

- **Passwords reach the database as query parameters** (over TLS on Supabase). Don't turn
  on logging of statement parameters on this database, or passwords would end up in its logs.
- **Nothing limits how fast someone can guess.** Each wrong guess costs about 80 ms of
  bcrypt, but there is no lockout. If the app is put on the college network, add rate
  limiting at the reverse proxy.
- **Who may do what is checked by the app, not by the database.** `pbl_app` is one login
  for everyone, so the database limits what the app as a whole can do, and the server
  decides between a student, a faculty member and the admin. Someone holding the
  `pbl_app` password could change any project's status or any student's marks. Keep that password
  secret like any other.
- **Sessions live in one server process's memory.** Restarting the server signs
  everyone out, and running several server processes would need a shared session store.
- **The session cookie is only `Secure` when the request came over HTTPS.** Put the app
  behind HTTPS before letting other computers in, or passwords and the cookie cross the
  network unencrypted.
- **Uploaded files are checked by extension, not scanned.** The server never opens them,
  and a PDF report is drawn by PDF.js in the page, but a file could still carry a macro or
  malware. The college's antivirus on the downloading machine is the last line.
- The sample accounts share one password. Real accounts should be made on the People
  page, which hands out a temporary password that has to be changed.
- **Anyone in the college who gets a link can submit through it.** A link isn't tied to a
  class list, because the app has no record of which student is in which division. The
  faculty member sees every team on the link's page and can reject a project from the
  wrong class, and closes the link after the deadline.
- The similarity score is a hint for a human, not proof of copying. The faculty member decides.
