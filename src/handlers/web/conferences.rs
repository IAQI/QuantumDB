use askama::Template;
use axum::extract::{Path, Query, State};
use axum::http::{StatusCode, HeaderMap};
use axum::response::{Html, IntoResponse, Response};
use serde::Deserialize;
use sqlx::{PgPool, FromRow};
use uuid::Uuid;

#[derive(Template)]
#[template(path = "conferences_list.html")]
struct ConferencesListTemplate {
    conferences: Vec<ConferenceListItemDisplay>,
}

#[derive(Template)]
#[template(path = "conferences_table_partial.html")]
struct ConferencesTablePartialTemplate {
    conferences: Vec<ConferenceListItemDisplay>,
}

#[derive(FromRow)]
struct ConferenceListItem {
    venue: String,
    year: i32,
    slug: String,
    city: Option<String>,
    country: Option<String>,
    start_date: Option<chrono::NaiveDate>,
    publication_count: i64,
    committee_member_count: i64,
    acceptance_rate: String,
}

struct ConferenceListItemDisplay {
    slug: String,
    venue: String,
    year: i32,
    location: String,
    start_date: String,
    publication_count: i64,
    committee_member_count: i64,
    acceptance_rate: String,
}

#[derive(Template)]
#[template(path = "conference_detail.html")]
struct ConferenceDetailTemplate {
    conference: ConferenceDetail,
    publications: Vec<PublicationItem>,
    committee_by_type: Vec<CommitteeSection>,
}

struct ConferenceDetail {
    slug: String,
    venue: String,
    year: i32,
    location: String,
    start_date: String,
    end_date: String,
    website_url: String,
    proceedings_url: String,
    is_virtual: bool,
    is_hybrid: bool,
    publication_count: i64,
    regular_paper_count: i64,
    invited_talk_count: i64,
    award_count: i64,
    committee_member_count: i64,
    unique_author_count: i64,
    submission_count: String,
    acceptance_count: String,
    acceptance_rate: String,
}

struct PublicationItem {
    title: String,
    paper_type: String,
    authors: Vec<AuthorInfo>,
    award: String,
    talk_date: String,
    talk_time: String,
    duration_minutes: String,
    arxiv_ids: Vec<String>,
    abstract_text: Option<String>,
    doi: Option<String>,
}

struct AuthorInfo {
    id: String,
    name: String,
}

#[derive(Clone)]
struct CommitteeSection {
    committee_type: String,
    members: Vec<CommitteeMember>,
}

#[derive(Clone)]
struct CommitteeMember {
    author_id: String,
    author_name: String,
    position: String,
    role_title: String,
    affiliation: String,
}

#[derive(Deserialize)]
pub struct ConferenceFilterParams {
    #[serde(default)]
    venues: String,
}

