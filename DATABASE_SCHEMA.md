# Database Schema for QuantumDB

## Design Principles

1. **Privacy First**: No email addresses stored (privacy-sensitive, often outdated)
2. **Citation Ready**: All fields needed for BibTeX generation
3. **Flexible Metadata**: JSONB fields for extensibility
4. **Audit Trail**: creator/modifier and timestamps on all tables
5. **PostgreSQL Native**: UUIDs, TIMESTAMPTZ, full-text search, proper constraints

## Core Tables

### 1. conferences
```sql
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

    -- Archive URLs (static backups of conference websites)
    archive_url              TEXT,         -- Main conference website archive
    archive_organizers_url   TEXT,         -- Archived organizers page
    archive_pc_url           TEXT,         -- Archived program committee page
    archive_steering_url     TEXT,         -- Archived steering committee page
    archive_program_url      TEXT,         -- Archived program/schedule page

    -- Proceedings metadata (for citations)
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
```

### 2. authors
```sql
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

    -- Current affiliation (historical affiliations in authorships)
    affiliation         TEXT,

    -- Audit fields
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator             TEXT NOT NULL,
    modifier            TEXT NOT NULL,
    metadata            JSONB DEFAULT '{}'::jsonb,

    CONSTRAINT valid_orcid CHECK (orcid IS NULL OR orcid ~ '^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$')
);

-- Indexes
CREATE INDEX idx_authors_normalized_name ON authors(normalized_name);
CREATE INDEX idx_authors_family_name ON authors(family_name);
CREATE INDEX idx_authors_orcid ON authors(orcid) WHERE orcid IS NOT NULL;
CREATE INDEX idx_authors_metadata ON authors USING GIN(metadata);
```

### 3. author_name_variants
Tracks alternative names/spellings for the same author (name changes, transliterations, etc.)

```sql
CREATE TABLE author_name_variants (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    author_id           UUID NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    variant_name        TEXT NOT NULL,        -- The alternative name/spelling
    normalized_variant  TEXT NOT NULL,        -- Normalized for matching
    variant_type        TEXT,                 -- e.g., "maiden_name", "transliteration", "abbreviation"
    notes               TEXT,                 -- Optional explanation

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator             TEXT NOT NULL,

    UNIQUE (author_id, normalized_variant)
);

CREATE INDEX idx_author_variants_normalized ON author_name_variants(normalized_variant);
```

### 4. publications
```sql
-- Paper types
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
    arxiv_ids           TEXT[],               -- arXiv identifiers (can have multiple, e.g., '{"2401.12345", "2312.09876"}')

    -- Core metadata
    title               TEXT NOT NULL,
    abstract            TEXT,
    paper_type          paper_type NOT NULL DEFAULT 'regular',

    -- Citation metadata
    pages               TEXT,                 -- Page range (e.g., "1:1-1:25" or "123-145")

    -- Presentation
    session_name        TEXT,                 -- Which session (e.g., "Quantum Error Correction")
    presentation_url    TEXT,                 -- Slides/presentation link
    video_url           TEXT,                 -- Video recording
    youtube_id          TEXT,                 -- YouTube video ID

    -- Awards
    award               TEXT,                 -- e.g., "Best Paper", "Best Student Paper"
    award_date          DATE,

    -- Dates
    published_date      DATE,                 -- When published in proceedings

    -- Full-text search
    search_vector       tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', title), 'A') ||
        setweight(to_tsvector('english', COALESCE(abstract, '')), 'B')
    ) STORED,

    -- Audit fields
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator             TEXT NOT NULL,
    modifier            TEXT NOT NULL,
    metadata            JSONB DEFAULT '{}'::jsonb,

);

-- Indexes
CREATE INDEX idx_publications_conference ON publications(conference_id);
CREATE INDEX idx_publications_search ON publications USING GIN(search_vector);
CREATE INDEX idx_publications_arxiv ON publications USING GIN(arxiv_ids) WHERE arxiv_ids IS NOT NULL;
CREATE INDEX idx_publications_doi ON publications(doi) WHERE doi IS NOT NULL;
CREATE INDEX idx_publications_award ON publications(award) WHERE award IS NOT NULL;
CREATE INDEX idx_publications_metadata ON publications USING GIN(metadata);
```

