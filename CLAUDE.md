# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QuantumDB is a REST API service for tracking quantum computing conferences (QIP, QCrypt, TQC), built with Rust and PostgreSQL. The system tracks conferences, publications, authors, and committee memberships.

**Current Status**: All core CRUD operations implemented. Fully modular architecture with complete REST API (versioned at `/api/v1/`), Swagger UI, name normalization utilities, archive URL tracking, source metadata system, input validation, per-IP rate limiting, CORS, and security headers. Ready for data population and production deployment.

**Development environment**: The runtime stack (`app`, `db`, `pgadmin`) runs in Docker via `docker compose`. The runtime image is intentionally cargo-less — Rust builds happen in the builder stage and only the compiled binary lands in the runtime image. So:

- **Database / SQL operations** → run inside the DB container (`docker exec quantumdb-db-1 psql ...`).
- **Rust builds, `cargo check`, `cargo test`, `cargo sqlx prepare`** → run on the host (the host has the toolchain; the runtime container does not).
- **Application reload** → `docker compose up -d --build app` rebuilds inside Docker and replaces the running container.

## Technology Stack

- **Backend**: Rust with Axum web framework, Tokio async runtime
- **Database**: PostgreSQL 15+ with SQLx (type-safe, compile-time verified queries)
- **API Documentation**: OpenAPI/Swagger via utoipa (interactive UI at `/api/v1/swagger-ui/`)
- **Containerization**: Docker + Docker Compose (the canonical dev/run environment)
- **Key Dependencies**: serde, uuid, chrono, tracing, utoipa, unicode-normalization, subtle (constant-time comparison), tower_governor (rate limiting), tower-http (cors + security headers)

## Essential Commands

Container names: `quantumdb-app-1`, `quantumdb-db-1`, `quantumdb-pgadmin-1`. The DB's `migrations/` and `seeds/` directories are bind-mounted, so adding a file on the host makes it visible inside the container immediately.

### Stack lifecycle (Docker)
```bash
# Build and start all services
docker compose up --build

# Start in background
docker compose up -d

# Rebuild + restart only the app (after Rust code changes)
docker compose up -d --build app

# View logs (follow)
docker compose logs -f app

# Stop services (preserves the DB volume)
docker compose down

# Stop and wipe DB volume (re-runs migrations + seeds on next `up`)
docker compose down -v
```

### Database / SQL (via the running DB container)
```bash
# Open a psql shell against the dev DB
docker exec -it quantumdb-db-1 psql -U quantumdb -d quantumdb

# Apply a new migration manually (only needed for an already-initialised DB —
# fresh DBs run all migrations via docker-init.sh)
docker exec quantumdb-db-1 psql -U quantumdb -d quantumdb -v ON_ERROR_STOP=1 \
    -f /migrations/<NEW_MIGRATION_FILE>.sql

# Refresh materialized views (CONCURRENTLY, since every view has a unique index)
docker exec quantumdb-db-1 psql -U quantumdb -d quantumdb -c \
    "REFRESH MATERIALIZED VIEW CONCURRENTLY author_stats;
     REFRESH MATERIALIZED VIEW CONCURRENTLY conference_stats;
     REFRESH MATERIALIZED VIEW CONCURRENTLY coauthor_pairs;"

# Access PgAdmin: http://localhost:5050  (admin@example.com / quantumdb)
```

### Rust (host toolchain — runtime image has no cargo)
```bash
# Fast feedback loop (no rebuild required)
cargo check
cargo clippy
cargo fmt

# Lib tests — no DB needed
cargo test --lib

# Integration tests — point DATABASE_URL at the dockerised DB
DATABASE_URL=postgres://quantumdb:quantumdb@localhost:5432/quantumdb cargo test

# After changing any SQLx query string, regenerate the .sqlx/ metadata
DATABASE_URL=postgres://quantumdb:quantumdb@localhost:5432/quantumdb cargo sqlx prepare

# Scaffold a new migration file
sqlx migrate add <migration_name>

# Once host code is satisfied, rebuild the image and replace the container:
docker compose up -d --build app
```

