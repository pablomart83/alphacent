-- P0-3 (Jun 2026 forensic audit): DB-level invariant — at most one OPEN
-- position per (strategy_id, symbol, account_type).
--
-- Until now this was enforced only in code. The guard had already failed in
-- practice (PLATINUM demo had two open rows under the same strategy on
-- 2026-06-10), and it is the same class of failure that produced the PANW
-- live triple-position. A partial unique index is the only defense that
-- survives session poisoning (InFailedSqlTransaction) and cross-thread races
-- between the trading cycle and the monitoring sync.
--
-- PREREQUISITE: there must be zero existing violations. Resolve any duplicate
-- OPEN positions first (close the surplus via pending_closure so eToro and DB
-- stay consistent). Verify with:
--   SELECT strategy_id, symbol, account_type, count(*)
--   FROM positions WHERE closed_at IS NULL
--   GROUP BY 1,2,3 HAVING count(*) > 1;
-- This must return zero rows before creating the index.

CREATE UNIQUE INDEX IF NOT EXISTS uq_open_pos_strategy_symbol_acct
    ON positions (strategy_id, symbol, account_type)
    WHERE closed_at IS NULL;
