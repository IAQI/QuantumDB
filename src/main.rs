use dotenvy::dotenv;
use sqlx::postgres::PgPoolOptions;
use sqlx::{Pool, Postgres};
use uuid::Uuid;
use serde::{Deserialize, Serialize};
 
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
}

// Struct for creating a new conference
#[derive(Deserialize)]
struct CreateConference {
    venue: String,
    year: i32,
    creator: String,
    modifier: String,
}

// Struct for updating a conference
#[derive(Deserialize)]
struct UpdateConference {
    venue: String,
    year: i32,
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
        "SELECT id, venue, year FROM conferences"
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
        "SELECT id, venue, year FROM conferences WHERE id = $1",
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
        "INSERT INTO conferences (venue, year, creator, modifier) VALUES ($1, $2, $3, $4) RETURNING id, venue, year",
        new_conference.venue,
        new_conference.year,
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
        "UPDATE conferences SET venue = $1, year = $2 WHERE id = $3 RETURNING id, venue, year",
        updated_conference.venue,
        updated_conference.year,
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