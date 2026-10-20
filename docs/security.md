# Security

## What we protect, and from whom

- **Personal data**: names, PRNs and emails of students and faculty.
- **Accounts**: passwords, and who is allowed to act as whom.
- **Marks**: only a project's own faculty member should be able to enter or change them, and
  only the team, that faculty member and the coordinator should see them unless the team
  makes them public.
- **Work in progress**: a project waiting for review, or rejected, is seen only by its team,
  its faculty member and the coordinator.
- **Decisions**: only a project's faculty member should approve or reject it.
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
| `pbl_app` can only update a project's status, review note, marks, `marks_public` and embedding | column-level `GRANT UPDATE` | The app can't rename a project, move it to another subject or faculty member, or change its year |
| Passwords hashed with bcrypt (pgcrypto `crypt()`, cost 11, about 80 ms a check) | `hash_password()` in `03_functions.sql` | A stolen copy of the table gives no passwords, and guessing them is slow |
| Passwords are checked inside the database | `sign_in()`, `SECURITY DEFINER` | The app sends a login and a password and gets back the account or "wrong"; it never sees a hash |
| Same answer for an unknown login and a wrong password, with the same bcrypt delay | `sign_in()` | The form can't be used to find out which PRNs or emails exist |
| A switched-off account is only told so after the right password | `sign_in()` | Guessing can't find out who has left |
| Temporary passwords are random (72 bits), shown once, and must be changed at the next sign-in | `temporary_password()`, `create_user()`, `reset_password()` | The coordinator never chooses or keeps anyone's real password |
| `hash_password()` and `temporary_password()` can't be called by `pbl_app` | not in the EXECUTE list | Only the functions that need them can use them |
| `submit_project()` is `SECURITY DEFINER` | `03_functions.sql` | It checks the leader is a student, the faculty member is current faculty, every PRN exists and the report is there, forces status `submitted` and the current year, and saves nothing if any check fails |
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
- **Who may do what is checked before anything runs.** Students can't open Review,
  People or Subjects (403). Only students can submit a project. A faculty member
  can decide on and mark only projects where `faculty_id` is their own id: the UPDATE
  itself has `WHERE faculty_id = <me>`, so another faculty member's project is not found
  (404). Links and files can be added or removed by the team, the project's faculty
  member or the admin, and nobody else (403).
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
- **Marks and unfinished work stay with the team.** The project page sends marks only to
  the team, its faculty member and the coordinator, unless the team has switched
  `marks_public` on; only team members can switch it. A project that is waiting or was
  rejected answers 404 to everyone else, and search only lists approved projects.
- **Uploads.** The report has to be a `.pdf`, the presentation a `.pptx` or `.pdf`, at most
  20 MB, and a PDF has to start with `%PDF-`. This is checked before the file is stored.
  The stored name is `<project id>/<random hex><extension>`; the name the user gave is
  only kept as text in `project_files`, so it can't be used to write somewhere else.
  Presentations download as attachments. A PDF can be opened inline so the project page
  can show the report, and that answer may only be framed by the app's own pages.
- **The storage key stays on the server.** The B2 application key is read from `.env`
  by `finder/storage.py`. It works on one bucket only, the browser never talks to B2,
  and the bucket is private.
- **Security headers.** A Content Security Policy that only allows the app's own scripts,
  styles and fonts, no framing (apart from the report, by the app itself), `nosniff`, and `no-store` on every API answer.
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
  message (for example "Marks 34.0 are more than the maximum 33.0 for this subject").
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
| See marks | own projects, or when the team made them public | own projects, or public | any project |
| Make the team's marks public or private | own projects | no | no |
| Submit a project with its report | yes | no | no |
| Add or remove links, upload or remove files | own projects | own projects | any project |
| Approve or reject a submission | no | own projects | own projects |
| Enter marks | no | own projects | own projects |
| Add people, reset passwords, switch accounts off, make admins | no | no | yes |
| Add subjects and set their maximum marks | no | no | yes |
| Change own password (needs the current one) | yes | yes | yes |

The admin is a faculty member with `is_admin` set, so they review and mark their own
projects like anyone else; being admin doesn't let them mark someone else's project.

## Tested

`tests/test_security.py` runs as `pbl_app` and checks it can't read password hashes,
delete projects or users, insert projects or users directly, change anything on a
project except the review and marks columns, call `hash_password()`, or become the
owner; that `submit_project()` saves nothing when one PRN is wrong; and that it needs
a PDF report.
`tests/test_auth.py` covers sign-in by PRN or email, the same answer for unknown logins
and wrong passwords, switched-off accounts, bcrypt storage, and password changes and
resets. `tests/test_api.py` checks the same from the app's side: nothing before sign-in,
other roles' pages refused, a faculty member unable to decide on or mark another's
project, waiting projects hidden from outsiders, marks hidden until the team makes them
public, links and files refused to outsiders, only PDF reports accepted, college emails only,
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
  `pbl_app` password could change any project's status or marks. Keep that password
  secret like any other.
- **Sessions live in one server process's memory.** Restarting the server signs
  everyone out, and running several server processes would need a shared session store.
- **The session cookie is only `Secure` when the request came over HTTPS.** Put the app
  behind HTTPS before letting other computers in, or passwords and the cookie cross the
  network unencrypted.
- **Uploaded files are checked by extension, not scanned.** The server never opens them,
  and a PDF report is shown by the browser's own viewer, but a file could still carry a macro or
  malware. The college's antivirus on the downloading machine is the last line.
- The sample accounts share one password. Real accounts should be made on the People
  page, which hands out a temporary password that has to be changed.
- The similarity score is a hint for a human, not proof of copying. The faculty member decides.
