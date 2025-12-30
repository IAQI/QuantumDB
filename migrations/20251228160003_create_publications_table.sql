-- Create paper_type enum and publications table

-- Paper/presentation types
CREATE TYPE paper_type AS ENUM (
    'regular',          -- Full paper
    'short',            -- Short/extended abstract
    'poster',           -- Poster presentation
    'invited',          -- Invited talk
    'tutorial',         -- Tutorial
    'keynote'           -- Keynote address
);

CREATE TABLE publications (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conference_id       UUID NOT NULL REFERENCES conferences(id),

    -- Identifiers
    canonical_key       TEXT NOT NULL UNIQUE, -- Unique key for the paper (e.g., "QIP2024-123")
    doi                 TEXT,                 -- DOI if available
    arxiv_ids           TEXT[],               -- arXiv identifiers (can have multiple)

    -- Core metadata
    title               TEXT NOT NULL,
    abstract            TEXT,
    paper_type          paper_type NOT NULL DEFAULT 'regular',

    -- Citation metadata (for BibTeX generation)
    pages               TEXT,                 -- Page range (e.g., "1:1-1:25" or "123-145")

    -- Presentation details
    session_name        TEXT,                 -- Which session (e.g., "Quantum Error Correction")
    presentation_url    TEXT,                 -- Slides/presentation link
    video_url           TEXT,                 -- Video recording URL
    youtube_id          TEXT,                 -- YouTube video ID (for embedding)

    -- Awards
    award               TEXT,                 -- e.g., "Best Paper", "Best Student Paper"
    award_date          DATE,

    -- Dates
    published_date      DATE,                 -- When published in proceedings (if applicable)

    -- Full-text search vector (auto-generated)
    search_vector       tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', title), 'A') ||
        setweight(to_tsvector('english', COALESCE(abstract, '')), 'B')
    ) STORED,

    -- Audit fields
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator             TEXT NOT NULL,
    modifier            TEXT NOT NULL,
    metadata            JSONB DEFAULT '{}'::jsonb
);

-- Indexes for common queries
CREATE INDEX idx_publications_conference ON publications(conference_id);
CREATE INDEX idx_publications_search ON publications USING GIN(search_vector);
CREATE INDEX idx_publications_arxiv ON publications USING GIN(arxiv_ids) WHERE arxiv_ids IS NOT NULL;
CREATE INDEX idx_publications_doi ON publications(doi) WHERE doi IS NOT NULL;
CREATE INDEX idx_publications_award ON publications(award) WHERE award IS NOT NULL;
CREATE INDEX idx_publications_paper_type ON publications(paper_type);
CREATE INDEX idx_publications_metadata ON publications USING GIN(metadata);

COMMENT ON TABLE publications IS 'Papers, talks, and presentations at conferences';
COMMENT ON COLUMN publications.canonical_key IS 'Unique identifier like QIP2024-123';
COMMENT ON COLUMN publications.arxiv_ids IS 'Array of arXiv IDs (some papers have multiple versions/parts)';
COMMENT ON COLUMN publications.search_vector IS 'Auto-generated full-text search index on title and abstract';
