-- Create conferences table
-- Core table for tracking QIP, QCrypt, and TQC conferences

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE conferences (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    venue               TEXT NOT NULL CHECK (venue IN ('QIP', 'QCRYPT', 'TQC')),
    year                INT NOT NULL,

    -- Dates
    start_date          DATE,
    end_date            DATE,

    -- Location
    city                TEXT,
    country             TEXT,
    country_code        CHAR(2),          -- ISO 3166-1 alpha-2 code
    is_virtual          BOOLEAN DEFAULT false,
    is_hybrid           BOOLEAN DEFAULT false,
    timezone            TEXT,             -- IANA timezone identifier
    venue_name          TEXT,             -- Physical venue name (e.g., "ETH Zurich")

    -- URLs
    website_url         TEXT,
    proceedings_url     TEXT,

    -- Proceedings metadata (for citations) - only TQC has proceedings
    proceedings_publisher TEXT,           -- e.g., "Schloss Dagstuhl - LIPIcs"
    proceedings_volume    TEXT,           -- e.g., "LIPIcs Volume 266"
    proceedings_doi       TEXT,           -- DOI for the proceedings collection

    -- Statistics
    submission_count    INT,
    acceptance_count    INT,

    -- Audit fields
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator             TEXT NOT NULL,
    modifier            TEXT NOT NULL,
    metadata            JSONB DEFAULT '{}'::jsonb,

    UNIQUE (venue, year),
    CONSTRAINT valid_country_code CHECK (country_code IS NULL OR country_code ~ '^[A-Z]{2}$'),
    CONSTRAINT valid_timezone CHECK (timezone IS NULL OR timezone ~ '^[A-Za-z]+/[A-Za-z_]+(/[A-Za-z_]+)?$')
);

CREATE INDEX idx_conferences_venue_year ON conferences(venue, year);

COMMENT ON TABLE conferences IS 'QIP, QCrypt, and TQC conference instances';
COMMENT ON COLUMN conferences.proceedings_publisher IS 'Only TQC has published proceedings';
