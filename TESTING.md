# Testing Guide

## Overview

QuantumDB includes a comprehensive test suite covering all CRUD operations for every entity. Tests use isolated PostgreSQL databases to enable parallel execution without interference.

## Test Suite Structure

**Location**: `tests/api_tests.rs` (1,155 lines)

The test suite covers:
- Conferences (CRUD + venue validation)
- Authors (CRUD + name normalization)
- Publications (CRUD + canonical_key uniqueness)
- Authorships (CRUD + relationships)
- Committee Roles (CRUD + enum types)

## Running Tests

### Basic Test Execution

```bash
# Run all tests
cargo test

# Run with output visible
cargo test -- --nocapture

# Run specific test
cargo test test_create_conference

# Run tests matching a pattern
cargo test conference

# Run with logging enabled
RUST_LOG=debug cargo test
```

### Parallel Execution

Tests run in parallel by default. Each test creates its own isolated database:

```bash
# Default: parallel execution
cargo test

# Single-threaded execution (if needed)
cargo test -- --test-threads=1
```

## Test Database Isolation

Each test creates a unique PostgreSQL database to prevent interference:

```rust
async fn setup_test_db() -> PgPool {
    let test_db_name = format!("quantumdb_test_{}", Uuid::new_v4().simple());
    // Creates database, runs migrations
    // Returns connection pool
}
```

**Cleanup**: Test databases are automatically dropped after each test completes.

## Test Patterns

### 1. CRUD Lifecycle Tests

Most tests follow the complete CRUD lifecycle:

```rust
#[tokio::test]
async fn test_conference_crud() {
    let pool = setup_test_db().await;
    let app = create_test_app(pool.clone());
    
    // CREATE
    let response = app.post("/conferences")
        .json(&create_payload)
        .await;
    assert_eq!(response.status(), StatusCode::CREATED);
    
    // READ
    let response = app.get(&format!("/conferences/{}", id)).await;
    assert_eq!(response.status(), StatusCode::OK);
    
    // UPDATE
    let response = app.put(&format!("/conferences/{}", id))
        .json(&update_payload)
        .await;
    assert_eq!(response.status(), StatusCode::OK);
    
    // DELETE
    let response = app.delete(&format!("/conferences/{}", id)).await;
    assert_eq!(response.status(), StatusCode::OK);
    
    cleanup_test_db(&test_db_name).await;
}
```

### 2. Validation Tests

Tests verify database constraints and validation:

```rust
#[tokio::test]
async fn test_invalid_venue() {
    // Attempt to create conference with invalid venue
    // Expect 400 BAD_REQUEST or 500 INTERNAL_SERVER_ERROR
}

#[tokio::test]
async fn test_duplicate_canonical_key() {
    // Attempt to create duplicate publication
    // Expect constraint violation
}
```

### 3. Relationship Tests

Tests verify foreign key relationships:

```rust
#[tokio::test]
async fn test_authorship_relationships() {
    // Create author
    // Create publication
    // Create authorship linking them
    // Verify relationships maintained
}
```

## Test Utilities

### Helper Functions

The test suite includes common utilities:

```rust
// Database setup and teardown
async fn setup_test_db() -> PgPool
async fn cleanup_test_db(db_name: &str)

// Test app creation
fn create_test_app(pool: PgPool) -> TestApp

// Payload builders
fn create_conference_payload() -> serde_json::Value
fn create_author_payload() -> serde_json::Value
```

### Common Module

`tests/common.rs` provides shared test infrastructure (if it exists).

## Test Coverage

### Conferences ✓
- ✓ Create conference
- ✓ Get conference by ID
- ✓ List all conferences
- ✓ Update conference
- ✓ Delete conference
- ✓ Venue validation (QIP, QCRYPT, TQC only)
- ✓ Unique (venue, year) constraint

### Authors ✓
- ✓ Create author
- ✓ Get author by ID
- ✓ List all authors
- ✓ Update author
- ✓ Delete author
- ✓ Name normalization
- ✓ ORCID validation

### Publications ✓
- ✓ Create publication
- ✓ Get publication by ID
- ✓ List all publications
- ✓ Update publication
- ✓ Delete publication
- ✓ Unique canonical_key constraint
- ✓ Conference foreign key relationship

### Authorships ✓
- ✓ Create authorship
- ✓ Get authorship by ID
- ✓ List all authorships
- ✓ Update authorship
- ✓ Delete authorship
- ✓ Author position ordering
- ✓ Unique (publication_id, author_id) constraint

### Committee Roles ✓
- ✓ Create committee role
- ✓ Get committee role by ID
- ✓ List all committee roles
- ✓ Update committee role
- ✓ Delete committee role
- ✓ Committee type enum (OC, PC, SC, Local)
- ✓ Position enum (chair, co_chair, area_chair, member)

## Writing New Tests

### Template for New Test

```rust
#[tokio::test]
async fn test_your_feature() {
    // 1. Setup test database
    let pool = setup_test_db().await;
    let app = create_test_app(pool.clone());
    
    // 2. Perform test actions
    let response = app.get("/your-endpoint").await;
    
    // 3. Assert expected outcomes
    assert_eq!(response.status(), StatusCode::OK);
    
    // 4. Cleanup (automatic for test databases)
}
```

### Best Practices

1. **Use unique identifiers**: Test databases use UUIDs to prevent collisions
2. **Test error cases**: Don't just test happy paths
3. **Verify database state**: Check that database changes actually occurred
4. **Clean up relationships**: When testing deletes, verify cascades work
5. **Use descriptive names**: `test_conference_requires_valid_venue` not `test_1`

## Debugging Tests

### View Test Output

```bash
# Show println! output
cargo test -- --nocapture

# Show test names as they run
cargo test -- --nocapture --test-threads=1
```

### Enable Logging

```bash
# Enable debug logging for SQLx
RUST_LOG=sqlx=debug cargo test

# Enable all debug logging
RUST_LOG=debug cargo test -- --nocapture
```

### Inspect Test Database

If a test hangs or you need to inspect the database:

```bash
# List all databases (look for quantumdb_test_*)
psql -l

# Connect to a specific test database
psql quantumdb_test_abc123...

# View tables
\dt

# Query data
SELECT * FROM conferences;
```

## Continuous Integration

Tests should pass before merging:

```bash
# Run full test suite
cargo test

# Check code formatting
cargo fmt --check

# Run linter
cargo clippy -- -D warnings

# Ensure SQLx offline data is current
cargo sqlx prepare --check
```

## Future Test Improvements

Potential enhancements for the test suite:

1. **Integration tests** for full workflows (create conference → add publications → add authors)
2. **Performance tests** for large datasets
3. **Concurrency tests** for race conditions
4. **Search tests** when full-text search is implemented
5. **Export tests** when BibTeX/CSV export is added
6. **API documentation tests** to verify Swagger spec accuracy

## Troubleshooting

### "Database already exists" error
- Usually means a previous test didn't clean up
- Manually drop: `dropdb quantumdb_test_<uuid>`

### "Connection refused" error
- Ensure PostgreSQL is running: `brew services start postgresql@15`
- Check `DATABASE_URL` in `.env`

### "Migration failed" error
- Ensure migrations are up to date: `sqlx migrate run`
- Regenerate SQLx data: `cargo sqlx prepare`

### Tests hang indefinitely
- May indicate deadlock or connection pool exhaustion
- Run with `--test-threads=1` to isolate
- Check for missing `.await` in async code
