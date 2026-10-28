use axum::{routing::get, Router};
use sqlx::{Pool, Postgres, postgres::PgPoolOptions};

/// Create a test database pool
pub async fn create_test_pool() -> Pool<Postgres> {
    dotenvy::dotenv().ok();
    let url = std::env::var("DATABASE_URL")
        .expect("DATABASE_URL must be set for tests");

    PgPoolOptions::new()
        .max_connections(5)
        .connect(&url)
        .await
        .expect("Failed to create test database pool")
}

/// Create the application router for testing
pub fn create_test_app(pool: Pool<Postgres>) -> Router {
    use quantumdb::handlers;

    Router::new()
        .route("/", get(|| async { "QuantumDB API - Test" }))
        // Conference routes
        .route("/conferences", get(handlers::list_conferences).post(handlers::create_conference))
        .route("/conferences/{id}", get(handlers::get_conference).put(handlers::update_conference).delete(handlers::delete_conference))
        // Author routes
        .route("/authors", get(handlers::list_authors).post(handlers::create_author))
        .route("/authors/{id}", get(handlers::get_author).put(handlers::update_author).delete(handlers::delete_author))
        // Publication routes
        .route("/publications", get(handlers::list_publications).post(handlers::create_publication))
        .route("/publications/{id}", get(handlers::get_publication).put(handlers::update_publication).delete(handlers::delete_publication))
        // Committee routes
        .route("/committees", get(handlers::list_committee_roles).post(handlers::create_committee_role))
        .route("/committees/{id}", get(handlers::get_committee_role).put(handlers::update_committee_role).delete(handlers::delete_committee_role))
        // Authorship routes
        .route("/authorships", get(handlers::list_authorships).post(handlers::create_authorship))
        .route("/authorships/{id}", get(handlers::get_authorship).put(handlers::update_authorship).delete(handlers::delete_authorship))
        // Bulk exports
        .route("/export/all.json", get(handlers::export_index))
        .route("/export/authors.json", get(handlers::export_authors))
        .route("/export/conferences/{slug}", get(handlers::export_conference))
        .route("/export/conferences/{slug}/talks.csv", get(handlers::export_conference_talks_csv))
        .route("/export/conferences/{slug}/posters.csv", get(handlers::export_conference_posters_csv))
        .route("/export/conferences/{slug}/committees.csv", get(handlers::export_conference_committees_csv))
        // Discovery files
        .route("/robots.txt", get(handlers::web::robots_txt))
        .route("/sitemap.xml", get(handlers::web::sitemap_xml))
        .route("/llms.txt", get(handlers::web::llms_txt))
        .with_state(pool)
}
