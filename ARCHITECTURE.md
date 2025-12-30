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
│   │   └── committee.rs     # CommitteeRole, CreateCommitteeRole, UpdateCommitteeRole
│   ├── handlers/            # API request handlers (IMPLEMENTED)
│   │   ├── mod.rs
│   │   ├── conferences.rs   # Full CRUD operations
│   │   ├── publications.rs  # Full CRUD operations
│   │   ├── authors.rs       # Full CRUD operations
│   │   ├── authorships.rs   # Full CRUD operations
│   │   └── committees.rs    # Full CRUD operations
│   └── utils/              # Shared utilities (IMPLEMENTED)
│       ├── mod.rs
│       ├── normalize.rs     # Unicode normalization, name similarity, variants
│       └── conference.rs    # Conference slug parsing (e.g., "QIP2024")
├── migrations/              # Database migrations (SQLx)
├── seeds/                   # Initial/sample data
└── tests/
    └── api_tests.rs         # Comprehensive test suite (1155 lines)
```

**Note**: Error handling is done directly in handlers with `StatusCode` returns. Database connection uses SQLx's `Extension(Pool<Postgres>)` pattern. No separate `config.rs`, `error.rs`, `db/`, or `api/` modules exist.

## API Design

### Interactive API Documentation

**Swagger UI**: `GET /swagger-ui/` - Interactive API explorer with live testing  
**OpenAPI Spec**: `GET /api-docs/openapi.json` - OpenAPI 3.0 specification

All endpoints are fully documented with request/response schemas in Swagger UI.

### Implemented RESTful Endpoints

**Health Check**:
```
GET    /                      # API health check
```

**Conferences** (full CRUD):
```
GET    /conferences           # List all conferences
GET    /conferences/:id       # Get conference by UUID
POST   /conferences           # Create new conference
PUT    /conferences/:id       # Update conference
DELETE /conferences/:id       # Delete conference
```

**Publications** (full CRUD):
```
GET    /publications          # List all publications
GET    /publications/:id      # Get publication by UUID
POST   /publications          # Create new publication
PUT    /publications/:id      # Update publication
DELETE /publications/:id      # Delete publication
```

**Authors** (full CRUD):
```
GET    /authors               # List all authors
GET    /authors/:id           # Get author by UUID
POST   /authors               # Create new author
PUT    /authors/:id           # Update author
DELETE /authors/:id           # Delete author
```

**Authorships** (full CRUD):
```
GET    /authorships           # List all authorships
GET    /authorships/:id       # Get authorship by UUID
POST   /authorships           # Create new authorship
PUT    /authorships/:id       # Update authorship
DELETE /authorships/:id       # Delete authorship
```

**Committee Roles** (full CRUD):
```
GET    /committees            # List all committee roles
GET    /committees/:id        # Get committee role by UUID
POST   /committees            # Create new committee role
PUT    /committees/:id        # Update committee role
DELETE /committees/:id        # Delete committee role
```

### Common Features

1. **Error Handling** (implemented)
   - Handlers return `(StatusCode, Json<T>)` tuples
   - Success: `(StatusCode::OK, Json(data))` or `(StatusCode::CREATED, Json(data))`
   - Not found: `(StatusCode::NOT_FOUND, Json(error_message))`
   - Database errors: `(StatusCode::INTERNAL_SERVER_ERROR, Json(error_message))`
   - Validation errors: `(StatusCode::BAD_REQUEST, Json(error_message))`

2. **Type Safety** (implemented)
   - SQLx `query!` and `query_as!` macros for compile-time verification
   - No raw SQL strings
   - Automatic type inference from database schema

3. **OpenAPI Integration** (implemented)
   - `#[utoipa::path(...)]` annotations on all handlers
   - Automatic schema generation from Rust types
   - Interactive Swagger UI at `/swagger-ui/`

4. **Name Normalization** (implemented)
   - Unicode NFKD normalization for author names
   - Name similarity scoring for fuzzy matching
   - Automatic name variant generation
   - Loose matching for search

5. **Source Tracking** (implemented)
   - Two-tier system: table-level comments + row-level JSONB metadata
   - JSONB metadata on authorships and committee_roles
   - Tracks source_type, source_url, scraped_date, notes

6. **Future Features**
   - Pagination (limit/offset)
   - Full-text search for publications
   - Advanced filtering
   - Authentication (JWT-based)
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
