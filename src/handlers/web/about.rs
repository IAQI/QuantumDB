use askama::Template;
use axum::http::StatusCode;
use axum::response::{Html, IntoResponse, Response};

#[derive(Template)]
#[template(path = "about.html")]
struct AboutTemplate {
    json_ld: String,
}

pub async fn about() -> Result<Response, StatusCode> {
    let template = AboutTemplate {
        json_ld: crate::utils::json_ld(&crate::utils::dataset_json_ld()),
    };

    match template.render() {
        Ok(html) => Ok(Html(html).into_response()),
        Err(e) => {
            tracing::error!("Template error: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}
