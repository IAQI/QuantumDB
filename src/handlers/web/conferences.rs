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
    talk_count: i64,
    poster_count: i64,
    committee_member_count: i64,
    acceptance_rate: Option<f64>,
    registered_participants: Option<i32>,
}

struct ConferenceListItemDisplay {
    slug: String,
    venue: String,
    year: i32,
    location: String,
    talk_count: i64,
    poster_count: i64,
    committee_member_count: i64,
    acceptance_rate: String,
    registered_participants: String,
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
    archive_url: String,
    proceedings_url: String,
    is_virtual: bool,
    is_hybrid: bool,
    talk_count: i64,
    poster_count: i64,
    regular_paper_count: i64,
    invited_talk_count: i64,
    award_count: i64,
    committee_member_count: i64,
    unique_author_count: i64,
    submission_count: String,
    acceptance_count: String,
    acceptance_rate: String,
    /// Stats announced at the business meeting (None if not recorded).
    business_meeting: Option<BusinessMeetingView>,
}

/// Pre-formatted business-meeting figures for display. Each field is an empty
/// string when that figure wasn't announced/recorded; the template renders a
/// line only when its value is non-empty.
struct BusinessMeetingView {
    meeting_date: String,
    registered_participants: String,
    onsite_participants: String,
    countries_represented: String,
    talk_submissions: String,
    talks_accepted: String,
    posters_submitted: String,
    posters_accepted: String,
    acceptance_rate: String,
    notes: String,
    /// Links to the business-meeting slide decks (PC report, local report, …).
    slides: Vec<SlideLink>,
}

struct SlideLink {
    label: String,
    url: String,
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
    abstract_text: String,
    video_url: String,
    /// Name of a non-author stand-in presenter (from metadata.presenter_name);
    /// empty when the talk was presented by one of its authors.
    presenter_name: String,
}

struct AuthorInfo {
    slug: String,
    name: String,
    is_speaker: bool,
}

/// Spell out the compact committee-type enum for display headings.
fn committee_full_label(c: &str) -> &str {
    match c {
        "PC" => "Program Committee",
        "SC" => "Steering Committee",
        "OC" => "Organizing Committee",
        x => x,
    }
}

#[derive(Clone)]
struct CommitteeSection {
    committee_label: String,
    members: Vec<CommitteeMember>,
}

