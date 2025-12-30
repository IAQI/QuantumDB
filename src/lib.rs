pub mod models;
pub mod handlers;
pub mod utils;

// Re-export commonly used items (avoiding ambiguous re-exports)
pub use models::{
    Author, CreateAuthor, UpdateAuthor,
    Authorship, CreateAuthorship, UpdateAuthorship,
    CommitteeRole, CommitteeType, CommitteePosition, CreateCommitteeRole, UpdateCommitteeRole,
    Conference, CreateConference, UpdateConference,
    Publication, PaperType, CreatePublication, UpdatePublication,
    normalize_name,
};
pub use handlers::*;
pub use utils::{
    parse_conference_slug, make_conference_slug,
    normalize_name_loose, name_similarity, split_name, extract_initials, generate_name_variants,
};
