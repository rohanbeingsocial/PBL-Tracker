# Viva notes

## Demo order (about 8 minutes)

Before the viva: open the app once so the model is loaded, and reset the database if you
rehearsed on it:

```
python -m scripts.setup_db --reset --yes
python -m scripts.load_data
python -m scripts.embed_projects
```

All sample accounts use the `SEED_PASSWORD` from `.env`. With `DEMO_SWITCHER=on`, use the
sidebar's "Switch account" menu instead of signing out and in again. Keep two small PDFs
and a .pptx on the desktop for steps 3 and 4.

1. **The problem (30 s).** Sign in as student `1032240102` (Akash Mane). Trends page:
   the most used tags per year, then "Ideas that keep coming back". Face recognition
   attendance was done in 2022-23 and 2025-26, and a third team submitted it again this year.
2. **Keywords vs. meaning (1 min).** Search page, type *predict heart attack risk from
   patient data*. Switch to **Keywords**: nothing. Switch to **Meaning**: Cardiac Risk
   Estimation and Heart Disease Prediction come first, although the cardiac project
   never says "heart". Then filter by subject IOT-PBL, type hardware, tag ESP32.
3. **Submit a project (1 min).** Submit page. Title *Attendance from classroom CCTV*,
   abstract *Recognise student faces from the CCTV camera in each classroom and mark
   attendance automatically during the first ten minutes.* The side panel shows the
   closest past projects, the top one marked as a near duplicate. Pick ML-PBL and
   Prof. S. Rao, type software, teammates `1032240105` and `1032240106`, tags Python and
   OpenCV, and a GitHub link. Press Submit without a report: it asks for the PDF. Attach
   one of the PDFs and submit. The project page opens with the report on the left,
   marked "Waiting for review".
4. **Links and files (1 min).** Sign in as `1032240101` (Rohan). On the Smart Water Tank
   project, add a working demo link, replace the report with the other PDF and add the
   .pptx as the presentation. Try a .txt as the report: refused. The report can only be
   replaced, never removed.
5. **Faculty (1.5 min).** Sign in as `srao@mitwpu.edu.in`. The dashboard shows what is waiting and how close each submission is to a past project.
   Open *Automatic Classroom Attendance from CCTV Footage*: the report is on the left,
   the decision on the right. Approve with an empty note and the database refuses, naming
   the closest project. Write a note and approve again with 28 marks: it goes through,
   and the approval date appears.
6. **Marks (30 s).** Sign in as `riyer@mitwpu.edu.in`. Open the water tank project: it is
   out of 33. Type 34: refused with the database's message. Type 27.5: saved. Switch to
   Akash, who isn't in the team: the marks are hidden. Switch to Rohan, turn on "Show our
   marks to everyone", and Akash now sees 27.5 / 33.
7. **Admin (1 min).** Sign in as `nshaikh@mitwpu.edu.in`. Subjects: CN-TH is out of 5,
   and a new subject can be added with any maximum. People: add a student, which shows a
   temporary password once; that student has to choose a new one at their first sign-in.
   Try a Gmail address: refused, only `@mitwpu.edu.in` accounts.
8. **SQL (2 min).** `psql "<ADMIN_DATABASE_URL>" -f sql/demo.sql`. Walk through the errors
   in steps 2-10, `pbl_app`'s privileges in 15, the joins in 16, and the index plans in 20.
   It all rolls back at the end. Expected output: [demo-output.txt](demo-output.txt).
9. **Cloud (30 s).** Supabase dashboard: Table Editor with the `pbl` schema. Backblaze
   dashboard: the bucket's file browser with the files uploaded in step 4.

## Likely questions

