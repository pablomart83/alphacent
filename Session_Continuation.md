# AlphaCent — Session Continuation

> Permanent rules are in `.kiro/steering/trading-system-context.md`. This file holds current system state, recent fixes, and open items.

---

## Session Start Checklist

```bash
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'cat /home/ubuntu/alphacent/logs/errors.log | tail -30'
ssh ... 'tail -80 /home/ubuntu/alphacent/logs/cycles/cycle_history.log'
ssh ... 'sudo -u postgres psql alphacent -t -A -c "SELECT balance, equity, updated_at FROM account_info ORDER BY updated_at DESC LIMIT 1;"'
ssh ... 'sudo -u postgres psql alphacent -t -A -c "SELECT date, equity, market_quality_score, market_quality_grade FROM equity_snapshots WHERE snapshot_type='"'"'daily'"'"' ORDER BY date DESC LIMIT 7;"'
```

---

## Current System State (May 2, 2026, 08:15 UTC)

- **Equity:** ~$475K (unchanged from May 1)
- **Open positions:** 85-90 depending on cycle
- **Active strategies:** 63 DSL + 1 AE (64 total per latest activation stage)
- **Directional split:** ~79 LONG / ~6 SHORT
- **Market regime:** `STRONG UPTREND` (20d +10.83%, 50d +5.49%, ATR/price 1.08%)
- **VIX:** 16.89
- **Scheduled cycles:** daily 15:15 UTC + weekdays 19:00 UTC

**Verified healthy:** process 931078 (restart on SignalAction hotfix deploy). TSL cycles emitting `errors=0` consistently. No crashes in errors.log since yesterday's post-audit deploy.

---

## Sessions shipped 2026-05-01 and 2026-05-02

### Batch 1 / Quick-wins (May 1) — data-pipeline audit
Shipped 10:02-10:54 UTC. DST yfinance fix, stale-1d detection in full sync, 1d corruption fix in quick update, conviction threshold 70→65, ETF/Index tradability bump, min_sharpe 0.4→1.0, crypto symbol normalization, yfinance tz-aware UTC bounds, freshness SLA gate (with a hotfix for the `session_scope` AttributeError that briefly skipped TSL updates for ~30 min), interval-aware incremental-fetch gate, FRED retry, rejection/zero-trade blacklists, pool_pre_ping, errors.log rotation. See previous Session_Continuation history for details; all commits are pre-May-2.

### Strategy Library deploy (May 1 12:02 UTC, commit `4acfadb`)
R1-R7 template removals + C1 VIX gate + C2 momentum crash breaker + C3 PEAD tightening + Q1 AE rotation + Q2 AE cap 5→8. Verified in a cycle at 13:06 UTC that day.

### TSL audit + observability (May 1 evening → May 2 morning)

Multi-commit workstream. Summary by commit:

- `686bf42` — TSL audit fixes: timeframe-aware ATR (position_intervals dict), per-class ATR_MULTIPLIER_BY_ASSET_CLASS (stock/etf/commodity 2.0x, crypto/index 1.5x, forex 1.0x), breach detection decoupled from market-open and freshness filters, per-cycle INFO summary line, ATR floor logged at INFO, counter semantics fixed (updated_ids set), dead `except EToroAPIError` branches removed, log retention raised (main 20 backups, component 10).
- `a5068a9` — Symbols tab surfaces lifetime trade history from trade_journal; added `symbols` + `template_name` JSON columns to `strategy_proposals` so per-symbol Proposed counts survive retirement. UI columns: Proposed / Active (open positions) / Traded / Sharpe / Win% / P&L / Best Template.
- `c5f949a` — Systemic fixes from TSLA audit: OrderORM.order_metadata column so market_regime survives async fills; `monitoring_service._update_trade_excursions` populates MAE/MFE every 60s; trend-consistency gate on execute_signal (blocks SHORT into oversold bounces / LONG into downtrends); SHORT-side WF tightening; recency-weighted symbol scores (14-day half-life); rejection-blacklist 30→14 days + regime-scoped expiry; neglected-symbol watchlist slot; directional-rebalance bonus; per-pair sizing penalty. Single commit post-user request.
- `69ad008` — Observability layer: `signal_decisions` table + indexes + migration; `src/analytics/decision_log.py` (fire-and-forget writer, bulk, prune); `src/analytics/observability.py` (5 analysers: MAE patterns, WF↔live divergence, regime×template matrix, graduation funnel, opportunity cost); 9 new endpoints under `/analytics/observability/*`, `/health/trading-gates`, `/strategies/risk-attribution`. Pipeline instrumentation on strategy_proposer (wf_validated/rejected) and order_executor (gate_blocked + order_submitted).
- `398cd59` — System page refresh: Trading Gates card (side panel), Observability card (main panel) with funnel + tiles + top missed-alpha list. Fixed empty sections caused by: SignalDecisionLogORM typo in events_24h query → now reads SignalDecisionORM; Background Threads reading wrong paths → now reads `data.background_threads.*`; fake cache-hit percentages → honest Warm/Cold labels. Side-metric "Cache Hit" replaced with "Blockers".
- `d65d9a1` — Hotfix: correct monitoring_service attribute names (`_last_quick_price_update`, `_last_price_sync`, result dicts); added `_last_price_sync_result` persistence.
- `c803a03` — TZ fix: backend now appends `Z` to every ISO string in control.py; frontend `formatAge` appends `Z` defensively. Four more decision-log stages wired: `proposed` (track_proposals), `activated`/`rejected_act` (autonomous_strategy_manager), `signal_emitted` (strategy_engine), `order_filled` (order_monitor).
- `d97a414` — Hotfix: NameError `SignalAction` in proposer WF path (SHORT-tightening block referenced unimported symbol). Simplified the check to `isinstance(direction, str) and direction.lower() == 'short'`. Cycle at 08:08 UTC on May 2 threw this and exited stage 3 with 0 proposals; fixed and redeployed within minutes.

