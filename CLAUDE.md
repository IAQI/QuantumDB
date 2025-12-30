# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QuantumDB is a REST API service for tracking quantum computing conferences (QIP, QCrypt, TQC), built with Rust and PostgreSQL. The system tracks conferences, publications, authors, and committee memberships.

**Current Status**: All core CRUD operations implemented. Fully modular architecture with complete REST API, Swagger UI, name normalization utilities, archive URL tracking, and source metadata system. Ready for data population and production deployment.

## Technology Stack

- **Backend**: Rust with Axum web framework, Tokio async runtime
- **Database**: PostgreSQL 15+ with SQLx (type-safe, compile-time verified queries)
- **API Documentation**: OpenAPI/Swagger via utoipa (interactive UI at `/swagger-ui/`)
- **Containerization**: Docker + Docker Compose
- **Key Dependencies**: serde, uuid, chrono, tracing, utoipa, unicode-normalization

## Essential Commands

### Development
```bash
# Start development server with auto-reload
cargo watch -x run

# Build and run
cargo build
cargo run

# Production build
cargo build --release
```

### Database
```bash
# Create database (first time only)
createdb quantumdb

# Run migrations (structural changes)
sqlx migrate run

# Run seed data (after migrations)
psql quantumdb < seeds/insert_qip_conferences.sql
psql quantumdb < seeds/insert_qcrypt_conferences.sql
psql quantumdb < seeds/insert_tqc_conferences.sql

# Create new migration
sqlx migrate add <migration_name>

# Prepare SQLx offline mode (required before Docker build)
cargo sqlx prepare

# Refresh materialized views (after bulk data changes)
psql quantumdb -c "REFRESH MATERIALIZED VIEW CONCURRENTLY author_stats;"
psql quantumdb -c "REFRESH MATERIALIZED VIEW CONCURRENTLY conference_stats;"
psql quantumdb -c "REFRESH MATERIALIZED VIEW CONCURRENTLY coauthor_pairs;"
```

### Testing
```bash
# Run all tests
cargo test

# Run specific test
cargo test <test_name>

# Run with logging
RUST_LOG=debug cargo test
```

### Docker
```bash
# Build and start all services (app + PostgreSQL + PgAdmin)
docker-compose up --build

# Start in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Access PgAdmin: http://localhost:5050
# - Email: admin@example.com
# - Password: quantumdb
```

### Code Quality
```bash
# Format code
cargo fmt

# Lint
cargo clippy

# Check without building
cargo check
```

## Architecture

### Current Project Structure

**Fully modular implementation** in `src/`:

```
src/
├── main.rs              # Application entry point, router setup, Swagger config
├── lib.rs               # Library exports
├── models/              # Database models (implemented)
│   ├── mod.rs
│   ├── conference.rs    # Conference, CreateConference, UpdateConference
│   ├── author.rs        # Author, CreateAuthor, UpdateAuthor
│   ├── publication.rs   # Publication, CreatePublication, UpdatePublication
│   └── committee.rs     # CommitteeRole, CreateCommitteeRole, UpdateCommitteeRole
├── handlers/            # API request handlers (implemented)
│   ├── mod.rs
│   ├── conferences.rs   # Full CRUD for conferences
│   ├── authors.rs       # Full CRUD for authors
│   ├── publications.rs  # Full CRUD for publications
│   ├── authorships.rs   # Full CRUD for authorships
│   └── committees.rs    # Full CRUD for committee roles
└── utils/               # Shared utilities (implemented)
    ├── mod.rs
    ├── normalize.rs     # Unicode normalization, name similarity, loose matching
    └── conference.rs    # Conference slug parsing (e.g., "QIP2024")
```

### Key Utilities

**Name Normalization** (`src/utils/normalize.rs`, 405 lines):
- `normalize_name()` - Unicode NFKD normalization, strip accents, lowercase
- `normalize_for_loose_match()` - Aggressive normalization for fuzzy matching
- `names_similar()` - Similarity scoring between names
- `generate_name_variants()` - Automatic generation of common name variations
- Used for author search, deduplication, name variant generation

**Conference Slug Utils** (`src/utils/conference.rs`):
- `parse_conference_slug()` - Extract venue and year from "QIP2024"
- `make_conference_slug()` - Generate slug from conference data
- `slug()` method on Conference struct

### Database Schema

