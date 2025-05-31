-- Add migration script here
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE conferences (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    venue           TEXT NOT NULL CHECK (venue IN ('qip', 'qcrypt', 'tqc')),
    year            INT NOT NULL,
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    location        TEXT NOT NULL,
    website_url     TEXT,
    proceedings_url TEXT,
    submission_count INT,
    acceptance_count INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator         TEXT NOT NULL,
    modifier        TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}'::jsonb,
    
    UNIQUE (venue, year)
);
