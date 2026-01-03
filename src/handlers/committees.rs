use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    Json,
};
use serde::Deserialize;
use sqlx::{Pool, Postgres};
use utoipa::IntoParams;
use uuid::Uuid;

use crate::models::{
    CommitteePosition, CommitteeRole, CommitteeType, CreateCommitteeRole, UpdateCommitteeRole,
};
use crate::utils::parse_conference_slug;

#[derive(Debug, Deserialize, IntoParams)]
pub struct CommitteeQuery {
    /// Filter by conference ID (UUID) - use 'conference' for slug-based filtering
    pub conference_id: Option<Uuid>,
    /// Filter by conference slug (e.g., QIP2024, QCRYPT2018, TQC2022)
    pub conference: Option<String>,
    /// Filter by author ID
    pub author_id: Option<Uuid>,
    /// Filter by committee type (OC, PC, SC, Local)
    pub committee_type: Option<String>,
    /// Filter by position (chair, co_chair, area_chair, member)
    pub position: Option<String>,
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
    path = "/committees",
    tag = "committees",
    params(CommitteeQuery),
    responses(
        (status = 200, description = "List of committee roles", body = Vec<CommitteeRole>),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn list_committee_roles(
    State(pool): State<Pool<Postgres>>,
    Query(query): Query<CommitteeQuery>,
) -> Result<Json<Vec<CommitteeRole>>, StatusCode> {
    let limit = query.limit.unwrap_or(100);
    let offset = query.offset.unwrap_or(0);

    // Resolve conference filter (supports both UUID and slug like QIP2024)
    let conf_id = resolve_conference_filter(&pool, query.conference_id, query.conference.as_deref()).await?;

    let roles = if let Some(cid) = conf_id {
        sqlx::query_as!(
            CommitteeRole,
            r#"
            SELECT
                id, conference_id, author_id,
                committee as "committee: CommitteeType",
                position as "position: CommitteePosition",
                role_title, term_start, term_end,
                affiliation,
                COALESCE(metadata, '{}'::jsonb) as "metadata!",
                created_at, updated_at
            FROM committee_roles
            WHERE conference_id = $1
            ORDER BY committee, position, role_title
            LIMIT $2 OFFSET $3
            "#,
            cid,
            limit,
            offset
        )
        .fetch_all(&pool)
        .await
    } else if let Some(auth_id) = query.author_id {
        sqlx::query_as!(
            CommitteeRole,
            r#"
            SELECT
                id, conference_id, author_id,
                committee as "committee: CommitteeType",
                position as "position: CommitteePosition",
                role_title, term_start, term_end,
                affiliation,
                COALESCE(metadata, '{}'::jsonb) as "metadata!",
                created_at, updated_at
            FROM committee_roles
            WHERE author_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            "#,
            auth_id,
            limit,
            offset
        )
        .fetch_all(&pool)
        .await
    } else {
        sqlx::query_as!(
            CommitteeRole,
            r#"
            SELECT
                id, conference_id, author_id,
                committee as "committee: CommitteeType",
                position as "position: CommitteePosition",
                role_title, term_start, term_end,
                affiliation,
                COALESCE(metadata, '{}'::jsonb) as "metadata!",
                created_at, updated_at
            FROM committee_roles
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
        tracing::error!("Failed to fetch committee roles: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    Ok(Json(roles))
}

#[utoipa::path(
    get,
    path = "/committees/{id}",
    tag = "committees",
    params(("id" = Uuid, Path, description = "Committee role ID")),
    responses(
        (status = 200, description = "Committee role found", body = CommitteeRole),
        (status = 404, description = "Committee role not found")
    )
)]
pub async fn get_committee_role(
    State(pool): State<Pool<Postgres>>,
    Path(id): Path<Uuid>,
) -> Result<Json<CommitteeRole>, StatusCode> {
    let role = sqlx::query_as!(
        CommitteeRole,
        r#"
        SELECT
            id, conference_id, author_id,
            committee as "committee: CommitteeType",
            position as "position: CommitteePosition",
            role_title, term_start, term_end,
            affiliation,
            COALESCE(metadata, '{}'::jsonb) as "metadata!",
            created_at, updated_at
        FROM committee_roles
        WHERE id = $1
        "#,
        id
    )
    .fetch_one(&pool)
    .await
    .map_err(|_| StatusCode::NOT_FOUND)?;

    Ok(Json(role))
}

#[utoipa::path(
    post,
    path = "/committees",
    tag = "committees",
    request_body = CreateCommitteeRole,
    responses(
        (status = 201, description = "Committee role created", body = CommitteeRole),
        (status = 401, description = "Unauthorized - missing or invalid token"),
        (status = 500, description = "Internal server error")
    ),
    security(
        ("bearer_auth" = [])
    )
)]
pub async fn create_committee_role(
    State(pool): State<Pool<Postgres>>,
    Json(new_role): Json<CreateCommitteeRole>,
) -> Result<(StatusCode, Json<CommitteeRole>), StatusCode> {
    let position = new_role.position.unwrap_or(CommitteePosition::Member);

    let role = sqlx::query_as!(
        CommitteeRole,
        r#"
        INSERT INTO committee_roles (
            conference_id, author_id,
            committee, position, role_title,
            term_start, term_end,
            affiliation, metadata,
            creator, modifier
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        RETURNING
            id, conference_id, author_id,
            committee as "committee: CommitteeType",
            position as "position: CommitteePosition",
            role_title, term_start, term_end,
            affiliation,
            COALESCE(metadata, '{}'::jsonb) as "metadata!",
            created_at, updated_at
        "#,
        new_role.conference_id,
        new_role.author_id,
        new_role.committee as CommitteeType,
        position as CommitteePosition,
        new_role.role_title,
        new_role.term_start,
        new_role.term_end,
        new_role.affiliation,
        new_role.metadata.unwrap_or_else(|| serde_json::json!({})),
        new_role.creator,
        new_role.modifier
    )
    .fetch_one(&pool)
    .await
    .map_err(|e| {
        tracing::error!("Failed to create committee role: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    Ok((StatusCode::CREATED, Json(role)))
}

#[utoipa::path(
    put,
    path = "/committees/{id}",
    tag = "committees",
    params(("id" = Uuid, Path, description = "Committee role ID")),
    request_body = UpdateCommitteeRole,
    responses(
        (status = 200, description = "Committee role updated", body = CommitteeRole),
        (status = 401, description = "Unauthorized - missing or invalid token"),
        (status = 404, description = "Committee role not found"),
        (status = 500, description = "Internal server error")
    ),
    security(
        ("bearer_auth" = [])
    )
)]
pub async fn update_committee_role(
    State(pool): State<Pool<Postgres>>,
    Path(id): Path<Uuid>,
    Json(update): Json<UpdateCommitteeRole>,
) -> Result<Json<CommitteeRole>, StatusCode> {
    // First fetch the existing role
    let existing = sqlx::query_as!(
        CommitteeRole,
        r#"
        SELECT
            id, conference_id, author_id,
            committee as "committee: CommitteeType",
            position as "position: CommitteePosition",
            role_title, term_start, term_end,
            affiliation,
            COALESCE(metadata, '{}'::jsonb) as "metadata!",
            created_at, updated_at
        FROM committee_roles
        WHERE id = $1
        "#,
        id
    )
    .fetch_optional(&pool)
    .await
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
    .ok_or(StatusCode::NOT_FOUND)?;

    // Update with provided values or keep existing
    let role = sqlx::query_as!(
        CommitteeRole,
        r#"
        UPDATE committee_roles
        SET
            committee = $1,
            position = $2,
            role_title = $3,
            term_start = $4,
            term_end = $5,
            affiliation = $6,
            metadata = $7,
            modifier = $8,
            updated_at = NOW()
        WHERE id = $9
        RETURNING
            id, conference_id, author_id,
            committee as "committee: CommitteeType",
            position as "position: CommitteePosition",
            role_title, term_start, term_end,
            affiliation,
            COALESCE(metadata, '{}'::jsonb) as "metadata!",
            created_at, updated_at
        "#,
        update.committee.unwrap_or(existing.committee) as CommitteeType,
        update.position.unwrap_or(existing.position) as CommitteePosition,
        update.role_title.or(existing.role_title),
        update.term_start.or(existing.term_start),
        update.term_end.or(existing.term_end),
        update.affiliation.or(existing.affiliation),
        update.metadata.unwrap_or(existing.metadata),
        update.modifier,
        id
    )
    .fetch_one(&pool)
    .await
    .map_err(|e| {
        tracing::error!("Failed to update committee role: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    Ok(Json(role))
}

#[utoipa::path(
    delete,
    path = "/committees/{id}",
    tag = "committees",
    params(("id" = Uuid, Path, description = "Committee role ID")),
    responses(
        (status = 204, description = "Committee role deleted"),
        (status = 401, description = "Unauthorized - missing or invalid token"),
        (status = 404, description = "Committee role not found"),
        (status = 500, description = "Internal server error")
    ),
    security(
        ("bearer_auth" = [])
    )
)]
pub async fn delete_committee_role(
    State(pool): State<Pool<Postgres>>,
    Path(id): Path<Uuid>,
) -> Result<StatusCode, StatusCode> {
    let result = sqlx::query!("DELETE FROM committee_roles WHERE id = $1", id)
        .execute(&pool)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    if result.rows_affected() == 0 {
        return Err(StatusCode::NOT_FOUND);
    }

    Ok(StatusCode::NO_CONTENT)
}