pub async fn conferences_list(
    Query(params): Query<ConferenceFilterParams>,
    State(pool): State<PgPool>,
    headers: HeaderMap,
) -> Result<Response, StatusCode> {
    // Parse venues parameter (comma-separated list)
    let venue_list: Vec<&str> = if params.venues.is_empty() {
        vec![]
    } else {
        params.venues.split(',').collect()
    };
    
    // Build dynamic query based on filter params
    let where_clause = if venue_list.is_empty() {
        String::new()
    } else {
        let placeholders: Vec<String> = (1..=venue_list.len())
            .map(|i| format!("${}", i))
            .collect();
        format!("WHERE c.venue IN ({})", placeholders.join(", "))
    };
    
    let query_str = format!(
        r#"
        SELECT 
            c.venue,
            c.year,
            CONCAT(c.venue, c.year::text) as slug,
            c.city,
            c.country,
            c.start_date,
            COALESCE(cs.publication_count, 0) as publication_count,
            COALESCE(cs.committee_member_count, 0) as committee_member_count,
            CASE 
                WHEN cs.acceptance_rate IS NOT NULL 
                THEN cs.acceptance_rate::text || '%'
                ELSE ''
            END as acceptance_rate
        FROM conferences c
        LEFT JOIN conference_stats cs ON c.id = cs.id
        {}
        ORDER BY c.year DESC, c.venue
        "#,
        where_clause
    );

    let mut query = sqlx::query_as::<_, ConferenceListItem>(&query_str);
    
    // Bind venue parameters
    for venue in &venue_list {
        query = query.bind(venue);
    }
    
    let conference_records = query
        .fetch_all(&pool)
        .await
        .map_err(|e| {
            eprintln!("Database error: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    let conferences: Vec<ConferenceListItemDisplay> = conference_records
        .into_iter()
        .map(|row| {
            let location = match (row.city.as_ref(), row.country.as_ref()) {
                (Some(city), Some(country)) => format!("{}, {}", city, country),
                (Some(city), None) => city.clone(),
                (None, Some(country)) => country.clone(),
                (None, None) => String::from("-"),
            };
            ConferenceListItemDisplay {
                slug: row.slug,
                venue: row.venue,
                year: row.year,
                location,
                start_date: row.start_date.map(|d| d.to_string()).unwrap_or_else(|| String::from("-")),
                publication_count: row.publication_count,
                committee_member_count: row.committee_member_count,
                acceptance_rate: row.acceptance_rate,
            }
        })
        .collect();

    // Check if this is an HTMX request
    let is_htmx = headers.get("hx-request").is_some();

    let html = if is_htmx {
        // Return partial template for HTMX requests
        let template = ConferencesTablePartialTemplate { conferences };
        template.render()
    } else {
        // Return full page for regular requests
        let template = ConferencesListTemplate { conferences };
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

pub async fn conference_detail(
    Path(slug): Path<String>,
    State(pool): State<PgPool>,
) -> Result<Response, StatusCode> {
    // Try to parse as UUID first, otherwise treat as slug
    let (venue, year) = if let Ok(id) = Uuid::parse_str(&slug) {
        // Get venue and year from conference ID
        let conf = sqlx::query!(
            r#"
            SELECT venue, year FROM conferences WHERE id = $1
            "#,
            id
        )
        .fetch_optional(&pool)
        .await
        .map_err(|e| {
            eprintln!("Database error: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?
        .ok_or(StatusCode::NOT_FOUND)?;
        (conf.venue, conf.year)
    } else {
        // Parse slug like "QIP2024"
        let v = slug.chars().take_while(|c| c.is_alphabetic()).collect::<String>();
        let year_str = slug.chars().skip_while(|c| c.is_alphabetic()).collect::<String>();
        let y: i32 = year_str.parse().map_err(|_| StatusCode::BAD_REQUEST)?;
        (v, y)
    };

    // Now fetch conference with a single query
    let conference = sqlx::query!(
        r#"
        SELECT 
            c.id,
            c.venue,
            c.year,
            CONCAT(c.venue, c.year::text) as slug,
            c.city,
            c.country,
            c.start_date,
            c.end_date,
            c.website_url,
            c.proceedings_url,
            c.is_virtual,
            c.is_hybrid,
            c.submission_count,
            c.acceptance_count,
            COALESCE(cs.publication_count, 0) as "publication_count!",
            COALESCE(cs.regular_paper_count, 0) as "regular_paper_count!",
            COALESCE(cs.invited_talk_count, 0) as "invited_talk_count!",
            COALESCE(cs.award_count, 0) as "award_count!",
            COALESCE(cs.committee_member_count, 0) as "committee_member_count!",
            COALESCE(cs.unique_author_count, 0) as "unique_author_count!",
            cs.acceptance_rate::text as acceptance_rate
        FROM conferences c
        LEFT JOIN conference_stats cs ON c.id = cs.id
        WHERE c.venue = $1 AND c.year = $2
        "#,
        venue,
        year
    )
    .fetch_optional(&pool)
    .await
    .map_err(|e| {
        eprintln!("Database error: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?
    .ok_or(StatusCode::NOT_FOUND)?;

    let conference_id = conference.id;
    let location = match (conference.city.as_ref(), conference.country.as_ref()) {
        (Some(city), Some(country)) => format!("{}, {}", city, country),
        (Some(city), None) => city.clone(),
        (None, Some(country)) => country.clone(),
        (None, None) => String::from("-"),
    };

    // Get publications with their IDs first
    let pub_records = sqlx::query!(
        r#"
        SELECT
            p.id,
            p.title,
            p.paper_type::text as "paper_type!",
            p.award,
            p.talk_date,
            p.talk_time,
            p.duration_minutes,
            COALESCE(p.arxiv_ids, ARRAY[]::text[]) as "arxiv_ids!",
            p.abstract as abstract_text,
            p.doi
        FROM publications p
        WHERE p.conference_id = $1
        ORDER BY
            COALESCE(p.talk_date, '9999-12-31'::date),
            COALESCE(p.talk_time, '23:59:59'::time),
            p.paper_type,
            p.title
        "#,
        conference_id
    )
    .fetch_all(&pool)
    .await
    .map_err(|e| {
        eprintln!("Database error fetching publications: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    // For each publication, get its authors
    let mut publications = Vec::new();
    for pub_record in pub_records {
        let authors = sqlx::query!(
            r#"
            SELECT
                a.id,
                a.full_name
            FROM authorships au
            JOIN authors a ON au.author_id = a.id
            WHERE au.publication_id = $1
            ORDER BY au.author_position
            "#,
            pub_record.id
        )
        .fetch_all(&pool)
        .await
        .map_err(|e| {
            eprintln!("Database error fetching authors: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?
        .into_iter()
        .map(|row| AuthorInfo {
            id: row.id.to_string(),
            name: row.full_name,
        })
        .collect();

        publications.push(PublicationItem {
            title: pub_record.title,
            paper_type: pub_record.paper_type,
            authors,
            award: pub_record.award.unwrap_or_default(),
            talk_date: pub_record.talk_date.map(|d| d.to_string()).unwrap_or_default(),
            talk_time: pub_record.talk_time.map(|t| t.format("%H:%M").to_string()).unwrap_or_default(),
            duration_minutes: pub_record.duration_minutes.map(|d| d.to_string()).unwrap_or_default(),
            arxiv_ids: pub_record.arxiv_ids,
            abstract_text: pub_record.abstract_text,
            doi: pub_record.doi,
        });
    }

    // Get committee members grouped by type
    let committee_members = sqlx::query!(
        r#"
        SELECT 
            cr.committee::text as "committee_type!",
            cr.position::text as "position!",
            COALESCE(cr.role_title, '') as "role_title!",
            COALESCE(cr.affiliation, '') as "affiliation!",
            a.id as "author_id!",
            a.full_name as "author_name!"
        FROM committee_roles cr
        JOIN authors a ON cr.author_id = a.id
        WHERE cr.conference_id = $1
        ORDER BY cr.committee, cr.position, a.full_name
        "#,
        conference_id
    )
    .fetch_all(&pool)
    .await
    .map_err(|e| {
        eprintln!("Database error fetching committees: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    // Group by committee type
    let mut committee_by_type: Vec<CommitteeSection> = Vec::new();
    let mut current_type: Option<String> = None;
    let mut current_members: Vec<CommitteeMember> = Vec::new();

    for row in committee_members {
        if current_type.as_ref() != Some(&row.committee_type) {
            if let Some(ctype) = current_type {
                committee_by_type.push(CommitteeSection {
                    committee_type: ctype,
                    members: current_members.clone(),
                });
                current_members.clear();
            }
            current_type = Some(row.committee_type.clone());
        }

        current_members.push(CommitteeMember {
            author_id: row.author_id.to_string(),
            author_name: row.author_name,
            position: row.position,
            role_title: row.role_title,
            affiliation: row.affiliation,
        });
    }

    // Add the last group
    if let Some(ctype) = current_type {
        committee_by_type.push(CommitteeSection {
            committee_type: ctype,
            members: current_members,
        });
    }

    let template = ConferenceDetailTemplate {
        conference: ConferenceDetail {
            slug: conference.slug.unwrap_or_default(),
            venue: conference.venue,
            year: conference.year,
            location,
            start_date: conference.start_date.map(|d| d.to_string()).unwrap_or_else(|| String::from("-")),
            end_date: conference.end_date.map(|d| d.to_string()).unwrap_or_else(|| String::from("-")),
            website_url: conference.website_url.unwrap_or_default(),
            proceedings_url: conference.proceedings_url.unwrap_or_default(),
            is_virtual: conference.is_virtual.unwrap_or(false),
            is_hybrid: conference.is_hybrid.unwrap_or(false),
            publication_count: conference.publication_count,
            regular_paper_count: conference.regular_paper_count,
            invited_talk_count: conference.invited_talk_count,
            award_count: conference.award_count,
            committee_member_count: conference.committee_member_count,
            unique_author_count: conference.unique_author_count,
            submission_count: conference.submission_count.map(|s| s.to_string()).unwrap_or_else(|| String::from("-")),
            acceptance_count: conference.acceptance_count.map(|a| a.to_string()).unwrap_or_else(|| String::from("-")),
            acceptance_rate: conference.acceptance_rate.map(|r| format!("{}%", r)).unwrap_or_else(|| String::from("-")),
        },
        publications,
        committee_by_type,
    };

    match template.render() {
        Ok(html) => Ok(Html(html).into_response()),
        Err(e) => {
            eprintln!("Template error: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}
