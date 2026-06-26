use serde::Serialize;
use utoipa::ToSchema;

/// One row of the per-conference statistics time series (one entry per
/// venue/year). Combines the computed counts from the `conference_stats`
/// materialized view with the announced participant figure from the
/// `conference_business_meetings` table. Drives the trend charts on the
/// conferences overview page and is exposed publicly so others can build
/// their own graphs.
#[derive(Debug, Serialize, sqlx::FromRow, ToSchema)]
pub struct ConferenceStat {
    /// Conference series: "QIP", "QCRYPT", or "TQC".
    pub venue: String,
    pub year: i32,
    /// Accepted talks/papers (every contribution that is not a poster).
    pub talk_count: i64,
    /// Accepted posters, counted separately from talks.
    pub poster_count: i64,
    /// Talk submissions announced at the business meeting, when known.
    pub submission_count: Option<i32>,
    /// Talks accepted as announced at the business meeting, when known.
    pub acceptance_count: Option<i32>,
    /// Acceptance rate in percent: the announced rate when given, otherwise
    /// computed from accepted/submitted talks (null when neither is available).
    pub acceptance_rate: Option<f64>,
    /// Registered participants announced at the business meeting (sparse).
    pub registered_participants: Option<i32>,
}
