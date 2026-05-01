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

## Current System State (May 1, 2026, post Strategy Library deploy)

- **Equity:** ~$475,886
- **Balance:** ~$61K freed
- **Open positions:** 86 | $403K deployed | +$4,552 unrealized (~69% WR on open book)
- **Active strategies:** 157+ (autonomous cycle ran 400-target, 392 DSL + 8 AE proposed)
- **Active AE strategies:** 5 in DB pre-deploy → 8 new proposed this cycle. First 2 already activated (Insider Buying LEU, Earnings Momentum APP). Templates that graduated NEW include Earnings Momentum, Gross Profitability Long, Price Target Upside Long, Earnings Momentum Combo Long, Sector Rotation, Revenue Acceleration, Multi-Factor Composite Long.
- **Directional split:** ~75 LONG / ~11 SHORT (still below target for `trending_up_weak`)
- **Market regime:** `trending_up_strong` per regime gate (VIX=18.8, 50d=+10.64%) | Market Quality Score: NOT PERSISTED (open issue — see below)
- **Symbol universe:** 297 instruments (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, **2 crypto** — BTC/ETH only, altcoins disabled due to eToro 1% fee)
- **Scheduled cycles:** daily 15:15 UTC + weekdays 19:00 UTC

**Deploys shipped today (2026-05-01):**
- 10:02 UTC — **Batch 1** (F02 DST fix + F09 freshness SLA)
- 10:19 UTC — **Quick-wins** (F13, F15, F19, F21, F22)
- 10:44 UTC — **F18-rest + F20 + F26** (silent-default logging + FRED retry + interval-aware incremental fetch)
- 10:54 UTC — **F30 positions closed** (mixed-asset-class forex positions, +$33.67 realised)
- 12:02 UTC — **Strategy Library** (commit `4acfadb`): R1-R7 template removals + C1 VIX gate + C2 momentum crash breaker + C3 PEAD tightening + Q1 AE rotation + Q2 AE cap 5→8

See `AUDIT_FIX_TRACKER.md` for live status and `STRATEGY_LIBRARY_REVIEW_2026-05.md` for the review that produced today's strategy-library changes.

---

## Observability & Logs (EC2 `/home/ubuntu/alphacent/logs/`)

| File | Use |
|---|---|
| `errors.log` | **First thing every session** — near-empty on healthy days |
| `cycles/cycle_history.log` | Structured cycle summaries, best for diagnostics |
| `strategy.log` | Signal gen, WF, conviction |
| `risk.log` | Position sizing, validation |
| `alphacent.log` | Full INFO+ audit trail (rotates 10MB × 5) |
| `data.log` | Price fetches, cache hits |
| `api.log` | HTTP + eToro API |

---

## Key Parameters (current, post-May 1)

### Risk per asset class
Stock/ETF: SL 6%, TP 15% | Forex: SL 2%, TP 5% | Crypto: SL 8%, TP 20% | Index: SL 5%, TP 12% | Commodity: SL 4%, TP 10%

### Position sizing
- `BASE_RISK_PCT`: 0.6% of equity per trade
- `CONFIDENCE_FLOOR`: 0.50 (signals below are noise)
- `MINIMUM_ORDER_SIZE`: $5,000
- Symbol cap: 3% of equity | Sector soft cap: 30% (halve if exceeded)
- `MAX_PORTFOLIO_HEAT_PCT`: 30% of equity
- Drawdown sizing: 50% reduction > 5% DD, 75% > 10% DD (30d peak)
- Vol scaling: 0.10x–1.50x | Target vol: 16%

### Activation thresholds
- `min_sharpe`: **1.0** (raised from 0.4 on May 1 — was allowing noise)
- `min_sharpe_crypto`: 0.5 | `min_sharpe_commodity`: 0.5
- `min_trades_dsl`: 8 (1d) | 8 (4h) | 15 (1h)
- `min_trades_alpha_edge`: 8 | `min_trades_commodity`: 6
- Sharpe exception: test_sharpe ≥ 2.0 + ≥ 3 trades bypasses min_trades