**Core tables** (see DATABASE_SCHEMA.md for full details):

- **conferences** - QIP, QCrypt, TQC conference instances with location, dates, proceedings metadata, **archive URLs** (archive_url, archive_organizers_url, archive_pc_url, archive_steering_url, archive_program_url for static website backups)
- **authors** - Unique individuals with name fields (full_name, family_name, given_name), ORCID, no email (privacy)
- **author_name_variants** - Track name changes, transliterations, abbreviations
- **publications** - Papers/talks with arxiv_ids (array), paper_type enum, full-text search
- **authorships** - Links authors to publications with position, point-in-time affiliation, **JSONB metadata field** for source tracking
- **committee_roles** - Committee membership (OC/PC/SC/Local) with position (chair/co_chair/area_chair/member), **affiliation field**, **JSONB metadata field** for source tracking

**Source Tracking Pattern** (migration 20251230100001):
- Two-tier tracking: table-level comments store primary source, row-level metadata JSONB stores detailed source info
- metadata JSONB structure: `{"source_type": "conference_website", "source_url": "...", "scraped_date": "...", "notes": "..."}`
- Common source_type values: "conference_website", "dblp", "arxiv", "manual_entry", "orcid"

**Materialized views** (refresh after bulk updates):
- **author_stats** - Publication counts, committee roles, venues
- **conference_stats** - Paper counts, acceptance rates
- **coauthor_pairs** - Collaboration network

### API Endpoints

**All CRUD operations fully implemented** for all entities. See interactive API documentation at `/swagger-ui/` for complete request/response schemas and live testing.

**Conferences**:
- `GET /` - Health check
- `GET /conferences` - List all conferences
- `GET /conferences/:id` - Get conference by ID
- `POST /conferences` - Create conference
- `PUT /conferences/:id` - Update conference
- `DELETE /conferences/:id` - Delete conference

**Authors**:
- `GET /authors` - List all authors
- `GET /authors/:id` - Get author by ID
- `POST /authors` - Create author
- `PUT /authors/:id` - Update author
- `DELETE /authors/:id` - Delete author

**Publications**:
- `GET /publications` - List all publications
- `GET /publications/:id` - Get publication by ID
- `POST /publications` - Create publication
- `PUT /publications/:id` - Update publication
- `DELETE /publications/:id` - Delete publication

**Authorships**:
- `GET /authorships` - List all authorships
- `GET /authorships/:id` - Get authorship by ID
- `POST /authorships` - Create authorship
- `PUT /authorships/:id` - Update authorship
- `DELETE /authorships/:id` - Delete authorship

**Committee Roles**:
- `GET /committees` - List all committee roles
- `GET /committees/:id` - Get committee role by ID
- `POST /committees` - Create committee role
- `PUT /committees/:id` - Update committee role
- `DELETE /committees/:id` - Delete committee role

**API Documentation**:
- `GET /swagger-ui/` - Interactive Swagger UI
- `GET /api-docs/openapi.json` - OpenAPI 3.0 specification

## Critical Implementation Details

### SQLx Offline Mode

SQLx requires database connection at compile time for query verification. For Docker builds:

1. **During development**: Ensure `.env` has `DATABASE_URL` pointing to running PostgreSQL
2. **Before Docker build**: Run `cargo sqlx prepare` to generate `.sqlx/` metadata
3. **In Dockerfile**: `ENV SQLX_OFFLINE=true` enables builds without database connection

### Conference Venue Validation

The `venue` field has a CHECK constraint enforcing only three values:
- 'QIP' (Quantum Information Processing)
- 'QCRYPT' (Annual Conference on Quantum Cryptography)
- 'TQC' (Theory of Quantum Computation)

API requests with other values will fail at the database level.

### Database Connection

Environment variable `DATABASE_URL` must be set:
```bash
# Development
DATABASE_URL=postgres://username:password@localhost/quantumdb

# Docker Compose (automatic)
DATABASE_URL=postgres://quantumdb:quantumdb@db:5432/quantumdb
```

### Error Handling Pattern

Handlers return `(StatusCode, Json<T>)` tuples:
- Success → `(StatusCode::OK, Json(data))` or `(StatusCode::CREATED, Json(data))`
- Database errors → `(StatusCode::INTERNAL_SERVER_ERROR, Json(error_message))`
- Not found → `(StatusCode::NOT_FOUND, Json(error_message))`
- Validation errors → `(StatusCode::BAD_REQUEST, Json(error_message))`