**Net: 8 files changed → 10 files → 11 files → 3 files → 2 files → 6 files → 1 file across the sequence. Every deploy verified healthy post-restart.**

### What's now persisted / visible that wasn't before

- `trade_journal.market_regime` — was 99.9% NULL (701/702 rows). Now populated on async fills via new `OrderORM.order_metadata` column.
- `trade_journal.max_adverse_excursion` / `max_favorable_excursion` — was NULL across all rows. Now updated every 60s on open positions.
- `OrderORM.slippage` / `fill_time_seconds` — now computed on fill before log_entry write.
- `signal_decisions` table — new; 8 stages wired (proposed, wf_validated/rejected, activated/rejected_act, signal_emitted, gate_blocked, order_submitted, order_filled).
- `strategy_proposals.symbols` / `template_name` — new columns; per-symbol proposed-count now survives retirement.
- System page: Trading Gates, Observability (funnel + tiles + missed-alpha), working Background Threads + 24h Event Timeline + Cache Status.
- 9 new endpoints: `/health/trading-gates`, `/strategies/risk-attribution`, `/analytics/observability/{mae-at-stop, wf-live-divergence, regime-template-matrix, graduation-funnel, opportunity-cost, signal-decisions/{symbol}, exec-summary}`.

### Cycle run 2026-05-02 08:08 UTC — post-audit verification

User triggered the first full autonomous cycle after all observability work shipped. Proposer threw the `SignalAction` NameError (my bug from the SHORT-tightening branch). Stage 3 exited with 0 proposals; downstream stages ran on existing strategies only. Hotfixed at 08:09 UTC via `d97a414`. Next cycle expected to populate `signal_decisions` across all 6 stages.

---

## Observability & Logs (EC2 `/home/ubuntu/alphacent/logs/`)

| File | Use |
|---|---|
| `errors.log` | **First thing every session** — near-empty on healthy days |
| `cycles/cycle_history.log` | Structured cycle summaries |
| `strategy.log` | Signal gen, WF, conviction |
| `risk.log` | Position sizing, validation |
| `alphacent.log` | Full INFO+ audit trail (rotates 10MB × 20 post-audit) |
| `data.log` | Price fetches, cache hits |
| `api.log` | HTTP + eToro API |
| `warnings.log` | WARNING level only |

Look for these INFO-level summary lines:
- `TSL cycle: ...` every 60s from monitoring_service
- `Exec cycle: ...` every signal-generation cycle from trading_scheduler
- `Price data sync complete: ...` hourly from monitoring_service
- `Quick price update: ...` every 10 min from monitoring_service

---

## Key Parameters (current, post-May 2)

### Risk per asset class
Stock/ETF: SL 6%, TP 15% | Forex: SL 2%, TP 5% | Crypto: SL 8%, TP 20% | Index: SL 5%, TP 12% | Commodity: SL 4%, TP 10%

