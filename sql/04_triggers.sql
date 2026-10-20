-- 04_triggers.sql
-- Rules that a CHECK constraint can't express, because they need to look at other
-- rows or other tables. Triggers run on every write, whichever app or person sends it.
SET search_path = pbl, extensions;


-- 1. A submitted project is approved or rejected once, and decided_at records when.
--    A project's faculty_id has to point to a faculty member, and marks can only be
--    given to an approved project, up to its subject's max_marks.
CREATE FUNCTION trg_check_project() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pbl, pg_temp
AS $$
DECLARE
    v_role  varchar;
    v_max   numeric;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.status IS DISTINCT FROM OLD.status THEN
        IF NOT (OLD.status = 'submitted' AND NEW.status IN ('approved', 'rejected')) THEN
            RAISE EXCEPTION 'Status cannot change from % to %', OLD.status, NEW.status
                  USING ERRCODE = 'check_violation';
        END IF;
        NEW.decided_at := now();
    END IF;

    IF TG_OP = 'INSERT' OR NEW.faculty_id IS DISTINCT FROM OLD.faculty_id THEN
        SELECT u.role INTO v_role FROM users u WHERE u.user_id = NEW.faculty_id;
        IF v_role IS DISTINCT FROM 'faculty' THEN
            RAISE EXCEPTION 'The assigned faculty member has to be a faculty user'
                  USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    IF NEW.marks IS NOT NULL THEN
        IF NEW.status <> 'approved' THEN
            RAISE EXCEPTION 'Only approved projects can be marked (this one is %)', NEW.status
                  USING ERRCODE = 'check_violation';
        END IF;

        SELECT s.max_marks INTO v_max FROM subjects s WHERE s.subject_id = NEW.subject_id;
        IF NEW.marks > v_max THEN
            RAISE EXCEPTION 'Marks % are more than the maximum % for this subject', NEW.marks, v_max
                  USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER check_project
BEFORE INSERT OR UPDATE OF faculty_id, subject_id, status, marks ON projects
FOR EACH ROW EXECUTE FUNCTION trg_check_project();


-- 2. Only students can be team members.
CREATE FUNCTION trg_check_member() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pbl, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users u WHERE u.user_id = NEW.user_id AND u.role = 'student') THEN
        RAISE EXCEPTION 'Only students can be team members' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER check_member
BEFORE INSERT OR UPDATE OF user_id ON project_members
FOR EACH ROW EXECUTE FUNCTION trg_check_member();


-- 3. Approving a project that is a near duplicate of an existing one needs a
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


-- 4. An embedding describes the title and abstract it was made from. When either
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


-- 5. A project keeps its report. A new report replaces the old one (an UPDATE of
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
