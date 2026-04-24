SELECT 
  s.name,
  COUNT(p.id) AS open_pos,
  round(SUM(p.unrealized_pnl)::numeric, 2) AS unrealized,
  round(SUM(p.realized_pnl)::numeric, 2) AS realized,
  round((SUM(p.unrealized_pnl) + SUM(p.realized_pnl))::numeric, 2) AS total_pnl,
  s.strategy_metadata->>'health_score' AS health,
  s.strategy_metadata->>'decay_score' AS decay,
  COALESCE(
    (s.backtest_results->>'total_trades')::int,
    (s.backtest_results->>'total_trades_in_backtest')::int
  ) AS bt_trades
FROM strategies s
JOIN positions p ON p.strategy_id = s.id 
  AND p.closed_at IS NULL 
  AND p.pending_closure = false
WHERE s.status = 'DEMO'
GROUP BY s.id, s.name
ORDER BY total_pnl DESC;