### Conviction scoring
- Threshold: **65/100** (dropped from 70 on Apr 30 — was blocking all signals)
- Components: WF edge (40) + signal (25) + regime (20) + asset tradability (15) + fundamental (±15) + carry (±5) + crypto cycle (±5) + news (±1) + factor (±6)
- Asset tradability: Tier 1 stocks & major crypto/forex/indices 15pts | Tier 2 liquid 13pts | **ETFs 13pts, Indices 14pts** (bumped May 1 — 64.6% ETF WR, 85.7% index WR live)
- Theoretical max: 132 (normalized to 100)
- Uptrend SHORT strategies get 20/20 regime fit (they are the hedge)

### ATR floor (SL adjustment at order time)
- Multiplier: **1.5× ATR** — HARDCODED at `order_executor.py:241`. Config key `atr_sl_multiplier: 2.5` in `autonomous_trading.yaml` is **unread** (confirmed by grep — no call sites). Code is source of truth.
- **Timeframe-aware**: 4H strategies use 4H ATR bars, 1D use daily
- Max SL clamp: Stocks/ETFs 9%, Crypto 15%, Forex 4%
- When SL widens, position size scales down proportionally (`new_size = old_size × old_sl / new_sl`) to preserve dollar risk

### Zombie exit (differentiated)
- Trend-following: 5 days (1D) / 3 days (4H) flat ±1%
- Mean reversion: 7 days (1D) / 4 days (4H)
- Alpha Edge: 14 days (1D) / 7 days (4H)
- Retirement blocker: pending_retirement strategies flat ±2% for 5+ days

### Directional quotas (trending_up regimes)
- `trending_up`: min_long 80%, min_short 5%
- `trending_up_weak`: min_long 75%, min_short 8%
- `trending_up_strong`: min_long 85%, min_short 3%
- Never zero short exposure

### Market Quality Score (0-100)
- Components: ADX(14) of SPY (40pts) + ATR/price inverted (30pts) + 5-day consistency (20pts) + VIX (10pts)
- Grades: High (>70) / Normal (40-70) / Choppy (<40)
- Actions: score < 40 → position sizing -30%, trend templates -50% weight at proposal, trend/momentum LONG entries blocked
- Persisted in `equity_snapshots` (market_quality_score, market_quality_grade columns)

### Monte Carlo Bootstrap
- 1000 iterations, p5 Sharpe threshold: 0.0 (break-even bar, standard post-WF filter)
- Min trades for bootstrap: 15 (strategies with < 15 bypass)
- Annualization: `sqrt(trades_per_year)` using 180-day test window

---

## Autonomous Cycle Pipeline

1. Cleanup — retire stale BACKTESTED
2. Market analysis — regime, Market Quality Score, fundamental loading
3. Proposal — 50-200 strategies from template library (regime + fast-feedback filtered)
4. Walk-forward validation — train/test split, Sharpe/trades/overfitting
5. Monte Carlo bootstrap — resample P&L, p5 Sharpe ≥ 0.0
6. Direction-aware thresholds — regime-specific min Sharpe/WR/return
7. Conviction scoring — FMP fundamentals, carry, crypto cycle, news, factors
8. Activation — top by conviction → BACKTESTED
9. Signal generation — run signals for newly activated strategies

---

## Session May 1, 2026 — Data Pipeline Audit

### Context
After April 29 trading overhaul, equity recovered to $476K. Friday May 1 diagnostic found the yfinance pipeline crashing on DST boundary (166 symbols failed at 01:47 UTC), plus two follow-on bugs in the price update flow. Full audit & fix of data integrity issues.

### Bugs fixed (all P0 — data integrity)

**1. yfinance DST AmbiguousTimeError**
- Root cause: `yf.download()` / `ticker.history()` return tz-aware timestamps. DST boundary crossings (EU last Sunday Oct/Mar, US first Sunday Nov/Mar) produce ambiguous local hours. `pd.resample()` and `Timestamp.to_pydatetime()` raise AmbiguousTimeError.
- Impact: at 01:47 UTC today, sync for 166 symbols failed. Previous outbreaks Apr 24 (8 forex pairs, ^GDAXI).
- Fix: normalize tz-aware index to UTC-naive BEFORE any resample/iteration (`hist.index.tz_convert('UTC').tz_localize(None)`) in 4 call sites: `market_data_manager._fetch_historical_from_yahoo_finance`, `monitoring_service._sync_price_data` batch, `etoro_client` legacy path, `analytics` SPY benchmark.
- Also moved tz_convert BEFORE 4H resample (it was after — resample itself was crashing).

