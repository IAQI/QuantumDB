//! Mapping SQLx/PostgreSQL errors to HTTP status codes.
//!
//! Write handlers must not collapse *client* errors (a duplicate row, a bad
//! venue, a dangling foreign key) into a generic 500. Those are 4xx: the caller
//! sent something the database legitimately rejected. Only genuinely unexpected
//! failures should surface as 500.

use axum::http::StatusCode;

// PostgreSQL SQLSTATE codes (class 23 — integrity constraint violation, plus
// 22P02 for malformed enum/uuid input text).
const PG_NOT_NULL_VIOLATION: &str = "23502";
const PG_FOREIGN_KEY_VIOLATION: &str = "23503";
const PG_UNIQUE_VIOLATION: &str = "23505";
const PG_CHECK_VIOLATION: &str = "23514";
const PG_INVALID_TEXT_REPRESENTATION: &str = "22P02";

/// Map an SQLx error to the status code a handler should return.
///
/// - unique violation → 409 Conflict (the row already exists)
/// - check / foreign-key / not-null / invalid-text → 400 Bad Request (the
///   payload violates a database rule, e.g. an out-of-range `venue` or a
///   conference id that doesn't exist)
/// - anything else → 500 Internal Server Error
pub fn map_db_error(err: &sqlx::Error) -> StatusCode {
    if let Some(db_err) = err.as_database_error() {
        match db_err.code().as_deref() {
            Some(PG_UNIQUE_VIOLATION) => return StatusCode::CONFLICT,
            Some(PG_CHECK_VIOLATION)
            | Some(PG_FOREIGN_KEY_VIOLATION)
            | Some(PG_NOT_NULL_VIOLATION)
            | Some(PG_INVALID_TEXT_REPRESENTATION) => return StatusCode::BAD_REQUEST,
            _ => {}
        }
    }
    StatusCode::INTERNAL_SERVER_ERROR
}
