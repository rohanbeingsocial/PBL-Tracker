-- 03_functions.sql
-- Helper functions, the three search functions, submit_project() and sign-in.
--
-- Every function pins its search_path, so a caller can't make it pick up a
-- look-alike table or operator from another schema.
SET search_path = pbl, extensions;


-- Academic year running today, e.g. '2026-27'. The year starts in June.
CREATE FUNCTION current_academic_year() RETURNS varchar
LANGUAGE sql STABLE
SET search_path = ''
AS $$
    SELECT y || '-' || lpad(((y + 1) % 100)::text, 2, '0')
    FROM (SELECT extract(year FROM current_date)::int
                 - CASE WHEN extract(month FROM current_date) < 6 THEN 1 ELSE 0 END AS y) AS t;
$$;


-- The one place where similarity scores get their labels. Used by the views, the
-- approval rule and the app. On the sample data, pairs that are the same idea scored
-- 0.50-0.76 and different ideas from the same field 0.42-0.56, so only 0.70+ is
-- treated as a near duplicate. Check again once real projects are loaded
-- (docs/design.md has the query).
CREATE FUNCTION similarity_band(similarity double precision) RETURNS text
LANGUAGE sql IMMUTABLE STRICT          -- STRICT: no score in, no label out
SET search_path = ''
AS $$
    SELECT CASE
               WHEN similarity >= 0.70 THEN 'near duplicate'
               WHEN similarity >= 0.50 THEN 'similar'
               WHEN similarity >= 0.35 THEN 'related'
               ELSE 'different'
           END;
$$;


-- Keyword search. websearch_to_tsquery never raises a syntax error on user input,
-- unlike to_tsquery. ts_headline is slow, so the matches are ranked and trimmed
-- to how_many first, and snippets are built only for the rows that are left.
CREATE FUNCTION keyword_search(query_text text, how_many int DEFAULT 20)
RETURNS TABLE (project_id int, title varchar, academic_year varchar, subject varchar,
               status varchar, rank real, snippet text)
LANGUAGE sql STABLE
SET search_path = pbl, pg_temp
AS $$
    SELECT m.project_id, m.title, l.academic_year, s.code, m.status, m.rank,
           ts_headline('english', m.abstract, m.query,
                       'StartSel=«, StopSel=», MaxWords=40, MinWords=20, MaxFragments=2')
    FROM (
        SELECT p.project_id, p.title, p.abstract, p.submission_link_id, p.status,
               q AS query, ts_rank_cd(p.search_text, q) AS rank
        FROM projects p, websearch_to_tsquery('english', query_text) AS q
        WHERE p.search_text @@ q
        ORDER BY rank DESC, p.project_id
        LIMIT how_many
    ) AS m
    JOIN submission_links l ON l.submission_link_id = m.submission_link_id
    JOIN subjects s         ON s.subject_id = l.subject_id
    ORDER BY m.rank DESC, m.project_id;
$$;


-- Meaning search. Python sends the 384 numbers as a plain float array; the cast to
-- vector(384) also rejects arrays of the wrong length.
CREATE FUNCTION similar_projects(query_embedding double precision[], how_many int DEFAULT 5,
                                 exclude_project int DEFAULT NULL)
RETURNS TABLE (project_id int, title varchar, academic_year varchar, subject varchar,
               status varchar, similarity double precision, band text)
LANGUAGE sql STABLE
SET search_path = pbl, extensions, pg_temp
AS $$
    SELECT p.project_id, p.title, l.academic_year, s.code, p.status,
           1 - (p.embedding <=> query_embedding::vector(384)),
           similarity_band(1 - (p.embedding <=> query_embedding::vector(384)))
    FROM projects p
    JOIN submission_links l ON l.submission_link_id = p.submission_link_id
    JOIN subjects s         ON s.subject_id = l.subject_id
    WHERE p.embedding IS NOT NULL
      AND p.project_id IS DISTINCT FROM exclude_project
    ORDER BY p.embedding <=> query_embedding::vector(384)
    LIMIT how_many;
$$;


