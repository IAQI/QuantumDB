# QuantumDB - Architecture Document

## Project Overview
A REST API service for tracking quantum computing conferences (QIP, QCrypt, TQC) including papers, videos, committee memberships, and awards. **All core CRUD operations are fully implemented** with complete modular architecture, Swagger UI, and production-ready features.

## Technology Stack

### Backend Architecture
- **Language & Framework:**
  - Rust with Axum web framework
  - Async runtime with Tokio
  - SQLx for type-safe database access
  - Tower middleware for request handling
  - OpenAPI/Swagger via utoipa for API documentation
  - unicode-normalization for name processing

- **Database:**
  - PostgreSQL 15+
  - Full-text search capabilities
  - JSONB for flexible metadata
  - Materialized views for performance

### Current Project Structure
```
quantumdb/
├── Cargo.toml
├── src/
│   ├── main.rs               # Application entry point, router setup, Swagger config
│   ├── lib.rs                # Library exports
│   ├── models/              # Database models (IMPLEMENTED)
│   │   ├── mod.rs
│   │   ├── conference.rs    # Conference, CreateConference, UpdateConference
│   │   ├── publication.rs   # Publication, CreatePublication, UpdatePublication
│   │   ├── author.rs        # Author, CreateAuthor, UpdateAuthor
│   │   ├── committee.rs     # CommitteeRole, CreateCommitteeRole, UpdateCommitteeRole
│   │   ├── business_meeting.rs # BusinessMeeting (stats announced at the business meeting)
│   │   └── stats.rs         # ConferenceStat (per-venue/year stats time series)
│   ├── handlers/            # API request handlers (IMPLEMENTED)
│   │   ├── mod.rs
│   │   ├── conferences.rs   # Full CRUD operations
│   │   ├── publications.rs  # Full CRUD operations (list supports ?search= full-text)
│   │   ├── authors.rs       # Full CRUD operations
│   │   ├── authorships.rs   # Full CRUD operations
│   │   ├── committees.rs    # Full CRUD operations
│   │   ├── stats.rs         # Read-only per-conference stats (GET /api/v1/stats/conferences)
│   │   └── web/             # Web interface handlers (IMPLEMENTED)
│   │       ├── mod.rs
│   │       ├── home.rs      # Homepage
│   │       ├── about.rs     # About page with IAQI branding
│   │       ├── authors.rs   # Author list and detail pages
│   │       ├── conferences.rs # Conference list and detail pages
│   │       ├── publications.rs # Publications browser (full-text search page)
│   │       └── admin.rs     # Admin utilities (stats refresh)
│   ├── middleware/          # Request middleware (IMPLEMENTED)
│   │   ├── mod.rs
│   │   └── auth.rs          # Opaque Bearer-token auth (constant-time comparison, not JWT)
│   └── utils/              # Shared utilities (IMPLEMENTED)
│       ├── mod.rs
│       ├── normalize.rs     # Unicode normalization, name similarity, variants
│       ├── conference.rs    # Conference slug parsing (e.g., "QIP2024")
│       ├── pagination.rs    # clamp_pagination() — bounds limit/offset
│       ├── validation.rs    # URL scheme + length + JSONB metadata validators
│       └── db_error.rs      # map_db_error()/map_delete_error() — SQLSTATE → HTTP status
├── migrations/              # Database migrations (SQLx)
├── seeds/                   # Initial/sample data
├── templates/               # HTML templates (Askama)
│   ├── base.html           # Base template with navigation
│   ├── home.html           # Homepage
│   ├── about.html          # About page
│   ├── authors_list.html   # Author listing
│   ├── author_detail.html  # Individual author page
│   ├── conferences_list.html # Conference listing
│   ├── conference_detail.html # Individual conference page
│   ├── publications_list.html # Publications browser (full-text search)
│   ├── authors_table_partial.html # HTMX partial for dynamic loading
│   ├── conferences_table_partial.html # HTMX partial for dynamic loading
│   └── publications_table_partial.html # HTMX partial for dynamic loading
├── static/                  # Static assets
│   └── images/
│       ├── favicon.png     # Site favicon
│       └── iaqi-logo.png   # IAQI branding logo
└── tests/
    ├── api_tests.rs         # Comprehensive test suite (~1940 lines)
    └── common.rs            # Shared test pool + router setup
```

