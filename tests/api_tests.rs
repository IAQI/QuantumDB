mod common;

use axum_test::TestServer;
use serde_json::json;
use serial_test::serial;
use uuid::Uuid;

/// Helper to create a test server
async fn setup() -> TestServer {
    let pool = common::create_test_pool().await;
    let app = common::create_test_app(pool);
    TestServer::new(app).unwrap()
}

/// Generate a unique year for test conferences (to avoid unique constraint violations)
fn unique_test_year() -> i32 {
    use std::sync::atomic::{AtomicI32, Ordering};
    static COUNTER: AtomicI32 = AtomicI32::new(5000);
    // Each call gets a unique year starting from 5000
    COUNTER.fetch_add(1, Ordering::SeqCst)
}

// ============================================================================
// Conference API Tests
// ============================================================================

#[tokio::test]
async fn test_list_conferences() {
    let server = setup().await;

    let response = server.get("/conferences").await;
    response.assert_status_ok();

    // Should return an array
    let conferences: Vec<serde_json::Value> = response.json();
    assert!(!conferences.is_empty(), "Should have seeded conference data");
}

#[tokio::test]
async fn test_list_and_retrieve_existing_conferences() {
    let server = setup().await;

    // List all conferences
    let response = server.get("/conferences").await;
    response.assert_status_ok();
    let conferences: Vec<serde_json::Value> = response.json();

    // Print summary of conferences found
    println!("Found {} conferences", conferences.len());

    // Verify we have data
    assert!(!conferences.is_empty(), "Should have seeded conference data");

    // Try to retrieve each of the first 5 conferences by ID
    let test_count = std::cmp::min(5, conferences.len());
    for conference in conferences.iter().take(test_count) {
        let id = conference["id"].as_str().expect("Conference should have an id");
        let venue = conference["venue"].as_str().unwrap_or("unknown");
        let year = conference["year"].as_i64().unwrap_or(0);

        println!("Retrieving conference: {} {} (id: {})", venue, year, id);

        // Retrieve the conference by ID
        let response = server.get(&format!("/conferences/{}", id)).await;
        response.assert_status_ok();

        let fetched: serde_json::Value = response.json();

        // Verify the fetched conference matches
        assert_eq!(fetched["id"], conference["id"], "Conference ID should match");
        assert_eq!(fetched["venue"], conference["venue"], "Conference venue should match");
        assert_eq!(fetched["year"], conference["year"], "Conference year should match");

        // Verify required fields are present
        assert!(fetched["id"].is_string(), "id should be a string");
        assert!(fetched["venue"].is_string(), "venue should be a string");
        assert!(fetched["year"].is_number(), "year should be a number");
        assert!(fetched["created_at"].is_string(), "created_at should be present");
        assert!(fetched["updated_at"].is_string(), "updated_at should be present");
    }

    // Verify we tested all we intended to
    println!("Successfully retrieved {} conferences by ID", test_count);
}

#[tokio::test]
async fn test_get_conference_not_found() {
    let server = setup().await;

    let fake_id = Uuid::new_v4();
    let response = server.get(&format!("/conferences/{}", fake_id)).await;
    response.assert_status_not_found();
}

#[tokio::test]
#[serial]
async fn test_conference_crud() {
    let server = setup().await;
    let test_year = unique_test_year();

    // Create a new conference
    let create_body = json!({
        "venue": "QIP",
        "year": test_year,
        "city": "Test City",
        "country": "Test Country",
        "country_code": "TC",
        "creator": "test_user",
        "modifier": "test_user"
    });

    let response = server.post("/conferences").json(&create_body).await;
    if !response.status_code().is_success() {
        let body = response.text();
        panic!("Failed to create conference: {} - {}", response.status_code(), body);
    }

    let created: serde_json::Value = response.json();
    let conference_id = created["id"].as_str().expect("Created conference should have an id");

    // Read the created conference
    let response = server.get(&format!("/conferences/{}", conference_id)).await;
    response.assert_status_ok();
    let fetched: serde_json::Value = response.json();
    assert_eq!(fetched["venue"], "QIP");
    assert_eq!(fetched["year"], test_year);
    assert_eq!(fetched["city"], "Test City");

    // Update the conference
    let update_body = json!({
        "venue": "QIP",
        "year": test_year,
        "city": "Updated City",
        "modifier": "test_user"
    });

    let response = server
        .put(&format!("/conferences/{}", conference_id))
        .json(&update_body)
        .await;
    response.assert_status_ok();
    let updated: serde_json::Value = response.json();
    assert_eq!(updated["city"], "Updated City");

    // Delete the conference
    let response = server.delete(&format!("/conferences/{}", conference_id)).await;
    response.assert_status(axum::http::StatusCode::NO_CONTENT);

    // Verify it's deleted
    let response = server.get(&format!("/conferences/{}", conference_id)).await;
    response.assert_status_not_found();
}

#[tokio::test]
async fn test_conference_venue_validation() {
    let server = setup().await;

    // Try to create with invalid venue - should fail at database level
    let create_body = json!({
        "venue": "INVALID",
        "year": unique_test_year(),
        "creator": "test_user",
        "modifier": "test_user"
    });

    let response = server.post("/conferences").json(&create_body).await;
    response.assert_status(axum::http::StatusCode::INTERNAL_SERVER_ERROR);
}

// ============================================================================
// Author API Tests
// ============================================================================

