use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    Json,
};
use serde::Deserialize;
use sqlx::{Pool, Postgres};
use utoipa::IntoParams;
use uuid::Uuid;

use crate::models::{Author, CreateAuthor, UpdateAuthor, normalize_name};

#[derive(Debug, Deserialize, IntoParams)]
pub struct AuthorQuery {
    /// Search term for author name
    pub search: Option<String>,
    /// Maximum number of results (default: 100)
    pub limit: Option<i64>,
    /// Number of results to skip (default: 0)
    pub offset: Option<i64>,
}

#[utoipa::path(
    get,
    path = "/authors",
    tag = "authors",
    params(AuthorQuery),
    responses(
        (status = 200, description = "List of authors", body = Vec<Author>),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn list_authors(
    State(pool): State<Pool<Postgres>>,
    Query(query): Query<AuthorQuery>,
) -> Result<Json<Vec<Author>>, StatusCode> {
    let limit = query.limit.unwrap_or(100);
    let offset = query.offset.unwrap_or(0);

    let authors = if let Some(search) = &query.search {
        let search_pattern = format!("%{}%", search);
        sqlx::query_as!(
            Author,
            r#"
            SELECT
                id, full_name, family_name, given_name,
                normalized_name, orcid, homepage_url, affiliation,
                created_at, updated_at
            FROM authors
            WHERE full_name ILIKE $1
               OR family_name ILIKE $1
               OR given_name ILIKE $1
               OR normalized_name ILIKE $1
            ORDER BY family_name, given_name
            LIMIT $2 OFFSET $3
            "#,
            search_pattern,
            limit,
            offset
        )
        .fetch_all(&pool)
        .await
    } else {
        sqlx::query_as!(
            Author,
            r#"
            SELECT
                id, full_name, family_name, given_name,
                normalized_name, orcid, homepage_url, affiliation,
                created_at, updated_at
            FROM authors
            ORDER BY family_name, given_name
            LIMIT $1 OFFSET $2
            "#,
            limit,
            offset
        )
        .fetch_all(&pool)
        .await
    }
    .map_err(|e| {
        tracing::error!("Failed to fetch authors: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    Ok(Json(authors))
}

#[utoipa::path(
    get,
    path = "/authors/{id}",
    tag = "authors",
    params(("id" = Uuid, Path, description = "Author ID")),
    responses(
        (status = 200, description = "Author found", body = Author),
        (status = 404, description = "Author not found")
    )
)]
pub async fn get_author(
    State(pool): State<Pool<Postgres>>,
    Path(id): Path<Uuid>,
) -> Result<Json<Author>, StatusCode> {
    let author = sqlx::query_as!(
        Author,
        r#"
        SELECT
            id, full_name, family_name, given_name,
            normalized_name, orcid, homepage_url, affiliation,
            created_at, updated_at
        FROM authors
        WHERE id = $1
        "#,
        id
    )
    .fetch_one(&pool)
    .await
    .map_err(|_| StatusCode::NOT_FOUND)?;

    Ok(Json(author))
}

#[utoipa::path(
    post,
    path = "/authors",
    tag = "authors",
    request_body = CreateAuthor,
    responses(
        (status = 201, description = "Author created", body = Author),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn create_author(
    State(pool): State<Pool<Postgres>>,
    Json(new_author): Json<CreateAuthor>,
) -> Result<(StatusCode, Json<Author>), StatusCode> {
    let normalized = normalize_name(&new_author.full_name);

    let author = sqlx::query_as!(
        Author,
        r#"
        INSERT INTO authors (
            full_name, family_name, given_name,
            normalized_name, orcid, homepage_url, affiliation,
            creator, modifier
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING
            id, full_name, family_name, given_name,
            normalized_name, orcid, homepage_url, affiliation,
            created_at, updated_at
        "#,
        new_author.full_name,
        new_author.family_name,
        new_author.given_name,
        normalized,
        new_author.orcid,
        new_author.homepage_url,
        new_author.affiliation,
        new_author.creator,
        new_author.modifier
    )
    .fetch_one(&pool)
    .await
    .map_err(|e| {
        tracing::error!("Failed to create author: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    Ok((StatusCode::CREATED, Json(author)))
}

#[utoipa::path(
    put,
    path = "/authors/{id}",
    tag = "authors",
    params(("id" = Uuid, Path, description = "Author ID")),
    request_body = UpdateAuthor,
    responses(
        (status = 200, description = "Author updated", body = Author),
        (status = 404, description = "Author not found"),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn update_author(
    State(pool): State<Pool<Postgres>>,
    Path(id): Path<Uuid>,
    Json(update): Json<UpdateAuthor>,
) -> Result<Json<Author>, StatusCode> {
    // First fetch the existing author
    let existing = sqlx::query_as!(
        Author,
        r#"
        SELECT
            id, full_name, family_name, given_name,
            normalized_name, orcid, homepage_url, affiliation,
            created_at, updated_at
        FROM authors
        WHERE id = $1
        "#,
        id
    )
    .fetch_optional(&pool)
    .await
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
    .ok_or(StatusCode::NOT_FOUND)?;

    let new_full_name = update.full_name.unwrap_or(existing.full_name);
    let normalized = normalize_name(&new_full_name);

    // Update with provided values or keep existing
    let author = sqlx::query_as!(
        Author,
        r#"
        UPDATE authors
        SET
            full_name = $1,
            family_name = $2,
            given_name = $3,
            normalized_name = $4,
            orcid = $5,
            homepage_url = $6,
            affiliation = $7,
            modifier = $8,
            updated_at = NOW()
        WHERE id = $9
        RETURNING
            id, full_name, family_name, given_name,
            normalized_name, orcid, homepage_url, affiliation,
            created_at, updated_at
        "#,
        new_full_name,
        update.family_name.or(existing.family_name),
        update.given_name.or(existing.given_name),
        normalized,
        update.orcid.or(existing.orcid),
        update.homepage_url.or(existing.homepage_url),
        update.affiliation.or(existing.affiliation),
        update.modifier,
        id
    )
    .fetch_one(&pool)
    .await
    .map_err(|e| {
        tracing::error!("Failed to update author: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    Ok(Json(author))
}

#[utoipa::path(
    delete,
    path = "/authors/{id}",
    tag = "authors",
    params(("id" = Uuid, Path, description = "Author ID")),
    responses(
        (status = 204, description = "Author deleted"),
        (status = 404, description = "Author not found"),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn delete_author(
    State(pool): State<Pool<Postgres>>,
    Path(id): Path<Uuid>,
) -> Result<StatusCode, StatusCode> {
    let result = sqlx::query!("DELETE FROM authors WHERE id = $1", id)
        .execute(&pool)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    if result.rows_affected() == 0 {
        return Err(StatusCode::NOT_FOUND);
    }

    Ok(StatusCode::NO_CONTENT)
}
