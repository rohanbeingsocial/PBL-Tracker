-- demo.sql: the viva demo, run with psql:
--
--     psql "<ADMIN_DATABASE_URL>" -f sql/demo.sql
--
-- Everything runs inside one transaction that is rolled back at the end, so the demo
-- can be run again and again. ON_ERROR_ROLLBACK lets the script carry on after the
-- statements that are meant to fail. Single statements can also be pasted into the
-- Supabase SQL editor; step 15 needs psql because it switches roles.

\set ON_ERROR_ROLLBACK on
\set ECHO queries
\pset footer off
BEGIN;
SET LOCAL search_path = pbl, extensions;

\echo '\n=== 1. Teams have no fixed size. ECE Lab Component Tracker has 2 members; add 3 more.'
INSERT INTO project_members (project_id, user_id)
SELECT p.project_id, u.user_id
FROM projects p, users u
WHERE p.title = 'ECE Lab Component Tracker'
  AND u.prn IN ('1032240102', '1032240103', '1032240104');

SELECT title, members FROM project_cards WHERE title = 'ECE Lab Component Tracker';

\echo '\n=== 2. Only students can be team members.'
INSERT INTO project_members (project_id, user_id)
SELECT p.project_id, u.user_id
FROM projects p, users u
WHERE p.title = 'ECE Lab Component Tracker' AND u.email = 'akulkarni@mitwpu.edu.in';

\echo '\n=== 3. The assigned faculty member has to be a faculty user.'
UPDATE projects SET faculty_id = (SELECT user_id FROM users WHERE prn = '1032240101')
WHERE title = 'ECE Lab Component Tracker';

\echo '\n=== 4. Marks: each subject sets its own maximum. DBMS-PBL is out of 33, CN-TH out of 5.'
UPDATE projects SET marks = 33.5 WHERE title = 'ECE Lab Component Tracker';

UPDATE projects SET marks = 30 WHERE title = 'ECE Lab Component Tracker'
RETURNING title, marks;

SELECT code, name, max_marks FROM subjects ORDER BY subject_id;

\echo '\n=== 5. Only approved projects can be marked.'
UPDATE projects SET marks = 10 WHERE title = 'Mess Meal Pre-Booking and Feedback';

\echo '\n=== 6. Only MIT-WPU accounts: every email has to end in @mitwpu.edu.in.'
INSERT INTO users (name, email, role, password_hash)
VALUES ('Outsider', 'someone@gmail.com', 'faculty', '$2a$11$xxxxxxxxxxxxxxxxxxxxxx');

\echo '\n=== 7. CHECK constraints on the academic year: format first, then the two years must follow each other.'
INSERT INTO projects (title, abstract, subject_id, faculty_id, academic_year, project_type)
SELECT 'Year check', 'Only here to show the academic year constraints.', 1, user_id, '2026', 'software'
FROM users WHERE email = 'akulkarni@mitwpu.edu.in';

INSERT INTO projects (title, abstract, subject_id, faculty_id, academic_year, project_type)
SELECT 'Year check', 'Only here to show the academic year constraints.', 1, user_id, '2026-28', 'software'
FROM users WHERE email = 'akulkarni@mitwpu.edu.in';

\echo '\n=== 8. A submitted project is approved or rejected once, and the trigger records when.'
UPDATE projects SET status = 'submitted' WHERE title = 'College Library Management';

UPDATE projects SET status = 'rejected', review_note = 'Same scope as the 2025-26 mess project.'
WHERE title = 'Mess Meal Pre-Booking and Feedback'
RETURNING title, status, decided_at;

\echo '\n=== 9. Reports: one per project, always a PDF. It can be replaced but not removed.'
INSERT INTO project_files (project_id, kind, file_name, storage_path, size_bytes, uploaded_by)
SELECT project_id, 'report', 'second.pdf', 'demo/second.pdf', 1000, faculty_id
FROM projects WHERE title = 'Smart Water Tank Level Controller';

UPDATE project_files SET storage_path = 'demo/report.docx'
WHERE kind = 'report' AND project_id = (SELECT project_id FROM projects WHERE title = 'Smart Water Tank Level Controller');

DELETE FROM project_files
WHERE kind = 'report' AND project_id = (SELECT project_id FROM projects WHERE title = 'Smart Water Tank Level Controller');

\echo '\n=== 10. Links must be http or https, and the same link can only be added once.'
INSERT INTO project_links (project_id, label, url)
SELECT project_id, 'GitHub', 'github.com/example/tank' FROM projects WHERE title = 'Smart Water Tank Level Controller';

INSERT INTO project_links (project_id, label, url)
SELECT project_id, 'GitHub', 'https://github.com/example/tank' FROM projects WHERE title = 'Smart Water Tank Level Controller'
RETURNING link_id, label, url;

\echo '\n=== 11. Keyword search (full-text search on a generated tsvector column, GIN index).'
SELECT title, rank, snippet FROM keyword_search('heart disease');

SELECT title FROM keyword_search('heart attack risk');