All handlers use SQLx query macros (`query!`, `query_as!`) for compile-time verification and type safety.

## Key Files

- **src/main.rs** - Application entry point, router setup, Swagger configuration
- **src/lib.rs** - Library exports for models, handlers, utils
- **src/models/** - All database models (Conference, Author, Publication, CommitteeRole, etc.)
- **src/handlers/** - All API request handlers with full CRUD operations
- **src/utils/** - Name normalization (405 lines), conference slug parsing
- **tests/api_tests.rs** - Comprehensive test suite (1155 lines) covering all CRUD operations
- **migrations/** - Database schema migrations (SQLx format, run in order)
  - `20251228160000_create_conferences_table.sql`
  - `20251228160001_create_authors_table.sql`
  - `20251228160002_create_author_name_variants.sql`
  - `20251228160003_create_publications_table.sql`
  - `20251228160004_create_authorships_table.sql`
  - `20251228160005_create_committee_roles_table.sql`
  - `20251228160006_create_materialized_views.sql`
  - `20251228200000_insert_2024_committee_data.sql`
  - `20251230000000_add_archive_urls.sql`
  - `20251230100000_add_affiliation_and_metadata.sql`
  - `20251230100001_add_source_tracking_comments.sql`
- **seeds/** - Initial data (run manually after migrations)
  - `insert_qip_conferences.sql` - Historical QIP data (1998-2024)
  - `insert_qcrypt_conferences.sql` - Historical QCrypt data
  - `insert_tqc_conferences.sql` - Historical TQC data
  - `z_insert_2024_committee_data.sql` - Committee role examples
- **Cargo.toml** - Dependencies and project configuration
- **Dockerfile** - Multi-stage build for production deployment
- **docker-compose.yml** - Development environment (app + DB + PgAdmin)

## Documentation Files

- **README.md** - User-facing overview, getting started guide
- **ARCHITECTURE.md** - System design, modular structure, API patterns
- **DATABASE_SCHEMA.md** - Complete database schema with all tables and fields
- **TESTING.md** - Test suite documentation, how to run tests
- **docs/archive/** - Historical planning documents

## Development Workflow

1. **Environment Setup**: Ensure PostgreSQL running, `.env` configured with `DATABASE_URL`
2. **Database Setup**: Create DB, run migrations, optionally run seed data
3. **Development**: Use `cargo watch -x run` for auto-reload, access Swagger UI at `http://localhost:3000/swagger-ui/`
4. **Database Changes**: Create migration, run it, update `cargo sqlx prepare` for offline mode
5. **Testing**: Write tests in `tests/api_tests.rs`, run with `cargo test` (uses isolated test databases)
6. **Docker Build**: Prepare SQLx metadata first, then `docker-compose up --build`

## Current Development Priorities

1. **Data Population**: Populate database with historical conference data, publications, authors, and committee roles
2. **Search & Analytics**: Add search endpoints (author search, publication search), implement analytics based on materialized views
3. **Data Import Tools**: Build tools to scrape/import data from conference websites, DBLP, arXiv
4. **Export Features**: Add BibTeX, CSV export functionality
5. **Production Deployment**: Deploy to production environment with monitoring

## Code Patterns & Best Practices

When extending the codebase:

1. **Use existing utilities**:
   - `normalize_name()` for author name processing
   - `parse_conference_slug()` for conference identification
   - `names_similar()` for fuzzy matching

2. **Follow established patterns**:
   - SQLx `query!` and `query_as!` macros for type safety
   - UUID primary keys via `gen_random_uuid()`
   - `created_at`/`updated_at`/`created_by`/`updated_by` audit fields
   - JSONB `metadata` for extensible data (use for source tracking)
   - `Extension(Pool<Postgres>)` for database access in handlers
   - OpenAPI annotations with `#[utoipa::path(...)]` for new endpoints

3. **Database changes**:
   - Update `.sqlx/` metadata with `cargo sqlx prepare` after query changes
   - Refresh materialized views after bulk data changes
   - Use CHECK constraints for enum-like fields (e.g., `venue` on conferences)

4. **Testing**:
   - Add tests to `tests/api_tests.rs` for new endpoints
   - Tests use isolated databases for parallel execution
   - Test full CRUD lifecycle for each entity