**Why one `users` table for students and faculty?**
Both are people who sign in, and both are referenced by projects: a team member through
`project_members.user_id`, the faculty member through `projects.faculty_id`. One table
gives one sign-in function and one place for emails. The differences are handled by
constraints: `students_have_a_prn` (students have a PRN, faculty don't),
`only_faculty_are_admins`, and two triggers that make sure a team member is a student
and a project's faculty member is faculty.

**Why isn't team size limited? Why can a student be in many projects?**
Because that is how PBL works here. Teams range from 2 to 5, and each student does
around 5 PBLs a semester, one per subject. The database enforces the rules that are
really rules (only students in a team, one leader) and doesn't invent others.

**How do marks work when subjects are marked out of different totals?**
Each subject has `max_marks` (33 for a lab, 5 for a theory mini project, anything the
admin sets). A project has one `marks` column. The `check_project` trigger looks up the
project's subject and refuses anything above its maximum. A CHECK handles the lower
bound (marks >= 0) because that needs nothing outside the row.

**Why a trigger for the maximum instead of a CHECK?**
A CHECK can only see the row being written. The maximum is in another table
(`subjects`), so only a trigger can compare against it.

**What is the difference between full-text search and vector search?**
Full-text search matches words, after stemming ("predicting" and "prediction" become
"predict"). Vector search matches meaning: the model turns text into 384 numbers and
texts about the same thing get nearby numbers, so "heart" and "cardiac" come out close.
We use both, and the Both mode merges the two rankings.

**What does `<=>` do?**
It's pgvector's cosine distance operator: 0 means the same direction, larger means more
different. We show similarity = 1 - distance because it's easier to read.

**What is an HNSW index? Why doesn't EXPLAIN use it?**
A graph of the vectors that lets Postgres jump to the nearest ones without comparing
against every row. It's approximate: it can very rarely miss the true nearest neighbour.
With 60 rows, reading the whole table is cheaper, so the planner skips the index; step 20
of the demo turns sequential scans off to show the plan that uses it.

**Why does Python make the embeddings and not the database?**
PostgreSQL can't run the model. Python turns text into numbers and sends them as a
float array; the database stores, indexes and searches them. The SQL functions cast the
array to `vector(384)`, which also rejects an array of the wrong length.

**Where are the reports and presentations stored?**
In a private Backblaze B2 bucket (10 GB free). The database has a `project_files` row
for each: which project, report or ppt, the original name, the size, who uploaded it, and
its path in the bucket. `UNIQUE (project_id, kind)` allows one report and one
presentation per project, and `reports_are_pdf` makes sure the report is a PDF. The path is random, so two files called `report.pdf` never clash and a
file name can't be used to write somewhere else. Deleting a project deletes its file
rows through `ON DELETE CASCADE`.

**Why subqueries in `project_cards` instead of joins?**
Joining members, tags, links and files together multiplies rows: 3 members x 4 tags x 2
links = 24 rows for one project, and any count over them would be wrong. Subqueries keep
one row per project.

**Where are the many-to-many relationships?**
Students-projects (`project_members`, which also stores the leader) and projects-tags
(`project_tags`). Links and files are one-to-many from projects.

**Is the schema in 3NF? BCNF?**
Yes to both. Every non-key column depends on the whole key and nothing else, and every
determinant is a candidate key (for example `users.email` is unique, so it is a
candidate key, not a hidden dependency). The normalisation walk-through is in
[design.md](design.md).

**Isn't `search_text` redundant?**
It's derived from title and abstract, but it is `GENERATED ALWAYS ... STORED`: Postgres
computes it, nobody can write a wrong value, and it gives the GIN index a column to index.

**What happens to the embedding if someone edits the abstract?**
The `clear_stale_embedding` trigger sets it to NULL, so a search can never use numbers
that describe the old text. `embed_projects.py` fills in every missing embedding.

**What can the app's database login do?**
`pbl_app` can read what the pages show but not `password_hash`. It can update only a
project's status, review note, marks, `marks_public` and embedding; it can't delete projects or users,
and it creates them only through `submit_project()` and `create_user()`. Step 15 of the
demo shows each refusal.

**What does `SECURITY DEFINER` mean, and why pin `search_path`?**
The function runs with its owner's rights, so the app can create a project only through
`submit_project()`, which checks everything. Pinning `search_path` stops a caller from
creating a look-alike table or operator in another schema and having the function use it.

**Then who stops a faculty member from marking someone else's project?**
The server. The UPDATE it runs is `... WHERE project_id = %s AND faculty_id = <me>`, so
another faculty member's project simply isn't found. The trade-off is in
[security.md](security.md): the database limits the app as a whole, the server decides
between users.

**How are passwords stored?**
As bcrypt hashes made by pgcrypto's `crypt(password, gen_salt('bf', 11))`. Each hash has
its own random salt, so two people with the same password get different hashes, and
cost 11 makes each check take about 80 ms. The app never sees a hash: it calls
`sign_in(login, password)`, which compares inside the database and returns the account
or "wrong".

**Why does a wrong password and an unknown PRN give the same message?**
So the sign-in form can't be used to find out which PRNs and emails exist. For an
unknown login the function still runs bcrypt once, so it takes as long to answer.

**If the admin switches an account off, is that person thrown out at once?**
Yes, on their next click. Every transaction first checks that the account is still
active and its password hasn't changed since this sign-in. If not, the server answers
401 and removes the cookie.

**Where do you use transactions?**
`submit_project()` inserts the project, members, tags, links and file rows as one unit: if the
third PRN doesn't exist, the project row disappears too. `setup_db.py` builds the whole
schema in one transaction. The SQL demo runs inside one and rolls back.

**How do you know when a project was approved?**
`decided_at`. The `check_project` trigger fills it in when the status changes from
`submitted` to `approved` or `rejected`, and refuses any other change of status, so a
decision is made once. The app can't write the column itself. The CHECK
`decided_once_reviewed` says `decided_at` is empty exactly while the project is
`submitted`, and `decided_after_submit` that it can't be before the project was created.

**Why can't the report be deleted, and why does deleting a project still work?**
A project without its report can't be reviewed or read. The `keep_report` trigger
refuses to delete a report row while its project exists. When the whole project is
deleted, the cascade removes the project first, the trigger finds no project, and lets
the report row go too.

**How do you keep people from outside MIT-WPU out?**
The CHECK `college_email` on `users`: `email LIKE '%@mitwpu.edu.in'`. Every account
needs it, whether it comes from `create_user()`, the People page or the sample data.

**Who sees the marks?**
The team, its faculty member and the coordinator. `marks_public` on the project lets the
team show them to everyone; only team members can switch it. The column is in the
database; who is shown what is decided by the server.

**Why two CHECK constraints for the academic year?**
`academic_year_format` checks the pattern; `academic_year_sequence` checks that 27 follows
26 using `::int` casts. Postgres tests CHECK constraints in alphabetical order of their
names, so the format check always runs first and "2026" fails with a clear message
instead of a cast error.

**What is Reciprocal Rank Fusion?**
A way to merge two ranked lists whose scores aren't comparable (keyword rank vs. cosine
similarity). Each project scores 1/(60 + its position) in each list, and the scores are
added. Projects near the top of both lists win.

**Why 0.70 for near duplicates, and why ask for a note instead of blocking?**
On our data, pairs that are the same idea scored 0.50-0.76, and different ideas on
related topics 0.42-0.57. The ranges overlap, so the score can't decide alone. Above
0.70 we ask the faculty member to write down what is different; they still decide.

**What if two teams submit the same title at the same moment?**
The unique index on `(subject_id, academic_year, lower(title))` lets one commit and makes
the other fail.

**How is it deployed?**
The database is on Supabase and the files are in a Backblaze B2 bucket. The app connects
through the Session pooler (works on IPv4) as `pbl_app.<project-ref>` with its own password; the scripts use
the owner login. No credentials are in the repository. People sign in to the app with
their own accounts, which live in the same database.
