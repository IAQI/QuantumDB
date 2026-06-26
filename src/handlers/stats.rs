use axum::{extract::State, http::StatusCode, Json};
use sqlx::{Pool, Postgres};

use crate::models::ConferenceStat;

/// Per-conference statistics time series (one row per venue/year). Combines the
/// computed counts from the `conference_stats` materialized view with the
/// announced participant figure from `conference_business_meetings`. Public,
/// read-only — intended for building trend charts.
#[utoipa::path(
    get,
    path = "/stats/conferences",
    tag = "stats",
    responses(
        (status = 200, description = "Per-conference statistics time series (one row per venue/year)", body = Vec<ConferenceStat>),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn list_conference_stats(
    State(pool): State<Pool<Postgres>>,
) -> Result<Json<Vec<ConferenceStat>>, StatusCode> {
    let stats = sqlx::query_as!(
        ConferenceStat,
        r#"
        SELECT
            c.venue                      AS "venue!",
            c.year                       AS "year!",
            COALESCE(pc.talk_count, 0)   AS "talk_count!",
            COALESCE(pc.poster_count, 0) AS "poster_count!",
            bm.talk_submissions          AS submission_count,
            bm.talks_accepted            AS acceptance_count,
            COALESCE(
                bm.acceptance_rate,
                ROUND(bm.talks_accepted::numeric / NULLIF(bm.talk_submissions, 0) * 100, 1)
            )::float8                    AS acceptance_rate,
            bm.registered_participants   AS registered_participants
        FROM conferences c
        LEFT JOIN (
            SELECT conference_id,
                   COUNT(*) FILTER (WHERE paper_type <> 'poster') AS talk_count,
                   COUNT(*) FILTER (WHERE paper_type =  'poster') AS poster_count
            FROM publications
            GROUP BY conference_id
        ) pc ON pc.conference_id = c.id
        LEFT JOIN conference_business_meetings bm ON bm.conference_id = c.id
        ORDER BY c.venue, c.year
        "#
    )
    .fetch_all(&pool)
    .await
    .map_err(|e| {
        tracing::error!("Failed to fetch conference stats: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    Ok(Json(stats))
}