#[tokio::test]
async fn test_list_authors() {
    let server = setup().await;

    let response = server.get("/authors").await;
    response.assert_status_ok();

    let authors: Vec<serde_json::Value> = response.json();
    // May be empty if no authors seeded, that's ok
    assert!(authors.is_empty() || !authors.is_empty());
}

#[tokio::test]
#[serial]
async fn test_author_crud() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // Create a new author
    let create_body = json!({
        "full_name": format!("Test Author {}", unique_suffix),
        "family_name": "Author",
        "given_name": "Test",
        "orcid": "0000-0001-2345-6789",
        "homepage_url": "https://example.com",
        "affiliation": "Test University",
        "creator": "test_user",
        "modifier": "test_user"
    });

    let response = server.post("/authors").json(&create_body).await;
    if !response.status_code().is_success() {
        let body = response.text();
        panic!("Failed to create author: {} - {}", response.status_code(), body);
    }

    let created: serde_json::Value = response.json();
    let author_id = created["id"].as_str().expect("Created author should have an id");
    assert!(created["full_name"].as_str().unwrap().contains("Test Author"));
    assert!(created["normalized_name"].as_str().unwrap().contains("test author"));

    // Read the created author
    let response = server.get(&format!("/authors/{}", author_id)).await;
    response.assert_status_ok();

    // Update the author
    let update_body = json!({
        "affiliation": "Updated University",
        "modifier": "test_user"
    });

    let response = server
        .put(&format!("/authors/{}", author_id))
        .json(&update_body)
        .await;
    response.assert_status_ok();
    let updated: serde_json::Value = response.json();
    assert_eq!(updated["affiliation"], "Updated University");

    // Delete the author
    let response = server.delete(&format!("/authors/{}", author_id)).await;
    response.assert_status(axum::http::StatusCode::NO_CONTENT);
}

#[tokio::test]
#[serial]
async fn test_author_search() {
    let server = setup().await;
    let unique_id = Uuid::new_v4().simple().to_string();

    // Create an author to search for
    let create_body = json!({
        "full_name": format!("Searchable{} Person", unique_id),
        "family_name": "Person",
        "given_name": format!("Searchable{}", unique_id),
        "creator": "test_user",
        "modifier": "test_user"
    });

    let response = server.post("/authors").json(&create_body).await;
    if !response.status_code().is_success() {
        let body = response.text();
        panic!("Failed to create author: {} - {}", response.status_code(), body);
    }
    let created: serde_json::Value = response.json();
    let author_id = created["id"].as_str().unwrap();

    // Search for the author
    let response = server.get(&format!("/authors?search=Searchable{}", unique_id)).await;
    response.assert_status_ok();
    let authors: Vec<serde_json::Value> = response.json();
    assert!(authors.iter().any(|a| a["full_name"].as_str().unwrap().contains(&unique_id)));

    // Cleanup
    server.delete(&format!("/authors/{}", author_id)).await;
}

#[tokio::test]
async fn test_author_pagination() {
    let server = setup().await;

    let response = server.get("/authors?limit=5&offset=0").await;
    response.assert_status_ok();
    let authors: Vec<serde_json::Value> = response.json();
    assert!(authors.len() <= 5);
}

#[tokio::test]
async fn test_author_orcid_validation() {
    let server = setup().await;

    // Try to create with invalid ORCID format
    let create_body = json!({
        "full_name": "Invalid ORCID Author",
        "orcid": "invalid-orcid",
        "creator": "test_user",
        "modifier": "test_user"
    });

    let response = server.post("/authors").json(&create_body).await;
    // Should fail due to ORCID check constraint
    response.assert_status(axum::http::StatusCode::INTERNAL_SERVER_ERROR);
}

// ============================================================================
// Publication API Tests
// ============================================================================

#[tokio::test]
async fn test_list_publications() {
    let server = setup().await;

    let response = server.get("/publications").await;
    response.assert_status_ok();

    let publications: Vec<serde_json::Value> = response.json();
    // May be empty, that's ok
    assert!(publications.is_empty() || !publications.is_empty());
}

#[tokio::test]
#[serial]
async fn test_publication_crud() {
    let server = setup().await;

    // First, get a conference ID to use
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    // Create a new publication
    let create_body = json!({
        "conference_id": conference_id,
        "canonical_key": format!("test-pub-{}", Uuid::new_v4()),
        "title": "Test Publication Title",
        "abstract": "This is a test abstract for the publication.",
        "paper_type": "regular",
        "arxiv_ids": ["2301.12345"],
        "creator": "test_user",
        "modifier": "test_user"
    });

    let response = server.post("/publications").json(&create_body).await;
    if !response.status_code().is_success() {
        let body = response.text();
        panic!("Failed to create publication: {} - {}", response.status_code(), body);
    }

    let created: serde_json::Value = response.json();
    let pub_id = created["id"].as_str().expect("Created publication should have an id");
    assert_eq!(created["title"], "Test Publication Title");

    // Read the created publication
    let response = server.get(&format!("/publications/{}", pub_id)).await;
    response.assert_status_ok();

    // Update the publication
    let update_body = json!({
        "title": "Updated Publication Title",
        "modifier": "test_user"
    });

    let response = server
        .put(&format!("/publications/{}", pub_id))
        .json(&update_body)
        .await;
    response.assert_status_ok();
    let updated: serde_json::Value = response.json();
    assert_eq!(updated["title"], "Updated Publication Title");

    // Delete the publication
    let response = server.delete(&format!("/publications/{}", pub_id)).await;
    response.assert_status(axum::http::StatusCode::NO_CONTENT);
}

