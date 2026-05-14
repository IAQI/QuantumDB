use askama::Template;
use axum::extract::{Path, Query, State};
use axum::http::{StatusCode, HeaderMap};
use axum::response::{Html, IntoResponse, Response};
use serde::Deserialize;
use sqlx::PgPool;

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
    slug: String,
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
    talks: Vec<PublicationItem>,
    posters: Vec<PublicationItem>,
    committee_roles: Vec<CommitteeRoleItem>,
    coauthors: Vec<CoauthorItem>,
    contribution: ContributionGraph,
}

// ─── Contribution-over-time SVG layout ──────────────────────────────────────

const CONTRIB_COL_W: i32 = 36;
const CONTRIB_PAPER_W: i32 = 28;
const CONTRIB_PAPER_H: i32 = 22;
const CONTRIB_PAPER_STEP: i32 = 24;
const CONTRIB_TOP_PAD: i32 = 14;
const CONTRIB_COMMITTEE_BAND_START: i32 = 30;
const CONTRIB_GLYPH_STEP: i32 = 22;

struct ContributionGraph {
    year_count: usize,
    viewbox_w: i32,
    viewbox_h: i32,
    axis_y: i32,
    axis_label_y: i32,
    year_labels: Vec<ContribYearLabel>,
    papers: Vec<ContribPaperCell>,
    committees: Vec<ContribCommitteeCell>,
}

struct ContribYearLabel {
    x: i32,
    year: i32,
}

struct ContribPaperCell {
    x: i32,
    y: i32,
    venue_class: &'static str,
    tooltip: String,
    target_id: String, // anchor of the matching row in the Talks table
    is_speaker: bool,  // page author was the presenter of this talk
}

struct ContribCommitteeCell {
    cx: i32,
    cy: i32,
    shape: &'static str, // "circle" or "polygon"
    points: String,
    class_name: &'static str,
    tooltip: String,
    target_id: String, // anchor of the matching row in the Committee table
}

fn paper_fill_class(venue: &str) -> &'static str {
    match venue.to_ascii_uppercase().as_str() {
        "QIP" => "fill-qip",
        "QCRYPT" => "fill-qcrypt",
        "TQC" => "fill-tqc",
        _ => "fill-ink",
    }
}

fn committee_class(venue: &str, filled: bool) -> &'static str {
    match (venue.to_ascii_uppercase().as_str(), filled) {
        ("QIP", true) => "fill-qip",
        ("QIP", false) => "stroke-qip",
        ("QCRYPT", true) => "fill-qcrypt",
        ("QCRYPT", false) => "stroke-qcrypt",
        ("TQC", true) => "fill-tqc",
        ("TQC", false) => "stroke-tqc",
        _ => "fill-ink",
    }
}

fn venue_order(venue: &str) -> u8 {
    match venue.to_ascii_uppercase().as_str() {
        "QIP" => 0,
        "QCRYPT" => 1,
        "TQC" => 2,
        _ => 3,
    }
}

fn committee_order(c: &str) -> u8 {
    match c {
        "PC" => 0,
        "SC" => 1,
        "OC" => 2,
        "Local" => 3,
        _ => 4,
    }
}

fn is_leadership(pos: &str) -> bool {
    matches!(pos, "chair" | "co_chair" | "area_chair")
}

fn humanize_position(pos: &str) -> &str {
    match pos {
        "co_chair" => "co-chair",
        "area_chair" => "area chair",
        x => x,
    }
}

fn committee_full_name(c: &str) -> &str {
    match c {
        "PC" => "program",
        "SC" => "steering",
        "OC" => "organising",
        "Local" => "local organising",
        x => x,
    }
}

fn truncate_chars(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        let mut out: String = s.chars().take(max).collect();
        out.push('…');
        out
    }
}

fn glyph_points(committee_type: &str, cx: i32, cy: i32) -> (&'static str, String) {
    match committee_type {
        // Triangle (PC)
        "PC" => (
            "polygon",
            format!("{},{} {},{} {},{}", cx, cy - 9, cx - 8, cy + 7, cx + 8, cy + 7),
        ),
        // Diamond (SC)
        "SC" => (
            "polygon",
            format!(
                "{},{} {},{} {},{} {},{}",
                cx, cy - 10, cx + 9, cy, cx, cy + 10, cx - 9, cy
            ),
        ),
        // Circle (OC) — points unused; template emits <circle>
        "OC" => ("circle", String::new()),
        // Square (Local) — polygon with 4 corners
        _ => (
            "polygon",
            format!(
                "{},{} {},{} {},{} {},{}",
                cx - 8,
                cy - 8,
                cx + 8,
                cy - 8,
                cx + 8,
                cy + 8,
                cx - 8,
                cy + 8
            ),
        ),
    }
}

