-- A2 (staleness unification) — add positions.price_updated_at
--
-- Single source of truth for "how fresh is this position's current_price".
-- Set by order_monitor.sync_positions whenever current_price is refreshed from
-- eToro. Breach enforcement uses it so stops act on fresh prices; FIX-09 / D1-D2
-- staleness predicates should standardise on it next.
--
-- Additive, nullable column — safe online migration, no rewrite of existing rows.
-- Existing rows are backfilled to opened_at as a conservative "unknown but not
-- newer than this" floor; the next position sync overwrites with the real value.

ALTER TABLE positions ADD COLUMN IF NOT EXISTS price_updated_at TIMESTAMP;

UPDATE positions
SET price_updated_at = COALESCE(price_updated_at, opened_at)
WHERE price_updated_at IS NULL;
