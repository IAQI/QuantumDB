use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize, Serializer};
use utoipa::ToSchema;
use uuid::Uuid;

/// Conference response model (matches database schema)
#[derive(Debug, sqlx::FromRow, ToSchema)]
pub struct Conference {
    pub id: Uuid,
    pub venue: String,
    pub year: i32,
    pub start_date: Option<NaiveDate>,
    pub end_date: Option<NaiveDate>,
    pub city: Option<String>,
    pub country: Option<String>,
    pub country_code: Option<String>,
    pub is_virtual: Option<bool>,
    pub is_hybrid: Option<bool>,
    pub timezone: Option<String>,
    pub venue_name: Option<String>,
    /// Original conference website URL (may become unavailable over time)
    pub website_url: Option<String>,
    pub proceedings_url: Option<String>,
    pub proceedings_publisher: Option<String>,
    pub proceedings_volume: Option<String>,
    pub proceedings_doi: Option<String>,
    pub submission_count: Option<i32>,
    pub acceptance_count: Option<i32>,
    /// Static archive root URL (e.g., https://qip.iaqi.org/2024/)
    pub archive_url: Option<String>,
    /// Archive URL for local organizing committee page
    pub archive_organizers_url: Option<String>,
    /// Archive URL for program committee page
    pub archive_pc_url: Option<String>,
    /// Archive URL for steering committee page
    pub archive_steering_url: Option<String>,
    /// Archive URL for conference program/schedule page
    pub archive_program_url: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl Conference {
    /// Get the human-friendly slug (e.g., QIP2024, QCRYPT2018)
    pub fn slug(&self) -> String {
        format!("{}{}", self.venue.to_uppercase(), self.year)
    }
}

// Custom serialization to include computed slug field
impl Serialize for Conference {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        use serde::ser::SerializeStruct;
        let mut state = serializer.serialize_struct("Conference", 27)?;
        state.serialize_field("id", &self.id)?;
        state.serialize_field("slug", &self.slug())?;
        state.serialize_field("venue", &self.venue)?;
        state.serialize_field("year", &self.year)?;
        state.serialize_field("start_date", &self.start_date)?;
        state.serialize_field("end_date", &self.end_date)?;
        state.serialize_field("city", &self.city)?;
        state.serialize_field("country", &self.country)?;
        state.serialize_field("country_code", &self.country_code)?;
        state.serialize_field("is_virtual", &self.is_virtual)?;
        state.serialize_field("is_hybrid", &self.is_hybrid)?;
        state.serialize_field("timezone", &self.timezone)?;
        state.serialize_field("venue_name", &self.venue_name)?;
        state.serialize_field("website_url", &self.website_url)?;
        state.serialize_field("proceedings_url", &self.proceedings_url)?;
        state.serialize_field("proceedings_publisher", &self.proceedings_publisher)?;
        state.serialize_field("proceedings_volume", &self.proceedings_volume)?;
        state.serialize_field("proceedings_doi", &self.proceedings_doi)?;
        state.serialize_field("submission_count", &self.submission_count)?;
        state.serialize_field("acceptance_count", &self.acceptance_count)?;
        state.serialize_field("archive_url", &self.archive_url)?;
        state.serialize_field("archive_organizers_url", &self.archive_organizers_url)?;
        state.serialize_field("archive_pc_url", &self.archive_pc_url)?;
        state.serialize_field("archive_steering_url", &self.archive_steering_url)?;
        state.serialize_field("archive_program_url", &self.archive_program_url)?;
        state.serialize_field("created_at", &self.created_at)?;
        state.serialize_field("updated_at", &self.updated_at)?;
        state.end()
    }
}

/// Request model for creating a new conference
#[derive(Debug, Deserialize, ToSchema)]
pub struct CreateConference {
    pub venue: String,
    pub year: i32,
    pub start_date: Option<NaiveDate>,
    pub end_date: Option<NaiveDate>,
    pub city: Option<String>,
    pub country: Option<String>,
    pub country_code: Option<String>,
    pub is_virtual: Option<bool>,
    pub is_hybrid: Option<bool>,
    pub timezone: Option<String>,
    pub venue_name: Option<String>,
    /// Original conference website URL
    pub website_url: Option<String>,
    pub proceedings_url: Option<String>,
    pub proceedings_publisher: Option<String>,
    pub proceedings_volume: Option<String>,
    pub proceedings_doi: Option<String>,
    pub submission_count: Option<i32>,
    pub acceptance_count: Option<i32>,
    /// Static archive root URL (e.g., https://qip.iaqi.org/2024/)
    pub archive_url: Option<String>,
    /// Archive URL for local organizing committee page
    pub archive_organizers_url: Option<String>,
    /// Archive URL for program committee page
    pub archive_pc_url: Option<String>,
    /// Archive URL for steering committee page
    pub archive_steering_url: Option<String>,
    /// Archive URL for conference program/schedule page
    pub archive_program_url: Option<String>,
    pub creator: String,
    pub modifier: String,
}

/// Request model for updating a conference
#[derive(Debug, Deserialize, ToSchema)]
pub struct UpdateConference {
    pub venue: Option<String>,
    pub year: Option<i32>,
    pub start_date: Option<NaiveDate>,
    pub end_date: Option<NaiveDate>,
    pub city: Option<String>,
    pub country: Option<String>,
    pub country_code: Option<String>,
    pub is_virtual: Option<bool>,
    pub is_hybrid: Option<bool>,
    pub timezone: Option<String>,
    pub venue_name: Option<String>,
    /// Original conference website URL
    pub website_url: Option<String>,
    pub proceedings_url: Option<String>,
    pub proceedings_publisher: Option<String>,
    pub proceedings_volume: Option<String>,
    pub proceedings_doi: Option<String>,
    pub submission_count: Option<i32>,
    pub acceptance_count: Option<i32>,
    /// Static archive root URL (e.g., https://qip.iaqi.org/2024/)
    pub archive_url: Option<String>,
    /// Archive URL for local organizing committee page
    pub archive_organizers_url: Option<String>,
    /// Archive URL for program committee page
    pub archive_pc_url: Option<String>,
    /// Archive URL for steering committee page
    pub archive_steering_url: Option<String>,
    /// Archive URL for conference program/schedule page
    pub archive_program_url: Option<String>,
    pub modifier: String,
}
