# Testing Guide

## Overview

QuantumDB includes a comprehensive integration test suite covering all CRUD
operations for every entity, plus unit tests for the `utils` modules.

## Test Suite Structure

| File | Lines | Purpose |
|------|------:|---------|
| `tests/api_tests.rs` | ~1,547 | Integration tests — full CRUD lifecycle for every entity, hitting an in-process Axum router |
| `tests/common.rs` | ~39 | Shared helpers: `create_test_pool()` and `create_test_app()` |

Unit tests live next to the code they exercise (`#[cfg(test)] mod tests`),
mostly in the `src/utils/` modules (normalization, slug parsing, pagination,
validation).

The integration suite covers:
- Conferences (CRUD + venue validation + unique `(venue, year)`)
- Authors (CRUD + name normalization + ORCID validation)
- Publications (CRUD + `canonical_key` uniqueness)
- Authorships (CRUD + position ordering + conflict handling)
- Committee Roles (CRUD + committee/position enums)

## How Tests Connect to the Database

**There is no per-test database creation.** `create_test_pool()` reads
`DATABASE_URL` from the environment (or `.env`) and connects to the **shared
dev database** — the same dockerised PostgreSQL the app uses:

```rust
// tests/common.rs
pub async fn create_test_pool() -> Pool<Postgres> {
    dotenvy::dotenv().ok();
    let url = std::env::var("DATABASE_URL")
        .expect("DATABASE_URL must be set for tests");
    PgPoolOptions::new().max_connections(5).connect(&url).await.unwrap()
}
```

Because every test shares one database, **isolation is achieved by namespacing
data, not by isolating databases.** `tests/api_tests.rs` provides:

```rust
fn unique_test_year() -> i32 {
    static COUNTER: AtomicI32 = AtomicI32::new(5000);
    COUNTER.fetch_add(1, Ordering::SeqCst)
}
```

Every test creates its conferences with a year drawn from this counter
(starting at 5000), so test rows never collide with seeded historical data
(1998–2026) or with each other — even when tests run in parallel.

`create_test_app(pool)` builds a **minimal, unversioned** Axum router with the
CRUD handlers wired up via `.with_state(pool)`. Note: the test router does
**not** mount the auth middleware, rate limiter, CORS, or the `/api/v1` prefix —
tests exercise handler logic directly, not the full production middleware stack.

## Running Tests

```bash
# Unit tests only — no database needed
cargo test --lib

# Full suite — requires DATABASE_URL pointing at the dockerised dev DB
DATABASE_URL=postgres://quantumdb:quantumdb@localhost:5432/quantumdb cargo test

# Run with output visible
cargo test -- --nocapture

# Run tests matching a pattern
cargo test conference

# Single-threaded execution (rarely needed — tests are isolated by year range)
cargo test -- --test-threads=1
```

Make sure the stack is up first (`docker compose up -d`) so the database is
reachable on `localhost:5432`.

## Test Patterns

### CRUD Lifecycle

Most tests follow the complete CRUD lifecycle against an in-process router:

```rust
#[tokio::test]
async fn test_conference_crud() {
    let server = setup().await;            // pool + test app as a TestServer
    let test_year = unique_test_year();    // collision-free year

    // CREATE
    let response = server.post("/conferences")
        .json(&json!({ "venue": "QIP", "year": test_year,
                       "creator": "test", "modifier": "test" }))
        .await;
    response.assert_status(StatusCode::CREATED);

    // READ / UPDATE / DELETE follow, using the returned id
}
```

### Validation & Constraint Tests

Tests verify database constraints and handler-level validation — invalid venue
values, duplicate `canonical_key`, duplicate `(publication_id, author_position)`
(expected `409 Conflict`), ORCID format, etc.

### Relationship Tests

Tests create an author + publication + authorship and verify foreign-key
relationships and cascade behaviour.

## Test Coverage

### Conferences
- Create / Get by ID / List / Update / Delete
- Venue validation (QIP, QCRYPT, TQC only)
- Unique `(venue, year)` constraint

### Authors
- Create / Get by ID / List / Update / Delete
- Name normalization
- ORCID validation

### Publications
- Create / Get by ID / List / Update / Delete
- Unique `canonical_key` constraint
- Conference foreign-key relationship

### Authorships
- Create / Get by ID / List / Update / Delete
- Author position ordering
- `409 Conflict` on duplicate `(publication_id, author_position)`

### Committee Roles
- Create / Get by ID / List / Update / Delete
- Committee type enum (OC, PC, SC, Local)
- Position enum (chair, co_chair, area_chair, member)

## Writing New Tests

1. Use `unique_test_year()` for any conference you create — never hard-code a
   year, or you risk colliding with seeded data or a parallel test.
2. Test error cases, not just happy paths.
3. Verify database state actually changed (re-`GET` after a write).
4. Use descriptive names: `test_conference_requires_valid_venue`, not `test_1`.
5. Tests do **not** clean up their rows. That's acceptable because the year
   namespace keeps them inert, but avoid creating unbounded data in a loop.

## CI Checks

Before merging, the following should pass:

```bash
cargo fmt --check
cargo clippy -- -D warnings
cargo test --lib
DATABASE_URL=... cargo test
cargo sqlx prepare --check   # .sqlx/ offline metadata is current
```

## Debugging Tests

```bash
# Show println! output and test names as they run
cargo test -- --nocapture --test-threads=1

# SQLx query logging
RUST_LOG=sqlx=debug cargo test -- --nocapture
```

To inspect what a test wrote, connect to the dev DB and filter by the test
year range (≥ 5000):

```bash
docker exec -it quantumdb-db-1 psql -U quantumdb -d quantumdb \
  -c "SELECT venue, year FROM conferences WHERE year >= 5000 ORDER BY year;"
```

## Troubleshooting

### "DATABASE_URL must be set for tests"
- Export it inline or put it in `.env`. The integration suite cannot run
  without a reachable database.

### "Connection refused"
- Ensure the stack is up: `docker compose up -d`.
- Confirm PostgreSQL is listening on `localhost:5432`.

### Tests pollute the dev database
- Expected, by design — test rows live in the year range ≥ 5000. If you want a
  clean slate, `docker compose down -v && docker compose up -d` re-runs
  migrations + seeds.

### `cargo sqlx prepare --check` fails
- A query string changed without regenerating offline metadata. Run
  `cargo sqlx prepare` (with `DATABASE_URL` set) and commit the `.sqlx/` diff.

## Future Test Improvements

1. Tests for the auth middleware, rate limiter, and `/api/v1` routing (the
   current suite bypasses the production middleware stack).
2. Integration tests for the Python scrape/import pipeline (`tools/scrapers/`).
3. Search/export endpoint tests once those features land.
4. A teardown helper so tests can optionally clean up their year range.
