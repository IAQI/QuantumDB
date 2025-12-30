-- Create authors table
-- No email field (privacy concern) - use ORCID for unique identification

CREATE TABLE authors (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Name fields
    full_name           TEXT NOT NULL,        -- Display name: "Alice B. Quantum"
    family_name         TEXT,                 -- For sorting: "Quantum"
    given_name          TEXT,                 -- First/given name: "Alice B."
    normalized_name     TEXT NOT NULL,        -- Lowercase, no accents, for matching

    -- Public identifiers (no private data like email)
    orcid               TEXT,                 -- ORCID identifier (0000-0000-0000-0000)
    homepage_url        TEXT,                 -- Personal/academic website

    -- Current affiliation (historical affiliations tracked in authorships)
    affiliation         TEXT,

    -- Audit fields
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator             TEXT NOT NULL,
    modifier            TEXT NOT NULL,
    metadata            JSONB DEFAULT '{}'::jsonb,

    -- ORCID format validation
    CONSTRAINT valid_orcid CHECK (orcid IS NULL OR orcid ~ '^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$')
);

-- Indexes for common lookups
CREATE INDEX idx_authors_normalized_name ON authors(normalized_name);
CREATE INDEX idx_authors_family_name ON authors(family_name);
CREATE INDEX idx_authors_orcid ON authors(orcid) WHERE orcid IS NOT NULL;
CREATE INDEX idx_authors_metadata ON authors USING GIN(metadata);

COMMENT ON TABLE authors IS 'Unique individuals who author papers or serve on committees';
COMMENT ON COLUMN authors.normalized_name IS 'Lowercase, ASCII-only version for fuzzy matching';
COMMENT ON COLUMN authors.orcid IS 'ORCID iD in format 0000-0000-0000-000X';
