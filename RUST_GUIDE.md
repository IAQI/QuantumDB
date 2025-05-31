# QuantumDB Rust Implementation Guide

## Development Setup

### Prerequisites
1. Install Rust and tools:
   ```bash
   # Install Rust
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

   # Install PostgreSQL
   brew install postgresql@15

   # Install development tools
   cargo install sqlx-cli
   cargo install cargo-watch
   cargo install cargo-edit
   ```

2. Database setup:
   ```bash
   # Start PostgreSQL
   brew services start postgresql@15

   # Create database
   createdb quantumdb
   ```

## Project Setup

### 1. Create New Project
```bash
# Create new project
cargo new quantumdb
cd quantumdb

# Add dependencies
cargo add \
    axum \
    tokio --features full \
    sqlx --features runtime-tokio-native-tls,postgres,uuid,json,time \
    serde --features derive \
    serde_json \
    tower-http --features trace,cors \
    tracing \
    tracing-subscriber \
    uuid --features v4,serde \
    thiserror
```

### 2. Project Configuration (Cargo.toml)
```toml
[package]
name = "quantumdb"
version = "0.1.0"
edition = "2021"

[dependencies]
axum = "0.7"
tokio = { version = "1", features = ["full"] }
sqlx = { version = "0.7", features = ["runtime-tokio-native-tls", "postgres", "uuid", "json", "time"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tower-http = { version = "0.4", features = ["trace", "cors"] }
tracing = "0.1"
tracing-subscriber = "0.3"
uuid = { version = "1", features = ["v4", "serde"] }
thiserror = "1"
```

## Core Implementation

### 1. Database Models
```rust
// src/models/conference.rs
use serde::{Deserialize, Serialize};
use sqlx::types::Uuid;
use time::OffsetDateTime;

#[derive(Debug, Serialize, Deserialize)]
pub struct Conference {
    pub id: Uuid,
    pub venue: String,
    pub year: i32,
    pub start_date: time::Date,
    pub end_date: time::Date,
    pub location: String,
    pub website_url: Option<String>,
    pub proceedings_url: Option<String>,
    pub submission_count: Option<i32>,
    pub acceptance_count: Option<i32>,
    pub created_at: OffsetDateTime,
    pub updated_at: OffsetDateTime,
    pub creator: String,
    pub modifier: String,
    pub metadata: serde_json::Value,
}
```

### 2. API Handlers
```rust
// src/handlers/conferences.rs
use axum::{
    extract::{Path, Query, State},
    response::Json,
};
use uuid::Uuid;

pub async fn list_conferences(
    pagination: Query<PaginationParams>,
    State(db): State<PgPool>,
) -> Result<Json<PaginatedResponse<Conference>>, ApiError> {
    let conferences = sqlx::query_as!(
        Conference,
        r#"
        SELECT *
        FROM conferences
        ORDER BY year DESC, venue
        LIMIT $1 OFFSET $2
        "#,
        pagination.limit() as i64,
        pagination.offset() as i64
    )
    .fetch_all(&db)
    .await?;

    Ok(Json(PaginatedResponse::new(conferences, pagination.0)))
}
```

### 3. Error Handling
```rust
// src/error.rs
use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;

#[derive(Debug, thiserror::Error)]
pub enum ApiError {
    #[error("Database error: {0}")]
    Database(#[from] sqlx::Error),
    #[error("Not found")]
    NotFound,
    #[error("Invalid input: {0}")]
    InvalidInput(String),
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let (status, message) = match self {
            Self::Database(err) => (StatusCode::INTERNAL_SERVER_ERROR, err.to_string()),
            Self::NotFound => (StatusCode::NOT_FOUND, "Resource not found".to_string()),
            Self::InvalidInput(msg) => (StatusCode::BAD_REQUEST, msg),
        };

        (status, Json(json!({ "error": message }))).into_response()
    }
}
```

### 4. Pagination
```rust
// src/utils/pagination.rs
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize)]
pub struct PaginationParams {
    pub page: Option<u32>,
    pub per_page: Option<u32>,
}

#[derive(Debug, Serialize)]
pub struct PaginatedResponse<T> {
    pub items: Vec<T>,
    pub total: u64,
    pub page: u32,
    pub per_page: u32,
    pub total_pages: u32,
}

impl PaginationParams {
    pub fn limit(&self) -> u32 {
        self.per_page.unwrap_or(20).min(100)
    }

    pub fn offset(&self) -> u32 {
        (self.page.unwrap_or(1) - 1) * self.limit()
    }
}
```

## Testing

### 1. Unit Tests
```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pagination_params() {
        let params = PaginationParams {
            page: Some(2),
            per_page: Some(30),
        };
        assert_eq!(params.limit(), 30);
        assert_eq!(params.offset(), 30);
    }
}
```

### 2. Integration Tests
```rust
// tests/api/conferences.rs
use sqlx::PgPool;

#[sqlx::test]
async fn test_list_conferences(pool: PgPool) {
    // Setup test data
    sqlx::query!(
        r#"
        INSERT INTO conferences (venue, year, ...)
        VALUES ($1, $2, ...)
        "#,
        "qip",
        2025,
        // ...
    )
    .execute(&pool)
    .await
    .unwrap();

    // Test API endpoint
    // ...
}
```

## Deployment

### 1. Build for Production
```bash
cargo build --release
```

### 2. Database Migrations
```bash
# Create a new migration
sqlx migrate add create_conferences

# Run migrations
sqlx migrate run
```

### 3. Environment Variables
```bash
export DATABASE_URL=postgres://user:password@localhost/quantumdb
export RUST_LOG=info
```

## Resources
1. [Axum Documentation](https://docs.rs/axum)
2. [SQLx Documentation](https://docs.rs/sqlx)
3. [Tower Documentation](https://docs.rs/tower)
