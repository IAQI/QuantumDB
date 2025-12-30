use anyhow::{Context, Result};
use chrono::Utc;
use clap::Parser;
use scraper::{Html, Selector};
use serde_json::json;
use sqlx::{PgPool, Row};
use tracing::{info, warn};
use uuid::Uuid;
use std::path::PathBuf;

use quantumdb::utils::normalize::normalize_name;

#[derive(Parser, Debug)]
#[command(name = "scrape_committees")]
#[command(about = "Scrape committee membership data from archived conference websites")]
struct Args {
    /// Conference venue to scrape (QIP, QCRYPT, TQC, or 'all')
    #[arg(short, long)]
    venue: Option<String>,

    /// Specific conference year
    #[arg(short, long)]
    year: Option<i32>,

    /// Dry run - don't commit to database
    #[arg(long)]
    dry_run: bool,

    /// Force re-scrape even if data exists
    #[arg(long)]
    force: bool,

    /// Use local files from ~/Web/ instead of fetching from archive.org
    #[arg(long)]
    local: bool,

    /// Custom local web directory (default: ~/Web/)
    #[arg(long)]
    local_dir: Option<PathBuf>,
}

#[derive(Debug)]
struct CommitteeMember {
    name: String,
    committee: String,  // OC, PC, SC, Local
    position: String,   // chair, co_chair, area_chair, member
    role_title: Option<String>,
    affiliation: Option<String>,
}

#[derive(Debug)]
struct ConferenceToScrape {
    id: Uuid,
    venue: String,
    year: i32,
    archive_pc_url: Option<String>,
    archive_organizers_url: Option<String>,
    archive_steering_url: Option<String>,
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt::init();

    // Load environment variables
    dotenvy::dotenv().ok();

    let args = Args::parse();

    // Validate local directory if using local files
    if args.local {
        let local_dir = get_local_dir(&args);
        if !local_dir.exists() {
            anyhow::bail!("Local directory does not exist: {}", local_dir.display());
        }
        info!("Using local files from: {}", local_dir.display());
    }

    // Connect to database
    let database_url = std::env::var("DATABASE_URL")
        .context("DATABASE_URL must be set")?;
    
    let pool = PgPool::connect(&database_url)
        .await
        .context("Failed to connect to database")?;

    info!("Connected to database");

    // Get conferences to scrape
    let conferences = get_conferences_to_scrape(&pool, &args).await?;
    
    if conferences.is_empty() {
        info!("No conferences found matching criteria");
        return Ok(());
    }

    info!("Found {} conference(s) to scrape", conferences.len());

    // Process each conference
    for conf in conferences {
        info!("\n=== Processing {} {} ===", conf.venue, conf.year);
        
        // Check if we should skip this conference
        if !args.force {
            let exists = check_committee_exists(&pool, conf.id).await?;
            if exists {
                info!("Committee data already exists for {} {}. Use --force to re-scrape.", 
                      conf.venue, conf.year);
                continue;
            }
        }

        // Scrape Program Committee
        if let Some(ref url) = conf.archive_pc_url {
            match scrape_committee_page(url, &args, "PC").await {
                Ok(members) => {
                    info!("Found {} PC members", members.len());
                    if args.dry_run {
                        for member in &members {
                            info!("  - {} ({}) [{}]", 
                                  member.name, 
                                  member.affiliation.as_deref().unwrap_or("?"),
                                  member.position);
                        }
                    } else {
                        insert_committee_members(&pool, conf.id, &members).await?;
                    }
                }
                Err(e) => warn!("Failed to scrape PC: {}", e),
            }
        }

        // Scrape Organizing Committee
        if let Some(ref url) = conf.archive_organizers_url {
            match scrape_committee_page(url, &args, "OC").await {
                Ok(members) => {
                    info!("Found {} OC members", members.len());
                    if args.dry_run {
                        for member in &members {
                            info!("  - {} ({}) [{}]", 
                                  member.name, 
                                  member.affiliation.as_deref().unwrap_or("?"),
                                  member.position);
                        }
                    } else {
                        insert_committee_members(&pool, conf.id, &members).await?;
                    }
                }
                Err(e) => warn!("Failed to scrape OC: {}", e),
            }
        }

        // Scrape Steering Committee
        if let Some(ref url) = conf.archive_steering_url {
            match scrape_committee_page(url, &args, "SC").await {
                Ok(members) => {
                    info!("Found {} SC members", members.len());
                    if args.dry_run {
                        for member in &members {
                            info!("  - {} ({}) [{}]", 
                                  member.name, 
                                  member.affiliation.as_deref().unwrap_or("?"),
                                  member.position);
                        }
                    } else {
                        insert_committee_members(&pool, conf.id, &members).await?;
                    }
                }
                Err(e) => warn!("Failed to scrape SC: {}", e),
            }
        }
    }

