use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

/// Paper type enum matching the database
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::Type, ToSchema)]
#[sqlx(type_name = "paper_type", rename_all = "lowercase")]
#[serde(rename_all = "lowercase")]
pub enum PaperType {
    Regular,
    Short,
    Poster,
    Invited,
    Tutorial,
    Keynote,
}

/// Publication response model
#[derive(Debug, Serialize, sqlx::FromRow, ToSchema)]
pub struct Publication {
    pub id: Uuid,
    pub conference_id: Uuid,
    pub canonical_key: String,
    pub doi: Option<String>,
    pub arxiv_ids: Vec<String>,
    pub title: String,
    #[sqlx(rename = "abstract")]
    #[serde(rename = "abstract")]
    pub abstract_text: Option<String>,
    pub paper_type: PaperType,
    pub pages: Option<String>,
    pub session_name: Option<String>,
    pub presentation_url: Option<String>,
    pub video_url: Option<String>,
    pub youtube_id: Option<String>,
    pub award: Option<String>,
    pub award_date: Option<NaiveDate>,
    pub published_date: Option<NaiveDate>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Request model for creating a publication
#[derive(Debug, Deserialize, ToSchema)]
pub struct CreatePublication {
    pub conference_id: Uuid,
    pub canonical_key: String,
    pub doi: Option<String>,
    pub arxiv_ids: Option<Vec<String>>,
    pub title: String,
    #[serde(rename = "abstract")]
    pub abstract_text: Option<String>,
    pub paper_type: Option<PaperType>,
    pub pages: Option<String>,
    pub session_name: Option<String>,
    pub presentation_url: Option<String>,
    pub video_url: Option<String>,
    pub youtube_id: Option<String>,
    pub award: Option<String>,
    pub award_date: Option<NaiveDate>,
    pub published_date: Option<NaiveDate>,
    pub creator: String,
    pub modifier: String,
}

/// Request model for updating a publication
#[derive(Debug, Deserialize, ToSchema)]
pub struct UpdatePublication {
    pub doi: Option<String>,
    pub arxiv_ids: Option<Vec<String>>,
    pub title: Option<String>,
    #[serde(rename = "abstract")]
    pub abstract_text: Option<String>,
    pub paper_type: Option<PaperType>,
    pub pages: Option<String>,
    pub session_name: Option<String>,
    pub presentation_url: Option<String>,
    pub video_url: Option<String>,
    pub youtube_id: Option<String>,
    pub award: Option<String>,
    pub award_date: Option<NaiveDate>,
    pub published_date: Option<NaiveDate>,
    pub modifier: String,
}

/// Authorship linking an author to a publication
#[derive(Debug, Serialize, sqlx::FromRow, ToSchema)]
pub struct Authorship {
    pub id: Uuid,
    pub publication_id: Uuid,
    pub author_id: Uuid,
    pub author_position: i32,
    pub published_as_name: String,
    pub affiliation: Option<String>,
    pub metadata: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Request model for adding an author to a publication
#[derive(Debug, Deserialize, ToSchema)]
pub struct CreateAuthorship {
    pub publication_id: Uuid,
    pub author_id: Uuid,
    pub author_position: i32,
    pub published_as_name: String,
    pub affiliation: Option<String>,
    pub metadata: Option<serde_json::Value>,
    pub creator: String,
    pub modifier: String,
}

/// Request model for updating an authorship
#[derive(Debug, Deserialize, ToSchema)]
pub struct UpdateAuthorship {
    pub author_position: Option<i32>,
    pub published_as_name: Option<String>,
    pub affiliation: Option<String>,
    pub metadata: Option<serde_json::Value>,
    pub modifier: String,
}
