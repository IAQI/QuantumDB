use dotenvy::dotenv;
use sqlx::postgres::PgPoolOptions;

use axum::{middleware, response::Json, routing::get, Router};
use tower_http::services::ServeDir;
use tracing::{info, Level};
use utoipa::OpenApi;
use utoipa_swagger_ui::SwaggerUi;

use quantumdb::{handlers, middleware::auth_middleware, models::*};

#[derive(OpenApi)]
#[openapi(
    info(
        title = "QuantumDB API",
        version = "0.1.0",
        description = "REST API for tracking quantum computing conferences (QIP, QCrypt, TQC), publications, authors, and committee memberships. Write operations (POST, PUT, DELETE) and admin endpoints require Bearer token authentication."
    ),
    servers(
        (url = "/api", description = "API endpoints")
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
    modifiers(&SecurityAddon),
    tags(
        (name = "conferences", description = "Conference management"),
        (name = "authors", description = "Author management"),
        (name = "publications", description = "Publication management"),
        (name = "committees", description = "Committee role management"),
        (name = "authorships", description = "Authorship (author-publication links) management"),
    )
)]
struct ApiDoc;

struct SecurityAddon;

impl utoipa::Modify for SecurityAddon {
    fn modify(&self, openapi: &mut utoipa::openapi::OpenApi) {
        use utoipa::openapi::security::{HttpAuthScheme, HttpBuilder, SecurityScheme};
        
        if let Some(components) = openapi.components.as_mut() {
            components.add_security_scheme(
                "bearer_auth",
                SecurityScheme::Http(
                    HttpBuilder::new()
                        .scheme(HttpAuthScheme::Bearer)
                        .bearer_format("token")
                        .description(Some("Bearer token authentication. Include your API token in the Authorization header as 'Bearer <token>'. Tokens must be at least 32 characters and contain only alphanumeric characters, hyphens, and underscores. Required for all POST, PUT, DELETE operations and admin endpoints."))
                        .build()
                ),
            );
        }
    }
}

#[tokio::main]
async fn main() -> Result<(), sqlx::Error> {
    dotenv().ok();
    let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
    let pool = PgPoolOptions::new().connect(&url).await?;

    tracing_subscriber::fmt().with_max_level(Level::INFO).init();

    // API routes (JSON endpoints)
    let api_routes = Router::new()
        // Conference routes (read-only)
        .route("/conferences", get(handlers::list_conferences))
        .route("/conferences/{id}", get(handlers::get_conference))
        // Author routes (read-only)
        .route("/authors", get(handlers::list_authors))
        .route("/authors/{id}", get(handlers::get_author))
        // Publication routes (read-only)
        .route("/publications", get(handlers::list_publications))
        .route("/publications/{id}", get(handlers::get_publication))
        // Committee routes (read-only)
        .route("/committees", get(handlers::list_committee_roles))
        .route("/committees/{id}", get(handlers::get_committee_role))
        // Authorship routes (read-only)
        .route("/authorships", get(handlers::list_authorships))
        .route("/authorships/{id}", get(handlers::get_authorship))
        // OpenAPI spec endpoint
        .route("/openapi.json", get(|| async { Json(ApiDoc::openapi()) }))
        // Swagger UI (will be served at /api/swagger-ui/)
        .merge(SwaggerUi::new("/swagger-ui").url("/api/openapi.json", ApiDoc::openapi()));

    // Protected API routes (require authentication)
    let protected_api_routes = Router::new()
        // Conference write operations
        .route("/conferences", axum::routing::post(handlers::create_conference))
        .route(
            "/conferences/{id}",
            axum::routing::put(handlers::update_conference)
                .delete(handlers::delete_conference),
        )
        // Author write operations
        .route("/authors", axum::routing::post(handlers::create_author))
        .route(
            "/authors/{id}",
            axum::routing::put(handlers::update_author)
                .delete(handlers::delete_author),
        )
        // Publication write operations
        .route(
            "/publications",
            axum::routing::post(handlers::create_publication),
        )
        .route(
            "/publications/{id}",
            axum::routing::put(handlers::update_publication)
                .delete(handlers::delete_publication),
        )
        // Committee write operations
        .route(
            "/committees",
            axum::routing::post(handlers::create_committee_role),
        )
        .route(
            "/committees/{id}",
            axum::routing::put(handlers::update_committee_role)
                .delete(handlers::delete_committee_role),
        )
        // Authorship write operations
        .route(
            "/authorships",
            axum::routing::post(handlers::create_authorship),
        )
        .route(
            "/authorships/{id}",
            axum::routing::put(handlers::update_authorship)
                .delete(handlers::delete_authorship),
        )
        // Apply authentication middleware to all protected routes
        .layer(middleware::from_fn(auth_middleware));

    // Web routes (HTML pages)
    let web_routes = Router::new()
        .route("/", get(handlers::web::home))
        .route("/authors", get(handlers::web::authors_list))
        .route("/authors/{id}", get(handlers::web::author_detail))
        .route("/conferences", get(handlers::web::conferences_list))
        .route("/conferences/{slug}", get(handlers::web::conference_detail))
        .route("/about", get(handlers::web::about))
        .route("/health", get(health))
        .route("/admin/refresh-stats", get(handlers::web::refresh_stats));

    // Protected web routes (admin operations) - currently none
    let protected_web_routes = Router::new()
        .layer(middleware::from_fn(auth_middleware));

    let app = Router::new()
        .merge(web_routes)
        .merge(protected_web_routes)
        .nest("/api", api_routes.merge(protected_api_routes))
        .nest_service("/static", ServeDir::new("static"))
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
