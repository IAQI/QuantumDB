-- Add `recent_affiliation` to the author_stats materialized view.
--
-- Motivation: the author page previously displayed `authors.affiliation`, a
-- single scalar that the CSV importer overwrites last-write-wins (whatever the
-- last-processed CSV naming that author happened to say). For authors spanning
-- many conference-years this is effectively arbitrary.
--
-- `recent_affiliation` instead picks the affiliation from the author's most
-- recent dated appearance — across both `authorships` and `committee_roles`,
-- ordered by conference year — falling back to `authors.affiliation` when no
-- dated appearance carries one.

DROP MATERIALIZED VIEW IF EXISTS author_stats;

CREATE MATERIALIZED VIEW author_stats AS
SELECT
    a.id,
    a.full_name,
    a.family_name,
    COUNT(DISTINCT p.id) AS publication_count,
    COUNT(DISTINCT cr.id) AS committee_role_count,
    COUNT(DISTINCT CASE
        WHEN cr."position" = ANY (ARRAY['chair'::committee_position, 'co_chair'::committee_position])
        THEN cr.id ELSE NULL::uuid END) AS leadership_count,
    ARRAY_AGG(DISTINCT c.venue ORDER BY c.venue) FILTER (WHERE c.venue IS NOT NULL) AS venues,
    MIN(c.year) AS first_year,
    MAX(c.year) AS last_year,
    COALESCE(
        (SELECT app.affiliation
         FROM (
             SELECT au2.affiliation, c2.year
             FROM authorships au2
             JOIN publications p2 ON au2.publication_id = p2.id
             JOIN conferences c2 ON p2.conference_id = c2.id
             WHERE au2.author_id = a.id
               AND au2.affiliation IS NOT NULL AND au2.affiliation <> ''
             UNION ALL
             SELECT cr2.affiliation, c2.year
             FROM committee_roles cr2
             JOIN conferences c2 ON cr2.conference_id = c2.id
             WHERE cr2.author_id = a.id
               AND cr2.affiliation IS NOT NULL AND cr2.affiliation <> ''
         ) app
         ORDER BY app.year DESC NULLS LAST
         LIMIT 1),
        a.affiliation
    ) AS recent_affiliation
FROM authors a
LEFT JOIN authorships au ON a.id = au.author_id
LEFT JOIN publications p ON au.publication_id = p.id
LEFT JOIN committee_roles cr ON a.id = cr.author_id
LEFT JOIN conferences c ON p.conference_id = c.id OR cr.conference_id = c.id
GROUP BY a.id, a.full_name, a.family_name, a.affiliation;

-- Unique index so the view can be refreshed CONCURRENTLY.
CREATE UNIQUE INDEX idx_author_stats_id ON author_stats(id);
