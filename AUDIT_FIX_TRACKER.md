# AlphaCent — Audit Fix Tracker

> Living document tracking execution of the 2026-05-01 audit findings. Update status inline as work progresses. Each finding has a unique ID (F##). See `AUDIT_REPORT_2026-05-01.md` for full audit context.

**Session legend:**
- [ ] Not started
- [.] In progress
- [D] Deployed, awaiting verification
- [x] Verified in production
- [!] Blocked / deferred
- [~] Rolled back

**Last updated:** 2026-05-01 (session 1 — quick-wins batch)

---

## Quick Status

| Batch | Focus | Status | Notes |
|---|---|---|---|
| 1 | Data integrity foundation | [D] Deployed | F02 A/B/C + F09 shipped 2026-05-01 10:02 UTC |
| Quick-wins | Low-risk cleanups | [D] Deployed | F13, F15, F19, F21, F22, docs — shipped 2026-05-01 10:19 UTC |
| 2 | Execution observability | [ ] Not started | F04 + F10 |
| 3 | Position risk | [ ] Not started | F03, F11, F18-critical |
| 4 | Signal quality | [ ] Not started | F01/F12 Phase 2, F05, F07, F08 |
| 5 | Alpha + polish | [ ] Not started | F06, F16, F17, F18-rest, F20, F24-25 |
| Deferred | Future sessions | [!] Deferred | F01/F12 Phase 3, F14, F11 full |

**Overall progress:** 9 / 25 findings deployed (awaiting verification)

---

## Deployment Rules (permanent)

1. Edit locally → `getDiagnostics` → scp to EC2 → restart service → verify `/health` → commit + push.
2. No in-place edits on EC2. No pulling files from EC2.
3. After each batch, observe for the stated window before moving on.
4. If any verification step fails, mark [~] rolled back and diagnose before retrying.
5. Update this document at every meaningful state change.

---

## Batch 1 — Data integrity foundation

**Deployed:** 2026-05-01 10:02 UTC. **Monitor for 24-48h.**  
**Success criteria:** Next daily sync (20:00 UTC today) completes with 0 AmbiguousTimeError; >290 symbols refreshed; no stale-data signals generated.

### F02 Part A — tz-aware UTC datetimes at all yfinance call sites

**Files changed:**
- [x] `src/core/monitoring_service.py:1094` — batch download
- [x] `src/data/market_data_manager.py:834-837` — latest quote via normalize_yf_index_to_utc_naive
- [x] `src/data/market_data_manager.py:882-897` — historical fetch with tz-aware bounds
- [x] `src/api/etoro_client.py:587-588` — historical fetch with tz-aware bounds (515 path uses `ticker.info`, no datetime bounds; left unchanged)
- [x] `src/api/routers/analytics.py:4120-4121` — SPY benchmark
- [x] `src/utils/yfinance_compat.py` — NEW module (`to_tz_aware_utc`, `normalize_yf_index_to_utc_naive`)

**Status:** [D] Deployed 2026-05-01 10:02 UTC.

**Initial verification (post-restart):**
- Batch Yahoo downloads 286 (1d) + 166 (1h) succeeded — the same 166-ticker batch that crashed at 01:47 UTC today
- `Price data sync complete: 297 daily + 295 hourly symbols synced in 89.7s ... 0 errors`
- No AmbiguousTimeError in errors.log since deploy
- NVDA, AAPL, GS, SPY, QQQ, TXN 1h all fresh to 10:00 UTC

**Full verification windows:** 20:00 UTC today (next daily sync) + 01:47 UTC tomorrow (next DST-adjacent overnight).

### F02 Part B — Per-ticker retry on batch miss

**Status:** [D] Deployed 2026-05-01 10:02 UTC.

Not yet triggered (batch succeeded fully — 0 misses). Logic in place for partial-batch fallback.

### F02 Part C — Freshness SLA blocking stale-data signals

**Files changed:**
- [x] `src/data/market_data_manager.py` — `_FRESHNESS_MAX_AGE_HOURS`, `_get_asset_class_family`, `get_latest_bar_timestamp`, `_subtract_weekend_hours`, `is_data_fresh_for_signal`
- [x] `src/strategy/strategy_engine.py` — `generate_signals_batch` drops stale (symbol, interval) pairs from `shared_data`
- [x] `src/core/monitoring_service.py _check_trailing_stops` — skip SL modification on stale data; preserve existing SL

**Status:** [D] Deployed 2026-05-01 10:02 UTC.

**Initial verification:**
- 196 stale (symbol, interval) pairs correctly blocked at cold-cache post-restart
- Warnings clear: `[freshness-sla] Skipping {sym} {interval} for signal generation: no cached data for ...`
- GS 4h (17 days stale) correctly blocked after cache warm-up

**Still to verify:**
- Trailing-stop skip log line for GS on next `_check_trailing_stops` cycle
- GS SL unchanged over next 24h despite stale data

### F09 — 4H stale on open-position symbols

**Status:** [D] Bundled into F02 Part C — reuses `is_data_fresh_for_signal` in `_check_trailing_stops`.

---

## Quick-wins (session 1) — deployed 2026-05-01 10:19 UTC

Low-risk cleanups shipped alongside Batch 1 to reduce noise and tidy config drift before Batch 2 verification windows.

### F13 — Delete dead `atr_sl_multiplier` from config

**Status:** [D] Deployed.

Removed `atr_sl_multiplier: 2.5` and `atr_tp_multiplier: 5.0` from `config/autonomous_trading.yaml` — both were never read. Replaced with comment pointing to the hardcoded 1.5x in `order_executor.py:241`. Documentation-vs-code drift eliminated.

### F15 — Remove BTC Lead-Lag Altcoin Momentum template

**Status:** [D] Deployed.

- Template definition removed from `src/strategy/strategy_templates.py` (lines ~7523-7568) with explanatory comment.
- One DEMO strategy `e5249e8f-660c-4176-a08d-06ceecf909de` retired via SQL UPDATE with `retirement_reason` set.
- Open ETH LONG position left intact with SL/TP enforcement — will exit naturally rather than crystallise the $105 unrealised loss.

### F19 — `pool_pre_ping=True` on SQLAlchemy engine

**Status:** [D] Deployed.

Flipped PostgreSQL engine from `pool_pre_ping=False` to `True` in `src/models/database.py:61`. Adds ~1ms per query but catches dead connections (SSL drops, network partition) before they surface as user errors. Motivated by the Apr 30 "SSL connection has been closed unexpectedly" incident.

### F21 — Phantom altcoin/delisted rows purged

**Status:** [D] Deployed.

`DELETE FROM historical_price_cache WHERE symbol IN (...)` — 79,785 rows removed for SOL/ADA/XRP/DOT/LINK/LTC/BCH/AVAX/NEAR (disabled altcoins) + UPS (delisted) + ZINC/RUBBER (unsupported commodities). Verified 0 open positions, 4 historical closed positions (left intact — no FK).

### F22 — errors.log rotated

**Status:** [D] Deployed.

Rotated `errors.log` (4.7MB, 31k lines of pre-fix noise) to `errors.log.pre-audit-2026-05-01`. Fresh 0-byte errors.log for clean Batch 1 verification windows. Service restart at 10:19 UTC ensured handlers reopen against new file.

### Docs updates

**Status:** [D] Deployed.

- `.kiro/steering/trading-system-context.md` — DST handling section rewritten to reflect `yfinance_compat.py`; ATR multiplier note corrected to "hardcoded, config key removed"; MQS persistence caveat added.
- `Session_Continuation.md` — current state refreshed post-Batch-1; open-items section rewritten to point at `AUDIT_FIX_TRACKER.md`; ATR multiplier note corrected.

---

## Batch 2 — Execution observability

**Deploy window:** Start after Batch 1 runs clean for 24-48h.  
**Success criteria:** Entry-order FAILED rate drops below 20%. Slippage column populated on every FILLED row. `cycle_history.log` shows no repeated signals during market-closed periods.

### F04 — Execution observability (three parts) + F10

#### F04 Part 1 — Upstream market-gate on signal generation

**Change:** Filter out strategies whose 100% of target symbols are in currently-closed markets before signal generation.

**Files:**
- [ ] `src/core/trading_scheduler.py` — extend `filtered_strategies` loop

**Status:** [ ]

#### F04 Part 2 — DEFERRED order status + cross-cycle dedup

**Files:**
- [ ] `src/models/orm.py` — add `DEFERRED` to OrderStatus
- [ ] `src/execution/order_executor.py:365` — on market-closed, set `order.status = DEFERRED`
- [ ] `src/core/trading_scheduler.py` — `self._deferred_signals: Dict[Tuple, datetime]` with 30min TTL

**Status:** [ ]

#### F04 Part 3 — Populate slippage and fill_time_seconds

**Files:**
- [ ] `src/core/order_monitor.py` — fill handler computes slippage + fill time

**Status:** [ ]

---

## Batch 3 — Position risk

**Deploy window:** Any time after Batch 1. Independent of Batch 2.

### F03 — Asset-class tiered concentration cap

**Caps:** stock 3% / etf 5% / index 6% / forex 5% / crypto 2.5% / commodity 4%.  
**Logic:** direction-aware netting, full-or-skip with 70% partial threshold.

**Files:**
- [ ] `src/execution/order_executor.py` — pre-flight concentration gate
- [ ] `config/autonomous_trading.yaml` — `symbol_concentration_caps_by_asset_class`
- [ ] `src/core/config_loader.py` — wire config

**Status:** [ ]

### F11 — Intermediate trailing-stop ratchet

**Change:** At +5% profit, move SL to entry + 2% (closes the gap between +3% breakeven and +7.5% trail activation).

**Files:**
- [ ] `src/execution/position_manager.py:91` — extend `PROFIT_LOCK_PARAMS`

**Status:** [ ]

### F18-critical — Silent failure fixes (sizing-critical only)

**Files:**
- [ ] `src/api/routers/account.py:1594, 1618` — equity fetch fallback changed from `return 0.0` to `raise`
- [ ] `src/core/monitoring_service.py:221, 236` — market-hours check flipped from fail-open to fail-closed with retry

**Status:** [ ]

---

## Batch 4 — Signal quality

**Deploy window:** After Batches 1-2 stable 3-5 days. Needs clean data + reliable exec metrics.

### F01/F12 Phase 2 — WF validation tightening (no cliff)

- Remove `test-dominant` bypass path
- Remove `excellent OOS` bypass path
- Add consistency gate: `(test_sharpe - train_sharpe) <= 1.5`
- Keep `min_sharpe = 1.0`
- Keep Pass-2 relaxed fallback (tighten to `train>0.3 AND test>0.5`)
- NO force-retirement of existing book

**Files:**
- [ ] `src/strategy/strategy_proposer.py:1635-1651`

**Status:** [ ]

### F05 — Triple EMA fix (named placeholders + hybrid substitution)

- `{fast_period}`, `{mid_period}`, `{slow_period}` in affected templates
- Hybrid substitution: `format_map` first, regex fallback
- Advisory startup validator (WARNING, not blocking)
- Audit script `scripts/diagnostics/audit_template_conditions.py`

**Files:**
- [ ] `src/strategy/strategy_templates.py`
- [ ] `src/strategy/strategy_proposer.py`
- [ ] `scripts/diagnostics/audit_template_conditions.py` (new)

**Status:** [ ]

### F07 — MC Bootstrap annualization window

**Change:** Use actual `test_days` per timeframe (1h=90, 4h=120, 1d=240) instead of hardcoded 180.

**Files:**
- [ ] `src/strategy/strategy_proposer.py:1567`

**Status:** [ ]

### F08 — Fast-feedback revision

- `LOOKBACK_DAYS = 10` (was 5), `MIN_TRADES = 4` (was 3)
- Suppress on WR < 35% OR profit_factor < 0.7
- Flag templates with 0 closed but significant open unrealized losses

**Files:**
- [ ] `src/analytics/trade_journal.py:1499-1580`
- [ ] `src/strategy/autonomous_strategy_manager.py:1253-1272`

**Status:** [ ]

---

## Batch 5 — Alpha + polish

### F06 — MQS persistence fix

**Investigation scope:**
- `_save_hourly_equity_snapshot` wraps MQS computation in `except: pass` (found during Batch 1 deploy)
- Root cause to identify: why is `MarketStatisticsAnalyzer.get_market_quality_score()` raising silently?
- Check whether MQS is an actual live input to sizing or dead code

**Then:** fix or remove accordingly. May need backfill from SPY+VIX history already in `historical_price_cache`.

**Status:** [ ]

### F16 — Asset-class-weighted proposal quotas

Multiply per-class proposal count by WR-driven weight refreshed every N cycles.

**Status:** [ ]

### F17 — Remove min_short hard enforcement, monitor as target

**Status:** [ ]

### F18-rest — `logger.exception` on silent defaults

Targets:
- `src/api/etoro_client.py:317, 326`
- `src/llm/llm_service.py:1071`
- `src/strategy/market_analyzer.py:776`
- `src/data/news_sentiment_provider.py:189, 284`

**Status:** [ ]

### F20 — FRED retry wrapper with exponential backoff

**Status:** [ ]

### F24 — `proposed` counter: wire or remove

**Status:** [ ]

### F25 — Overview chart panel rewrite (L effort — defer design doc first)

**Status:** [ ]

---

## Deferred (future sessions)

### F01/F12 Phase 3 — Calibrate min_sharpe from live data

Trigger: 2-4 weeks of clean runs after Batch 4 deploy.

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

Use `live_sharpe` distribution to set new `min_sharpe` floor keeping expected forward Sharpe >= 0.5.

**Status:** [!] Deferred — scheduled post-Batch-4-stable.

### F14 — Yahoo forex/SPY fallback

Re-audit after F02 deploys. If "possibly delisted" errors persist, design per-symbol fallback.

**Status:** [!] Deferred — depends on F02 outcome.

### F11 full — Chandelier / percentage continuous trail

Alpha optimisation after F11-lite shows whether the ratchet gap was a meaningful leak.

**Status:** [!] Deferred.

---

## Batch 1 Verification Queries

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
ssh ... 'grep "freshness-sla" /home/ubuntu/alphacent/logs/alphacent.log | tail -20'
# Expected: some skips on stale symbols; most symbols pass

# 4. Signals still firing on fresh data
ssh ... 'tail -30 /home/ubuntu/alphacent/logs/cycles/cycle_history.log'
# Expected: normal signal generation continues
```

---

## Session Log

### Session 1 — 2026-05-01

- Completed full audit (`AUDIT_REPORT_2026-05-01.md`)
- Reviewed top-5 findings under trading-PoV lens
- Reviewed remaining findings, produced final fix list with batch sequencing
- Created this tracker
- **Batch 1 deployed 10:02 UTC:** F02 A/B/C + F09 (DST fix + freshness SLA).  
  - 297 daily + 295 hourly symbols synced in 89.7s, 0 errors
  - 196 stale pairs correctly blocked from signal gen
  - NVDA/AAPL/GS/SPY/QQQ 1h all fresh to 10:00 UTC
- **Quick-wins deployed 10:19 UTC:** F13 (dead config removed), F15 (BTC Lead-Lag template + strategy retired), F19 (pool_pre_ping on), F21 (79,785 phantom rows deleted), F22 (errors.log rotated), plus docs refresh to eliminate documentation-vs-code drift
- Service healthy, errors.log stays at 0 bytes post-restart
- Commits: `c1f7761` (Batch 1), pending (quick-wins)

**Next actions:**
1. Monitor 20:00 UTC daily sync for Batch 1 Part A full verification
2. Monitor 01:47 UTC tomorrow for DST-boundary-adjacent overnight sync
3. After 24-48h clean window on Batch 1, start Batch 2 (execution observability)

[continue log as work progresses]
