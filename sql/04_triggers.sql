-- 04_triggers.sql
-- Rules that a CHECK constraint can't express, because they need to look at other
-- rows or other tables. Triggers run on every write, whichever app or person sends it.
SET search_path = pbl, extensions;


-- 1. A submission link belongs to a faculty member, and starts with its subject's
--    usual total when no max_marks is given. Lowering max_marks below marks that
--    were already given is refused, and so are team sizes that a team already in
--    the link wouldn't fit (a rejected team doesn't count).
CREATE FUNCTION trg_check_submission_link() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pbl, pg_temp
AS $$
DECLARE
    v_highest   numeric;
    v_smallest  int;
    v_largest   int;
BEGIN
    IF TG_OP = 'INSERT' OR NEW.faculty_id IS DISTINCT FROM OLD.faculty_id THEN
        IF NOT EXISTS (SELECT 1 FROM users u WHERE u.user_id = NEW.faculty_id AND u.role = 'faculty') THEN
            RAISE EXCEPTION 'A submission link has to belong to a faculty user'
                  USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    IF NEW.max_marks IS NULL THEN
        SELECT s.max_marks INTO NEW.max_marks FROM subjects s WHERE s.subject_id = NEW.subject_id;
    END IF;

    IF TG_OP = 'UPDATE' AND NEW.max_marks < OLD.max_marks THEN
        SELECT max(pm.marks) INTO v_highest
          FROM project_members pm
          JOIN projects p ON p.project_id = pm.project_id
         WHERE p.submission_link_id = NEW.submission_link_id;
        IF v_highest > NEW.max_marks THEN
            RAISE EXCEPTION 'A student in this link already has % marks, so the maximum can''t go below that', v_highest
                  USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    IF TG_OP = 'UPDATE' AND (NEW.min_members, NEW.max_members) IS DISTINCT FROM (OLD.min_members, OLD.max_members) THEN
        SELECT min(teams.size), max(teams.size) INTO v_smallest, v_largest
          FROM (SELECT count(*) AS size
                  FROM project_members pm
                  JOIN projects p ON p.project_id = pm.project_id
                 WHERE p.submission_link_id = NEW.submission_link_id AND p.status <> 'rejected'
                 GROUP BY pm.project_id) AS teams;
        IF v_largest > NEW.max_members THEN
            RAISE EXCEPTION 'A team in this link already has % students, so the most in a team can''t go below that', v_largest
                  USING ERRCODE = 'check_violation';
        END IF;
        IF v_smallest < NEW.min_members THEN
            RAISE EXCEPTION 'A team in this link has only % students, so the fewest in a team can''t go above that', v_smallest
                  USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER check_submission_link
BEFORE INSERT OR UPDATE OF faculty_id, subject_id, max_marks, min_members, max_members ON submission_links
FOR EACH ROW EXECUTE FUNCTION trg_check_submission_link();


-- 2. A submitted project is approved or rejected once, and decided_at records when.
CREATE FUNCTION trg_check_project() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pbl, pg_temp
AS $$
BEGIN
    IF NOT (OLD.status = 'submitted' AND NEW.status IN ('approved', 'rejected')) THEN
        RAISE EXCEPTION 'Status cannot change from % to %', OLD.status, NEW.status
              USING ERRCODE = 'check_violation';
    END IF;
    NEW.decided_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER check_project
BEFORE UPDATE OF status ON projects
FOR EACH ROW
WHEN (NEW.status IS DISTINCT FROM OLD.status)
EXECUTE FUNCTION trg_check_project();


