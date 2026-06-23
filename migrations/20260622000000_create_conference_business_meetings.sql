-- Create conference_business_meetings table
-- Stores statistics ANNOUNCED at a conference's annual business meeting
-- (registered participants, submission/acceptance counts, prizes context, etc.).
-- One row per conference (1:1). Deliberately distinct from the COMPUTED figures
-- in the conference_stats materialized view: the announced numbers are a sourced,
-- point-in-time record and may legitimately diverge from counts derived from
-- imported talk rows. This is a plain table -- no materialized-view refresh needed.

CREATE TABLE conference_business_meetings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conference_id UUID NOT NULL UNIQUE REFERENCES conferences(id) ON DELETE CASCADE,
    meeting_date DATE,

    -- Announced participation
    registered_participants INT,
    onsite_participants     INT,
    countries_represented   INT,

    -- Announced submission / acceptance (as stated at the meeting)
    talk_submissions   INT,
    talks_accepted     INT,
    posters_submitted  INT,
    posters_accepted   INT,
    acceptance_rate    NUMERIC(4,1),   -- announced %, when given directly

    -- TQC reports proceedings/workshop/poster-only splits; keep the granular
    -- breakdown here while the headline totals live in the columns above.
    track_breakdown JSONB,

    notes    TEXT,                            -- anything else announced (narrative)
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,  -- per-fact provenance: {"sources": {field: {source_type, source_url, source_date}}}

    -- Audit fields (mirrors conferences)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator TEXT NOT NULL,
    modifier TEXT NOT NULL
);

-- GIN index for JSONB provenance queries (matches the authorships/committee_roles pattern)
CREATE INDEX idx_conference_business_meetings_metadata
    ON conference_business_meetings USING GIN (metadata);

COMMENT ON TABLE conference_business_meetings IS
    'As-announced business-meeting statistics (1:1 with a conference). Distinct from the computed figures in conference_stats; see metadata->sources for per-fact provenance.';