### Position sizing
- `BASE_RISK_PCT`: 0.6% of equity per trade
- `CONFIDENCE_FLOOR`: 0.50
- `MINIMUM_ORDER_SIZE`: $5,000
- Symbol cap: 5% | Sector soft cap: 30% | Portfolio heat: 30%
- Drawdown sizing: 50% >5% DD, 75% >10% DD (30d peak)
- Vol scaling: 0.10x–1.50x
- **Per-pair loser penalty (May 2)**: (template, symbol) with ≥3 net-losing trades halves size until net-P&L flips positive.

### Activation thresholds
- `min_sharpe`: 1.0 | `min_sharpe_crypto`: 0.5 | `min_sharpe_commodity`: 0.5
- `min_trades_dsl`: 8 (1d) | 8 (4h) | 15 (1h)
- `min_trades_alpha_edge`: 8 | `min_trades_commodity`: 6
- Sharpe exception: test_sharpe ≥ 2.0 + ≥ 3 trades bypasses min_trades
- **SHORT tightening**: primary path needs min_sharpe +0.3 for shorts; relaxed-OOS rescue path removed for shorts; test-dominant needs ≥4 test trades.

### Conviction scoring
- Threshold: 65/100
- Asset tradability: Tier 1 15pts | Tier 2 13pts | ETFs 13pts | Indices 14pts

### Trailing Stop System
- Per-class ATR multiplier: stock/etf/commodity 2.0x, crypto/index 1.5x, forex 1.0x
- Timeframe-aware ATR (4H strategies use 4H bars)
- Breach enforcement independent of historical-bar freshness (needs only current_price + stop_loss from 60s sync)
- Per-cycle INFO summary line

### Signal-time gates (block orders at execute_signal)
- **C1 VIX**: blocks LONG when VIX>25 AND VIX_5d>+15% (crypto exempt)
- **C2 Momentum Crash**: regime_fit −10 for LONG trend/momentum/breakout when SPY_5d<−3% AND VIX_1d>+10%
- **C3 Trend Consistency**: blocks SHORT above rising 50d SMA or inside oversold-bounce zone; blocks LONG below falling 50d SMA (crypto/forex exempt)

### Feedback-loop decay
- Symbol score: 14-day half-life on trade recency; floor 0.2
- Rejection blacklist: 14-day cooldown (was 30) + regime-scoped early expiry
- Neglected-symbol reserve: 15% of each watchlist for symbols not seen in 7 days
- Directional-rebalance bonus: +8 for counter-direction on imbalanced-loser symbols

### Zombie exit (differentiated)
- Trend-following: 5d (1D) / 3d (4H)
- Mean reversion: 7d (1D) / 4d (4H)
- Alpha Edge: 14d (1D) / 7d (4H)

### Directional quotas (trending_up regimes)
- `trending_up`: min_long 80%, min_short 5%
- `trending_up_weak`: min_long 75%, min_short 8%
- `trending_up_strong`: min_long 85%, min_short 3%

---

## Diagnostic Queries

```sql
-- Decision-log funnel for the last cycle
SELECT stage, COUNT(*) FROM signal_decisions
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY stage ORDER BY COUNT(*) DESC;

-- Why didn't we trade TSLA? (or any symbol)
SELECT timestamp, stage, decision, template_name, reason
FROM signal_decisions
WHERE symbol='TSLA' AND timestamp > NOW() - INTERVAL '7 days'
ORDER BY timestamp DESC LIMIT 50;

-- Symbols with directional imbalance (still relevant after the rebalance bonus landed)
SELECT symbol, COUNT(*) AS trades,
       SUM(CASE WHEN side='LONG' THEN 1 ELSE 0 END) AS longs,
       SUM(CASE WHEN side='SHORT' THEN 1 ELSE 0 END) AS shorts,
       ROUND(SUM(pnl)::numeric, 2) AS pnl
FROM trade_journal WHERE pnl IS NOT NULL
GROUP BY symbol HAVING COUNT(*) >= 3
  AND (SUM(CASE WHEN side='LONG' THEN 1 ELSE 0 END) = 0
       OR SUM(CASE WHEN side='SHORT' THEN 1 ELSE 0 END) = 0)
ORDER BY pnl;

-- MAE vs exit P&L per symbol (entry quality diagnosis)
SELECT symbol,
       COUNT(*) AS trades,
       ROUND(AVG(max_adverse_excursion)::numeric, 3) AS avg_mae,
       ROUND(AVG(max_favorable_excursion)::numeric, 3) AS avg_mfe,
       ROUND(AVG(pnl_percent)::numeric, 2) AS avg_pnl_pct
FROM trade_journal
WHERE exit_time IS NOT NULL AND max_adverse_excursion IS NOT NULL
GROUP BY symbol HAVING COUNT(*) >= 5
ORDER BY avg_pnl_pct;

-- WF test-Sharpe vs live-Sharpe divergence
SELECT s.name, (s.strategy_metadata->>'wf_test_sharpe')::float AS wf,
       COUNT(p.id) FILTER (WHERE p.closed_at IS NOT NULL) AS closed,
       ROUND(AVG(p.realized_pnl) FILTER (WHERE p.closed_at IS NOT NULL), 2) AS avg_pnl
FROM strategies s
LEFT JOIN positions p ON p.strategy_id = s.id
GROUP BY s.id, s.name, (s.strategy_metadata->>'wf_test_sharpe')
HAVING COUNT(p.id) FILTER (WHERE p.closed_at IS NOT NULL) >= 5
ORDER BY ABS(COALESCE((s.strategy_metadata->>'wf_test_sharpe')::float, 0)) DESC;
```

