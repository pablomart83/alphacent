-- P2-4 (2026-06-11 audit): drop redundant duplicate indexes on `positions`.
--
-- The table carried two identical single-column indexes for each of strategy_id
-- and closed_at (SQLAlchemy-style `ix_*` plus migration-added `idx_*`). Duplicate
-- indexes add write overhead (every INSERT/UPDATE maintains both) for zero read
-- benefit. We keep the `ix_*` copies and the genuinely-distinct composite indexes
-- (idx_positions_account_closed, idx_positions_pending_closure).
--
-- CONCURRENTLY: no ACCESS EXCLUSIVE table lock, safe to run on the live DB during
-- market hours. Run each statement on its own (cannot run inside a transaction).

DROP INDEX CONCURRENTLY IF EXISTS idx_positions_strategy_id;
DROP INDEX CONCURRENTLY IF EXISTS idx_positions_closed_at;
