# Database design

## What it has to do

- Keep every PBL project: title, abstract, subject, class, faculty member, year, software or hardware, status, team, tags, links, report, presentation and each student's marks.
- Find past projects by keyword and by meaning, and warn when a new idea is close to an old one.
- Enforce the rules that actually hold in our college, and nothing more: teams of whatever size the faculty member sets, students in several projects at once, and marks out of whatever each submission is marked out of.
- Let a faculty member collect a class's projects through one submission link (subject, class, what it is for), approve or reject each one, give every student their own marks, and export them.
- Keep marks private to the student, the team and the faculty member unless the team chooses to show its team score.
- Only MIT-WPU students and faculty can use it.
- Show trends: which stacks come up each year, repeated ideas, faculty load.

Sizes we designed for: a student does around 5 PBLs a semester, so a department of a few
hundred students adds several hundred projects a year. Ten years is a few thousand
projects and around 15,000 member rows. Everything here is comfortable up to tens of
thousands of projects.

## Entities and relationships

- A **user** is a student or a faculty member (`role`), always with an `@mitwpu.edu.in` email. Students have a PRN; faculty don't. A faculty member can also be an admin (the PBL coordinator).
- A **subject** (DBMS-PBL, ML-PBL, CN-TH, ...) has its own usual `max_marks`.
- A **submission link** is made by one faculty member (`faculty_id`, a user with the faculty role) for one subject, academic year, class (`TY ECE Div A`) and purpose (`Semester PBL`, `LCA 1`). It has a random `code` that forms its URL, a `max_marks` that starts as the subject's, the fewest and most students a team can have (`min_members`, `max_members`; any size until set), and can be closed. A faculty member has many links; a subject has many links.
- A **project** comes in through one submission link. The link's faculty member approves or rejects it (`decided_at` records when).
- Projects and students are many-to-many through **project_members**, which also stores who leads the team and each student's `marks`. A team has as many students as its link allows, and a student can be in any number of projects, but only one live project per link.
- Projects and **tags** are many-to-many through **project_tags**.
- A project has any number of **links** (GitHub, working demo, video) and up to two **files**: exactly one report (a PDF) and at most one presentation. Each file row records who uploaded it.

![ER diagram](screenshots/er-diagram.png)

*ER diagram of schema `pbl`, taken from Supabase's Schema Visualizer.*

| Table | Primary key | Notable rules |
|---|---|---|
| users | user_id | email unique, lowercase and `@mitwpu.edu.in`; PRN 10 digits, only for students; only faculty can be admins; bcrypt hash only |
| subjects | subject_id | code unique; max_marks > 0 |
| submission_links | submission_link_id | code unique, random, 6 to 16 lowercase letters or digits; faculty only; year format and sequence checks; max_marks > 0 and not below marks already given; min_members at least 1, max_members not below it, and neither one leaving out a team already in the link; one link per faculty member, subject, year, class and purpose |
| projects | project_id | status list; `decided_at` set exactly when decided; type list; title once per link; generated search_text |
| project_members | (project_id, user_id) | students only; one leader per team; one live project per student per link; marks 0 to the link's max, only once approved |
| tags | tag_id | name unique ignoring case |
| project_tags | (project_id, tag_id) | link table |
| project_links | link_id | http or https only; the same URL once per project |
| project_files | file_id | one report and at most one ppt per project; reports are PDFs; the report can't be removed; 1 byte to 20 MB; storage_path unique |

## Rules the database enforces

