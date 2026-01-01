use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    Json,
};
use serde::Deserialize;
use sqlx::{Pool, Postgres};
use utoipa::IntoParams;
use uuid::Uuid;

use crate::models::{CreatePublication, PaperType, Publication, UpdatePublication};
use crate::utils::parse_conference_slug;

#[derive(Debug, Deserialize, IntoParams)]
pub struct PublicationQuery {
    /// Full-text search term
    pub search: Option<String>,
    /// Filter by conference ID (UUID) - use 'conference' for slug-based filtering
    pub conference_id: Option<Uuid>,
    /// Filter by conference slug (e.g., QIP2024, QCRYPT2018, TQC2022)
    pub conference: Option<String>,
    /// Filter by paper type
    pub paper_type: Option<String>,
    /// Maximum number of results (default: 100)
    pub limit: Option<i64>,
    /// Number of results to skip (default: 0)
    pub offset: Option<i64>,
}

/// Resolve conference filter to UUID (from either conference_id or conference slug)
async fn resolve_conference_filter(
    pool: &Pool<Postgres>,
    conference_id: Option<Uuid>,
    conference_slug: Option<&str>,
) -> Result<Option<Uuid>, StatusCode> {
    // If conference_id is provided directly, use it
    if let Some(id) = conference_id {
        return Ok(Some(id));
    }

    // If conference slug is provided, resolve it
    if let Some(slug) = conference_slug {
        if let Some((venue, year)) = parse_conference_slug(slug) {
            let result = sqlx::query_scalar!(
                "SELECT id FROM conferences WHERE venue = $1 AND year = $2",
                venue,
                year
            )
            .fetch_optional(pool)
            .await
            .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

            if let Some(id) = result {
                return Ok(Some(id));
            }
            // Conference not found
            return Err(StatusCode::NOT_FOUND);
        }
        // Invalid slug format
        return Err(StatusCode::BAD_REQUEST);
    }

    Ok(None)
}