**2. Full sync was caching stale 1d DB data**
- Root cause: `_sync_price_data` reads DB 1d bars and pre-populates shared in-memory `HistoricalDataCache` without checking if DB data is stale. Strategy engine hits this cache first and bypasses `get_historical_data` — where gap detection + Yahoo top-up lives.
- Impact: 1d bars stayed 1-2 days stale for up to 1 hour after restart. Every strategy running in that window computed RSI/SMA/MACD on data missing the most recent 1-2 daily candles. Affected ~61 DEMO + ~117 BACKTESTED 1d strategies daily.
- Fix: explicit staleness check in `_sync_price_data` before caching. Crypto/forex: stale if gap > 1.2 days. Stocks/ETFs/indices/commodities: stale if gap > 1.2 days AND not a weekend gap. Stale symbols queued for Yahoo batch fetch.
- Verified: first post-fix sync queued **232 stale 1d symbols** for Yahoo (was 0). AAPL, NVDA, BTC, EURUSD advanced by 1 day.

**3. Quick update corrupting 1d historical bars**
- Root cause: `_quick_price_update` runs every 10 min updating the last bar's OHLC with live tick. For 1h it correctly appends new bar when hour rolls over. For **1d there was no equivalent check** — live ticks were written into the last 1d bar regardless of whether that bar was today or yesterday.
- Impact: if the 1d cache had yesterday's bar (stale — common), every 10 min live ticks corrupted yesterday's historical candle with today's prices, then saved to DB. Data contamination in `historical_price_cache`. Walk-forward backtests running on recent history got partial look-ahead bias on days where the end of the test window overlapped a corruption day.
- Fix: removed 1d update from quick update entirely. Quick update now only maintains 1h bars (intraday appropriate). 1d refreshed exclusively by the full hourly sync pulling proper end-of-day data from Yahoo.
- Verified: quick update continues running (166 symbols updated, 0 errors) with only 1h touches.

### Other fixes this session

**4. Conviction threshold: 70 → 65**
- 70 was above practical DSL ceiling (observed max: 69.x). Zero orders for 30+ min at London open.
- 65 gives ~25% pass rate based on today's score distribution. Healthy.

**5. Conviction tier bump for ETF/Index**
- ETFs 12 → 13 (64.6% live WR justifies Tier 2) | Indices 12 → 14 (85.7% live WR, tightest eToro CFD spreads)
- Tier 1 stocks (SPX500, NSDQ100) unchanged at 15.

**6. Zombie exit thresholds for trend-following raised**
- 1D: 3 → 5 days | 4H: 2 → 3 days
- Reason: winners avg 5.4 days hold; 3-day threshold was flagging profitable positions before maturation. Mean reversion unchanged.

**7. WF Sharpe activation floor raised to 1.0**
- min_sharpe 0.4 → 1.0 (live data: Sharpe 0.4-1.0 strategies had <30% live WR)
- min_sharpe_crypto 0.1 → 0.5 | min_sharpe_commodity 0.3 → 0.5
- Existing BACKTESTED strategies with Sharpe < 1.0 run to natural close via decay scorer (not force-retired)

**8. Rename `symbol_mapper.normalize_symbol` → `to_etoro_wire_format`**
- Two functions named `normalize_symbol` doing different things was a maintenance trap. Now explicit.
- Backward-compat alias preserved. No call-site breakage.

**9. Crypto symbol normalization in `historical_price_cache` (shipped earlier)**
- `historical_price_cache` had crypto as `BTCUSD`/`ETHUSD` (eToro wire format) while positions/orders used `BTC`/`ETH`. 8,676 BTC + 8,674 ETH rows were unreachable.
- Fix: `market_data_manager.get_historical_data` separates `db_symbol` (canonical: BTC) from `normalized_symbol` (eToro wire: BTCUSD). DB migration renamed all crypto rows to display form.
- Impact: vol-scaling for crypto now uses real realized vol (~60% BTC), WF backtests on crypto use correct history, ATR on crypto works.