---

## Open Items — Priority Order

### Next sprint (2026-05-02 audit findings) — USE THE PROMPT BELOW TO START

Copy this as-is into a new session when you're ready to execute:

```
Start this session by reading Session_Continuation.md (this file), AUDIT_REPORT_2026-05-02.md, and .kiro/steering/trading-system-context.md — in that order. They contain the full state, audit findings, and permanent rules. Do not skip.

Context in one paragraph: yesterday (May 1) shipped the observability layer + TSL audit + crypto min_trades tier. Today (May 2) discovered the observability layer was silently dropping every write (permission grant missing) — fixed, verified with a cycle producing 402 decision rows across 5 stages. Also raised symbol cap 3% → 5%, fixed MAE/MFE trade_id mismatch, backfilled 175 trade_journal orphans, fixed crypto commission modeling (was 0%, real is 1% per side → backtests overstated returns by ~2%/trade), expanded crypto universe to 6 coins (BTC/ETH/SOL/AVAX/LINK/DOT), added 2 new crypto trend templates, and fixed TZ drift on the UI. See AUDIT_REPORT_2026-05-02.md for the full findings list.

Your mission this session: ship the ordered fix list below. Each item is scoped to minutes of work, deployable independently, verified against ground truth before moving on. Follow the permanent deployment workflow (edit local → getDiagnostics → scp → restart → curl /health → commit + push).

TIER 1 (ship these definitely, ~90 min total):

1. P0-1 RETIREMENT REVIEW FIRST (before any change). The audit found 33 strategies carry pending_retirement=true, some since April 22, yet generated 27+ new entry orders AFTER the flag was set — last zombie signal May 1 10:21 UTC. Filter at trading_scheduler.py:285 exists but isn't preventing this. Don't fix by assumption — first trace:
   - Read all 5 retirement-flagging paths in monitoring_service.py (_check_strategy_decay, _check_strategy_health, _process_pending_retirements, _close_shorts_in_bull_market) and autonomous_strategy_manager.py (_check_retirement_triggers_in_cycle).
   - Identify every signal-generation entry point. Not just run_signal_generation_sync — check if anything else calls generate_signals or generate_signals_batch directly.
   - Check whether `superseded` or variation logic clears the flag.
   - Check timing: does decay check fire mid-cycle while signal gen is already running?
   Then propose your fix and implement it. Expected outcome: 33 zombie strategies stop firing new signals; flag either demotes them to BACKTESTED or strictly blocks signal gen; existing positions still close naturally via SL/TP.

2. P0-2 live_trade_count is 0 on all 180 strategies despite 85 open positions and 700+ closed trades. Root cause: order_executor._increment_strategy_live_trade_count only fires on synchronous fills; eToro async fills (all real fills) go through order_monitor.check_submitted_orders which never calls this increment. Move the increment to order_monitor fill handler. Then backfill historical counts from trade_journal: UPDATE strategies SET live_trade_count = (SELECT COUNT(*) FROM trade_journal WHERE strategy_id=strategies.id AND exit_time IS NOT NULL). Verify downstream: retirement_logic.min_live_trades_before_evaluation=5 gate should now fire for strategies with ≥5 closed trades.

3. P0-6 Cycle-error observability gap. When a cycle stage throws (SignalAction NameError today, Tuple NameError at 07:22 UTC), cycle_history.log shows [ERROR] CYCLE but nothing writes to signal_decisions. Add a `cycle_error` stage write in the top-level run_strategy_cycle try/except in autonomous_strategy_manager.py. ~10 lines. Ensures stage failures surface in the Observability funnel.

TIER 2 (ship if time permits, ~60 min):

4. P1-5 Factor-validation gate failures are logged as ERROR but they're just gate rejections. 4 per cycle. Reclassify to INFO in autonomous_strategy_manager._activate_alpha_edge (factor gate path).

5. P1-4 MINIMUM_ORDER_SIZE bypasses penalty mechanisms. risk_manager.calculate_position_size Step 11 bumps any sub-$5K position back to $5K even if drawdown sizing, vol scaling, and loser-pair penalty all fired. Track a penalty_applied flag through the function; if True, return 0 instead of bumping.

6. P1-6 Raise log rotation. src/core/logging_config.py — bump main log backup_count 20 → 100. Current window is ~8h of history, too short for DST/incident forensics.

TIER 3 (nice to have):

7. P1-1 DELETE FROM orders WHERE status='FAILED' AND submitted_at < '2026-04-30' AND order_action='entry'. One-off SQL. Cleans up 800 legacy FAILED rows from the Apr 27-29 DST-crash spike.

8. P1-3 Zero-out bad fill_time_seconds: UPDATE orders SET fill_time_seconds = NULL WHERE fill_time_seconds < 0. Legacy data bug; ~44 rows with negative fill times from pre-today compute-quality work.

9. P1-extra Extend crypto WF test window. For 1d crypto templates with expected_holding_period > 30d (21W MA, Vol-Compression, Weekly Trend Follow, Golden Cross), use 730-day test window instead of 180. Currently long-horizon crypto strategies can't produce enough trades in 180d. Add a lookup in strategy_proposer WF dispatch.

KEEP DEFERRED (already in backlog, don't touch):

- Monday Asia Open session template (needs DSL HOUR() support — 2-3h infra work)
- Vol-Compression template non-propose debug (filed as P2-1)
- Overview chart panel rewrite (needs design doc first)
- trade_id convention unification (P1-2, 90 min — pair with next architectural work)

VERIFICATION QUERIES (run these after each Tier 1 fix):

-- After P0-1 retirement fix:
SELECT COUNT(*) as active_zombies FROM strategies
WHERE (strategy_metadata::jsonb->>'pending_retirement')::text='true'
  AND status IN ('DEMO','LIVE');
-- Target: should trend to 0 over days (positions close → demote)

-- Check no new signals for flagged strategies post-fix:
SELECT p.name, COUNT(o.id) FILTER (WHERE o.submitted_at > NOW() - INTERVAL '30 minutes' AND o.order_action='entry') as new_zombie_signals
FROM strategies p LEFT JOIN orders o ON o.strategy_id = p.id
WHERE (p.strategy_metadata::jsonb->>'pending_retirement')::text='true'
GROUP BY p.id, p.name HAVING COUNT(o.id) FILTER (WHERE o.submitted_at > NOW() - INTERVAL '30 minutes' AND o.order_action='entry') > 0;
-- Target: 0 rows

-- After P0-2 live_trade_count fix + backfill:
SELECT status, COUNT(*), AVG(live_trade_count)::int as avg, MAX(live_trade_count) FROM strategies GROUP BY status;
-- Target: DEMO strategies with closed trades should have live_trade_count > 0

-- After P0-6 cycle_error:
SELECT stage, COUNT(*) FROM signal_decisions WHERE timestamp > NOW() - INTERVAL '2 hours' GROUP BY stage;
-- Target: stages list includes cycle_error if any stage threw in the window

-- Ambient health (run before starting):
SELECT 'signal_decisions_last_cycle' as m, COUNT(*)::text FROM signal_decisions WHERE timestamp > NOW() - INTERVAL '30 minutes'
UNION ALL SELECT 'mae_populated_open', COUNT(*)::text FROM trade_journal WHERE exit_time IS NULL AND max_adverse_excursion IS NOT NULL
UNION ALL SELECT 'pending_retire_zombies', COUNT(*)::text FROM strategies WHERE (strategy_metadata::jsonb->>'pending_retirement')::text='true';
```

