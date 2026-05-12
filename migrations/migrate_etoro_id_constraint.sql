-- Migration: replace global unique constraint on etoro_position_id with
-- a composite unique constraint on (etoro_position_id, account_type).
--
-- Root cause: eToro reuses numeric position IDs across demo and live accounts.
-- The old global constraint prevented a live position from being created when
-- a closed (or open) demo position held the same etoro_position_id.
--
-- Safe to run while service is running — only DDL, no data changes.

BEGIN;

-- 1. Drop the old global unique constraint
ALTER TABLE positions DROP CONSTRAINT IF EXISTS positions_etoro_position_id_key;

-- 2. Add the composite unique constraint (etoro_position_id, account_type)
--    This allows the same numeric ID to exist in both demo and live rows,
--    but prevents duplicates within the same account.
ALTER TABLE positions
    ADD CONSTRAINT uq_positions_etoro_id_account
    UNIQUE (etoro_position_id, account_type);

COMMIT;
