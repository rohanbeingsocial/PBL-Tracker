-- demo.sql: the viva demo, run with psql:
--
--     psql "<ADMIN_DATABASE_URL>" -f sql/demo.sql
--
-- Everything runs inside one transaction that is rolled back at the end, so the demo
-- can be run again and again. ON_ERROR_ROLLBACK lets the script carry on after the
-- statements that are meant to fail. Single statements can also be pasted into the
-- Supabase SQL editor; step 16 needs psql because it switches roles.

\set ON_ERROR_ROLLBACK on
\set ECHO queries
\pset footer off
BEGIN;
SET LOCAL search_path = pbl, extensions;

\echo '\n=== 1. The faculty member decides how many students a team has. ECE Lab Component Tracker''s'
\echo '        link takes any size, so its team of 2 can grow to 5.'
INSERT INTO project_members (project_id, user_id)
SELECT p.project_id, u.user_id
FROM projects p, users u
WHERE p.title = 'ECE Lab Component Tracker'
  AND u.prn IN ('1262241766', '1032240103', '1032240104');

SELECT title, members FROM project_cards WHERE title = 'ECE Lab Component Tracker';

\echo '\n        Now the link takes teams of 2 to 5: a sixth student is refused, and so is lowering the limit to 4.'
UPDATE submission_links SET min_members = 2, max_members = 5
WHERE submission_link_id = (SELECT submission_link_id FROM projects WHERE title = 'ECE Lab Component Tracker');

INSERT INTO project_members (project_id, user_id)
SELECT p.project_id, u.user_id
FROM projects p, users u
WHERE p.title = 'ECE Lab Component Tracker' AND u.prn = '1032240105';

UPDATE submission_links SET max_members = 4
WHERE submission_link_id = (SELECT submission_link_id FROM projects WHERE title = 'ECE Lab Component Tracker');

\echo '\n=== 2. Only students can be team members.'
INSERT INTO project_members (project_id, user_id)
SELECT p.project_id, u.user_id
FROM projects p, users u
WHERE p.title = 'ECE Lab Component Tracker' AND u.email = 'akulkarni@mitwpu.edu.in';

\echo '\n=== 3. Projects come in through submission links. A faculty member makes one per class and'
\echo '        purpose and sends it to the students; subject, faculty member and year come from the link.'
SELECT subject, class_name, purpose, academic_year, max_marks, is_open, waiting, approved, graded, students
FROM link_progress
WHERE faculty = 'Prof. S. Rao'
ORDER BY academic_year DESC, class_name
LIMIT 4;

\echo '\n=== 4. A link has to belong to a faculty user, and a student has one live project per link.'
UPDATE submission_links SET faculty_id = (SELECT user_id FROM users WHERE prn = '1262241783')
WHERE submission_link_id = (SELECT submission_link_id FROM projects
                            WHERE title = 'Automatic Classroom Attendance from CCTV Footage');

SELECT submit_project(
    (SELECT user_id FROM users WHERE prn = '1262241783'),
    'Second try at CCTV attendance',
    'Only here to show that a student has one live project per submission link.',
    (SELECT l.code FROM submission_links l JOIN projects p USING (submission_link_id)
     WHERE p.title = 'Automatic Classroom Attendance from CCTV Footage'),
    ARRAY['1032240115'], 'software', ARRAY['Python'], ARRAY[]::text[], ARRAY[]::text[], NULL,
    'report.pdf', 'demo/report.pdf', 1000);

\echo '\n=== 5. Each student gets their own marks, up to the link''s maximum (here 33).'
\echo '        The team score is the average, once every member has marks.'
UPDATE project_members SET marks = 33.5
WHERE project_id = (SELECT project_id FROM projects WHERE title = 'ECE Lab Component Tracker');

UPDATE project_members SET marks = 30
WHERE project_id = (SELECT project_id FROM projects WHERE title = 'ECE Lab Component Tracker')
  AND is_leader;

SELECT p.title, t.members, t.graded, t.team_score FROM team_marks t JOIN projects p USING (project_id)
WHERE p.title = 'ECE Lab Component Tracker';

UPDATE project_members SET marks = 28
WHERE project_id = (SELECT project_id FROM projects WHERE title = 'ECE Lab Component Tracker')
  AND NOT is_leader;

