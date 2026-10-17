-- 06_security.sql
-- What the web app's database login may do.
--
-- The app connects as pbl_app, never as the owner. pbl_app can read what the pages
-- show and change only the columns the app needs to change. It can't read password
-- hashes, can't delete projects or users, and creates projects and accounts only
-- through the functions in 03_functions.sql. Which signed-in person may do what
-- (a student, the project's faculty member, an admin) is checked by the app.
SET search_path = pbl, extensions;


-- Roles are shared by the whole database server, so create it only if missing.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pbl_app') THEN
        CREATE ROLE pbl_app LOGIN;   -- password is set by scripts/setup_db.py
    END IF;
END $$;

ALTER ROLE pbl_app CONNECTION LIMIT 20;
ALTER ROLE pbl_app SET statement_timeout = '5s';
ALTER ROLE pbl_app SET idle_in_transaction_session_timeout = '30s';


-- Schema and function basics. New functions are executable by everyone (PUBLIC)
-- unless that is taken away, so take it away now and for functions added later.
REVOKE ALL ON SCHEMA pbl FROM PUBLIC;
GRANT USAGE ON SCHEMA pbl TO pbl_app;
GRANT USAGE ON SCHEMA extensions TO pbl_app;      -- the vector type and its operators
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA pbl FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA pbl REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

DO $$
BEGIN
    IF NOT has_schema_privilege('pbl_app', 'extensions', 'USAGE') THEN
        RAISE EXCEPTION 'Could not grant USAGE on schema extensions to pbl_app. Run this file as the database owner.';
    END IF;
END $$;


-- Reading ----------------------------------------------------------------------
GRANT SELECT ON subjects, tags, projects, project_members, project_links, project_tags, project_files,
                project_cards, review_queue, repeated_ideas, tag_trends
      TO pbl_app;

-- Every column of users except password_hash.
GRANT SELECT (user_id, name, email, prn, role, is_admin, must_change_password,
              password_changed_at, is_active, created_at)
      ON users TO pbl_app;


-- Changing ---------------------------------------------------------------------
-- Column-level UPDATE: the review decision, marks, and the embedding the app makes
-- for older projects. Title, abstract, subject and faculty can't be changed by the app.
GRANT UPDATE (status, review_note, marks, embedding) ON projects TO pbl_app;

-- Links and files are added and removed after a project exists.
GRANT INSERT, DELETE ON project_links, project_files TO pbl_app;

-- Admin pages: subjects, and switching people on or off or making them admins.
GRANT INSERT, UPDATE ON subjects TO pbl_app;
GRANT UPDATE (name, email, is_admin, is_active) ON users TO pbl_app;


-- Functions --------------------------------------------------------------------
-- hash_password() and temporary_password() are not on this list: only the
-- SECURITY DEFINER functions call them.
GRANT EXECUTE ON FUNCTION
      current_academic_year(),
      similarity_band(double precision),
      keyword_search(text, int),
      similar_projects(double precision[], int, int),
      hybrid_search(text, double precision[], int),
      submit_project(int, text, text, int, int, text[], text, text[], text[], text[], double precision[]),
      sign_in(text, text),
      change_password(int, text, text),
      create_user(text, text, text, text, boolean),
      reset_password(int)
      TO pbl_app;
