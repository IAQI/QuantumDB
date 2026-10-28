//! Discovery files for crawlers and AI agents: robots.txt, sitemap.xml, llms.txt.

use askama::Template;
use axum::extract::State;
use axum::http::{header, HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use sqlx::PgPool;

use crate::utils::{
    public_base_url, xml_escape, CONTACT_EMAIL, DATA_LICENSE_URL, HOW_TO_CITE, SOURCE_REPO,
};

const CACHE_CONTROL: &str = "public, max-age=3600";

fn text(content_type: &'static str, body: String) -> Response {
    (
        [
            (header::CONTENT_TYPE, HeaderValue::from_static(content_type)),
            (header::CACHE_CONTROL, HeaderValue::from_static(CACHE_CONTROL)),
        ],
        body,
    )
        .into_response()
}

fn db_err(e: sqlx::Error) -> StatusCode {
    tracing::error!("Discovery query failed: {e:?}");
    StatusCode::INTERNAL_SERVER_ERROR
}

/// Every crawler, AI crawlers included, is welcome. Only the admin routes are off limits.
pub async fn robots_txt() -> Response {
    let base = public_base_url();
    text(
        "text/plain; charset=utf-8",
        format!(
            "# QuantumDB: open data (CC0) on the QIP, QCrypt and TQC conferences.\n\
             # Agents: see {base}/llms.txt for bulk exports (one request per conference).\n\
             User-agent: *\n\
             Allow: /\n\
             Disallow: /admin/\n\
             \n\
             Sitemap: {base}/sitemap.xml\n"
        ),
    )
}

pub async fn sitemap_xml(State(pool): State<PgPool>) -> Result<Response, StatusCode> {
    let base = public_base_url();
    let conferences = sqlx::query!(
        r#"SELECT LOWER(venue) || '-' || year::text as "slug!", updated_at FROM conferences ORDER BY venue, year"#
    )
    .fetch_all(&pool)
    .await
    .map_err(db_err)?;
    let authors = sqlx::query!(r#"SELECT slug as "slug!", updated_at FROM authors ORDER BY slug"#)
        .fetch_all(&pool)
        .await
        .map_err(db_err)?;

    let mut xml = String::with_capacity(160 * (conferences.len() + authors.len() + 8));
    xml.push_str("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n");
    xml.push_str("<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n");
    let mut url = |loc: String, lastmod: Option<chrono::DateTime<chrono::Utc>>| {
        xml.push_str("  <url><loc>");
        xml.push_str(&xml_escape(&loc));
        xml.push_str("</loc>");
        if let Some(t) = lastmod {
            xml.push_str("<lastmod>");
            xml.push_str(&t.format("%Y-%m-%d").to_string());
            xml.push_str("</lastmod>");
        }
        xml.push_str("</url>\n");
    };
    for path in ["/", "/conferences", "/authors", "/publications", "/about", "/llms.txt"] {
        url(format!("{base}{path}"), None);
    }
    for c in conferences {
        url(format!("{base}/conferences/{}", c.slug), Some(c.updated_at));
    }
    for a in authors {
        url(format!("{base}/authors/{}", a.slug), Some(a.updated_at));
    }
    xml.push_str("</urlset>\n");
    Ok(text("application/xml; charset=utf-8", xml))
}

#[derive(Template)]
#[template(path = "llms.txt")]
struct LlmsTxtTemplate<'a> {
    base: &'a str,
    source_repo: &'a str,
    license_url: &'a str,
    how_to_cite: &'a str,
    contact: &'a str,
    conference_count: i64,
    talk_count: i64,
    poster_count: i64,
    author_count: i64,
    committee_count: i64,
    qip_years: String,
    qcrypt_years: String,
    tqc_years: String,
}

pub async fn llms_txt(State(pool): State<PgPool>) -> Result<Response, StatusCode> {
    let counts = sqlx::query!(
        r#"
        SELECT
            (SELECT COUNT(*) FROM conferences) as "conferences!",
            (SELECT COUNT(*) FROM publications WHERE paper_type <> 'poster') as "talks!",
            (SELECT COUNT(*) FROM publications WHERE paper_type = 'poster') as "posters!",
            (SELECT COUNT(*) FROM authors) as "authors!",
            (SELECT COUNT(*) FROM committee_roles) as "committee_roles!"
        "#
    )
    .fetch_one(&pool)
    .await
    .map_err(db_err)?;

    let spans = sqlx::query!(
        r#"SELECT venue, MIN(year) as "first!", MAX(year) as "last!" FROM conferences GROUP BY venue"#
    )
    .fetch_all(&pool)
    .await
    .map_err(db_err)?;
    let years = |venue: &str| {
        spans
            .iter()
            .find(|s| s.venue == venue)
            .map(|s| format!("{}–{}", s.first, s.last))
            .unwrap_or_else(|| "years vary".to_string())
    };

    let body = LlmsTxtTemplate {
        base: public_base_url(),
        source_repo: SOURCE_REPO,
        license_url: DATA_LICENSE_URL,
        how_to_cite: HOW_TO_CITE,
        contact: CONTACT_EMAIL,
        conference_count: counts.conferences,
        talk_count: counts.talks,
        poster_count: counts.posters,
        author_count: counts.authors,
        committee_count: counts.committee_roles,
        qip_years: years("QIP"),
        qcrypt_years: years("QCRYPT"),
        tqc_years: years("TQC"),
    }
    .render()
    .map_err(|e| {
        tracing::error!("llms.txt template error: {e}");
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    Ok(text("text/markdown; charset=utf-8", body))
}
