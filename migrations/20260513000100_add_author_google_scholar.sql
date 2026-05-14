-- Google Scholar identifier for authors.
--
-- Stored as the bare user_id (the value from ?user=… in a profile URL).
-- Web pages render an https://scholar.google.com/citations?user=<id> link.

ALTER TABLE authors ADD COLUMN google_scholar_id TEXT;

COMMENT ON COLUMN authors.google_scholar_id IS
    'Google Scholar user_id (the ?user=… value from a profile URL).';
