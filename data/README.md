# Sample data

Made up for testing and the demo. Nothing here is a real person, apart from the name of
the demo student `1032240101` (Rohan Deogaonkar, a team member; PRN and email are made up).

| File | Rows | Columns |
|---|---|---|
| `faculty.csv` | 8 | name, email, is_active, is_admin |
| `students.csv` | 126 | prn, name, email |
| `projects.csv` | 60 | academic_year, subject, title, abstract, faculty_email, status, type, members, tags, marks, review_note, links |

`projects.csv` is laid out the way faculty usually keep a sheet: `members`, `tags` and
`links` hold several values separated by `;`. The first PRN in `members` is the team
leader. Each link is written `label|url`, for example
`GitHub|https://github.com/example/tank`. `type` is `software`, `hardware` or `both`, and
`marks` is the project's total out of its subject's maximum (empty if not marked yet).
`scripts/load_data.py` splits these into the normalised tables; tags that don't exist
yet are added.

The projects run from 2021-22 to 2026-27 across DBMS-PBL, ML-PBL and IOT-PBL. The
subjects themselves, and what each is marked out of, come from
`sql/07_reference_data.sql`. The topics are ones that come up often in engineering PBLs,
and a few are deliberately close to each other so the duplicate detection has something
to find. Names, PRNs and emails are invented; emails use the reserved `example.edu` domain.

`scripts/load_data.py` also gives every student and faculty member the password in
`SEED_PASSWORD` from `.env`. Students sign in with their PRN, faculty with their email.
Dr. N. Shaikh is the admin (PBL coordinator), and Dr. K. Menon, who has left, is
switched off. That shared password is for sample data only: real users are added on the
People page, which gives each person a temporary password they have to change.

To add the department's real projects, append rows to `projects.csv` with titles and
abstracts only (no names, PRNs or phone numbers in a public repository), leave
`members` and `marks` empty if they aren't known, and run `python -m scripts.load_data`
and then `python -m scripts.embed_projects`.