-- Both at once. Keyword and meaning search each produce a ranked list, and the lists
-- are merged with Reciprocal Rank Fusion: score = 1/(60 + rank in list A) + 1/(60 + rank
-- in list B). A project that ranks well in both lists ends up on top. Meaning-only hits
-- with a 'different' similarity are dropped, otherwise every query returns something.
CREATE FUNCTION hybrid_search(query_text text, query_embedding double precision[], how_many int DEFAULT 10)
RETURNS TABLE (project_id int, title varchar, academic_year varchar, subject varchar,
               status varchar, keyword_rank bigint, meaning_rank bigint,
               similarity double precision, band text, score numeric)
LANGUAGE sql STABLE
SET search_path = pbl, extensions, pg_temp
AS $$
    WITH keyword AS (
        SELECT p.project_id,
               row_number() OVER (ORDER BY ts_rank_cd(p.search_text, q) DESC, p.project_id) AS rank_no
        FROM projects p, websearch_to_tsquery('english', query_text) AS q
        WHERE p.search_text @@ q
        ORDER BY rank_no
        LIMIT 50
    ),
    meaning AS (
        SELECT n.project_id,
               row_number() OVER (ORDER BY n.distance) AS rank_no,
               1 - n.distance AS similarity
        FROM (SELECT p.project_id, p.embedding <=> query_embedding::vector(384) AS distance
              FROM projects p
              WHERE p.embedding IS NOT NULL
              ORDER BY distance          -- this ORDER BY + LIMIT can use the HNSW index
              LIMIT 50) AS n
    )
    SELECT p.project_id, p.title, l.academic_year, s.code, p.status,
           k.rank_no, m.rank_no, m.similarity, similarity_band(m.similarity),
           coalesce(1.0 / (60 + k.rank_no), 0) + coalesce(1.0 / (60 + m.rank_no), 0) AS score
    FROM keyword k
    FULL JOIN meaning m ON m.project_id = k.project_id
    JOIN projects p         ON p.project_id = coalesce(k.project_id, m.project_id)
    JOIN submission_links l ON l.submission_link_id = p.submission_link_id
    JOIN subjects s         ON s.subject_id = l.subject_id
    WHERE k.project_id IS NOT NULL OR similarity_band(m.similarity) <> 'different'
    ORDER BY score DESC, p.project_id
    LIMIT how_many;
$$;


