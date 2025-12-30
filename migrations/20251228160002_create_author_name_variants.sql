-- Create author_name_variants table
-- Tracks alternative names/spellings for the same author
-- Useful for: name changes, transliterations, abbreviations, maiden names

CREATE TABLE author_name_variants (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    author_id           UUID NOT NULL REFERENCES authors(id) ON DELETE CASCADE,

    variant_name        TEXT NOT NULL,        -- The alternative name/spelling
    normalized_variant  TEXT NOT NULL,        -- Normalized for matching
    variant_type        TEXT,                 -- e.g., "maiden_name", "transliteration", "abbreviation"
    notes               TEXT,                 -- Optional explanation

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator             TEXT NOT NULL,

    -- Each author can only have one entry per normalized variant
    UNIQUE (author_id, normalized_variant)
);

-- Index for searching by variant name
CREATE INDEX idx_author_variants_normalized ON author_name_variants(normalized_variant);

COMMENT ON TABLE author_name_variants IS 'Alternative names/spellings for authors (name changes, transliterations, etc.)';