    info!("\nScraping complete!");
    Ok(())
}

fn get_local_dir(args: &Args) -> PathBuf {
    args.local_dir.clone().unwrap_or_else(|| {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        PathBuf::from(home).join("Web")
    })
}

fn url_to_local_path(args: &Args, url: &str) -> Result<PathBuf> {
    let local_dir = get_local_dir(args);
    
    // Parse the URL to extract domain and path
    let without_protocol = url.trim_start_matches("http://")
                              .trim_start_matches("https://");
    
    let parts: Vec<&str> = without_protocol.splitn(2, '/').collect();
    let domain = parts[0];
    let path = parts.get(1).map(|s| *s).unwrap_or("");
    
    // Check if the local_dir already ends with the domain
    // This prevents doubling up the domain in the path
    let base = if local_dir.ends_with(domain) {
        local_dir.clone()
    } else {
        local_dir.join(domain)
    };
    
    // Construct the full path
    let mut full_path = base.join(path);
    
    // If it's a directory URL (doesn't end with a file extension), add index.html
    if !path.contains('.') || path.ends_with('/') {
        full_path = full_path.join("index.html");
    }
    
    Ok(full_path)
}

async fn get_conferences_to_scrape(pool: &PgPool, args: &Args) -> Result<Vec<ConferenceToScrape>> {
    let mut query = sqlx::QueryBuilder::new(
        "SELECT id, venue, year, archive_pc_url, archive_organizers_url, archive_steering_url
         FROM conferences
         WHERE (archive_pc_url IS NOT NULL 
                OR archive_organizers_url IS NOT NULL 
                OR archive_steering_url IS NOT NULL)"
    );

    if let Some(ref venue) = args.venue {
        if venue.to_lowercase() != "all" {
            query.push(" AND venue = ");
            query.push_bind(venue.to_uppercase());
        }
    }

    if let Some(year) = args.year {
        query.push(" AND year = ");
        query.push_bind(year);
    }

    query.push(" ORDER BY year DESC, venue");

    let rows = query.build()
        .fetch_all(pool)
        .await
        .context("Failed to fetch conferences")?;

    let conferences: Vec<ConferenceToScrape> = rows.into_iter().map(|row| {
        ConferenceToScrape {
            id: row.get("id"),
            venue: row.get("venue"),
            year: row.get("year"),
            archive_pc_url: row.get("archive_pc_url"),
            archive_organizers_url: row.get("archive_organizers_url"),
            archive_steering_url: row.get("archive_steering_url"),
        }
    }).collect();

    Ok(conferences)
}

async fn check_committee_exists(pool: &PgPool, conference_id: Uuid) -> Result<bool> {
    let count: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM committee_roles WHERE conference_id = $1"
    )
    .bind(conference_id)
    .fetch_one(pool)
    .await
    .context("Failed to check committee existence")?;

    Ok(count > 0)
}

async fn scrape_committee_page(url: &str, args: &Args, committee_type: &str) -> Result<Vec<CommitteeMember>> {
    info!("Scraping {} from: {}", committee_type, url);
    
    // Get HTML content (either from local file or remote URL)
    let html_content = if args.local {
        let local_path = url_to_local_path(args, url)?;
        info!("Reading local file: {}", local_path.display());
        
        std::fs::read_to_string(&local_path)
            .context(format!("Failed to read local file: {}", local_path.display()))?
    } else {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .build()?;
        
        let response = client.get(url)
            .send()
            .await
            .context("Failed to fetch URL")?;
        
        response.text()
            .await
            .context("Failed to read response body")?
    };
    
    let document = Html::parse_document(&html_content);
    
    // Parse committee members based on conference-specific patterns
    parse_committee_members(&document, committee_type)
}