SELECT p.title, t.members, t.graded, t.team_score, t.max_marks, t.percent
FROM team_marks t JOIN projects p USING (project_id)
WHERE p.title = 'ECE Lab Component Tracker';

\echo '\n=== 6. A new link starts with its subject''s usual total (CN-TH is out of 5), and gets a random code.'
\echo '        Only approved projects can be marked.'
INSERT INTO submission_links (faculty_id, subject_id, academic_year, class_name, purpose)
SELECT u.user_id, s.subject_id, current_academic_year(), 'TY ECE Div A', 'Mini project'
FROM users u, subjects s
WHERE u.email = 'akulkarni@mitwpu.edu.in' AND s.code = 'CN-TH'
RETURNING class_name, purpose, max_marks, code;

UPDATE project_members SET marks = 10
WHERE project_id = (SELECT project_id FROM projects WHERE title = 'Mess Meal Pre-Booking and Feedback');

\echo '\n=== 7. Only MIT-WPU accounts: every email has to end in @mitwpu.edu.in.'
INSERT INTO users (name, email, role, password_hash)
VALUES ('Outsider', 'someone@gmail.com', 'faculty', '$2a$11$xxxxxxxxxxxxxxxxxxxxxx');

\echo '\n=== 8. CHECK constraints on a link''s academic year: format first, then the two years must follow each other.'
INSERT INTO submission_links (faculty_id, subject_id, academic_year, class_name, purpose)
SELECT user_id, 1, '2026', 'TY ECE Div A', 'Year check'
FROM users WHERE email = 'akulkarni@mitwpu.edu.in';

INSERT INTO submission_links (faculty_id, subject_id, academic_year, class_name, purpose)
SELECT user_id, 1, '2026-28', 'TY ECE Div A', 'Year check'
FROM users WHERE email = 'akulkarni@mitwpu.edu.in';

\echo '\n=== 9. A submitted project is approved or rejected once, and the trigger records when.'
UPDATE projects SET status = 'submitted' WHERE title = 'College Library Management';

UPDATE projects SET status = 'rejected', review_note = 'Same scope as the 2025-26 mess project.'
WHERE title = 'Mess Meal Pre-Booking and Feedback'
RETURNING title, status, decided_at;

\echo '\n=== 10. Reports: one per project, always a PDF. It can be replaced but not removed.'
INSERT INTO project_files (project_id, kind, file_name, storage_path, size_bytes, uploaded_by)
SELECT m.project_id, 'report', 'second.pdf', 'demo/second.pdf', 1000, m.user_id
FROM project_members m JOIN projects p USING (project_id)
WHERE p.title = 'Smart Water Tank Level Controller' AND m.is_leader;

UPDATE project_files SET storage_path = 'demo/report.docx'
WHERE kind = 'report' AND project_id = (SELECT project_id FROM projects WHERE title = 'Smart Water Tank Level Controller');

DELETE FROM project_files
WHERE kind = 'report' AND project_id = (SELECT project_id FROM projects WHERE title = 'Smart Water Tank Level Controller');

\echo '\n=== 11. Links must be http or https, and the same link can only be added once.'
INSERT INTO project_links (project_id, label, url)
SELECT project_id, 'GitHub', 'github.com/example/tank' FROM projects WHERE title = 'Smart Water Tank Level Controller';

INSERT INTO project_links (project_id, label, url)
SELECT project_id, 'GitHub', 'https://github.com/example/tank' FROM projects WHERE title = 'Smart Water Tank Level Controller'
RETURNING link_id, label, url;

\echo '\n=== 12. Keyword search (full-text search on a generated tsvector column, GIN index).'
SELECT title, rank, snippet FROM keyword_search('heart disease');

SELECT title FROM keyword_search('heart attack risk');

\echo '\n=== 13. Meaning search in SQL: each waiting submission and its closest existing project (LATERAL + HNSW).'
SELECT title, closest_title, closest_year, round(similarity::numeric, 2) AS similarity, band
FROM review_queue
ORDER BY similarity DESC NULLS LAST;

\echo '\n=== 14. Ideas that keep coming back (self-join on embeddings).'
SELECT first_title, first_year, second_title, second_year, round(similarity::numeric, 2) AS similarity, band
FROM repeated_ideas
ORDER BY similarity DESC
LIMIT 8;