**Note**: Error handling is done directly in handlers with `StatusCode` returns. Database access uses Axum's `State(Pool<Postgres>)` pattern (the router is built with `.with_state(pool)`, not `Extension`). No separate `config.rs`, `error.rs`, `db/`, or `api/` modules exist.

## API Design

The REST API is versioned and mounted under `/api/v1/`. The HTML web interface and `/health` are unversioned.

### Interactive API Documentation

**Swagger UI**: `GET /api/v1/swagger-ui/` - Interactive API explorer with live testing  
**OpenAPI Spec**: `GET /api/v1/openapi.json` - OpenAPI 3.0 specification

All endpoints are fully documented with request/response schemas in Swagger UI.

### Implemented RESTful Endpoints

**Web Interface**:
```
GET    /                      # Homepage
GET    /about                 # About page (IAQI branding)
GET    /authors               # Author list (paginated, searchable)
GET    /authors/:id           # Author detail page
GET    /conferences           # Conference list (filterable by venue)
GET    /conferences/:slug     # Conference detail page (e.g., /conferences/qip-2024)
GET    /publications          # Publications browser (full-text search over title/abstract/authors)
```

**Static Assets**:
```
GET    /static/*              # Serve static files (images, CSS, JS)
```

**Admin Endpoints** (requires authentication):
```
GET    /admin/refresh-stats   # Refresh materialized views
```

**API Health Check**:
```
GET    /health                # API health status
```

All CRUD endpoints below are mounted under `/api/v1/`. `GET` is public; `POST`/`PUT`/`DELETE` require a Bearer token.

**Conferences** (full CRUD):
```
GET    /api/v1/conferences           # List all conferences
GET    /api/v1/conferences/:id       # Get conference by UUID
POST   /api/v1/conferences           # Create new conference
PUT    /api/v1/conferences/:id       # Update conference
DELETE /api/v1/conferences/:id       # Delete conference
```

**Publications** (full CRUD):
```
GET    /api/v1/publications          # List all publications
GET    /api/v1/publications/:id      # Get publication by UUID
POST   /api/v1/publications          # Create new publication
PUT    /api/v1/publications/:id      # Update publication
DELETE /api/v1/publications/:id      # Delete publication
```

**Authors** (full CRUD):
```
GET    /api/v1/authors               # List all authors
GET    /api/v1/authors/:id           # Get author by UUID
POST   /api/v1/authors               # Create new author
PUT    /api/v1/authors/:id           # Update author
DELETE /api/v1/authors/:id           # Delete author
```

**Authorships** (full CRUD):
```
GET    /api/v1/authorships           # List all authorships
GET    /api/v1/authorships/:id       # Get authorship by UUID
POST   /api/v1/authorships           # Create new authorship  (409 on position conflict)
PUT    /api/v1/authorships/:id       # Update authorship      (409 on position conflict)
DELETE /api/v1/authorships/:id       # Delete authorship
```

**Committee Roles** (full CRUD):
```
GET    /api/v1/committees            # List all committee roles
GET    /api/v1/committees/:id        # Get committee role by UUID
POST   /api/v1/committees            # Create new committee role
PUT    /api/v1/committees/:id        # Update committee role
DELETE /api/v1/committees/:id        # Delete committee role
```

**Stats** (read-only):
```
GET    /api/v1/stats/conferences     # Per-conference (venue/year) stats time series
```

### Common Features

