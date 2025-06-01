use dotenvy::dotenv;
use sqlx::postgres::PgPoolOptions;
use sqlx::{Pool, Postgres};
use uuid::Uuid;
use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};
 
use axum::{
    extract::{Extension, Path}, 
    routing::get,
    Router,
    Json,
    http::StatusCode,
};
use tracing::{info, Level};
use tracing_subscriber;

// Struct for conference response
#[derive(Serialize)]
struct Conference {
    id: Uuid,
    venue: String,
    year: i32,
    start_date: Option<chrono::NaiveDate>,
    end_date: Option<chrono::NaiveDate>,
    city: Option<String>,
    country: Option<String>,
    country_code: Option<String>,
    is_virtual: bool,
    is_hybrid: bool,
    timezone: Option<String>,
    venue_name: Option<String>,
    website_url: Option<String>,
    proceedings_url: Option<String>,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>
}

// Struct for creating a new conference
#[derive(Deserialize)]
struct CreateConference {
    venue: String,
    year: i32,
    start_date: Option<chrono::NaiveDate>,
    end_date: Option<chrono::NaiveDate>,
    city: Option<String>,
    country: Option<String>,
    country_code: Option<String>,
    is_virtual: Option<bool>,
    is_hybrid: Option<bool>,
    timezone: Option<String>,
    venue_name: Option<String>,
    website_url: Option<String>,
    proceedings_url: Option<String>,
    creator: String,
    modifier: String
}

// Struct for updating a conference
#[derive(Deserialize)]
struct UpdateConference {
    venue: String,
    year: i32,
    start_date: Option<chrono::NaiveDate>,
    end_date: Option<chrono::NaiveDate>,
    city: Option<String>,
    country: Option<String>,
    country_code: Option<String>,
    is_virtual: Option<bool>,
    is_hybrid: Option<bool>,
    timezone: Option<String>,
    venue_name: Option<String>,
    website_url: Option<String>,
    proceedings_url: Option<String>
}

#[tokio::main]
async fn main() -> Result<(), sqlx::Error> {
    dotenv().ok();
    let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
    let pool = PgPoolOptions::new().connect(&url).await?;
 
    tracing_subscriber::fmt().with_max_level(Level::INFO).init();
 
    let app = Router::new()
        // Root route
        .route("/", get(root))
        .route("/conferences", get(get_conferences).post(create_conference))
        .route("/conferences/:id", get(get_conference).put(update_conference).delete(delete_conference))
        // Extension Layer
        .layer(Extension(pool));
 
    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await.unwrap();
 
    info!("Server is running on http://0.0.0.0:3000");
    axum::serve(listener, app).await.unwrap();
 
    Ok(())
}
 
// handler for GET /
async fn root() -> &'static str {
    "Hello, world!"
}

// handler for GET /conferences
async fn get_conferences(
    Extension(pool): Extension<Pool<Postgres>>
) -> Result<Json<Vec<Conference>>, StatusCode> {
    let conferences = sqlx::query_as!(
        Conference,
        r#"
        SELECT 
            id, venue, year, start_date, end_date,
            city, country, country_code, is_virtual, is_hybrid,
            timezone, venue_name, website_url, proceedings_url,
            created_at, updated_at
        FROM conferences
        "#
    )
    .fetch_all(&pool)
    .await
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
 
    Ok(Json(conferences))
}

// handler for GET /conferences/:id
async fn get_conference(
    Extension(pool): Extension<Pool<Postgres>>,
    Path(id): Path<Uuid>,
) -> Result<Json<Conference>, StatusCode> {
    let conference = sqlx::query_as!(
        Conference,
        r#"
        SELECT 
            id, venue, year, start_date, end_date,
            city, country, country_code, is_virtual, is_hybrid,
            timezone, venue_name, website_url, proceedings_url,
            created_at, updated_at
        FROM conferences 
        WHERE id = $1
        "#,
        id
    )
    .fetch_one(&pool)
    .await
    .map_err(|_| StatusCode::NOT_FOUND)?;
 
    Ok(Json(conference))
}

// handler for POST /conferences
async fn create_conference(
    Extension(pool): Extension<Pool<Postgres>>,
    Json(new_conference): Json<CreateConference>,
) -> Result<Json<Conference>, StatusCode> {
    let conference = sqlx::query_as!(
        Conference,
        r#"
        INSERT INTO conferences (
            venue, year, start_date, end_date, 
            city, country, country_code, is_virtual, is_hybrid,
            timezone, venue_name, website_url, proceedings_url,
            creator, modifier
        ) 
        VALUES (
            $1, $2, $3, $4, 
            $5, $6, $7, $8, $9,
            $10, $11, $12, $13,
            $14, $15
        ) 
        RETURNING 
            id, venue, year, start_date, end_date,
            city, country, country_code, is_virtual, is_hybrid,
            timezone, venue_name, website_url, proceedings_url,
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
        new_conference.creator,
        new_conference.modifier
    )
    .fetch_one(&pool)
    .await
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
 
    Ok(Json(conference))
}

// handler for PUT /conferences/:id
async fn update_conference(
    Extension(pool): Extension<Pool<Postgres>>,
    Path(id): Path<Uuid>,
    Json(updated_conference): Json<UpdateConference>,
) -> Result<Json<Conference>, StatusCode> {
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
            updated_at = NOW()
        WHERE id = $14
        RETURNING 
            id, venue, year, start_date, end_date,
            city, country, country_code, is_virtual, is_hybrid,
            timezone, venue_name, website_url, proceedings_url,
            created_at, updated_at
        "#,
        updated_conference.venue,
        updated_conference.year,
        updated_conference.start_date,
        updated_conference.end_date,
        updated_conference.city,
        updated_conference.country,
        updated_conference.country_code,
        updated_conference.is_virtual.unwrap_or(false),
        updated_conference.is_hybrid.unwrap_or(false),
        updated_conference.timezone,
        updated_conference.venue_name,
        updated_conference.website_url,
        updated_conference.proceedings_url,
        id
    )
    .fetch_one(&pool)
    .await;
 
    match conference {
        Ok(conference) => Ok(Json(conference)),
        Err(_) => Err(StatusCode::NOT_FOUND),
    }
}

// handler for DELETE /conferences/:id
async fn delete_conference(
    Extension(pool): Extension<Pool<Postgres>>,
    Path(id): Path<Uuid>,
) -> Result<Json<serde_json::Value>, StatusCode> {
    let result = sqlx::query!("DELETE FROM conferences WHERE id = $1", id)
        .execute(&pool)
        .await;
    match result {
        Ok(_) => Ok(Json(serde_json::json! ({
            "message": "conference deleted successfully"
        }))),
        Err(_) => Err(StatusCode::NOT_FOUND),
    }
}