### Authentication
```bash
# Generate API token
./tools/generate_token.sh

# Add token to .env file (gitignored). Restart the app container to pick it up:
echo "API_TOKENS=your-token-here" >> .env
docker compose up -d --force-recreate app

# Use token with API (note the /api/v1 prefix)
curl -H "Authorization: Bearer YOUR_TOKEN" \
  -X POST http://localhost:3000/api/v1/conferences \
  -H "Content-Type: application/json" \
  -d '{"venue": "QIP", "year": 2026, "creator": "you", "modifier": "you"}'
```

Tokens are opaque shared secrets: any character set is accepted as long as the token is at least 32 characters. Comparison is constant-time (`subtle` crate) and runs against every configured token regardless of match position.

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
│   ├── committees.rs    # Full CRUD for committee roles
│   └── web/             # Web interface handlers (implemented)
│       ├── mod.rs
│       ├── home.rs      # Homepage
│       ├── about.rs     # About page with IAQI branding
│       ├── authors.rs   # Author list and detail pages
│       ├── conferences.rs # Conference list and detail pages
│       └── admin.rs     # Admin utilities (stats refresh)
├── middleware/          # Request middleware (implemented)
│   ├── mod.rs
│   └── auth.rs          # JWT-based Bearer token authentication
└── utils/               # Shared utilities (implemented)
    ├── mod.rs
    ├── normalize.rs     # Unicode normalization, name similarity, loose matching
    ├── conference.rs    # Conference slug parsing (e.g., "QIP2024")
    ├── pagination.rs    # clamp_pagination() — bounds limit/offset (default 100, max 1000)
    └── validation.rs    # URL scheme + length + JSONB metadata validators
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

**Pagination** (`src/utils/pagination.rs`):
- `clamp_pagination(limit, offset)` - Clamp client-supplied paging args to safe ranges
- Defaults: `limit = 100`, max `limit = 1000`; negative values are coerced
- Used by every list handler (`list_authors`, `list_publications`, `list_committee_roles`)

**Input validation** (`src/utils/validation.rs`):
- `validate_url(s)` / `validate_optional_url(s)` - Reject anything that isn't `http(s)://...` (case-insensitive); 2 KB length cap. Prevents `javascript:` / `data:` / `file:` URIs from reaching `<a href>` rendering.
- `validate_text_len(s, max)` / `validate_optional_text_len` - Generic per-field length cap. Constants: `MAX_NAME_LEN = 255`, `MAX_TITLE_LEN = 1000`, `MAX_ABSTRACT_LEN = 50_000`.
- `validate_metadata(opt_value)` - Requires JSONB metadata to be an object (not array/scalar) and ≤ 4 KB serialised.
- All validators return `Err(StatusCode::BAD_REQUEST)` so handlers can `?`-propagate.

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

**All CRUD operations fully implemented** for all entities. The REST API is mounted under `/api/v1/` (versioned). Read endpoints (`GET`) are public; write endpoints (`POST`, `PUT`, `DELETE`) require a Bearer token. Interactive API documentation at `/api/v1/swagger-ui/`.

**Conferences** (`/api/v1/conferences`):
- `GET /api/v1/conferences` - List all conferences
- `GET /api/v1/conferences/:id` - Get conference by ID
- `POST /api/v1/conferences` - Create conference (auth)
- `PUT /api/v1/conferences/:id` - Update conference (auth)
- `DELETE /api/v1/conferences/:id` - Delete conference (auth)

**Authors** (`/api/v1/authors`):
- `GET /api/v1/authors` - List all authors (paginated)
- `GET /api/v1/authors/:id` - Get author by ID
- `POST /api/v1/authors` - Create author (auth)
- `PUT /api/v1/authors/:id` - Update author (auth)
- `DELETE /api/v1/authors/:id` - Delete author (auth)