### P0 — needs verification post-next-cycle (triggered 08:08 UTC May 2)
- Confirm `signal_decisions` has rows across all 6 primary stages (proposed, wf_validated, activated, signal_emitted, order_submitted, order_filled). SQL: `SELECT stage, COUNT(*) FROM signal_decisions GROUP BY stage;`
- Confirm System page Observability funnel populates.
- Confirm `trade_journal.market_regime` has non-NULL values on new trades.
- Confirm MAE/MFE populating on open positions.

### P1 — deferred work (from ranked observability list and prior audits)
- **Entry-timing score** — needs per-minute post-entry price snapshots (not currently captured).
- **Deploy-validation auto-tracker** — subsumed by signal_decisions once populated.
- **WF bypass path tightening for LONG** — primary + test-dominant paths admit regime-luck on LONG side. Consider `(test_sharpe - train_sharpe) ≤ 1.5` consistency gate.
- **Cycle-error stage** — add `cycle_error` decision_log write when a cycle stage throws so stage failures are visible in the funnel. Today's `SignalAction` NameError was only visible in logs.

### P2 — known bugs not yet addressed
- Entry order 82% FAILED rate (cosmetic, market-closed deferrals)
- NVDA/AMZN cumulative symbol concentration (7.43% each)
- Triple EMA Alignment DSL bug (EMA(10)>EMA(10))
- MQS persistence silent failure
- Sector Rotation + Pairs Trading template structural issues
- Regime classification two-tier inconsistency
- Overview chart panel axis alignment