### 5. authorships
Links authors to publications with ordering and point-in-time affiliation.

```sql
CREATE TABLE authorships (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    publication_id      UUID NOT NULL REFERENCES publications(id) ON DELETE CASCADE,
    author_id           UUID NOT NULL REFERENCES authors(id),

    author_position     INT NOT NULL,         -- 1-indexed author order
    published_as_name   TEXT NOT NULL,        -- Name as it appeared on the paper
    affiliation         TEXT,                 -- Affiliation at time of publication
    metadata            JSONB DEFAULT '{}'::jsonb,  -- Source tracking and additional data

    -- Audit fields
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator             TEXT NOT NULL,
    modifier            TEXT NOT NULL,

    UNIQUE (publication_id, author_id),
    UNIQUE (publication_id, author_position)
);

-- Indexes
CREATE INDEX idx_authorships_author ON authorships(author_id);
CREATE INDEX idx_authorships_publication ON authorships(publication_id);
```

### 6. committee_roles
```sql
-- Committee types
CREATE TYPE committee_type AS ENUM (
    'OC',               -- Organizing Committee (General Chair, etc.)
    'PC',               -- Program Committee
    'SC',               -- Steering Committee
    'Local'             -- Local Organizers
);

-- Position/role within committee
CREATE TYPE committee_position AS ENUM (
    'chair',            -- Chair (General Chair, PC Chair, etc.)
    'co_chair',         -- Co-Chair
    'area_chair',       -- Area Chair (for large PCs)
    'member'            -- Regular member
);

CREATE TABLE committee_roles (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conference_id       UUID NOT NULL REFERENCES conferences(id),
    author_id           UUID NOT NULL REFERENCES authors(id),

    committee           committee_type NOT NULL,
    position            committee_position NOT NULL DEFAULT 'member',
    role_title          TEXT,                 -- Custom title (e.g., "Publicity Chair", "Web Chair")
    affiliation         TEXT,                 -- Affiliation at time of service

    -- For steering committee or multi-year roles
    term_start          DATE,
    term_end            DATE,
    metadata            JSONB DEFAULT '{}'::jsonb,  -- Source tracking and additional data

    -- Audit fields
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator             TEXT NOT NULL,
    modifier            TEXT NOT NULL,
    metadata            JSONB DEFAULT '{}'::jsonb,

    -- A person can have multiple roles at same conference (e.g., OC chair + PC member)
    -- but not the same role twice
    UNIQUE (conference_id, author_id, committee, position)
);

-- Indexes
CREATE INDEX idx_committee_roles_conference ON committee_roles(conference_id);
CREATE INDEX idx_committee_roles_author ON committee_roles(author_id);
CREATE INDEX idx_committee_roles_committee ON committee_roles(committee, position);
```

## Example Data

