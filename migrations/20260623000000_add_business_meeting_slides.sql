-- Add a `slides` column to conference_business_meetings: an ordered array of
-- {label, url} links to the business-meeting slide decks (typically a PC-chair
-- report and a local-organizers report, sometimes award/opening/closing decks).

ALTER TABLE conference_business_meetings
ADD COLUMN slides JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN conference_business_meetings.slides IS
    'Ordered array of {label, url} links to business-meeting slide decks (e.g. PC chair report, local organizers report).';
