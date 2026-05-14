-- Permanent human-readable author URL slugs.
--
-- Format: lower(family_name)-lower(given_name), accents stripped, non-alphanumeric runs
-- collapsed to a single hyphen. Collisions get a deterministic numeric suffix
-- ("-2", "-3", …) in (created_at, id) order so existing URLs stay stable.
--
-- Slugs are sticky once assigned: they are NOT recomputed on UPDATE. URL is forever.

CREATE EXTENSION IF NOT EXISTS unaccent;

-- Slugify a single string: strip accents, lowercase, collapse non-alphanumeric to "-".
CREATE OR REPLACE FUNCTION quantumdb_slugify(s TEXT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT NULLIF(
        trim(both '-' from regexp_replace(lower(unaccent(coalesce(s, ''))), '[^a-z0-9]+', '-', 'g')),
        ''
    );
$$;

ALTER TABLE authors ADD COLUMN slug TEXT;

-- Backfill existing rows with deterministic collision-suffixed slugs.
WITH base AS (
    SELECT
        id,
        created_at,
        COALESCE(
            NULLIF(concat_ws('-', quantumdb_slugify(family_name), quantumdb_slugify(given_name)), ''),
            quantumdb_slugify(full_name),
            'anon'
        ) AS base_slug
    FROM authors
),
ranked AS (
    SELECT
        id,
        base_slug,
        ROW_NUMBER() OVER (PARTITION BY base_slug ORDER BY created_at, id) AS dup
    FROM base
)
UPDATE authors a
SET slug = ranked.base_slug || CASE WHEN ranked.dup > 1 THEN '-' || ranked.dup ELSE '' END
FROM ranked
WHERE a.id = ranked.id;

ALTER TABLE authors ALTER COLUMN slug SET NOT NULL;
CREATE UNIQUE INDEX authors_slug_unique ON authors(slug);

-- Trigger: assign a unique slug on INSERT when one isn't provided.
-- Concurrent inserts can race on the EXISTS check; for this single-tenant
-- scraper-driven workload that's acceptable. A serious multi-writer setup
-- would handle the unique-violation in app code instead.
CREATE OR REPLACE FUNCTION authors_assign_slug()
RETURNS TRIGGER AS $$
DECLARE
    base_slug TEXT;
    candidate TEXT;
    n INT := 1;
BEGIN
    IF NEW.slug IS NOT NULL AND NEW.slug <> '' THEN
        RETURN NEW;
    END IF;
    base_slug := COALESCE(
        NULLIF(concat_ws('-', quantumdb_slugify(NEW.family_name), quantumdb_slugify(NEW.given_name)), ''),
        quantumdb_slugify(NEW.full_name),
        'anon'
    );
    candidate := base_slug;
    WHILE EXISTS(SELECT 1 FROM authors WHERE slug = candidate) LOOP
        n := n + 1;
        candidate := base_slug || '-' || n;
    END LOOP;
    NEW.slug := candidate;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_authors_assign_slug
BEFORE INSERT ON authors
FOR EACH ROW
EXECUTE FUNCTION authors_assign_slug();

COMMENT ON COLUMN authors.slug IS 'Permanent human-readable URL slug. Auto-assigned on INSERT; never recomputed.';