**Publications** (`/api/v1/publications`):
- `GET /api/v1/publications` - List all publications (paginated, searchable, filterable)
- `GET /api/v1/publications/:id` - Get publication by ID
- `POST /api/v1/publications` - Create publication (auth)
- `PUT /api/v1/publications/:id` - Update publication (auth)
- `DELETE /api/v1/publications/:id` - Delete publication (auth)

**Authorships** (`/api/v1/authorships`): full CRUD; `POST` and `PUT` may return **409 Conflict** when `(publication_id, author_position)` already exists for the publication.

**Committee Roles** (`/api/v1/committees`): full CRUD with auth on writes.

**Web Interface** (HTML pages, server-rendered, unversioned):
- `GET /` - Homepage
- `GET /about` - About page (IAQI branding)
- `GET /authors`, `GET /authors/:id` - Author list / detail
- `GET /conferences`, `GET /conferences/:slug` - Conference list / detail
- `GET /static/*` - Static assets
- `GET /health` - Health check (used by Dockerfile HEALTHCHECK)

**Admin Routes** (Bearer token required):
- `GET /admin/refresh-stats` - Refresh all materialized views (uses `REFRESH MATERIALIZED VIEW CONCURRENTLY`)

**API Documentation**:
- `GET /api/v1/swagger-ui/` - Interactive Swagger UI
- `GET /api/v1/openapi.json` - OpenAPI 3.0 specification

## Critical Implementation Details

### Security & Middleware Stack

The router applies (outermost → innermost):