fn build_contribution_graph(
    pubs: &[PublicationItem],
    roles: &[CommitteeRoleItem],
) -> ContributionGraph {
    use std::collections::BTreeMap;

    let mut years: std::collections::BTreeSet<i32> = std::collections::BTreeSet::new();
    for p in pubs {
        years.insert(p.conference_year);
    }
    for r in roles {
        years.insert(r.conference_year);
    }

    if years.is_empty() {
        return ContributionGraph {
            year_count: 0,
            viewbox_w: 0,
            viewbox_h: 0,
            axis_y: 0,
            axis_label_y: 0,
            year_labels: Vec::new(),
            papers: Vec::new(),
            committees: Vec::new(),
        };
    }

    let first = *years.iter().next().unwrap();
    let last = *years.iter().next_back().unwrap();
    let year_count = (last - first + 1) as usize;

    // Keep each item's original index so chart cells can anchor to the
    // matching table row (talk-<i> / committee-<i>).
    let mut by_year_pub: BTreeMap<i32, Vec<(usize, &PublicationItem)>> = BTreeMap::new();
    for (idx, p) in pubs.iter().enumerate() {
        by_year_pub
            .entry(p.conference_year)
            .or_default()
            .push((idx, p));
    }
    for v in by_year_pub.values_mut() {
        v.sort_by_key(|(_, p)| venue_order(&p.conference_venue));
    }

    let mut by_year_role: BTreeMap<i32, Vec<(usize, &CommitteeRoleItem)>> = BTreeMap::new();
    for (idx, r) in roles.iter().enumerate() {
        by_year_role
            .entry(r.conference_year)
            .or_default()
            .push((idx, r));
    }
    for v in by_year_role.values_mut() {
        v.sort_by_key(|(_, r)| {
            (
                committee_order(&r.committee_type),
                if is_leadership(&r.position) { 0u8 } else { 1u8 },
            )
        });
    }

    let max_paper_stack: usize = by_year_pub.values().map(|v| v.len()).max().unwrap_or(0);
    let max_committee_stack: usize = by_year_role.values().map(|v| v.len()).max().unwrap_or(0);

    let axis_y = CONTRIB_TOP_PAD + (max_paper_stack as i32) * CONTRIB_PAPER_STEP;
    let committee_band_h =
        (max_committee_stack as i32) * CONTRIB_GLYPH_STEP + CONTRIB_COMMITTEE_BAND_START + 6;
    let viewbox_h = axis_y + committee_band_h;
    let viewbox_w = (year_count as i32) * CONTRIB_COL_W + 4;

    let col_center =
        |year_idx: usize| -> i32 { (year_idx as i32) * CONTRIB_COL_W + CONTRIB_COL_W / 2 + 2 };

    let year_labels: Vec<ContribYearLabel> = (0..year_count)
        .map(|i| ContribYearLabel {
            x: col_center(i),
            year: first + (i as i32),
        })
        .collect();

    let mut papers = Vec::new();
    for (year, ps) in &by_year_pub {
        let year_idx = (*year - first) as usize;
        let cx = col_center(year_idx);
        for (stack_idx, (orig_idx, p)) in ps.iter().enumerate() {
            let title = truncate_chars(&p.title, 80);
            let mut tooltip = format!(
                "{} {} — {}: {}",
                p.conference_venue, p.conference_year, p.paper_type, title
            );
            if p.presenter_is_self {
                tooltip.push_str("  ▸ presenter");
            }
            papers.push(ContribPaperCell {
                x: cx - CONTRIB_PAPER_W / 2,
                y: axis_y - CONTRIB_PAPER_H - (stack_idx as i32) * CONTRIB_PAPER_STEP,
                venue_class: paper_fill_class(&p.conference_venue),
                tooltip,
                target_id: format!("talk-{}", orig_idx),
                is_speaker: p.presenter_is_self,
            });
        }
    }

    let mut committees = Vec::new();
    for (year, rs) in &by_year_role {
        let year_idx = (*year - first) as usize;
        let cx = col_center(year_idx);
        for (stack_idx, (orig_idx, r)) in rs.iter().enumerate() {
            let cy = axis_y
                + CONTRIB_COMMITTEE_BAND_START
                + (stack_idx as i32) * CONTRIB_GLYPH_STEP;
            let leadership = is_leadership(&r.position);
            let class_name = committee_class(&r.conference_venue, leadership);
            let position_label = humanize_position(&r.position);
            let role_extra = if !r.role_title.is_empty() {
                format!(" ({})", r.role_title)
            } else {
                String::new()
            };
            let tooltip = format!(
                "{} {} — {} · {}{}",
                r.conference_venue,
                r.conference_year,
                committee_full_name(&r.committee_type),
                position_label,
                role_extra
            );
            let (shape, points) = glyph_points(&r.committee_type, cx, cy);
            committees.push(ContribCommitteeCell {
                cx,
                cy,
                shape,
                points,
                class_name,
                tooltip,
                target_id: format!("committee-{}", orig_idx),
            });
        }
    }

    ContributionGraph {
        year_count,
        viewbox_w,
        viewbox_h,
        axis_y,
        axis_label_y: axis_y + 14,
        year_labels,
        papers,
        committees,
    }
}