fn parse_committee_members(document: &Html, committee_type: &str) -> Result<Vec<CommitteeMember>> {
    let mut members = Vec::new();

    // Define section header patterns for each committee type
    let section_patterns = match committee_type {
        "PC" => vec![
            "program committee",
            "pc members",
            "programme committee",
        ],
        "OC" => vec![
            "organizing committee",
            "organising committee",
            "local organizing committee",
            "local organising committee",
            "organization",
            "organisers",
            "organizers",
        ],
        "SC" => vec![
            "steering committee",
            "sc members",
        ],
        _ => vec![],
    };

    // Try to find the section for this committee type
    info!("Looking for section matching: {:?}", section_patterns);
    
    // Use section-aware parsing
    if let Some(section_members) = parse_section_based(document, &section_patterns, committee_type) {
        if !section_members.is_empty() {
            info!("Found {} members using section-based parsing", section_members.len());
            return Ok(section_members);
        }
    }

    // Fallback: Try more specific selectors first (conference-specific patterns)
    let specific_selectors = [
        ".committee-member",
        ".person",
        ".team-member",
        "div.member",
        "div.speaker",  // Some sites use speaker class for committee
    ];

    // Try specific selectors first
    for selector_str in specific_selectors {
        if let Ok(selector) = Selector::parse(selector_str) {
            let elements: Vec<_> = document.select(&selector).collect();
            if !elements.is_empty() {
                info!("Using specific selector: {} ({} elements)", selector_str, elements.len());
                for element in elements {
                    let text = element.text().collect::<Vec<_>>().join(" ").trim().to_string();
                    
                    if text.len() < 3 || text.len() > 300 {
                        continue;
                    }

                    if let Some(member) = parse_member_entry(&text, committee_type) {
                        members.push(member);
                    }
                }
                
                // If we found members with specific selectors, use those
                if !members.is_empty() {
                    members.sort_by(|a, b| a.name.cmp(&b.name));
                    members.dedup_by(|a, b| normalize_name(&a.name) == normalize_name(&b.name));
                    return Ok(members);
                }
            }
        }
    }

    // Final fallback: Try generic selectors looking for lists
    info!("Trying generic list selectors");
    let generic_selectors = [
        "ul li",
        "div.content p",
        "article p",
    ];

    for selector_str in generic_selectors {
        if let Ok(selector) = Selector::parse(selector_str) {
            for element in document.select(&selector) {
                let text = element.text().collect::<Vec<_>>().join(" ").trim().to_string();
                
                if text.len() < 3 || text.len() > 300 {
                    continue;
                }

                if let Some(member) = parse_member_entry(&text, committee_type) {
                    members.push(member);
                }
            }
        }
    }

    // Remove duplicates
    members.sort_by(|a, b| a.name.cmp(&b.name));
    members.dedup_by(|a, b| normalize_name(&a.name) == normalize_name(&b.name));

    if members.is_empty() {
        warn!("No committee members found");
    }

    Ok(members)
}

fn parse_section_based(document: &Html, section_patterns: &[&str], committee_type: &str) -> Option<Vec<CommitteeMember>> {
    // Try to parse using heading-based sections
    if let Ok(heading_selector) = Selector::parse("h1, h2, h3, h4, h5, h6") {
        let headings: Vec<_> = document.select(&heading_selector).collect();
        
        // Find the heading that matches our section
        for (idx, heading) in headings.iter().enumerate() {
            let heading_text = heading.text().collect::<String>().to_lowercase();
            
            // Check if this heading matches any of our patterns
            if section_patterns.iter().any(|pattern| heading_text.contains(pattern)) {
                info!("Found section header: '{}'", heading.text().collect::<String>().trim());
                
                // Get all content between this heading and the next heading at same or higher level
                let next_heading = headings.iter().skip(idx + 1).find(|h| {
                    // Find next heading at same or higher level (h2 stops at next h2 or h1)
                    let curr_level = get_heading_level(heading.value().name());
                    let next_level = get_heading_level(h.value().name());
                    next_level <= curr_level
                });
                
                let members = extract_members_between_headings(document, heading, next_heading.copied(), committee_type);
                
                if !members.is_empty() {
                    info!("Found {} members using section-based parsing", members.len());
                    return Some(members);
                }
            }
        }
    }
    
    None
}

fn get_heading_level(name: &str) -> u8 {
    match name {
        "h1" => 1,
        "h2" => 2,
        "h3" => 3,
        "h4" => 4,
        "h5" => 5,
        "h6" => 6,
        _ => 99,
    }
}

