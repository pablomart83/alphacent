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

## Current System State (May 1, 2026)

- **Equity:** ~$476,900 (+$5.4K since Apr 29 correction, record high in May)
- **Balance:** ~$61K freed
- **Open positions:** 87 | $409K deployed | +$5,560 unrealized (59 green / 28 red = 68% WR on open book)
- **Active strategies:** 64 DEMO | 109 BACKTESTED | 42 RETIRED
- **Directional split:** 199 LONG / 6 SHORT (all forex) — SHORT equity pipeline unblocked but nothing activated yet
- **Market regime:** trending_up_weak | Market Quality Score: 85/100 High (ADX 51, ATR 1.0%, VIX 18)
- **Symbol universe:** 297 instruments (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 2 crypto)
- **Scheduled cycles:** daily 15:15 UTC + weekdays 19:00 UTC

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
- Multiplier: **1.5× ATR** (standard Wilder, lowered from 2.5× May 1 — was inflating SLs 2.5x)
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

## Open Items (May 1, 2026)

### Monitor
- **First autonomous cycle after May 1 fixes** — first run on clean data. Expected: fewer activations (Sharpe ≥ 1.0 gate), backtest Sharpes on crypto may change significantly now that vol-scaling uses real data.
- **Monday market open** — watch first 5-10 orders for new ATR floor behavior. Check for `ATR floor at order time for SYMBOL (4h)` log lines with 3-4% SLs, not 8-13%.
- **Sharpe 1.0-2.0 BACKTESTED strategies (14 of them)** — decay scorer will retire underperformers naturally. Don't force.
- **Index/ETF signal flow** — with conviction tier bump, expect more SPY/QQQ/DJ30/GER40 signals passing 65 threshold.

### Still open
- **Triple EMA Alignment DSL bug** — `EMA(10) > EMA(10)` always false, 0 trades. 10-min fix.
- **Overview chart panel** — 3 separate chart components with misaligned axes. Multi-pane rewrite needed. Previous attempt failed due to lightweight-charts v5 pane API complexity. Design before coding next time.
- **Gold Momentum GOLD duplicates** — 10 copies in BACKTESTED, delete 9.
- **FMP insider endpoint** — 403/404 on current plan; using momentum proxy fallback.
- **`historical_price_cache` duplicate 1d rows** — low priority cleanup (00:00 vs 04:00 same-day entries).
- **`proposed` counter in UI** — showing all 0, counter never written. Fix or remove.

### Deferred / architectural
- **1h strategies** — still 0 active/BACKTESTED. Pipeline fixes from Apr 25 shipped but no 1h strategies have passed WF yet. Re-evaluate after a few cycles on clean data.
- **Strategy lifespan** — avg 5.7 days. Investigate whether healthy or retiring too fast.
- **Session persistence** — sessions wiped on restart, users re-login. Low priority.

---

## Files Changed (May 1, 2026)

### Backend
- `src/data/market_data_manager.py` — crypto symbol split (db_symbol vs normalized_symbol), DST tz normalization before resample
- `src/core/monitoring_service.py` — stale-1d detection in full sync, 1d update removed from quick update, DST fix in batch yf.download
- `src/api/etoro_client.py` — DST fix in legacy yfinance path
- `src/api/routers/analytics.py` — DST fix in SPY benchmark
- `src/api/routers/data_management.py` — DB lookup uses display symbol (P0 fix applied to data_management router)
- `src/execution/order_executor.py` — ATR floor: 2.5× → 1.5×, interval-aware (4H strategies use 4H ATR), position size scales on SL widen
- `src/strategy/conviction_scorer.py` — ETF 12→13, Index 12→14 asset tradability scores
- `src/utils/symbol_mapper.py` — `normalize_symbol` renamed to `to_etoro_wire_format` (with backward-compat alias)
- `src/core/trading_scheduler.py` — `invested_amount=order.quantity` on immediate position creation (UI fix)
- `config/autonomous_trading.yaml` — min_conviction_score 70→65, min_sharpe 0.4→1.0, min_sharpe_crypto 0.1→0.5, min_sharpe_commodity 0.3→0.5

### DB migration
- `UPDATE historical_price_cache SET symbol='BTC' WHERE symbol='BTCUSD'` (+ 10 other crypto). 58,000+ rows renamed.

---

## Diagnostic Scripts

```bash
# Check eToro vs DB position diff
cd /home/ubuntu/alphacent && venv/bin/python3 scripts/diagnostics/etoro_position_diff.py

# Close orphaned positions (also records P&L in DB)
cd /home/ubuntu/alphacent && venv/bin/python3 scripts/diagnostics/close_orphaned_positions.py
```