### How the price-data bugs actually impacted trading

The three data bugs compounded:
- DST crash prevented fresh fetches across DST boundary periods
- Full sync cached whatever stale data was in DB → strategies saw yesterday's candle during the first hour of each day
- Quick update then corrupted that stale candle every 10 min with today's tick prices

Net effect: **every signal, every SL calculation, every WF backtest Sharpe estimate since at least April 24 had unknown error bars.** The system was still profitable, but indicators computed on polluted data mean:
- April 29 overhaul decisions (min_sharpe threshold, template suspensions, MQS calibration) were made partly on contaminated backtests
- 4H strategies computing ATR-based SLs on stale 1h bars — wrong stop distances
- The April 30 conviction threshold calibration (70→65) was done on scores produced by strategies consuming corrupted data

Can't replay to quantify exact P&L impact. What we can do: give the pipeline a clean week to produce trustworthy data, then re-audit the key thresholds.

### Pre-existing data issue noted (not yet fixed)

`historical_price_cache` has duplicate 1d entries for some symbols — same OHLC stored under `YYYY-MM-DD 00:00:00` AND `YYYY-MM-DD 04:00:00`. Caused by different code paths storing at different times-of-day with the same date. `_save_historical_to_db` dedup uses full timestamp for intraday and date-only for daily, but the implementation doesn't catch this cross-time-of-day case. Low priority cleanup.

---

## Open Items (May 1, 2026, post-audit)

Full audit complete — see `AUDIT_REPORT_2026-05-01.md` for all 25 findings and `AUDIT_FIX_TRACKER.md` for live status and batching plan.

### Batch 1 — deployed 2026-05-01 10:02 UTC, awaiting 24-48h verification
- F02 A/B/C: tz-aware UTC to yfinance + per-ticker retry + freshness SLA
- F09: freshness gate on trailing stop updates
- **Verification windows:** 20:00 UTC today (next daily sync), 01:47 UTC tomorrow (next DST-adjacent overnight), 24h open-position observation.

### Batch 2-5 — scheduled (see tracker)
- **Batch 2**: execution observability (F04 + F10) — after Batch 1 stable 24-48h
- **Batch 3**: position risk (F03 concentration cap, F11 trailing step, F18-critical)
- **Batch 4**: signal quality (F01/F12 WF bypass removal, F05 Triple EMA fix, F07 MC annualization, F08 fast feedback) — needs clean Batch-1 data
- **Batch 5**: alpha + polish (MQS investigation, asset-class weighting, etc.)

### Quick-wins shipped alongside Batch 1 (session 1)
- **F13** — `atr_sl_multiplier` removed from config (was unread dead code)
- **F15** — BTC Lead-Lag Altcoin template removed from active library (altcoins disabled)
- **F19** — `pool_pre_ping=True` on SQLAlchemy engine (SSL pool resilience)
- **F21** — phantom altcoin/delisted rows purged from `historical_price_cache`
- **F22** — `errors.log` rotated (was 4.7MB/31k lines of stale noise)
- **F18-rest** — typed excepts + debug logging on 6 silent-default paths (not sizing-critical)
- **F20** — FRED retry wrapper (3 attempts, 1s/3s backoff, transient-only)
- **F26** — interval-aware incremental fetch gate (1h >3h / 4h >6h / 1d >1d); fixed forex/stock 4H bars lagging 17-19h
- **F30** — 4 mixed-asset-class forex positions closed (net +$33.67 realised); proposer root-cause fix pending (Batch 4)
- Docs: steering file + this file updated to match actual code state

### Strategy Library deploy (2026-05-01 12:02 UTC, commit `4acfadb`)

Standalone batch driven by `STRATEGY_LIBRARY_REVIEW_2026-05.md` — web-research-backed review of the ~246-template library against 2025-2026 hedge-fund practice and live P&L.

