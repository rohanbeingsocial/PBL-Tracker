-- 04_triggers.sql
-- Rules that a CHECK constraint can't express, because they need to look at other
-- rows or other tables. Triggers run on every write, whichever app or person sends it.
SET search_path = pbl, extensions;


-- 1. Status changes only move forward: proposed -> approved or rejected,
--    approved -> completed. A project's faculty_id has to point to a faculty member,
--    and marks can only be given to an approved or completed project, up to its
--    subject's max_marks.
CREATE FUNCTION trg_check_project() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pbl, pg_temp
AS $$
DECLARE
    v_role  varchar;
    v_max   numeric;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.status IS DISTINCT FROM OLD.status
       AND NOT (   (OLD.status = 'proposed' AND NEW.status IN ('approved', 'rejected'))
                OR (OLD.status = 'approved' AND NEW.status = 'completed')) THEN
        RAISE EXCEPTION 'Status cannot change from % to %', OLD.status, NEW.status
              USING ERRCODE = 'check_violation';
    END IF;

    IF TG_OP = 'INSERT' OR NEW.faculty_id IS DISTINCT FROM OLD.faculty_id THEN
        SELECT u.role INTO v_role FROM users u WHERE u.user_id = NEW.faculty_id;
        IF v_role IS DISTINCT FROM 'faculty' THEN
            RAISE EXCEPTION 'The assigned faculty member has to be a faculty user'
                  USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    IF NEW.marks IS NOT NULL THEN
        IF NEW.status NOT IN ('approved', 'completed') THEN
            RAISE EXCEPTION 'Only approved or completed projects can be marked (this one is %)', NEW.status
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


-- 3. Approving a proposal that is a near duplicate of an existing project needs a
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
            RAISE EXCEPTION 'This proposal is very close to "%" (similarity %)',
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
WHEN (OLD.status = 'proposed' AND NEW.status = 'approved')
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
