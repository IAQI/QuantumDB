# QuantumDB

A REST API service for tracking quantum computing conferences (QIP, QCrypt, TQC), built with Rust and PostgreSQL.

## Overview

QuantumDB provides a comprehensive system for tracking:
- Conference events and their details
- Publications and presentations
- Author profiles and contributions
- Committee memberships and roles
- Video recordings and presentation materials

## Documentation

- [Architecture](ARCHITECTURE.md) - System design and technical stack
- [Database Schema](DATABASE_SCHEMA.md) - Detailed database structure
- [Features](FEATURES.md) - Complete feature list and requirements
- [Rust Implementation Guide](RUST_GUIDE.md) - Development and deployment guide

## Technology Stack

- **Backend:**
  - Rust with Axum web framework
  - PostgreSQL database
  - Full-text search
  - REST API with pagination

## Key Features

### Conference Management
- Track conference details (dates, locations, URLs)
- Monitor submission and acceptance statistics
- Store proceedings and website links

### Publication Tracking
- Full paper metadata
- Author affiliations
- Presentation materials
- Video recordings
- DOI integration

### Author Profiles
- Publication history
- Committee service records
- ORCID integration
- Affiliation tracking

### Committee Management
- Program Committee tracking
- Steering Committee records
- Local organizer information
- Historical service records

## Getting Started

1. **Prerequisites**
   ```bash
   # Install Rust
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   
   # Install PostgreSQL
   brew install postgresql@15
   
   # Install development tools
   cargo install sqlx-cli cargo-watch cargo-audit
   ```

2. **Database Setup**
   ```bash
   # Start PostgreSQL
   brew services start postgresql@15
   
   # Create database
   createdb quantumdb
   
   # Run migrations
   sqlx migrate run
   ```

3. **Run the Application**
   ```bash
   # Development mode
   cargo watch -x run
   
   # Production mode
   cargo run --release
   ```

## API Documentation

The API provides the following main endpoints:

```
/api/v1/conferences    # Conference management
/api/v1/publications   # Publication tracking
/api/v1/authors       # Author profiles
/api/v1/committees    # Committee management
```

Each endpoint supports:
- Pagination
- Full-text search
- Filtering
- Sorting

For detailed API documentation, run the server and visit `/api/docs`.
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    venue conference_venue NOT NULL,
    year INTEGER NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    location TEXT NOT NULL,
    website_url TEXT,
    proceedings_url TEXT,
    submission_count INTEGER,
    acceptance_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb,
    UNIQUE (venue, year)
);

-- Publications table
CREATE TABLE publications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conference_event_id UUID NOT NULL REFERENCES conference_events(id),
    title TEXT NOT NULL,
    abstract TEXT,
    paper_type TEXT NOT NULL DEFAULT 'regular',  -- regular, invited, tutorial, etc.
    presentation_url TEXT,
    video_url TEXT,
    doi TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', title), 'A') ||
        setweight(to_tsvector('english', COALESCE(abstract, '')), 'B')
    ) STORED
);

-- Authors table
CREATE TABLE authors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name TEXT NOT NULL,
    orcid TEXT UNIQUE,
    email TEXT UNIQUE,
    webpage_url TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Authorships table
CREATE TABLE authorships (
    publication_id UUID REFERENCES publications(id),
    author_id UUID REFERENCES authors(id),
    position INTEGER NOT NULL,
    affiliation TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (publication_id, author_id)
);

-- Committee roles table
CREATE TABLE committee_roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conference_event_id UUID NOT NULL REFERENCES conference_events(id),
    author_id UUID NOT NULL REFERENCES authors(id),
    role committee_role NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (conference_event_id, author_id, role)
);

-- Enums
CREATE TYPE conference_venue AS ENUM ('qip', 'qcrypt', 'tqc');
CREATE TYPE committee_role AS ENUM ('pc', 'sc', 'chair', 'local');
```

### Indexes and Performance Optimizations

```sql
-- Full-text search
CREATE INDEX publications_search_idx ON publications USING GIN(search_vector);

-- Foreign keys and common queries
CREATE INDEX publications_conference_idx ON publications(conference_event_id);
CREATE INDEX committee_roles_conference_idx ON committee_roles(conference_event_id);
CREATE INDEX authorships_publication_idx ON authorships(publication_id);
CREATE INDEX authorships_author_idx ON authorships(author_id);

-- JSON queries
CREATE INDEX publications_metadata_idx ON publications USING GIN(metadata);
CREATE INDEX conference_events_metadata_idx ON conference_events USING GIN(metadata);

-- Common queries
CREATE INDEX conference_events_year_venue_idx ON conference_events(year, venue);
```

### Materialized Views

```sql
-- Author statistics
CREATE MATERIALIZED VIEW author_stats AS
SELECT 
    a.id,
    a.full_name,
    COUNT(DISTINCT p.id) as publication_count,
    COUNT(DISTINCT cr.id) as committee_roles_count,
    array_agg(DISTINCT ce.venue) as venues,
    array_agg(DISTINCT ce.year) as years
FROM authors a
LEFT JOIN authorships au ON a.id = au.author_id
LEFT JOIN publications p ON au.publication_id = p.id
LEFT JOIN committee_roles cr ON a.id = cr.author_id
LEFT JOIN conference_events ce ON 
    (p.conference_event_id = ce.id OR cr.conference_event_id = ce.id)
GROUP BY a.id, a.full_name;

-- Conference statistics
CREATE MATERIALIZED VIEW conference_stats AS
SELECT 
    ce.id,
    ce.venue,
    ce.year,
    COUNT(DISTINCT p.id) as publication_count,
    COUNT(DISTINCT cr.id) as committee_count,
    COUNT(DISTINCT a.id) as unique_authors,
    ce.submission_count,
    ce.acceptance_count,
    CASE 
        WHEN ce.submission_count > 0 
        THEN ROUND((ce.acceptance_count::float / ce.submission_count::float) * 100, 2)
        ELSE NULL
    END as acceptance_rate
FROM conference_events ce
LEFT JOIN publications p ON ce.id = p.conference_event_id
LEFT JOIN committee_roles cr ON ce.id = cr.conference_event_id
LEFT JOIN authorships au ON p.id = au.publication_id
LEFT JOIN authors a ON au.author_id = a.id
GROUP BY ce.id, ce.venue, ce.year;
```

## API Implementation

See [RUST_GUIDE.md](RUST_GUIDE.md) for detailed API implementation with pagination and search functionality.

## Deployment

See [POSTGRES_GUIDE.md](POSTGRES_GUIDE.md) for deployment configuration on Jelastic Cloud.

## Development Workflow

1. **Local Development**
   ```bash
   # Install Rust
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   
   # Install PostgreSQL
   brew install postgresql@15
   
   # Setup local database
   createdb quantumdb
   ```

## Development

See [RUST_GUIDE.md](RUST_GUIDE.md) for detailed development instructions, including:
- Project setup
- Database migrations
- Testing
- Deployment

## Database Schema

See [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) for the complete database structure, including:
- Table definitions
- Relationships
- Indexes
- Materialized views

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details
