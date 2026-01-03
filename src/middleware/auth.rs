use axum::{
    extract::Request,
    http::{HeaderMap, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
};
use serde_json::json;
use std::env;

/// Authentication middleware that validates Bearer tokens
///
/// Expects tokens in the `Authorization` header as `Bearer <token>`.
/// Validates against comma-separated tokens from the `API_TOKENS` environment variable.
/// Tokens must be at least 32 characters and contain only alphanumeric characters, hyphens, and underscores.
pub async fn auth_middleware(headers: HeaderMap, request: Request, next: Next) -> Response {
    // Extract Authorization header
    let auth_header = match headers.get("authorization") {
        Some(header) => header,
        None => {
            return (
                StatusCode::UNAUTHORIZED,
                [(axum::http::header::CONTENT_TYPE, "application/json")],
                json!({
                    "error": "Unauthorized",
                    "message": "Missing Authorization header. Please provide a Bearer token."
                })
                .to_string(),
            )
                .into_response();
        }
    };

    // Parse Bearer token
    let auth_str = match auth_header.to_str() {
        Ok(s) => s,
        Err(_) => {
            return (
                StatusCode::UNAUTHORIZED,
                [(axum::http::header::CONTENT_TYPE, "application/json")],
                json!({
                    "error": "Unauthorized",
                    "message": "Invalid Authorization header format."
                })
                .to_string(),
            )
                .into_response();
        }
    };

    if !auth_str.starts_with("Bearer ") {
        return (
            StatusCode::UNAUTHORIZED,
            [(axum::http::header::CONTENT_TYPE, "application/json")],
            json!({
                "error": "Unauthorized",
                "message": "Authorization header must use Bearer scheme (e.g., 'Authorization: Bearer <token>')."
            })
            .to_string(),
        )
            .into_response();
    }

    let provided_token = auth_str.trim_start_matches("Bearer ").trim();

    // Validate token format (minimum 32 characters, alphanumeric plus -_)
    if provided_token.len() < 32 {
        return (
            StatusCode::UNAUTHORIZED,
            [(axum::http::header::CONTENT_TYPE, "application/json")],
            json!({
                "error": "Unauthorized",
                "message": "Invalid token format."
            })
            .to_string(),
        )
            .into_response();
    }

    if !provided_token
        .chars()
        .all(|c| c.is_alphanumeric() || c == '-' || c == '_')
    {
        return (
            StatusCode::UNAUTHORIZED,
            [(axum::http::header::CONTENT_TYPE, "application/json")],
            json!({
                "error": "Unauthorized",
                "message": "Invalid token format."
            })
            .to_string(),
        )
            .into_response();
    }

    // Get valid tokens from environment variable
    let valid_tokens = match env::var("API_TOKENS") {
        Ok(tokens_str) => tokens_str
            .split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect::<Vec<String>>(),
        Err(_) => {
            eprintln!("ERROR: API_TOKENS environment variable not set");
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                [(axum::http::header::CONTENT_TYPE, "application/json")],
                json!({
                    "error": "Internal Server Error",
                    "message": "Authentication is not properly configured on the server."
                })
                .to_string(),
            )
                .into_response();
        }
    };

    // Check if provided token matches any valid token
    if !valid_tokens.iter().any(|t| t == provided_token) {
        return (
            StatusCode::UNAUTHORIZED,
            [(axum::http::header::CONTENT_TYPE, "application/json")],
            json!({
                "error": "Unauthorized",
                "message": "Invalid or expired token."
            })
            .to_string(),
        )
            .into_response();
    }

    // Token is valid, proceed with the request
    next.run(request).await
}
