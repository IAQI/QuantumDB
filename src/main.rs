use dotenvy::dotenv;
use sqlx::postgres::PgPoolOptions;
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use axum::{
    extract::DefaultBodyLimit,
    http::{header, HeaderValue, Method},
    middleware,
    response::Json,
    routing::get,
    Router,
};
use tower_governor::{
    governor::GovernorConfigBuilder, key_extractor::SmartIpKeyExtractor, GovernorLayer,
};
use tower_http::{
    cors::CorsLayer,
    services::ServeDir,
    set_header::SetResponseHeaderLayer,
};
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
        (url = "/api/v1", description = "API v1 endpoints")
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
        handlers::list_conference_stats,
    ),
    components(schemas(
        Conference, CreateConference, UpdateConference,
        Author, CreateAuthor, UpdateAuthor,
        Publication, CreatePublication, UpdatePublication, PaperType,
        CommitteeRole, CreateCommitteeRole, UpdateCommitteeRole, CommitteeType, CommitteePosition,
        Authorship, CreateAuthorship, UpdateAuthorship,
        ConferenceStat,
    )),
    modifiers(&SecurityAddon),
    tags(
        (name = "conferences", description = "Conference management"),
        (name = "authors", description = "Author management"),
        (name = "publications", description = "Publication management"),
        (name = "committees", description = "Committee role management"),
        (name = "authorships", description = "Authorship (author-publication links) management"),
        (name = "stats", description = "Aggregated conference statistics"),
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
                        .description(Some("Bearer token authentication. Include your API token in the Authorization header as 'Bearer <token>'. Tokens must be at least 32 characters; the body is treated as opaque (any character set accepted). Required for all POST, PUT, DELETE operations and admin endpoints."))
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
    let mut api_routes = Router::new()
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
        .route("/stats/conferences", get(handlers::list_conference_stats));

    // API docs (OpenAPI spec + Swagger UI) enumerate the API surface, so they are
    // gated behind ENABLE_SWAGGER. Enabled by default for local/dev convenience;
    // set ENABLE_SWAGGER=0 (or false) in production to hide them.
    if env_flag("ENABLE_SWAGGER", true) {
        api_routes = api_routes
            .route("/openapi.json", get(|| async { Json(ApiDoc::openapi()) }))
            .merge(SwaggerUi::new("/swagger-ui").url("/api/v1/openapi.json", ApiDoc::openapi()));
    }

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
        .route("/publications", get(handlers::web::publications_list))
        .route("/about", get(handlers::web::about))
        .route("/health", get(health));

    // Protected web routes (admin operations)
    let protected_web_routes = Router::new()
        .route("/admin/refresh-stats", get(handlers::web::refresh_stats))
        .layer(middleware::from_fn(auth_middleware));

    // CORS is driven by CORS_ALLOWED_ORIGINS (comma-separated origins). When unset,
    // cross-origin browser requests are disallowed (same-origin requests are
    // unaffected). Set it to a list of origins in production, or to `*` to keep the
    // old any-origin behaviour for a fully public read API. Note: write endpoints
    // require a Bearer token, which CORS does not protect — the token is the real
    // boundary; this just controls which sites a browser may call the API from.
    let cors = {
        let cors = CorsLayer::new()
            .allow_methods([Method::GET, Method::POST, Method::PUT, Method::DELETE])
            .allow_headers([header::AUTHORIZATION, header::CONTENT_TYPE]);
        match std::env::var("CORS_ALLOWED_ORIGINS") {
            Ok(v) if v.trim() == "*" => cors.allow_origin(tower_http::cors::Any),
            Ok(v) if !v.trim().is_empty() => {
                let origins: Vec<HeaderValue> = v
                    .split(',')
                    .filter_map(|o| o.trim().parse::<HeaderValue>().ok())
                    .collect();
                cors.allow_origin(origins)
            }
            _ => {
                info!("CORS_ALLOWED_ORIGINS not set; cross-origin browser requests are disallowed");
                cors
            }
        }
    };

    // Hardening response headers applied to every response.
    //
    // The Content-Security-Policy allows the inline scripts/styles the templates rely
    // on plus the specific CDNs they load (Pico/MathJax via jsdelivr, HTMX via unpkg,
    // Google Fonts). 'unsafe-inline' is required by the existing inline handlers and
    // styles, so the CSP mainly hardens framing and restricts external origins.
    // HSTS is always sent; browsers ignore it over plain HTTP and only honour it on
    // HTTPS responses, which is exactly what we want once TLS is terminated by a proxy.
    const CSP: &str = "default-src 'self'; \
        script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net; \
        style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; \
        font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net data:; \
        img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; \
        base-uri 'self'; form-action 'self'";
    let security_headers = tower::ServiceBuilder::new()
        .layer(SetResponseHeaderLayer::if_not_present(
            header::X_FRAME_OPTIONS,
            HeaderValue::from_static("DENY"),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            header::X_CONTENT_TYPE_OPTIONS,
            HeaderValue::from_static("nosniff"),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            header::REFERRER_POLICY,
            HeaderValue::from_static("strict-origin-when-cross-origin"),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            header::HeaderName::from_static("permissions-policy"),
            HeaderValue::from_static("geolocation=(), microphone=(), camera=()"),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            header::CONTENT_SECURITY_POLICY,
            HeaderValue::from_static(CSP),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            header::STRICT_TRANSPORT_SECURITY,
            HeaderValue::from_static("max-age=31536000; includeSubDomains"),
        ));

    let app = Router::new()
        .merge(web_routes)
        .merge(protected_web_routes)
        .nest("/api/v1", api_routes.merge(protected_api_routes))
        .nest_service("/static", ServeDir::new("static"))
        .layer(cors)
        .layer(security_headers)
        // Cap request bodies; the largest legitimate payload is a ~50 KB abstract.
        .layer(DefaultBodyLimit::max(1024 * 1024))
        // Database pool state
        .with_state(pool);

    // Per-IP rate limit: 10 req/sec sustained (period = 100ms) with bursts up to 100,
    // applied outermost so over-limit requests are rejected before any handler work.
    // Behind a reverse proxy every request arrives from the proxy IP, which would
    // collapse the limit into one global bucket — set TRUST_PROXY=1 to key on the
    // X-Forwarded-For / X-Real-IP the proxy sets. Only enable it when a trusted proxy
    // actually overwrites those headers, otherwise clients can spoof them to evade limits.
    let trust_proxy = env_flag("TRUST_PROXY", false);
    let app = if trust_proxy {
        let conf = Arc::new(
            GovernorConfigBuilder::default()
                .per_millisecond(100)
                .burst_size(100)
                .use_headers()
                .key_extractor(SmartIpKeyExtractor)
                .finish()
                .expect("rate limit config is valid"),
        );
        let limiter = conf.limiter().clone();
        tokio::spawn(async move {
            let mut ticker = tokio::time::interval(Duration::from_secs(60));
            loop {
                ticker.tick().await;
                limiter.retain_recent();
            }
        });
        app.layer(GovernorLayer { config: conf })
    } else {
        let conf = Arc::new(
            GovernorConfigBuilder::default()
                .per_millisecond(100)
                .burst_size(100)
                .use_headers()
                .finish()
                .expect("rate limit config is valid"),
        );
        let limiter = conf.limiter().clone();
        tokio::spawn(async move {
            let mut ticker = tokio::time::interval(Duration::from_secs(60));
            loop {
                ticker.tick().await;
                limiter.retain_recent();
            }
        });
        app.layer(GovernorLayer { config: conf })
    };

    // Bind address is configurable (BIND_ADDR). Default 0.0.0.0:3000 keeps Docker and
    // local dev working; for a direct (non-containerised) run behind a proxy you can
    // set 127.0.0.1:3000 so only the proxy can reach the app.
    let bind_addr = std::env::var("BIND_ADDR").unwrap_or_else(|_| "0.0.0.0:3000".to_string());
    let listener = tokio::net::TcpListener::bind(&bind_addr).await.unwrap();

    info!("Server is running on http://{bind_addr}");
    // `with_connect_info` exposes the peer SocketAddr to the rate-limiter middleware
    // so it can key on client IP (also the fallback for SmartIpKeyExtractor).
    axum::serve(listener, app.into_make_service_with_connect_info::<SocketAddr>())
        .await
        .unwrap();

    Ok(())
}

// Health check endpoint
async fn health() -> &'static str {
    "OK"
}

/// Read a boolean-ish environment variable. Treats `1`/`true`/`yes`/`on`
/// (case-insensitive) as true and `0`/`false`/`no`/`off` as false; any other
/// value (or unset) yields `default`.
fn env_flag(name: &str, default: bool) -> bool {
    match std::env::var(name) {
        Ok(v) => match v.trim().to_ascii_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => true,
            "0" | "false" | "no" | "off" => false,
            _ => default,
        },
        Err(_) => default,
    }
}
