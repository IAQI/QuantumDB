use axum::{
    extract::Request,
    http::{HeaderMap, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
};
use serde_json::json;
use std::env;
use subtle::ConstantTimeEq;

/// Authentication middleware that validates Bearer tokens
///
/// Expects tokens in the `Authorization` header as `Bearer <token>`.
/// Validates against comma-separated tokens from the `API_TOKENS` environment variable.
/// Tokens must be at least 32 characters; the body is treated as opaque so any
/// scheme that produces a sufficiently-long secret (base64, hex, UUID, etc.) works.
pub async fn auth_middleware(headers: HeaderMap, request: Request, next: Next) -> Response {
    // Local dev bypass: when AUTH_DISABLED=1 the middleware short-circuits.
    // Intended for `cargo run` / docker-compose against a local DB; never set in production.
    if env::var("AUTH_DISABLED")
        .map(|v| v == "1" || v.eq_ignore_ascii_case("true"))
        .unwrap_or(false)
    {
        return next.run(request).await;
    }

    // Token must come from the Authorization header. A `?token=...` query-string
    // fallback was intentionally removed: query strings leak into reverse-proxy
    // and access logs, browser history, and the Referer header. Call protected
    // endpoints (including /admin/refresh-stats) with `Authorization: Bearer <token>`.
    let provided_token: String = match headers.get("authorization") {
        Some(auth_header) => {
            let auth_str = match auth_header.to_str() {
                Ok(s) => s,
                Err(_) => {
                    return unauthorized_json("Invalid Authorization header format.");
                }
            };
            if !auth_str.starts_with("Bearer ") {
                return unauthorized_json(
                    "Authorization header must use Bearer scheme (e.g., 'Authorization: Bearer <token>').",
                );
            }
            auth_str.trim_start_matches("Bearer ").trim().to_string()
        }
        None => {
            return unauthorized_json(
                "Missing Authorization header. Please provide a Bearer token.",
            );
        }
    };
    let provided_token = provided_token.as_str();

    // Minimum length sanity check. The token body is treated as opaque — any character
    // set is accepted. The real check is the constant-time comparison below.
    if provided_token.len() < 32 {
        return unauthorized_json("Invalid token format.");
    }

    // Get valid tokens from environment variable
    let valid_tokens = match env::var("API_TOKENS") {
        Ok(tokens_str) => tokens_str
            .split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect::<Vec<String>>(),
        Err(_) => {
            tracing::error!("API_TOKENS environment variable not set");
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

    // Constant-time comparison against every configured token. Iterate through all
    // tokens unconditionally and OR the results so the loop's runtime does not depend
    // on which (if any) token matched.
    let provided_bytes = provided_token.as_bytes();
    let mut matched = subtle::Choice::from(0u8);
    for valid in &valid_tokens {
        matched |= valid.as_bytes().ct_eq(provided_bytes);
    }
    if !bool::from(matched) {
        return unauthorized_json("Invalid or expired token.");
    }

    // Token is valid, proceed with the request
    next.run(request).await
}

fn unauthorized_json(message: &str) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        [(axum::http::header::CONTENT_TYPE, "application/json")],
        json!({ "error": "Unauthorized", "message": message }).to_string(),
    )
        .into_response()
}