1. **Security headers** (`tower_http::set_header`) — every response gets `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, and a restrictive `Permissions-Policy`. Applied with `if_not_present` so handlers can override.
2. **CORS** (`tower_http::cors`) — currently `Any` origin with `GET/POST/PUT/DELETE` and `Authorization`/`Content-Type` headers. Tighten the origin list before any non-trivial public deployment.
3. **Rate limiting** (`tower_governor`) — keyed on peer IP; 10 req/sec sustained (period = 100 ms) with burst size 100. Adds `x-ratelimit-*` response headers via `use_headers()`. A background tokio task calls `retain_recent()` every 60 s to bound memory. Required `axum::serve(_, app.into_make_service_with_connect_info::<SocketAddr>())` so the layer can extract IPs.
4. **Auth** (`src/middleware/auth.rs`) — applied only to the protected sub-router. Bearer-token check is constant-time via `subtle::ConstantTimeEq`; the loop iterates every configured token unconditionally. Tokens must be ≥ 32 chars; the body is opaque (any character set).

When adding a new write endpoint, register it on `protected_api_routes` (or `protected_web_routes` for HTML admin) so it inherits `auth_middleware`. **Do not register write handlers on the public router** — the empty `protected_web_routes` was the root cause of the original `/admin/refresh-stats` exposure.

### Input Validation

All `Create*` / `Update*` handlers validate inputs *before* hitting the DB:
- Strings are length-capped (see `MAX_NAME_LEN` etc. in `src/utils/validation.rs`).
- URL fields are scheme-checked (`http`/`https` only) — protects against `javascript:` URIs surviving Askama HTML-attribute escaping.
- JSONB `metadata` must be a JSON object ≤ 4 KB.
- Pagination `limit`/`offset` are clamped via `clamp_pagination()` in list handlers.

When adding a new field, decide which of these caps applies and call the corresponding validator at the top of the handler.

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

### Paper Types

The `paper_type` enum has 8 values representing different publication/talk types as they appear in conference programs (not the selection mechanism):

- `regular` - Standard contributed talk (use for both historical single-track conferences and modern parallel-session contributed talks)
- `poster` - Poster presentation
- `invited` - Invited speaker
- `tutorial` - Tutorial session
- `keynote` - Keynote address
- `plenary` - Contributed plenary talk (use only for modern parallel-track era prestigious talks)
- `plenary_short` - Short plenary at QIP (~15 min)
- `plenary_long` - Long plenary at QIP (~25+ min)

**Note:** The `short` type was removed (as of migration 20260101000000) in favor of using `duration_minutes` to track talk length.

**Usage Conventions:**
- For historical single-track conferences (where all talks were effectively plenary format), use `regular` for contributed talks
- Use `plenary` types only for prestigious talks in the modern parallel-track era (roughly 2010s onward)
- These types represent what appears in conference programs. Selection mechanisms (e.g., SC-invited vs PC-reviewed) may evolve over time and are not explicitly tracked.

### Presenter Tracking

Publications can specify who presented the talk via `presenter_author_id`:
- Must be one of the authors in the `authorships` table
- Validated by database trigger `ensure_presenter_is_author`
- Optional field (nullable) - often unknown for contributed talks
- May be inferred later from videos, slides, or other sources
- For rare cases where presenter is not an author, leave `presenter_author_id` as NULL and store presenter information in the `metadata` JSONB field (e.g., `{"presenter_name": "...", "presenter_note": "..."}`)

### Proceedings vs Workshop Tracks

The `is_proceedings_track` boolean distinguishes formal proceedings publications:
- **TQC**: Has both proceedings track (LIPIcs) and workshop track
- **QIP/QCrypt**: All workshop-style (`is_proceedings_track = FALSE`)
- Affects citation format and archival status
- Defaults to `FALSE` for backward compatibility

### Talk Scheduling

Publications can track when and how long talks occurred:
- `talk_date` (DATE) - Date when the talk was given (if known). Useful for multi-day conferences
- `talk_time` (TIME) - Start time of the talk (if known). Useful for detailed schedule tracking  
- `duration_minutes` (INTEGER) - Talk duration in minutes (if known). Replaces the need for a 'short' paper type
- All three fields are optional (nullable) - populate when data is available from conference programs or videos
- Duration constraint: `duration_minutes >= 0` if provided

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
  - `20260101000000_add_talk_presenter_and_types.sql` - Removes 'short' paper type, adds plenary types, presenter tracking, proceedings track flag, and talk scheduling fields
  - `20260505000000_coauthor_pairs_unique_index.sql` - Adds UNIQUE INDEX on `coauthor_pairs(author1_id, author2_id)` so the view can be refreshed with `REFRESH MATERIALIZED VIEW CONCURRENTLY`
  - `20260505000001_authors_orcid_unique.sql` - Promotes the partial ORCID index to a UNIQUE constraint (`authors_orcid_unique`) and drops the redundant `idx_authors_orcid`
- **seeds/** - Initial data (run manually after migrations)
  - `insert_qip_conferences.sql` - Historical QIP data (1998-2024)
  - `insert_qcrypt_conferences.sql` - Historical QCrypt data
  - `insert_tqc_conferences.sql` - Historical TQC data
  - `z_insert_2024_committee_data.sql` - Committee role examples
- **Cargo.toml** - Dependencies and project configuration
- **Dockerfile** - Multi-stage build for production deployment
- **docker-compose.yml** - Development environment (app + DB + PgAdmin)
- **.env** - Environment variables (DATABASE_URL, API_TOKENS) - gitignored
- **templates/** - HTML templates for web interface (Askama)
- **static/** - Static assets (images, CSS, JS)
- **data/conferences/** - Source-of-truth CSVs per conference (`<venue>_<year>/{committees,talks,proceedings,workshop}.csv`). Edit these to fix data; importer scripts read from here. See `data/README.md` for schemas.
- **data/SOURCES.md** - Per-conference provenance (which page each CSV was scraped from).
- **tools/scrapers/** - Unified scrape + import package; subcommand CLIs `scrape_to_csv.py {committees|talks}` and `import_from_csv.py {committees|talks}`. Venue scrapers under `committees/` and `talks/` subpackages.
- **tools/one_off/** - Archived historical/monolithic scrapers and one-off conversion projects (QIP 2026, TQC 2023-24, TQC LIPIcs).
- **tools/generate_token.sh** - Secure token generation utility

## Documentation Files

- **README.md** - User-facing overview, getting started guide
- **ARCHITECTURE.md** - System design, modular structure, API patterns
- **DATABASE_SCHEMA.md** - Complete database schema with all tables and fields
- **TESTING.md** - Test suite documentation, how to run tests
- **docs/CODE_REVIEW.md** - Comprehensive security + code-quality review with findings, severities, and fixes
- **docs/archive/** - Historical planning documents

## Development Workflow

Hybrid: stack runs in Docker, Rust toolchain runs on the host.

1. **Bring the stack up**: `docker compose up -d` (rebuilds only on `--build`). The DB volume persists across restarts; on first start, `docker-init.sh` runs every file in `migrations/` and `seeds/` in order.
2. **Apply a new migration**: drop the `<timestamp>_<name>.sql` file into `migrations/`. For an existing DB, run it manually with `docker exec quantumdb-db-1 psql -U quantumdb -d quantumdb -v ON_ERROR_STOP=1 -f /migrations/<file>.sql`. (For a fresh DB, `docker compose down -v && docker compose up -d` re-runs everything.)
3. **Iterate on code**: edit on the host. `cargo check` / `cargo clippy` / `cargo test --lib` give fast feedback locally; once you're ready to exercise the running app, `docker compose up -d --build app` rebuilds the image and swaps the container.
4. **After SQL query changes**: run `cargo sqlx prepare` (host) to regenerate `.sqlx/`. Commit the result; the Dockerfile builds with `SQLX_OFFLINE=true` and reads from this directory.
5. **Test**: `cargo test --lib` for unit tests; `cargo test` (with `DATABASE_URL` pointing at `localhost:5432`) for the integration suite — it talks to the dockerised DB. Tests share the dev DB but use unique year ranges (`unique_test_year()` starts at 5000) to avoid colliding with seeded data.
6. **Refresh stats**: hit the auth-protected `GET /admin/refresh-stats`, or run the SQL directly via `docker exec quantumdb-db-1 psql ...`.
7. **Swagger UI**: <http://localhost:3000/api/v1/swagger-ui/>

## Current Development Priorities

1. **Data Population**: Populate database with historical conference data, publications, authors, and committee roles. Source-of-truth CSVs live under `data/conferences/<venue>_<year>/`; scrape and import via `tools/scrapers/{scrape_to_csv,import_from_csv}.py` with a `committees | talks` subcommand.
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
   - `clamp_pagination()` for any new list endpoint (don't roll your own `unwrap_or(100)`)
   - `validate_url`, `validate_text_len`, `validate_metadata` at the top of any new `Create*`/`Update*` handler

2. **Follow established patterns**:
   - SQLx `query!` and `query_as!` macros for type safety (compile-time-checked against `.sqlx/`)
   - UUID primary keys via `gen_random_uuid()`
   - `created_at`/`updated_at`/`creator`/`modifier` audit fields
   - JSONB `metadata` for extensible data (use for source tracking)
   - `State(Pool<Postgres>)` for database access in handlers (the project uses `with_state`, not `Extension`)
   - OpenAPI annotations with `#[utoipa::path(...)]` for new endpoints — include all expected status codes (401, 404, 409, 500) in `responses(...)`
   - New write endpoints go on `protected_api_routes` (or `protected_web_routes`); new read endpoints go on `api_routes` / `web_routes`

3. **Database changes**:
   - Add a migration in `migrations/` with a `YYYYMMDDHHMMSS_description.sql` filename
   - Apply it to the running dev DB via `docker exec quantumdb-db-1 psql ... -f /migrations/...`
   - Run `cargo sqlx prepare` on the host (with `DATABASE_URL` pointing at the dockerised DB) so `.sqlx/` reflects new query shapes; commit the result
   - Refresh materialized views after bulk data changes (CONCURRENTLY is fine — every view has a unique index now)
   - Use CHECK constraints for enum-like fields (e.g., `venue` on conferences)

4. **Testing**:
   - Add tests to `tests/api_tests.rs` for new endpoints
   - Lib tests live next to the code (`#[cfg(test)] mod tests`); the `utils` modules have ~30 of these
   - Test full CRUD lifecycle for each entity