struct AuthorDetail {
    slug: String,
    full_name: String,
    initials: String,
    family_name: String,
    given_name: String,
    affiliation: String,
    orcid: String,
    homepage_url: String,
    google_scholar_id: String,
    publication_count: i64,
    committee_role_count: i64,
    leadership_count: i64,
    venues: String,
    first_year: String,
    last_year: String,
}

fn compute_initials(full_name: &str) -> String {
    let parts: Vec<&str> = full_name.split_whitespace().collect();
    if parts.is_empty() {
        return "?".to_string();
    }
    if parts.len() == 1 {
        return parts[0]
            .chars()
            .take(2)
            .collect::<String>()
            .to_uppercase();
    }
    let first = parts.first().unwrap().chars().next().unwrap_or('?');
    let last = parts.last().unwrap().chars().next().unwrap_or('?');
    let mut s = String::new();
    s.extend(first.to_uppercase());
    s.extend(last.to_uppercase());
    s
}

struct PublicationItem {
    title: String,
    conference_venue: String,
    conference_year: i32,
    conference_slug: String,
    paper_type: String,
    coauthors: Vec<CoauthorRef>,
    arxiv_ids: Vec<String>,
    abstract_text: String,
    video_url: String,
    presenter_is_self: bool,
}

struct CoauthorRef {
    slug: String,
    name: String,
    is_speaker: bool,
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
    coauthor_slug: String,
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
            a.slug as "slug!",
            a.full_name,
            COALESCE(ast.recent_affiliation, a.affiliation, '') as "affiliation!",
            COALESCE(ast.publication_count, 0) as "publication_count!",
            COALESCE(ast.committee_role_count, 0) as "committee_role_count!",
            COALESCE(ast.first_year::text, '') as "first_year!",
            COALESCE(ast.last_year::text, '') as "last_year!"
        FROM authors a
        LEFT JOIN author_stats ast ON a.id = ast.id
        WHERE a.full_name ILIKE $1 OR a.normalized_name ILIKE $1
        ORDER BY a.full_name
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
        slug: row.slug,
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
    Path(slug): Path<String>,
    State(pool): State<PgPool>,
) -> Result<Response, StatusCode> {
    // Get author with stats
    let author = sqlx::query!(
        r#"
        SELECT
            a.id,
            a.slug as "slug!",
            a.full_name,
            COALESCE(a.family_name, '') as "family_name!",
            COALESCE(a.given_name, '') as "given_name!",
            COALESCE(ast.recent_affiliation, a.affiliation, '') as "affiliation!",
            COALESCE(a.orcid, '') as "orcid!",
            COALESCE(a.homepage_url, '') as "homepage_url!",
            COALESCE(a.google_scholar_id, '') as "google_scholar_id!",
            COALESCE(ast.publication_count, 0) as "publication_count!",
            COALESCE(ast.committee_role_count, 0) as "committee_role_count!",
            COALESCE(ast.leadership_count, 0) as "leadership_count!",
            COALESCE(array_to_string(ast.venues, ', '), '') as "venues!",
            COALESCE(ast.first_year::text, '') as "first_year!",
            COALESCE(ast.last_year::text, '') as "last_year!"
        FROM authors a
        LEFT JOIN author_stats ast ON a.id = ast.id
        WHERE a.slug = $1
        "#,
        slug
    )
    .fetch_optional(&pool)
    .await
    .map_err(|e| {
        eprintln!("Database error: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?
    .ok_or(StatusCode::NOT_FOUND)?;

    let author_id = author.id;

    // Get publications
    let publications: Vec<PublicationItem> = sqlx::query!(
        r#"
        SELECT
            p.title,
            c.venue as "conference_venue!",
            c.year as "conference_year!",
            LOWER(c.venue) || '-' || c.year::text as "conference_slug!",
            p.paper_type::text as "paper_type!",
            COALESCE(
                array_agg(a2.slug ORDER BY au2.author_position) FILTER (WHERE a2.id IS NOT NULL),
                ARRAY[]::text[]
            ) as "coauthor_slugs!",
            COALESCE(
                array_agg(a2.full_name ORDER BY au2.author_position) FILTER (WHERE a2.id IS NOT NULL),
                ARRAY[]::text[]
            ) as "coauthor_names!",
            COALESCE(
                array_agg(COALESCE(a2.id = p.presenter_author_id, false) ORDER BY au2.author_position) FILTER (WHERE a2.id IS NOT NULL),
                ARRAY[]::boolean[]
            ) as "coauthor_is_speaker!",
            COALESCE(p.presenter_author_id = $1, false) as "presenter_is_self!",
            COALESCE(p.arxiv_ids, ARRAY[]::text[]) as "arxiv_ids!",
            COALESCE(p.abstract, '') as "abstract_text!",
            COALESCE(p.video_url, '') as "video_url!"
        FROM authorships au
        JOIN publications p ON au.publication_id = p.id
        JOIN conferences c ON p.conference_id = c.id
        LEFT JOIN authorships au2 ON p.id = au2.publication_id AND au2.author_id != $1
        LEFT JOIN authors a2 ON au2.author_id = a2.id
        WHERE au.author_id = $1
        GROUP BY p.id, p.title, c.venue, c.year, p.paper_type, p.arxiv_ids, p.abstract, p.video_url
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
    .map(|row| {
        let coauthors: Vec<CoauthorRef> = row
            .coauthor_slugs
            .into_iter()
            .zip(row.coauthor_names)
            .zip(row.coauthor_is_speaker)
            .map(|((slug, name), is_speaker)| CoauthorRef {
                slug,
                name,
                is_speaker,
            })
            .collect();
        PublicationItem {
            title: row.title,
            conference_venue: row.conference_venue,
            conference_year: row.conference_year,
            conference_slug: row.conference_slug,
            paper_type: row.paper_type,
            coauthors,
            arxiv_ids: row.arxiv_ids,
            abstract_text: row.abstract_text,
            video_url: row.video_url,
            presenter_is_self: row.presenter_is_self,
        }
    })
    .collect();

    // Get committee roles
    let committee_roles: Vec<CommitteeRoleItem> = sqlx::query!(
        r#"
        SELECT
            c.venue as "conference_venue!",
            c.year as "conference_year!",
            LOWER(c.venue) || '-' || c.year::text as "conference_slug!",
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
            a.slug as "coauthor_slug!",
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
        coauthor_slug: row.coauthor_slug,
        coauthor_name: row.coauthor_name,
        collaboration_count: row.collaboration_count.unwrap_or(0),
    })
    .collect();

    let (talks, posters): (Vec<PublicationItem>, Vec<PublicationItem>) = publications
        .into_iter()
        .partition(|p| p.paper_type != "poster");

    let contribution = build_contribution_graph(&talks, &committee_roles);

    let initials = compute_initials(&author.full_name);

    let template = AuthorDetailTemplate {
        author: AuthorDetail {
            slug: author.slug,
            full_name: author.full_name,
            initials,
            family_name: author.family_name,
            given_name: author.given_name,
            affiliation: author.affiliation,
            orcid: author.orcid,
            homepage_url: author.homepage_url,
            google_scholar_id: author.google_scholar_id,
            publication_count: author.publication_count,
            committee_role_count: author.committee_role_count,
            leadership_count: author.leadership_count,
            venues: author.venues,
            first_year: author.first_year,
            last_year: author.last_year,
        },
        talks,
        posters,
        committee_roles,
        coauthors,
        contribution,
    };

    match template.render() {
        Ok(html) => Ok(Html(html).into_response()),
        Err(e) => {
            eprintln!("Template error: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}