fn extract_members_between_headings(
    document: &Html,
    start_heading: &scraper::ElementRef,
    end_heading: Option<scraper::ElementRef>,
    committee_type: &str,
) -> Vec<CommitteeMember> {
    let mut members = Vec::new();
    
    // Get the HTML as a string and find positions
    let html = document.html();
    
    // Get the position of the start heading in the HTML
    let start_text = start_heading.html();
    let start_pos = html.find(&start_text);
    
    if start_pos.is_none() {
        return members;
    }
    let start_idx = start_pos.unwrap();
    
    // Get the position of the end heading (if it exists) - must be after start
    let end_idx = if let Some(end) = end_heading {
        let end_text = end.html();
        // Search for end heading only AFTER the start position
        html[start_idx..].find(&end_text).map(|pos| start_idx + pos)
    } else {
        None
    };
    
    // Extract the HTML between start and end
    let section_html = if let Some(end_pos) = end_idx {
        &html[start_idx..end_pos]
    } else {
        &html[start_idx..]
    };
    
    // Parse this section as a sub-document
    let section_doc = Html::parse_fragment(section_html);
    
    // Extract members from list items in this section
    if let Ok(li_selector) = Selector::parse("ul li, ol li") {
        for item in section_doc.select(&li_selector) {
            let text = item.text().collect::<Vec<_>>().join(" ").trim().to_string();
            
            if text.len() < 3 || text.len() > 300 {
                continue;
            }
            
            if let Some(member) = parse_member_entry(&text, committee_type) {
                members.push(member);
            }
        }
    }
    
    // Remove duplicates
    members.sort_by(|a, b| a.name.cmp(&b.name));
    members.dedup_by(|a, b| normalize_name(&a.name) == normalize_name(&b.name));
    
    members
}

fn extract_members_from_element(element: scraper::ElementRef, committee_type: &str) -> Vec<CommitteeMember> {
    let mut members = Vec::new();
    
    // Try to find list items within this element
    if let Ok(li_selector) = Selector::parse("ul li, ol li") {
        for item in element.select(&li_selector) {
            let text = item.text().collect::<Vec<_>>().join(" ").trim().to_string();
            
            if text.len() < 3 || text.len() > 300 {
                continue;
            }
            
            if let Some(member) = parse_member_entry(&text, committee_type) {
                members.push(member);
            }
        }
    }
    
    // Also try paragraphs if no list items found
    if members.is_empty() {
        if let Ok(p_selector) = Selector::parse("p") {
            for para in element.select(&p_selector) {
                let text = para.text().collect::<Vec<_>>().join(" ").trim().to_string();
                
                if text.len() < 3 || text.len() > 300 {
                    continue;
                }
                
                if let Some(member) = parse_member_entry(&text, committee_type) {
                    members.push(member);
                }
            }
        }
    }
    
    // Remove duplicates
    members.sort_by(|a, b| a.name.cmp(&b.name));
    members.dedup_by(|a, b| normalize_name(&a.name) == normalize_name(&b.name));
    
    members
}

fn parse_member_entry(text: &str, committee_type: &str) -> Option<CommitteeMember> {
    let text_lower = text.to_lowercase();
    
    // Expanded blacklist of navigation/menu items and section headers
    let blacklist = [
        "committee", "members:", "chair:", "co-chair:", "organizers:",
        "accepted papers", "call for papers", "code of conduct", "charter",
        "schedule", "speakers", "poster", "pictures", "sponsors", "partners",
        "twitter", "youtube", "linkedin", "facebook", "instagram",
        "& 202", "proceedings", "registration", "venue", "travel",
        "accommodation", "contact", "about", "home", "news", "archive",
        "previous", "next", "program", "tutorials", "workshops",
        "support", "members only", "login", "logout", "search",
        "steering committee", "program committee", "organizing committee",
        "general chairs", "program chairs", "local arrangements",
    ];
    
    for item in blacklist {
        if text_lower.contains(item) && text.len() < 50 {
            return None;
        }
    }
    
    // Skip if it looks like a link/menu item (all caps, or ends with common menu patterns)
    if text.chars().all(|c| c.is_uppercase() || c.is_whitespace() || c.is_numeric()) {
        return None;
    }
    
    // Skip URLs
    if text.contains("http://") || text.contains("https://") || text.contains("www.") {
        return None;
    }
    
    // Must have at least some alphabetic characters and look like a name
    let alpha_count = text.chars().filter(|c| c.is_alphabetic()).count();
    if alpha_count < 3 {
        return None;
    }
    
    // Skip single words (likely not a full name)
    let word_count = text.split_whitespace().count();
    if word_count < 2 && !text.contains('(') {
        return None;
    }

    // Parse the text to extract name, affiliation, and role
    let (name, affiliation, role_info) = extract_name_affiliation_role(text);
    
    // Validate the name looks reasonable
    if name.len() < 3 || name.len() > 100 {
        return None;
    }
    
    // Skip if name is all lowercase or all uppercase (likely not a proper name)
    if name == name.to_lowercase() || name == name.to_uppercase() {
        return None;
    }

    // Detect position from role information
    let (position, role_title) = detect_position(&name, text, &role_info);

    Some(CommitteeMember {
        name: clean_name(&name),
        committee: committee_type.to_string(),
        position,
        role_title,
        affiliation,
    })
}

