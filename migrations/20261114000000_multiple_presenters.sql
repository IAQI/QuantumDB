-- Migration: allow several presenters per talk.
--
-- A presenter used to be a single column, publications.presenter_author_id,
-- kept consistent with the author list by two triggers
-- (ensure_presenter_is_author on publications,
-- trg_clear_presenter_on_authorship_delete on authorships). Some talks are
-- given by several of their authors (panels, merged talks, posters with two
-- presenters), which that column cannot hold.
--
-- The presenter is now a flag on the authorship row. A presenting author is
-- an author by construction, so both triggers go away. Presenters who are not
-- authors (rare: the authors could not travel) stay plain text in
-- publications.metadata.presenter_name ("; "-separated), deliberately not
-- linked to a person.
--
-- No backfill: the production DB is rebuilt from the CSVs in data/conferences/
-- (wipe + migrate + re-import), and the importer sets the flag from the
-- `speakers` column.

ALTER TABLE authorships
    ADD COLUMN is_presenter BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN authorships.is_presenter IS
'True when this author presented the talk/poster. A talk may have several presenters; often none is known. Presenters who are not authors are kept as text in publications.metadata.presenter_name.';

CREATE INDEX idx_authorships_presenter ON authorships(publication_id) WHERE is_presenter;

DROP TRIGGER IF EXISTS trg_clear_presenter_on_authorship_delete ON authorships;
DROP FUNCTION IF EXISTS clear_presenter_on_authorship_delete();

DROP TRIGGER IF EXISTS ensure_presenter_is_author ON publications;
DROP FUNCTION IF EXISTS validate_presenter_is_author();

DROP INDEX IF EXISTS idx_publications_presenter;
ALTER TABLE publications DROP COLUMN IF EXISTS presenter_author_id;