---

## Files Changed (May 1-2, 2026)

### Backend
- `src/models/orm.py` — added `OrderORM.order_metadata`, `StrategyProposalORM.symbols` + `template_name`, new `SignalDecisionORM` class
- `src/core/monitoring_service.py` — timeframe-aware TSL, decoupled breach, per-cycle summary, MAE/MFE updater, `_last_price_sync_result` persistence
- `src/core/order_monitor.py` — order_metadata hydration on fill, slippage + fill_time compute, order_filled decision write
- `src/core/trading_scheduler.py` — metadata persistence on order insert, Exec cycle summary line
- `src/execution/position_manager.py` — rewritten TSL method (cleaner), ATR_MULTIPLIER_BY_ASSET_CLASS, dead except branches removed
- `src/execution/order_executor.py` — C3 trend-consistency gate, `_log_decision` helper, order_submitted write
- `src/strategy/strategy_proposer.py` — recency-weighted symbol score, rejection blacklist 30→14 days + regime expiry, neglected-symbol slot, directional rebalance bonus, SHORT WF tightening, proposed-stage decision log, SignalAction typo hotfix
- `src/strategy/strategy_engine.py` — signal_emitted decision log
- `src/strategy/autonomous_strategy_manager.py` — activated / rejected_act decision log
- `src/risk/risk_manager.py` — per-pair sizing penalty (Step 10b)
- `src/analytics/trade_journal.py` — recency_weight per symbol in performance feedback
- `src/analytics/decision_log.py` — NEW (fire-and-forget writer + bulk + prune)
- `src/analytics/observability.py` — NEW (5 analysers: MAE, WF divergence, regime×template matrix, funnel, opp cost)
- `src/api/routers/analytics.py` — 7 observability endpoints
- `src/api/routers/strategies.py` — /risk-attribution endpoint, Symbols-tab endpoint consumes trade_journal
- `src/api/routers/control.py` — /health/trading-gates, extended /control/system-health with background_threads + trading_gates + observability + Z-suffix ISO timestamps; SignalDecisionLogORM typo fix in events_24h
- `src/api/app.py` — /health/trading-gates endpoint
- `src/core/logging_config.py` — backup_count 5→20 main, 3→10 component

### Frontend
- `frontend/src/components/trading/SymbolManager.tsx` — reworked columns (Proposed/Active/Traded/Sharpe/Win%/P&L/Best Template), lifetime data source
- `frontend/src/pages/SystemHealthPage.tsx` — Trading Gates card, Observability card with funnel + tiles + missed-alpha, Background Threads fixed path, Cache Status labels, formatAge TZ defensive parsing
- `frontend/src/lib/stores/system-health-store.ts` — new types for background_threads, trading_gates, observability

### DB migrations applied to prod
- `ALTER TABLE orders ADD COLUMN order_metadata JSON;`
- `ALTER TABLE strategy_proposals ADD COLUMN symbols JSON, ADD COLUMN template_name VARCHAR;`
- `CREATE TABLE signal_decisions (...)` with 5 indexes