fn extract_name_affiliation_role(text: &str) -> (String, Option<String>, String) {
    // Handle pattern: "Name University/Company Site role"
    // Example: "Anne Broadbent University of Ottawa Site PC primary chair"
    
    let mut name = String::new();
    let mut affiliation = None;
    let mut role_info = String::new();
    
    // Check for "Site" keyword which often separates affiliation from role
    if text.contains(" Site ") {
        let parts: Vec<&str> = text.splitn(2, " Site ").collect();
        let before_site = parts[0];
        let after_site = parts.get(1).map(|s| *s).unwrap_or("");
        
        // Before "Site" should have name and affiliation
        let words: Vec<&str> = before_site.split_whitespace().collect();
        
        // Assume first 2-3 words are the name (capitalized words)
        let name_word_count = if words.len() > 2 {
            let mut count = 2;
            for i in 2..words.len().min(5) {
                if words[i].chars().next().map_or(false, |c| c.is_uppercase()) {
                    count = i;
                } else {
                    break;
                }
            }
            count + 1
        } else {
            words.len().min(2)
        };
        
        name = words[..name_word_count].join(" ");
        
        if name_word_count < words.len() {
            affiliation = Some(words[name_word_count..].join(" "));
        }
        
        role_info = after_site.to_string();
    }
    // Check for pattern: "Name (Affiliation)"
    else if text.contains('(') && text.contains(')') {
        let parts: Vec<&str> = text.splitn(2, '(').collect();
        name = parts[0].trim().to_string();
        
        if let Some(rest) = parts.get(1) {
            if let Some(end_paren) = rest.find(')') {
                let in_parens = &rest[..end_paren];
                
                // Check if what's in parentheses looks like a role or affiliation
                let in_parens_lower = in_parens.to_lowercase();
                if in_parens_lower.contains("chair") || in_parens_lower.contains("member") {
                    role_info = in_parens.to_string();
                } else {
                    affiliation = Some(in_parens.to_string());
                }
                
                // Check for role info after the parentheses
                let after_parens = &rest[end_paren + 1..].trim();
                if !after_parens.is_empty() {
                    role_info.push_str(" ");
                    role_info.push_str(after_parens);
                }
            }
        }
    }
    // Check for pattern: "Name - Affiliation"
    else if text.contains(" - ") || text.contains(" – ") {
        let separator = if text.contains(" - ") { " - " } else { " – " };
        let parts: Vec<&str> = text.splitn(2, separator).collect();
        name = parts[0].trim().to_string();
        
        if let Some(rest) = parts.get(1) {
            // Check if rest contains role keywords
            let rest_lower = rest.to_lowercase();
            if rest_lower.contains("chair") || rest_lower.contains("member") || rest_lower.contains("organizer") {
                role_info = rest.to_string();
            } else {
                affiliation = Some(rest.to_string());
            }
        }
    }
    // Check for pattern: "Name, Affiliation"
    else if text.contains(',') {
        let parts: Vec<&str> = text.splitn(2, ',').collect();
        name = parts[0].trim().to_string();
        
        if let Some(rest) = parts.get(1) {
            let rest = rest.trim();
            // Check if rest contains role keywords
            let rest_lower = rest.to_lowercase();
            if rest_lower.contains("chair") || rest_lower.contains("member") || rest_lower.contains("organizer") {
                role_info = rest.to_string();
            } else {
                affiliation = Some(rest.to_string());
            }
        }
    }
    // Default: just the name
    else {
        name = text.to_string();
        role_info = text.to_string();
    }
    
    (name, affiliation, role_info)
}

