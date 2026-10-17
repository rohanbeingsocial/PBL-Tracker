-- 01_tables.sql
-- Extensions, the pbl schema and the eight tables.
--
-- Everything lives in its own schema, "pbl". On Supabase only the "public" schema
-- is exposed through the auto-generated REST API, so these tables can't be reached
-- that way. The app connects to Postgres directly.

-- pgvector for the embeddings, pgcrypto for password hashing. Supabase already has
-- both in the "extensions" schema; a local Postgres gets them here.
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;

DO $$
DECLARE
    v_ext text;
BEGIN
    SELECT string_agg(extname, ', ') INTO v_ext
    FROM pg_extension
    WHERE extname IN ('vector', 'pgcrypto') AND extnamespace::regnamespace::text <> 'extensions';
    IF v_ext IS NOT NULL THEN
        RAISE EXCEPTION 'Installed in another schema: %. Move it first, e.g. ALTER EXTENSION pgcrypto SET SCHEMA extensions;', v_ext;
    END IF;
END $$;

CREATE SCHEMA pbl;
SET search_path = pbl, extensions;


-- Everyone who signs in: students and faculty. Students sign in with their PRN or
-- email, faculty with their email. Emails are stored in lowercase only, so UNIQUE
-- can't be dodged with capital letters. Only bcrypt hashes are stored, and the app's
-- login can't read that column (06_security.sql).
CREATE TABLE users (
    user_id               INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                  VARCHAR(100) NOT NULL CHECK (length(btrim(name)) >= 2),
    email                 VARCHAR(120) NOT NULL UNIQUE CHECK (email ~ '^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'),
    prn                   VARCHAR(10)  UNIQUE CHECK (prn ~ '^[0-9]{10}$'),
    role                  VARCHAR(10)  NOT NULL CHECK (role IN ('student', 'faculty')),
    is_admin              BOOLEAN      NOT NULL DEFAULT false,    -- the PBL coordinator
    password_hash         TEXT         NOT NULL CHECK (password_hash LIKE '$2a$%'),
    must_change_password  BOOLEAN      NOT NULL DEFAULT true,     -- after an admin sets a temporary one
    password_changed_at   TIMESTAMPTZ  NOT NULL DEFAULT clock_timestamp(),
    is_active             BOOLEAN      NOT NULL DEFAULT true,     -- false after they leave; their projects stay
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT students_have_a_prn     CHECK ((role = 'student') = (prn IS NOT NULL)),
    CONSTRAINT only_faculty_are_admins CHECK (NOT is_admin OR role = 'faculty')
);

-- Each subject marks its project out of its own total: a lab might give 33, a
-- theory subject 5. The faculty member enters any value from 0 to that total.
CREATE TABLE subjects (
    subject_id  INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        VARCHAR(20)  NOT NULL UNIQUE CHECK (code ~ '^[A-Z0-9-]{2,20}$'),   -- 'DBMS-PBL'
    name        VARCHAR(100) NOT NULL,
    max_marks   NUMERIC(5,1) NOT NULL CHECK (max_marks > 0)
);

CREATE TABLE projects (
    project_id     INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title          VARCHAR(200) NOT NULL CHECK (length(btrim(title)) >= 5),
    abstract       TEXT         NOT NULL CHECK (length(abstract) BETWEEN 30 AND 3000),
    subject_id     INT          NOT NULL REFERENCES subjects(subject_id),
    faculty_id     INT          NOT NULL REFERENCES users(user_id),       -- must be faculty (trigger)
    academic_year  VARCHAR(7)   NOT NULL,                                 -- '2026-27'
    project_type   VARCHAR(10)  NOT NULL CHECK (project_type IN ('software', 'hardware', 'both')),
    status         VARCHAR(10)  NOT NULL DEFAULT 'proposed'
                   CHECK (status IN ('proposed', 'approved', 'rejected', 'completed')),
    review_note    VARCHAR(1000),
    marks          NUMERIC(5,1) CHECK (marks >= 0),     -- the upper limit is the subject's max_marks (trigger)
    search_text    TSVECTOR GENERATED ALWAYS AS (
                       setweight(to_tsvector('english', title), 'A') ||
                       setweight(to_tsvector('english', abstract), 'B')
                   ) STORED,
    embedding      vector(384),                         -- made by Python from title + abstract; NULL until then
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- Postgres tests CHECK constraints in alphabetical order of their names, so the
    -- format check always runs before the ::int casts in the sequence check.
    CONSTRAINT academic_year_format   CHECK (academic_year ~ '^20[0-9]{2}-[0-9]{2}$'),
    CONSTRAINT academic_year_sequence CHECK (right(academic_year, 2)::int = (left(academic_year, 4)::int + 1) % 100)
);

-- A team can have any number of students, and a student can be in several projects
-- in the same year (one per subject is normal). Deleting a project removes its
-- members, links, tags and file records (ON DELETE CASCADE). Deleting a user who is
-- still in a team is refused, because that would rewrite history.
CREATE TABLE project_members (
    project_id  INT     NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    user_id     INT     NOT NULL REFERENCES users(user_id),               -- must be a student (trigger)
    is_leader   BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (project_id, user_id)
);

CREATE TABLE project_links (
    link_id     INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id  INT          NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    label       VARCHAR(40)  NOT NULL CHECK (length(btrim(label)) >= 1),   -- 'GitHub', 'Demo video'
    url         VARCHAR(300) NOT NULL CHECK (url ~ '^https?://[^[:space:]]+$'),
    UNIQUE (project_id, url)
);

-- The stack a project used: 'ESP32', 'Flask', 'PostgreSQL'.
CREATE TABLE tags (
    tag_id  INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name    VARCHAR(60) NOT NULL CHECK (length(btrim(name)) >= 1)
);

CREATE TABLE project_tags (
    project_id  INT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    tag_id      INT NOT NULL REFERENCES tags(tag_id),
    PRIMARY KEY (project_id, tag_id)
);

-- Reports and presentations. The file itself is in the storage bucket; this row
-- says which project it belongs to, who uploaded it and where in the bucket it is.
CREATE TABLE project_files (
    file_id       INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id    INT          NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    kind          VARCHAR(10)  NOT NULL CHECK (kind IN ('report', 'ppt')),
    file_name     VARCHAR(200) NOT NULL CHECK (length(btrim(file_name)) >= 1),
    storage_path  VARCHAR(300) NOT NULL UNIQUE,
    size_bytes    INT          NOT NULL CHECK (size_bytes BETWEEN 1 AND 20971520),   -- 20 MB
    uploaded_by   INT          NOT NULL REFERENCES users(user_id),
    uploaded_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