- **R1-R7** — 7 losing templates removed: Fast EMA Crossover, SMA Proximity Entry, BB Middle Band Bounce, SMA Envelope Reversion Long/Short, BB Midband Reversion Tight, 4H VWAP Trend Continuation. Stops ~$4-8K/yr drag. Academic evidence (SSRN 5186655, Chen 2024) + live -$378/-$308/-$141 open P&L aligned.
- **C1** — VIX signal-time gate in `order_executor.execute_signal`. Blocks ENTER_LONG when VIX > 25 AND VIX_5d > +15%. Crypto exempt, 5-min cache, fail-open. Reference: Bilello post-spike research.
- **C2** — Momentum crash circuit breaker in `conviction_scorer._score_regime_fit`. Subtracts 10 points from regime_fit when SPY_5d < -3% AND VIX_1d > +10%, for LONG momentum/trend/breakout only. Floored at 5. Reference: Byun & Jeon SSRN 2900073.
- **C3** — Post-Earnings Drift Long tightening: `min_earnings_surprise_pct` 2% → 4%, added `min_revenue_growth_qoq: 0.08` ("confirmed momentum" per Lord Abbett research).
- **Q1** — AE template rotation. `alpha_edge_templates_filtered` is shuffled by hour-of-year offset each cycle so the proposer visits different AE templates across cycles instead of always the first N in definition order.
- **Q2** — AE proposal cap raised 5 → 8 when DSL templates exist. Root cause of 5-template-bottleneck identified: the cap was blocking 20 of 25 AE templates per cycle. Over 1-2 business days with Q1 rotation, all regime-eligible AE templates now get visited.

Verified post-deploy:
- 400-strategy cycle at 13:06 UTC produced 392 DSL + 8 AE — hit target exactly.
- 8 NEW Alpha Edge template types proposed this cycle (Gross Profitability Long, Price Target Upside Long, Earnings Momentum Combo Long, Earnings Momentum, Sector Rotation, Insider Buying, Revenue Acceleration, Multi-Factor Composite Long). Pre-deploy only 5 AE strategies existed in DB, mostly duplicates of 2 template types.
- 2 already activated within 30 minutes: Insider Buying LEU, Earnings Momentum APP.
- C1/C2 armed but did NOT fire (VIX=18.8, market trending_up — correct behavior).
- Regime gate at cycle output: `trending_up_strong → 36 matching templates (VIX=18.8)` with `{alpha_edge: 8}` — confirms regime filter correctly narrows AE pool; Q1+Q2 operate on the filtered pool.
- Service healthy, zero new post-deploy errors related to changes. 5 yfinance "possibly delisted" errors for MRK/COP/PSA are pre-existing F14 behavior, unrelated.

**Known regime-classification inconsistency (not new):** market_analyzer detected "HIGH VOLATILITY RANGING (57% confidence)" while proposer gate locked in `trending_up_strong`. Two-tier regime system — worth verifying in a follow-up session, but not a regression from this deploy.

### Pre-existing items (deferred, low priority)
- **Overview chart panel** — 3 separate chart components with misaligned axes. Multi-pane rewrite needed. Previous attempt failed due to lightweight-charts v5 pane API complexity. Design before coding next time.
- **Gold Momentum GOLD duplicates** — 10 copies in BACKTESTED, delete 9.
- **FMP insider endpoint** — 403/404 on current plan; using momentum proxy fallback.
- **`historical_price_cache` duplicate 1d rows** — low priority cleanup (00:00 vs 04:00 same-day entries).
- **`proposed` counter in UI** — showing all 0, counter never written. Fix or remove.
- **Session persistence** — sessions wiped on restart, users re-login. Low priority.
- **1h strategies** — still 1 BACKTESTED / 0 DEMO. No explicit gate blocks them; emergent from `min_trades_dsl_1h=15` + F07 MC annualization bug. Expect graduation to resume once F07 (Batch 4) ships on clean post-F02 data. Observe 2 weeks post-Batch 4; only nudge (`min_trades_dsl_1h` to 10 or add 1h quota) if <5 active.
- **Strategy lifespan** — avg 5.7 days. Batch 4 may rebalance naturally via stricter gate.
- **AE pipeline deferred items** — Sector Rotation template has `fixed_symbols: [XLF, XLK, XLI, XLP, XLY]` covering only 5 of 11 SPDR sectors (missing XLE/XLV/XLY/XLP/XLU/XLRE/XLC). Pairs Trading Market Neutral's DSL entry conditions are momentum-long signals, not actual pairs — z-score logic in `default_parameters` never consumed by any execution path. Both need design work, not parameter tweaks. Dedicated follow-up session.
- **Regime classification two-tier inconsistency** — sub-regime analyzer and proposer regime gate disagree (analyzer said RANGING_HIGH_VOL 57%, proposer used trending_up_strong). Not a regression, worth tracing in a follow-up.

