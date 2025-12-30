-- Add affiliation and metadata fields for source tracking and point-in-time affiliation tracking
-- Migration: 20251230100000_add_affiliation_and_metadata.sql

-- Add affiliation field to committee_roles for point-in-time affiliation tracking
ALTER TABLE committee_roles
ADD COLUMN affiliation TEXT;

-- Add metadata field to committee_roles for source tracking (already exists for extensibility)
-- committee_roles.metadata already exists, so this is a no-op
-- Just verify it exists in the comment below

-- Add metadata field to authorships for source tracking
ALTER TABLE authorships
ADD COLUMN metadata JSONB DEFAULT '{}'::jsonb NOT NULL;

-- Add GIN index on authorships.metadata for efficient JSONB queries
CREATE INDEX idx_authorships_metadata ON authorships USING GIN (metadata);

-- Add GIN index on committee_roles.metadata for efficient JSONB queries
-- (metadata field should already exist from 20251228160005_create_committee_roles_table.sql)
CREATE INDEX IF NOT EXISTS idx_committee_roles_metadata ON committee_roles USING GIN (metadata);
