-- Migration: keep presenter_author_id consistent when an authorship is removed.
--
-- Background: publications.presenter_author_id must reference one of the
-- publication's authors (enforced by ensure_presenter_is_author, a BEFORE
-- INSERT/UPDATE trigger on publications). That invariant is only maintained on
-- the *publications* side: nothing on the authorships side cleans up the
-- presenter when the presenter's authorship row is deleted.
--
-- Two failure modes result from that gap when authorship rows are rewritten
-- (e.g. the talk importer's delete-then-reinsert, or an author merge):
--   1. Without any sync, deleting a presenter's authorship silently leaves
--      presenter_author_id dangling (points at a non-author, no error).
--   2. With trg_authorships_sync_author_names (which runs
--      `UPDATE publications SET author_names_text = ...` on any authorship
--      change), that update re-fires ensure_presenter_is_author *mid-delete*,
--      raising "presenter_author_id must be one of the publication authors".
--
-- Fix: a BEFORE DELETE trigger on authorships that clears the presenter when the
-- authorship being removed is the presenter's. BEFORE-delete runs ahead of the
-- AFTER-delete sync trigger, so presenter_author_id is already NULL (allowed) by
-- the time the sync UPDATE re-validates. Callers that replace authorships and
-- want to keep the presenter simply set it again afterwards (the importer does).
-- This makes the invariant self-maintaining for every caller, not just the
-- importer.

CREATE OR REPLACE FUNCTION clear_presenter_on_authorship_delete()
RETURNS TRIGGER AS $$
BEGIN
    -- Only touches the publication when the deleted authorship IS the presenter,
    -- so the UPDATE is a no-op (0 rows) for ordinary co-author deletions.
    UPDATE publications
    SET presenter_author_id = NULL
    WHERE id = OLD.publication_id
      AND presenter_author_id = OLD.author_id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_clear_presenter_on_authorship_delete ON authorships;
CREATE TRIGGER trg_clear_presenter_on_authorship_delete
    BEFORE DELETE ON authorships
    FOR EACH ROW
    EXECUTE FUNCTION clear_presenter_on_authorship_delete();
