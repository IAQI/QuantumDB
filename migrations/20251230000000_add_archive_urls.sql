-- Add archive URL fields for static backups of conference websites
-- Archive sites: qip.iaqi.org, tqc.iaqi.org, qcrypt.iaqi.org

-- Root URL for the archived conference website
ALTER TABLE conferences ADD COLUMN archive_url TEXT;

-- Specific page URLs within the archive
ALTER TABLE conferences ADD COLUMN archive_organizers_url TEXT;  -- Local organizing committee
ALTER TABLE conferences ADD COLUMN archive_pc_url TEXT;          -- Program committee (chairs + members)
ALTER TABLE conferences ADD COLUMN archive_steering_url TEXT;    -- Steering committee
ALTER TABLE conferences ADD COLUMN archive_program_url TEXT;     -- Conference program/schedule

COMMENT ON COLUMN conferences.website_url IS 'Original conference website URL (may become unavailable)';
COMMENT ON COLUMN conferences.archive_url IS 'Static archive root URL (e.g., https://qip.iaqi.org/2024/)';
COMMENT ON COLUMN conferences.archive_organizers_url IS 'Archive URL for local organizing committee page';
COMMENT ON COLUMN conferences.archive_pc_url IS 'Archive URL for program committee page';
COMMENT ON COLUMN conferences.archive_steering_url IS 'Archive URL for steering committee page';
COMMENT ON COLUMN conferences.archive_program_url IS 'Archive URL for conference program/schedule page';
