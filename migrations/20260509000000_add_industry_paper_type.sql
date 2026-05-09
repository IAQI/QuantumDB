-- Add 'industry' to paper_type enum
--
-- Motivation: QIP 2019 included a sponsored "Industry session" with short
-- talks from Alibaba, Baidu, 1QBit, Google, IBM, Microsoft, and Rigetti
-- representatives. These don't fit the existing types: not peer-reviewed
-- (so not regular/plenary/poster), not academic invited speakers, not
-- tutorials. A dedicated 'industry' value preserves the distinction.
--
-- PostgreSQL 12+ allows ALTER TYPE ... ADD VALUE inside a transaction
-- block as long as the new value is not used in the same transaction.
-- This migration only adds the value; it does not insert any rows.

ALTER TYPE paper_type ADD VALUE IF NOT EXISTS 'industry';

COMMENT ON TYPE paper_type IS
'Publication/talk type as it appears in conference programs: regular (contributed), poster, invited, tutorial, keynote, plenary (contributed plenary), plenary_short (short plenary at QIP), plenary_long (long plenary at QIP), industry (sponsored industry-session talk). The ''short'' type was removed in favor of duration_minutes field. Types represent program listings, not selection mechanism.';