---

## Files Changed (May 1, 2026)

### Backend
- `src/data/market_data_manager.py` — crypto symbol split (db_symbol vs normalized_symbol), DST tz normalization before resample, F26 interval-aware incremental-fetch gate (1h >3h / 4h >6h / 1d >1d)
- `src/core/monitoring_service.py` — stale-1d detection in full sync, 1d update removed from quick update, DST fix in batch yf.download, freshness SLA bundled into trailing stops
- `src/api/etoro_client.py` — DST fix in legacy yfinance path, F18-rest typed excepts
- `src/api/routers/analytics.py` — DST fix in SPY benchmark
- `src/api/routers/data_management.py` — DB lookup uses display symbol (P0 fix applied to data_management router)
- `src/execution/order_executor.py` — ATR floor: 2.5× → 1.5×, interval-aware (4H strategies use 4H ATR), position size scales on SL widen, **C1 VIX signal-time gate in `execute_signal`**
- `src/strategy/conviction_scorer.py` — ETF 12→13, Index 12→14 asset tradability scores, **C2 momentum crash circuit breaker in `_score_regime_fit` with 5-min TTL cache on SPY_5d/VIX_1d check**
- `src/strategy/strategy_proposer.py` — **Q1 AE template rotation by hour-of-year offset, Q2 AE cap 5 → 8**
- `src/strategy/strategy_templates.py` — R1-R7 losing templates removed (Fast EMA Crossover, SMA Proximity Entry, BB Middle Band Bounce, SMA Envelope Reversion Long/Short, BB Midband Reversion Tight, 4H VWAP Trend Continuation), C3 Post-Earnings Drift Long tightened
- `src/strategy/market_analyzer.py` — F18-rest typed excepts with debug logging, F20 FRED retry wrapper (3 attempts, 1s/3s backoff)
- `src/data/news_sentiment_provider.py` — F18-rest typed excepts
- `src/strategy/strategy_engine.py` — F18-rest typed excepts in datetime deserialize path
- `src/strategy/autonomous_strategy_manager.py` — F18-rest typed excepts in JSON parse
- `src/llm/llm_service.py` — F18-rest debug logging on DEMO credentials fallback
- `src/models/database.py` — `pool_pre_ping=True` (F19)
- `src/utils/symbol_mapper.py` — `normalize_symbol` renamed to `to_etoro_wire_format` (with backward-compat alias)
- `src/utils/yfinance_compat.py` — NEW module: `to_tz_aware_utc`, `normalize_yf_index_to_utc_naive`
- `src/core/trading_scheduler.py` — `invested_amount=order.quantity` on immediate position creation (UI fix)
- `config/autonomous_trading.yaml` — min_conviction_score 70→65, min_sharpe 0.4→1.0, min_sharpe_crypto 0.1→0.5, min_sharpe_commodity 0.5, `atr_sl_multiplier` removed (was dead config)

### DB migration
- `UPDATE historical_price_cache SET symbol='BTC' WHERE symbol='BTCUSD'` (+ 10 other crypto). 58,000+ rows renamed.
- `DELETE FROM historical_price_cache WHERE symbol IN (...)` — 79,785 phantom altcoin/delisted rows purged (F21).

---

## Diagnostic Scripts

```bash
# Check eToro vs DB position diff
cd /home/ubuntu/alphacent && venv/bin/python3 scripts/diagnostics/etoro_position_diff.py

# Close orphaned positions (also records P&L in DB)
cd /home/ubuntu/alphacent && venv/bin/python3 scripts/diagnostics/close_orphaned_positions.py
```
