use askama::Template;
use axum::extract::{Query, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{Html, IntoResponse, Response};
use serde::Deserialize;
use sqlx::PgPool;

#[derive(Template)]
#[template(path = "publications_list.html")]
struct PublicationsListTemplate {
    publications: Vec<PublicationListItem>,
    search_term: String,
}

#[derive(Template)]
#[template(path = "publications_table_partial.html")]
struct PublicationsTablePartialTemplate {
    publications: Vec<PublicationListItem>,
    search_term: String,
}

struct PublicationListItem {
    title: String,
    conference_venue: String,
    conference_year: i32,
    conference_slug: String,
    paper_type: String,
    authors: Vec<AuthorRef>,
    arxiv_ids: Vec<String>,
    abstract_text: String,
    video_url: String,
    award: String,
}

struct AuthorRef {
    slug: String,
    name: String,
    is_speaker: bool,
}

#[derive(Deserialize)]
pub struct PublicationSearchParams {
    #[serde(default)]
    search: String,
}

/// Full-text search over publication titles, abstracts, and author names.
///
/// Uses the extended `search_vector` (title=A, abstract=B, author names=C). The
/// query ORs an `english` and a `simple` tsquery so author surnames that the
/// english stemmer would mangle still match (author names are stored `simple`).
/// An empty search lists recent publications.
pub async fn publications_list(
    Query(params): Query<PublicationSearchParams>,
    State(pool): State<PgPool>,
    headers: HeaderMap,
) -> Result<Response, StatusCode> {
    let publications = sqlx::query!(
        r#"
        SELECT
            p.title,
            c.venue as "venue!",
            c.year  as "year!",
            LOWER(c.venue) || '-' || c.year::text as "conference_slug!",
            p.paper_type::text as "paper_type!",
            COALESCE(
                array_agg(a.slug ORDER BY au.author_position) FILTER (WHERE a.id IS NOT NULL),
                ARRAY[]::text[]
            ) as "author_slugs!",
            COALESCE(
                array_agg(a.full_name ORDER BY au.author_position) FILTER (WHERE a.id IS NOT NULL),
                ARRAY[]::text[]
            ) as "author_names!",
            COALESCE(
                array_agg(COALESCE(a.id = p.presenter_author_id, false) ORDER BY au.author_position)
                    FILTER (WHERE a.id IS NOT NULL),
                ARRAY[]::boolean[]
            ) as "author_is_speaker!",
            COALESCE(p.arxiv_ids, ARRAY[]::text[]) as "arxiv_ids!",
            COALESCE(p.abstract, '') as "abstract_text!",
            COALESCE(p.video_url, '') as "video_url!",
            COALESCE(p.award, '') as "award!"
        FROM publications p
        JOIN conferences c ON c.id = p.conference_id
        LEFT JOIN authorships au ON au.publication_id = p.id
        LEFT JOIN authors a ON a.id = au.author_id
        WHERE $1 = ''
           OR p.search_vector @@ plainto_tsquery('english', $1)
           OR p.search_vector @@ plainto_tsquery('simple', $1)
        GROUP BY p.id, p.title, c.venue, c.year, p.paper_type, p.arxiv_ids, p.abstract, p.video_url, p.award
        ORDER BY
            ts_rank(p.search_vector, plainto_tsquery('english', $1))
              + ts_rank(p.search_vector, plainto_tsquery('simple', $1)) DESC,
            c.year DESC,
            p.title
        LIMIT 100
        "#,
        params.search
    )
    .fetch_all(&pool)
    .await
    .map_err(|e| {
        tracing::error!("Database error: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?
    .into_iter()
    .map(|row| {
        let authors: Vec<AuthorRef> = row
            .author_slugs
            .into_iter()
            .zip(row.author_names)
            .zip(row.author_is_speaker)
            .map(|((slug, name), is_speaker)| AuthorRef {
                slug,
                name,
                is_speaker,
            })
            .collect();
        PublicationListItem {
            title: row.title,
            conference_venue: row.venue,
            conference_year: row.year,
            conference_slug: row.conference_slug,
            paper_type: row.paper_type,
            authors,
            arxiv_ids: row.arxiv_ids,
            abstract_text: row.abstract_text,
            video_url: row.video_url,
            award: row.award,
        }
    })
    .collect();

    // HTMX requests get just the results table; full requests get the whole page.
    let is_htmx = headers.get("hx-request").is_some();

    let html = if is_htmx {
        PublicationsTablePartialTemplate {
            publications,
            search_term: params.search,
        }
        .render()
    } else {
        PublicationsListTemplate {
            publications,
            search_term: params.search,
        }
        .render()
    };

    match html {
        Ok(html) => Ok(Html(html).into_response()),
        Err(e) => {
            tracing::error!("Template error: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}
