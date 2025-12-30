use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

/// Author response model
#[derive(Debug, Serialize, sqlx::FromRow, ToSchema)]
pub struct Author {
    pub id: Uuid,
    pub full_name: String,
    pub family_name: Option<String>,
    pub given_name: Option<String>,
    pub normalized_name: String,
    pub orcid: Option<String>,
    pub homepage_url: Option<String>,
    pub affiliation: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Request model for creating a new author
#[derive(Debug, Deserialize, ToSchema)]
pub struct CreateAuthor {
    pub full_name: String,
    pub family_name: Option<String>,
    pub given_name: Option<String>,
    pub orcid: Option<String>,
    pub homepage_url: Option<String>,
    pub affiliation: Option<String>,
    pub creator: String,
    pub modifier: String,
}

/// Request model for updating an author
#[derive(Debug, Deserialize, ToSchema)]
pub struct UpdateAuthor {
    pub full_name: Option<String>,
    pub family_name: Option<String>,
    pub given_name: Option<String>,
    pub orcid: Option<String>,
    pub homepage_url: Option<String>,
    pub affiliation: Option<String>,
    pub modifier: String,
}

/// Author name variant for tracking alternative names
#[derive(Debug, Serialize, sqlx::FromRow, ToSchema)]
pub struct AuthorNameVariant {
    pub id: Uuid,
    pub author_id: Uuid,
    pub variant_name: String,
    pub normalized_variant: String,
    pub variant_type: Option<String>,
    pub notes: Option<String>,
    pub created_at: DateTime<Utc>,
}

// Re-export normalize_name from utils for backwards compatibility
pub use crate::utils::normalize_name;
