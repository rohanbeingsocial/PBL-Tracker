-- 02_indexes.sql
SET search_path = pbl, extensions;

-- Keyword search: GIN index on the generated tsvector column.
CREATE INDEX projects_search_idx ON projects USING gin (search_text);

-- Meaning search: HNSW index for nearest-neighbour lookups by cosine distance.
-- Rows without an embedding yet are simply not in the index.
CREATE INDEX projects_embedding_idx ON projects USING hnsw (embedding vector_cosine_ops);

-- Postgres does not index foreign keys by itself. These back the common joins.
-- (project_members, project_tags and project_links already start with project_id
-- in their primary key or UNIQUE constraint.)
CREATE INDEX projects_faculty_idx          ON projects (faculty_id);
CREATE INDEX projects_subject_year_idx     ON projects (subject_id, academic_year);
CREATE INDEX project_members_user_idx      ON project_members (user_id);
CREATE INDEX project_tags_tag_idx          ON project_tags (tag_id);
CREATE INDEX project_files_project_idx     ON project_files (project_id);

-- The same title twice in one subject and year is almost always a double submit.
CREATE UNIQUE INDEX projects_title_once_per_year ON projects (subject_id, academic_year, lower(title));

-- Tag names are unique ignoring case, so 'PostgreSQL' and 'postgresql' can't both exist.
CREATE UNIQUE INDEX tags_name_key ON tags (lower(name));

-- At most one leader per team. A partial index only covers rows where is_leader is true.
CREATE UNIQUE INDEX project_members_one_leader ON project_members (project_id) WHERE is_leader;
