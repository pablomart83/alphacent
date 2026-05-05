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

## Current System State (May 4, 2026, ~21:30 UTC, post FMP-timezone + conviction-persist deploy)

- **Equity:** ~$474K
- **Open positions:** 69
- **Active strategies:** ~54 DEMO + BACKTESTED combined
- **Directional split:** ~80% LONG / ~6% SHORT
- **Market regime (equity):** `TRENDING_UP_STRONG` (92% confidence)
- **Market regime (crypto):** `RANGING_LOW_VOL`
- **VIX:** 17
- **Mode:** eToro DEMO
- **Scheduled cycles:** daily 15:15 UTC + weekdays 19:00 UTC

**Health:**
- errors.log: 0 new entries since 21:25 UTC restart. Pre-existing: morning VWAP_None (known P1), eToro 404 cancellations (user-side), FRED 500 (third-party)
- warnings.log: clean. Startup self-checks firing (template_name 25.6%, conviction_score 0.1% expected to climb post-fix)
- MQS: 85/100 "high" persisting
- Cycle activation rate: 2-4 per cycle when post-fix data is clean; one 0-activation cycle observed at 20:29 caught by ex-post 730d gate (working as designed)
- Unified funnel: full rejection taxonomy populated; 89-345 filter rejections per cycle visible with per-row conviction breakdown
- Market-hours primitive: singleton, symbol-aware, 24/5 compliant (Sun 20:05 ET → Fri 16:00 ET)
- FMP 1h ingestion: **fixed today.** 275 of 277 non-crypto symbols within 1h of current bar (was 141 stuck). Real UTC-stamped OHLCV across universe.
- **Known orphan positions (P0 next session):** 7 positions in DB with `strategy_id='etoro_position'` default, 4 of them opened 2026-05-05 13:30 UTC (SOXL/SMH/TQQQ/XLK) from orders we submitted 2026-05-04 21:42-21:46 UTC, incorrectly marked CANCELLED locally when cancel_order got 404, then executed by eToro at market open. These 4 positions are currently un-managed (no TSL, no strategy linkage, no trade-journal attribution). Detailed remediation plan in the next-session MISSION block.

**Data routing matrix (unchanged from 2026-05-03 evening):**

| Asset class / interval | Primary source | Cache depth | Fallback |
|---|---|---|---|
| Crypto (6) @ 1d / 1h / 4h | **Binance** | 2.7y / 2y / 2y | — |
| US stocks + ETFs @ 1d / 1h / 4h | **FMP Starter** | 5y | Yahoo |
| Forex majors + Gold/Silver @ 1d / 1h / 4h | **FMP Starter** | 5y | Yahoo |
| US indices (SPX500/NSDQ100/DJ30) @ 1d / 1h | **FMP Starter** | 5y | Yahoo |
| US indices @ 4h | Yahoo 1h→4h resample | 180d cap | — |
| UK100, STOXX50 @ 1h | FMP | 5y | Yahoo |
| UK100, STOXX50 @ 4h | Yahoo 1h→4h resample | 180d cap | — |
| GER40, FR40 (any), OIL @ 1h, COPPER @ 1h | Yahoo | Yahoo default | — |
| OIL @ 4h, COPPER @ 4h | FMP | 5y | Yahoo |

287 non-crypto symbols fully backfilled at FMP 5y. Premium-blocked set (DAX, CAC, oil-1h, copper-1h, non-US indices at 4h) flows through Yahoo with visible engine-cap truncation logs.

---

## Session shipped 2026-05-04 late evening — P0 FMP 1h ingestion + conviction-persist fix + scorer audit

Three-sprint session reacting to two discovered P0s. The FMP ingestion bug was discovered via the per-interval-freshness display shipped this morning. Halfway through the session, a conviction-scorer audit surfaced that the scoring pipeline has no validation loop because `conviction_score` was never being persisted on closed trades.

### Sprint 1 — P0: FMP 1h ingestion stops at 11:30 UTC for 141 symbols

Discovered 2026-05-04 ~17:00 UTC. 141 of 287 FMP-served US stocks stuck at `2026-05-04 11:30:00 UTC` while 144 others looked fresh at 16:00-17:00 UTC. Cross-tab by active-strategy coverage: all 143 active symbols fresh, 155 inactive symbols stale. Perfect split.

Three stacked bugs, each hiding inside the next:

1. **FMP `/stable/historical-chart/1hour` returns timestamps in US/Eastern, not UTC.** Empirically verified across stocks (CCI, AAPL), forex (EURUSD), crypto (BTCUSD), commodities (GOLD). Code stored them as naive and treated them as UTC, systematically under-reporting bar age by 4-5h. The `_gap_h < 1.5` short-circuit skipped real-5.5h-stale bars as fresh.

2. **The 1h staleness gate only queued active-strategy symbols** via `(is_always_on OR is_active)`. Inactive non-crypto symbols (stocks with no DEMO/LIVE/BACKTESTED strategy targeting them) never got refreshed between full syncs. 4h already iterated over all non-crypto; 1h was the outlier.

3. **`_quick_price_update` wrote synthetic single-tick bars (O=H=L=C, V=0, tagged FMP)** to `historical_price_cache` every 10 min for active symbols. Those "fresh" active symbols had real-looking freshness but their OHLC was fake — any Keltner/Donchian/BB/RSI signal computed on those bars was reading synthetic values. Explains TSLA-style late-cycle false breakouts over recent weeks.

