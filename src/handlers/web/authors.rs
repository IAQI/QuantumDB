use askama::Template;
use axum::extract::{Path, Query, State};
use axum::http::{StatusCode, HeaderMap};
use axum::response::{Html, IntoResponse, Response};
use serde::Deserialize;
use sqlx::PgPool;
use uuid::Uuid;

use crate::models::{PaperType, CommitteeType, CommitteePosition};

#[derive(Template)]
#[template(path = "authors_list.html")]
struct AuthorsListTemplate {
    authors: Vec<AuthorListItem>,
    search_term: String,
}

#[derive(Template)]
#[template(path = "authors_table_partial.html")]
struct AuthorsTablePartialTemplate {
    authors: Vec<AuthorListItem>,
    search_term: String,
}

struct AuthorListItem {
    id: String,
    full_name: String,
    affiliation: String,
    publication_count: i64,
    committee_role_count: i64,
    first_year: String,
    last_year: String,
}

#[derive(Template)]
#[template(path = "author_detail.html")]
struct AuthorDetailTemplate {
    author: AuthorDetail,
    publications: Vec<PublicationItem>,
    committee_roles: Vec<CommitteeRoleItem>,
    coauthors: Vec<CoauthorItem>,
}

struct AuthorDetail {
    id: String,
    full_name: String,
    family_name: String,
    given_name: String,
    affiliation: String,
    orcid: String,
    homepage_url: String,
    publication_count: i64,
    committee_role_count: i64,
    leadership_count: i64,
    venues: String,
    first_year: String,
    last_year: String,
}

struct PublicationItem {
    title: String,
    conference_venue: String,
    conference_year: i32,
    conference_slug: String,
    paper_type: String,
    coauthors: String,
    arxiv_ids: Vec<String>,
    abstract_text: Option<String>,
    doi: Option<String>,
}

struct CommitteeRoleItem {
    conference_venue: String,
    conference_year: i32,
    conference_slug: String,
    committee_type: String,
    position: String,
    role_title: String,
}

struct CoauthorItem {
    coauthor_id: String,
    coauthor_name: String,
    collaboration_count: i64,
}

#[derive(Deserialize)]
pub struct AuthorSearchParams {
    #[serde(default)]
    search: String,
}

