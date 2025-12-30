use axum::{
    extract::{Path, State},
    http::StatusCode,
    Json,
};
use sqlx::{Pool, Postgres};
use uuid::Uuid;

use crate::models::{Conference, CreateConference, UpdateConference};
use crate::utils::parse_conference_slug;

/// Resolve a conference ID or slug to a UUID
async fn resolve_conference_id(pool: &Pool<Postgres>, id_or_slug: &str) -> Result<Uuid, StatusCode> {
    // Try parsing as UUID first
    if let Ok(uuid) = Uuid::parse_str(id_or_slug) {
        return Ok(uuid);
    }

    // Try parsing as slug (e.g., QIP2024, QCRYPT2018, TQC2022)
    if let Some((venue, year)) = parse_conference_slug(id_or_slug) {
        let result = sqlx::query_scalar!(
            "SELECT id FROM conferences WHERE venue = $1 AND year = $2",
            venue,
            year
        )
        .fetch_optional(pool)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

        if let Some(id) = result {
            return Ok(id);
        }
        return Err(StatusCode::NOT_FOUND);
    }

    // Invalid format
    Err(StatusCode::BAD_REQUEST)
}

#[utoipa::path(
    get,
    path = "/conferences",
    tag = "conferences",
    responses(
        (status = 200, description = "List all conferences", body = Vec<Conference>),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn list_conferences(
    State(pool): State<Pool<Postgres>>,
) -> Result<Json<Vec<Conference>>, StatusCode> {
    let conferences = sqlx::query_as!(
        Conference,
        r#"
        SELECT
            id, venue, year, start_date, end_date,
            city, country, country_code, is_virtual, is_hybrid,
            timezone, venue_name, website_url, proceedings_url,
            proceedings_publisher, proceedings_volume, proceedings_doi,
            submission_count, acceptance_count,
            archive_url, archive_organizers_url, archive_pc_url,
            archive_steering_url, archive_program_url,
            created_at, updated_at
        FROM conferences
        ORDER BY year DESC, venue
        "#
    )
    .fetch_all(&pool)
    .await
    .map_err(|e| {
        tracing::error!("Failed to fetch conferences: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    Ok(Json(conferences))
}

#[utoipa::path(
    get,
    path = "/conferences/{id}",
    tag = "conferences",
    params(("id" = String, Path, description = "Conference ID (UUID) or slug (e.g., QIP2024, QCRYPT2018, TQC2022)")),
    responses(
        (status = 200, description = "Conference found", body = Conference),
        (status = 404, description = "Conference not found"),
        (status = 400, description = "Invalid ID format")
    )
)]
pub async fn get_conference(
    State(pool): State<Pool<Postgres>>,
    Path(id_or_slug): Path<String>,
) -> Result<Json<Conference>, StatusCode> {
    // Try parsing as UUID first
    if let Ok(uuid) = Uuid::parse_str(&id_or_slug) {
        let conference = sqlx::query_as!(
            Conference,
            r#"
            SELECT
                id, venue, year, start_date, end_date,
                city, country, country_code, is_virtual, is_hybrid,
                timezone, venue_name, website_url, proceedings_url,
                proceedings_publisher, proceedings_volume, proceedings_doi,
                submission_count, acceptance_count,
                archive_url, archive_organizers_url, archive_pc_url,
                archive_steering_url, archive_program_url,
                created_at, updated_at
            FROM conferences
            WHERE id = $1
            "#,
            uuid
        )
        .fetch_one(&pool)
        .await
        .map_err(|_| StatusCode::NOT_FOUND)?;

        return Ok(Json(conference));
    }

    // Try parsing as slug (e.g., QIP2024, QCRYPT2018, TQC2022)
    if let Some((venue, year)) = parse_conference_slug(&id_or_slug) {
        let conference = sqlx::query_as!(
            Conference,
            r#"
            SELECT
                id, venue, year, start_date, end_date,
                city, country, country_code, is_virtual, is_hybrid,
                timezone, venue_name, website_url, proceedings_url,
                proceedings_publisher, proceedings_volume, proceedings_doi,
                submission_count, acceptance_count,
                archive_url, archive_organizers_url, archive_pc_url,
                archive_steering_url, archive_program_url,
                created_at, updated_at
            FROM conferences
            WHERE venue = $1 AND year = $2
            "#,
            venue,
            year
        )
        .fetch_one(&pool)
        .await
        .map_err(|_| StatusCode::NOT_FOUND)?;

        return Ok(Json(conference));
    }

    // Invalid format
    Err(StatusCode::BAD_REQUEST)
}

#[utoipa::path(
    post,
    path = "/conferences",
    tag = "conferences",
    request_body = CreateConference,
    responses(
        (status = 201, description = "Conference created", body = Conference),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn create_conference(
    State(pool): State<Pool<Postgres>>,
    Json(new_conference): Json<CreateConference>,
) -> Result<(StatusCode, Json<Conference>), StatusCode> {
    let conference = sqlx::query_as!(
        Conference,
        r#"
        INSERT INTO conferences (
            venue, year, start_date, end_date,
            city, country, country_code, is_virtual, is_hybrid,
            timezone, venue_name, website_url, proceedings_url,
            proceedings_publisher, proceedings_volume, proceedings_doi,
            submission_count, acceptance_count,
            archive_url, archive_organizers_url, archive_pc_url,
            archive_steering_url, archive_program_url,
            creator, modifier
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9,
            $10, $11, $12, $13, $14, $15, $16, $17, $18,
            $19, $20, $21, $22, $23, $24, $25
        )
        RETURNING
            id, venue, year, start_date, end_date,
            city, country, country_code, is_virtual, is_hybrid,
            timezone, venue_name, website_url, proceedings_url,
            proceedings_publisher, proceedings_volume, proceedings_doi,
            submission_count, acceptance_count,
            archive_url, archive_organizers_url, archive_pc_url,
            archive_steering_url, archive_program_url,
            created_at, updated_at
        "#,
        new_conference.venue,
        new_conference.year,
        new_conference.start_date,
        new_conference.end_date,
        new_conference.city,
        new_conference.country,
        new_conference.country_code,
        new_conference.is_virtual.unwrap_or(false),
        new_conference.is_hybrid.unwrap_or(false),
        new_conference.timezone,
        new_conference.venue_name,
        new_conference.website_url,
        new_conference.proceedings_url,
        new_conference.proceedings_publisher,
        new_conference.proceedings_volume,
        new_conference.proceedings_doi,
        new_conference.submission_count,
        new_conference.acceptance_count,
        new_conference.archive_url,
        new_conference.archive_organizers_url,
        new_conference.archive_pc_url,
        new_conference.archive_steering_url,
        new_conference.archive_program_url,
        new_conference.creator,
        new_conference.modifier
    )
    .fetch_one(&pool)
    .await
    .map_err(|e| {
        tracing::error!("Failed to create conference: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    Ok((StatusCode::CREATED, Json(conference)))
}

#[utoipa::path(
    put,
    path = "/conferences/{id}",
    tag = "conferences",
    params(("id" = String, Path, description = "Conference ID (UUID) or slug (e.g., QIP2024, QCRYPT2018, TQC2022)")),
    request_body = UpdateConference,
    responses(
        (status = 200, description = "Conference updated", body = Conference),
        (status = 404, description = "Conference not found"),
        (status = 400, description = "Invalid ID format"),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn update_conference(
    State(pool): State<Pool<Postgres>>,
    Path(id_or_slug): Path<String>,
    Json(update): Json<UpdateConference>,
) -> Result<Json<Conference>, StatusCode> {
    // Resolve ID to UUID
    let id = resolve_conference_id(&pool, &id_or_slug).await?;

    // First fetch the existing conference
    let existing = sqlx::query_as!(
        Conference,
        r#"
        SELECT
            id, venue, year, start_date, end_date,
            city, country, country_code, is_virtual, is_hybrid,
            timezone, venue_name, website_url, proceedings_url,
            proceedings_publisher, proceedings_volume, proceedings_doi,
            submission_count, acceptance_count,
            archive_url, archive_organizers_url, archive_pc_url,
            archive_steering_url, archive_program_url,
            created_at, updated_at
        FROM conferences
        WHERE id = $1
        "#,
        id
    )
    .fetch_optional(&pool)
    .await
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
    .ok_or(StatusCode::NOT_FOUND)?;

    // Update with provided values or keep existing
    let conference = sqlx::query_as!(
        Conference,
        r#"
        UPDATE conferences
        SET
            venue = $1,
            year = $2,
            start_date = $3,
            end_date = $4,
            city = $5,
            country = $6,
            country_code = $7,
            is_virtual = $8,
            is_hybrid = $9,
            timezone = $10,
            venue_name = $11,
            website_url = $12,
            proceedings_url = $13,
            proceedings_publisher = $14,
            proceedings_volume = $15,
            proceedings_doi = $16,
            submission_count = $17,
            acceptance_count = $18,
            archive_url = $19,
            archive_organizers_url = $20,
            archive_pc_url = $21,
            archive_steering_url = $22,
            archive_program_url = $23,
            modifier = $24,
            updated_at = NOW()
        WHERE id = $25
        RETURNING
            id, venue, year, start_date, end_date,
            city, country, country_code, is_virtual, is_hybrid,
            timezone, venue_name, website_url, proceedings_url,
            proceedings_publisher, proceedings_volume, proceedings_doi,
            submission_count, acceptance_count,
            archive_url, archive_organizers_url, archive_pc_url,
            archive_steering_url, archive_program_url,
            created_at, updated_at
        "#,
        update.venue.unwrap_or(existing.venue),
        update.year.unwrap_or(existing.year),
        update.start_date.or(existing.start_date),
        update.end_date.or(existing.end_date),
        update.city.or(existing.city),
        update.country.or(existing.country),
        update.country_code.or(existing.country_code),
        update.is_virtual.or(existing.is_virtual).unwrap_or(false),
        update.is_hybrid.or(existing.is_hybrid).unwrap_or(false),
        update.timezone.or(existing.timezone),
        update.venue_name.or(existing.venue_name),
        update.website_url.or(existing.website_url),
        update.proceedings_url.or(existing.proceedings_url),
        update.proceedings_publisher.or(existing.proceedings_publisher),
        update.proceedings_volume.or(existing.proceedings_volume),
        update.proceedings_doi.or(existing.proceedings_doi),
        update.submission_count.or(existing.submission_count),
        update.acceptance_count.or(existing.acceptance_count),
        update.archive_url.or(existing.archive_url),
        update.archive_organizers_url.or(existing.archive_organizers_url),
        update.archive_pc_url.or(existing.archive_pc_url),
        update.archive_steering_url.or(existing.archive_steering_url),
        update.archive_program_url.or(existing.archive_program_url),
        update.modifier,
        id
    )
    .fetch_one(&pool)
    .await
    .map_err(|e| {
        tracing::error!("Failed to update conference: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    Ok(Json(conference))
}

#[utoipa::path(
    delete,
    path = "/conferences/{id}",
    tag = "conferences",
    params(("id" = String, Path, description = "Conference ID (UUID) or slug (e.g., QIP2024, QCRYPT2018, TQC2022)")),
    responses(
        (status = 204, description = "Conference deleted"),
        (status = 404, description = "Conference not found"),
        (status = 400, description = "Invalid ID format"),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn delete_conference(
    State(pool): State<Pool<Postgres>>,
    Path(id_or_slug): Path<String>,
) -> Result<StatusCode, StatusCode> {
    let id = resolve_conference_id(&pool, &id_or_slug).await?;
    let result = sqlx::query!("DELETE FROM conferences WHERE id = $1", id)
        .execute(&pool)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    if result.rows_affected() == 0 {
        return Err(StatusCode::NOT_FOUND);
    }

    Ok(StatusCode::NO_CONTENT)
}
