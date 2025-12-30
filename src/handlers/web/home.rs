use askama::Template;
use axum::extract::State;
use axum::http::StatusCode;
use axum::response::{Html, IntoResponse, Response};
use sqlx::PgPool;

#[derive(Template)]
#[template(path = "home.html")]
struct HomeTemplate {
    total_authors: i64,
    total_publications: i64,
    total_conferences: i64,
    total_committee_roles: i64,
    recent_conferences: Vec<RecentConference>,
}

struct RecentConference {
    slug: String,
    venue: String,
    year: i32,
    location: String,
    start_date: String,
}

pub async fn home(State(pool): State<PgPool>) -> Result<Response, StatusCode> {
    // Get aggregate statistics from materialized views
    let stats = sqlx::query!(
        r#"
        SELECT 
            (SELECT COUNT(DISTINCT id) FROM author_stats) as "total_authors!",
            (SELECT COUNT(*) FROM publications) as "total_publications!",
            (SELECT COUNT(*) FROM conferences) as "total_conferences!",
            (SELECT COUNT(*) FROM committee_roles) as "total_committee_roles!"
        "#
    )
    .fetch_one(&pool)
    .await
    .map_err(|e| {
        eprintln!("Database error fetching stats: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    // Get recent conferences
    let recent_conferences = sqlx::query!(
        r#"
        SELECT 
            venue,
            year,
            CONCAT(venue, year::text) as slug,
            city,
            country,
            start_date
        FROM conferences
        ORDER BY year DESC, venue
        LIMIT 10
        "#
    )
    .fetch_all(&pool)
    .await
    .map_err(|e| {
        eprintln!("Database error fetching conferences: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?
    .into_iter()
    .map(|row| {
        let location = match (row.city.as_ref(), row.country.as_ref()) {
            (Some(city), Some(country)) => format!("{}, {}", city, country),
            (Some(city), None) => city.clone(),
            (None, Some(country)) => country.clone(),
            (None, None) => String::from("-"),
        };
        RecentConference {
            slug: row.slug.unwrap_or_default(),
            venue: row.venue,
            year: row.year,
            location,
            start_date: row.start_date.map(|d| d.to_string()).unwrap_or_else(|| String::from("-")),
        }
    })
    .collect();

    let template = HomeTemplate {
        total_authors: stats.total_authors,
        total_publications: stats.total_publications,
        total_conferences: stats.total_conferences,
        total_committee_roles: stats.total_committee_roles,
        recent_conferences,
    };

    match template.render() {
        Ok(html) => Ok(Html(html).into_response()),
        Err(e) => {
            eprintln!("Template error: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}
