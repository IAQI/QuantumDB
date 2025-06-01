-- Add migration script here
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE conferences (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    venue           TEXT NOT NULL CHECK (venue IN ('QIP', 'QCRYPT', 'TQC')),
    year            INT NOT NULL,
    start_date      DATE,
    end_date        DATE,
    city            TEXT,
    country         TEXT,
    country_code    CHAR(2),  -- ISO 3166-1 alpha-2 code
    is_virtual      BOOLEAN DEFAULT false,
    is_hybrid       BOOLEAN DEFAULT false,
    timezone        TEXT,     -- IANA timezone identifier
    venue_name      TEXT,     -- Physical venue name (e.g., "ETH Zurich Main Building")
    website_url     TEXT,
    proceedings_url TEXT,
    submission_count INT,
    acceptance_count INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator         TEXT NOT NULL,
    modifier        TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}'::jsonb,
    
    UNIQUE (venue, year),
    -- Ensure country_code is valid ISO 3166-1 alpha-2
    CONSTRAINT valid_country_code CHECK (country_code ~ '^[A-Z]{2}$'),
    -- Ensure timezone is in a basic valid format
    CONSTRAINT valid_timezone CHECK (timezone ~ '^[A-Za-z]+/[A-Za-z_]+(/[A-Za-z_]+)?$')
);
