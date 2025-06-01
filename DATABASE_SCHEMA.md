# Database Schema for QuantumDB

## Core Tables

### 1. conferences
```sql
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
```

### 2. publications
```sql
CREATE TABLE publications (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conference_id   UUID NOT NULL REFERENCES conferences(id),
    lastmodified    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creationdate    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    canonicalkey    TEXT NOT NULL,        -- Unique identifier for the paper
    creator         TEXT NOT NULL,        -- Who/what created this record
    modifier        TEXT NOT NULL,        -- Who/what last modified this record
    title           TEXT NOT NULL,
    abstract        TEXT,
    videourl        TEXT,
    youtube         TEXT,
    presentationurl TEXT,
    award           TEXT,                 -- e.g., "Best Paper", "Best Student Paper"
    publisheddate   DATE,
    awarddate       DATE,
    invited         TEXT,                 -- For invited talks
    doi             TEXT,
    metadata        JSONB DEFAULT '{}'::jsonb,
    search_vector   tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', title), 'A') ||
        setweight(to_tsvector('english', COALESCE(abstract, '')), 'B')
    ) STORED,
    
    PRIMARY KEY (pubkey),
    UNIQUE KEY (canonicalkey),
    
    FOREIGN KEY (conference_id) REFERENCES conferences(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create indexes for publications
CREATE INDEX idx_publications_search ON publications USING GIN(search_vector);
CREATE INDEX idx_publications_conference ON publications(conference_id);
CREATE INDEX idx_publications_metadata ON publications USING GIN(metadata);
```

### 3. authors
```sql
CREATE TABLE authors (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name       TEXT NOT NULL,
    normalized_name TEXT NOT NULL,  -- Lowercase, no accents, for matching
    orcid          TEXT,           -- ORCID identifier
    email          TEXT,
    affiliation    TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator        TEXT NOT NULL,
    modifier       TEXT NOT NULL,
    metadata       JSONB DEFAULT '{}'::jsonb,
    
    -- Ensure normalized names are unique
    UNIQUE (normalized_name)
);

-- Index for faster name lookups
CREATE INDEX idx_authors_normalized_name ON authors(normalized_name);
CREATE INDEX idx_authors_metadata ON authors USING GIN(metadata);
```

### 4. authorships
```sql
CREATE TABLE authorships (
    publication_id  UUID NOT NULL REFERENCES publications(id),
    author_id       UUID NOT NULL REFERENCES authors(id),
    authornumber    INT NOT NULL,         -- Order of authors
    publishedasname TEXT NOT NULL,        -- Name as it appeared on the paper
    affiliation     TEXT,                 -- Affiliation at time of publication
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator         TEXT NOT NULL,
    modifier        TEXT NOT NULL,
    
    PRIMARY KEY (publication_id, author_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create indexes for authorships
CREATE INDEX idx_authorships_author ON authorships(author_id);
CREATE INDEX idx_authorships_publication ON authorships(publication_id);
```

### 5. committee_roles
```sql
-- Committee types (PC = Program Committee, SC = Steering Committee)
CREATE TYPE committee_type AS ENUM ('PC', 'SC', 'Local');

-- Position types within a committee
CREATE TYPE position_type AS ENUM ('chair', 'co-chair', 'member');

CREATE TABLE committee_roles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conference_id   UUID NOT NULL REFERENCES conferences(id),
    author_id       UUID NOT NULL REFERENCES authors(id),
    committee       committee_type NOT NULL,
    position        position_type NOT NULL DEFAULT 'member',
    title           TEXT,           -- Optional custom title (e.g., "General Chair", "Local Arrangements Chair")
    start_date      DATE,
    end_date        DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator         TEXT NOT NULL,
    modifier        TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}'::jsonb,
    
    -- Ensure no duplicate roles for same person at same conference and committee
    UNIQUE (conference_id, author_id, committee),
    
    -- Constraint: Only one chair per committee per conference
    UNIQUE (conference_id, committee, position) 
    WHERE position = 'chair'
);

-- Indexes for faster lookups
CREATE INDEX idx_committee_roles_conference ON committee_roles(conference_id);
CREATE INDEX idx_committee_roles_author ON committee_roles(author_id);
CREATE INDEX idx_committee_roles_metadata ON committee_roles USING GIN(metadata);
```

Example committee role assignments:
```sql
-- Program Committee Chair
INSERT INTO committee_roles (conference_id, author_id, committee, position, title)
VALUES ('123', '456', 'pc', 'chair', 'Program Committee Chair');

-- Program Committee Co-Chair
INSERT INTO committee_roles (conference_id, author_id, committee, position, title)
VALUES ('123', '789', 'pc', 'co-chair', 'Program Committee Co-Chair');

-- Regular PC member
INSERT INTO committee_roles (conference_id, author_id, committee, position)
VALUES ('123', '012', 'pc', 'member');

-- Local Chair
INSERT INTO committee_roles (conference_id, author_id, committee, position, title)
VALUES ('123', '345', 'local', 'chair', 'Local Arrangements Chair');
```

## Materialized Views
```sql
-- Author statistics
CREATE MATERIALIZED VIEW author_stats AS
SELECT 
    a.id,
    a.fullname,
    COUNT(DISTINCT p.id) as publication_count,
    COUNT(DISTINCT cr.id) as committee_roles_count,
    array_agg(DISTINCT c.venue) as venues,
    array_agg(DISTINCT c.year) as years
FROM authors a
LEFT JOIN authorships au ON a.id = au.author_id
LEFT JOIN publications p ON au.publication_id = p.id
LEFT JOIN committee_roles cr ON a.id = cr.author_id
LEFT JOIN conferences c ON 
    (p.conference_id = c.id OR cr.conference_id = c.id)
GROUP BY a.id, a.fullname;

-- Conference statistics
CREATE MATERIALIZED VIEW conference_stats AS
SELECT 
    c.id,
    c.venue,
    c.year,
    COUNT(DISTINCT p.id) as publication_count,
    COUNT(DISTINCT cr.id) as committee_count,
    COUNT(DISTINCT a.id) as unique_authors,
    c.submission_count,
    c.acceptance_count,
    CASE 
        WHEN c.submission_count > 0 
        THEN ROUND((c.acceptance_count::float / c.submission_count::float) * 100, 2)
        ELSE NULL
    END as acceptance_rate
FROM conferences c
LEFT JOIN publications p ON c.id = p.conference_id
LEFT JOIN committee_roles cr ON c.id = cr.conference_id
LEFT JOIN authorships au ON p.id = au.publication_id
LEFT JOIN authors a ON au.author_id = a.id
GROUP BY c.id, c.venue, c.year;

## Changes from Original Schema

1. Modernized for PostgreSQL:
   - Changed to UUID primary keys
   - Added TIMESTAMPTZ for timestamps
   - Added JSONB for flexible metadata
   - Added full-text search capabilities
   - Added materialized views for performance

2. Added conferences table:
   - Central reference for conference instances
   - Tracks venue details and statistics
   - Links to proceedings and websites

3. Enhanced tracking:
   - Better audit trails with created_at/updated_at
   - Flexible metadata storage
   - Improved indexing strategy

4. Preserved core functionality:
   - Author name changes
   - Multiple affiliations
   - Committee roles
   - Paper types and awards
