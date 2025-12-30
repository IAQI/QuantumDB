-- Create committee types and committee_roles table

-- Committee types
CREATE TYPE committee_type AS ENUM (
    'OC',               -- Organizing Committee (General Chair, etc.)
    'PC',               -- Program Committee
    'SC',               -- Steering Committee
    'Local'             -- Local Organizers
);

-- Position/role within committee
CREATE TYPE committee_position AS ENUM (
    'chair',            -- Chair (General Chair, PC Chair, etc.)
    'co_chair',         -- Co-Chair
    'area_chair',       -- Area Chair (for large PCs)
    'member'            -- Regular member
);

CREATE TABLE committee_roles (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conference_id       UUID NOT NULL REFERENCES conferences(id),
    author_id           UUID NOT NULL REFERENCES authors(id),

    committee           committee_type NOT NULL,
    position            committee_position NOT NULL DEFAULT 'member',
    role_title          TEXT,                 -- Custom title (e.g., "Publicity Chair", "Web Chair")

    -- For steering committee or multi-year roles
    term_start          DATE,
    term_end            DATE,

    -- Audit fields
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creator             TEXT NOT NULL,
    modifier            TEXT NOT NULL,
    metadata            JSONB DEFAULT '{}'::jsonb,

    -- A person can have multiple roles at same conference (e.g., OC chair + PC member)
    -- but not the same exact role twice
    UNIQUE (conference_id, author_id, committee, position)
);

-- Indexes for common queries
CREATE INDEX idx_committee_roles_conference ON committee_roles(conference_id);
CREATE INDEX idx_committee_roles_author ON committee_roles(author_id);
CREATE INDEX idx_committee_roles_committee ON committee_roles(committee, position);

COMMENT ON TABLE committee_roles IS 'Committee membership and roles for conferences';
COMMENT ON COLUMN committee_roles.role_title IS 'Custom title like "Publicity Chair" or "Local Arrangements"';
COMMENT ON COLUMN committee_roles.term_start IS 'For multi-year roles like Steering Committee';