| Rule | How |
|---|---|
| A team has as many students as its link allows: the faculty member sets the fewest and the most, or leaves it at any size | `team_size_range` CHECK; `check_member` trigger refuses one student too many; `submit_project()` checks the whole team; `check_submission_link` refuses sizes that a team already in the link doesn't fit |
| A student can be in any number of projects in a year | Nothing limits it, on purpose |
| A student has one live project per submission link (a rejected one doesn't count, so the team can try again) | `check_member` trigger, with an advisory lock so two submits at once can't both get in |
| Only students can be team members | `check_member` trigger |
| One leader per team | Partial unique index |
| A submission link belongs to a faculty user | `check_submission_link` trigger |
| A link's code is random and comes from the database, never from the app | `gen_random_bytes()` default, and `pbl_app` has no rights on the column |
| A closed link takes no new projects | `submit_project()` |
| Each student's marks can't be negative or more than the link's maximum, which starts as the subject's (33 for a lab, 5 for a theory mini project) | CHECK + `check_member` trigger |
| A link's maximum can't go below marks already given | `check_submission_link` trigger |
| Only approved projects can be marked | `check_member` trigger |
| The team score is the average of its members' marks, shown only once all of them have marks | `team_marks` view |
| Status is submitted, then approved or rejected once; the trigger records the date | CHECK + `check_project` trigger, and a CHECK that `decided_at` is set exactly when it was decided |
| Every account has an `@mitwpu.edu.in` email | `college_email` CHECK |
| A project is submitted with its report; one report (a PDF) and at most one presentation per project; the report can be replaced but not removed | `submit_project()`, unique `(project_id, kind)`, `reports_are_pdf` CHECK, `keep_report` trigger |
| Approving a near duplicate (similarity 0.70 or more) needs a review note | `check_near_duplicate` trigger, using pgvector |
| A link's academic year looks like `2026-27`, and 27 follows 26 | Two named CHECK constraints (regex, then arithmetic) |
| The same title can't be submitted twice through one link | Unique index on `(submission_link_id, lower(title))` |
| Links start with http:// or https://, once per project | CHECK + unique constraint |
| Files are up to 20 MB | CHECK on `size_bytes` |
| Tag names are unique ignoring case | Unique index on `lower(name)` |
| Students have a 10-digit PRN, faculty don't; only faculty can be admins | Two CHECK constraints on `users` |
| Deleting a project removes its members, tags, links and file records; a user still in a team can't be deleted | `ON DELETE CASCADE` from projects only |
| Editing a title or abstract throws away its old embedding | `clear_stale_embedding` trigger |
| Only bcrypt hashes are stored | `hash_password()` with pgcrypto |

## Normalisation

Faculty keep PBL records in a sheet like this. `data/projects.csv` is in this shape on
purpose, and `scripts/load_data.py` does the normalising.

| Year | Subject | Class | Purpose | Title | Faculty | Faculty email | Type | Members | Tags | Links | Marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2025-26 | DBMS-PBL | TY ECE Div A | Semester PBL | College Library Management | Prof. A. Kulkarni | akulkarni@... | software | Yash, Tanvi | PostgreSQL | GitHub | 23.5, 22.5 |
| 2024-25 | IOT-PBL | TY ECE Div C | Semester PBL | Automatic Plant Watering System with ESP32 | Prof. R. Iyer | riyer@... | hardware | Aarav, Sayali | ESP32, Blynk | | 15, 16 |

Problems with it:

- **Update anomaly**: the faculty member's email is repeated on every row. Change it in one place and the rows disagree.
- **Insertion anomaly**: a new faculty member or subject can't be recorded until some project uses it.
- **Deletion anomaly**: deleting the only project of a class loses the fact that the class was ever asked to submit, and what it was marked out of.
- Members, tags, links and marks are lists inside one cell, so "which projects used ESP32?" means string matching, and which marks belong to which student depends on the order of two lists.

**1NF, one value per cell.** The lists move to their own tables: members to
`project_members`, tags to `project_tags` (with the names in `tags`), links to
`project_links`. Reports and presentations get `project_files`, one row per file.

**2NF, no partial dependencies.** In `project_members` the key is (project_id, user_id). A
student's marks depend on both (the same student gets different marks in different
projects), so they stay there. A student's name depends only on user_id, so it lives in
`users`, not in the link table. The same goes for `project_tags`: the tag's name depends
only on tag_id.

**3NF, no transitive dependencies.** In the sheet, the year, subject, class, purpose and
faculty member are the same for every project a class submitted for one purpose: they
depend on the submission, not on the project. They move to `submission_links`, and
`projects` keeps only `submission_link_id`. The faculty email depends on the faculty
member, so `submission_links` keeps only `faculty_id`; name and email live in `users`.
The subject's name depends on the subject, so the link keeps only `subject_id`. The
"out of" belongs to the submission (one faculty member may mark an LCA out of 10 and the
semester PBL out of 33), so it is `submission_links.max_marks`, and each student's marks
are checked against it. The team score is the average of the members' marks, so it isn't
stored at all: the `team_marks` view works it out.

Two columns look like they break this, and both are on purpose:

- `projects.search_text` is computed from title and abstract. It is a `GENERATED ALWAYS ... STORED`
  column, so Postgres keeps it up to date and nobody can write a wrong value into it. It
  exists so the GIN index has something to index.
