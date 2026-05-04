SELECT
  CASE
    WHEN (tj.trade_metadata->>'conviction_score')::float < 60 THEN '1:<60'
    WHEN (tj.trade_metadata->>'conviction_score')::float < 65 THEN '2:60-65'
    WHEN (tj.trade_metadata->>'conviction_score')::float < 70 THEN '3:65-70'
    WHEN (tj.trade_metadata->>'conviction_score')::float < 75 THEN '4:70-75'
    ELSE '5:>=75'
  END AS bucket,
  COUNT(*) AS n,
  ROUND(AVG(pnl)::numeric, 2) AS avg_pnl,
  ROUND((100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0))::numeric, 1) AS wr,
  ROUND(SUM(pnl)::numeric, 2) AS total_pnl
FROM trade_journal tj
WHERE pnl IS NOT NULL
  AND (tj.trade_metadata->>'conviction_score') IS NOT NULL
GROUP BY bucket
ORDER BY bucket;
