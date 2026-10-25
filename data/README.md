# Sample data

Made up for testing and the demo. Nothing here is a real person, apart from the two demo
students `1262241783` (Rohan Deogaonkar) and `1262241766` (Krishna Bhand), who are on the
team; their emails are made up.

| File | Rows | Columns |
|---|---|---|
| `faculty.csv` | 8 | name, email, is_active, is_admin |
| `students.csv` | 126 | prn, name, email |
| `projects.csv` | 60 | academic_year, subject, class, purpose, title, abstract, faculty_email, status, type, members, tags, marks, review_note, links |

`projects.csv` is laid out the way faculty usually keep a sheet: `members`, `tags`,
`marks` and `links` hold several values separated by `;`. The first PRN in `members` is
the team leader. `marks` has one value per member, in the same order as `members`, out of
the subject's maximum (empty if not marked yet; only approved projects have marks). Each
link is written `label|url`, for example `GitHub|https://github.com/example/tank`. `type`
is `software`, `hardware` or `both`. `status` is `submitted` (waiting for the faculty
member), `approved` or `rejected`. `class` (`TY ECE Div A`) and `purpose`
(`Semester PBL`) say which submission the project came in through.
`scripts/load_data.py` splits these into the normalised tables: one submission link for
each faculty member, subject, year, class and purpose (open for this year, closed for
earlier ones), then the projects, their members with their marks, tags and links. Tags
that don't exist yet are added.

The projects run from 2021-22 to 2026-27 across DBMS-PBL, ML-PBL and IOT-PBL. The
subjects themselves, and what each is marked out of, come from
`sql/07_reference_data.sql`. The topics are ones that come up often in engineering PBLs,
and a few are deliberately close to each other so the duplicate detection has something
to find. Names, PRNs and emails are invented. Emails end in `@mitwpu.edu.in`, because the
database only accepts college emails, but none of them belong to a real person.

There are no real reports in the repository. For every project, `scripts/load_data.py`
makes a one-page PDF with the title, subject, faculty member, team and abstract
(`scripts/sample_reports.py`) and stores it as the project's report, so each project page
has something to show.

`scripts/load_data.py` also gives every student and faculty member the password in
`SEED_PASSWORD` from `.env`. Students sign in with their PRN, faculty with their email.
Dr. N. Shaikh is the admin (PBL coordinator), and Dr. K. Menon, who has left, is
switched off. That shared password is for sample data only: real users are added on the
People page, which gives each person a temporary password they have to change.

To add the department's real projects, append rows to `projects.csv` with titles and
abstracts only (no names, PRNs or phone numbers in a public repository), leave
`members` and `marks` empty if they aren't known, and run `python -m scripts.load_data`
and then `python -m scripts.embed_projects`.