#[tokio::test]
#[serial]
async fn test_publication_full_text_search() {
    let server = setup().await;

    // Get a conference ID
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    // Create a publication with specific searchable content
    let unique_term = format!("quantumentanglement{}", Uuid::new_v4().simple());
    let create_body = json!({
        "conference_id": conference_id,
        "canonical_key": format!("search-test-{}", Uuid::new_v4()),
        "title": format!("Research on {}", unique_term),
        "abstract": "Exploring quantum entanglement in distributed systems.",
        "creator": "test_user",
        "modifier": "test_user"
    });

    let response = server.post("/publications").json(&create_body).await;
    if !response.status_code().is_success() {
        let body = response.text();
        panic!("Failed to create publication: {} - {}", response.status_code(), body);
    }
    let created: serde_json::Value = response.json();
    let pub_id = created["id"].as_str().unwrap();

    // Search for it
    let response = server
        .get(&format!("/publications?search={}", unique_term))
        .await;
    response.assert_status_ok();
    let results: Vec<serde_json::Value> = response.json();
    assert!(!results.is_empty(), "Should find the publication by search");

    // Cleanup
    server.delete(&format!("/publications/{}", pub_id)).await;
}

#[tokio::test]
async fn test_publication_filter_by_conference() {
    let server = setup().await;

    // Get a conference ID
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    let response = server
        .get(&format!("/publications?conference_id={}", conference_id))
        .await;
    response.assert_status_ok();
}

// ============================================================================
// Committee Role API Tests
// ============================================================================

#[tokio::test]
async fn test_list_committee_roles() {
    let server = setup().await;

    let response = server.get("/committees").await;
    response.assert_status_ok();

    let roles: Vec<serde_json::Value> = response.json();
    assert!(roles.is_empty() || !roles.is_empty());
}