### Committee Role Examples
```sql
-- General Chair (part of Organizing Committee)
INSERT INTO committee_roles (conference_id, author_id, committee, position, role_title, creator, modifier)
VALUES ('...', '...', 'OC', 'chair', 'General Chair', 'system', 'system');

-- PC Chair
INSERT INTO committee_roles (conference_id, author_id, committee, position, role_title, creator, modifier)
VALUES ('...', '...', 'PC', 'chair', 'Program Committee Chair', 'system', 'system');

-- PC Co-Chair
INSERT INTO committee_roles (conference_id, author_id, committee, position, role_title, creator, modifier)
VALUES ('...', '...', 'PC', 'co_chair', 'Program Committee Co-Chair', 'system', 'system');

-- Area Chair
INSERT INTO committee_roles (conference_id, author_id, committee, position, role_title, creator, modifier)
VALUES ('...', '...', 'PC', 'area_chair', 'Quantum Error Correction Area Chair', 'system', 'system');

-- Regular PC member
INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
VALUES ('...', '...', 'PC', 'member', 'system', 'system');

-- Local Arrangements Chair
INSERT INTO committee_roles (conference_id, author_id, committee, position, role_title, creator, modifier)
VALUES ('...', '...', 'Local', 'chair', 'Local Arrangements Chair', 'system', 'system');

-- Steering Committee member (with term dates)
INSERT INTO committee_roles (conference_id, author_id, committee, position, term_start, term_end, creator, modifier)
VALUES ('...', '...', 'SC', 'member', '2020-01-01', '2024-12-31', 'system', 'system');
```

## Materialized Views

### Author Statistics
```sql
CREATE MATERIALIZED VIEW author_stats AS
SELECT
    a.id,
    a.full_name,
    a.family_name,
    COUNT(DISTINCT p.id) as publication_count,
    COUNT(DISTINCT cr.id) as committee_role_count,
    COUNT(DISTINCT CASE WHEN cr.position IN ('chair', 'co_chair') THEN cr.id END) as leadership_count,
    array_agg(DISTINCT c.venue ORDER BY c.venue) FILTER (WHERE c.venue IS NOT NULL) as venues,
    MIN(c.year) as first_year,
    MAX(c.year) as last_year
FROM authors a
LEFT JOIN authorships au ON a.id = au.author_id
LEFT JOIN publications p ON au.publication_id = p.id
LEFT JOIN committee_roles cr ON a.id = cr.author_id
LEFT JOIN conferences c ON (p.conference_id = c.id OR cr.conference_id = c.id)
GROUP BY a.id, a.full_name, a.family_name;

CREATE UNIQUE INDEX idx_author_stats_id ON author_stats(id);
```

### Conference Statistics
```sql
CREATE MATERIALIZED VIEW conference_stats AS
SELECT
    c.id,
    c.venue,
    c.year,
    COUNT(DISTINCT p.id) as publication_count,
    COUNT(DISTINCT CASE WHEN p.paper_type = 'regular' THEN p.id END) as regular_paper_count,
    COUNT(DISTINCT CASE WHEN p.paper_type = 'invited' THEN p.id END) as invited_talk_count,
    COUNT(DISTINCT CASE WHEN p.award IS NOT NULL THEN p.id END) as award_count,
    COUNT(DISTINCT cr.id) as committee_member_count,
    COUNT(DISTINCT a.id) as unique_author_count,
    c.submission_count,
    c.acceptance_count,
    CASE
        WHEN c.submission_count > 0 AND c.acceptance_count IS NOT NULL
        THEN ROUND((c.acceptance_count::numeric / c.submission_count::numeric) * 100, 1)
        ELSE NULL
    END as acceptance_rate
FROM conferences c
LEFT JOIN publications p ON c.id = p.conference_id
LEFT JOIN committee_roles cr ON c.id = cr.conference_id
LEFT JOIN authorships au ON p.id = au.publication_id
LEFT JOIN authors a ON au.author_id = a.id
GROUP BY c.id, c.venue, c.year, c.submission_count, c.acceptance_count;

CREATE UNIQUE INDEX idx_conference_stats_id ON conference_stats(id);
```

### Coauthor Network (for future analysis)
```sql
CREATE MATERIALIZED VIEW coauthor_pairs AS
SELECT
    a1.author_id as author1_id,
    a2.author_id as author2_id,
    COUNT(DISTINCT a1.publication_id) as collaboration_count
FROM authorships a1
JOIN authorships a2 ON a1.publication_id = a2.publication_id
    AND a1.author_id < a2.author_id  -- Avoid duplicates and self-pairs
GROUP BY a1.author_id, a2.author_id;

CREATE INDEX idx_coauthor_pairs_author1 ON coauthor_pairs(author1_id);
CREATE INDEX idx_coauthor_pairs_author2 ON coauthor_pairs(author2_id);
```

