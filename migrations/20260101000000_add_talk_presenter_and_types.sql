-- Migration: Add talk presenter tracking and enhanced talk types
-- Created: 2026-01-01

-- Step 1: Remove 'short' from paper_type enum
-- Since no existing data uses 'short', we can safely remove it
-- PostgreSQL requires creating a new enum and converting the column

-- First check that no data uses 'short' (should return 0)
DO $$
DECLARE
    short_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO short_count FROM publications WHERE paper_type = 'short';
    IF short_count > 0 THEN
        RAISE EXCEPTION 'Cannot remove ''short'' paper_type - % publications still use it', short_count;
    END IF;
END $$;

-- Create new enum without 'short', with new plenary types
CREATE TYPE paper_type_new AS ENUM (
    'regular',          -- Full paper / contributed talk
    'poster',           -- Poster presentation
    'invited',          -- Invited talk
    'tutorial',         -- Tutorial
    'keynote',          -- Keynote address
    'plenary',          -- Plenary talk (modern parallel-track conferences)
    'plenary_short',    -- Short plenary (e.g., at QIP)
    'plenary_long'      -- Long plenary (e.g., at QIP)
);

-- Drop materialized views that reference paper_type column
DROP MATERIALIZED VIEW IF EXISTS conference_stats;

-- Convert column to new enum type
-- First remove the default, then alter the type, then add the default back
ALTER TABLE publications 
    ALTER COLUMN paper_type DROP DEFAULT;

ALTER TABLE publications 
    ALTER COLUMN paper_type TYPE paper_type_new 
    USING paper_type::text::paper_type_new;

ALTER TABLE publications 
    ALTER COLUMN paper_type SET DEFAULT 'regular'::paper_type_new;

-- Drop old enum and rename new one
DROP TYPE paper_type;
ALTER TYPE paper_type_new RENAME TO paper_type;

-- Recreate the materialized view with updated reference
CREATE MATERIALIZED VIEW conference_stats AS
SELECT
    c.id,
    c.venue,
    c.year,
    COUNT(DISTINCT p.id) as publication_count,
    COUNT(DISTINCT CASE WHEN p.paper_type = 'regular' THEN p.id END) as regular_paper_count,
    COUNT(DISTINCT CASE WHEN p.paper_type = 'invited' THEN p.id END) as invited_talk_count,
    COUNT(DISTINCT CASE WHEN p.award IS NOT NULL THEN p.id END) as award_count,
    COUNT(DISTINCT cr.id) as committee_member_count,
    COUNT(DISTINCT a.id) as unique_author_count,
    c.submission_count,
    c.acceptance_count,
    CASE
        WHEN c.submission_count > 0 AND c.acceptance_count IS NOT NULL
        THEN ROUND((c.acceptance_count::numeric / c.submission_count::numeric) * 100, 1)
        ELSE NULL
    END as acceptance_rate
FROM conferences c
LEFT JOIN publications p ON c.id = p.conference_id
LEFT JOIN committee_roles cr ON c.id = cr.conference_id
LEFT JOIN authorships au ON p.id = au.publication_id
LEFT JOIN authors a ON au.author_id = a.id
GROUP BY c.id, c.venue, c.year, c.submission_count, c.acceptance_count;

CREATE UNIQUE INDEX idx_conference_stats_id ON conference_stats(id);

-- Step 2: Add presenter_author_id to publications table
-- This is a nullable FK to authors - represents who gave the talk
-- Must be one of the authors in authorships table (enforced by trigger)
-- ON DELETE SET NULL ensures data integrity if author is deleted

ALTER TABLE publications
ADD COLUMN presenter_author_id UUID REFERENCES authors(id) ON DELETE SET NULL;

-- Step 3: Add is_proceedings_track boolean
-- Default FALSE for backward compatibility (QIP/QCrypt are workshop-style)
-- TQC has both proceedings and workshop tracks
-- Affects citation format and archival status

ALTER TABLE publications
ADD COLUMN is_proceedings_track BOOLEAN NOT NULL DEFAULT FALSE;

-- Step 4: Add talk scheduling fields
-- All fields are nullable - populate when data is available from conference programs

ALTER TABLE publications
ADD COLUMN talk_date DATE,
ADD COLUMN talk_time TIME,
ADD COLUMN duration_minutes INTEGER CHECK (duration_minutes >= 0);

-- Step 5: Create index on presenter for efficient queries
-- Partial index (WHERE NOT NULL) saves storage and improves performance

CREATE INDEX idx_publications_presenter ON publications(presenter_author_id)
WHERE presenter_author_id IS NOT NULL;

-- Step 6: Update column comments for documentation

COMMENT ON COLUMN publications.presenter_author_id IS
'Author who presented the talk (must be one of the publication authors). Often unknown for contributed talks. For rare cases where presenter is not an author, store presenter info in metadata field and leave this NULL.';

COMMENT ON COLUMN publications.is_proceedings_track IS
'Whether this publication is in the formal proceedings track (vs workshop track). TQC has both proceedings and workshop tracks; QIP/QCrypt are workshop-style only.';

COMMENT ON COLUMN publications.talk_date IS
'Date when the talk was given (if known). Useful for conferences with multi-day programs.';

COMMENT ON COLUMN publications.talk_time IS
'Time when the talk started (if known). Useful for detailed schedule tracking.';

COMMENT ON COLUMN publications.duration_minutes IS
'Duration of the talk in minutes (if known). Replaces the need for a ''short'' paper type.';

COMMENT ON TYPE paper_type IS
'Publication/talk type as it appears in conference programs: regular (contributed), poster, invited, tutorial, keynote, plenary (contributed plenary), plenary_short (short plenary at QIP), plenary_long (long plenary at QIP). The ''short'' type was removed in favor of duration_minutes field. Types represent program listings, not selection mechanism.';

-- Step 7: Create validation function and trigger
-- Ensures presenter_author_id references one of the publication's authors
-- Allows NULL (unknown presenter) but prevents invalid author references

CREATE OR REPLACE FUNCTION validate_presenter_is_author()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.presenter_author_id IS NOT NULL THEN
        -- Check that presenter is actually an author of this publication
        IF NOT EXISTS (
            SELECT 1 FROM authorships
            WHERE publication_id = NEW.id
            AND author_id = NEW.presenter_author_id
        ) THEN
            RAISE EXCEPTION 'presenter_author_id must be one of the publication authors (check authorships table)';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ensure_presenter_is_author
    BEFORE INSERT OR UPDATE ON publications
    FOR EACH ROW
    EXECUTE FUNCTION validate_presenter_is_author();

-- Migration notes:
-- - 'short' paper_type removed from enum (no existing data uses it)
-- - Existing publications will have presenter_author_id = NULL (acceptable - often unknown)
-- - Existing publications will have is_proceedings_track = FALSE (correct for QIP/QCrypt)
-- - Existing publications will have talk scheduling fields = NULL (acceptable - often unknown)
-- - Existing paper_type values remain valid (enum modified to add plenary types)
-- - No data migration required
