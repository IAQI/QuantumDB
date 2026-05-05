-- Add a UNIQUE index on coauthor_pairs so it can be refreshed with
-- REFRESH MATERIALIZED VIEW CONCURRENTLY (which requires at least one
-- unique index covering all rows).
--
-- The view's GROUP BY (author1_id, author2_id) already guarantees uniqueness,
-- so this index is a structural assertion, not a deduplication step.

CREATE UNIQUE INDEX IF NOT EXISTS idx_coauthor_pairs_unique
    ON coauthor_pairs(author1_id, author2_id);
