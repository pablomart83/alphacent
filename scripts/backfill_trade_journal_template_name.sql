-- Backfill trade_journal.trade_metadata['template_name'] from strategies table.
--
-- Context: the loser-pair sizing penalty in risk_manager.calculate_position_size
-- (Step 10b) queries trade_journal.trade_metadata->>'template_name' to identify
-- (template, symbol) pairs with net-losing history. Before 2026-05-05 the write
-- path never populated template_name, so zero of 892 closed trades had the key
-- and the penalty never fired. The write path is now fixed; this query recovers
-- what it can for historical rows.
--
-- Every backfilled row gets:
--   trade_metadata.template_name         = recovered template identifier
--   trade_metadata.backfill_source       = 'legacy_backfill_2026_05_05'
--   trade_metadata.backfill_template_src = 'strategies' | 'strategy_proposals'
--
-- Usage:
--   sudo -u postgres psql alphacent -f scripts/backfill_trade_journal_template_name.sql
--
-- This is a single atomic transaction. If anything goes wrong it rolls back.

BEGIN;

-- Preview scope before changing anything.
SELECT
  COUNT(*)                                                                   AS closed_total,
  COUNT(*) FILTER (WHERE (t.trade_metadata::jsonb) ? 'template_name')        AS has_template,
  COUNT(*) FILTER (WHERE NOT COALESCE((t.trade_metadata::jsonb) ? 'template_name', false)
                     AND s.id IS NOT NULL
                     AND COALESCE((s.strategy_metadata::jsonb) ? 'template_name', false)
                  )                                                          AS recoverable_strategies,
  COUNT(*) FILTER (WHERE NOT COALESCE((t.trade_metadata::jsonb) ? 'template_name', false)
                     AND s.id IS NULL
                  )                                                          AS retired_strategy
FROM trade_journal t
LEFT JOIN strategies s ON s.id = t.strategy_id
WHERE t.pnl IS NOT NULL;

-- Source 1: strategies.strategy_metadata->>'template_name'
-- Uses COALESCE so rows with NULL trade_metadata get a fresh object.
UPDATE trade_journal t
SET trade_metadata = (
  COALESCE(t.trade_metadata::jsonb, '{}'::jsonb)
  || jsonb_build_object(
       'template_name',         COALESCE(s.strategy_metadata::jsonb ->> 'template_name', s.name),
       'backfill_source',       'legacy_backfill_2026_05_05',
       'backfill_template_src', 'strategies'
     )
)::json
FROM strategies s
WHERE s.id = t.strategy_id
  AND t.pnl IS NOT NULL
  AND NOT COALESCE((t.trade_metadata::jsonb) ? 'template_name', false)
  AND (
    COALESCE(s.strategy_metadata::jsonb ->> 'template_name', '') <> ''
    OR COALESCE(s.name, '') <> ''
  );

-- Source 2: strategy_proposals fallback for rows whose strategy was retired.
-- Picks the most recent proposal row per strategy_id that carries a template_name.
WITH props AS (
  SELECT DISTINCT ON (strategy_id) strategy_id, template_name
  FROM strategy_proposals
  WHERE template_name IS NOT NULL AND template_name <> ''
  ORDER BY strategy_id, proposed_at DESC
)
UPDATE trade_journal t
SET trade_metadata = (
  COALESCE(t.trade_metadata::jsonb, '{}'::jsonb)
  || jsonb_build_object(
       'template_name',         p.template_name,
       'backfill_source',       'legacy_backfill_2026_05_05',
       'backfill_template_src', 'strategy_proposals'
     )
)::json
FROM props p
WHERE p.strategy_id = t.strategy_id
  AND t.pnl IS NOT NULL
  AND NOT COALESCE((t.trade_metadata::jsonb) ? 'template_name', false);

-- Post-state report
SELECT
  COUNT(*)                                                                   AS closed_total,
  COUNT(*) FILTER (WHERE (t.trade_metadata::jsonb) ? 'template_name')        AS has_template,
  COUNT(*) FILTER (WHERE NOT COALESCE((t.trade_metadata::jsonb) ? 'template_name', false)) AS still_missing
FROM trade_journal t
WHERE t.pnl IS NOT NULL;

-- Show source distribution among backfilled rows
SELECT t.trade_metadata::jsonb ->> 'backfill_template_src' AS source, COUNT(*) AS rows
FROM trade_journal t
WHERE t.pnl IS NOT NULL
  AND t.trade_metadata::jsonb ->> 'backfill_source' = 'legacy_backfill_2026_05_05'
GROUP BY source
ORDER BY rows DESC;

COMMIT;