#[derive(Clone)]
struct CommitteeMember {
    author_slug: String,
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
            LOWER(c.venue) || '-' || c.year::text as slug,
            c.city,
            c.country,
            COALESCE(pc.talk_count, 0) as talk_count,
            COALESCE(pc.poster_count, 0) as poster_count,
            COALESCE(cs.committee_member_count, 0) as committee_member_count,
            COALESCE(
                bm.acceptance_rate,
                ROUND(bm.talks_accepted::numeric / NULLIF(bm.talk_submissions, 0) * 100, 1)
            )::float8 as acceptance_rate,
            bm.registered_participants as registered_participants
        FROM conferences c
        LEFT JOIN conference_stats cs ON c.id = cs.id
        LEFT JOIN (
            SELECT conference_id,
                   COUNT(*) FILTER (WHERE paper_type <> 'poster') AS talk_count,
                   COUNT(*) FILTER (WHERE paper_type =  'poster') AS poster_count
            FROM publications
            GROUP BY conference_id
        ) pc ON pc.conference_id = c.id
        LEFT JOIN conference_business_meetings bm ON bm.conference_id = c.id
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
            tracing::error!("Database error: {}", e);
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
                talk_count: row.talk_count,
                poster_count: row.poster_count,
                committee_member_count: row.committee_member_count,
                acceptance_rate: row
                    .acceptance_rate
                    .map(|r| format!("{}%", r))
                    .unwrap_or_default(),
                registered_participants: row
                    .registered_participants
                    .map(|n| n.to_string())
                    .unwrap_or_default(),
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
            tracing::error!("Template error: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

pub async fn conference_detail(
    Path(slug): Path<String>,
    State(pool): State<PgPool>,
) -> Result<Response, StatusCode> {
    // Slug formats accepted: "qip-2024" (canonical) and legacy "QIP2024".
    let (venue, year) = crate::utils::parse_conference_slug(&slug)
        .ok_or(StatusCode::NOT_FOUND)?;

    // Now fetch conference with a single query
    let conference = sqlx::query!(
        r#"
        SELECT
            c.id,
            c.venue,
            c.year,
            LOWER(c.venue) || '-' || c.year::text as slug,
            c.city,
            c.country,
            c.start_date,
            c.end_date,
            c.website_url,
            c.archive_url,
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
        tracing::error!("Database error: {}", e);
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
            p.presenter_author_id,
            COALESCE(p.arxiv_ids, ARRAY[]::text[]) as "arxiv_ids!",
            COALESCE(p.abstract, '') as "abstract_text!",
            COALESCE(p.video_url, '') as "video_url!",
            COALESCE(p.metadata->>'presenter_name', '') as "presenter_name!"
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
        tracing::error!("Database error fetching publications: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    // Split the headline programme count into talks vs posters (computed from the
    // live publications, like the conferences list page does).
    let poster_count = pub_records
        .iter()
        .filter(|r| r.paper_type == "poster")
        .count() as i64;
    let talk_count = pub_records.len() as i64 - poster_count;

    // For each publication, get its authors
    let mut publications = Vec::new();
    for pub_record in pub_records {
        let authors = sqlx::query!(
            r#"
            SELECT
                a.slug as "slug!",
                a.full_name,
                COALESCE(a.id = $2, false) as "is_speaker!"
            FROM authorships au
            JOIN authors a ON au.author_id = a.id
            WHERE au.publication_id = $1
            ORDER BY au.author_position
            "#,
            pub_record.id,
            pub_record.presenter_author_id
        )
        .fetch_all(&pool)
        .await
        .map_err(|e| {
            tracing::error!("Database error fetching authors: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?
        .into_iter()
        .map(|row| AuthorInfo {
            slug: row.slug,
            name: row.full_name,
            is_speaker: row.is_speaker,
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
            video_url: pub_record.video_url,
            presenter_name: pub_record.presenter_name,
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
            a.slug as "author_slug!",
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
        tracing::error!("Database error fetching committees: {}", e);
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
                    committee_label: committee_full_label(&ctype).to_string(),
                    members: current_members.clone(),
                });
                current_members.clear();
            }
            current_type = Some(row.committee_type.clone());
        }

        current_members.push(CommitteeMember {
            author_slug: row.author_slug,
            author_name: row.author_name,
            position: row.position,
            role_title: row.role_title,
            affiliation: row.affiliation,
        });
    }

    // Add the last group
    if let Some(ctype) = current_type {
        committee_by_type.push(CommitteeSection {
            committee_label: committee_full_label(&ctype).to_string(),
            members: current_members,
        });
    }

    // Business-meeting stats (announced figures), if recorded for this conference
    let business_meeting = sqlx::query!(
        r#"
        SELECT
            meeting_date,
            registered_participants,
            onsite_participants,
            countries_represented,
            talk_submissions,
            talks_accepted,
            posters_submitted,
            posters_accepted,
            acceptance_rate::text as acceptance_rate,
            notes,
            slides
        FROM conference_business_meetings
        WHERE conference_id = $1
        "#,
        conference_id
    )
    .fetch_optional(&pool)
    .await
    .map_err(|e| {
        tracing::error!("Database error fetching business meeting: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?
    .map(|bm| {
        let int = |v: Option<i32>| v.map(|n| n.to_string()).unwrap_or_default();
        // Parse the slides JSONB array into validated {label, url} links.
        // Only http(s) URLs are kept (these render as <a href>).
        let slides: Vec<SlideLink> = serde_json::from_value::<Vec<serde_json::Value>>(bm.slides)
            .unwrap_or_default()
            .into_iter()
            .filter_map(|s| {
                let url = s.get("url")?.as_str()?.to_string();
                let lower = url.to_ascii_lowercase();
                if !(lower.starts_with("http://") || lower.starts_with("https://")) {
                    return None;
                }
                let label = s.get("label").and_then(|l| l.as_str()).unwrap_or("slides").to_string();
                Some(SlideLink { label, url })
            })
            .collect();
        BusinessMeetingView {
            meeting_date: bm.meeting_date.map(|d| d.to_string()).unwrap_or_default(),
            registered_participants: int(bm.registered_participants),
            onsite_participants: int(bm.onsite_participants),
            countries_represented: int(bm.countries_represented),
            talk_submissions: int(bm.talk_submissions),
            talks_accepted: int(bm.talks_accepted),
            posters_submitted: int(bm.posters_submitted),
            posters_accepted: int(bm.posters_accepted),
            acceptance_rate: bm.acceptance_rate.map(|r| format!("{}%", r)).unwrap_or_default(),
            notes: bm.notes.unwrap_or_default(),
            slides,
        }
    });

    let template = ConferenceDetailTemplate {
        conference: ConferenceDetail {
            slug: conference.slug.unwrap_or_default(),
            venue: conference.venue,
            year: conference.year,
            location,
            start_date: conference.start_date.map(|d| d.to_string()).unwrap_or_else(|| String::from("-")),
            end_date: conference.end_date.map(|d| d.to_string()).unwrap_or_else(|| String::from("-")),
            website_url: conference.website_url.unwrap_or_default(),
            archive_url: conference.archive_url.unwrap_or_default(),
            proceedings_url: conference.proceedings_url.unwrap_or_default(),
            is_virtual: conference.is_virtual.unwrap_or(false),
            is_hybrid: conference.is_hybrid.unwrap_or(false),
            talk_count,
            poster_count,
            regular_paper_count: conference.regular_paper_count,
            invited_talk_count: conference.invited_talk_count,
            award_count: conference.award_count,
            committee_member_count: conference.committee_member_count,
            unique_author_count: conference.unique_author_count,
            submission_count: conference.submission_count.map(|s| s.to_string()).unwrap_or_else(|| String::from("-")),
            acceptance_count: conference.acceptance_count.map(|a| a.to_string()).unwrap_or_else(|| String::from("-")),
            acceptance_rate: conference.acceptance_rate.map(|r| format!("{}%", r)).unwrap_or_else(|| String::from("-")),
            business_meeting,
        },
        publications,
        committee_by_type,
    };

    match template.render() {
        Ok(html) => Ok(Html(html).into_response()),
        Err(e) => {
            tracing::error!("Template error: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}
