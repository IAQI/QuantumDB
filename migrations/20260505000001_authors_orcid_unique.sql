-- Enforce that ORCID iDs are globally unique across authors.
--
-- ORCIDs are by definition unique identifiers for a single researcher; allowing two
-- author rows to share an ORCID is a data-integrity bug, not a use case. PostgreSQL
-- treats NULLs as distinct, so authors without an ORCID are unaffected.
--
-- The existing partial index `idx_authors_orcid` (WHERE orcid IS NOT NULL) is dropped
-- because the new UNIQUE constraint creates its own backing index that subsumes it.

ALTER TABLE authors
    ADD CONSTRAINT authors_orcid_unique UNIQUE (orcid);

DROP INDEX IF EXISTS idx_authors_orcid;
