use axum::extract::State;
use axum::http::StatusCode;
use axum::response::{Html, IntoResponse, Response};
use sqlx::PgPool;

/// Admin endpoint to refresh all materialized views.
///
/// Uses `REFRESH MATERIALIZED VIEW CONCURRENTLY` so readers are not blocked during
/// the refresh. CONCURRENTLY requires every view to have at least one UNIQUE index;
/// `author_stats` and `conference_stats` got theirs at creation, and `coauthor_pairs`
/// got one in migration 20260505000000.
pub async fn refresh_stats(State(pool): State<PgPool>) -> Result<Response, StatusCode> {
    sqlx::query("REFRESH MATERIALIZED VIEW CONCURRENTLY author_stats")
        .execute(&pool)
        .await
        .map_err(|e| {
            tracing::error!(error = ?e, "Failed to refresh author_stats");
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    sqlx::query("REFRESH MATERIALIZED VIEW CONCURRENTLY conference_stats")
        .execute(&pool)
        .await
        .map_err(|e| {
            tracing::error!(error = ?e, "Failed to refresh conference_stats");
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    sqlx::query("REFRESH MATERIALIZED VIEW CONCURRENTLY coauthor_pairs")
        .execute(&pool)
        .await
        .map_err(|e| {
            tracing::error!(error = ?e, "Failed to refresh coauthor_pairs");
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    let html = r#"<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="2;url=/">
    <title>Refreshing Statistics - QuantumDB</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
</head>
<body>
    <main class="container">
        <article>
            <header>
                <h1>Statistics Refreshed</h1>
            </header>
            <p>All materialized views have been successfully refreshed:</p>
            <ul>
                <li>Author statistics</li>
                <li>Conference statistics</li>
                <li>Coauthor pairs</li>
            </ul>
            <p>Redirecting to homepage in 2 seconds...</p>
            <footer>
                <a href="/" role="button">Go to Homepage</a>
            </footer>
        </article>
    </main>
</body>
</html>"#;

    Ok(Html(html).into_response())
}
