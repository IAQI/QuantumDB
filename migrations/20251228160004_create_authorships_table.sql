-- Create authorships table
-- Links authors to publications with ordering and point-in-time affiliation

CREATE TABLE authorships (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    publication_id      UUID NOT NULL REFERENCES publications(id) ON DELETE CASCADE,
    author_id           UUID NOT NULL REFERENCES authors(id),

    author_position     INT NOT NULL,         -- 1-indexed author order
    published_as_name   TEXT NOT NULL,        -- Name as it appeared on the paper
    affiliation         TEXT,                 -- Affiliation at time of publication

    -- Audit fields
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator             TEXT NOT NULL,
    modifier            TEXT NOT NULL,

    -- Constraints
    UNIQUE (publication_id, author_id),       -- Each author appears once per paper
    UNIQUE (publication_id, author_position)  -- Each position is unique per paper
);

-- Indexes for common queries
CREATE INDEX idx_authorships_author ON authorships(author_id);
CREATE INDEX idx_authorships_publication ON authorships(publication_id);

COMMENT ON TABLE authorships IS 'Links authors to publications with ordering and historical affiliation';
COMMENT ON COLUMN authorships.author_position IS '1-indexed position in author list';
COMMENT ON COLUMN authorships.published_as_name IS 'Name exactly as it appeared on the paper';
COMMENT ON COLUMN authorships.affiliation IS 'Author affiliation at time of publication';
