use dotenvy::dotenv;
use sqlx::postgres::PgPoolOptions;
 
use axum::{
    extract::Extension, 
    routing::get,
    Router,
};
use tracing::{info, Level};
use tracing_subscriber;
 
#[tokio::main]
async fn main() -> Result<(), sqlx::Error> {
    dotenv().ok();
    let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
    let pool = PgPoolOptions::new().connect(&url).await?;
 
    tracing_subscriber::fmt().with_max_level(Level::INFO).init();
 
    let app = Router::new()
        // Root route
        .route("/", get(root))
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