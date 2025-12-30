use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    Json,
};
use serde::Deserialize;
use sqlx::{Pool, Postgres};
use utoipa::IntoParams;
use uuid::Uuid;

use crate::models::{Authorship, CreateAuthorship, UpdateAuthorship};

#[derive(Debug, Deserialize, IntoParams)]
pub struct AuthorshipQuery {
    /// Filter by publication ID
    pub publication_id: Option<Uuid>,
    /// Filter by author ID
    pub author_id: Option<Uuid>,
}

#[utoipa::path(
    get,
    path = "/authorships",
    tag = "authorships",
    params(AuthorshipQuery),
    responses(
        (status = 200, description = "List of authorships", body = Vec<Authorship>),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn list_authorships(
    State(pool): State<Pool<Postgres>>,
    Query(query): Query<AuthorshipQuery>,
) -> Result<Json<Vec<Authorship>>, StatusCode> {
    let authorships = match (query.publication_id, query.author_id) {
        (Some(pub_id), Some(auth_id)) => {
            sqlx::query_as::<_, Authorship>(
                r#"SELECT id, publication_id, author_id, author_position, published_as_name, 
                   affiliation, COALESCE(metadata, '{}'::jsonb) as metadata, created_at, updated_at 
                   FROM authorships WHERE publication_id = $1 AND author_id = $2 ORDER BY author_position"#,
            )
            .bind(pub_id)
            .bind(auth_id)
            .fetch_all(&pool)
            .await
        }
        (Some(pub_id), None) => {
            sqlx::query_as::<_, Authorship>(
                r#"SELECT id, publication_id, author_id, author_position, published_as_name, 
                   affiliation, COALESCE(metadata, '{}'::jsonb) as metadata, created_at, updated_at 
                   FROM authorships WHERE publication_id = $1 ORDER BY author_position"#,
            )
            .bind(pub_id)
            .fetch_all(&pool)
            .await
        }
        (None, Some(auth_id)) => {
            sqlx::query_as::<_, Authorship>(
                r#"SELECT id, publication_id, author_id, author_position, published_as_name, 
                   affiliation, COALESCE(metadata, '{}'::jsonb) as metadata, created_at, updated_at 
                   FROM authorships WHERE author_id = $1 ORDER BY created_at DESC"#,
            )
            .bind(auth_id)
            .fetch_all(&pool)
            .await
        }
        (None, None) => {
            sqlx::query_as::<_, Authorship>(
                r#"SELECT id, publication_id, author_id, author_position, published_as_name, 
                   affiliation, COALESCE(metadata, '{}'::jsonb) as metadata, created_at, updated_at 
                   FROM authorships ORDER BY created_at DESC LIMIT 100"#,
            )
            .fetch_all(&pool)
            .await
        }
    };

    authorships
        .map(Json)
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)
}

#[utoipa::path(
    get,
    path = "/authorships/{id}",
    tag = "authorships",
    params(("id" = Uuid, Path, description = "Authorship ID")),
    responses(
        (status = 200, description = "Authorship found", body = Authorship),
        (status = 404, description = "Authorship not found")
    )
)]
pub async fn get_authorship(
    State(pool): State<Pool<Postgres>>,
    Path(id): Path<Uuid>,
) -> Result<Json<Authorship>, StatusCode> {
    sqlx::query_as::<_, Authorship>(
        r#"SELECT id, publication_id, author_id, author_position, published_as_name, 
           affiliation, COALESCE(metadata, '{}'::jsonb) as metadata, created_at, updated_at 
           FROM authorships WHERE id = $1"#
    )
        .bind(id)
        .fetch_optional(&pool)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
        .map(Json)
        .ok_or(StatusCode::NOT_FOUND)
}

#[utoipa::path(
    post,
    path = "/authorships",
    tag = "authorships",
    request_body = CreateAuthorship,
    responses(
        (status = 201, description = "Authorship created", body = Authorship),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn create_authorship(
    State(pool): State<Pool<Postgres>>,
    Json(payload): Json<CreateAuthorship>,
) -> Result<(StatusCode, Json<Authorship>), StatusCode> {
    let authorship = sqlx::query_as::<_, Authorship>(
        r#"
        INSERT INTO authorships (
            publication_id, author_id, author_position, published_as_name,
            affiliation, metadata, creator, modifier
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id, publication_id, author_id, author_position, published_as_name, 
                  affiliation, COALESCE(metadata, '{}'::jsonb) as metadata, created_at, updated_at
        "#,
    )
    .bind(&payload.publication_id)
    .bind(&payload.author_id)
    .bind(&payload.author_position)
    .bind(&payload.published_as_name)
    .bind(&payload.affiliation)
    .bind(payload.metadata.unwrap_or_else(|| serde_json::json!({})))
    .bind(&payload.creator)
    .bind(&payload.modifier)
    .fetch_one(&pool)
    .await
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    Ok((StatusCode::CREATED, Json(authorship)))
}

#[utoipa::path(
    put,
    path = "/authorships/{id}",
    tag = "authorships",
    params(("id" = Uuid, Path, description = "Authorship ID")),
    request_body = UpdateAuthorship,
    responses(
        (status = 200, description = "Authorship updated", body = Authorship),
        (status = 404, description = "Authorship not found"),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn update_authorship(
    State(pool): State<Pool<Postgres>>,
    Path(id): Path<Uuid>,
    Json(payload): Json<UpdateAuthorship>,
) -> Result<Json<Authorship>, StatusCode> {
    // First check if authorship exists
    let existing = sqlx::query_as::<_, Authorship>(
        r#"SELECT id, publication_id, author_id, author_position, published_as_name, 
           affiliation, COALESCE(metadata, '{}'::jsonb) as metadata, created_at, updated_at 
           FROM authorships WHERE id = $1"#
    )
        .bind(id)
        .fetch_optional(&pool)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
        .ok_or(StatusCode::NOT_FOUND)?;

    let authorship = sqlx::query_as::<_, Authorship>(
        r#"
        UPDATE authorships SET
            author_position = COALESCE($1, author_position),
            published_as_name = COALESCE($2, published_as_name),
            affiliation = COALESCE($3, affiliation),
            metadata = COALESCE($4, metadata),
            modifier = $5,
            updated_at = NOW()
        WHERE id = $6
        RETURNING id, publication_id, author_id, author_position, published_as_name, 
                  affiliation, COALESCE(metadata, '{}'::jsonb) as metadata, created_at, updated_at
        "#,
    )
    .bind(payload.author_position.or(Some(existing.author_position)))
    .bind(payload.published_as_name.or(Some(existing.published_as_name)))
    .bind(payload.affiliation.or(existing.affiliation))
    .bind(payload.metadata.or(Some(existing.metadata)))
    .bind(&payload.modifier)
    .bind(id)
    .fetch_one(&pool)
    .await
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    Ok(Json(authorship))
}

#[utoipa::path(
    delete,
    path = "/authorships/{id}",
    tag = "authorships",
    params(("id" = Uuid, Path, description = "Authorship ID")),
    responses(
        (status = 204, description = "Authorship deleted"),
        (status = 404, description = "Authorship not found"),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn delete_authorship(
    State(pool): State<Pool<Postgres>>,
    Path(id): Path<Uuid>,
) -> Result<StatusCode, StatusCode> {
    let result = sqlx::query("DELETE FROM authorships WHERE id = $1")
        .bind(id)
        .execute(&pool)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    if result.rows_affected() == 0 {
        Err(StatusCode::NOT_FOUND)
    } else {
        Ok(StatusCode::NO_CONTENT)
    }
}