#[utoipa::path(
    get,
    path = "/publications",
    tag = "publications",
    params(PublicationQuery),
    responses(
        (status = 200, description = "List of publications", body = Vec<Publication>),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn list_publications(
    State(pool): State<Pool<Postgres>>,
    Query(query): Query<PublicationQuery>,
) -> Result<Json<Vec<Publication>>, StatusCode> {
    let limit = query.limit.unwrap_or(100);
    let offset = query.offset.unwrap_or(0);

    // Resolve conference filter (supports both UUID and slug like QIP2024)
    let conf_id = resolve_conference_filter(&pool, query.conference_id, query.conference.as_deref()).await?;

    // Build dynamic query based on filters
    let publications = if let Some(search) = &query.search {
        // Full-text search
        sqlx::query_as!(
            Publication,
            r#"
            SELECT
                id, conference_id, canonical_key, doi,
                COALESCE(arxiv_ids, ARRAY[]::text[]) as "arxiv_ids!",
                title, abstract as "abstract_text",
                paper_type as "paper_type: PaperType",
                pages, session_name, presentation_url, video_url, youtube_id,
                award, award_date, published_date,
                presenter_author_id, is_proceedings_track,
                talk_date, talk_time, duration_minutes,
                created_at, updated_at
            FROM publications
            WHERE search_vector @@ plainto_tsquery('english', $1)
            ORDER BY ts_rank(search_vector, plainto_tsquery('english', $1)) DESC
            LIMIT $2 OFFSET $3
            "#,
            search,
            limit,
            offset
        )
        .fetch_all(&pool)
        .await
    } else if let Some(cid) = conf_id {
        sqlx::query_as!(
            Publication,
            r#"
            SELECT
                id, conference_id, canonical_key, doi,
                COALESCE(arxiv_ids, ARRAY[]::text[]) as "arxiv_ids!",
                title, abstract as "abstract_text",
                paper_type as "paper_type: PaperType",
                pages, session_name, presentation_url, video_url, youtube_id,
                award, award_date, published_date,
                presenter_author_id, is_proceedings_track,
                talk_date, talk_time, duration_minutes,
                created_at, updated_at
            FROM publications
            WHERE conference_id = $1
            ORDER BY session_name, title
            LIMIT $2 OFFSET $3
            "#,
            cid,
            limit,
            offset
        )
        .fetch_all(&pool)
        .await
    } else {
        sqlx::query_as!(
            Publication,
            r#"
            SELECT
                id, conference_id, canonical_key, doi,
                COALESCE(arxiv_ids, ARRAY[]::text[]) as "arxiv_ids!",
                title, abstract as "abstract_text",
                paper_type as "paper_type: PaperType",
                pages, session_name, presentation_url, video_url, youtube_id,
                award, award_date, published_date,
                presenter_author_id, is_proceedings_track,
                talk_date, talk_time, duration_minutes,
                created_at, updated_at
            FROM publications
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            "#,
            limit,
            offset
        )
        .fetch_all(&pool)
        .await
    }
    .map_err(|e| {
        tracing::error!("Failed to fetch publications: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    Ok(Json(publications))
}

#[utoipa::path(
    get,
    path = "/publications/{id}",
    tag = "publications",
    params(("id" = Uuid, Path, description = "Publication ID")),
    responses(
        (status = 200, description = "Publication found", body = Publication),
        (status = 404, description = "Publication not found")
    )
)]
pub async fn get_publication(
    State(pool): State<Pool<Postgres>>,
    Path(id): Path<Uuid>,
) -> Result<Json<Publication>, StatusCode> {
    let publication = sqlx::query_as!(
        Publication,
        r#"
        SELECT
            id, conference_id, canonical_key, doi,
            COALESCE(arxiv_ids, ARRAY[]::text[]) as "arxiv_ids!",
            title, abstract as "abstract_text",
            paper_type as "paper_type: PaperType",
            pages, session_name, presentation_url, video_url, youtube_id,
            award, award_date, published_date,
            presenter_author_id, is_proceedings_track,
            talk_date, talk_time, duration_minutes,
            created_at, updated_at
        FROM publications
        WHERE id = $1
        "#,
        id
    )
    .fetch_one(&pool)
    .await
    .map_err(|_| StatusCode::NOT_FOUND)?;

    Ok(Json(publication))
}

#[utoipa::path(
    post,
    path = "/publications",
    tag = "publications",
    request_body = CreatePublication,
    responses(
        (status = 201, description = "Publication created", body = Publication),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn create_publication(
    State(pool): State<Pool<Postgres>>,
    Json(new_pub): Json<CreatePublication>,
) -> Result<(StatusCode, Json<Publication>), StatusCode> {
    let arxiv_ids = new_pub.arxiv_ids.unwrap_or_default();
    let paper_type = new_pub.paper_type.unwrap_or(PaperType::Regular);
    let is_proceedings_track = new_pub.is_proceedings_track.unwrap_or(false);

    let publication = sqlx::query_as!(
        Publication,
        r#"
        INSERT INTO publications (
            conference_id, canonical_key, doi, arxiv_ids,
            title, abstract, paper_type,
            pages, session_name, presentation_url, video_url, youtube_id,
            award, award_date, published_date,
            presenter_author_id, is_proceedings_track,
            talk_date, talk_time, duration_minutes,
            creator, modifier
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22)
        RETURNING
            id, conference_id, canonical_key, doi,
            COALESCE(arxiv_ids, ARRAY[]::text[]) as "arxiv_ids!",
            title, abstract as "abstract_text",
            paper_type as "paper_type: PaperType",
            pages, session_name, presentation_url, video_url, youtube_id,
            award, award_date, published_date,
            presenter_author_id, is_proceedings_track,
            talk_date, talk_time, duration_minutes,
            created_at, updated_at
        "#,
        new_pub.conference_id,
        new_pub.canonical_key,
        new_pub.doi,
        &arxiv_ids,
        new_pub.title,
        new_pub.abstract_text,
        paper_type as PaperType,
        new_pub.pages,
        new_pub.session_name,
        new_pub.presentation_url,
        new_pub.video_url,
        new_pub.youtube_id,
        new_pub.award,
        new_pub.award_date,
        new_pub.published_date,
        new_pub.presenter_author_id,
        is_proceedings_track,
        new_pub.talk_date,
        new_pub.talk_time,
        new_pub.duration_minutes,
        new_pub.creator,
        new_pub.modifier
    )
    .fetch_one(&pool)
    .await
    .map_err(|e| {
        tracing::error!("Failed to create publication: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    Ok((StatusCode::CREATED, Json(publication)))
}

#[utoipa::path(
    put,
    path = "/publications/{id}",
    tag = "publications",
    params(("id" = Uuid, Path, description = "Publication ID")),
    request_body = UpdatePublication,
    responses(
        (status = 200, description = "Publication updated", body = Publication),
        (status = 404, description = "Publication not found"),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn update_publication(
    State(pool): State<Pool<Postgres>>,
    Path(id): Path<Uuid>,
    Json(update): Json<UpdatePublication>,
) -> Result<Json<Publication>, StatusCode> {
    // First fetch the existing publication
    let existing = sqlx::query_as!(
        Publication,
        r#"
        SELECT
            id, conference_id, canonical_key, doi,
            COALESCE(arxiv_ids, ARRAY[]::text[]) as "arxiv_ids!",
            title, abstract as "abstract_text",
            paper_type as "paper_type: PaperType",
            pages, session_name, presentation_url, video_url, youtube_id,
            award, award_date, published_date,
            presenter_author_id, is_proceedings_track,
            talk_date, talk_time, duration_minutes,
            created_at, updated_at
        FROM publications
        WHERE id = $1
        "#,
        id
    )
    .fetch_optional(&pool)
    .await
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
    .ok_or(StatusCode::NOT_FOUND)?;

    let arxiv_ids = update.arxiv_ids.unwrap_or(existing.arxiv_ids);

    // Update with provided values or keep existing
    let publication = sqlx::query_as!(
        Publication,
        r#"
        UPDATE publications
        SET
            doi = $1,
            arxiv_ids = $2,
            title = $3,
            abstract = $4,
            paper_type = $5,
            pages = $6,
            session_name = $7,
            presentation_url = $8,
            video_url = $9,
            youtube_id = $10,
            award = $11,
            award_date = $12,
            published_date = $13,
            presenter_author_id = $14,
            is_proceedings_track = $15,
            talk_date = $16,
            talk_time = $17,
            duration_minutes = $18,
            modifier = $19,
            updated_at = NOW()
        WHERE id = $20
        RETURNING
            id, conference_id, canonical_key, doi,
            COALESCE(arxiv_ids, ARRAY[]::text[]) as "arxiv_ids!",
            title, abstract as "abstract_text",
            paper_type as "paper_type: PaperType",
            pages, session_name, presentation_url, video_url, youtube_id,
            award, award_date, published_date,
            presenter_author_id, is_proceedings_track,
            talk_date, talk_time, duration_minutes,
            created_at, updated_at
        "#,
        update.doi.or(existing.doi),
        &arxiv_ids,
        update.title.unwrap_or(existing.title),
        update.abstract_text.or(existing.abstract_text),
        update.paper_type.unwrap_or(existing.paper_type) as PaperType,
        update.pages.or(existing.pages),
        update.session_name.or(existing.session_name),
        update.presentation_url.or(existing.presentation_url),
        update.video_url.or(existing.video_url),
        update.youtube_id.or(existing.youtube_id),
        update.award.or(existing.award),
        update.award_date.or(existing.award_date),
        update.published_date.or(existing.published_date),
        update.presenter_author_id.or(existing.presenter_author_id),
        update.is_proceedings_track.unwrap_or(existing.is_proceedings_track),
        update.talk_date.or(existing.talk_date),
        update.talk_time.or(existing.talk_time),
        update.duration_minutes.or(existing.duration_minutes),
        update.modifier,
        id
    )
    .fetch_one(&pool)
    .await
    .map_err(|e| {
        tracing::error!("Failed to update publication: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    Ok(Json(publication))
}

#[utoipa::path(
    delete,
    path = "/publications/{id}",
    tag = "publications",
    params(("id" = Uuid, Path, description = "Publication ID")),
    responses(
        (status = 204, description = "Publication deleted"),
        (status = 404, description = "Publication not found"),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn delete_publication(
    State(pool): State<Pool<Postgres>>,
    Path(id): Path<Uuid>,
) -> Result<StatusCode, StatusCode> {
    let result = sqlx::query!("DELETE FROM publications WHERE id = $1", id)
        .execute(&pool)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    if result.rows_affected() == 0 {
        return Err(StatusCode::NOT_FOUND);
    }

    Ok(StatusCode::NO_CONTENT)
}