\echo '\n=== 12. Meaning search in SQL: each waiting submission and its closest existing project (LATERAL + HNSW).'
SELECT title, closest_title, closest_year, round(similarity::numeric, 2) AS similarity, band
FROM review_queue
ORDER BY similarity DESC NULLS LAST;

\echo '\n=== 13. Ideas that keep coming back (self-join on embeddings).'
SELECT first_title, first_year, second_title, second_year, round(similarity::numeric, 2) AS similarity, band
FROM repeated_ideas
ORDER BY similarity DESC
LIMIT 8;

\echo '\n=== 14. Approving a near duplicate needs a review note.'
UPDATE projects SET status = 'approved'
WHERE title = 'Automatic Classroom Attendance from CCTV Footage';

UPDATE projects
SET status = 'approved',
    review_note = 'Uses the CCTV cameras already in classrooms instead of a separate webcam. Builds on the 2025-26 project.'
WHERE title = 'Automatic Classroom Attendance from CCTV Footage'
RETURNING title, status;

\echo '\n=== 15. Privileges. The web app logs in as pbl_app: no password hashes, no deletes,'
\echo '        and only the review, marks and marks_public columns of a project can change.'
SET LOCAL ROLE pbl_app;

SELECT name, role FROM users WHERE email = 'srao@mitwpu.edu.in';

SELECT name, password_hash FROM users LIMIT 1;

DELETE FROM projects WHERE title = 'Placement Drive Tracker';

UPDATE projects SET title = 'Renamed' WHERE title = 'Placement Drive Tracker';

UPDATE projects SET status = 'rejected', review_note = 'Overlaps the 2024-25 Campus Placement Portal.'
WHERE title = 'Placement Drive Tracker'
RETURNING title, status;

RESET ROLE;

\echo '\n=== 16. Joins through two link tables: hardware projects that used ESP32, with their team.'
SELECT p.title, p.academic_year, s.code AS subject, string_agg(u.name, ', ' ORDER BY u.name) AS team
FROM projects p
JOIN subjects s        ON s.subject_id = p.subject_id
JOIN project_tags pt   ON pt.project_id = p.project_id
JOIN tags t            ON t.tag_id = pt.tag_id
JOIN project_members m ON m.project_id = p.project_id
JOIN users u           ON u.user_id = m.user_id
WHERE t.name = 'ESP32' AND p.project_type = 'hardware'
GROUP BY p.project_id, s.code
ORDER BY p.academic_year, p.title;

\echo '\n=== 17. A student can be in several projects in one year (one per subject this semester).'
SELECT u.name, p.academic_year, count(*) AS projects
FROM project_members m
JOIN users u    ON u.user_id = m.user_id
JOIN projects p ON p.project_id = m.project_id
GROUP BY u.user_id, p.academic_year
ORDER BY projects DESC, u.name
LIMIT 5;

\echo '\n=== 18. Views and aggregates.'
SELECT project_id, title, subject, faculty, project_type, members, tags
FROM project_cards
ORDER BY project_id
LIMIT 5;

SELECT tag, academic_year, project_count
FROM tag_trends
WHERE tag IN ('ESP32', 'Flask')
ORDER BY tag, academic_year;

SELECT s.code, count(p.marks) AS marked, round(avg(p.marks), 1) AS average, s.max_marks AS out_of,
       round(100 * avg(p.marks / s.max_marks), 0) AS average_percent
FROM subjects s
JOIN projects p ON p.subject_id = s.subject_id
GROUP BY s.subject_id
ORDER BY s.code;

\echo '\n=== 19. Deleting a project takes its members, tags, links and files with it (ON DELETE CASCADE).'
SELECT project_id AS tank FROM projects WHERE title = 'Smart Water Tank Level Controller' \gset

SELECT (SELECT count(*) FROM project_members WHERE project_id = :tank) AS members,
       (SELECT count(*) FROM project_tags    WHERE project_id = :tank) AS tags,
       (SELECT count(*) FROM project_links   WHERE project_id = :tank) AS links,
       (SELECT count(*) FROM project_files   WHERE project_id = :tank) AS files;

DELETE FROM projects WHERE project_id = :tank;

SELECT (SELECT count(*) FROM project_members WHERE project_id = :tank) AS members,
       (SELECT count(*) FROM project_tags    WHERE project_id = :tank) AS tags,
       (SELECT count(*) FROM project_links   WHERE project_id = :tank) AS links,
       (SELECT count(*) FROM project_files   WHERE project_id = :tank) AS files;

\echo '\n=== 20. The indexes exist and get used. With only 60 rows a full scan is cheaper, so'
\echo '        sequential scans are switched off here just to show the plans.'
SET LOCAL enable_seqscan = off;

EXPLAIN (COSTS OFF)
SELECT title FROM projects WHERE search_text @@ websearch_to_tsquery('english', 'heart disease');

EXPLAIN (COSTS OFF)
SELECT project_id FROM projects
ORDER BY embedding <=> (SELECT embedding FROM projects WHERE embedding IS NOT NULL LIMIT 1)
LIMIT 5;

ROLLBACK;
\echo '\nDone. Everything above was rolled back.'
