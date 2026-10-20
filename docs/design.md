# Database design

## What it has to do

- Keep every PBL project: title, abstract, subject, faculty member, year, software or hardware, status, team, tags, links, report, presentation and marks.
- Find past projects by keyword and by meaning, and warn when a new idea is close to an old one.
- Enforce the rules that actually hold in our college, and nothing more: teams of any size, students in several projects at once, and marks out of whatever each subject is marked out of.
- Let a team submit its finished project with the report to a faculty member, who approves or rejects it and gives the marks.
- Keep marks private to the team and its faculty member unless the team chooses to show them.
- Only MIT-WPU students and faculty can use it.
- Show trends: which stacks come up each year, repeated ideas, faculty load.

Sizes we designed for: a student does around 5 PBLs a semester, so a department of a few
hundred students adds several hundred projects a year. Ten years is a few thousand
projects and around 15,000 member rows. Everything here is comfortable up to tens of
thousands of projects.

## Entities and relationships

- A **user** is a student or a faculty member (`role`), always with an `@mitwpu.edu.in` email. Students have a PRN; faculty don't. A faculty member can also be an admin (the PBL coordinator).
- A **subject** (DBMS-PBL, ML-PBL, CN-TH, ...) has many projects and its own `max_marks`.
- A **project** belongs to one subject and is submitted to one faculty member (`faculty_id`, a user with the faculty role), who approves or rejects it (`decided_at` records when) and gives the marks.
- Projects and students are many-to-many through **project_members**, which also stores who leads the team. A team has no fixed size, and a student can be in any number of projects.
- Projects and **tags** are many-to-many through **project_tags**.
- A project has any number of **links** (GitHub, working demo, video) and up to two **files**: exactly one report (a PDF) and at most one presentation. Each file row records who uploaded it.

The ER diagram is in the README (GitHub draws it from the Mermaid source).

| Table | Primary key | Notable rules |
|---|---|---|
| users | user_id | email unique, lowercase and `@mitwpu.edu.in`; PRN 10 digits, only for students; only faculty can be admins; bcrypt hash only |
| subjects | subject_id | code unique; max_marks > 0 |
| projects | project_id | year format and sequence checks; status list; `decided_at` set exactly when decided; type list; marks 0 to the subject's max, only once approved; title once per subject and year; generated search_text |
| project_members | (project_id, user_id) | students only; one leader per team |
| tags | tag_id | name unique ignoring case |
| project_tags | (project_id, tag_id) | link table |
| project_links | link_id | http or https only; the same URL once per project |
| project_files | file_id | one report and at most one ppt per project; reports are PDFs; the report can't be removed; 1 byte to 20 MB; storage_path unique |

## Normalisation

Faculty keep PBL records in a sheet like this. `data/projects.csv` is in this shape on
purpose, and `scripts/load_data.py` does the normalising.

| Year | Subject | Title | Faculty | Faculty email | Type | Members | Tags | Links | Marks |
|---|---|---|---|---|---|---|---|---|---|
| 2025-26 | DBMS-PBL | College Library Management | Prof. A. Kulkarni | akulkarni@... | software | Yash, Tanvi | PostgreSQL | GitHub | 23 |
| 2024-25 | IOT-PBL | Automatic Plant Watering System with ESP32 | Prof. R. Iyer | riyer@... | hardware | Aarav, Sayali | ESP32, Blynk | | 15.5 |

Problems with it:

- **Update anomaly**: the faculty member's email is repeated on every row. Change it in one place and the rows disagree.
- **Insertion anomaly**: a new faculty member or subject can't be recorded until some project uses it.
- **Deletion anomaly**: deleting the only project of a subject loses the subject and what it is marked out of.
- Members, tags and links are lists inside one cell, so "which projects used ESP32?" means string matching.

**1NF, one value per cell.** The lists move to their own tables: members to
`project_members`, tags to `project_tags` (with the names in `tags`), links to
`project_links`. Reports and presentations get `project_files`, one row per file.

**2NF, no partial dependencies.** In `project_members` the key is (project_id, user_id). A
student's name depends only on user_id, so it lives in `users`, not in the link table.
The same goes for `project_tags`: the tag's name depends only on tag_id.