-- The only way a project gets created from the app. Everything happens in one
-- transaction: if one PRN is wrong or one link is malformed, nothing is saved.
-- The report is required; the presentation is optional. The app stores both files
-- in the bucket first and passes their names, paths and sizes here.
--
-- SECURITY DEFINER means it runs with the rights of the function's owner, so the
-- app's login needs no INSERT rights on projects. The project goes in through a
-- submission link, which fixes the subject, faculty member and year; the status is
-- always 'submitted', whatever the caller sends. The student who submits it becomes
-- the team leader.
CREATE FUNCTION submit_project(
    p_leader_id     int,
    p_title         text,
    p_abstract      text,
    p_link_code     text,
    p_member_prns   text[],
    p_project_type  text,
    p_tags          text[],
    p_link_labels   text[],
    p_link_urls     text[],
    p_embedding     double precision[],
    p_report_name   text,
    p_report_path   text,
    p_report_size   int,
    p_ppt_name      text DEFAULT NULL,
    p_ppt_path      text DEFAULT NULL,
    p_ppt_size      int  DEFAULT NULL
) RETURNS int
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pbl, extensions, pg_temp
AS $$
DECLARE
    v_link        submission_links;
    v_project_id  int;
    v_unknown     text;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users u WHERE u.user_id = p_leader_id AND u.role = 'student' AND u.is_active) THEN
        RAISE EXCEPTION 'Only a student can submit a project' USING ERRCODE = 'check_violation';
    END IF;

    SELECT * INTO v_link FROM submission_links l WHERE l.code = p_link_code;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'No submission link with this code' USING ERRCODE = 'check_violation';
    END IF;
    IF NOT v_link.is_open THEN
        RAISE EXCEPTION 'This submission link is closed. Ask your faculty member.' USING ERRCODE = 'check_violation';
    END IF;

    SELECT string_agg(m, ', ') INTO v_unknown
    FROM unnest(p_member_prns) AS m
    WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.prn = m AND u.role = 'student');
    IF v_unknown IS NOT NULL THEN
        RAISE EXCEPTION 'No student with PRN %', v_unknown USING ERRCODE = 'check_violation';
    END IF;

    IF p_report_path IS NULL THEN
        RAISE EXCEPTION 'A project can only be submitted with its report' USING ERRCODE = 'check_violation';
    END IF;

    IF coalesce(cardinality(p_link_labels), 0) <> coalesce(cardinality(p_link_urls), 0) THEN
        RAISE EXCEPTION 'Every link needs a label and a URL' USING ERRCODE = 'check_violation';
    END IF;

    IF EXISTS (SELECT 1 FROM projects p
               WHERE p.submission_link_id = v_link.submission_link_id
                 AND lower(p.title) = lower(btrim(p_title))) THEN
        RAISE EXCEPTION 'A project with this title has already been submitted through this link'
              USING ERRCODE = 'unique_violation';
    END IF;

    INSERT INTO projects (submission_link_id, title, abstract, project_type, embedding)
    VALUES (v_link.submission_link_id, btrim(p_title), btrim(p_abstract), p_project_type,
            p_embedding::vector(384))
    RETURNING project_id INTO v_project_id;

    -- check_member() refuses a student who already has a live project in this link.

    INSERT INTO project_members (project_id, user_id, is_leader)
    VALUES (v_project_id, p_leader_id, true);

    INSERT INTO project_members (project_id, user_id)
    SELECT DISTINCT v_project_id, u.user_id
    FROM unnest(p_member_prns) AS m
    JOIN users u ON u.prn = m
    WHERE u.user_id <> p_leader_id;

    -- New tags are added to the list as they come; existing ones are matched ignoring case.
    INSERT INTO tags (name)
    SELECT DISTINCT btrim(t) FROM unnest(p_tags) AS t
    WHERE btrim(t) <> ''
    ON CONFLICT ((lower(name))) DO NOTHING;

    INSERT INTO project_tags (project_id, tag_id)
    SELECT DISTINCT v_project_id, tg.tag_id
    FROM unnest(p_tags) AS t
    JOIN tags tg ON lower(tg.name) = lower(btrim(t));

    INSERT INTO project_links (project_id, label, url)
    SELECT v_project_id, btrim(l.label), btrim(l.url)
    FROM unnest(p_link_labels, p_link_urls) AS l(label, url)
    ON CONFLICT (project_id, url) DO NOTHING;

    INSERT INTO project_files (project_id, kind, file_name, storage_path, size_bytes, uploaded_by)
    VALUES (v_project_id, 'report', btrim(p_report_name), p_report_path, p_report_size, p_leader_id);

    IF p_ppt_path IS NOT NULL THEN
        INSERT INTO project_files (project_id, kind, file_name, storage_path, size_bytes, uploaded_by)
        VALUES (v_project_id, 'ppt', btrim(p_ppt_name), p_ppt_path, p_ppt_size, p_leader_id);
    END IF;

    RETURN v_project_id;
END;
$$;


-- Sign-in ------------------------------------------------------------------------
--
-- Passwords are hashed with bcrypt through pgcrypto's crypt(). Cost 11 makes one
-- check take about 80 ms on our laptop: nothing for a person signing in, slow for
-- someone trying millions of guesses. The hashes never leave the database. The app
-- sends what was typed and gets back the user, or the reason it was refused.

-- Used by the functions below and by scripts/load_data.py. The app can't call it.
CREATE FUNCTION hash_password(p_password text) RETURNS text
LANGUAGE plpgsql VOLATILE
SET search_path = extensions, pg_temp
AS $$
BEGIN
    IF length(coalesce(p_password, '')) < 8 THEN
        RAISE EXCEPTION 'A password needs at least 8 characters' USING ERRCODE = 'check_violation';
    END IF;
    -- bcrypt reads only the first 72 bytes, so the rest of a longer password would be ignored.
    IF octet_length(p_password) > 72 THEN
        RAISE EXCEPTION 'A password can be at most 72 characters long' USING ERRCODE = 'check_violation';
    END IF;
    RETURN crypt(p_password, gen_salt('bf', 11));
END;
$$;


-- 12 random characters (72 bits) for an admin to hand to someone. It only works
-- until they sign in, because it is always stored with must_change_password.
CREATE FUNCTION temporary_password() RETURNS text
LANGUAGE sql VOLATILE
SET search_path = extensions, pg_temp
AS $$
    SELECT translate(encode(gen_random_bytes(9), 'base64'), '+/', 'kx');
$$;


