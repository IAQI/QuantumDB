use dotenvy::dotenv;
use sqlx::postgres::PgPoolOptions;

use axum::{response::Json, routing::get, Router};
use tracing::{info, Level};
use utoipa::OpenApi;
use utoipa_swagger_ui::SwaggerUi;

use quantumdb::{handlers, models::*};

#[derive(OpenApi)]
#[openapi(
    info(
        title = "QuantumDB API",
        version = "0.1.0",
        description = "REST API for tracking quantum computing conferences (QIP, QCrypt, TQC), publications, authors, and committee memberships."
    ),
    paths(
        handlers::list_conferences,
        handlers::get_conference,
        handlers::create_conference,
        handlers::update_conference,
        handlers::delete_conference,
        handlers::list_authors,
        handlers::get_author,
        handlers::create_author,
        handlers::update_author,
        handlers::delete_author,
        handlers::list_publications,
        handlers::get_publication,
        handlers::create_publication,
        handlers::update_publication,
        handlers::delete_publication,
        handlers::list_committee_roles,
        handlers::get_committee_role,
        handlers::create_committee_role,
        handlers::update_committee_role,
        handlers::delete_committee_role,
        handlers::list_authorships,
        handlers::get_authorship,
        handlers::create_authorship,
        handlers::update_authorship,
        handlers::delete_authorship,
    ),
    components(schemas(
        Conference, CreateConference, UpdateConference,
        Author, CreateAuthor, UpdateAuthor,
        Publication, CreatePublication, UpdatePublication, PaperType,
        CommitteeRole, CreateCommitteeRole, UpdateCommitteeRole, CommitteeType, CommitteePosition,
        Authorship, CreateAuthorship, UpdateAuthorship,
    )),
    tags(
        (name = "conferences", description = "Conference management"),
        (name = "authors", description = "Author management"),
        (name = "publications", description = "Publication management"),
        (name = "committees", description = "Committee role management"),
        (name = "authorships", description = "Authorship (author-publication links) management"),
    )
)]
struct ApiDoc;

#[tokio::main]
async fn main() -> Result<(), sqlx::Error> {
    dotenv().ok();
    let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
    let pool = PgPoolOptions::new().connect(&url).await?;

    tracing_subscriber::fmt().with_max_level(Level::INFO).init();

    // API routes (JSON endpoints)
    let api_routes = Router::new()
        // Conference routes
        .route(
            "/conferences",
            get(handlers::list_conferences).post(handlers::create_conference),
        )
        .route(
            "/conferences/{id}",
            get(handlers::get_conference)
                .put(handlers::update_conference)
                .delete(handlers::delete_conference),
        )
        // Author routes
        .route(
            "/authors",
            get(handlers::list_authors).post(handlers::create_author),
        )
        .route(
            "/authors/{id}",
            get(handlers::get_author)
                .put(handlers::update_author)
                .delete(handlers::delete_author),
        )
        // Publication routes
        .route(
            "/publications",
            get(handlers::list_publications).post(handlers::create_publication),
        )
        .route(
            "/publications/{id}",
            get(handlers::get_publication)
                .put(handlers::update_publication)
                .delete(handlers::delete_publication),
        )
        // Committee routes
        .route(
            "/committees",
            get(handlers::list_committee_roles).post(handlers::create_committee_role),
        )
        .route(
            "/committees/{id}",
            get(handlers::get_committee_role)
                .put(handlers::update_committee_role)
                .delete(handlers::delete_committee_role),
        )
        // Authorship routes
        .route(
            "/authorships",
            get(handlers::list_authorships).post(handlers::create_authorship),
        )
        .route(
            "/authorships/{id}",
            get(handlers::get_authorship)
                .put(handlers::update_authorship)
                .delete(handlers::delete_authorship),
        )
        // OpenAPI spec endpoint
        .route("/openapi.json", get(|| async { Json(ApiDoc::openapi()) }))
        // Swagger UI (will be served at /api/swagger-ui/)
        .merge(SwaggerUi::new("/swagger-ui").url("/api/openapi.json", ApiDoc::openapi()));

    // Web routes (HTML pages)
    let web_routes = Router::new()
        .route("/", get(handlers::web::home))
        .route("/authors", get(handlers::web::authors_list))
        .route("/authors/{id}", get(handlers::web::author_detail))
        .route("/conferences", get(handlers::web::conferences_list))
        .route("/conferences/{slug}", get(handlers::web::conference_detail))
        .route("/admin/refresh-stats", get(handlers::web::refresh_stats))
        .route("/health", get(health));

    let app = Router::new()
        .merge(web_routes)
        .nest("/api", api_routes)
        // Database pool state
        .with_state(pool);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await.unwrap();

    info!("Server is running on http://0.0.0.0:3000");
    info!("Web interface available at http://0.0.0.0:3000/");
    info!("API documentation at http://0.0.0.0:3000/api/swagger-ui/");
    axum::serve(listener, app).await.unwrap();

    Ok(())
}

// Health check endpoint
async fn health() -> &'static str {
    "OK"
}