**Fixes:**
- `src/api/fmp_ohlc.py` `_parse_bars`: convert intraday timestamps from naive ET to naive UTC at the parser boundary via `pytz.timezone("America/New_York").localize(ts, is_dst=None).astimezone(UTC)`. Single source of truth for FMP timezone downstream. EOD (date-only) preserved as midnight-naive.
- `src/core/monitoring_service.py` `_sync_price_data` 1h staleness gate: drop the `and (is_always_on or is_active)` condition. Every stale non-crypto symbol gets refreshed (287 syms × 1 req/hour easily fits FMP Starter's 300/min budget).
- `src/core/monitoring_service.py` `_quick_price_update`: remove DB writes of synthetic bars. Keep in-memory `hist_cache` update only (signal-gen reads current live price from the last in-memory bar). Real OHLC stays real.
- `src/data/market_data_manager.py`: update stale log line that claimed `"Binance primary for crypto, Yahoo for the rest"` to reflect the May-3 FMP routing.

**Cleanup + re-backfill** (`scripts/purge_and_rebackfill_fmp_intraday.py`):
- Phase 1: purged 5,270 synthetic placeholder bars (O=H=L=C, V=0, any interval, any source).
- Phase 2: purged 1,907,799 FMP-sourced 1h/4h bars (wrong-timezone convention).
- Phase 3: rebackfilled 578 (symbol, interval) combos via the fixed adapter. Result: 2,650,953 new 1h FMP bars + 758,478 new 4h FMP bars, all UTC-stamped.

**Verification post-deploy:**
- Histogram: 275 of 277 non-crypto symbols within 1h of current bar (was 141 stuck). 2 legitimate outliers (foreign listings premium-blocked).
- CCI 19:30 UTC real OHLC: O=89.46 H=89.87 L=89.4 C=89.76 V=190,752. Pre-fix: stuck since 11:30.
- AAPL 17:30 UTC real OHLC: H=277.4 L=276.675 V=2,435,436. Pre-fix: O=H=L=C=276.78 V=0 (synthetic).
- errors.log clean post-restart.

### Sprint 2 — Conviction-scorer audit (hedge-fund-style P&L validation)

User asked: "Make sure our conviction scorer is fair and follows top hedge-fund practice. Are we leaving money on the table?"

Methodology: walk the 1,215-line scorer component by component, measure live distribution of scores across 47k recent signals, correlate with realized P&L via retroactive join on conviction_score_logs × trade_journal.

**Key findings:**

- **The score is NOT monotonic in P&L over the last 10 days** (549 LONG trades matched):
  - <60 bucket: 173 trades, −$75 avg, −$12.9K total
  - 60-65: 233 trades, +$3 avg, +$0.7K total (BEST)
  - 65-70: 143 trades, **−$184 avg, −$26.3K total (WORST despite above-threshold)**
- 73% win rate in the 65-70 bucket with negative avg P&L means winners are tiny and losers are catastrophic — classic "pick up pennies in front of a steamroller" signature. The scorer is actively promoting bad setups.
- **Distribution is compressed.** 97% of all 47k signals last week score between 55 and 70. 58% cluster at 60-65, within ±5 of the 65 threshold. A well-calibrated hedge-fund conviction score needs ~3x more dynamic range.
- **Several components are near-constants.** `signal_quality` is 20/25 for most DSL signals (floor clamped to 8 pts); `regime_fit` is saturated at 20/20 in the current trending_up_strong regime; `asset_tradability` clusters at 13-14 for ~60% of the universe. Effectively only WF_edge and fundamentals_direction drive real variance.
- **Correlated components double-count.** Regime_fit (20 pts) measures what WF already validated — strategies that passed WF in the current regime already have regime validation baked in.
- **Static FMP factor proxies** — beta, PE, revenue_growth are point-in-time snapshots. Crypto/forex get 0 points here. Real factor exposure requires trailing realized sigma, ADV, funding rates.
- **Arbitrary binary thresholds** in the fundamental-quality component. Continuous logistic scaling would be cleaner.

**The validation loop was broken.** `trade_journal.conviction_score` column was NULL on every closed trade over the last 10 days. Without this, we couldn't answer "is conviction_score predictive of P&L?" — the retroactive join via `conviction_score_logs` was the only way we got the 549 observations above.

### Sprint 3 — P0: Conviction-score persistence fix (shipped this session)

Same class of bug as yesterday's `template_name` fix — the ingestion/persist write path was broken for a specific metadata field. 

**Root cause:** three `autonomous_signal` backfill paths (where positions get trade_journal entries retroactively from force-closes or sync-discovery) only populated `template_name`, not the full signal-time context:
- `src/core/order_monitor.py` — sync-discovered position backfill
- `src/strategy/portfolio_manager.py` — strategy-retirement force-close
- `src/core/monitoring_service.py` — pending-closure force-close

Verified via DB: 228 closed trades in the last 10 days, 0 with `conviction_score` populated, even though `order.order_metadata` DOES carry `conviction_score` (plus `market_regime`, `ml_confidence`, `fundamental_data`) for ~20% of rows. The primary fill path (`order_monitor.check_submitted_orders`) already propagates these correctly. The three backfill paths were incomplete.

**Fix:** each backfill path now recovers signal-time context from the matching order via `(strategy_id, symbol, submitted_at within ±10min)`. Spreads `conviction_score`, `market_regime`, `ml_confidence`, `fundamental_data` into the `log_entry` call. Preserves `template_name` from strategy-row lookup (previously working).

Added a startup self-check mirroring the template_name guard — `src/api/app.py` emits a WARNING if 0 of the last 1000 closed trades carry `conviction_score`. Post-deploy: `Startup self-check: 1 of last 910 closed trades carry conviction_score (0.1%)` — expected to climb to 70-80% within 48h as new trades flow through the fix.

**Files changed this sprint:**
- `src/core/order_monitor.py` — backfill path enrichment + `Any` import
- `src/strategy/portfolio_manager.py` — backfill path enrichment + `Any` import  
- `src/core/monitoring_service.py` — backfill path enrichment + `Any` import
- `src/api/app.py` — startup self-check for conviction_score column

### Noted but deferred to next session (after 2-3 weeks of data collection)

The conviction-scorer audit surfaced 6 actionable items, ranked by ROI:

1. ✅ **SHIPPED today**: persist `conviction_score` on trade_journal (enable validation loop)
2. **Build score-vs-P&L monitor** — daily cron grouping trades by bucket, flagging monotonicity violations and negative-EV buckets. ~2h work, NOW that the write path is armed.
3. **Regression-fit component weights on live P&L** — our 549 matched trades are marginal for 9 components (~3 weeks to reach 2000+ trades with regime mix). Planned after 3-4 weeks of clean data.
4. **Collapse signal_quality into WF_edge** — signal_quality's 25-pt range collapses to ~4-5 pts of variance for 85% of DSL signals (floor-clamped). Structural dead weight.
5. **Make asset_tradability dynamic** — replace hardcoded tiers with ADV/volume-based scaling. Static bucketing gives ~5 pts of dynamic range across 287 symbols.
6. **Two-factor conviction gate** — `score ≥ 65 OR (wf_edge_normalized ≥ 0.8 AND score ≥ 60)` — admits high-WF-edge boundary cases (MU × Keltner 64.6, UNH × 4H ADX 64.6, ROST × 4H VWAP 64.8) without opening door to weak-WF broad-market noise.

Estimated incremental P&L from items 2-6 (once backed by data): $10-20K/month at current capital base. Currently leaking ~$26K/10 days from the 65-70 bucket alone.

### Files changed across the three sprints

- `src/api/fmp_ohlc.py` — ET→UTC parser-boundary conversion
- `src/core/monitoring_service.py` — is_active gate drop + synthetic-bar DB-write removal + conviction backfill path + Any import
- `src/data/market_data_manager.py` — stale routing log line
- `src/core/order_monitor.py` — conviction backfill path + Any import
- `src/strategy/portfolio_manager.py` — conviction backfill path + Any import
- `src/api/app.py` — conviction_score startup self-check
- NEW `scripts/purge_and_rebackfill_fmp_intraday.py` — one-shot cleanup + 5y rebackfill
- NEW `scripts/analysis/conviction_pnl_analysis.py` — retroactive conviction-vs-P&L validator

---

## Session shipped 2026-05-04 evening — 24/5 readiness + MarketHoursManager rewrite + filter-rejection funnel

Three fixes in one session sprint, all solving real observability or trader-reality gaps.

### Sprint 1 — 24/5 readiness (MarketHoursManager rewrite)

eToro announced 24/5 trading for all S&P 500 + Nasdaq 100 stocks on 2025-11-17 with a Sun 20:05 ET → Fri 16:00 ET window. Our system still gated orders on NYSE regular hours (9:30-16:00 ET) or the older ad-hoc 04:00-20:00 ET window scattered across six call sites. 4H strategies closing at 00:00/04:00/20:00 ET had three of six daily closes fall outside the gate, silently deferring orders.

Root cause: `MarketHoursManager.is_market_open(asset_class, check_time, symbol)` accepted a `symbol` parameter but ignored it. `AssetClass` enum only defined `STOCK/ETF/CRYPTOCURRENCY` while callers passed `FOREX/COMMODITY/INDEX` — those fell through a try/except and silently defaulted to `STOCK` with NYSE regular hours. Forex orders and commodity orders were being time-gated by NYSE rules, wrong for both.

**Fix:** rewrite `src/data/market_hours_manager.py` around 6 schedule regimes selected by `(asset_class, symbol)`:
- `CRYPTO_24_7` — always open
- `ETORO_24_5` — Sun 20:05 → Fri 16:00 ET, holidays closed (default for STOCK/ETF)
- `US_EXTENDED` — Mon-Fri 04:00-20:00 ET (opt-out for non-24/5 stocks)
- `FOREX_24_5` — Sun 17:00 → Fri 17:00 ET, continuous
- `US_INDEX_FUTURES` — Sun 18:00 → Fri 17:00 ET with 17:00-18:00 daily break (SPX500/NSDQ100/DJ30)
- `COMMODITY_FUTURES` — same CME schedule (GOLD/SILVER/OIL/COPPER)
- `NON_US_INDEX` — local exchange hours (UK100/GER40/FR40/STOXX50 → 02:00-11:30 ET)

`AssetClass` enum extended to include FOREX/INDEX/COMMODITY as first-class values. `SymbolRegistry.get_market_schedule(symbol)` added for per-symbol overrides in `config/symbols.yaml` (not needed today — every stock in our universe is S&P/NDX-eligible, the asset-class default is correct).

**Decision I didn't take:** no static 24/5 symbol registry. Every stock/ETF in our DEMO universe is a curated US large-cap by construction; the asset-class default is always correct. If we ever add a non-24/5 name, it gets `market_schedule: us_extended` in symbols.yaml — one line. Zero-maintenance by default.

**Eliminated ad-hoc checks at 7 call sites** (all replaced with `is_market_open(asset_class, symbol=...)`):
- `src/strategy/strategy_engine.py:5024`
- `src/core/monitoring_service.py:206` + `:240`
- `src/core/order_monitor.py:2052`
- `src/core/trading_scheduler.py:318`
- `src/api/routers/control.py:1751`
- `src/api/routers/data_management.py:385`
- `src/api/app.py:440`
- Plus fixed `src/execution/order_executor.py:408` and `:1722` to pass `symbol=`

**Pre-deploy verification:** `scripts/verify_market_hours_24_5.py` truth-table test (30 cases across all 6 regimes + holiday + early-close): 30/30 pass.

**Post-deploy live verification:** `scripts/verify_24_5_backtested.py` walks every BACKTESTED + DEMO strategy in the library (172 total), classifies primary symbols, and calls `is_market_open` at 6 representative ET times (regular hours, post-market, overnight, pre-market, Saturday, Sunday reopen). Result: **116/116 BACKTESTED and 56/56 DEMO strategies open during all four 24/5 windows** (regular, post-market, overnight, pre-market). Saturday shows the correct closure for everything except crypto (5 crypto-primary BACKTESTED strategies). **Every existing BACKTESTED strategy benefits from 24/5 identically to DEMO strategies** — same code path, no status-specific branch.

### Sprint 2 — MarketHoursManager singleton (log-spam regression fix)

Post-deploy, the TSL cycle iterating 75 positions instantiated `MarketHoursManager()` 75 times and each init logged `Initialized MarketHoursManager (symbol-aware, 24/5 capable)` at INFO. Multiplied across monitoring_service, trading_scheduler, order_executor, order_monitor, strategy_engine — a same-second flood of 75+ identical lines in alphacent.log.

**Fix:** module-level singleton via `get_market_hours_manager()` in `src/data/market_hours_manager.py`. Init log moved to DEBUG on class construction + one INFO line from the singleton getter on first call. All 10 call sites across 7 files migrated from `MarketHoursManager()` → `get_market_hours_manager()`. Verified post-restart: exactly 1 "singleton created" log line; 0 per-call init lines.

The log spam was the visible symptom; the architectural fix (singleton for a stateless resource) is the proper solution.

### Sprint 3 — Filter-rejection funnel writes (observability gap)

Cycle footer said `[SIGNALS] 2 generated → 0 coordinated → 2 rejected` but `signal_decisions` showed 0 rows for that cycle. Conviction + frequency + ML + fundamental + low-confidence filter rejections in `strategy_engine.generate_signals` were only logging to alphacent.log; the funnel writer at the bottom (`record_batch` for `signal_emitted`) only fired when `filtered_signals` was non-empty. When every signal was filtered, the funnel stayed silent.

**Fix:** helper `_log_filter_rejection(reason_text, extra_md)` closure inside the filter loop. Writes one `signal_decisions` row per rejection with `stage=signal_emitted`, `decision=rejected`, and a `filter:<kind>` reason prefix (`filter:conviction`, `filter:frequency`, `filter:ml`, `filter:fundamental`, `filter:low_confidence`). Structured `decision_metadata` carries the conviction score, threshold, breakdown, ML confidence, etc. Every write wrapped in try/except — analytics failures never break signal gen.

**Immediate payoff in observability:** post-deploy the first batch sweep captured 89 filter rejections with precise score breakdowns. Distribution analysis (see "Observation — conviction floor clipping" below) surfaced a real design question that was invisible before.

**Observation — conviction floor clipping (surfaced by the new visibility)**

Of the 89 filter rejections captured, the scores clustered tight against the 65 threshold:
- Mean 61.0, max 64.8, min 45.5
- 18 rejections (20%) scored 64-65 — within 1 point of the floor
- 37 rejections (42%) scored ≥62 — within 3 points
- Only 2 rejections scored below 55

Repeated rejections for the same (template, symbol) pair: XLK × Keltner Channel Breakout 9 times at avg 62.1, XLK × 4H EMA Ribbon 4 times, SPY × 4H EMA Ribbon 2 times, TQQQ × 4H EMA Ribbon 3 times. Broad-market ETFs in a trending_up_strong regime repeatedly scoring just under the 65 floor.

**Trader's read:** the system is correctly rejecting low-edge broad-market entries (wf_edge 23-27/40 for those) even though regime_fit is maxed. The floor is doing its job post-TSLA audit. BUT — edge cases like MU × Keltner Breakout at 64.6, UNH × 4H ADX Trend Swing at 64.6, ROST × 4H VWAP at 64.8 suggest the binary threshold is occasionally costing us real single-stock edge. This is a design question, not an emergency — kicked to P1 next session (see Open Items).

### Files changed this sprint

- `src/data/market_hours_manager.py` — full rewrite (6 regimes + singleton)
- `src/core/symbol_registry.py` — `get_market_schedule()` added
- `src/strategy/strategy_engine.py` — ad-hoc check removed + filter-rejection funnel writes
- `src/core/monitoring_service.py` — 2 ad-hoc sites refactored + singleton switch
- `src/core/order_monitor.py` — ad-hoc site refactored + singleton switch
- `src/core/trading_scheduler.py` — ad-hoc check removed + singleton switch (3 sites)
- `src/execution/order_executor.py` — pass `symbol=` to is_market_open, singleton
- `src/api/routers/control.py` — `market_hours` gate rewritten to use primitive
- `src/api/routers/data_management.py` — market-open display string via primitive
- `src/api/routers/account.py` — singleton switch
- `src/api/routers/orders.py` — singleton switch
- `src/api/app.py` — trading-gates endpoint rewritten to use primitive

New scripts:
- `scripts/verify_market_hours_24_5.py` — 30-case boundary truth table
- `scripts/verify_24_5_backtested.py` — per-strategy 24/5 eligibility matrix
- `scripts/check_market_hours_live.py` — quick live-state debug

**Verification:** errors.log clean across all three restarts. Post-singleton restart the 89 filter rejections reconciled exactly with the raw `Batch signal generation: 10 signals from 151 strategies (89 rejected)` log line. Cycle footer and funnel now agree.

---

## Session shipped 2026-05-04 afternoon — P0 loser-pair penalty data integrity

Single-sprint fix for the silent-failure rail discovered during the morning observability verification. The 2026-05-02 TSLA audit had added a per-pair sizing penalty (`risk_manager.calculate_position_size` Step 10b) that halves position size when a `(template, symbol)` pair has ≥3 closed trades with net-negative P&L. The lookup keys on `trade_journal.trade_metadata->>'template_name'` — a key that the trade-journal write path had **never populated**. Zero of 892 closed trades carried it, so the penalty never fired. Known losing combos got sized at full budget every time.

### Root cause

No single write site was to blame — there were five paths into `trade_journal.log_entry` and every one of them omitted `template_name`:

- `order_monitor.check_submitted_orders` (the async fill path, main production path) spread `order.order_metadata` keys into the journal metadata. The spread was correct; `template_name` simply wasn't in `order.order_metadata` because it wasn't in `signal.metadata` to begin with.
- `order_executor._handle_buy_fill` / `_handle_sell_fill` (synchronous fill) ignored order metadata.
- `portfolio_manager._close_positions_for_retirement` and `monitoring_service` pending-closure paths (defensive "make sure an entry row exists" backfill) passed no metadata at all.
- `api/routers/orders.py` manual-order submission had no strategy context in signal metadata.

Deeper: the DSL signal path in `strategy_engine._generate_signal_for_symbol` built metadata with `strategy_name` but not `template_name`. Alpha Edge signals used `template_type` (a different key). There was no canonical write-site that guaranteed every signal carried its template identifier.

### Fix

Single architectural write-site in `strategy_engine.generate_signals` — right after a signal is returned from either the DSL or Alpha Edge engine, before conviction/frequency/ML filtering and before risk validation. Source: `strategy.metadata['template_name']` (populated at proposal time); fallback: `strategy.name`. This single line guarantees every signal from every current and future engine carries `template_name` into downstream stages. Since `trading_scheduler` already copies `signal.metadata → order.order_metadata` at submit and `order_monitor` spreads `order.order_metadata` into the journal write, the full chain is repaired with one enrichment.

**Secondary fixes for defensive paths** (where signal metadata isn't available — force-close, sync-created position backfill, manual order submission): each recovers `template_name` via a small DB lookup on the strategy row. Pairs-trading hedge-leg order creation in `trading_scheduler` now preserves `order_metadata` too (it was dropping it previously). Files touched:

- `src/strategy/strategy_engine.py` — canonical enrichment after signal emission
- `src/core/trading_scheduler.py` — hedge-leg `order_metadata` preservation
- `src/strategy/portfolio_manager.py` — strategy-retired force-close lookup
- `src/core/monitoring_service.py` — pending-closure force-close lookup
- `src/core/order_monitor.py` — sync-created-position backfill lookup
- `src/api/routers/orders.py` — manual-order strategy lookup (+ `Any` import)
- `src/api/app.py` — startup self-check: `WARNING` if 0 of last-1000 closed trades carry `template_name`, so a future regression surfaces within one restart

### Backfill

Historical rows: 216 of 892 closed trades recovered via `strategies.strategy_metadata->>'template_name'` (single SQL transaction, `scripts/backfill_trade_journal_template_name.sql`). 676 rows unrecoverable — their originating strategies have been retired and deleted from the `strategies` table, and `strategy_proposals` coverage is minimal for older trades (the proposals table is newer than most of the historical journal). Backfilled rows tagged `trade_metadata.backfill_source = 'legacy_backfill_2026_05_05'` + `backfill_template_src = 'strategies'` for auditability.

### Verification

Six real `(template, symbol)` loser pairs became eligible for the penalty after the backfill:

| symbol | template | trades | net P&L |
|---|---|---|---|
| SCCO | EMA Ribbon Expansion Long | 3 | -$304 |
| HIMS | 4H VWAP Trend Continuation | 4 | -$225 |
| GEV | 4H EMA Ribbon Trend Long | 5 | -$220 |
| GS | ATR Dynamic Trend Follow | 6 | -$122 |
| PYPL | 4H ADX Trend Swing | 4 | -$91 |
| BTC | EMA Pullback Momentum | 4 | -$7 |

`scripts/verify_loser_pair_penalty.py` invokes the live `RiskManager._get_symbol_template_loser_stats` against production DB: all 6 return `would_fire_penalty=True`; control target returns `trades=0`. Standing verification tool.

Live-fire cycle at 12:05 UTC post-deploy: 400 candidates → 15/19 WF pass (78.9%) → 2 activated (Keltner TSM LONG S=1.78, 4H EMA Ribbon SILVER LONG S=1.48). Funnel rows: 45 `signal_emitted`, 29 `gate_blocked`, 2 `order_submitted` — **every row carries `template_name`**. GS × `ATR Dynamic Trend Follow` entry signal surfaced and was blocked at the `Symbol limit` gate (upstream of sizing), so the `Loser penalty:` log-line didn't emit this cycle — but the path is armed and will fire the moment a loser-pair signal clears the position-limit check.

errors.log: 0 entries post-restart. warnings.log: clean. Startup self-check emitted the expected `STARTUP SELF-CHECK FAILED: 0 of last 892 closed trades carry trade_metadata.template_name` WARNING on first boot after the fix; will flip to INFO on the next restart once ≥50 post-fix trades have cleared.

### Ordering note

The per-strategy symbol-count cap (`Symbol limit: N existing positions in SYM`) runs BEFORE sizing. If a symbol is at its per-strategy cap, the signal dies there regardless of whether the loser-pair penalty would also have caught it. That's correct — position limits are hard gates, the sizing penalty is a soft de-risker. No code change needed; just documenting the priority for future debugging.

---

## Session shipped 2026-05-04 — cycle-health audit + observability unification

Four sprints across a single-day session. Mission: "I just ran a few autonomous cycles. Check logs, results, rejections, calculations, data fetching, WF window, everything." What started as a check-in surfaced a chain of silent failures in activation, sizing, and observability.

### Sprint 1 — Activation pipeline (morning, commit S1)

Autonomous cycles this morning were producing **0 activations** despite 13-20 WF-passed candidates per cycle. Walked the funnel end-to-end and found three root causes.

1. **`backtest_strategy()` silent strategy mutation.** Root cause of the 0 activations. `strategy_engine.backtest_strategy()` had always silently run `strategy.backtest_results = results` at the end of every call — a side effect the signature didn't advertise. This was fine until Sprint 5 F2 (2026-05-02) added a 730d ex-post sanity backtest *after* WF passes. The ex-post call ignored its return value but its side effect overwrote `strategy.backtest_results` with the 730d full-period results (mostly the training-leg flavour). Activation then compared that Sharpe to the threshold instead of the WF test Sharpe that had just proven generalization. Pattern: WF test_S=2.20 → overwritten by 730d S=0.97 → rejected as `Sharpe 0.97 < 1.0`. Happened on every strategy whose train Sharpe was mediocre but test Sharpe was strong — which is the most valuable signal pattern. **Fix**: `backtest_strategy()` is now a pure function; the 2 callers that want to persist results (CLI bootstrap, manual-backtest API endpoint) do so explicitly. Verified live: MU activated at S=2.20 (WF test), CAT at S=2.46, SHOP SHORT at S=3.33.

2. **DSL `VWAP()` codegen produced `VWAP_None` keys.** ~1,224 errors.log entries in 24h. Lark grammar rule `INDICATOR_NAME "(" [arg ("," arg)*] ")"` materializes an empty optional group as a single `None` child in the Tree. `_handle_indicator_with_params` then called `_extract_arg_value(None)` which returned `None`, and `INDICATOR_MAPPING['VWAP']([None])` produced `VWAP_None`. Every template using `VWAP()` silently dropped all conditions in codegen → WF reported 0 trades → strategy looked untradable. **Fix**: filter `None` children at the arg-extraction loop. Clean at the primitive level, applies to any future indicator with optional args.

3. **Symbol concentration cap ignored pending unfilled orders.** Detected live: 2× $17.5K URI BUY orders from different strategies (CAT LONG watchlist hit + NXPI LONG watchlist hit) submitted 9 minutes apart pre-market. Each sizer checked `positions` (filled only), saw $0 existing URI exposure, and sized to the full 5% budget. When market opened both would have filled at 7.3% of equity — cap breached. **Fix**: new `_get_pending_entry_exposure` helper queries `orders` for PENDING / PARTIALLY_FILLED + order_action=entry rows. Both cap-check sites (`calculate_position_size` Step 6 + `check_symbol_concentration`) include pending exposure. Safe on fail: DB error returns (0, set(), 0) so a broken query degrades to the previous positions-only behaviour, never crashes the risk path. Also fixed the `backtest_strategy` side effect in the same sprint because they compounded.

### Sprint 2 — P0 batch: observability reasons + footer honesty + eToro 404 (commit S2)

Three independent observability bugs that compounded to hide what the system was doing.

4. **In-risk-manager rejections wrote useless reasons to the funnel.** `risk_manager.calculate_position_size` has 8 early-zero paths (symbol cap, portfolio heat, drawdown sizing, below-min-with-penalty, insufficient balance, etc.). All of them fed `ValidationResult(reason="Calculated position size is zero or negative")` to the decision-log writer. Ten rejections in a row looked like ten copies of the same vague string. **Fix**: new `self._last_sizing_reason` sentinel is populated at every early-zero path with a specific string (`symbol_cap_exhausted (CAT at $21675/$24050, $17554 pending)`, `below_min_with_penalty (size=$2260 < $5000, penalty_applied=True)`, etc.). `validate_signal` reads it and threads it into the ValidationResult. The existing `trading_scheduler._log_signal_decision` writer persists it. Grepping `risk.log` to understand why a signal died is no longer necessary.

5. **Cycle footer lied about activations.** `[ACTIVATION] N activated` inline line vs `Activated: 0` footer. The footer received `promoted_to_demo` (count of strategies that got a first fill this cycle) while the inline heading reported `strategies_activated` (count that passed activation criteria → BACKTESTED). In any cycle where signals defer (market-closed, gate-blocked, pending), the two diverge and the footer prints 0 despite 4-6 successful activations. **Fix**: footer reports `strategies_activated` directly, with optional `(→ M promoted to DEMO)` annotation when M ≠ N. Matches inline headline one-for-one. Also exposed `strategies_promoted_to_demo` as a distinct stats field for callers that care about live-fill-through vs library-graduation.

6. **eToro 404 on cancelled orders produced infinite error spam.** When a user cancels an order in the eToro UI, the next `order_monitor.check_submitted_orders` poll hits the order-status endpoint, gets 404, logs ERROR, and retries every 30s forever. Observed live: URI order 348195217 cancelled by user → 100+ `Failed to get order status: API request failed: 404` ERROR lines in errors.log across 30 min. **Fix**: new typed exception `EToroOrderNotFoundError(EToroAPIError)` raised specifically on 404 for `/orders/*` and `/positions/*` endpoints. `_get_order_status_cached` catches it distinctly and returns a `{"_not_found": True}` sentinel (cached for TTL so we don't re-query). `check_submitted_orders` sees the sentinel → transitions the local order row to CANCELLED and stops polling. Clean convergence within 30s of a user-side cancel.

### Sprint 3 — Observability unification (commit S3)

Discovered during P0-1 verification: the system had **TWO parallel decision tables** that didn't know about each other.

- `signal_decisions` (SignalDecisionORM) — the 2026-05-02 "audit log of every template × symbol × decision" funnel. Written by proposer, walk-forward, MC bootstrap, cross-validation, activation gate, ex-post veto, order executor.
- `signal_decision_log` (SignalDecisionLogORM) — legacy. Written ONLY by `trading_scheduler._log_signal_decision` at coordination and validation time. Not connected to the funnel.

Result: coordinator dedup rejections (same-template duplicates, symbol limits) and risk-manager rejections (the ones Sprint 2 just fixed to carry useful reasons) were invisible to the funnel. The UI was reading 3-4 different sources and reconciling badly. Cycle Intelligence panel said `Signals: 0`, Signal Stats widget said `Total 50 Exec'd 4 Rejected 46`, top bar said `Signal 8m ago - 20 → exec`. Nothing agreed.

**Fix**: unified on `signal_decisions` as the single source of truth.
- `trading_scheduler._log_signal_decision` dual-writes: legacy table + new `gate_blocked` / `order_submitted` rows in `signal_decisions`
- `/api/signals/recent` migrated to read `SignalDecisionORM`, response schema preserved so frontend widgets work unchanged
- `/api/audit/log` and `/api/audit/trade-lifecycle/{id}` migrated identically
- Stage taxonomy documented at the top of `decision_log.py` — 10 stages split into strategy-lifecycle (proposed, wf_*, activated, rejected_act, cross_validation) and signal-lifecycle (signal_emitted, gate_blocked, order_submitted, order_filled, order_failed)
- One-time backfill: 27,424 legacy rows from last 7 days copied to unified table with `source=legacy_backfill_2026_05_04` marker so the UI stays populated seamlessly post-deploy
- `SignalDecisionLogORM` model marked `[DEPRECATED 2026-05-04]` with migration plan — dual-write retained for deprecation window, table drop scheduled for T+30d

### Cycle verification post-deploy (cycle_1777893312, 11:15 UTC)

```
[PROPOSALS]    200 candidates → 19 fresh (DSL=11, AE=8), 181 cached
[WALK-FORWARD] 12/19 passed (63.2%)
[ACTIVATION]   4 activated:
   + BB Squeeze Reversal Short Uptrend SHOP SHORT   S=3.33 wr=100% t=6
   + Keltner Channel Breakout CCJ LONG              S=2.63 wr=62%  t=8
   + 4H EMA Ribbon Trend Long C LONG                S=2.07 wr=45%  t=11
   + Strong Uptrend MACD BHP LONG MA(12/26)         S=1.53 wr=50%  t=8
[SIGNALS] 3 generated → 1 coordinated → 2 rejected
[ORDERS]  0 submitted, 0 filled
Footer: Activated: 4 (→ 0 promoted to DEMO) | Retired: 0 | Total active: 58
```

All 3 signals killed by risk rails with clear reasons in the unified funnel:
- MU: `below_min_with_penalty (size=$4845 < $5000, penalty_applied=True)` — vol-scaling penalty
- CAT: `below_min_with_penalty (size=$2260 < $5000)` — vol-scaling penalty
- TXN: `Same-template duplicate: 4H EMA Ribbon Trend Long already queued for TXN`

Funnel stage counts across last 90 min:
```
 activated        | accepted |    14
 cross_validation | rejected |     3
 gate_blocked     | rejected |    47    ← previously 0 (unified with legacy)
 order_submitted  | accepted |     2
 proposed         | accepted |  1000
 rejected_act     | rejected |    41
 signal_emitted   | emitted  |    63
 wf_rejected      | rejected |   767
 wf_validated     | accepted |    46
```

### Latent bug discovered — loser-pair penalty silently disabled (RESOLVED 2026-05-04 afternoon, see block above)

While verifying the Sprint 2 observability fix, confirmed that the loser-pair sizing penalty (added in the 2026-05-02 TSLA audit) **had never fired since it was written**. `risk_manager._get_symbol_template_loser_stats` queries `trade_journal.trade_metadata->>'template_name'` — a key the write path never populated. Zero of 891 closed trades carried it. Fixed in the afternoon sprint (see "Session shipped 2026-05-04 afternoon — P0 loser-pair penalty data integrity" above).

**Files changed today:**
- Sprint 1: `src/strategy/strategy_engine.py`, `src/strategy/bootstrap_service.py`, `src/api/routers/strategies.py`, `src/strategy/trading_dsl.py`, `src/risk/risk_manager.py`
- Sprint 2: `src/risk/risk_manager.py` (observability reasons), `src/core/cycle_logger.py`, `src/strategy/autonomous_strategy_manager.py` (footer), `src/api/etoro_client.py`, `src/core/order_monitor.py` (404 handler)
- Sprint 3: `src/core/trading_scheduler.py`, `src/api/routers/signals.py`, `src/api/routers/audit.py`, `src/models/orm.py`, `src/analytics/decision_log.py` (unification)
- DB: 27,424-row legacy→unified backfill; signal_decisions stage counts populating correctly

---

## Session shipped 2026-05-03 evening (log-hygiene audit + commodity 1h narrowing + MQS persistence)

Two commits landed this evening after the FMP-primary overhaul was observed running in production. The mission was: "run an autonomous cycle, check errors + warnings, fix what's broken." The cycle ran 400 candidates → 10 activated (healthy). The cleanup was in observability, not trading logic.

### Commit 1 — `18c3315` errors.log noise cleanup + MQS diagnostic + cycle summary clarity

Six fixes targeting errors.log flood and observability gaps:

1. **Yahoo 1h rolling-cap guard** (`market_data_manager._fetch_historical_from_yahoo_finance`). WF backtests for OIL/COPPER/GER40/FR40 1h (FMP premium-blocked) cascaded to Yahoo with `start` dates > 720d old, producing empty responses AND yfinance root-logger ERRORs that flooded errors.log (~80/hour). The rule: Yahoo 1h serves only where `start >= now - 730d`. If `start` is outside that cap, return `[]` immediately and let the DB cache fallback serve. Initial fix checked `end` which was wrong — Yahoo's cap is measured from now, not from the window's end. Corrected to check `start_age_days > 720`.
2. **Incremental-fetch skip for past-dated WF windows** (`get_historical_data`). DB-cache-first path was firing live Yahoo calls when DB was 'stale' even if the requested `end` was already a year in the past. A backtest window doesn't need live data. Now only fires incremental when `end` is within 1d of now.
3. **yfinance + urllib3 loggers pinned to WARNING** (`logging_config`). yfinance writes ERROR directly to root logger on every empty-response case. We already catch and re-log with context. Pinned to WARNING so genuine breakage still surfaces.
4. **MQS silent-except → diagnostic WARNING** (`monitoring_service._save_hourly_equity_snapshot`). Previously `except: pass`, silently leaving `equity_snapshots.market_quality_score` NULL for weeks. Now logs exception class + repr on failure. Snapshot still saves (MQS non-critical).
5. **Cycle summary shows pre-WF count** (`cycle_logger.log_proposals` + `autonomous_strategy_manager`). `[PROPOSALS] N generated` line now renders as `[PROPOSALS] 400 candidates → 28 fresh (DSL=20, AE=8), 372 cached from earlier cycles` when proposer's `_last_pre_wf_count` is available. Same format in `CYCLE COMPLETE` footer. Resolves "I asked for 400 and only 28 show up" ambiguity.
6. **FMP runtime block-set dedup + concurrent-page short-circuit** (`fmp_ohlc._mark_blocked`, `_fetch_page`). Multi-page parallel fetches for blocked symbols (RHM.DE, RR.L at 4h) produced 10-20 "runtime block-set updated" INFO lines per cycle because all 4 page workers hit 402 before any could update the set. Added check-before-add dedup and sibling-aware early-out. Also added RHM.DE and RR.L to `EXPLICIT_BLOCKED` at 1h/4h (foreign listings blocked by Starter's US-coverage clause).

**Verification:** HG/CL error count frozen at 80 post-restart (confirmed zero new yfinance ERRORs). RHM/RR.L block-set spam zero. Cycle summary shows the new format.

### Commit 2 — `4970dae` warnings.log cascade cleanup + commodity 1h narrowing

Eight fixes targeting warnings.log flood (was 55 warnings/min, ~778 per 15 min) following commit 1:

1. **Commodity 1h templates narrowed to GOLD+SILVER** (`strategy_templates`). The fundamental trader-level decision of this session. DB coverage reality:
   - GOLD, SILVER @ 1h: FMP-served, 15k+ bars, 2.5y depth. Fully WF-validateable.
   - OIL, COPPER, NATGAS @ 1h: Yahoo fallback only, ~5.5k bars, ~11 months depth. Not enough for 365/365 WF with min_trades_dsl_1h=15.
   - PLATINUM @ 1h: not even in DB.
   
   Each WF cycle fired 5 cascading warnings per OIL/COPPER strategy (~380 total per cycle): `No valid data from Yahoo` → `Refusing 275 bars as 1h` → `Data quality validation` → `Symbol has 275 bars (14% coverage)` → `Very limited data`. Narrowed `Commodity Hourly Momentum Surge Long`, `Commodity Hourly Oversold Bounce Long`, and `Commodity Hourly Spike Fade Short` from `[OIL, GOLD, SILVER, COPPER, NATGAS, PLATINUM]` → `[GOLD, SILVER]`. Template names preserved for lineage with 313 historical proposals in `strategy_proposals`. 4h/1d commodity templates unchanged — those intervals have full FMP coverage.

2. **Listing-date awareness for `limited data` warnings** (`strategy_engine._run_vectorbt_backtest`). GEV (GE Vernova IPO April 2024) has 526 1d bars = 100% of its history, but 48% of 573 expected from the backtest window. 40 warnings per cycle for a symbol we can't have more data on. Added `is_listing_limited` detection via span-coverage ≥ 85% (gap-free over the period the ticker existed). Gappy data still WARNINGs; full-since-listing gets INFO.

3. **Signal-overlap resolution demoted to INFO** (`strategy_engine`). `Detected N days with conflicting entry/exit signals. Prioritizing entries.` is working-as-designed backtest behavior in volatile regimes. Kept the log line (useful for whipsaw-tuning) but at INFO.

4. **Data quality validation severity by score** (`market_data_manager`). Cached-report validation was always WARNING when `has_warnings()=True`. A 95/100 score with 1 minor issue is healthy data. Now: score ≥ 70 = INFO, 50-69 = WARNING, < 50 = ERROR. Matches the non-cached path semantics; drops ~44 crypto-data-quality warnings per cycle.

5. **Weekend-gap adjustment for commodity + forex** (`market_data_manager._subtract_weekend_hours` + `is_data_fresh_for_signal`). Previously only applied for `stock_etf_index`. GOLD/NATGAS/SILVER 1d and USDCHF/USDCAD 4h tripped the freshness SLA every Sunday cycle with raw ages of 51h+ (Friday close + weekend). These markets close the same Fri-evening → Sun-evening hours as equities. Now all three families (stock_etf_index, commodity, forex) get the 48h weekend subtraction. Crypto stays raw (24/7).

6. **MQS on-demand MDM construction** (`monitoring_service._write_equity_snapshot`). The root cause of weeks of NULL `market_quality_score` values. The shared `MarketDataManager` singleton is registered lazily by `_sync_price_data` on first run (~55 min after boot). Snapshots firing before that hit `get_market_data_manager() → None` and silently left `_mqs_score = None`. Fix cascade:
   - If shared singleton is None, try `self._market_data` (set later in same service).
   - If that's also None, construct a transient `MarketDataManager(etoro_client, config)` on demand and register it as the singleton so all subsequent callers find it.
   - Added entry-INFO log for the hourly tick and upgraded success save log from DEBUG to INFO.
   
   Verified: `2026-05-03 23:00` hourly row went from NULL → `85.3/high` in DB after the fix landed.

7. **Invalid session demoted to INFO** (`middleware.py`). Stale browser tabs polling auth endpoints fired 13 WARNINGs per 15 min from one user. Uvicorn access log already records 401s for audit. Demoted to INFO.

8. **ASGI shutdown event-loop handled correctly** (`app.py`). `Cannot run the event loop while another loop is running` fired on every shutdown because we tried `asyncio.new_event_loop()` when an ASGI loop was already running. Now checks for running loop first and uses `create_task`; falls back to new loop only for non-ASGI shutdowns.

**Verification post-final-restart at 23:43 UTC:**
- errors.log: 0 new entries (zero yfinance ERRORs)
- warnings.log: 3 warnings in 2 min (was 55/min — **95%+ reduction**)
- 2026-05-03 23:00 hourly snapshot now has MQS=85.3 (was NULL)
- GER40 4h freshness WARNING still fires (correct — EU index genuinely stale on Sunday)

**Files changed:**
- `src/data/market_data_manager.py`, `src/core/monitoring_service.py`, `src/core/cycle_logger.py`, `src/core/logging_config.py`, `src/strategy/autonomous_strategy_manager.py`, `src/strategy/strategy_engine.py`, `src/strategy/strategy_templates.py`, `src/api/fmp_ohlc.py`, `src/api/middleware.py`, `src/api/app.py`

---

## Session shipped 2026-05-03 (FMP primary for all non-crypto intervals + per-position RPT / WF window refactor)

Five commits landed over the course of the day:

1. **`b10cb6c`** — morning cost-math triple-fix (per_symbol precedence, RPT unit mismatch, edge_ratio unit mismatch). First non-F2-bypass crypto activation: `Crypto BTC Follower 4H ETH LONG`.
2. **`bd9e3fb`** — WF window single-source-of-truth refactor. `backtest.walk_forward.asset_class_windows` + `long_horizon_templates` in yaml; `strategy_proposer._select_wf_window()` is the only Python site picking windows.
3. **`474c0e0`** — FMP Starter primary for non-crypto 1h/4h. New `src/api/fmp_ohlc.py` client, routing in `market_data_manager`, batch blocks in `monitoring_service._sync_price_data`. Widened `non_crypto_1h` and `non_crypto_4h` from 180/90 and 240/120 to 365/365.
4. **`df8a5b0`** — fix forex weekend noise (trust FMP 0-bar response, don't fall through to Yahoo which then logs `possibly delisted`).
5. **`7a425e6`** — **FMP primary for 1d too** plus 429 backoff. Closes the cross-timeframe OHLC consistency gap (Yahoo 1d adjusted-close vs FMP intraday raw-close differed 0.5-1% on the same stock/day, creating phantom indicator signals at day-boundaries). 1d uses `/historical-price-eod/full` endpoint. Parallel workers 4→2 + exponential backoff on 429 to stay inside the 300 req/min budget.

**Key per-sprint takeaways:**

### Morning — cost-math triple fix

- **`portfolio_manager.evaluate_for_activation:1307`**: `return_per_trade = total_return / total_trades` was treating a fraction-of-init_cash metric as per-position. At 10-30% position sizing that understated per-position returns by 3-10x. Extended `BacktestResults` with `avg_trade_value` + `init_cash`; RPT gate now divides raw metric by `avg_trade_value / init_cash` to get per-position return before comparison.
- **`strategy_engine._run_vectorbt_backtest`**: per-symbol cost overrides (`per_symbol.BTC`, `per_symbol.ETH`) were ignored — engine read `per_asset_class` only. Added precedence lookup `per_symbol > per_asset_class > global` at all 3 call sites.
- **`cost_model.edge_ratio`**: same unit mismatch as the RPT gate — observability-only but misleading on the Data Page. Takes optional `avg_trade_value` + `init_cash` now, scales numerator to per-position.

Verified live: BTC Follower 4H ETH flipped from rejected (`Return/trade 0.831% < 1.800%`) to activated (`rpt=7.712% per-position @ 12.0% sizing, edge_ratio=4.51`) in cycle_1777808795 (11:52 UTC).

### Afternoon — WF window single-source-of-truth

- Previously 5 hardcoded branches lived in `strategy_proposer.py` duplicated at two WF call sites (~130 lines of overrides). Now one `_select_wf_window(strategy, end_date) → (train, test, start, end)` helper reads `backtest.walk_forward.asset_class_windows` from yaml.
- Yaml keys: `crypto_1h`, `crypto_4h`, `crypto_1d`, `crypto_1d_longhorizon`, `non_crypto_1d`, `non_crypto_1h`, `non_crypto_4h`. Plus `long_horizon_templates` list for the `crypto_1d_longhorizon` branch selection.
- Engine-level Yahoo cap at `walk_forward_validate` stays as safety net, now conditional on `fmp_ohlc.is_supported()` — FMP-served symbols bypass the cap. Emits INFO log when it fires.
- Settings UI Card 6 shows per-asset-class windows as read-only table. Editable fallback `wf_train_days` / `wf_test_days` stays.
- WF cache schema hash (`fmp_intraday_2026_05_03`) includes the new window values so any future yaml change auto-invalidates all cached entries.

### Evening — FMP intraday + 1d integration

- **`src/api/fmp_ohlc.py`** NEW — `fetch_klines(symbol, start, end, interval)`. 1h/4h use `/stable/historical-chart/{interval}`. 1d uses `/stable/historical-price-eod/full` (NOT `/historical-chart/1day` which returns empty for everything on Starter). Paginates per-interval (85d for 1h, 170d for 4h, 1825d single call for 1d). 2 parallel workers per-symbol + 429 exponential backoff 2/4/8s. `EXPLICIT_BLOCKED` set documents Starter gaps (GDAXI/FCHI all intervals; OIL/COPPER at 1h and 1d; US indices at 4h; UK100/STOXX50 at 4h).
- **`market_data_manager._fetch_historical_from_yahoo_finance`** — FMP-first branch for non-crypto 1h/4h/1d before Yahoo fallback. When FMP returns 0 bars for a supported symbol (weekend forex, future window), trust it and return `[]` — don't cascade to Yahoo which generates `possibly delisted` errors on the same empty window.
- **`market_data_manager._get_historical_from_db`** — source tag read bug fixed: `source = DataSource.YAHOO_FINANCE` default was silently re-tagging BINANCE/FMP/ETORO rows as Yahoo at read-time.
- **`monitoring_service._sync_price_data`** — FMP 1h, 4h, and 1d batch blocks. Source-aware incremental: if latest DB bar is Yahoo-sourced (legacy cache), force full 5y FMP backfill; if FMP-sourced and fresh, skip; if FMP-sourced and stale, incremental (2h-overlap 1h, 8h-overlap 4h, 2d-overlap 1d). Main-loop 1d pre-check adds a depth test (< 4y triggers backfill).
- **`monitoring_service._quick_price_update`** — the 10-min synthetic bar from eToro live ticks now tags source by asset class (crypto → BINANCE, FMP-supported → FMP, else YAHOO_FINANCE) instead of inheriting from the previous in-memory bar. Previously one stale Yahoo bar could propagate to every subsequent synthetic 1h write, which silently contaminated crypto as "yahoo" on the Data Page.
- **`config/autonomous_trading.yaml`** — `non_crypto_1h`: 180/90 → **365/365**, `non_crypto_4h`: 240/120 → **365/365**. Yaml header comment documents the full FMP/Yahoo/Binance routing matrix.
- **`src/api/routers/data_management.get_data_quality`** — `_canon()` helper collapses wire-form (`BTCUSD`) and Yahoo-ticker-form (`BTC-USD`) legacy residue to display form (`BTC`) at read-time. Prevents duplicate Data Page rows when old writes leaked into the `data_quality_reports` / `symbol_news_sentiment` tables.

**Cleanup actions applied today:**
- Deleted **12 legacy wire-form rows** from `data_quality_reports` (BTCUSD, ETHUSD, BTC-USD, etc.)
- Deleted **120 stale Yahoo crypto 1h rows** from `historical_price_cache` (contaminated by the old quick-update inheritance bug)
- Deleted **424 shallow FMP rows** (pre-fix bootstrap residue, < 100 bars/symbol)
- Deleted **1,136,620 Yahoo 1h/4h rows** for FMP-covered symbols (legacy cache, now redundant)
- Deleted **178,002 Yahoo 1d rows** for FMP-covered symbols (legacy, now redundant)
- Normalized **13,861 lowercase `yahoo` source rows** to `YAHOO_FINANCE`

**Post-deploy verification:**
- Full FMP backfill via `scripts/force_fmp_backfill_now.py` completed in ~10 min with zero 429 failures.
- Post-run DB: FMP at 287 sym @ 1d / 286 sym @ 1h / 286 sym @ 4h; Binance unchanged; Yahoo fallback set = 3 syms @ 1d/1h (OIL/COPPER/GER40), 5 syms @ 4h (non-US indices).
- `errors.log` clean after the deploys. Forex weekend `possibly delisted` noise gone.
- Data Page no longer shows duplicate BTC/BTCUSD rows, no crypto-as-yahoo mis-tagging.

**Files changed today:**
- `src/api/fmp_ohlc.py` (new), `src/data/market_data_manager.py`, `src/core/monitoring_service.py`, `src/strategy/strategy_engine.py`, `src/strategy/strategy_proposer.py`, `src/strategy/portfolio_manager.py`, `src/strategy/cost_model.py`, `src/models/dataclasses.py`, `src/api/routers/config.py`, `src/api/routers/data_management.py`, `frontend/src/pages/SettingsNew.tsx`, `config/autonomous_trading.yaml`
- New scripts: `scripts/probe_fmp_coverage.py`, `scripts/verify_wf_window_helper.py`, `scripts/cleanup_stale_yahoo_cache_v2.py`, `scripts/force_fmp_backfill_now.py`

---

## Earlier sprint history (condensed)

### Sprint 1 (2026-05-02 late session) — Cross-asset DSL primitives

- **F1**: `LAG_RETURN("SYM", bars, "interval")` and `RANK_IN_UNIVERSE("SELF", [...], window, top_n)` as first-class DSL indicators. Computed bar-by-bar in backtest AND signal-gen so WF sees the cross-asset edge. 4 Batch C templates rewritten to use them (BTC Follower 1H/4H/Daily, Cross-Sectional Momentum). Post-deploy: BTC Follower Daily test_sharpe flipped from negative to >1.4 on 4/5 alts.
- **F3**: raised crypto `min_return_per_trade` floors to clear the 2.96% eToro round-trip cost + 50bps minimum edge = 3.5%. WF cache schema bumped.
- **F7**: deleted the broken Pairs Trading Market Neutral template (momentum-long conditions, not a pairs spread).

### Sprint 2 (2026-05-02 late session) — F2 cross-symbol consistency + library expansion

- **F2**: template-level verdict replaces per-pair gates for templates flagged `requires_cross_validation: True`. When ≥4/6 symbols in `family_universe` clear `test_sharpe > 0.3 AND test_return > 0 AND ≥2 test trades AND not overfitted`, activation bypasses per-pair Sharpe / min_trades / RPT gates. Net-return > 0 and risk gates stay enforced. `cross_validation` decision-log stage with per-symbol breakdown.
- **F2.1**: primary-only dedup in `active_symbol_template_pairs` (was including full watchlist, which over-blocked subsequent cycles via cached WF failures).
- **F10**: reconciled 4h crypto cache against 1h source window; added invariant that refuses to return 4h bars outside the 1h range.
- **+5 crypto templates** (Donchian Breakout Daily, Keltner Breakout 4H, OBV Accumulation Daily, 20D MA Variable Cross Daily, BB Volume Breakout Daily) and **+3 DSL indicators** (OBV, DONCHIAN_UPPER/LOWER, KELTNER_UPPER/MIDDLE/LOWER).

### Sprint 3 partial (2026-05-02 late afternoon + evening) — MC calibration + DSL rewrites

- **S3.0**: asset-class-aware MC bootstrap (equity `p5 ≥ 0.0` / n≥15, crypto/commodity `p10 ≥ -0.2` / n≥20 with heavy-tail pass-through).
- **S3.0b**: DEMO-only `min_sharpe_crypto` 0.5→0.3, `min_return_per_trade.crypto_*` 0.035→0.030 for live signal data collection. Documented revert path in yaml for live deployment.
- **S3.0c**: Pass-2-relaxed now requires MC-passed ID (was silently bypassing the MC filter for crypto). MC annualization reads test window from results instead of hardcoded 180d.
- **S3.0d**: DSL grammar extension so `CROSSES_ABOVE` accepts `arith_expr` on both sides (unblocks `VOLUME CROSSES_ABOVE VOLUME_MA(20) * 2.0` etc.). 8 crypto templates rewritten from state-condition entries (`CLOSE > SMA(50)`) to event-condition (`CLOSE CROSSES_ABOVE SMA(50)`) to fix whipsaw 28-trades-with-21%-WR pattern. `PRICE_CHANGE_PCT(N)` auto-detection bug fixed. `scripts/clear_crypto_wf_cache.py` JSON-format bug fixed.

### Sprint-Binance-data-sources (2026-05-02 crypto deep-dive) — Batches A-E + hotfixes

Full crypto pipeline rework. Batch A unblock (min_return_per_trade tiers, timeframe-aware SL/TP floors). Batch B regime gates (auto-injected ADX on crypto_optimized templates). Batch C alpha expansion (BTC Follower 1H/4H/Daily + Cross-Sectional Momentum + Dominance Inversion dropped). Batch D infrastructure (1h crypto 90/90 WF, 4h crypto 180/180 WF, WF cache schema versioning, `proposals_pre_wf` column). Batch E pruning + doc sync. Hotfixes for portfolio_manager interval-key lookup missing 1d, Batch C templates missing RANGING_LOW_VOL in market_regimes, non-crypto_optimized templates blocked on crypto symbols (Option Y asset-class isolation).

### Post-audit fixes (2026-05-02 afternoon) — P0s

- **P0-1**: retirement black-hole. `_demote_idle_strategies` was resurrecting `activation_approved` on pending_retirement strategies. Filter refactored to `_is_eligible()`; 24 zombies cleaned.
- **P0-2**: `live_trade_count=0` on all 180 strategies. `order_executor._increment_strategy_live_trade_count` only fired on synchronous fills; async fills via `order_monitor.check_submitted_orders` never called it. Moved increment there + backfilled from trade_journal.
- **P0-6**: `cycle_error` decision-log stage added so stage failures surface in the observability funnel (previously only logged to cycle_history.log).
- **P1-4**: `MINIMUM_ORDER_SIZE` bumped any sub-$5K position back to $5K even after drawdown/vol-scaling/loser-pair penalty fired. Now returns 0 when `penalty_applied=True`.
- **P1-5**: factor-gate rejections reclassified to INFO (were ERROR, 4 per cycle).

### Pre-May-2 baseline

Observability layer + TSL audit + crypto universe expansion landed May 1. Ground truth captured in `AUDIT_REPORT_2026-05-02.md` (permanent audit reference) and `AUDIT_REPORT_2026-05-01.md`.

---

## Observability & Logs (EC2 `/home/ubuntu/alphacent/logs/`)

| File | Use |
|---|---|
| `errors.log` | **First thing every session** — near-empty on healthy days |
| `cycles/cycle_history.log` | Structured cycle summaries |
| `strategy.log` | Signal gen, WF, conviction |
| `risk.log` | Position sizing, validation |
| `alphacent.log` | Full INFO+ audit trail (rotates 10MB × 20) |
| `data.log` | Price fetches, cache hits |
| `api.log` | HTTP + eToro API |
| `warnings.log` | WARNING level only |

Key INFO-level summary lines to grep:
- `TSL cycle: ...` every 60s from monitoring_service
- `Exec cycle: ...` every signal-generation cycle from trading_scheduler
- `Price data sync complete: ...` hourly from monitoring_service
- `Quick price update: ...` every 10 min
- `FMP (primary non-crypto 1h/4h/1d): ...` and `Binance (primary): ...` per fetch
- `WF window [<key>]: ...` from `_select_wf_window` — shows which asset-class window each WF ran on

---

## Key Parameters (current)

### Risk per asset class
Stock/ETF: SL 6%, TP 15% | Forex: SL 2%, TP 5% | Crypto: SL 8%, TP 20% | Index: SL 5%, TP 12% | Commodity: SL 4%, TP 10%

### Position sizing
- `BASE_RISK_PCT`: 0.6% of equity per trade
- `CONFIDENCE_FLOOR`: 0.50
- `MINIMUM_ORDER_SIZE`: $5,000 (returns 0 if drawdown/vol/loser-pair penalty applied)
- Symbol cap: 5% | Sector soft cap: 30% | Portfolio heat: 30%
- Drawdown sizing: 50% >5% DD, 75% >10% DD (30d peak)
- Vol scaling: 0.10x–1.50x
- **Per-pair loser penalty**: (template, symbol) with ≥3 net-losing trades halves size until net-P&L flips positive.

### Activation thresholds
- `min_sharpe`: 1.0 | `min_sharpe_crypto`: 0.3 (DEMO; revert to 0.5 for live) | `min_sharpe_commodity`: 0.5
- `min_trades_dsl`: 8 (1d) | 8 (4h) | 15 (1h)
- `min_trades_alpha_edge`: 8 | `min_trades_commodity`: 6
- Sharpe exception: test_sharpe ≥ 2.0 + ≥ 3 trades bypasses min_trades
- `min_return_per_trade.crypto_*`: 0.030 (DEMO; revert to 0.035 for live)
- **SHORT tightening**: primary path needs min_sharpe +0.3 for shorts; relaxed-OOS rescue path removed for shorts; test-dominant needs ≥4 test trades.

### WF windows (authoritative — yaml-managed via `asset_class_windows`)
- `crypto_1h`: 365 / 365
- `crypto_4h`: 365 / 365
- `crypto_1d`: 365 / 365
- `crypto_1d_longhorizon`: 730 / 730 (templates: 21W MA Trend Follow, Vol-Compression Momentum, Weekly Trend Follow, Golden Cross)
- `non_crypto_1d`: 730 / 365
- `non_crypto_1h`: 365 / 365 (FMP-covered) / Yahoo-cap 180 / 90 (fallback)
- `non_crypto_4h`: 365 / 365 (FMP-covered) / Yahoo-cap 240 / 120 (fallback)

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
- **C3 Trend Consistency**: blocks SHORT above rising 50d SMA or in oversold-bounce zone; blocks LONG below falling 50d SMA (crypto/forex exempt)

### Feedback-loop decay
- Symbol score: 14-day half-life on trade recency; floor 0.2
- Rejection blacklist: 14-day cooldown + regime-scoped early expiry
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

-- Why didn't we trade <SYMBOL>? (7-day lookback)
SELECT timestamp, stage, decision, template_name, reason
FROM signal_decisions
WHERE symbol='TSLA' AND timestamp > NOW() - INTERVAL '7 days'
ORDER BY timestamp DESC LIMIT 50;

-- Symbols with directional imbalance
SELECT symbol, COUNT(*) AS trades,
       SUM(CASE WHEN side='LONG' THEN 1 ELSE 0 END) AS longs,
       SUM(CASE WHEN side='SHORT' THEN 1 ELSE 0 END) AS shorts,
       ROUND(SUM(pnl)::numeric, 2) AS pnl
FROM trade_journal WHERE pnl IS NOT NULL
GROUP BY symbol HAVING COUNT(*) >= 3
  AND (SUM(CASE WHEN side='LONG' THEN 1 ELSE 0 END) = 0
       OR SUM(CASE WHEN side='SHORT' THEN 1 ELSE 0 END) = 0)
ORDER BY pnl;

-- Cache depth per (symbol, interval, source)
SELECT source, interval, COUNT(DISTINCT symbol) AS symbols, COUNT(*) AS bars,
       MIN(date)::date AS earliest, MAX(date)::date AS latest
FROM historical_price_cache
GROUP BY source, interval ORDER BY source, interval;

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

### Ready-to-run (data fully primed, log hygiene complete)

Trigger a full autonomous cycle when ready. Data is in place:
- Crypto 1d/1h/4h on Binance, full depth.
- Non-crypto 1d/1h/4h on FMP Starter, 5y depth for 286-287 symbols.
- Yahoo fallback ready for the 8-11 premium-blocked (symbol, interval) combos.

Cross-timeframe OHLC consistency guaranteed for FMP-served symbols (raw-close across 1d/1h/4h) — no more day-boundary phantom gaps from Yahoo 1d adjusted-close vs FMP intraday raw-close.

Log hygiene post-2026-05-03 evening: errors.log clean, warnings.log at signal-to-noise ratio high enough that any new entry indicates something real.

### Verification after next cycle

1. **FMP coverage**: grep `FMP (primary` and `Binance (primary` across all 3 intervals. No symbol should hit Yahoo unless it's in the premium-blocked set.
2. **WF window selection**: every strategy emits `WF window [<key>]:` at INFO. Expect all 7 keys to fire across the cycle.
3. **Activation health**: crypto activations at normal rate (post-per-position-RPT-fix); non-crypto at normal rate.
4. **errors.log**: should stay near-empty. Zero yfinance ERRORs expected (720d-cap guard blocks them at source).
5. **warnings.log**: expect < 10 warnings per autonomous cycle. GER40 4h freshness is legitimate on Sunday/Monday mornings. OIL/COPPER 1h warnings should be zero (templates narrowed to GOLD/SILVER).
6. **MQS persistence**: every new `equity_snapshots` row should have non-NULL `market_quality_score` and `market_quality_grade`.
7. **Cycle summary**: should read `[PROPOSALS] N candidates → M fresh, K cached from earlier cycles` when cache has been warmed by prior cycles.

### Deferred / still open

- **Conviction-floor two-factor gate** (P0 next session): the 65 conviction floor is correctly killing low-edge broad-market entries (XLK/SPY/TQQQ repeatedly scoring 60-64 in a trending_up_strong regime with wf_edge 23-27/40 — right decision). But the same binary threshold also clips edge-case single-stock entries at 64.5-64.8 where WF quality is genuinely good (MU × Keltner 64.6, UNH × 4H ADX 64.6, ROST × 4H VWAP 64.8). These are real setups the system is missing by 0.2-0.5 points. Proper fix: two-factor gate `score ≥ 65 OR (score ≥ 62 AND wf_edge ≥ 32 AND persistence ≥ 9/10)` — lets through high-quality boundary cases without opening the door to weak-WF broad-market noise. Design session first, then implement. 2-4 hours total. Details in next-session kickoff prompt.
- **Triple EMA Alignment DSL bug** (P1): `EMA(10) > EMA(10)` tautology from regex param collapse in `strategy_proposer.customize_template_parameters`. ~30 min fix to add explicit positional-EMA-period handling.
- **WF bypass-path tightening for LONG** (P1): primary + test-dominant paths admit regime-luck on LONG side. Consider `(test_sharpe - train_sharpe) ≤ 1.5` consistency gate. SHORT already tightened (Sprint 1).
- **Cross-cycle signal dedup for market-closed deferrals** (P1): entry-order 82% FAILED rate is cosmetic — market-closed deferrals re-fire each cycle. 30-min TTL map on `(strategy_id, symbol, direction)` in trading_scheduler.
- **trade_id convention unification** (P2): `log_entry` uses `position.id`; `log_exit` uses order UUID. Migrate `order_monitor.check_submitted_orders` to `position.id`.
- **Sector Rotation + Pairs Trading template rewrites** (P2): both structurally broken. Design-first, then rewrite.
- **Monday Asia Open template** (P2): needs DSL `HOUR()` primitive.
- **On-chain metrics** (P1, Sprint 4): BTC dominance, stablecoin supply momentum. `ONCHAIN("metric", lookback_days)` DSL primitive. CoinGecko + DeFi Llama free tiers to start.
- **Forex on-demand via new `fmp_ohlc` client**: the legacy `_fetch_historical_from_fmp` path for forex 1d still uses the dead v3 `historical-price-full` endpoint — returns empty, falls through. Not breaking anything; cleanup task only; ~15 min.
- **Overview chart panel rewrite** (P2): 3 chart components with misaligned axes; design-first.
- **Commodity 1h coverage expansion** (P3): if FMP Starter upgrade is ever considered, OIL/COPPER/NATGAS 1h would become WF-validateable with their full 5y history. Until then, 4h is the minimum viable intraday for commodities.

---

## Next-session kickoff prompt

Copy this as-is into a new session when you're ready:

```
Start this session by reading, in this exact order:
(1) .kiro/steering/trading-system-context.md — especially:
    - "Think Like a Trader, Not a Software Engineer"
    - "Proper Solutions Only — No Patches, No Stopgaps"
    - "Deployment Workflow — Mandatory" (the full scp-only rule +
      the narrow autonomous_trading.yaml exception)
(2) Session_Continuation.md — full file, especially the 2026-05-04
    late evening session block (FMP 1h ingestion + conviction-persist
    + scorer audit) and the Open Items section below.

Confirm you've read them and begin.

==========================================================================
CONTEXT ENTERING THIS SESSION
==========================================================================

The 2026-05-04 late evening session shipped 3 sprints in one session:

- P0 FMP 1h ingestion fix (3 stacked bugs: ET→UTC timezone, active-only
  gate dropping 141 stocks, synthetic O=H=L=C placeholder bars in DB).
  Purged 1.9M corrupted bars, rebackfilled 3.4M clean UTC-stamped bars.
  275/277 non-crypto symbols now fresh within 1h.

- Conviction-scorer audit. Walked the 1215-line scorer component by
  component. Key discovery: over the last 10 days, avg P&L is NON-
  MONOTONIC in conviction bucket — 65-70 bucket (above threshold) loses
  $184/trade on avg with 73% WR (fat-tailed losers); 60-65 bucket (just
  below threshold) is +$3/trade. Scorer is actively promoting bad setups.
  Distribution compressed (97% of 47k signals between 55-70). Multiple
  components (signal_quality, regime_fit, asset_tradability) are near-
  constants. Several components double-count what WF already validated.

- P0 conviction-score persistence fix. Same class as yesterday's
  template_name bug — 3 backfill paths (order_monitor sync, portfolio
  manager retirement, monitoring_service pending-closure) only populated
  template_name, not conviction_score/market_regime/ml_confidence/
  fundamentals. Fixed via (strategy_id, symbol, ±10min) order lookup
  + spread into log_entry. Startup self-check armed; expected to climb
  from 0.1% to 70-80% within 48h.

System state at session close:
- Equity: ~$474K, 69 open positions
- 275/277 non-crypto 1h bars fresh (was 141 stuck at 11:30)
- All 1h/4h FMP bars are real UTC-stamped OHLCV (no synthetic)
- conviction_score column now armed on write path; validation loop
  functional once ~2-3 weeks of data accumulates
- errors.log clean post-restart
- Cycle activation rate: normal pattern (2-4/cycle) with occasional
  0-cycle when WF-pass candidates all fail the ex-post 730d gate
  — working as intended on cleaner post-fix data

Last commits on main (newest first):
- [pending] P0 conviction-persist + scorer audit notes
- 905908d fix: FMP 1h ingestion — ET→UTC + drop active-only gate + stop synthetic-bar DB writes
- b8aeab6 fix: Data-page quality table — per-interval freshness
- 9b8142a fix: Binance status — measure freshness as intervals-behind
- 27ee374 feat: 24/5 readiness + MarketHoursManager singleton + filter-funnel
- f29f23f fix: loser-pair penalty data integrity — populate template_name

==========================================================================
MISSION — P0: ORPHAN-POSITION BUG (strategy_id='etoro_position')
==========================================================================

Discovered 2026-05-05 ~18:40 UTC while reviewing the Portfolio page.
Four of today's positions (SOXL, SMH, TQQQ, XLK, all opened 13:30 UTC
on the 2026-05-05 US market open) display "etoro_po" in the Strategy
column — the truncated form of `strategy_id='etoro_position'`, which
is the default sync-path fallback for eToro positions we don't
recognize locally. But these WERE our signals. The orphan-creation
chain is:

Timeline reconstructed from logs and DB (six eToro order IDs traced):

  1. 2026-05-04 21:42-21:46 UTC (17:42-17:46 ET). Autonomous cycle
     generates entry signals for XLK, SOXL, SMH, TQQQ (all post-
     market-close ET). execute_signal's market-hours gate ALLOWED
     submission (24/5 schedule, Monday evening is within window).
     Six orders submitted to eToro successfully:
        348446527 (SMH), 348450614 (TQQQ), 348446528 (SOXL),
        348418989 (SOXL), 348405225 (XLK), 348405233 (XLK),
        348405234 (SOXL)
     Each has a valid etoro_order_id in our orders table, status
     PENDING. These orders are QUEUED on eToro for market open.

  2. 2026-05-04 21:52:49-21:52:59 UTC. Something triggered a cleanup
     /cancel pass ~6-10 minutes after submission. Our code calls
     etoro_client.cancel_order(<id>) for each — eToro returns 404
     "Unknown error". Our code interprets 404 as "order gone,
     mark CANCELLED locally" and transitions the DB row to
     status=CANCELLED. The 404 is the same handling added 2026-05-04
     morning (EToroOrderNotFoundError → sentinel) for user-cancelled
     orders — which is wrong here because cancel-route 404 doesn't
     imply the order is dead.

     NOTE: three orders (348405233/348405234 at 21:46, one more at
     similar time) show status=FAILED instead of CANCELLED — likely
     hit a different error path in the same cleanup sweep.

  3. 2026-05-05 13:30:03-13:30:06 UTC (09:30:03-09:30:06 ET, US market
     open). eToro executes the queued orders we thought we cancelled.
     4 positions open on the eToro side (SOXL/SMH/TQQQ/XLK). Two
     orders (348446528, 348418989) merged into a single SOXL position.

  4. Next monitoring_service sync tick (60s cadence). Sync fetches
     eToro positions, finds 4 new positions with etoro_position_id
     not in our DB, creates PositionORM rows with default fallback
     strategy_id='etoro_position' (src/api/routers/account.py:1004).

The bug is NOT the sync-path fallback — that's correct behavior for
a genuinely-externally-opened position. The bug is that the CANCEL
path mis-classifies live-queued orders as dead, silently releasing
them to eToro's open-market execution queue, where they then come
back through the sync-path as orphans.

BLAST RADIUS (today): 4 open positions invisible to:
  - TSL cycle (no strategy_id → no risk_params lookup → no trail)
  - loser-pair penalty (no template_name in metadata)
  - conviction validation loop (no conviction_score, no template)
  - per-strategy concentration caps
  - strategy retirement cleanup
  - trade journal closed-trade attribution when they exit

Plus the 3 earlier orphans (URI 2026-05-04, UK100 + NFLX 2026-04-13)
indicate this has been happening since at least April. Not a
regression from today's work.

YOUR MISSION for P0 (three parts, in order):

========================================================================
PART 1 — IMMEDIATE RECOVERY (script-only, one-shot)
========================================================================

Write scripts/recover_orphan_positions.py that:

1. Queries positions where strategy_id = 'etoro_position' AND
   closed_at IS NULL.

2. For each orphan, attempts to find the originating order via:
   (a) orders table match on (symbol, submitted_at within ±24h of
       position.opened_at, status IN CANCELLED/FAILED, order_metadata
       IS NOT NULL)
   (b) If multiple matches, pick the one whose etoro_order_id is
       numerically closest to the position's etoro_position_id
       (eToro positions reuse or derive from order IDs on fill).
   (c) If no match in orders, try conviction_score_logs by
       (symbol, timestamp within 6h before position.opened_at).

3. For a matched orphan:
   - UPDATE positions.strategy_id = <real_strategy_id>
   - UPDATE positions.stop_loss, take_profit from strategy.risk_params
     if currently NULL
   - Backfill trade_journal entry with conviction_score, template_name,
     market_regime from order.order_metadata
   - Write a reconciliation log row to trade_journal.trade_metadata
     with key "orphan_recovery_source": "sync_path_relink_2026_05_06"

4. Dry-run by default. Verify on 4 known orphans:
     SOXL (pos_id=3509139906)
     SMH  (pos_id=3509138740)
     TQQQ (pos_id=3509138333)
     XLK  (pos_id=3509137957)
   Expected match via CANCELLED orders submitted 2026-05-04 21:42-21:46.

5. Idempotent — only touches strategy_id = 'etoro_position' rows, so
   re-running is safe.

========================================================================
PART 2 — ROOT-CAUSE FIX (cancel_order 404 handling)
========================================================================

Find the cancel-sweep caller that fired at 2026-05-04 21:52 UTC. Likely
candidates:
  - src/strategy/portfolio_manager.py (strategy retirement path)
  - src/strategy/strategy_engine.py (pending-closure cleanup)
  - src/core/order_monitor.py _cleanup_stale_pending
  - src/api/etoro_client.py cancel_order 404 handling

Hypothesis to verify first: a 30-min stale-pending sweep ran and tried
to cancel orders that had been PENDING > some threshold. Those orders
were queued for market open but hadn't filled yet (correctly PENDING).
The cancel attempt hit 404 — the code then assumed cancellation success
and marked CANCELLED locally. Six minutes is too short for a "stale"
classification.

Fix strategy:
  (a) ANY cancel_order call that gets a 404 response MUST NOT
      transition the local row to CANCELLED. Instead: log a WARNING,
      leave the row as-is, and let the next poll of order_monitor
      (which queries order STATUS, not cancel) establish ground truth.
  (b) The "after-hours grace period" logic at order_monitor.py:2125
      needs to cover orders submitted in the last trading-day evening
      (Mon 17:00-20:00 ET) that are waiting for tomorrow's Tue 09:30
      ET open. Current timeout seems too short.
  (c) Distinguish "cancel endpoint 404" from "status-poll 404" at the
      API-client layer via two distinct exceptions or a context flag.
      Cancel-404 → order still unknown. Status-poll-404 → order
      definitely gone.

This is the SAME bug family as the earlier 2026-05-04 fix (user
cancels in UI → our status poll 404s → mark CANCELLED). That fix was
correct for the USER-cancel case. It became wrong when the same 404
code path was reused for the cancel-attempt case where 404 doesn't
imply the order is dead.

========================================================================
PART 3 — ARCHITECTURAL DEFENSE (sync-path strategy-relink)
========================================================================

The sync path at src/api/routers/account.py:1004 defaults to
strategy_id='etoro_position' when creating a PositionORM for an eToro
position that doesn't exist locally. This is the last-resort fallback
and it's correct as a fallback. But BEFORE defaulting, the sync should
attempt to match the eToro position back to a local order by:

  (a) Match on etoro_position_id == any orders.etoro_order_id
      (eToro position IDs often derive from order IDs on fill — the
      SOXL case shows position_id 3509139906 and etoro_order_id
      348405234 which are similar/derived).
  (b) Match on (symbol, position.opened_at within ±5 min of any
      recent order.submitted_at).
  (c) If a match exists, pull strategy_id + metadata from that order
      instead of defaulting to 'etoro_position'. Record the match
      reason in position.closure_reason temporarily so we can audit.

This is defense-in-depth — even if Part 2's cancel fix has a gap,
orphans auto-recover on the sync tick instead of stranding silently.

========================================================================
NON-GOALS (DO NOT WORK ON THESE)
========================================================================

- Do NOT change the sync-path default fallback to something other
  than 'etoro_position'. External positions (user-opened in eToro UI)
  are legitimate and need a marker.
- Do NOT remove the 404-on-status-poll → CANCELLED path from the
  2026-05-04 morning fix. That path is correct for the user-cancel
  case.
- Do NOT block submission when "market closed" for post-regular-hours
  orders. eToro's 24/5 window IS open those hours — our orders
  correctly land there.

========================================================================
VERIFICATION CHECKLIST
========================================================================

After Part 1:
  - SELECT COUNT(*) FROM positions WHERE strategy_id='etoro_position'
    AND closed_at IS NULL should drop from 7 to 3 (the 3 genuinely
    external positions: URI, UK100, NFLX — those don't have matching
    orders, so they're legitimate externals).
  - The 4 relinked positions should now appear under their real
    strategy names on the Portfolio page.

After Part 2:
  - Submit a test order post-market-close, wait 10 min, confirm it
    stays PENDING locally even if any cleanup sweep fires a cancel.
  - errors.log should no longer show the "Failed to cancel order XXX:
    404 - Unknown error" pattern from our own cleanup.

After Part 3:
  - Manually open a position on eToro UI (user-path simulation).
    Sync should still create it with strategy_id='etoro_position'
    (legitimate external).
  - Submit a real autonomous signal, force-cancel the local order
    row (simulate bug), let it fill at market open. Sync should now
    auto-relink to the real strategy instead of orphaning.

========================================================================
ALSO IN SCOPE — was next session's original mission (DEFER if P0 runs long)
========================================================================

The conviction-tier position sizing + 4H template kill + SHORT hard-gate
+ intraday ATR-widen mission is still queued but secondary to the
orphan-position fix. If P0 Parts 1-3 complete with runway remaining,
pick up items 1-4 from the "MISSION — CONVICTION-TIER POSITION SIZING"
block documented in the prior commit's next-session prompt (see
commit f27c13e message).

Rules (same as every session):
- Proper solutions only. No patches.
- Research the cancel-sweep trigger BEFORE editing.
- Deploy via the scp workflow. Never edit on EC2.

Estimate: 3-5 hours for Parts 1-3. The research phase (tracing the
cancel-sweep trigger) is the high-variance piece.

==========================================================================
OTHER OPEN ITEMS — DO NOT WORK ON THESE BEFORE THE P0
==========================================================================

P1 (carry forward):
- Conviction-tier position sizing + 4H template remediation +
  SHORT hard-gate + intraday ATR-widen (detailed in f27c13e commit
  message and Session_Continuation prior section).
- Triple EMA Alignment DSL regex collapse
- WF test-dominant path admits regime-luck on LONG
- Cross-cycle signal dedup for market-closed deferrals
- NATGAS 1h stale

P2:
- trade_id convention unification
- Sector Rotation + Pairs Trading template rewrites
- Monday Asia Open template (needs DSL HOUR() primitive)
- ONCHAIN DSL primitive
- Overview chart panel rewrite
- CI/CD hardening

P3:
- Commodity 1h coverage
- Forex 1d legacy FMP path cleanup
- SignalDecisionLogORM table drop (T+30d after 2026-05-04)
```

---

---

## Reference — DB migrations applied to prod (cumulative)

- `ALTER TABLE orders ADD COLUMN order_metadata JSON;`
- `ALTER TABLE strategy_proposals ADD COLUMN symbols JSON, ADD COLUMN template_name VARCHAR;`
- `CREATE TABLE signal_decisions (...)` with 5 indexes
- `ALTER TABLE autonomous_cycle_runs ADD COLUMN proposals_pre_wf INTEGER;`
- (From today's FMP integration) no schema changes — `historical_price_cache` already supported multi-source via the `source` VARCHAR column.
