use chrono::{DateTime, NaiveDate, NaiveTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

/// Paper type enum matching the database
/// Types represent what appears in conference programs, not selection mechanism
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::Type, ToSchema)]
#[sqlx(type_name = "paper_type", rename_all = "snake_case")]
#[serde(rename_all = "lowercase")]
pub enum PaperType {
    /// Standard contributed talk (peer-reviewed)
    Regular,
    /// Poster presentation (peer-reviewed)
    Poster,
    /// Invited talk
    Invited,
    /// Tutorial session
    Tutorial,
    /// Keynote address
    Keynote,
    /// Contributed plenary talk (peer-reviewed, more prestigious)
    Plenary,
    /// Short plenary talk at QIP (15 min, peer-reviewed)
    #[serde(rename = "plenary_short")]
    PlenaryShort,
    /// Long plenary talk at QIP (25+ min, peer-reviewed)
    #[serde(rename = "plenary_long")]
    PlenaryLong,
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
    /// Author who presented the talk (must be one of the authors)
    /// Often unknown for contributed talks, may be inferred from video/slides
    pub presenter_author_id: Option<Uuid>,
    /// Whether this is in the formal proceedings track (TQC only)
    /// TQC has both proceedings and workshop tracks; QIP/QCrypt are workshop-style only
    pub is_proceedings_track: bool,
    /// Date when the talk was given (if known)
    pub talk_date: Option<NaiveDate>,
    /// Time when the talk started (if known)
    pub talk_time: Option<NaiveTime>,
    /// Duration of the talk in minutes (if known)
    pub duration_minutes: Option<i32>,
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
    /// Author who presented the talk (must be one of the authors)
    pub presenter_author_id: Option<Uuid>,
    /// Whether this is in the formal proceedings track
    pub is_proceedings_track: Option<bool>,
    /// Date when the talk was given
    pub talk_date: Option<NaiveDate>,
    /// Time when the talk started
    pub talk_time: Option<NaiveTime>,
    /// Duration of the talk in minutes
    pub duration_minutes: Option<i32>,
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
    /// Author who presented the talk (must be one of the authors)
    pub presenter_author_id: Option<Uuid>,
    /// Whether this is in the formal proceedings track
    pub is_proceedings_track: Option<bool>,
    /// Date when the talk was given
    pub talk_date: Option<NaiveDate>,
    /// Time when the talk started
    pub talk_time: Option<NaiveTime>,
    /// Duration of the talk in minutes
    pub duration_minutes: Option<i32>,
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