\echo '\n=== 15. Approving a near duplicate needs a review note.'
UPDATE projects SET status = 'approved'
WHERE title = 'Automatic Classroom Attendance from CCTV Footage';

UPDATE projects
SET status = 'approved',
    review_note = 'Uses the CCTV cameras already in classrooms instead of a separate webcam. Builds on the 2025-26 project.'
WHERE title = 'Automatic Classroom Attendance from CCTV Footage'
RETURNING title, status;

\echo '\n=== 16. Privileges. The web app logs in as pbl_app: no password hashes, no deletes, only the'
\echo '        review and marks_public columns of a project and each student''s marks can change,'
\echo '        and a link''s code always comes from the database.'
SET LOCAL ROLE pbl_app;

SELECT name, role FROM users WHERE email = 'srao@mitwpu.edu.in';

SELECT name, password_hash FROM users LIMIT 1;

DELETE FROM projects WHERE title = 'Placement Drive Tracker';

UPDATE projects SET title = 'Renamed' WHERE title = 'Placement Drive Tracker';

UPDATE submission_links SET code = 'easy123'
WHERE submission_link_id = (SELECT submission_link_id FROM projects WHERE title = 'Placement Drive Tracker');

UPDATE projects SET status = 'rejected', review_note = 'Overlaps the 2024-25 Campus Placement Portal.'
WHERE title = 'Placement Drive Tracker'
RETURNING title, status;

RESET ROLE;

\echo '\n=== 17. Joins through two link tables: hardware projects that used ESP32, with their team.'
SELECT p.title, l.academic_year, s.code AS subject, string_agg(u.name, ', ' ORDER BY u.name) AS team
FROM projects p
JOIN submission_links l ON l.submission_link_id = p.submission_link_id
JOIN subjects s         ON s.subject_id = l.subject_id
JOIN project_tags pt    ON pt.project_id = p.project_id
JOIN tags t             ON t.tag_id = pt.tag_id
JOIN project_members m  ON m.project_id = p.project_id
JOIN users u            ON u.user_id = m.user_id
WHERE t.name = 'ESP32' AND p.project_type = 'hardware'
GROUP BY p.project_id, l.academic_year, s.code
ORDER BY l.academic_year, p.title;

\echo '\n=== 18. A student can be in several projects in one year (one per submission link).'
SELECT u.name, l.academic_year, count(*) AS projects
FROM project_members m
JOIN users u            ON u.user_id = m.user_id
JOIN projects p         ON p.project_id = m.project_id
JOIN submission_links l ON l.submission_link_id = p.submission_link_id
GROUP BY u.user_id, l.academic_year
ORDER BY projects DESC, u.name
LIMIT 5;

\echo '\n=== 19. Views and aggregates.'
SELECT project_id, title, subject, class_name, faculty, project_type, members, tags
FROM project_cards
ORDER BY project_id
LIMIT 5;

SELECT tag, academic_year, project_count
FROM tag_trends
WHERE tag IN ('ESP32', 'Flask')
ORDER BY tag, academic_year;

SELECT c.subject, count(t.team_score) AS graded_teams, round(avg(t.team_score), 1) AS average_score,
       round(avg(t.percent), 0) AS average_percent
FROM project_cards c
JOIN team_marks t USING (project_id)
GROUP BY c.subject
ORDER BY c.subject;

\echo '\n=== 20. Deleting a project takes its members, tags, links and files with it (ON DELETE CASCADE).'
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

\echo '\n=== 21. The indexes exist and get used. With only 60 rows a full scan is cheaper, so'
\echo '        sequential scans are switched off here just to show the plans.'
SET LOCAL enable_seqscan = off;

EXPLAIN (COSTS OFF)
SELECT title FROM projects WHERE search_text @@ websearch_to_tsquery('english', 'heart disease');

EXPLAIN (COSTS OFF)
SELECT project_id FROM projects
ORDER BY embedding <=> (SELECT embedding FROM projects WHERE embedding IS NOT NULL LIMIT 1)
LIMIT 5;

EXPLAIN (COSTS OFF)
SELECT project_id, title FROM projects WHERE submission_link_id = 1;

ROLLBACK;
\echo '\nDone. Everything above was rolled back.'