pub async fn authors_list(
    Query(params): Query<AuthorSearchParams>,
    State(pool): State<PgPool>,
    headers: HeaderMap,
) -> Result<Response, StatusCode> {
    let search_pattern = format!("%{}%", params.search);

    let authors = sqlx::query!(
        r#"
        SELECT 
            a.id,
            a.full_name,
            COALESCE(a.affiliation, '') as "affiliation!",
            COALESCE(ast.publication_count, 0) as "publication_count!",
            COALESCE(ast.committee_role_count, 0) as "committee_role_count!",
            COALESCE(ast.first_year::text, '') as "first_year!",
            COALESCE(ast.last_year::text, '') as "last_year!"
        FROM authors a
        LEFT JOIN author_stats ast ON a.id = ast.id
        WHERE a.full_name ILIKE $1 OR a.normalized_name ILIKE $1
        ORDER BY a.full_name
        LIMIT 100
        "#,
        search_pattern
    )
    .fetch_all(&pool)
    .await
    .map_err(|e| {
        eprintln!("Database error: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?
    .into_iter()
    .map(|row| AuthorListItem {
        id: row.id.to_string(),
        full_name: row.full_name,
        affiliation: row.affiliation,
        publication_count: row.publication_count,
        committee_role_count: row.committee_role_count,
        first_year: row.first_year,
        last_year: row.last_year,
    })
    .collect();

    // Check if this is an HTMX request
    let is_htmx = headers.get("hx-request").is_some();

    let html = if is_htmx {
        // Return partial template for HTMX requests
        let template = AuthorsTablePartialTemplate {
            authors,
            search_term: params.search,
        };
        template.render()
    } else {
        // Return full page for regular requests
        let template = AuthorsListTemplate {
            authors,
            search_term: params.search,
        };
        template.render()
    };

    match html {
        Ok(html) => Ok(Html(html).into_response()),
        Err(e) => {
            eprintln!("Template error: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

pub async fn author_detail(
    Path(id): Path<String>,
    State(pool): State<PgPool>,
) -> Result<Response, StatusCode> {
    let author_id = Uuid::parse_str(&id).map_err(|_| StatusCode::BAD_REQUEST)?;

    // Get author with stats
    let author = sqlx::query!(
        r#"
        SELECT 
            a.id,
            a.full_name,
            COALESCE(a.family_name, '') as "family_name!",
            COALESCE(a.given_name, '') as "given_name!",
            COALESCE(a.affiliation, '') as "affiliation!",
            COALESCE(a.orcid, '') as "orcid!",
            COALESCE(a.homepage_url, '') as "homepage_url!",
            COALESCE(ast.publication_count, 0) as "publication_count!",
            COALESCE(ast.committee_role_count, 0) as "committee_role_count!",
            COALESCE(ast.leadership_count, 0) as "leadership_count!",
            COALESCE(array_to_string(ast.venues, ', '), '') as "venues!",
            COALESCE(ast.first_year::text, '') as "first_year!",
            COALESCE(ast.last_year::text, '') as "last_year!"
        FROM authors a
        LEFT JOIN author_stats ast ON a.id = ast.id
        WHERE a.id = $1
        "#,
        author_id
    )
    .fetch_optional(&pool)
    .await
    .map_err(|e| {
        eprintln!("Database error: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?
    .ok_or(StatusCode::NOT_FOUND)?;

    // Get publications
    let publications = sqlx::query!(
        r#"
        SELECT
            p.title,
            c.venue as "conference_venue!",
            c.year as "conference_year!",
            CONCAT(c.venue, c.year::text) as "conference_slug!",
            p.paper_type::text as "paper_type!",
            array_to_string(
                array_agg(a2.full_name ORDER BY au2.author_position)
                FILTER (WHERE a2.id != $1),
                ', '
            ) as coauthors,
            COALESCE(p.arxiv_ids, ARRAY[]::text[]) as "arxiv_ids!",
            p.abstract as abstract_text,
            p.doi
        FROM authorships au
        JOIN publications p ON au.publication_id = p.id
        JOIN conferences c ON p.conference_id = c.id
        LEFT JOIN authorships au2 ON p.id = au2.publication_id AND au2.author_id != $1
        LEFT JOIN authors a2 ON au2.author_id = a2.id
        WHERE au.author_id = $1
        GROUP BY p.id, p.title, c.venue, c.year, p.paper_type, p.arxiv_ids, p.abstract, p.doi
        ORDER BY c.year DESC, c.venue
        "#,
        author_id
    )
    .fetch_all(&pool)
    .await
    .map_err(|e| {
        eprintln!("Database error fetching publications: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?
    .into_iter()
    .map(|row| PublicationItem {
        title: row.title,
        conference_venue: row.conference_venue,
        conference_year: row.conference_year,
        conference_slug: row.conference_slug,
        paper_type: row.paper_type,
        coauthors: row.coauthors.unwrap_or_default(),
        arxiv_ids: row.arxiv_ids,
        abstract_text: row.abstract_text,
        doi: row.doi,
    })
    .collect();

    // Get committee roles
    let committee_roles = sqlx::query!(
        r#"
        SELECT 
            c.venue as "conference_venue!",
            c.year as "conference_year!",
            CONCAT(c.venue, c.year::text) as "conference_slug!",
            cr.committee::text as "committee_type!",
            cr.position::text as "position!",
            COALESCE(cr.role_title, '') as "role_title!"
        FROM committee_roles cr
        JOIN conferences c ON cr.conference_id = c.id
        WHERE cr.author_id = $1
        ORDER BY c.year DESC, c.venue, cr.committee
        "#,
        author_id
    )
    .fetch_all(&pool)
    .await
    .map_err(|e| {
        eprintln!("Database error fetching committee roles: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?
    .into_iter()
    .map(|row| CommitteeRoleItem {
        conference_venue: row.conference_venue,
        conference_year: row.conference_year,
        conference_slug: row.conference_slug,
        committee_type: row.committee_type,
        position: row.position,
        role_title: row.role_title,
    })
    .collect();

    // Get coauthors
    let coauthors = sqlx::query!(
        r#"
        SELECT 
            a.id as coauthor_id,
            a.full_name as coauthor_name,
            cp.collaboration_count
        FROM coauthor_pairs cp
        JOIN authors a ON (
            CASE 
                WHEN cp.author1_id = $1 THEN cp.author2_id
                ELSE cp.author1_id
            END = a.id
        )
        WHERE cp.author1_id = $1 OR cp.author2_id = $1
        ORDER BY cp.collaboration_count DESC, a.full_name
        LIMIT 20
        "#,
        author_id
    )
    .fetch_all(&pool)
    .await
    .map_err(|e| {
        eprintln!("Database error fetching coauthors: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?
    .into_iter()
    .map(|row| CoauthorItem {
        coauthor_id: row.coauthor_id.to_string(),
        coauthor_name: row.coauthor_name,
        collaboration_count: row.collaboration_count.unwrap_or(0),
    })
    .collect();

    let template = AuthorDetailTemplate {
        author: AuthorDetail {
            id: author.id.to_string(),
            full_name: author.full_name,
            family_name: author.family_name,
            given_name: author.given_name,
            affiliation: author.affiliation,
            orcid: author.orcid,
            homepage_url: author.homepage_url,
            publication_count: author.publication_count,
            committee_role_count: author.committee_role_count,
            leadership_count: author.leadership_count,
            venues: author.venues,
            first_year: author.first_year,
            last_year: author.last_year,
        },
        publications,
        committee_roles,
        coauthors,
    };

    match template.render() {
        Ok(html) => Ok(Html(html).into_response()),
        Err(e) => {
            eprintln!("Template error: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}
