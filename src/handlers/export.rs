//! Bulk, denormalized exports for agents, crawlers and researchers.
//!
//! The rest of the API is normalized (UUID-keyed, paginated). These endpoints
//! return whole conferences — or the whole dataset — in one request, with
//! author names, slugs and ORCIDs inline, plus a license/citation header.

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use axum::{
    body::Bytes,
    extract::{Path, State},
    http::{header, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
};
use chrono::{DateTime, NaiveDate, Utc};
use serde::Serialize;
use sqlx::{Pool, Postgres};
use utoipa::ToSchema;
use uuid::Uuid;

use crate::utils::{
    csv_row, parse_conference_slug, public_base_url, DATA_LICENSE, DATA_LICENSE_URL, HOW_TO_CITE,
    THIRD_PARTY_NOTICE,
};

// ─── Response shapes ────────────────────────────────────────────────────────

/// License, provenance and citation header carried by every export.
#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct DatasetInfo {
    pub name: String,
    pub source: String,
    /// SPDX identifier of the data license (`CC0-1.0`).
    pub license: String,
    pub license_url: String,
    pub rights_notice: String,
    pub how_to_cite: String,
    /// Agent/LLM-oriented guide to the dataset.
    pub documentation: String,
    pub api_spec: String,
    pub generated_at: DateTime<Utc>,
}

impl DatasetInfo {
    pub fn new() -> Self {
        let base = public_base_url();
        DatasetInfo {
            name: "QuantumDB".to_string(),
            source: base.to_string(),
            license: DATA_LICENSE.to_string(),
            license_url: DATA_LICENSE_URL.to_string(),
            rights_notice: THIRD_PARTY_NOTICE.to_string(),
            how_to_cite: HOW_TO_CITE.to_string(),
            documentation: format!("{base}/llms.txt"),
            api_spec: format!("{base}/api/v1/openapi.json"),
            generated_at: Utc::now(),
        }
    }
}

impl Default for DatasetInfo {
    fn default() -> Self {
        Self::new()
    }
}

/// URLs of every export of one conference.
#[derive(Debug, Serialize, ToSchema)]
pub struct ExportLinks {
    pub page: String,
    pub json: String,
    pub talks_csv: String,
    pub posters_csv: String,
    pub committees_csv: String,
}