## Refresh Materialized Views

```sql
-- Run periodically or after bulk updates
REFRESH MATERIALIZED VIEW CONCURRENTLY author_stats;
REFRESH MATERIALIZED VIEW CONCURRENTLY conference_stats;
REFRESH MATERIALIZED VIEW CONCURRENTLY coauthor_pairs;
```

## Source Tracking Pattern

QuantumDB implements a **two-tier source tracking system** to maintain data provenance:

### Tier 1: Table-Level Comments
Every table has a comment storing the primary data source:
```sql
COMMENT ON TABLE conferences IS 'Source: Conference websites and archives';
COMMENT ON TABLE authorships IS 'Source: Conference proceedings and programs';
COMMENT ON TABLE committee_roles IS 'Source: Conference websites, archived pages';
```

### Tier 2: Row-Level Metadata (JSONB)
Tables `authorships` and `committee_roles` have a `metadata` JSONB field for detailed source tracking:

```json
{
  "source_type": "conference_website",
  "source_url": "https://qip2024.tw/organizers",
  "scraped_date": "2024-12-30",
  "notes": "Scraped from organizers page"
}
```

**Common `source_type` values**:
- `conference_website` - Scraped from official conference site
- `dblp` - Imported from DBLP database
- `arxiv` - Metadata from arXiv
- `orcid` - Pulled from ORCID profile
- `manual_entry` - Manually entered/curated
- `archive_org` - Retrieved from web archive

**Usage Example**:
```sql
-- Insert committee role with source tracking
INSERT INTO committee_roles (
    conference_id, author_id, committee, position, 
    affiliation, metadata, creator, modifier
) VALUES (
    '...', '...', 'PC', 'chair',
    'University of Example',
    '{"source_type": "conference_website", "source_url": "https://qip2024.tw/pc", "scraped_date": "2024-12-30"}'::jsonb,
    'scraper_bot', 'scraper_bot'
);
```

This pattern allows:
- Full data provenance tracking
- Easy identification of data quality (manual vs. automated)
- Ability to re-scrape from original sources
- Debugging data inconsistencies

## Privacy Considerations

### What We Store (Public Data)
- Conference metadata (dates, locations, URLs)
- Publication titles, abstracts, DOIs, arXiv IDs
- Author names (as published)
- Committee membership (public service record)
- ORCIDs (public identifier)
- Author websites (publicly shared by authors)
- Institutional affiliations (in published papers)

### What We Do NOT Store
- **Email addresses** - Privacy-sensitive, often outdated
- Private contact information
- Unpublished submission data
- Review scores or comments

### ORCID Note
ORCID is the recommended way to uniquely identify authors. It's:
- Public and author-controlled
- Designed for exactly this purpose
- Solves name disambiguation
- Internationally recognized

## Schema Changes from v1

1. **Privacy**: Removed email field from authors table
2. **Authors**: Added family_name/given_name for proper sorting
3. **Authors**: Added ORCID validation constraint
4. **Publications**: Added arxiv_ids as TEXT[] array (supports multiple arXiv references per paper)
5. **Publications**: Added pages for BibTeX generation
6. **Publications**: Added paper_type enum (regular/short/poster/invited/tutorial/keynote)
7. **Publications**: Added session_name for conference organization
8. **Conferences**: Added proceedings_publisher, proceedings_volume, proceedings_doi (all optional - only TQC has proceedings)
9. **Committee Roles**: Added 'OC' committee type and 'area_chair' position
10. **Author Name Variants**: New table for tracking name changes/spellings
11. **Fixed**: Pure PostgreSQL syntax (removed MySQL artifacts)
12. **Added**: Coauthor network materialized view
