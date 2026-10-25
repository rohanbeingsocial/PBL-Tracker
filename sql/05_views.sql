-- 05_views.sql
-- Views are what the app reads for lists and pages.
SET search_path = pbl, extensions;


-- One row per project with everything a project card shows. Members, tags, links and
-- files come from subqueries rather than joins: joining all four would multiply rows
-- (3 members x 4 tags x 2 links = 24 rows for one project). Marks are left out: only
-- the team and its faculty member see them, unless the team has made its score
-- public (marks_public), so the app reads team_marks when it may show them.
CREATE VIEW project_cards AS
SELECT p.project_id,
       p.title,
       p.abstract,
       l.academic_year,
       s.code  AS subject,
       s.name  AS subject_name,
       l.faculty_id,
       f.name  AS faculty,
       p.submission_link_id,
       l.class_name,
       l.purpose,
       p.project_type,
       p.status,
       p.review_note,
       p.decided_at,
       p.marks_public,
       (SELECT string_agg(u.name, ', ' ORDER BY pm.is_leader DESC, u.name)
          FROM project_members pm
          JOIN users u ON u.user_id = pm.user_id
         WHERE pm.project_id = p.project_id) AS members,
       ARRAY(SELECT pm.user_id
               FROM project_members pm
              WHERE pm.project_id = p.project_id) AS member_ids,
       ARRAY(SELECT t.name::text
               FROM project_tags pt
               JOIN tags t ON t.tag_id = pt.tag_id
              WHERE pt.project_id = p.project_id
              ORDER BY t.name) AS tags,
       (SELECT coalesce(jsonb_agg(jsonb_build_object('link_id', l.link_id, 'label', l.label, 'url', l.url)
                                  ORDER BY l.link_id), '[]')
          FROM project_links l
         WHERE l.project_id = p.project_id) AS links,
       (SELECT coalesce(jsonb_agg(jsonb_build_object('file_id', pf.file_id, 'kind', pf.kind,
                                                     'file_name', pf.file_name, 'size_bytes', pf.size_bytes,
                                                     'uploaded_at', pf.uploaded_at)
                                  ORDER BY pf.uploaded_at DESC), '[]')
          FROM project_files pf
         WHERE pf.project_id = p.project_id) AS files,
       p.created_at
FROM projects p
JOIN submission_links l ON l.submission_link_id = p.submission_link_id
JOIN subjects s         ON s.subject_id = l.subject_id
JOIN users f            ON f.user_id = l.faculty_id;


-- Each student's marks are in project_members; the team score is their average,
-- shown only once every member has marks, so a half-marked team doesn't look
-- finished. percent puts links with different totals on one scale.
CREATE VIEW team_marks AS
SELECT p.project_id,
       l.max_marks,
       count(pm.user_id)        AS members,
       count(pm.marks)          AS graded,
       CASE WHEN count(pm.marks) = count(pm.user_id) THEN round(avg(pm.marks), 1) END AS team_score,
       CASE WHEN count(pm.marks) = count(pm.user_id) THEN round(100 * avg(pm.marks) / l.max_marks, 1) END AS percent
FROM projects p
JOIN submission_links l      ON l.submission_link_id = p.submission_link_id
LEFT JOIN project_members pm ON pm.project_id = p.project_id
GROUP BY p.project_id, l.max_marks;


-- One row per submission link with how far its class has got: what the faculty
-- member sees on the Submission links page.
CREATE VIEW link_progress AS
SELECT l.submission_link_id,
       l.code,
       l.faculty_id,
       f.name AS faculty,
       s.code AS subject,
       s.name AS subject_name,
       l.academic_year,
       l.class_name,
       l.purpose,
       l.max_marks,
       l.min_members,
       l.max_members,
       l.is_open,
       l.created_at,
       count(p.project_id) FILTER (WHERE p.status = 'submitted') AS waiting,
       count(p.project_id) FILTER (WHERE p.status = 'approved')  AS approved,
       count(p.project_id) FILTER (WHERE p.status = 'rejected')  AS rejected,
       count(t.team_score)                                       AS graded,
       coalesce(sum(t.members) FILTER (WHERE p.status <> 'rejected'), 0)::int AS students
FROM submission_links l
JOIN subjects s      ON s.subject_id = l.subject_id
JOIN users f         ON f.user_id = l.faculty_id
LEFT JOIN projects p ON p.submission_link_id = l.submission_link_id
LEFT JOIN team_marks t ON t.project_id = p.project_id
GROUP BY l.submission_link_id, f.name, s.code, s.name;


-- Submissions waiting for a decision, each with its closest existing project.
-- LATERAL runs the nearest-neighbour search once per submission, using that
-- submission's own embedding.
CREATE VIEW review_queue AS
SELECT p.project_id,
       p.title,
       l.academic_year,
       s.code AS subject,
       l.faculty_id,
       p.created_at,
       nn.project_id    AS closest_id,
       nn.title         AS closest_title,
       nn.academic_year AS closest_year,
       nn.status        AS closest_status,
       nn.similarity,
       similarity_band(nn.similarity) AS band
FROM projects p
JOIN submission_links l ON l.submission_link_id = p.submission_link_id
JOIN subjects s         ON s.subject_id = l.subject_id
LEFT JOIN LATERAL (
    SELECT o.project_id, o.title, ol.academic_year, o.status,
           1 - (o.embedding <=> p.embedding) AS similarity
    FROM projects o
    JOIN submission_links ol ON ol.submission_link_id = o.submission_link_id
    WHERE p.embedding IS NOT NULL
      AND o.embedding IS NOT NULL
      AND o.project_id <> p.project_id
      AND o.status <> 'rejected'
    ORDER BY o.embedding <=> p.embedding
    LIMIT 1
) nn ON true
WHERE p.status = 'submitted';


-- Pairs of projects that are about the same thing. A plain self-join compares every
-- pair once (a.project_id < b.project_id); fine for a few thousand projects.
CREATE VIEW repeated_ideas AS
SELECT a.project_id     AS first_id,
       a.title          AS first_title,
       la.academic_year AS first_year,
       b.project_id     AS second_id,
       b.title          AS second_title,
       lb.academic_year AS second_year,
       1 - (a.embedding <=> b.embedding) AS similarity,
       similarity_band(1 - (a.embedding <=> b.embedding)) AS band
FROM projects a
JOIN projects b          ON a.project_id < b.project_id
JOIN submission_links la ON la.submission_link_id = a.submission_link_id
JOIN submission_links lb ON lb.submission_link_id = b.submission_link_id
WHERE a.status <> 'rejected'
  AND b.status <> 'rejected'
  AND similarity_band(1 - (a.embedding <=> b.embedding)) IN ('near duplicate', 'similar');


-- How many projects used each tag per year. Shows which stacks get picked again and again.
CREATE VIEW tag_trends AS
SELECT t.name AS tag,
       l.academic_year,
       count(*) AS project_count
FROM project_tags pt
JOIN tags t             ON t.tag_id = pt.tag_id
JOIN projects p         ON p.project_id = pt.project_id
JOIN submission_links l ON l.submission_link_id = p.submission_link_id
WHERE p.status <> 'rejected'
GROUP BY t.name, l.academic_year;
