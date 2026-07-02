-- Extend publication full-text search to cover author names (weight C),
-- in addition to the existing title (A) and abstract (B).
--
-- A GENERATED column cannot reference other tables, and author names live in
-- `authors` linked through `authorships`. So we denormalize the author-name text
-- onto each publication row (maintained by triggers) and fold that column into
-- the generated `search_vector`. Author names use the `simple` config (no
-- stemming) so proper nouns aren't mangled; the API query ORs a `simple`
-- tsquery so english-stemmed query terms still match.

-- 1. Plain maintained column holding concatenated author-name text.
ALTER TABLE publications ADD COLUMN author_names_text TEXT NOT NULL DEFAULT '';

-- 2. Rebuild the generated column to append the author-name portion.
--    Dropping search_vector also drops idx_publications_search (it depends on
--    the column), so the GIN index MUST be recreated below.
ALTER TABLE publications DROP COLUMN search_vector;
ALTER TABLE publications ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', title), 'A') ||
    setweight(to_tsvector('english', COALESCE(abstract, '')), 'B') ||
    setweight(to_tsvector('simple',  COALESCE(author_names_text, '')), 'C')
) STORED;
CREATE INDEX idx_publications_search ON publications USING GIN(search_vector);

COMMENT ON COLUMN publications.search_vector IS
    'Auto-generated FTS index on title (A), abstract (B), and author names (C)';
COMMENT ON COLUMN publications.author_names_text IS
    'Denormalized author full_name + published_as_name, maintained by triggers';

-- 3. Recompute helper: build the author-name text for one publication.
CREATE OR REPLACE FUNCTION publications_author_names_text(pub_id UUID)
RETURNS TEXT AS $$
    SELECT COALESCE(
        string_agg(concat_ws(' ', a.full_name, au.published_as_name), ' '),
        ''
    )
    FROM authorships au
    JOIN authors a ON a.id = au.author_id
    WHERE au.publication_id = pub_id;
$$ LANGUAGE SQL STABLE;

-- 4a. authorships INSERT/UPDATE/DELETE -> recompute the affected publication(s).
CREATE OR REPLACE FUNCTION authorships_sync_author_names()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        UPDATE publications
           SET author_names_text = publications_author_names_text(OLD.publication_id)
         WHERE id = OLD.publication_id;
        RETURN OLD;
    END IF;

    UPDATE publications
       SET author_names_text = publications_author_names_text(NEW.publication_id)
     WHERE id = NEW.publication_id;

    -- If an UPDATE moved the authorship to a different publication, refresh the old one too.
    IF TG_OP = 'UPDATE' AND NEW.publication_id <> OLD.publication_id THEN
        UPDATE publications
           SET author_names_text = publications_author_names_text(OLD.publication_id)
         WHERE id = OLD.publication_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_authorships_sync_author_names
AFTER INSERT OR UPDATE OR DELETE ON authorships
FOR EACH ROW
EXECUTE FUNCTION authorships_sync_author_names();

-- 4b. authors name change -> recompute every publication that author appears on.
CREATE OR REPLACE FUNCTION authors_sync_publication_author_names()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE publications p
       SET author_names_text = publications_author_names_text(p.id)
     WHERE p.id IN (SELECT publication_id FROM authorships WHERE author_id = NEW.id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_authors_sync_publication_author_names
AFTER UPDATE OF full_name, family_name, given_name, normalized_name ON authors
FOR EACH ROW
WHEN (OLD.full_name IS DISTINCT FROM NEW.full_name)
EXECUTE FUNCTION authors_sync_publication_author_names();

-- 5. One-time backfill for existing rows (also regenerates search_vector via the
--    STORED generated column, since author_names_text changes).
UPDATE publications p SET author_names_text = publications_author_names_text(p.id);
