use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use utoipa::ToSchema;
use uuid::Uuid;

/// Statistics announced at a conference's annual business meeting (1:1 with a
/// conference). These are the figures the PC/local chairs reported at the
/// meeting — a sourced, point-in-time record — and are deliberately distinct
/// from the counts computed in the `conference_stats` materialized view.
#[derive(Debug, Serialize, sqlx::FromRow, ToSchema)]
pub struct BusinessMeeting {
    pub id: Uuid,
    pub conference_id: Uuid,
    pub meeting_date: Option<NaiveDate>,

    // Announced participation
    pub registered_participants: Option<i32>,
    pub onsite_participants: Option<i32>,
    pub countries_represented: Option<i32>,

    // Announced submission / acceptance
    pub talk_submissions: Option<i32>,
    pub talks_accepted: Option<i32>,
    pub posters_submitted: Option<i32>,
    pub posters_accepted: Option<i32>,
    /// Announced acceptance rate (percent), when stated directly. Stored as
    /// NUMERIC(4,1) in Postgres; query it with `acceptance_rate::text` when a
    /// numeric Rust type isn't wired up.
    pub acceptance_rate: Option<f64>,

    /// TQC proceedings/workshop/poster-only splits (the headline totals live in
    /// the columns above).
    pub track_breakdown: Option<Value>,
    /// Ordered array of `{label, url}` links to the slide decks (PC chair
    /// report, local organizers report, …).
    pub slides: Value,
    /// Free-form narrative — anything else announced.
    pub notes: Option<String>,
    /// Per-fact provenance: `{"sources": {field: {source_type, source_url, source_date}}}`.
    pub metadata: Value,

    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Payload for creating a business-meeting record.
#[derive(Debug, Deserialize, ToSchema)]
pub struct CreateBusinessMeeting {
    pub conference_id: Uuid,
    pub meeting_date: Option<NaiveDate>,
    pub registered_participants: Option<i32>,
    pub onsite_participants: Option<i32>,
    pub countries_represented: Option<i32>,
    pub talk_submissions: Option<i32>,
    pub talks_accepted: Option<i32>,
    pub posters_submitted: Option<i32>,
    pub posters_accepted: Option<i32>,
    pub acceptance_rate: Option<f64>,
    pub track_breakdown: Option<Value>,
    pub slides: Option<Value>,
    pub notes: Option<String>,
    pub metadata: Option<Value>,
    pub creator: String,
    pub modifier: String,
}

/// Payload for updating a business-meeting record (all fields optional).
#[derive(Debug, Deserialize, ToSchema)]
pub struct UpdateBusinessMeeting {
    pub meeting_date: Option<NaiveDate>,
    pub registered_participants: Option<i32>,
    pub onsite_participants: Option<i32>,
    pub countries_represented: Option<i32>,
    pub talk_submissions: Option<i32>,
    pub talks_accepted: Option<i32>,
    pub posters_submitted: Option<i32>,
    pub posters_accepted: Option<i32>,
    pub acceptance_rate: Option<f64>,
    pub track_breakdown: Option<Value>,
    pub slides: Option<Value>,
    pub notes: Option<String>,
    pub metadata: Option<Value>,
    pub modifier: String,
}