- `projects.embedding` is also derived from title and abstract. It can't be a generated
  column because Postgres can't run the model. Instead the `clear_stale_embedding`
  trigger sets it to NULL whenever the title or abstract changes, and
  `embed_projects.py` makes a new one.

## Decisions and why

| Decision | Why |
|---|---|
| One `users` table with a `role` column, not separate student and faculty tables | A team member and a faculty member are both people who sign in. One table gives one sign-in function and lets `project_members` and `submission_links.faculty_id` point at the same place. Two CHECK constraints keep the PRN for students only and the admin flag for faculty only; triggers make sure a team member is a student and a link's owner is faculty. |
| Projects come in only through submission links | The faculty member decides which class submits what, and every project lands in the right class's list without anyone picking a subject or a faculty member from a menu. A student can't send a project to a faculty member who never asked for it. |
| A random code for each link, made by the database | The code is the link's URL, so it must not be guessable. `encode(gen_random_bytes(6), 'hex')` gives 12 hex characters (2^48 possibilities). `pbl_app` can't insert or change the column, so nobody can choose an easy one. |
| One live project per student per link | A class submits one project per team for each purpose. The `check_member` trigger refuses a second one, and takes a `pg_advisory_xact_lock` on (link, student) first so two submits at the same moment can't both pass the check. A rejected project doesn't count, so the team can submit a better one. |
| Team size on the link, set by the faculty member | Teams here are usually 2 to 5, but each faculty member decides for their own submission, so `min_members` and `max_members` sit on the link, like `max_marks`. Empty means any size. `check_member` refuses one student too many, after a `pg_advisory_xact_lock` on the project so two students joining at once can't both get in. The fewest is checked by `submit_project()`, because a team is added one student at a time. Changing the sizes is refused if a team already in the link wouldn't fit; a rejected team doesn't count. |
| No limit on projects per student | Around 5 projects per student each semester, one per subject. A limit in the database would only get in the way. |
| `max_marks` on the link, `marks` on each team member | Labs are usually marked out of 33 and a theory mini project out of 5, but each submission can differ, so the faculty member sets the total on the link (empty means the subject's usual one, filled in by the `check_submission_link` trigger). Students in a team often don't get the same marks, so each one is marked separately and `check_member` checks the marks against the link. The team score is their average. Lowering a link's maximum below marks already given is refused. |
| Software / hardware / both as a column, the stack as tags | Every project is exactly one of the three, so it is a column with a CHECK. The stack is a list of any length, so it goes in `tags`. |
| Files in a storage bucket, details in `project_files` | A 15 MB report doesn't belong in a table row. The bucket holds the bytes; the table holds the name, size, kind, project and uploader, with foreign keys, so the database still knows what belongs to what. |
| The report is required and must be a PDF | It is the project; a submission without it can't be reviewed. A PDF opens in any browser, so the project page can show it straight away. `submit_project()` takes the report, `reports_are_pdf` checks the type, and the `keep_report` trigger stops it being deleted while the project exists. A new report replaces the old row in place. |
| One step from submission to marks | Teams submit finished work, so there is no separate idea stage: `submitted`, then `approved` or `rejected` once. Marks are only allowed on approved projects. |
| `marks_public` on the project | The team score belongs to the team. The app shows it to the team, its faculty member and the coordinator, and to everyone else only when the team turns this on. A student's own marks are shown only to that student, the faculty member and the coordinator. |
| College emails only | A CHECK (`college_email`) on `users`, so no other address can get in, whichever way a user is added. |
| Own schema `pbl` | Supabase exposes `public` through an automatic REST API. Tables in `pbl` are not reachable that way. |
| `GENERATED ALWAYS AS IDENTITY` keys | SQL-standard; the database always picks the id, so ids can't be forced or collide. |
| Status as a CHECK list, not an ENUM | Same safety, and a CHECK is easier to change later. |
| Academic year as text with two CHECKs, on the link | It's how everyone writes it. Postgres tests CHECK constraints in alphabetical order of their names, so `academic_year_format` (regex) always runs before `academic_year_sequence` (the `::int` cast) and bad input gets a clear error instead of a cast error. |
| `ON DELETE CASCADE` only from projects to its own detail rows | Members, tags, links and file records mean nothing without the project. Deleting a user or tag that is still used is refused, because that would rewrite history. Users who leave are switched off (`is_active`) instead. |
| Embedding as a column on `projects` | One embedding per project, made from that project's own title and abstract. Ordinary queries list their columns, so the 1.5 KB of numbers is only read by the searches that need it. |
| Python sends embeddings as a plain float array | The SQL functions cast it to `vector(384)`. The app needs no pgvector client library, and an array of the wrong length is rejected by the cast. |
| `similarity_band()` function | The 0.70 / 0.50 / 0.35 cut-offs live in one place. The app, the views and the approval trigger all use it. |
| Projects are created only through `submit_project()` | One call, one transaction: the project, team, tags, links, report and presentation are saved together, and if any PRN is wrong nothing is saved. It takes the link's code, refuses a closed link, and forces status `submitted`. Tags that don't exist yet are added. |
| Hybrid search with Reciprocal Rank Fusion | Keyword ranks and similarity scores aren't on the same scale, so they can't be added. RRF only uses each project's position in each list: `1/(60 + rank)`. |
| Passwords hashed and checked inside the database (pgcrypto bcrypt, cost 11) | The hash never leaves the database and the app's login can't read it. One check takes about 80 ms, which a person doesn't notice and a guesser does. |

## Indexes

| Index | Used by |
|---|---|
| GIN on `projects.search_text` | keyword search (`@@`) |
| HNSW on `projects.embedding` (cosine) | nearest-neighbour search (`ORDER BY embedding <=> query LIMIT n`) |
| `submission_links(faculty_id)`, `submission_links(subject_id, academic_year)` | a faculty member's links, filters by subject and year |
| `projects(submission_link_id)` | the projects that came in through one link |
| `project_members(user_id)` | a student's own projects on their home page |
| `project_tags(tag_id)` | joins from the other side; Postgres doesn't index foreign keys by itself |
| unique `project_files(project_id, kind)` | one report and one presentation per project; also serves lookups by project |
| unique `projects(submission_link_id, lower(title))` | stops double submits |
| unique `submission_links(faculty_id, subject_id, academic_year, lower(class_name), lower(purpose))` | stops a faculty member making the same link twice |
| unique `lower(name)` on tags | stops 'PostgreSQL' and 'postgresql' existing together |
| partial unique `project_members(project_id) WHERE is_leader` | one leader per team |

With 60 rows Postgres reads whole tables instead of using these indexes, because that is
cheaper. Step 21 of `sql/demo.sql` turns sequential scans off to show the plans that use
the GIN, HNSW and link indexes.

HNSW is approximate: it can occasionally miss the true nearest neighbour in exchange for
speed. Under a few thousand rows the difference doesn't show.

## Choosing the similarity cut-offs

all-MiniLM-L6-v2 turns each `title. abstract` into 384 numbers; similarity is
`1 - cosine distance`. On the sample data:

- pairs that are the same idea scored **0.50 to 0.76** (face recognition attendance 2022-23 vs 2025-26: 0.76; leaf disease CNN vs tomato leaf on mobile: 0.71; IR parking vs IoT parking finder: 0.68; the two library systems: 0.53; heart disease vs cardiac risk: 0.50)
- different ideas on related topics scored **0.42 to 0.57** (driver drowsiness vs driver fatigue: 0.57; accident alert vs driver fatigue: 0.56)
- unrelated pairs were mostly below 0.30

The ranges overlap, which is why a score is a prompt for a human, not a verdict. The
labels: 0.70 and up is a **near duplicate** (approval needs a written note), 0.50-0.70
**similar**, 0.35-0.50 **related**, below that **different**. Re-check them once real
projects are loaded:

```sql
SELECT round((1 - (a.embedding <=> b.embedding))::numeric, 2) AS similarity,
       a.title, b.title
FROM pbl.projects a
JOIN pbl.projects b ON a.project_id < b.project_id
WHERE a.embedding IS NOT NULL AND b.embedding IS NOT NULL
ORDER BY 1 DESC
LIMIT 40;
```

## At ten times the size

- Search and the review queue use the indexes and stay in milliseconds.
- `repeated_ideas` compares every pair (a self-join), which grows with the square of the
  number of projects. Around 5,000 projects it would be worth replacing with a `LATERAL`
  nearest-neighbour query like the one in `review_queue`.
- Files don't touch the database beyond one small row each, so the bucket can grow
  without slowing anything down.
- The model runs inside the web server process on CPU. Loading it takes about 10
  seconds once, then embedding one idea takes under 10 ms.
