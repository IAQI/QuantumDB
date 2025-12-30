-- Document source tracking patterns and affiliation tracking
-- Migration: 20251230100001_add_source_tracking_comments.sql

-- Document committee_roles.affiliation usage
COMMENT ON COLUMN committee_roles.affiliation IS 
'Point-in-time affiliation of the author at the time of their committee service. This captures the institutional affiliation shown on the conference website/program. The authors.affiliation field should be updated to reflect the most recent affiliation across all committee roles and authorships.';

-- Document committee_roles.metadata usage for source tracking
COMMENT ON COLUMN committee_roles.metadata IS 
'Source tracking and additional metadata in JSONB format. Supports two-tier source tracking:
1. Primary: Uses conference-level archive URLs (archive_pc_url, archive_organizers_url, archive_steering_url, archive_url) as default sources
2. Override: Store record-specific details when source differs from conference default or needs clarification

Schema pattern:
{
  "source_type": "archive|proceedings|hotcrp|manual",
  "source_url": "optional-override-url",
  "source_description": "human-readable note",
  "source_date": "YYYY-MM-DD"
}

Example: {"source_type": "archive", "source_url": "https://qip.iaqi.org/2024/pc.html#area-chairs", "source_description": "Listed in Area Chairs section"}
If empty {}, the source is assumed to be the appropriate conference archive URL based on committee type.';

-- Document authorships.affiliation usage (already exists)
COMMENT ON COLUMN authorships.affiliation IS 
'Point-in-time affiliation of the author at the time of publication. This captures the institutional affiliation shown in the publication itself. The authors.affiliation field should be updated to reflect the most recent affiliation across all committee roles and authorships.';

-- Document authorships.metadata usage for source tracking
COMMENT ON COLUMN authorships.metadata IS 
'Source tracking and additional metadata in JSONB format. Supports two-tier source tracking:
1. Primary: Uses conference archive_program_url as default source for authorships
2. Override: Store record-specific details when source differs from conference default or needs clarification

Schema pattern:
{
  "source_type": "archive|proceedings|hotcrp|manual",
  "source_url": "optional-override-url",
  "source_description": "human-readable note",
  "source_date": "YYYY-MM-DD"
}

Example: {"source_type": "hotcrp", "source_url": "hotcrp-qip2024.json", "source_description": "Imported from HotCRP export"}
If empty {}, the source is assumed to be the conference archive_program_url.';

-- Document archive URL usage patterns
COMMENT ON COLUMN conferences.archive_pc_url IS 
'URL to archived program committee page. Serves as default source for committee_roles with committee=''PC'' when metadata.source_url is not specified.';

COMMENT ON COLUMN conferences.archive_organizers_url IS 
'URL to archived local organizers page. Serves as default source for committee_roles with committee=''Local'' when metadata.source_url is not specified.';

COMMENT ON COLUMN conferences.archive_steering_url IS 
'URL to archived steering committee page. Serves as default source for committee_roles with committee=''SC'' when metadata.source_url is not specified.';

COMMENT ON COLUMN conferences.archive_url IS 
'URL to archived main conference website. Serves as default source for committee_roles with committee=''OC'' and general conference information when metadata.source_url is not specified.';

COMMENT ON COLUMN conferences.archive_program_url IS 
'URL to archived conference program. Serves as default source for authorships (publications) when metadata.source_url is not specified.';
