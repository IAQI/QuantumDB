-- This migration file has been moved to seeds/z_insert_2024_committee_data.sql
-- Committee data should be inserted after conference seed data, not during migrations

-- Migration kept for version tracking but contents moved to seed file
-- See: seeds/z_insert_2024_committee_data.sql

-- The migration was failing because it tried to insert committee roles
-- for conferences that don't exist until seeds run. The init script runs
-- migrations first, then seeds. Committee data depends on conference records,
-- so it must run as a seed file after conference seeds.

SELECT 'Committee data moved to seeds/z_insert_2024_committee_data.sql' as migration_note;