-- Always returns one row. status is 'ok', 'wrong' (unknown login or wrong password,
-- the same answer on purpose so the form doesn't reveal which logins exist) or
-- 'disabled'. The other columns are filled only for 'ok'.
--
-- SECURITY DEFINER: it reads password_hash, which the caller has no rights on.
CREATE FUNCTION sign_in(p_login text, p_password text)
RETURNS TABLE (status text, user_id int, role text, is_admin boolean, name text, login text,
               prn text, must_change_password boolean, signed_in_at timestamptz)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pbl, extensions, pg_temp
AS $$
#variable_conflict use_column
DECLARE
    -- Lowercase, no spaces around it, and no invisible characters (zero-width spaces,
    -- word joiners) that come along when an address is copied from a web page.
    v_login  text := lower(btrim(regexp_replace(coalesce(p_login, ''), '[​-‍⁠﻿]', '', 'g')));
    v        record;
BEGIN
    SELECT u.* INTO v
      FROM users u
     WHERE u.prn = v_login OR u.email = v_login;

    IF NOT FOUND THEN
        -- Hash anyway, so an unknown login takes as long to refuse as a wrong password.
        PERFORM crypt(coalesce(p_password, ''), gen_salt('bf', 11));
        status := 'wrong';
        RETURN NEXT;
        RETURN;
    END IF;

    IF v.password_hash IS DISTINCT FROM crypt(coalesce(p_password, ''), v.password_hash) THEN
        status := 'wrong';
        RETURN NEXT;
        RETURN;
    END IF;

    -- Checked after the password, so only the real owner learns the account is off.
    IF NOT v.is_active THEN
        status := 'disabled';
        RETURN NEXT;
        RETURN;
    END IF;

    status := 'ok';
    user_id := v.user_id;
    role := v.role;
    is_admin := v.is_admin;
    name := v.name;
    login := coalesce(v.prn, v.email);
    prn := v.prn;
    must_change_password := v.must_change_password;
    signed_in_at := clock_timestamp();
    RETURN NEXT;
END;
$$;


-- A signed-in person choosing a new password. The current one is needed as well, so
-- a session left open on a lab computer can't be used to take the account over.
-- Returns the time of the change, or NULL if the current password was wrong. The app
-- keeps that time as its new sign-in time: this session stays valid and every other
-- one ends (finder/db.py compares it with password_changed_at).
CREATE FUNCTION change_password(p_user_id int, p_current text, p_new text) RETURNS timestamptz
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pbl, extensions, pg_temp
AS $$
DECLARE
    v_hash     text;
    v_changed  timestamptz := clock_timestamp();
BEGIN
    SELECT u.password_hash INTO v_hash FROM users u WHERE u.user_id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'No such user' USING ERRCODE = 'check_violation';
    END IF;

    IF v_hash IS DISTINCT FROM crypt(coalesce(p_current, ''), v_hash) THEN
        RETURN NULL;
    END IF;

    IF p_new = p_current THEN
        RAISE EXCEPTION 'The new password has to be different from the current one'
              USING ERRCODE = 'check_violation';
    END IF;

    UPDATE users u
       SET password_hash = hash_password(p_new),
           must_change_password = false,
           password_changed_at = v_changed
     WHERE u.user_id = p_user_id;
    RETURN v_changed;
END;
$$;


-- For the admin pages. Both return a temporary password to hand over once; the
-- person has to choose their own at the next sign-in.
CREATE FUNCTION create_user(p_name text, p_email text, p_prn text, p_role text, p_is_admin boolean)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pbl, extensions, pg_temp
AS $$
DECLARE
    v_temp  text := temporary_password();
BEGIN
    INSERT INTO users (name, email, prn, role, is_admin, password_hash, must_change_password)
    VALUES (btrim(p_name), lower(btrim(p_email)), nullif(btrim(p_prn), ''), p_role, coalesce(p_is_admin, false),
            hash_password(v_temp), true);
    RETURN v_temp;
END;
$$;


CREATE FUNCTION reset_password(p_user_id int) RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pbl, extensions, pg_temp
AS $$
DECLARE
    v_temp  text := temporary_password();
BEGIN
    UPDATE users u
       SET password_hash = hash_password(v_temp),
           must_change_password = true,
           password_changed_at = clock_timestamp()
     WHERE u.user_id = p_user_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'No such user' USING ERRCODE = 'check_violation';
    END IF;
    RETURN v_temp;
END;
$$;