-- 3. Team members are students, each in at most one live project per submission
--    link (a rejected project doesn't count, so the team can try again). A team
--    grows only up to the link's max_members; submit_project() checks min_members,
--    because a team is added one student at a time. Marks go to each student only
--    once the project is approved, up to the link's max_marks.
CREATE FUNCTION trg_check_member() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pbl, pg_temp
AS $$
DECLARE
    v_project  projects;
    v_link     submission_links;
    v_prn      varchar;
    v_others   int;
BEGIN
    SELECT * INTO v_project FROM projects p WHERE p.project_id = NEW.project_id;
    SELECT * INTO v_link FROM submission_links l WHERE l.submission_link_id = v_project.submission_link_id;

    IF TG_OP = 'INSERT' OR NEW.user_id IS DISTINCT FROM OLD.user_id THEN
        SELECT u.prn INTO v_prn FROM users u WHERE u.user_id = NEW.user_id AND u.role = 'student';
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Only students can be team members' USING ERRCODE = 'check_violation';
        END IF;

        -- Two submissions with the same student at the same moment would both pass
        -- the check below, so they take turns: the lock is held until COMMIT.
        PERFORM pg_advisory_xact_lock(v_project.submission_link_id, NEW.user_id);
        IF v_project.status <> 'rejected' AND EXISTS (SELECT 1
                     FROM project_members pm
                     JOIN projects p ON p.project_id = pm.project_id
                    WHERE pm.user_id = NEW.user_id
                      AND pm.project_id <> NEW.project_id
                      AND p.submission_link_id = v_project.submission_link_id
                      AND p.status <> 'rejected') THEN
            RAISE EXCEPTION 'PRN % already has a project in this submission link', v_prn
                  USING ERRCODE = 'unique_violation';
        END IF;

        -- Students joining the same team take turns too (a one-number lock, so it
        -- can't clash with the two-number one above).
        IF v_link.max_members IS NOT NULL THEN
            PERFORM pg_advisory_xact_lock(NEW.project_id);
            SELECT count(*) INTO v_others
              FROM project_members pm
             WHERE pm.project_id = NEW.project_id
               AND pm.user_id <> NEW.user_id
               AND pm.user_id IS DISTINCT FROM OLD.user_id;      -- a student being swapped out doesn't count
            IF v_others >= v_link.max_members THEN
                RAISE EXCEPTION 'This submission link takes teams of at most % students', v_link.max_members
                      USING ERRCODE = 'check_violation';
            END IF;
        END IF;
    END IF;

    IF NEW.marks IS NOT NULL THEN
        IF v_project.status <> 'approved' THEN
            RAISE EXCEPTION 'Only approved projects can be marked (this one is %)', v_project.status
                  USING ERRCODE = 'check_violation';
        END IF;

        IF NEW.marks > v_link.max_marks THEN
            RAISE EXCEPTION 'Marks % are more than the maximum % for this submission', NEW.marks, v_link.max_marks
                  USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER check_member
BEFORE INSERT OR UPDATE OF user_id, marks ON project_members
FOR EACH ROW EXECUTE FUNCTION trg_check_member();


-- 4. Approving a project that is a near duplicate of an existing one needs a
--    review note that says what is different about it.
CREATE FUNCTION trg_check_near_duplicate() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pbl, extensions, pg_temp
AS $$
DECLARE
    v_title       varchar;
    v_similarity  double precision;
BEGIN
    IF NEW.embedding IS NOT NULL AND coalesce(btrim(NEW.review_note), '') = '' THEN
        SELECT p.title, 1 - (p.embedding <=> NEW.embedding)
          INTO v_title, v_similarity
          FROM projects p
         WHERE p.project_id <> NEW.project_id
           AND p.status <> 'rejected'
           AND p.embedding IS NOT NULL
         ORDER BY p.embedding <=> NEW.embedding
         LIMIT 1;

        IF similarity_band(v_similarity) = 'near duplicate' THEN
            RAISE EXCEPTION 'This project is very close to "%" (similarity %)',
                            v_title, round(v_similarity::numeric, 2)
                  USING ERRCODE = 'check_violation',
                        HINT = 'Approve it with a review note that says how this project is different.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER check_near_duplicate
BEFORE UPDATE OF status ON projects
FOR EACH ROW
WHEN (OLD.status = 'submitted' AND NEW.status = 'approved')
EXECUTE FUNCTION trg_check_near_duplicate();


-- 5. An embedding describes the title and abstract it was made from. When either
--    changes, the old embedding is cleared and embed_projects.py makes a fresh one.
CREATE FUNCTION trg_clear_stale_embedding() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pbl, pg_temp
AS $$
BEGIN
    NEW.embedding := NULL;
    RETURN NEW;
END;
$$;

CREATE TRIGGER clear_stale_embedding
BEFORE UPDATE OF title, abstract ON projects
FOR EACH ROW
WHEN (OLD.title IS DISTINCT FROM NEW.title OR OLD.abstract IS DISTINCT FROM NEW.abstract)
EXECUTE FUNCTION trg_clear_stale_embedding();


-- 6. A project keeps its report. A new report replaces the old one (an UPDATE of
--    the same row), but the row itself can only go when the whole project is deleted.
CREATE FUNCTION trg_keep_report() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pbl, pg_temp
AS $$
BEGIN
    -- During ON DELETE CASCADE the project row is already gone.
    IF EXISTS (SELECT 1 FROM projects p WHERE p.project_id = OLD.project_id) THEN
        RAISE EXCEPTION 'A project''s report can be replaced but not removed'
              USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
END;
$$;

CREATE TRIGGER keep_report
BEFORE DELETE ON project_files
FOR EACH ROW
WHEN (OLD.kind = 'report')
EXECUTE FUNCTION trg_keep_report();