fn detect_position(name: &str, full_text: &str, role_info: &str) -> (String, Option<String>) {
    let combined = format!("{} {}", full_text, role_info).to_lowercase();
    
    // Check for specific chair titles
    if combined.contains("general chair") || combined.contains("conference chair") {
        ("chair".to_string(), Some("General Chair".to_string()))
    } else if combined.contains("program chair") || combined.contains("pc chair") || combined.contains("pc primary chair") {
        ("chair".to_string(), Some("Program Chair".to_string()))
    } else if combined.contains("steering chair") || combined.contains("sc chair") {
        ("chair".to_string(), Some("Steering Chair".to_string()))
    } else if combined.contains("local chair") {
        ("chair".to_string(), Some("Local Chair".to_string()))
    } else if combined.contains("co-chair") || combined.contains("cochair") || combined.contains("pc co-chair") {
        ("co_chair".to_string(), None)
    } else if combined.contains("area chair") || combined.contains("senior pc") {
        ("area_chair".to_string(), None)
    } else if combined.contains("chair") {
        // Generic "chair" mention
        ("chair".to_string(), None)
    } else {
        // Default to member
        ("member".to_string(), None)
    }
}

fn clean_name(name: &str) -> String {
    name.trim()
        .split_whitespace()
        .filter(|word| !word.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}

async fn insert_committee_members(
    pool: &PgPool,
    conference_id: Uuid,
    members: &[CommitteeMember],
) -> Result<()> {
    for member in members {
        // First, get or create the author
        let author_id = get_or_create_author(pool, &member.name, member.affiliation.as_deref()).await?;
        
        // Then insert the committee role
        insert_committee_role(pool, conference_id, author_id, &member.committee, &member.position, member.role_title.as_deref()).await?;
    }
    
    info!("Inserted {} committee members", members.len());
    Ok(())
}

async fn get_or_create_author(pool: &PgPool, name: &str, affiliation: Option<&str>) -> Result<Uuid> {
    let normalized_name = normalize_name(name);
    
    // Try to find existing author
    let existing: Option<Uuid> = sqlx::query_scalar(
        "SELECT id FROM authors WHERE normalized_name = $1"
    )
    .bind(&normalized_name)
    .fetch_optional(pool)
    .await
    .context("Failed to query authors")?;

    if let Some(id) = existing {
        info!("Found existing author: {} ({})", name, id);
        return Ok(id);
    }

    // Create new author
    let id = Uuid::new_v4();
    
    let metadata = if let Some(aff) = affiliation {
        json!({ "affiliation": aff })
    } else {
        json!({})
    };

    sqlx::query(
        "INSERT INTO authors (id, canonical_name, normalized_name, metadata, created_at, updated_at)
         VALUES ($1, $2, $3, $4, $5, $6)"
    )
    .bind(id)
    .bind(name)
    .bind(&normalized_name)
    .bind(&metadata)
    .bind(Utc::now())
    .bind(Utc::now())
    .execute(pool)
    .await
    .context("Failed to insert author")?;

    info!("Created new author: {} ({})", name, id);
    Ok(id)
}

async fn insert_committee_role(
    pool: &PgPool,
    conference_id: Uuid,
    author_id: Uuid,
    committee: &str,
    position: &str,
    role_title: Option<&str>,
) -> Result<()> {
    let id = Uuid::new_v4();
    
    let mut metadata = json!({});
    if let Some(title) = role_title {
        metadata["role_title"] = json!(title);
    }

    sqlx::query(
        "INSERT INTO committee_roles (id, conference_id, author_id, committee, position, metadata, created_at, updated_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
         ON CONFLICT (conference_id, author_id, committee) 
         DO UPDATE SET position = EXCLUDED.position, metadata = EXCLUDED.metadata, updated_at = EXCLUDED.updated_at"
    )
    .bind(id)
    .bind(conference_id)
    .bind(author_id)
    .bind(committee)
    .bind(position)
    .bind(&metadata)
    .bind(Utc::now())
    .bind(Utc::now())
    .execute(pool)
    .await
    .context("Failed to insert committee role")?;

    Ok(())
}