impl ExportLinks {
    fn for_slug(slug: &str) -> Self {
        let base = public_base_url();
        let api = format!("{base}/api/v1/export/conferences/{slug}");
        ExportLinks {
            page: format!("{base}/conferences/{slug}"),
            json: api.clone(),
            talks_csv: format!("{api}/talks.csv"),
            posters_csv: format!("{api}/posters.csv"),
            committees_csv: format!("{api}/committees.csv"),
        }
    }
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ExportConference {
    pub id: Uuid,
    /// Canonical slug, e.g. `qip-2015`.
    pub slug: String,
    /// `QIP`, `QCRYPT` or `TQC`.
    pub venue: String,
    pub year: i32,
    /// Display name, e.g. `QIP 2015`.
    pub name: String,
    pub start_date: Option<NaiveDate>,
    pub end_date: Option<NaiveDate>,
    pub city: Option<String>,
    pub country: Option<String>,
    pub country_code: Option<String>,
    pub is_virtual: Option<bool>,
    pub is_hybrid: Option<bool>,
    pub timezone: Option<String>,
    pub venue_name: Option<String>,
    pub website_url: Option<String>,
    pub proceedings_url: Option<String>,
    pub proceedings_publisher: Option<String>,
    pub proceedings_volume: Option<String>,
    pub proceedings_doi: Option<String>,
    pub submission_count: Option<i32>,
    pub acceptance_count: Option<i32>,
    pub archive_url: Option<String>,
    pub archive_organizers_url: Option<String>,
    pub archive_pc_url: Option<String>,
    pub archive_steering_url: Option<String>,
    pub archive_program_url: Option<String>,
    pub updated_at: DateTime<Utc>,
    pub links: ExportLinks,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ExportCommitteeMember {
    /// `program`, `steering` or `organizing`.
    pub committee: String,
    /// `chair`, `co_chair`, `area_chair` or `member`.
    pub position: String,
    pub role_title: Option<String>,
    pub name: String,
    pub affiliation: Option<String>,
    pub author_id: Uuid,
    pub author_slug: String,
    pub orcid: Option<String>,
    pub author_url: String,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ExportAuthorRef {
    /// 1-based position in the author list.
    pub position: i32,
    /// Canonical name of the person in QuantumDB.
    pub name: String,
    /// Name as printed in this programme, when it differs.
    pub published_as_name: Option<String>,
    /// Affiliation at the time of this talk.
    pub affiliation: Option<String>,
    pub is_presenter: bool,
    pub author_id: Uuid,
    pub author_slug: String,
    pub orcid: Option<String>,
    pub author_url: String,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ExportPublication {
    pub id: Uuid,
    pub title: String,
    /// `regular`, `poster`, `invited`, `tutorial`, `keynote`, `plenary`,
    /// `plenary_short`, `plenary_long` or `industry`.
    pub paper_type: String,
    /// TQC only: published in the formal (LIPIcs/LNCS) proceedings track.
    pub is_proceedings_track: bool,
    pub authors: Vec<ExportAuthorRef>,
    /// Presenter's name (an author, or a non-author recorded in metadata).
    pub presenter: Option<String>,
    pub arxiv_ids: Vec<String>,
    pub doi: Option<String>,
    pub pages: Option<String>,
    /// Abstract text; copyright remains with the authors.
    #[serde(rename = "abstract")]
    pub abstract_text: Option<String>,
    pub session_name: Option<String>,
    pub award: Option<String>,
    pub talk_date: Option<NaiveDate>,
    /// Start time, `HH:MM` (conference-local).
    pub talk_time: Option<String>,
    pub duration_minutes: Option<i32>,
    pub presentation_url: Option<String>,
    pub video_url: Option<String>,
    pub youtube_id: Option<String>,
    pub notes: Option<String>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ExportBusinessMeeting {
    pub meeting_date: Option<NaiveDate>,
    pub registered_participants: Option<i32>,
    pub onsite_participants: Option<i32>,
    pub countries_represented: Option<i32>,
    pub talk_submissions: Option<i32>,
    pub talks_accepted: Option<i32>,
    pub posters_submitted: Option<i32>,
    pub posters_accepted: Option<i32>,
    /// Percent, as announced.
    pub acceptance_rate: Option<f64>,
    #[schema(value_type = Object)]
    pub track_breakdown: Option<serde_json::Value>,
    pub notes: Option<String>,
    /// Slide decks: `[{label, url}]`.
    #[schema(value_type = Object)]
    pub slides: serde_json::Value,
    /// Per-fact provenance.
    #[schema(value_type = Object)]
    pub sources: Option<serde_json::Value>,
}

/// Everything QuantumDB knows about one conference.
#[derive(Debug, Serialize, ToSchema)]
pub struct ConferenceExport {
    /// License and citation header (omitted inside the full-dataset dump,
    /// which carries it once at the top).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub dataset: Option<DatasetInfo>,
    pub conference: ExportConference,
    pub business_meeting: Option<ExportBusinessMeeting>,
    pub committees: Vec<ExportCommitteeMember>,
    /// Talks and posters, in programme order.
    pub publications: Vec<ExportPublication>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct FullExport {
    pub dataset: DatasetInfo,
    pub conferences: Vec<ConferenceExport>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ConferenceIndexEntry {
    pub slug: String,
    pub venue: String,
    pub year: i32,
    pub name: String,
    pub start_date: Option<NaiveDate>,
    pub end_date: Option<NaiveDate>,
    pub city: Option<String>,
    pub country: Option<String>,
    pub is_virtual: Option<bool>,
    pub is_hybrid: Option<bool>,
    pub website_url: Option<String>,
    pub talk_count: i64,
    pub poster_count: i64,
    pub committee_member_count: i64,
    pub updated_at: DateTime<Utc>,
    pub links: ExportLinks,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct DatasetIndex {
    pub dataset: DatasetInfo,
    /// Full nested dump of every conference in one file.
    pub full_dataset_url: String,
    pub authors_url: String,
    pub conferences: Vec<ConferenceIndexEntry>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ExportAuthor {
    pub id: Uuid,
    pub slug: String,
    pub name: String,
    pub family_name: Option<String>,
    pub given_name: Option<String>,
    pub orcid: Option<String>,
    pub google_scholar_id: Option<String>,
    pub homepage_url: Option<String>,
    /// Affiliation at the author's most recent dated appearance.
    pub recent_affiliation: Option<String>,
    pub publication_count: i64,
    pub committee_role_count: i64,
    pub venues: Vec<String>,
    pub first_year: Option<i32>,
    pub last_year: Option<i32>,
    pub url: String,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct AuthorsExport {
    pub dataset: DatasetInfo,
    pub authors: Vec<ExportAuthor>,
}

// ─── Loader ─────────────────────────────────────────────────────────────────

fn author_url(slug: &str) -> String {
    format!("{}/authors/{slug}", public_base_url())
}

/// Map the DB committee enum to the vocabulary used in `committees.csv`.
fn committee_name(code: &str) -> &'static str {
    match code {
        "PC" => "program",
        "SC" => "steering",
        _ => "organizing", // OC and the deprecated Local
    }
}

fn non_empty(s: Option<String>) -> Option<String> {
    s.filter(|v| !v.trim().is_empty())
}

/// Load conferences with everything attached. `filter = Some((venue, year))`
/// loads one; `None` loads all. Five queries in total either way.
pub async fn load_conference_exports(
    pool: &Pool<Postgres>,
    filter: Option<(&str, i32)>,
) -> Result<Vec<ConferenceExport>, sqlx::Error> {
    let (venue, year) = match filter {
        Some((v, y)) => (Some(v.to_string()), Some(y)),
        None => (None, None),
    };

    let conferences = sqlx::query!(
        r#"
        SELECT
            id, venue, year, start_date, end_date, city, country,
            country_code::text as country_code, is_virtual, is_hybrid,
            timezone, venue_name, website_url, proceedings_url,
            proceedings_publisher, proceedings_volume, proceedings_doi,
            submission_count, acceptance_count,
            archive_url, archive_organizers_url, archive_pc_url,
            archive_steering_url, archive_program_url, updated_at
        FROM conferences
        WHERE ($1::text IS NULL OR venue = $1)
          AND ($2::int IS NULL OR year = $2)
        ORDER BY venue, year
        "#,
        venue,
        year
    )
    .fetch_all(pool)
    .await?;

    if conferences.is_empty() {
        return Ok(Vec::new());
    }
    let ids: Vec<Uuid> = conferences.iter().map(|c| c.id).collect();

    // Authors of every publication in these conferences, in author order.
    let author_rows = sqlx::query!(
        r#"
        SELECT
            au.publication_id,
            au.author_position,
            au.published_as_name,
            au.affiliation,
            a.id as author_id,
            a.slug as "slug!",
            a.full_name,
            a.orcid,
            COALESCE(p.presenter_author_id = a.id, false) as "is_presenter!"
        FROM authorships au
        JOIN publications p ON p.id = au.publication_id
        JOIN authors a ON a.id = au.author_id
        WHERE p.conference_id = ANY($1::uuid[])
        ORDER BY au.publication_id, au.author_position
        "#,
        &ids[..]
    )
    .fetch_all(pool)
    .await?;

    let mut authors_by_pub: HashMap<Uuid, Vec<ExportAuthorRef>> = HashMap::new();
    for r in author_rows {
        let published_as = non_empty(Some(r.published_as_name)).filter(|n| *n != r.full_name);
        authors_by_pub
            .entry(r.publication_id)
            .or_default()
            .push(ExportAuthorRef {
                position: r.author_position,
                author_url: author_url(&r.slug),
                name: r.full_name,
                published_as_name: published_as,
                affiliation: non_empty(r.affiliation),
                is_presenter: r.is_presenter,
                author_id: r.author_id,
                author_slug: r.slug,
                orcid: non_empty(r.orcid),
            });
    }

    let pub_rows = sqlx::query!(
        r#"
        SELECT
            id, conference_id, title,
            paper_type::text as "paper_type!",
            COALESCE(is_proceedings_track, false) as "is_proceedings_track!",
            COALESCE(arxiv_ids, ARRAY[]::text[]) as "arxiv_ids!",
            doi, pages, abstract, session_name, award,
            talk_date, talk_time, duration_minutes,
            presentation_url, video_url, youtube_id,
            NULLIF(metadata->>'notes', 'Imported from CSV') as notes,
            metadata->>'presenter_name' as presenter_name
        FROM publications
        WHERE conference_id = ANY($1::uuid[])
        ORDER BY
            conference_id,
            COALESCE(talk_date, '9999-12-31'::date),
            COALESCE(talk_time, '23:59:59'::time),
            paper_type,
            title
        "#,
        &ids[..]
    )
    .fetch_all(pool)
    .await?;

    let mut pubs_by_conf: HashMap<Uuid, Vec<ExportPublication>> = HashMap::new();
    for r in pub_rows {
        let authors = authors_by_pub.remove(&r.id).unwrap_or_default();
        let presenter = authors
            .iter()
            .find(|a| a.is_presenter)
            .map(|a| a.published_as_name.clone().unwrap_or_else(|| a.name.clone()))
            .or_else(|| non_empty(r.presenter_name));
        pubs_by_conf
            .entry(r.conference_id)
            .or_default()
            .push(ExportPublication {
                id: r.id,
                title: r.title,
                paper_type: r.paper_type,
                is_proceedings_track: r.is_proceedings_track,
                authors,
                presenter,
                arxiv_ids: r.arxiv_ids,
                doi: non_empty(r.doi),
                pages: non_empty(r.pages),
                abstract_text: non_empty(r.r#abstract),
                session_name: non_empty(r.session_name),
                award: non_empty(r.award),
                talk_date: r.talk_date,
                talk_time: r.talk_time.map(|t| t.format("%H:%M").to_string()),
                duration_minutes: r.duration_minutes,
                presentation_url: non_empty(r.presentation_url),
                video_url: non_empty(r.video_url),
                youtube_id: non_empty(r.youtube_id),
                notes: non_empty(r.notes),
            });
    }

    let committee_rows = sqlx::query!(
        r#"
        SELECT
            cr.conference_id,
            cr.committee::text as "committee!",
            cr.position::text as "position!",
            cr.role_title,
            cr.affiliation,
            a.id as author_id,
            a.slug as "slug!",
            a.full_name,
            a.orcid
        FROM committee_roles cr
        JOIN authors a ON a.id = cr.author_id
        WHERE cr.conference_id = ANY($1::uuid[])
        ORDER BY cr.conference_id, cr.committee, cr.position, a.full_name
        "#,
        &ids[..]
    )
    .fetch_all(pool)
    .await?;

    let mut committees_by_conf: HashMap<Uuid, Vec<ExportCommitteeMember>> = HashMap::new();
    for r in committee_rows {
        committees_by_conf
            .entry(r.conference_id)
            .or_default()
            .push(ExportCommitteeMember {
                committee: committee_name(&r.committee).to_string(),
                position: r.position,
                role_title: non_empty(r.role_title),
                author_url: author_url(&r.slug),
                name: r.full_name,
                affiliation: non_empty(r.affiliation),
                author_id: r.author_id,
                author_slug: r.slug,
                orcid: non_empty(r.orcid),
            });
    }

    let bm_rows = sqlx::query!(
        r#"
        SELECT
            conference_id, meeting_date,
            registered_participants, onsite_participants, countries_represented,
            talk_submissions, talks_accepted, posters_submitted, posters_accepted,
            acceptance_rate::float8 as acceptance_rate,
            track_breakdown, notes, slides,
            metadata->'sources' as sources
        FROM conference_business_meetings
        WHERE conference_id = ANY($1::uuid[])
        "#,
        &ids[..]
    )
    .fetch_all(pool)
    .await?;

    let mut bm_by_conf: HashMap<Uuid, ExportBusinessMeeting> = bm_rows
        .into_iter()
        .map(|r| {
            (
                r.conference_id,
                ExportBusinessMeeting {
                    meeting_date: r.meeting_date,
                    registered_participants: r.registered_participants,
                    onsite_participants: r.onsite_participants,
                    countries_represented: r.countries_represented,
                    talk_submissions: r.talk_submissions,
                    talks_accepted: r.talks_accepted,
                    posters_submitted: r.posters_submitted,
                    posters_accepted: r.posters_accepted,
                    acceptance_rate: r.acceptance_rate,
                    track_breakdown: r.track_breakdown,
                    notes: non_empty(r.notes),
                    slides: r.slides,
                    sources: r.sources,
                },
            )
        })
        .collect();

    Ok(conferences
        .into_iter()
        .map(|c| {
            let slug = format!("{}-{}", c.venue.to_lowercase(), c.year);
            ConferenceExport {
                dataset: None,
                business_meeting: bm_by_conf.remove(&c.id),
                committees: committees_by_conf.remove(&c.id).unwrap_or_default(),
                publications: pubs_by_conf.remove(&c.id).unwrap_or_default(),
                conference: ExportConference {
                    id: c.id,
                    links: ExportLinks::for_slug(&slug),
                    name: format!("{} {}", display_venue(&c.venue), c.year),
                    slug,
                    venue: c.venue,
                    year: c.year,
                    start_date: c.start_date,
                    end_date: c.end_date,
                    city: c.city,
                    country: c.country,
                    country_code: c.country_code,
                    is_virtual: c.is_virtual,
                    is_hybrid: c.is_hybrid,
                    timezone: c.timezone,
                    venue_name: c.venue_name,
                    website_url: c.website_url,
                    proceedings_url: c.proceedings_url,
                    proceedings_publisher: c.proceedings_publisher,
                    proceedings_volume: c.proceedings_volume,
                    proceedings_doi: c.proceedings_doi,
                    submission_count: c.submission_count,
                    acceptance_count: c.acceptance_count,
                    archive_url: c.archive_url,
                    archive_organizers_url: c.archive_organizers_url,
                    archive_pc_url: c.archive_pc_url,
                    archive_steering_url: c.archive_steering_url,
                    archive_program_url: c.archive_program_url,
                    updated_at: c.updated_at,
                },
            }
        })
        .collect())
}

/// `QCRYPT` → `QCrypt`; others unchanged.
pub fn display_venue(venue: &str) -> &str {
    match venue {
        "QCRYPT" => "QCrypt",
        v => v,
    }
}

// ─── Response helpers ───────────────────────────────────────────────────────

const CACHE_CONTROL: &str = "public, max-age=3600";
const DESCRIBED_BY: &str = "</llms.txt>; rel=\"describedby\"";

fn json_response(body: Bytes) -> Response {
    (
        [
            (header::CONTENT_TYPE, HeaderValue::from_static("application/json")),
            (header::CACHE_CONTROL, HeaderValue::from_static(CACHE_CONTROL)),
            (header::LINK, HeaderValue::from_static(DESCRIBED_BY)),
        ],
        body,
    )
        .into_response()
}

fn to_json<T: Serialize>(value: &T) -> Result<Bytes, StatusCode> {
    serde_json::to_vec(value).map(Bytes::from).map_err(|e| {
        tracing::error!("Failed to serialize export: {e}");
        StatusCode::INTERNAL_SERVER_ERROR
    })
}

fn csv_response(body: String, filename: &str) -> Response {
    let disposition = HeaderValue::from_str(&format!("inline; filename=\"{filename}\""))
        .unwrap_or_else(|_| HeaderValue::from_static("inline"));
    (
        [
            (header::CONTENT_TYPE, HeaderValue::from_static("text/csv; charset=utf-8")),
            (header::CONTENT_DISPOSITION, disposition),
            (header::CACHE_CONTROL, HeaderValue::from_static(CACHE_CONTROL)),
            (header::LINK, HeaderValue::from_static(DESCRIBED_BY)),
        ],
        body,
    )
        .into_response()
}

fn db_err(e: sqlx::Error) -> StatusCode {
    tracing::error!("Export query failed: {e:?}");
    StatusCode::INTERNAL_SERVER_ERROR
}

/// Resolve `qip-2015`, `QIP2015` or `qip-2015.json` to one loaded conference.
async fn load_one(pool: &Pool<Postgres>, slug: &str) -> Result<ConferenceExport, StatusCode> {
    let slug = slug.strip_suffix(".json").unwrap_or(slug);
    let (venue, year) = parse_conference_slug(slug).ok_or(StatusCode::NOT_FOUND)?;
    load_conference_exports(pool, Some((&venue, year)))
        .await
        .map_err(db_err)?
        .into_iter()
        .next()
        .ok_or(StatusCode::NOT_FOUND)
}

// ─── CSV encoders ───────────────────────────────────────────────────────────

/// Canonical `talks.csv` header from `data/README.md`, plus two extra columns
/// (`is_proceedings_track`, `author_slugs`) appended at the end.
pub const TALKS_CSV_HEADER: [&str; 20] = [
    "venue", "year", "paper_type", "title", "speakers", "authors", "affiliations", "abstract",
    "arxiv_ids", "presentation_url", "video_url", "youtube_id", "session_name", "award", "notes",
    "scheduled_date", "scheduled_time", "duration_minutes", "is_proceedings_track", "author_slugs",
];

/// Canonical `committees.csv` header, plus `author_slug`.
pub const COMMITTEES_CSV_HEADER: [&str; 8] = [
    "venue", "year", "committee_type", "position", "full_name", "affiliation", "role_title",
    "author_slug",
];

fn publications_csv(export: &ConferenceExport, posters: bool) -> String {
    let c = &export.conference;
    let year = c.year.to_string();
    let mut out = csv_row(&TALKS_CSV_HEADER);
    for p in export
        .publications
        .iter()
        .filter(|p| (p.paper_type == "poster") == posters)
    {
        let printed = |a: &ExportAuthorRef| a.published_as_name.clone().unwrap_or_else(|| a.name.clone());
        let authors: Vec<String> = p.authors.iter().map(printed).collect();
        let affiliations: Vec<&str> = p
            .authors
            .iter()
            .map(|a| a.affiliation.as_deref().unwrap_or(""))
            .collect();
        let affiliations = if affiliations.iter().all(|a| a.is_empty()) {
            String::new()
        } else {
            affiliations.join(";")
        };
        let slugs: Vec<&str> = p.authors.iter().map(|a| a.author_slug.as_str()).collect();
        let opt = |s: &Option<String>| s.clone().unwrap_or_default();
        out.push_str(&csv_row(&[
            c.venue.clone(),
            year.clone(),
            p.paper_type.clone(),
            p.title.clone(),
            opt(&p.presenter),
            authors.join(";"),
            affiliations,
            opt(&p.abstract_text),
            p.arxiv_ids.join(";"),
            opt(&p.presentation_url),
            opt(&p.video_url),
            opt(&p.youtube_id),
            opt(&p.session_name),
            opt(&p.award),
            opt(&p.notes),
            p.talk_date.map(|d| d.to_string()).unwrap_or_default(),
            opt(&p.talk_time),
            p.duration_minutes.map(|d| d.to_string()).unwrap_or_default(),
            if p.is_proceedings_track { "TRUE" } else { "FALSE" }.to_string(),
            slugs.join(";"),
        ]));
    }
    out
}

fn committees_csv(export: &ConferenceExport) -> String {
    let c = &export.conference;
    let year = c.year.to_string();
    let mut out = csv_row(&COMMITTEES_CSV_HEADER);
    for m in &export.committees {
        out.push_str(&csv_row(&[
            c.venue.as_str(),
            year.as_str(),
            m.committee.as_str(),
            m.position.as_str(),
            m.name.as_str(),
            m.affiliation.as_deref().unwrap_or(""),
            m.role_title.as_deref().unwrap_or(""),
            m.author_slug.as_str(),
        ]));
    }
    out
}

// ─── Handlers ───────────────────────────────────────────────────────────────

#[utoipa::path(
    get,
    path = "/export/conferences/{slug}",
    tag = "export",
    params(("slug" = String, Path, description = "Conference slug: `qip-2015` (canonical), `QIP2015`, or `qip-2015.json`")),
    responses(
        (status = 200, description = "The whole conference — committees, talks and posters with authors inline, business-meeting figures — plus a license/citation header", body = ConferenceExport),
        (status = 404, description = "Unknown conference"),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn export_conference(
    State(pool): State<Pool<Postgres>>,
    Path(slug): Path<String>,
) -> Result<Response, StatusCode> {
    let mut export = load_one(&pool, &slug).await?;
    export.dataset = Some(DatasetInfo::new());
    Ok(json_response(to_json(&export)?))
}

#[utoipa::path(
    get,
    path = "/export/conferences/{slug}/talks.csv",
    tag = "export",
    params(("slug" = String, Path, description = "Conference slug, e.g. `qip-2015`")),
    responses(
        (status = 200, description = "All non-poster programme items, in the `data/conferences/*/talks.csv` format (plus `is_proceedings_track` and `author_slugs`)", content_type = "text/csv", body = String),
        (status = 404, description = "Unknown conference")
    )
)]
pub async fn export_conference_talks_csv(
    State(pool): State<Pool<Postgres>>,
    Path(slug): Path<String>,
) -> Result<Response, StatusCode> {
    let export = load_one(&pool, &slug).await?;
    let filename = format!("{}_talks.csv", export.conference.slug);
    Ok(csv_response(publications_csv(&export, false), &filename))
}

#[utoipa::path(
    get,
    path = "/export/conferences/{slug}/posters.csv",
    tag = "export",
    params(("slug" = String, Path, description = "Conference slug, e.g. `qip-2015`")),
    responses(
        (status = 200, description = "Accepted posters, same columns as talks.csv", content_type = "text/csv", body = String),
        (status = 404, description = "Unknown conference")
    )
)]
pub async fn export_conference_posters_csv(
    State(pool): State<Pool<Postgres>>,
    Path(slug): Path<String>,
) -> Result<Response, StatusCode> {
    let export = load_one(&pool, &slug).await?;
    let filename = format!("{}_posters.csv", export.conference.slug);
    Ok(csv_response(publications_csv(&export, true), &filename))
}

#[utoipa::path(
    get,
    path = "/export/conferences/{slug}/committees.csv",
    tag = "export",
    params(("slug" = String, Path, description = "Conference slug, e.g. `qip-2015`")),
    responses(
        (status = 200, description = "Committee members in the `data/conferences/*/committees.csv` format (plus `author_slug`)", content_type = "text/csv", body = String),
        (status = 404, description = "Unknown conference")
    )
)]
pub async fn export_conference_committees_csv(
    State(pool): State<Pool<Postgres>>,
    Path(slug): Path<String>,
) -> Result<Response, StatusCode> {
    let export = load_one(&pool, &slug).await?;
    let filename = format!("{}_committees.csv", export.conference.slug);
    Ok(csv_response(committees_csv(&export), &filename))
}

#[utoipa::path(
    get,
    path = "/export/all.json",
    tag = "export",
    responses(
        (status = 200, description = "Index of every conference with counts and the URLs of its exports", body = DatasetIndex),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn export_index(State(pool): State<Pool<Postgres>>) -> Result<Response, StatusCode> {
    let rows = sqlx::query!(
        r#"
        SELECT
            c.venue, c.year, c.start_date, c.end_date, c.city, c.country,
            c.is_virtual, c.is_hybrid, c.website_url, c.updated_at,
            (SELECT COUNT(*) FROM publications p
               WHERE p.conference_id = c.id AND p.paper_type <> 'poster') as "talk_count!",
            (SELECT COUNT(*) FROM publications p
               WHERE p.conference_id = c.id AND p.paper_type = 'poster') as "poster_count!",
            (SELECT COUNT(*) FROM committee_roles cr
               WHERE cr.conference_id = c.id) as "committee_member_count!"
        FROM conferences c
        ORDER BY c.venue, c.year
        "#
    )
    .fetch_all(&pool)
    .await
    .map_err(db_err)?;

    let base = public_base_url();
    let index = DatasetIndex {
        dataset: DatasetInfo::new(),
        full_dataset_url: format!("{base}/api/v1/export/all-full.json"),
        authors_url: format!("{base}/api/v1/export/authors.json"),
        conferences: rows
            .into_iter()
            .map(|r| {
                let slug = format!("{}-{}", r.venue.to_lowercase(), r.year);
                ConferenceIndexEntry {
                    links: ExportLinks::for_slug(&slug),
                    name: format!("{} {}", display_venue(&r.venue), r.year),
                    slug,
                    venue: r.venue,
                    year: r.year,
                    start_date: r.start_date,
                    end_date: r.end_date,
                    city: r.city,
                    country: r.country,
                    is_virtual: r.is_virtual,
                    is_hybrid: r.is_hybrid,
                    website_url: r.website_url,
                    talk_count: r.talk_count,
                    poster_count: r.poster_count,
                    committee_member_count: r.committee_member_count,
                    updated_at: r.updated_at,
                }
            })
            .collect(),
    };
    Ok(json_response(to_json(&index)?))
}

/// The full dump is ~19 MB; build it at most once per TTL.
const FULL_EXPORT_TTL: Duration = Duration::from_secs(600);

fn full_export_cache() -> &'static Mutex<Option<(Instant, Bytes)>> {
    static CACHE: OnceLock<Mutex<Option<(Instant, Bytes)>>> = OnceLock::new();
    CACHE.get_or_init(|| Mutex::new(None))
}

#[utoipa::path(
    get,
    path = "/export/all-full.json",
    tag = "export",
    responses(
        (status = 200, description = "Every conference with committees, talks/posters and authors inline, in one file (regenerated at most every 10 minutes)", body = FullExport),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn export_all_full(State(pool): State<Pool<Postgres>>) -> Result<Response, StatusCode> {
    if let Ok(guard) = full_export_cache().lock() {
        if let Some((built, body)) = guard.as_ref() {
            if built.elapsed() < FULL_EXPORT_TTL {
                return Ok(json_response(body.clone()));
            }
        }
    }

    let conferences = load_conference_exports(&pool, None).await.map_err(db_err)?;
    let body = to_json(&FullExport {
        dataset: DatasetInfo::new(),
        conferences,
    })?;
    if let Ok(mut guard) = full_export_cache().lock() {
        *guard = Some((Instant::now(), body.clone()));
    }
    Ok(json_response(body))
}

#[utoipa::path(
    get,
    path = "/export/authors.json",
    tag = "export",
    responses(
        (status = 200, description = "Every author with permanent slug, ORCID / Google Scholar ids and activity summary", body = AuthorsExport),
        (status = 500, description = "Internal server error")
    )
)]
pub async fn export_authors(State(pool): State<Pool<Postgres>>) -> Result<Response, StatusCode> {
    let rows = sqlx::query!(
        r#"
        SELECT
            a.id, a.slug as "slug!", a.full_name, a.family_name, a.given_name,
            a.orcid, a.google_scholar_id, a.homepage_url,
            s.recent_affiliation,
            COALESCE(s.publication_count, 0) as "publication_count!",
            COALESCE(s.committee_role_count, 0) as "committee_role_count!",
            COALESCE(s.venues, ARRAY[]::text[]) as "venues!",
            s.first_year, s.last_year
        FROM authors a
        LEFT JOIN author_stats s ON s.id = a.id
        ORDER BY a.slug
        "#
    )
    .fetch_all(&pool)
    .await
    .map_err(db_err)?;

    let export = AuthorsExport {
        dataset: DatasetInfo::new(),
        authors: rows
            .into_iter()
            .map(|r| ExportAuthor {
                id: r.id,
                url: author_url(&r.slug),
                slug: r.slug,
                name: r.full_name,
                family_name: non_empty(r.family_name),
                given_name: non_empty(r.given_name),
                orcid: non_empty(r.orcid),
                google_scholar_id: non_empty(r.google_scholar_id),
                homepage_url: non_empty(r.homepage_url),
                recent_affiliation: non_empty(r.recent_affiliation),
                publication_count: r.publication_count,
                committee_role_count: r.committee_role_count,
                venues: r.venues,
                first_year: r.first_year,
                last_year: r.last_year,
            })
            .collect(),
    };
    Ok(json_response(to_json(&export)?))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn maps_committee_codes_to_csv_vocabulary() {
        assert_eq!(committee_name("PC"), "program");
        assert_eq!(committee_name("SC"), "steering");
        assert_eq!(committee_name("OC"), "organizing");
        assert_eq!(committee_name("Local"), "organizing");
    }

    #[test]
    fn talks_header_starts_with_canonical_columns() {
        assert_eq!(&TALKS_CSV_HEADER[..4], &["venue", "year", "paper_type", "title"]);
        assert_eq!(TALKS_CSV_HEADER[17], "duration_minutes");
    }
}