**3NF, no transitive dependencies.** In the sheet, the faculty email depends on the
faculty member, not on the project. `projects` keeps only `faculty_id`; name and email
live in `users`. The subject's name and maximum marks depend on the subject, so
`projects` keeps only `subject_id`. That is also why marks are checked against
`subjects.max_marks` instead of storing an "out of" on every project.

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
| One `users` table with a `role` column, not separate student and faculty tables | A team member and a faculty member are both people who sign in. One table gives one sign-in function and lets `project_members` and `projects.faculty_id` point at the same place. Two CHECK constraints keep the PRN for students only and the admin flag for faculty only; triggers make sure a team member is a student and a project's faculty member is faculty. |
| No limit on team size or on projects per student | That is how PBL works here: teams of 2 to 5, and around 5 projects per student each semester, one per subject. A limit in the database would only get in the way. |
| `max_marks` on the subject, and one `marks` column on the project | Labs are marked out of 33 and a theory mini project out of 5, but the admin can set anything. Each project gets one total, entered by its faculty member; the trigger checks it against its own subject. |
| Software / hardware / both as a column, the stack as tags | Every project is exactly one of the three, so it is a column with a CHECK. The stack is a list of any length, so it goes in `tags`. |
| Files in a storage bucket, details in `project_files` | A 15 MB report doesn't belong in a table row. The bucket holds the bytes; the table holds the name, size, kind, project and uploader, with foreign keys, so the database still knows what belongs to what. |
| The report is required and must be a PDF | It is the project; a submission without it can't be reviewed. A PDF opens in any browser, so the project page can show it straight away. `submit_project()` takes the report, `reports_are_pdf` checks the type, and the `keep_report` trigger stops it being deleted while the project exists. A new report replaces the old row in place. |
| One step from submission to marks | Teams submit finished work, so there is no separate idea stage: `submitted`, then `approved` or `rejected` once. Marks are only allowed on approved projects. |
| `marks_public` on the project | Marks belong to the team. The app shows them to the team, its faculty member and the coordinator, and to everyone else only when the team turns this on. |
| College emails only | A CHECK (`college_email`) on `users`, so no other address can get in, whichever way a user is added. |
| Own schema `pbl` | Supabase exposes `public` through an automatic REST API. Tables in `pbl` are not reachable that way. |
| `GENERATED ALWAYS AS IDENTITY` keys | SQL-standard; the database always picks the id, so ids can't be forced or collide. |
| Status as a CHECK list, not an ENUM | Same safety, and a CHECK is easier to change later. |
| Academic year as text with two CHECKs | It's how everyone writes it. Postgres tests CHECK constraints in alphabetical order of their names, so `academic_year_format` (regex) always runs before `academic_year_sequence` (the `::int` cast) and bad input gets a clear error instead of a cast error. |
| `ON DELETE CASCADE` only from projects to its own detail rows | Members, tags, links and file records mean nothing without the project. Deleting a user or tag that is still used is refused, because that would rewrite history. Users who leave are switched off (`is_active`) instead. |
| Embedding as a column on `projects` | One embedding per project, made from that project's own title and abstract. Ordinary queries list their columns, so the 1.5 KB of numbers is only read by the searches that need it. |
| Python sends embeddings as a plain float array | The SQL functions cast it to `vector(384)`. The app needs no pgvector client library, and an array of the wrong length is rejected by the cast. |
| `similarity_band()` function | The 0.70 / 0.50 / 0.35 cut-offs live in one place. The app, the views and the approval trigger all use it. |
| Projects are created only through `submit_project()` | One call, one transaction: the project, team, tags, links, report and presentation are saved together, and if any PRN is wrong nothing is saved. Status is forced to `submitted` and the year to the current one. Tags that don't exist yet are added. |
| Hybrid search with Reciprocal Rank Fusion | Keyword ranks and similarity scores aren't on the same scale, so they can't be added. RRF only uses each project's position in each list: `1/(60 + rank)`. |
| Passwords hashed and checked inside the database (pgcrypto bcrypt, cost 11) | The hash never leaves the database and the app's login can't read it. One check takes about 80 ms, which a person doesn't notice and a guesser does. |

## Indexes

| Index | Used by |
|---|---|
| GIN on `projects.search_text` | keyword search (`@@`) |
| HNSW on `projects.embedding` (cosine) | nearest-neighbour search (`ORDER BY embedding <=> query LIMIT n`) |
| `projects(faculty_id)`, `projects(subject_id, academic_year)` | faculty pages, filters by subject and year |
| `project_members(user_id)` | a student's own projects on their home page |
| `project_tags(tag_id)` | joins from the other side; Postgres doesn't index foreign keys by itself |
| unique `project_files(project_id, kind)` | one report and one presentation per project; also serves lookups by project |
| unique `projects(subject_id, academic_year, lower(title))` | stops double submits |
| unique `lower(name)` on tags | stops 'PostgreSQL' and 'postgresql' existing together |
| partial unique `project_members(project_id) WHERE is_leader` | one leader per team |

With 60 rows Postgres reads whole tables instead of using these indexes, because that is
cheaper. Step 20 of `sql/demo.sql` turns sequential scans off to show the plans that use
the GIN and HNSW indexes.

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
