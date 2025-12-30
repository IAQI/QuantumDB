-- Insert committee data for 2024 conferences
-- Data sourced from conference websites

-- First, insert all authors (skip if already exists using ON CONFLICT)

-- ============================================================================
-- QIP 2024 Local Organizing Committee (Taiwan)
-- ============================================================================

-- Get QIP 2024 conference ID
DO $$
DECLARE
    qip2024_id UUID;
    qcrypt2024_id UUID;
    tqc2024_id UUID;
    author_id UUID;
BEGIN
    -- Get conference IDs
    SELECT id INTO qip2024_id FROM conferences WHERE venue = 'QIP' AND year = 2024;
    SELECT id INTO qcrypt2024_id FROM conferences WHERE venue = 'QCRYPT' AND year = 2024;
    SELECT id INTO tqc2024_id FROM conferences WHERE venue = 'TQC' AND year = 2024;

    -- ========================================================================
    -- QIP 2024 LOCAL ORGANIZING COMMITTEE
    -- ========================================================================

    -- Min-Hsiu Hsieh (Chair)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Min-Hsiu Hsieh', 'Hsieh', 'Min-Hsiu', 'min-hsiu hsieh', 'Hon-Hai Quantum Computing Center', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'min-hsiu hsieh' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, role_title, creator, modifier)
    VALUES (qip2024_id, author_id, 'Local', 'chair', 'Chair', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Hao-Chung Cheng (Co-Chair)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Hao-Chung Cheng', 'Cheng', 'Hao-Chung', 'hao-chung cheng', 'National Taiwan University', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'hao-chung cheng' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, role_title, creator, modifier)
    VALUES (qip2024_id, author_id, 'Local', 'co_chair', 'Co-Chair', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Ching-Ray Chang (Member)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Ching-Ray Chang', 'Chang', 'Ching-Ray', 'ching-ray chang', 'Chung Yuan Christian University', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'ching-ray chang' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qip2024_id, author_id, 'Local', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Hsi-Sheng Goan (Member)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Hsi-Sheng Goan', 'Goan', 'Hsi-Sheng', 'hsi-sheng goan', 'National Taiwan University', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'hsi-sheng goan' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qip2024_id, author_id, 'Local', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Kai-Min Chung (Member)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Kai-Min Chung', 'Chung', 'Kai-Min', 'kai-min chung', 'Academia Sinica', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'kai-min chung' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qip2024_id, author_id, 'Local', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Yeong-Cherng Liang (Member)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Yeong-Cherng Liang', 'Liang', 'Yeong-Cherng', 'yeong-cherng liang', 'National Cheng Kung University', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'yeong-cherng liang' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qip2024_id, author_id, 'Local', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Kuei-Lin Chiu (Member)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Kuei-Lin Chiu', 'Chiu', 'Kuei-Lin', 'kuei-lin chiu', 'National Sun Yat-sen University', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'kuei-lin chiu' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qip2024_id, author_id, 'Local', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Ching-Yi Lai (Member)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Ching-Yi Lai', 'Lai', 'Ching-Yi', 'ching-yi lai', 'National Yang Ming Chiao Tung University', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'ching-yi lai' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qip2024_id, author_id, 'Local', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Han-Hsuan Lin (Member)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Han-Hsuan Lin', 'Lin', 'Han-Hsuan', 'han-hsuan lin', 'National Tsing Hua University', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'han-hsuan lin' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qip2024_id, author_id, 'Local', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- ========================================================================
    -- QCRYPT 2024 ORGANIZING COMMITTEE (Vigo, Spain)
    -- ========================================================================

    -- Marcos Curty (General Chair)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Marcos Curty', 'Curty', 'Marcos', 'marcos curty', 'University of Vigo', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'marcos curty' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, role_title, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'OC', 'chair', 'General Chair', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Natalia Costas (Support)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Natalia Costas', 'Costas', 'Natalia', 'natalia costas', 'CESGA Galicia Supercomputing Center', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'natalia costas' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'OC', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Antía Lamas-Linares (Support)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Antía Lamas-Linares', 'Lamas-Linares', 'Antía', 'antia lamas-linares', 'University of Vigo / Amazon Web Services', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'antia lamas-linares' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'OC', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Vadim Makarov (Support)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Vadim Makarov', 'Makarov', 'Vadim', 'vadim makarov', 'University of Vigo', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'vadim makarov' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'OC', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Davide Rusca (Support + SC Member)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Davide Rusca', 'Rusca', 'Davide', 'davide rusca', 'University of Vigo', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'davide rusca' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'OC', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'SC', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Hugo Zbinden (Support)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Hugo Zbinden', 'Zbinden', 'Hugo', 'hugo zbinden', 'University of Vigo', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'hugo zbinden' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'OC', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- ========================================================================
    -- QCRYPT 2024 STEERING COMMITTEE
    -- ========================================================================

    -- Li Qian (SC Chair)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Li Qian', 'Qian', 'Li', 'li qian', 'University of Toronto', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'li qian' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, role_title, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'SC', 'chair', 'SC Chair', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Kai-Min Chung (SC Co-Chair) - already inserted above
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'kai-min chung' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, role_title, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'SC', 'co_chair', 'SC Co-Chair', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Gorjan Alagic (SC Member)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Gorjan Alagic', 'Alagic', 'Gorjan', 'gorjan alagic', 'University of Maryland', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'gorjan alagic' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'SC', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Rotem Arnon-Friedman (SC Member)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Rotem Arnon-Friedman', 'Arnon-Friedman', 'Rotem', 'rotem arnon-friedman', 'Weizmann Institute of Science', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'rotem arnon-friedman' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'SC', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Charles Lim (SC Member)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Charles Lim', 'Lim', 'Charles', 'charles lim', 'JPMorgan Chase & Co', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'charles lim' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'SC', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Marco Lucamarini (SC Member)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Marco Lucamarini', 'Lucamarini', 'Marco', 'marco lucamarini', 'University of York', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'marco lucamarini' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'SC', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Feihu Xu (SC Member)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Feihu Xu', 'Xu', 'Feihu', 'feihu xu', 'University of Science and Technology of China', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'feihu xu' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'SC', 'member', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- ========================================================================
    -- QCRYPT 2024 PROGRAM COMMITTEE
    -- ========================================================================

    -- Anne Broadbent (PC Chair - Theory)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Anne Broadbent', 'Broadbent', 'Anne', 'anne broadbent', 'University of Ottawa', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'anne broadbent' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, role_title, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'PC', 'chair', 'PC Chair (Theory)', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- Bing Qi (PC Co-Chair - Experiment)
    INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
    VALUES ('Bing Qi', 'Qi', 'Bing', 'bing qi', 'New York University Shanghai', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;
    SELECT id INTO author_id FROM authors WHERE normalized_name = 'bing qi' LIMIT 1;
    INSERT INTO committee_roles (conference_id, author_id, committee, position, role_title, creator, modifier)
    VALUES (qcrypt2024_id, author_id, 'PC', 'co_chair', 'PC Co-Chair (Experiment)', 'data_import', 'data_import')
    ON CONFLICT DO NOTHING;

    -- ========================================================================
    -- TQC 2024 (Okinawa, Japan) - Note: Limited data available
    -- ========================================================================
    -- We have TQC 2025 data but need TQC 2024 data separately
    -- Adding placeholder note: TQC 2024 was held in Okinawa, Japan

END $$;

-- Verification queries
SELECT 'Authors inserted:' as info, COUNT(*) as count FROM authors WHERE creator = 'data_import';
SELECT 'Committee roles inserted:' as info, COUNT(*) as count FROM committee_roles WHERE creator = 'data_import';
