# AlphaCent — Audit Fix Tracker

> Living document tracking execution of the 2026-05-01 audit findings. Update status inline as work progresses. Each finding has a unique ID (F##). See `AUDIT_REPORT_2026-05-01.md` for full audit context.

**Session legend:**
- ⬜ Not started
- 🟡 In progress
- 🔵 Deployed, awaiting verification
- ✅ Verified in production
- ❌ Blocked / deferred
- 🔁 Rolled back

**Last updated:** 2026-05-01 (session 1)

---

## Quick Status

| Batch | Focus | Status | Notes |
|---|---|---|---|
| 1 | Data integrity foundation | � Deployed, awaiting verification | F02 A/B/C + F09 shipped 2026-05-01 10:02 UTC |
| 2 | Execution observability | ⬜ Not started | F04 + F10 |
| 3 | Position risk | ⬜ Not started | F03, F11, F18-critical |
| 4 | Signal quality | ⬜ Not started | F01/F12 Phase 2, F05, F07, F08 |
| 5 | Alpha + polish | ⬜ Not started | F06, F16, F17, F13, F15, F18-rest, F19-22, F24-25 |
| Deferred | Future sessions | ⬜ Not started | F01/F12 Phase 3, F14, F11 full |

**Overall progress:** 4 / 25 findings deployed (awaiting verification)

---

## Deployment Rules (permanent)

1. Edit locally → `getDiagnostics` → scp to EC2 → restart service → verify `/health` → commit + push.
2. No in-place edits on EC2. No pulling files from EC2.
3. After each batch, observe for the stated window before moving on.
4. If any verification step fails, mark 🔁 rolled back and diagnose before retrying.
5. Update this document at every meaningful state change.

---

## Batch 1 — Data integrity foundation

**Deploy window:** Start now. Monitor for 24-48h before moving to Batch 2.  
**Success criteria:** Next daily sync (20:00 UTC today) completes with 0 AmbiguousTimeError; >290 symbols refreshed; no stale-data signals generated.

### F02 — DST / yfinance fix (three parts)

**Root cause:** `yf.download()` with naive datetimes triggers internal tz-inference that crashes on DST boundaries (2025-11-02 ambiguous hour). Existing post-return tz_convert fix runs too late. 166 symbols failed overnight at 01:47 UTC today.

#### F02 Part A — tz-aware UTC datetimes at all yfinance call sites

**Files changed (6 call sites):**
- [x] `src/core/monitoring_service.py:1094` — batch download
- [x] `src/data/market_data_manager.py:834-837` — ticker.history(period="1d",interval="1m") for latest (added normalize_yf_index_to_utc_naive)
- [x] `src/data/market_data_manager.py:882-897` — ticker.history(start,end,interval)
- [x] `src/api/etoro_client.py:515` — NOTE: left unchanged; this path uses ticker.info which doesn't take user datetimes
- [x] `src/api/etoro_client.py:587-588` — ticker.history(start,end)
- [x] `src/api/routers/analytics.py:4120-4121` — SPY benchmark
- [x] `src/utils/yfinance_compat.py` — NEW module (to_tz_aware_utc, normalize_yf_index_to_utc_naive)

**Status:** 🔵 Deployed 2026-05-01 10:02 UTC, awaiting 24h verification window.

**Initial verification (post-restart 10:02 UTC):**
- `[bg-full-sync] Batch Yahoo download: 286 symbols for 1d` — succeeded
- `[bg-full-sync] Batch Yahoo download: 166 symbols for 1h` — succeeded (exact same batch that crashed at 01:47 UTC)
- `Price data sync complete: 297 daily + 295 hourly symbols synced in 89.7s ... 0 errors`
- No AmbiguousTimeError in `errors.log` since deploy
- Sample symbols (NVDA, AAPL, GS, SPY, QQQ, TXN) all show `1h MAX(date) = 2026-05-01 10:00:00` — fresh

**Full verification needed at 20:00 UTC today (next daily sync) and 01:47 UTC tomorrow (next DST-adjacent overnight window).**

#### F02 Part B — Per-ticker retry on batch miss

**Status:** 🔵 Deployed 2026-05-01 10:02 UTC.

**Initial verification:** Not yet triggered (batch succeeded fully — 0 misses). Logic in place to fire when batch returns partial data.

#### F02 Part C — Freshness SLA blocking stale-data signals

**Files changed:**
- [x] `src/data/market_data_manager.py` — added `_FRESHNESS_MAX_AGE_HOURS`, `_get_asset_class_family`, `get_latest_bar_timestamp`, `_subtract_weekend_hours`, `is_data_fresh_for_signal`
- [x] `src/strategy/strategy_engine.py` — `generate_signals_batch` calls freshness check; stale symbols removed from `shared_data`
- [x] `src/core/monitoring_service.py _check_trailing_stops` — freshness check before modification; skip + preserve existing SL on stale data

**Status:** 🔵 Deployed 2026-05-01 10:02 UTC.

**Initial verification:**
- Post-restart cold-cache state correctly flagged 196 (symbol, interval) pairs with no cached data, preventing signal gen
- Warnings logged clearly: `[freshness-sla] Skipping {sym} {interval} for signal generation: no cached data for ...`
- After sync completed (10:03:57), freshness gate still active for truly stale pairs (e.g. GS 4h at 2026-04-14 = 17d stale) — correctly blocked

**Still to verify:**
- Trailing-stop skip behaviour on GS 4h (next `_check_trailing_stops` cycle should log skip for GS)
- SL on GS position unchanged over next 24h despite stale data

### F09 — 4H stale on open-position symbols

**Status:** 🔵 Deployed 2026-05-01 10:02 UTC (bundled into F02 Part C — reuses `is_data_fresh_for_signal`).

### Batch 1 Verification Queries (run after deploy)

```bash
# 1. DST crash should not recur
ssh ... 'grep "AmbiguousTimeError" /home/ubuntu/alphacent/logs/errors.log | tail -5'
# Expected: no entries since deploy time

# 2. Fresh data coverage
ssh ... 'sudo -u postgres psql alphacent -t -A -c "
  SELECT interval, COUNT(DISTINCT symbol) as syms, MIN(maxdate) as oldest 
  FROM (SELECT symbol, interval, MAX(date) as maxdate FROM historical_price_cache GROUP BY symbol, interval) a 
  GROUP BY interval;"'
# Expected: 1d oldest within 48h; 4h within 30h; 1h within 6h

# 3. Freshness gate firing
ssh ... 'grep "data too stale" /home/ubuntu/alphacent/logs/alphacent.log | tail -20'
# Expected: some skips on stale symbols; most symbols pass

# 4. Signals still firing on fresh data
ssh ... 'tail -30 /home/ubuntu/alphacent/logs/cycles/cycle_history.log'
# Expected: normal signal generation continues
```

---

## Batch 2 — Execution observability

**Deploy window:** Start after Batch 1 runs clean for 24-48h.  
**Success criteria:** Entry-order FAILED rate drops below 20%. Slippage column populated on every FILLED row. `cycle_history.log` shows no repeated signals during market-closed periods.

### F04 — Execution observability (three parts) + F10 (same root cause)

#### F04 Part 1 — Upstream market-gate on signal generation

**Change:** Before running strategy signal loop, filter out strategies whose 100% of target symbols are in currently-closed markets.

**Files:**
- [ ] `src/core/trading_scheduler.py` — extend existing `filtered_strategies` loop to check all strategy.symbols, skip if all closed

**Status:** ⬜
**Verification:** `cycle_history.log` pre-market (09:00 UTC) should show 0 stock entry signals; crypto strategies should continue.

#### F04 Part 2 — DEFERRED status + cross-cycle dedup

**Files:**
- [ ] `src/models/orm.py` or wherever OrderStatus enum lives — add `DEFERRED`
- [ ] `src/execution/order_executor.py:365` — on market-closed, set `order.status = DEFERRED` and return (don't raise)
- [ ] `src/core/trading_scheduler.py` — add `self._deferred_signals: Dict[Tuple, datetime]` with 30min TTL; check at signal-processing time

**Status:** ⬜
**Verification:** Query order status distribution over 1 full trading day — DEFERRED should replace most FAILED entries; cross-cycle dedup should prevent multiple DEFERRED rows per (strategy, symbol, direction) within 30 min.

#### F04 Part 3 — Populate slippage and fill_time_seconds

**Files:**
- [ ] `src/core/order_monitor.py` — in fill handler, compute `slippage = direction_sign * (filled - expected)/expected` and `fill_time_seconds = (filled_at - submitted_at).total_seconds()`

**Status:** ⬜
**Verification:** `SELECT COUNT(slippage), COUNT(*) FROM orders WHERE status='FILLED' AND filled_at >= (deploy_time)` — 100% populated.

---

## Batch 3 — Position risk

**Deploy window:** Can deploy any time after Batch 1. Independent of Batch 2.

### F03 — Asset-class tiered concentration cap

**Caps:**
- stock: 3%
- etf: 5%
- index: 6%
- forex: 5%
- crypto: 2.5%
- commodity: 4%

**Logic:** Direction-aware net exposure. Full-or-skip with 70% partial threshold. Cumulative across all strategies on the symbol.

**Files:**
- [ ] `src/execution/order_executor.py` — add pre-flight concentration gate after market-hours check
- [ ] `config/autonomous_trading.yaml` — add `symbol_concentration_caps_by_asset_class` section
- [ ] `src/core/config_loader.py` — wire new config

**Status:** ⬜
**Verification:** DB query `SELECT symbol, asset_class, SUM(invested_amount * side_sign) / equity * 100` — no symbol net% exceeds its asset-class cap. Log line appears on scale-down and skip events.

### F11 — Intermediate trailing-stop ratchet

**Change:** Add one step between breakeven (+3%) and trail activation (+7.5%): at +5% profit, move SL to entry + 2%.

**Files:**
- [ ] `src/execution/position_manager.py:91` — add to `PROFIT_LOCK_PARAMS` and check logic

**Status:** ⬜
**Verification:** Query positions currently at +3% to +7.5% profit — after next trailing check, positions above +5% should have SL ≈ entry + 2%.

### F18-critical — Silent failure fixes (sizing-critical only)

**Files:**
- [ ] `src/api/routers/account.py:1594, 1618` — change `return 0.0` to `raise` for equity snapshot fetch failures
- [ ] `src/core/monitoring_service.py:221, 236` — change market-hours fail-open to fail-closed with 3-attempt retry

**Status:** ⬜
**Verification:** Grep for changes in DB/SQLAlchemy error rate (shouldn't increase — these paths rarely error). No new exceptions propagating during normal ops.

---

## Batch 4 — Signal quality

**Deploy window:** After Batches 1-2 stable for 3-5 days. Needs clean data and reliable execution metrics to verify.

### F01/F12 Phase 2 — WF validation tightening

**Changes:**
- Remove `test-dominant` pass path (train ≥ -0.1 AND test ≥ min_sharpe)
- Remove `excellent OOS` pass path (train ≥ -0.3 AND test ≥ min_sharpe × 2)
- Add consistency gate: `(test_sharpe - train_sharpe) <= 1.5`
- Keep `min_sharpe = 1.0` unchanged
- Keep Pass-2 relaxed fallback (but tighten to `train>0.3 AND test>0.5` from current `>0.1/>0.1`)
- NO force-retirement of existing book — decay scorer handles naturally

**Files:**
- [ ] `src/strategy/strategy_proposer.py:1635-1651` — remove bypass paths, add consistency gate

**Status:** ⬜
**Verification:**
- Next cycle activation pass-rate ~15% (was ~25%)
- New activations have test-train gap ≤ 1.5
- Over 2 weeks, track live Sharpe of new cohort vs expected (feeds Phase 3 calibration)

### F05 — Triple EMA fix + hybrid substitution

**Changes:**
- Add `{fast_period}`, `{mid_period}`, `{slow_period}` placeholders to Triple EMA Alignment template only
- Add hybrid substitution: format_map first, regex fallback
- Add advisory validator (startup WARNING, not blocking)
- One-off audit script to dump all template conditions post-substitution

**Files:**
- [ ] `src/strategy/strategy_templates.py` — Triple EMA Alignment entry/exit conditions
- [ ] `src/strategy/strategy_proposer.py` — `_apply_params` becomes hybrid; add `_validate_template_conditions` at module load
- [ ] `scripts/diagnostics/audit_template_conditions.py` — new

**Status:** ⬜
**Verification:** Startup logs show 0 or minimal validator warnings. Triple EMA variants in DB post-next-cycle have distinct EMA periods per clause. Audit script output reviewed.

### F07 — MC Bootstrap annualization window

**Change:** Use actual test_days per timeframe (1h=90, 4h=120, 1d=240) instead of hardcoded 180.

**Files:**
- [ ] `src/strategy/strategy_proposer.py:1567` — replace hardcoded value with `_get_test_window_days(strategy)`

**Status:** ⬜
**Verification:** WF log lines should show MC using correct window per strategy. Next cycle: more 4H passes than before (was under-estimated).

### F08 — Fast-feedback revision

**Changes:**
- `LOOKBACK_DAYS = 10` (was 5)
- `MIN_TRADES = 4` (was 3)
- Suppress if WR < 35% OR profit_factor < 0.7
- Flag templates with 0 closed but significant open unrealized losses (monitor only)

**Files:**
- [ ] `src/analytics/trade_journal.py:1499-1580` — `get_fast_performance_feedback`
- [ ] `src/strategy/autonomous_strategy_manager.py:1253-1272` — call with new params

**Status:** ⬜
**Verification:** Next cycle log shows suppression decisions with profit-factor values. Losing templates (Fast EMA Crossover, SMA Proximity) trip suppression after a few more closes.

---

## Batch 5 — Alpha + infra polish (low priority)

### F06 — MQS persistence investigation + fix

**First:** 1-hour investigation to determine if MQS is used live, or dead code.
- grep `market_quality_score` readers
- check sizing paths
- query historical snapshots for any non-NULL

**Then:** fix or remove accordingly. May also need backfill from SPY+VIX history in `historical_price_cache`.

**Status:** ⬜

### F16 — Asset-class-weighted proposal quotas

**Change:** Multiply per-class proposal count by WR-driven weight refreshed every N cycles. Over-propose high-WR classes (ETF, index), under-propose low-WR (stock).

**Status:** ⬜

### F17 — Remove min_short hard enforcement; monitor as target only

**Status:** ⬜

### F13 — Delete dead `atr_sl_multiplier` from config

**Status:** ⬜

### F15 — Remove BTC Lead-Lag Altcoin template from library

**Status:** ⬜

### F18-rest — Add `logger.exception` to silent defaults

- `etoro_client.py:317, 326`
- `llm_service.py:1071`
- `market_analyzer.py:776`
- `news_sentiment_provider.py:189, 284`

**Status:** ⬜

### F19 — `pool_pre_ping=True` on SQLAlchemy engine

**Status:** ⬜

### F20 — FRED retry wrapper

**Status:** ⬜

### F21 — Delete phantom altcoin rows from historical_price_cache

```sql
DELETE FROM historical_price_cache 
WHERE symbol IN ('SOL','ADA','XRP','DOT','LINK','LTC','BCH','AVAX','NEAR','DOGE')
   OR symbol IN ('UPS','ZINC','RUBBER');  -- also phantom stocks/commodities
```

**Status:** ⬜

### F22 — Rotate errors.log once; tighten policy

**Status:** ⬜

### F24 — Remove or wire `proposed` counter in UI

**Status:** ⬜

### F25 — Overview chart panel rewrite (L effort — defer design doc first)

**Status:** ⬜

---

## Deferred (future sessions)

### F01/F12 Phase 3 — Calibrate min_sharpe from live data

Trigger: 2-4 weeks of clean runs after Batch 4 deploy. Run diagnostic query over all activated strategies:

```sql
SELECT 
  s.name,
  (s.strategy_metadata->>'wf_test_sharpe')::float as test_sharpe,
  (s.strategy_metadata->>'wf_train_sharpe')::float as train_sharpe,
  (SELECT AVG(realized_pnl)/NULLIF(STDDEV(realized_pnl),0)*SQRT(252) 
   FROM positions WHERE strategy_id = s.id AND closed_at IS NOT NULL) as live_sharpe,
  (SELECT COUNT(*) FROM positions WHERE strategy_id=s.id AND closed_at IS NOT NULL) as closed_n
FROM strategies s
WHERE s.status IN ('DEMO','BACKTESTED')
  AND (SELECT COUNT(*) FROM positions WHERE strategy_id=s.id AND closed_at IS NOT NULL) >= 5;
```

Use live_sharpe distribution to set new `min_sharpe` floor that keeps expected forward live Sharpe ≥ 0.5.

**Status:** ❌ Deferred — scheduled for post-Batch-4-stable

### F14 — Yahoo forex/SPY fallback

Re-audit after F02 deploys. If "possibly delisted" errors persist, design per-symbol fallback.

**Status:** ❌ Deferred — depends on F02 outcome

### F11 full — Chandelier / percentage continuous trail

Alpha optimisation after F11-lite (single intermediate step) shows whether the gap was a meaningful alpha leak.

**Status:** ❌ Deferred

---

## Session Log

### Session 1 — 2026-05-01
- Completed full audit, findings in `AUDIT_REPORT_2026-05-01.md`
- Reviewed top-5 findings under trading-PoV lens, refined fix proposals
- Reviewed remaining P0/P1/P2 findings, produced final fix list with batch sequencing
- Created this tracker
- **Deployed Batch 1** at 2026-05-01 10:02 UTC:
  - F02 Part A — tz-aware UTC at all yfinance call sites + new `src/utils/yfinance_compat.py` helper module
  - F02 Part B — per-ticker retry on batch miss (capped at 20)
  - F02 Part C — freshness SLA via `is_data_fresh_for_signal` helper, wired into `generate_signals_batch` and `_check_trailing_stops`
  - F09 — bundled into F02 Part C
- Batch 1 initial verification: 297 daily + 295 hourly symbols synced with 0 errors; 196 stale pairs correctly blocked from signal gen; NVDA/AAPL/GS/SPY/QQQ 1h all fresh to 2026-05-01 10:00
- Full Batch 1 verification windows: 20:00 UTC today (next daily sync) + 01:47 UTC tomorrow (next DST-adjacent overnight) + 24h open-position stability with freshness gates active

[continue log as work progresses]
