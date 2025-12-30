use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

/// Committee type enum matching the database
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::Type, ToSchema)]
#[sqlx(type_name = "committee_type")]
pub enum CommitteeType {
    OC,    // Organizing Committee
    PC,    // Program Committee
    SC,    // Steering Committee
    Local, // Local Organizers
}

/// Committee position enum matching the database
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::Type, ToSchema)]
#[sqlx(type_name = "committee_position")]
pub enum CommitteePosition {
    #[sqlx(rename = "chair")]
    #[serde(rename = "chair")]
    Chair,
    #[sqlx(rename = "co_chair")]
    #[serde(rename = "co_chair")]
    CoChair,
    #[sqlx(rename = "area_chair")]
    #[serde(rename = "area_chair")]
    AreaChair,
    #[sqlx(rename = "member")]
    #[serde(rename = "member")]
    Member,
}

/// Committee role response model
#[derive(Debug, Serialize, sqlx::FromRow, ToSchema)]
pub struct CommitteeRole {
    pub id: Uuid,
    pub conference_id: Uuid,
    pub author_id: Uuid,
    pub committee: CommitteeType,
    pub position: CommitteePosition,
    pub role_title: Option<String>,
    pub term_start: Option<NaiveDate>,
    pub term_end: Option<NaiveDate>,
    pub affiliation: Option<String>,
    pub metadata: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Request model for creating a committee role
#[derive(Debug, Deserialize, ToSchema)]
pub struct CreateCommitteeRole {
    pub conference_id: Uuid,
    pub author_id: Uuid,
    pub committee: CommitteeType,
    pub position: Option<CommitteePosition>,
    pub role_title: Option<String>,
    pub term_start: Option<NaiveDate>,
    pub term_end: Option<NaiveDate>,
    pub affiliation: Option<String>,
    pub metadata: Option<serde_json::Value>,
    pub creator: String,
    pub modifier: String,
}

/// Request model for updating a committee role
#[derive(Debug, Deserialize, ToSchema)]
pub struct UpdateCommitteeRole {
    pub committee: Option<CommitteeType>,
    pub position: Option<CommitteePosition>,
    pub role_title: Option<String>,
    pub term_start: Option<NaiveDate>,
    pub term_end: Option<NaiveDate>,
    pub affiliation: Option<String>,
    pub metadata: Option<serde_json::Value>,
    pub modifier: String,
}
