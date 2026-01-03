use askama::Template;
use axum::http::StatusCode;
use axum::response::{Html, IntoResponse, Response};

#[derive(Template)]
#[template(path = "about.html")]
struct AboutTemplate {}

pub async fn about() -> Result<Response, StatusCode> {
    let template = AboutTemplate {};

    match template.render() {
        Ok(html) => Ok(Html(html).into_response()),
        Err(e) => {
            eprintln!("Template error: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}