1. **Error Handling** (implemented)
   - Handlers return `(StatusCode, Json<T>)` tuples
   - Success: `(StatusCode::OK, Json(data))` or `(StatusCode::CREATED, Json(data))`
   - Not found: `(StatusCode::NOT_FOUND, Json(error_message))`
   - Database errors: mapped by `map_db_error()`/`map_delete_error()` (`src/utils/db_error.rs`) — unique → 409, check/FK/not-null/invalid-text → 400, still-referenced-on-delete → 409, else 500
   - Validation errors: `(StatusCode::BAD_REQUEST, Json(error_message))`

2. **Type Safety** (implemented)
   - SQLx `query!` and `query_as!` macros for compile-time verification
   - No raw SQL strings
   - Automatic type inference from database schema

3. **OpenAPI Integration** (implemented)
   - `#[utoipa::path(...)]` annotations on all handlers
   - Automatic schema generation from Rust types
   - Interactive Swagger UI at `/api/v1/swagger-ui/`

4. **Name Normalization** (implemented)
   - Unicode NFKD normalization for author names
   - Name similarity scoring for fuzzy matching
   - Automatic name variant generation
   - Loose matching for search

5. **Source Tracking** (implemented)
   - Two-tier system: table-level comments + row-level JSONB metadata
   - JSONB metadata on authorships and committee_roles
   - Tracks source_type, source_url, scraped_date, notes

6. **Authentication** (implemented)
   - Opaque Bearer-token authentication (shared secrets, ≥32 chars, constant-time comparison via the `subtle` crate — not JWT)
   - Environment variable token configuration (API_TOKENS)
   - Multiple tokens supported (comma-separated)
   - Protects write operations (POST, PUT, DELETE)
   - Protects admin endpoints
   - Public read access maintained

7. **Web Interface** (implemented)
   - Server-side rendered HTML templates (Askama)
   - HTMX for dynamic content loading
   - Responsive design with modern CSS
   - Author and conference browsing
   - About page with IAQI branding

8. **Pagination & Validation** (implemented)
   - `clamp_pagination()` bounds `limit`/`offset` on every list endpoint (default 100, max 1000)
   - Input validators for URL scheme, text length, and JSONB metadata on all `Create*`/`Update*` handlers

9. **Hardening** (implemented)
   - Per-IP rate limiting (`tower_governor`)
   - CORS and security-header middleware (`tower-http`)

10. **Business-Meeting Stats** (implemented)
   - `conference_business_meetings` table (1:1 with a conference) records figures *announced* at the annual business meeting — registered/onsite participants, countries, submission/acceptance counts, posters, `track_breakdown` (JSONB), and slide-deck links (`slides` JSONB). Distinct from the computed `conference_stats` view.
   - Populated from a tall `business_meeting.csv` per conference via `import_from_csv.py business-meetings`; rendered on the conference detail page and (registered count) on the conference overview.

11. **Full-text search** (implemented)
   - `GET /api/v1/publications?search=` and the `/publications` web browser query `search_vector` (title `A`, abstract `B`, author names `C`) via `plainto_tsquery`
   - `search_vector` covers author names through the maintained `publications.author_names_text` column (migration 20260702000000)

12. **Future Features**
   - Advanced filtering
   - Export to BibTeX, CSV

## Development Workflow

1. Local Development
```bash
# Start PostgreSQL
brew services start postgresql@15

# Create database
createdb quantumdb

# Run migrations
sqlx migrate run

# Start development server
cargo watch -x run
```

2. Testing
```bash
# Run unit tests
cargo test

# Run integration tests
cargo test --test '*'
```

## Performance Considerations

1. Database
   - Efficient indexing
   - Materialized views
   - Connection pooling

2. API
   - Response caching
   - Batch operations
   - Efficient pagination

3. Monitoring
   - Request timing
   - Error tracking
   - Resource usage

## Security

1. Input Validation
   - Request payload validation
   - SQL injection prevention
   - XSS protection

2. Rate Limiting
   - Per-IP limits
   - Per-endpoint limits
   - Configurable thresholds

3. Error Handling
   - No sensitive data in errors
   - Proper logging
   - Rate limit on failed attempts
