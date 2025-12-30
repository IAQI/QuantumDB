-- Create materialized views for common statistics and queries

-- Author statistics view
CREATE MATERIALIZED VIEW author_stats AS
SELECT
    a.id,
    a.full_name,
    a.family_name,
    COUNT(DISTINCT p.id) as publication_count,
    COUNT(DISTINCT cr.id) as committee_role_count,
    COUNT(DISTINCT CASE WHEN cr.position IN ('chair', 'co_chair') THEN cr.id END) as leadership_count,
    array_agg(DISTINCT c.venue ORDER BY c.venue) FILTER (WHERE c.venue IS NOT NULL) as venues,
    MIN(c.year) as first_year,
    MAX(c.year) as last_year
FROM authors a
LEFT JOIN authorships au ON a.id = au.author_id
LEFT JOIN publications p ON au.publication_id = p.id
LEFT JOIN committee_roles cr ON a.id = cr.author_id
LEFT JOIN conferences c ON (p.conference_id = c.id OR cr.conference_id = c.id)
GROUP BY a.id, a.full_name, a.family_name;

CREATE UNIQUE INDEX idx_author_stats_id ON author_stats(id);

-- Conference statistics view
CREATE MATERIALIZED VIEW conference_stats AS
SELECT
    c.id,
    c.venue,
    c.year,
    COUNT(DISTINCT p.id) as publication_count,
    COUNT(DISTINCT CASE WHEN p.paper_type = 'regular' THEN p.id END) as regular_paper_count,
    COUNT(DISTINCT CASE WHEN p.paper_type = 'invited' THEN p.id END) as invited_talk_count,
    COUNT(DISTINCT CASE WHEN p.award IS NOT NULL THEN p.id END) as award_count,
    COUNT(DISTINCT cr.id) as committee_member_count,
    COUNT(DISTINCT a.id) as unique_author_count,
    c.submission_count,
    c.acceptance_count,
    CASE
        WHEN c.submission_count > 0 AND c.acceptance_count IS NOT NULL
        THEN ROUND((c.acceptance_count::numeric / c.submission_count::numeric) * 100, 1)
        ELSE NULL
    END as acceptance_rate
FROM conferences c
LEFT JOIN publications p ON c.id = p.conference_id
LEFT JOIN committee_roles cr ON c.id = cr.conference_id
LEFT JOIN authorships au ON p.id = au.publication_id
LEFT JOIN authors a ON au.author_id = a.id
GROUP BY c.id, c.venue, c.year, c.submission_count, c.acceptance_count;

CREATE UNIQUE INDEX idx_conference_stats_id ON conference_stats(id);

-- Coauthor network view (for future analysis)
CREATE MATERIALIZED VIEW coauthor_pairs AS
SELECT
    a1.author_id as author1_id,
    a2.author_id as author2_id,
    COUNT(DISTINCT a1.publication_id) as collaboration_count
FROM authorships a1
JOIN authorships a2 ON a1.publication_id = a2.publication_id
    AND a1.author_id < a2.author_id  -- Avoid duplicates and self-pairs
GROUP BY a1.author_id, a2.author_id;

CREATE INDEX idx_coauthor_pairs_author1 ON coauthor_pairs(author1_id);
CREATE INDEX idx_coauthor_pairs_author2 ON coauthor_pairs(author2_id);

COMMENT ON MATERIALIZED VIEW author_stats IS 'Pre-computed author statistics - refresh after bulk updates';
COMMENT ON MATERIALIZED VIEW conference_stats IS 'Pre-computed conference statistics - refresh after bulk updates';
COMMENT ON MATERIALIZED VIEW coauthor_pairs IS 'Coauthor collaboration counts - refresh after bulk updates';