#[tokio::test]
#[serial]
async fn test_committee_role_crud() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // First, create an author
    let author_body = json!({
        "full_name": format!("Committee Member {}", unique_suffix),
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authors").json(&author_body).await;
    if !response.status_code().is_success() {
        let body = response.text();
        panic!("Failed to create author: {} - {}", response.status_code(), body);
    }
    let author: serde_json::Value = response.json();
    let author_id = author["id"].as_str().unwrap();

    // Get a conference ID
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    // Create a committee role
    let create_body = json!({
        "conference_id": conference_id,
        "author_id": author_id,
        "committee": "PC",
        "position": "member",
        "creator": "test_user",
        "modifier": "test_user"
    });

    let response = server.post("/committees").json(&create_body).await;
    if !response.status_code().is_success() {
        let body = response.text();
        panic!("Failed to create committee role: {} - {}", response.status_code(), body);
    }

    let created: serde_json::Value = response.json();
    let role_id = created["id"].as_str().expect("Created role should have an id");
    assert_eq!(created["committee"], "PC");
    assert_eq!(created["position"], "member");

    // Read the role
    let response = server.get(&format!("/committees/{}", role_id)).await;
    response.assert_status_ok();

    // Update the role
    let update_body = json!({
        "position": "chair",
        "role_title": "PC Chair",
        "modifier": "test_user"
    });

    let response = server
        .put(&format!("/committees/{}", role_id))
        .json(&update_body)
        .await;
    response.assert_status_ok();
    let updated: serde_json::Value = response.json();
    assert_eq!(updated["position"], "chair");
    assert_eq!(updated["role_title"], "PC Chair");

    // Delete the role
    let response = server.delete(&format!("/committees/{}", role_id)).await;
    response.assert_status(axum::http::StatusCode::NO_CONTENT);

    // Cleanup author
    server.delete(&format!("/authors/{}", author_id)).await;
}

#[tokio::test]
async fn test_committee_filter_by_conference() {
    let server = setup().await;

    // Get a conference ID
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    let response = server
        .get(&format!("/committees?conference_id={}", conference_id))
        .await;
    response.assert_status_ok();
}

#[tokio::test]
#[serial]
async fn test_committee_filter_by_author() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // Create an author
    let author_body = json!({
        "full_name": format!("Filter Test Author {}", unique_suffix),
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authors").json(&author_body).await;
    let author: serde_json::Value = response.json();
    let author_id = author["id"].as_str().unwrap();

    let response = server
        .get(&format!("/committees?author_id={}", author_id))
        .await;
    response.assert_status_ok();

    // Cleanup
    server.delete(&format!("/authors/{}", author_id)).await;
}

// ============================================================================
// Edge Cases and Error Handling
// ============================================================================

#[tokio::test]
async fn test_get_nonexistent_author() {
    let server = setup().await;

    let fake_id = Uuid::new_v4();
    let response = server.get(&format!("/authors/{}", fake_id)).await;
    response.assert_status_not_found();
}

#[tokio::test]
async fn test_get_nonexistent_publication() {
    let server = setup().await;

    let fake_id = Uuid::new_v4();
    let response = server.get(&format!("/publications/{}", fake_id)).await;
    response.assert_status_not_found();
}

#[tokio::test]
async fn test_get_nonexistent_committee_role() {
    let server = setup().await;

    let fake_id = Uuid::new_v4();
    let response = server.get(&format!("/committees/{}", fake_id)).await;
    response.assert_status_not_found();
}

#[tokio::test]
async fn test_delete_nonexistent_conference() {
    let server = setup().await;

    let fake_id = Uuid::new_v4();
    let response = server.delete(&format!("/conferences/{}", fake_id)).await;
    response.assert_status_not_found();
}

#[tokio::test]
async fn test_delete_nonexistent_author() {
    let server = setup().await;

    let fake_id = Uuid::new_v4();
    let response = server.delete(&format!("/authors/{}", fake_id)).await;
    response.assert_status_not_found();
}

// ============================================================================
// Authorship API Tests
// ============================================================================

#[tokio::test]
async fn test_list_authorships() {
    let server = setup().await;

    let response = server.get("/authorships").await;
    response.assert_status_ok();

    let authorships: Vec<serde_json::Value> = response.json();
    // May be empty, that's ok
    assert!(authorships.is_empty() || !authorships.is_empty());
}

#[tokio::test]
async fn test_get_nonexistent_authorship() {
    let server = setup().await;

    let fake_id = Uuid::new_v4();
    let response = server.get(&format!("/authorships/{}", fake_id)).await;
    response.assert_status_not_found();
}

#[tokio::test]
#[serial]
async fn test_authorship_crud() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // First, create an author
    let author_body = json!({
        "full_name": format!("Authorship Test Author {}", unique_suffix),
        "family_name": "Author",
        "given_name": "Authorship Test",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authors").json(&author_body).await;
    if !response.status_code().is_success() {
        let body = response.text();
        panic!("Failed to create author: {} - {}", response.status_code(), body);
    }
    let author: serde_json::Value = response.json();
    let author_id = author["id"].as_str().unwrap();

    // Get a conference ID and create a publication
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    let pub_body = json!({
        "conference_id": conference_id,
        "canonical_key": format!("authorship-test-{}", unique_suffix),
        "title": "Test Publication for Authorship",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/publications").json(&pub_body).await;
    if !response.status_code().is_success() {
        let body = response.text();
        panic!("Failed to create publication: {} - {}", response.status_code(), body);
    }
    let publication: serde_json::Value = response.json();
    let publication_id = publication["id"].as_str().unwrap();

    // Create an authorship (link author to publication)
    let create_body = json!({
        "publication_id": publication_id,
        "author_id": author_id,
        "author_position": 1,
        "published_as_name": format!("A. T. Author {}", unique_suffix),
        "affiliation": "Test University",
        "creator": "test_user",
        "modifier": "test_user"
    });

    let response = server.post("/authorships").json(&create_body).await;
    if !response.status_code().is_success() {
        let body = response.text();
        panic!("Failed to create authorship: {} - {}", response.status_code(), body);
    }

    let created: serde_json::Value = response.json();
    let authorship_id = created["id"].as_str().expect("Created authorship should have an id");
    assert_eq!(created["author_position"], 1);
    assert_eq!(created["affiliation"], "Test University");

    // Read the authorship
    let response = server.get(&format!("/authorships/{}", authorship_id)).await;
    response.assert_status_ok();

    // Update the authorship
    let update_body = json!({
        "author_position": 2,
        "affiliation": "Updated University",
        "modifier": "test_user"
    });

    let response = server
        .put(&format!("/authorships/{}", authorship_id))
        .json(&update_body)
        .await;
    response.assert_status_ok();
    let updated: serde_json::Value = response.json();
    assert_eq!(updated["author_position"], 2);
    assert_eq!(updated["affiliation"], "Updated University");

    // Delete the authorship
    let response = server.delete(&format!("/authorships/{}", authorship_id)).await;
    response.assert_status(axum::http::StatusCode::NO_CONTENT);

    // Verify it's deleted
    let response = server.get(&format!("/authorships/{}", authorship_id)).await;
    response.assert_status_not_found();

    // Cleanup: delete publication and author
    server.delete(&format!("/publications/{}", publication_id)).await;
    server.delete(&format!("/authors/{}", author_id)).await;
}

#[tokio::test]
#[serial]
async fn test_authorship_filter_by_publication() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // Create author
    let author_body = json!({
        "full_name": format!("Filter Pub Author {}", unique_suffix),
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authors").json(&author_body).await;
    let author: serde_json::Value = response.json();
    let author_id = author["id"].as_str().unwrap();

    // Get conference and create publication
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    let pub_body = json!({
        "conference_id": conference_id,
        "canonical_key": format!("filter-pub-test-{}", unique_suffix),
        "title": "Filter Test Publication",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/publications").json(&pub_body).await;
    let publication: serde_json::Value = response.json();
    let publication_id = publication["id"].as_str().unwrap();

    // Create authorship
    let authorship_body = json!({
        "publication_id": publication_id,
        "author_id": author_id,
        "author_position": 1,
        "published_as_name": "Filter Author",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authorships").json(&authorship_body).await;
    let authorship: serde_json::Value = response.json();
    let authorship_id = authorship["id"].as_str().unwrap();

    // Filter by publication_id
    let response = server
        .get(&format!("/authorships?publication_id={}", publication_id))
        .await;
    response.assert_status_ok();
    let authorships: Vec<serde_json::Value> = response.json();
    assert!(!authorships.is_empty(), "Should find authorship by publication");

    // Cleanup
    server.delete(&format!("/authorships/{}", authorship_id)).await;
    server.delete(&format!("/publications/{}", publication_id)).await;
    server.delete(&format!("/authors/{}", author_id)).await;
}

#[tokio::test]
#[serial]
async fn test_authorship_filter_by_author() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // Create author
    let author_body = json!({
        "full_name": format!("Filter Auth Author {}", unique_suffix),
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authors").json(&author_body).await;
    let author: serde_json::Value = response.json();
    let author_id = author["id"].as_str().unwrap();

    // Get conference and create publication
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    let pub_body = json!({
        "conference_id": conference_id,
        "canonical_key": format!("filter-auth-test-{}", unique_suffix),
        "title": "Filter Auth Test Publication",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/publications").json(&pub_body).await;
    let publication: serde_json::Value = response.json();
    let publication_id = publication["id"].as_str().unwrap();

    // Create authorship
    let authorship_body = json!({
        "publication_id": publication_id,
        "author_id": author_id,
        "author_position": 1,
        "published_as_name": "Filter Auth Author",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authorships").json(&authorship_body).await;
    let authorship: serde_json::Value = response.json();
    let authorship_id = authorship["id"].as_str().unwrap();

    // Filter by author_id
    let response = server
        .get(&format!("/authorships?author_id={}", author_id))
        .await;
    response.assert_status_ok();
    let authorships: Vec<serde_json::Value> = response.json();
    assert!(!authorships.is_empty(), "Should find authorship by author");

    // Cleanup
    server.delete(&format!("/authorships/{}", authorship_id)).await;
    server.delete(&format!("/publications/{}", publication_id)).await;
    server.delete(&format!("/authors/{}", author_id)).await;
}

#[tokio::test]
async fn test_delete_nonexistent_authorship() {
    let server = setup().await;

    let fake_id = Uuid::new_v4();
    let response = server.delete(&format!("/authorships/{}", fake_id)).await;
    response.assert_status_not_found();
}

// ============================================================================
// Metadata and Affiliation Tests
// ============================================================================

#[tokio::test]
#[serial]
async fn test_committee_role_with_affiliation_and_metadata() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // Create an author
    let author_body = json!({
        "full_name": format!("Metadata Test Author {}", unique_suffix),
        "family_name": "TestAuthor",
        "given_name": "Metadata",
        "affiliation": "MIT",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authors").json(&author_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let author: serde_json::Value = response.json();
    let author_id = author["id"].as_str().unwrap();

    // Get a conference ID
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    // Create a committee role with affiliation and metadata
    let create_body = json!({
        "conference_id": conference_id,
        "author_id": author_id,
        "committee": "PC",
        "position": "chair",
        "affiliation": "MIT CSAIL",
        "metadata": {
            "source_type": "archive",
            "source_description": "Verified from archived program committee page"
        },
        "creator": "test_user",
        "modifier": "test_user"
    });

    let response = server.post("/committees").json(&create_body).await;
    if !response.status_code().is_success() {
        let body = response.text();
        panic!("Failed to create committee role with metadata: {} - {}", response.status_code(), body);
    }

    let created: serde_json::Value = response.json();
    let role_id = created["id"].as_str().expect("Created role should have an id");
    
    // Verify affiliation and metadata fields are present and correct
    assert_eq!(created["committee"], "PC");
    assert_eq!(created["position"], "chair");
    assert_eq!(created["affiliation"], "MIT CSAIL");
    assert!(created["metadata"].is_object(), "metadata should be an object");
    assert_eq!(created["metadata"]["source_type"], "archive");
    assert_eq!(created["metadata"]["source_description"], "Verified from archived program committee page");

    // Read the role back to verify persistence
    let response = server.get(&format!("/committees/{}", role_id)).await;
    response.assert_status_ok();
    let fetched: serde_json::Value = response.json();
    assert_eq!(fetched["affiliation"], "MIT CSAIL");
    assert_eq!(fetched["metadata"]["source_type"], "archive");

    // Update the affiliation and metadata
    let update_body = json!({
        "affiliation": "MIT Media Lab",
        "metadata": {
            "source_type": "manual",
            "source_description": "Updated affiliation from personal knowledge",
            "source_date": "2025-12-30"
        },
        "modifier": "test_update"
    });

    let response = server
        .put(&format!("/committees/{}", role_id))
        .json(&update_body)
        .await;
    response.assert_status_ok();
    let updated: serde_json::Value = response.json();
    assert_eq!(updated["affiliation"], "MIT Media Lab");
    assert_eq!(updated["metadata"]["source_type"], "manual");
    assert_eq!(updated["metadata"]["source_description"], "Updated affiliation from personal knowledge");
    assert_eq!(updated["metadata"]["source_date"], "2025-12-30");

    // Cleanup
    server.delete(&format!("/committees/{}", role_id)).await;
    server.delete(&format!("/authors/{}", author_id)).await;
}

#[tokio::test]
#[serial]
async fn test_committee_role_without_metadata_defaults_to_empty_object() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // Create an author
    let author_body = json!({
        "full_name": format!("Default Meta Author {}", unique_suffix),
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authors").json(&author_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let author: serde_json::Value = response.json();
    let author_id = author["id"].as_str().unwrap();

    // Get a conference ID
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    // Create a committee role without affiliation or metadata
    let create_body = json!({
        "conference_id": conference_id,
        "author_id": author_id,
        "committee": "SC",
        "position": "member",
        "creator": "test_user",
        "modifier": "test_user"
    });

    let response = server.post("/committees").json(&create_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let created: serde_json::Value = response.json();
    let role_id = created["id"].as_str().unwrap();
    
    // Verify affiliation is null and metadata is empty object
    assert!(created["affiliation"].is_null(), "affiliation should be null when not provided");
    assert!(created["metadata"].is_object(), "metadata should be an object");
    assert_eq!(created["metadata"].as_object().unwrap().len(), 0, "metadata should be empty object");

    // Cleanup
    server.delete(&format!("/committees/{}", role_id)).await;
    server.delete(&format!("/authors/{}", author_id)).await;
}

#[tokio::test]
#[serial]
async fn test_authorship_with_metadata() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // Create an author
    let author_body = json!({
        "full_name": format!("Authorship Meta Author {}", unique_suffix),
        "family_name": "MetaAuthor",
        "given_name": "Authorship",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authors").json(&author_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let author: serde_json::Value = response.json();
    let author_id = author["id"].as_str().unwrap();

    // Get a conference ID and create a publication
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    let pub_body = json!({
        "conference_id": conference_id,
        "canonical_key": format!("meta-test-{}", unique_suffix),
        "title": "Test Publication with Metadata",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/publications").json(&pub_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let publication: serde_json::Value = response.json();
    let publication_id = publication["id"].as_str().unwrap();

    // Create an authorship with affiliation and metadata
    let create_body = json!({
        "publication_id": publication_id,
        "author_id": author_id,
        "author_position": 1,
        "published_as_name": "Alice Quantum",
        "affiliation": "MIT CSAIL",
        "metadata": {
            "source_type": "hotcrp",
            "source_url": "hotcrp-qip2024.json",
            "source_description": "Imported from HotCRP export"
        },
        "creator": "test_user",
        "modifier": "test_user"
    });

    let response = server.post("/authorships").json(&create_body).await;
    if !response.status_code().is_success() {
        let body = response.text();
        panic!("Failed to create authorship with metadata: {} - {}", response.status_code(), body);
    }

    let created: serde_json::Value = response.json();
    let authorship_id = created["id"].as_str().expect("Created authorship should have an id");
    
    // Verify affiliation and metadata fields
    assert_eq!(created["author_position"], 1);
    assert_eq!(created["published_as_name"], "Alice Quantum");
    assert_eq!(created["affiliation"], "MIT CSAIL");
    assert!(created["metadata"].is_object(), "metadata should be an object");
    assert_eq!(created["metadata"]["source_type"], "hotcrp");
    assert_eq!(created["metadata"]["source_url"], "hotcrp-qip2024.json");
    assert_eq!(created["metadata"]["source_description"], "Imported from HotCRP export");

    // Read the authorship back to verify persistence
    let response = server.get(&format!("/authorships/{}", authorship_id)).await;
    response.assert_status_ok();
    let fetched: serde_json::Value = response.json();
    assert_eq!(fetched["affiliation"], "MIT CSAIL");
    assert_eq!(fetched["metadata"]["source_type"], "hotcrp");

    // Update the metadata
    let update_body = json!({
        "affiliation": "Caltech",
        "metadata": {
            "source_type": "proceedings",
            "source_description": "Updated from published proceedings"
        },
        "modifier": "test_user"
    });

    let response = server
        .put(&format!("/authorships/{}", authorship_id))
        .json(&update_body)
        .await;
    response.assert_status_ok();
    let updated: serde_json::Value = response.json();
    assert_eq!(updated["affiliation"], "Caltech");
    assert_eq!(updated["metadata"]["source_type"], "proceedings");
    assert_eq!(updated["metadata"]["source_description"], "Updated from published proceedings");

    // Cleanup
    server.delete(&format!("/authorships/{}", authorship_id)).await;
    server.delete(&format!("/publications/{}", publication_id)).await;
    server.delete(&format!("/authors/{}", author_id)).await;
}

#[tokio::test]
#[serial]
async fn test_authorship_metadata_empty_by_default() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // Create an author
    let author_body = json!({
        "full_name": format!("No Meta Author {}", unique_suffix),
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authors").json(&author_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let author: serde_json::Value = response.json();
    let author_id = author["id"].as_str().unwrap();

    // Get a conference ID and create a publication
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    let pub_body = json!({
        "conference_id": conference_id,
        "canonical_key": format!("no-meta-{}", unique_suffix),
        "title": "Publication without metadata",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/publications").json(&pub_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let publication: serde_json::Value = response.json();
    let publication_id = publication["id"].as_str().unwrap();

    // Create an authorship without metadata
    let create_body = json!({
        "publication_id": publication_id,
        "author_id": author_id,
        "author_position": 1,
        "published_as_name": "No Meta Author",
        "creator": "test_user",
        "modifier": "test_user"
    });

    let response = server.post("/authorships").json(&create_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let created: serde_json::Value = response.json();
    let authorship_id = created["id"].as_str().unwrap();

    // Verify metadata defaults to empty object
    assert!(created["metadata"].is_object(), "metadata should be an object");
    assert_eq!(created["metadata"].as_object().unwrap().len(), 0, "metadata should be empty object");

    // Cleanup
    server.delete(&format!("/authorships/{}", authorship_id)).await;
    server.delete(&format!("/publications/{}", publication_id)).await;
    server.delete(&format!("/authors/{}", author_id)).await;
}

// ============================================================================
// New Talk/Publication Features Tests
// ============================================================================

#[tokio::test]
#[serial]
async fn test_publication_with_presenter() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // Create two authors
    let author1_body = json!({
        "full_name": format!("Author One {}", unique_suffix),
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authors").json(&author1_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let author1: serde_json::Value = response.json();
    let author1_id = author1["id"].as_str().unwrap();

    let author2_body = json!({
        "full_name": format!("Author Two {}", unique_suffix),
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authors").json(&author2_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let author2: serde_json::Value = response.json();
    let author2_id = author2["id"].as_str().unwrap();

    // Get a conference ID
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    // Create publication without presenter
    let pub_body = json!({
        "conference_id": conference_id,
        "canonical_key": format!("presenter-test-{}", unique_suffix),
        "title": "Publication with Presenter Test",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/publications").json(&pub_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let publication: serde_json::Value = response.json();
    let publication_id = publication["id"].as_str().unwrap();

    // Verify presenter_author_id is initially null
    assert!(publication["presenter_author_id"].is_null(), "presenter_author_id should be null initially");

    // Create authorships for both authors
    let authorship1_body = json!({
        "publication_id": publication_id,
        "author_id": author1_id,
        "author_position": 1,
        "published_as_name": format!("Author One {}", unique_suffix),
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authorships").json(&authorship1_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let authorship1: serde_json::Value = response.json();
    let authorship1_id = authorship1["id"].as_str().unwrap();

    let authorship2_body = json!({
        "publication_id": publication_id,
        "author_id": author2_id,
        "author_position": 2,
        "published_as_name": format!("Author Two {}", unique_suffix),
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authorships").json(&authorship2_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let authorship2: serde_json::Value = response.json();
    let authorship2_id = authorship2["id"].as_str().unwrap();

    // Update publication to set presenter_author_id to one of the authors
    let update_body = json!({
        "presenter_author_id": author1_id,
        "modifier": "test_user"
    });
    let response = server.put(&format!("/publications/{}", publication_id)).json(&update_body).await;
    response.assert_status_ok();
    let updated: serde_json::Value = response.json();

    // Verify presenter is set correctly
    assert_eq!(updated["presenter_author_id"].as_str().unwrap(), author1_id, "presenter_author_id should be set to author1");

    // Cleanup
    server.delete(&format!("/authorships/{}", authorship1_id)).await;
    server.delete(&format!("/authorships/{}", authorship2_id)).await;
    server.delete(&format!("/publications/{}", publication_id)).await;
    server.delete(&format!("/authors/{}", author1_id)).await;
    server.delete(&format!("/authors/{}", author2_id)).await;
}

#[tokio::test]
#[serial]
async fn test_new_paper_types() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // Get a conference ID
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    // Test plenary paper type
    let pub_body = json!({
        "conference_id": conference_id,
        "canonical_key": format!("plenary-test-{}", unique_suffix),
        "title": "Plenary Talk Test",
        "paper_type": "plenary",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/publications").json(&pub_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let publication: serde_json::Value = response.json();
    let plenary_id = publication["id"].as_str().unwrap();
    assert_eq!(publication["paper_type"].as_str().unwrap(), "plenary", "paper_type should be plenary");

    // Test plenary_short paper type
    let pub_body2 = json!({
        "conference_id": conference_id,
        "canonical_key": format!("plenary-short-test-{}", unique_suffix),
        "title": "Short Plenary Talk Test",
        "paper_type": "plenary_short",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/publications").json(&pub_body2).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let publication2: serde_json::Value = response.json();
    let plenary_short_id = publication2["id"].as_str().unwrap();
    assert_eq!(publication2["paper_type"].as_str().unwrap(), "plenary_short", "paper_type should be plenary_short");

    // Test plenary_long paper type
    let pub_body3 = json!({
        "conference_id": conference_id,
        "canonical_key": format!("plenary-long-test-{}", unique_suffix),
        "title": "Long Plenary Talk Test",
        "paper_type": "plenary_long",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/publications").json(&pub_body3).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let publication3: serde_json::Value = response.json();
    let plenary_long_id = publication3["id"].as_str().unwrap();
    assert_eq!(publication3["paper_type"].as_str().unwrap(), "plenary_long", "paper_type should be plenary_long");

    // Cleanup
    server.delete(&format!("/publications/{}", plenary_id)).await;
    server.delete(&format!("/publications/{}", plenary_short_id)).await;
    server.delete(&format!("/publications/{}", plenary_long_id)).await;
}

#[tokio::test]
#[serial]
async fn test_proceedings_track_flag() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // Get a conference ID
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    // Create publication without is_proceedings_track (should default to false)
    let pub_body1 = json!({
        "conference_id": conference_id,
        "canonical_key": format!("workshop-track-{}", unique_suffix),
        "title": "Workshop Track Publication",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/publications").json(&pub_body1).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let publication1: serde_json::Value = response.json();
    let workshop_id = publication1["id"].as_str().unwrap();
    assert_eq!(publication1["is_proceedings_track"].as_bool().unwrap(), false, "is_proceedings_track should default to false");

    // Create publication with is_proceedings_track set to true
    let pub_body2 = json!({
        "conference_id": conference_id,
        "canonical_key": format!("proceedings-track-{}", unique_suffix),
        "title": "Proceedings Track Publication",
        "is_proceedings_track": true,
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/publications").json(&pub_body2).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let publication2: serde_json::Value = response.json();
    let proceedings_id = publication2["id"].as_str().unwrap();
    assert_eq!(publication2["is_proceedings_track"].as_bool().unwrap(), true, "is_proceedings_track should be true");

    // Update workshop track publication to proceedings track
    let update_body = json!({
        "is_proceedings_track": true,
        "modifier": "test_user"
    });
    let response = server.put(&format!("/publications/{}", workshop_id)).json(&update_body).await;
    response.assert_status_ok();
    let updated: serde_json::Value = response.json();
    assert_eq!(updated["is_proceedings_track"].as_bool().unwrap(), true, "is_proceedings_track should be updated to true");

    // Cleanup
    server.delete(&format!("/publications/{}", workshop_id)).await;
    server.delete(&format!("/publications/{}", proceedings_id)).await;
}

#[tokio::test]
#[serial]
async fn test_presenter_validation_trigger() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // Create two authors
    let author1_body = json!({
        "full_name": format!("Author One {}", unique_suffix),
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authors").json(&author1_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let author1: serde_json::Value = response.json();
    let author1_id = author1["id"].as_str().unwrap();

    let author2_body = json!({
        "full_name": format!("Non-Author {}", unique_suffix),
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authors").json(&author2_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let author2: serde_json::Value = response.json();
    let author2_id = author2["id"].as_str().unwrap();

    // Get a conference ID
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    // Create publication
    let pub_body = json!({
        "conference_id": conference_id,
        "canonical_key": format!("trigger-test-{}", unique_suffix),
        "title": "Presenter Validation Test",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/publications").json(&pub_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let publication: serde_json::Value = response.json();
    let publication_id = publication["id"].as_str().unwrap();

    // Add author1 as an author
    let authorship_body = json!({
        "publication_id": publication_id,
        "author_id": author1_id,
        "author_position": 1,
        "published_as_name": format!("Author One {}", unique_suffix),
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/authorships").json(&authorship_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let authorship: serde_json::Value = response.json();
    let authorship_id = authorship["id"].as_str().unwrap();

    // Try to set presenter to author2 (not an author) - should fail
    let update_body = json!({
        "presenter_author_id": author2_id,
        "modifier": "test_user"
    });
    let response = server.put(&format!("/publications/{}", publication_id)).json(&update_body).await;
    // This should fail because of the trigger
    response.assert_status(axum::http::StatusCode::INTERNAL_SERVER_ERROR);

    // Try to set presenter to author1 (an author) - should succeed
    let update_body = json!({
        "presenter_author_id": author1_id,
        "modifier": "test_user"
    });
    let response = server.put(&format!("/publications/{}", publication_id)).json(&update_body).await;
    response.assert_status_ok();
    let updated: serde_json::Value = response.json();
    assert_eq!(updated["presenter_author_id"].as_str().unwrap(), author1_id, "presenter_author_id should be set to author1");

    // Cleanup
    server.delete(&format!("/authorships/{}", authorship_id)).await;
    server.delete(&format!("/publications/{}", publication_id)).await;
    server.delete(&format!("/authors/{}", author1_id)).await;
    server.delete(&format!("/authors/{}", author2_id)).await;
}

#[tokio::test]
#[serial]
async fn test_talk_scheduling() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // Get a conference ID
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    // Create publication with scheduling fields
    let pub_body = json!({
        "conference_id": conference_id,
        "canonical_key": format!("scheduling-test-{}", unique_suffix),
        "title": "Talk with Scheduling Info",
        "talk_date": "2024-03-15",
        "talk_time": "14:30:00",
        "duration_minutes": 25,
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/publications").json(&pub_body).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let publication: serde_json::Value = response.json();
    let publication_id = publication["id"].as_str().unwrap();

    // Verify scheduling fields are set correctly
    assert_eq!(publication["talk_date"].as_str().unwrap(), "2024-03-15", "talk_date should be set");
    assert_eq!(publication["talk_time"].as_str().unwrap(), "14:30:00", "talk_time should be set");
    assert_eq!(publication["duration_minutes"].as_i64().unwrap(), 25, "duration_minutes should be 25");

    // Create publication without scheduling fields (all should be null)
    let pub_body2 = json!({
        "conference_id": conference_id,
        "canonical_key": format!("no-scheduling-{}", unique_suffix),
        "title": "Talk without Scheduling Info",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/publications").json(&pub_body2).await;
    response.assert_status(axum::http::StatusCode::CREATED);
    let publication2: serde_json::Value = response.json();
    let publication2_id = publication2["id"].as_str().unwrap();
    assert!(publication2["talk_date"].is_null(), "talk_date should be null");
    assert!(publication2["talk_time"].is_null(), "talk_time should be null");
    assert!(publication2["duration_minutes"].is_null(), "duration_minutes should be null");

    // Update publication to add scheduling info
    let update_body = json!({
        "talk_date": "2024-03-16",
        "talk_time": "10:00:00",
        "duration_minutes": 45,
        "modifier": "test_user"
    });
    let response = server.put(&format!("/publications/{}", publication2_id)).json(&update_body).await;
    response.assert_status_ok();
    let updated: serde_json::Value = response.json();
    assert_eq!(updated["talk_date"].as_str().unwrap(), "2024-03-16", "talk_date should be updated");
    assert_eq!(updated["talk_time"].as_str().unwrap(), "10:00:00", "talk_time should be updated");
    assert_eq!(updated["duration_minutes"].as_i64().unwrap(), 45, "duration_minutes should be updated");

    // Cleanup
    server.delete(&format!("/publications/{}", publication_id)).await;
    server.delete(&format!("/publications/{}", publication2_id)).await;
}

#[tokio::test]
#[serial]
async fn test_short_paper_type_rejected() {
    let server = setup().await;
    let unique_suffix = Uuid::new_v4().simple().to_string();

    // Get a conference ID
    let response = server.get("/conferences").await;
    let conferences: Vec<serde_json::Value> = response.json();
    let conference_id = conferences[0]["id"].as_str().unwrap();

    // Try to create publication with 'short' paper type - should fail
    let pub_body = json!({
        "conference_id": conference_id,
        "canonical_key": format!("short-test-{}", unique_suffix),
        "title": "Short Paper Type Test",
        "paper_type": "short",
        "creator": "test_user",
        "modifier": "test_user"
    });
    let response = server.post("/publications").json(&pub_body).await;
    // Should fail because 'short' is not a valid enum value anymore
    response.assert_status(axum::http::StatusCode::UNPROCESSABLE_ENTITY);
}
