-- Sprint 3-4 Cleanup: Retire failing strategies
-- Run: sudo -u postgres psql alphacent -f retire_failing_strategies.sql
-- 
-- DEMO strategies: set pending_retirement in metadata (positions run to SL/TP naturally)
-- BACKTESTED strategies: direct RETIRED (no open positions)

BEGIN;

-- ── 1. DEMO losing strategies → pending_retirement ───────────────────────────
-- These have open positions. We mark pending_retirement so the monitoring service
-- stops generating new signals but existing positions run to their SL/TP.

UPDATE strategies
SET strategy_metadata = (strategy_metadata::jsonb || jsonb_build_object(
    'pending_retirement', true,
    'pending_retirement_reason', 'Retired: insufficient backtest trades + negative live P&L',
    'pending_retirement_at', now()::text
))::json
WHERE status = 'DEMO'
AND name IN (
    'RSI Dip Buy Multi RSI(35/55) V99',
    'RSI Dip Buy XLE LONG RSI(35/55)',
    'EMA Pullback Momentum Multi MA(10/30) V168',
    '4H Stochastic Swing Long Multi V113',
    'Dual MA Volume Surge Multi MA(20/50) V17',
    '4H ADX Trend Swing TXN LONG',
    'ATR Dynamic Trend Follow NSDQ100 LONG',
    '4H BB Squeeze Swing Long Multi V35',
    'SMA Envelope Reversion Long Multi V135',
    '4H VWAP Trend Continuation BAC LONG',
    'Stochastic Midrange Long Multi V96',
    '4H EMA Ribbon Trend Long Multi V169',
    'SMA Trend Momentum Multi V36',
    'Stochastic Overbought Short Ranging Multi V140',
    'BB Middle Band Bounce Multi BB(20,2.0) V187',
    'BB Midband Reversion Tight Multi BB(30,2.5) V124',
    '4H EMA Ribbon Trend Long Multi V119',
    '4H EMA Rejection Short Multi V161',
    'Dual MA Volume Surge Multi MA(20/50) V105',
    '4H EMA Ribbon Trend Long Multi V57',
    'SMA Proximity Entry Multi V284',
    'BB Middle Band Bounce Multi BB(20,2.0) V25',
    'BB Middle Band Bounce Multi BB(20,2.0) V20',
    '4H EMA Ribbon Trend Long HII LONG',
    '4H VWAP Trend Continuation SPX500 LONG',
    'SMA Envelope Reversion Long Multi V164',
    'SMA Envelope Reversion Long Multi V107',
    '4H EMA Ribbon Trend Long Multi V155',
    'BB Middle Band Bounce Multi BB(20,2.0) V108',
    'SMA Proximity Entry Multi V51',
    'SMA Proximity Entry Multi V129',
    'SMA Envelope Reversion Short Multi V141',
    '4H MACD Trend Continuation Multi V173'
);

-- Handle the two SMA Envelope Reversion Long V51 duplicates (same name, different strategies)
-- and SMA Envelope Reversion Long V51 (stock, 2 versions)
UPDATE strategies
SET strategy_metadata = (strategy_metadata::jsonb || jsonb_build_object(
    'pending_retirement', true,
    'pending_retirement_reason', 'Retired: insufficient backtest trades + negative live P&L',
    'pending_retirement_at', now()::text
))::json
WHERE status = 'DEMO'
AND name = 'SMA Envelope Reversion Long Multi V51'
AND (strategy_metadata->'customized_parameters'->>'stop_loss_pct')::float = 0.015;

-- ── 2. BACKTESTED failing → RETIRED directly ─────────────────────────────────
-- No open positions. Direct retirement.

UPDATE strategies
SET 
    status = 'RETIRED',
    retired_at = now()
WHERE status = 'BACKTESTED'
AND (
    -- Too few trades (< 8 for 4h/1d/forex/index/stock/etf, < 6 for commodity, < 8 for crypto)
    COALESCE(
        (backtest_results->>'total_trades')::int,
        (backtest_results->>'total_trades_in_backtest')::int
    ) < CASE
        WHEN (strategy_metadata->>'asset_class') = 'crypto' THEN 8
        WHEN (strategy_metadata->>'interval') = '1h' THEN 20
        WHEN (strategy_metadata->>'interval') = '4h' THEN 8
        WHEN (strategy_metadata->>'asset_class') = 'commodity' THEN 6
        ELSE 8
    END
    OR
    -- Crypto with SL < 8% (structurally broken)
    (
        (strategy_metadata->>'asset_class') = 'crypto'
        AND (strategy_metadata->'customized_parameters'->>'stop_loss_pct')::numeric < 0.08
    )
);

COMMIT;

-- Verify
SELECT status, COUNT(*) FROM strategies GROUP BY status ORDER BY status;
