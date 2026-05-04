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

## Current System State (May 3, 2026, ~23:45 UTC, post-warnings-log-audit)

- **Equity:** ~$480K
- **Open positions:** 80
- **Active strategies:** 60 (after late-day cycle)
- **Directional split:** ~75% LONG / ~6% SHORT
- **Market regime (equity):** `STRONG UPTREND` (20d +10%, 50d +5%, MQS 85/100 high)
- **Market regime (crypto):** `RANGING_LOW_VOL`
- **VIX:** 17
- **Mode:** eToro DEMO
- **Scheduled cycles:** daily 15:15 UTC + weekdays 19:00 UTC

**Data routing matrix (final state after today):**

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
    - "Deployment Workflow — Mandatory" (the full scp-only rule + the narrow
      autonomous_trading.yaml exception)
(2) Session_Continuation.md — full file, especially the two 2026-05-03 blocks
    (FMP primary for all intervals; log-hygiene audit + commodity 1h narrowing).
(3) AUDIT_REPORT_2026-05-02.md only if we hit something that needs the
    pre-May-2 baseline.

Confirm you've read them and begin.

==========================================================================
CONTEXT ENTERING THIS SESSION
==========================================================================

Two back-to-back sessions on 2026-05-03 shipped:

- The full data-pipeline overhaul (FMP Starter primary for non-crypto at
  all 3 intervals, Binance for crypto, Yahoo strictly as fallback for the
  8-11 premium-blocked combos).
- A log-hygiene audit that cleaned errors.log (0 new entries in 30+ min)
  and dropped warnings.log from ~55/min to ~3/2min (95%+ reduction).

Last 10 commits on main (newest first):
- 4970dae fix: warnings.log cascade cleanup + MQS on-demand MDM + commodity 1h narrowing
- 18c3315 fix: errors.log noise cleanup + MQS diagnostic + cycle summary clarity
- 61581eb fix: MarketDataManager config loader (FMP key overlay)
- 364e1cd docs: trim Session_Continuation
- 7a425e6 feat: FMP primary for all non-crypto intervals + rate-limit backoff
- cddf1f1 fix: tag quick-update synthetic bars by asset class
- 0d3643c fix: collapse legacy wire-form symbols on Data Page
- df8a5b0 fix: trust FMP 0-bar response instead of falling to Yahoo
- 474c0e0 feat: FMP Starter as primary non-crypto intraday source
- bd9e3fb refactor: single-source WF window selection

System state at session close:
- Equity: ~$480K, 80 open positions, 60 active strategies
- MQS: 85/100 "high" (equity_snapshots.market_quality_score finally
  persisting — was NULL for weeks)
- errors.log: 0 new entries since the Yahoo 1h cap guard landed
- warnings.log: only legitimate warnings (GER40 4h genuinely stale on
  Sunday; nothing else firing during cycle runs)

==========================================================================
MISSION — CI/CD + DEPLOYMENT WORKFLOW HARDENING
==========================================================================

The manual scp-restart-verify loop is the only deployment pathway today.
Every fix is: edit local → scp file → ssh restart → curl health → tail
logs → sometimes 2-3 iterations before the fix holds. This works but has
three real problems:

1. Deployment is a single point of failure — a forgotten scp, a typo in
   the remote path, or a restart-during-live-cycle can brick trading
   until someone notices. No rollback. No diff verification.

2. No pre-deploy gate — we ship Python files that parse locally but the
   actual `import` graph is only exercised at service start. A circular
   import or missing dependency surfaces as a restart loop, not as a
   caught build error.

3. No post-deploy verification checklist. Each session we improvise
   what to grep for. When a cycle completes badly, we notice by eye,
   not by automated threshold.

Your mission this session: design and ship a CI/CD layer that preserves
the scp-only deployment model (local → EC2 direct, no registry, no
Docker rebuild for a bug fix) while adding the three missing pieces:

(A) PRE-DEPLOY GATE (P1) — a `deploy/preflight.sh` script that, before
    any scp happens, runs locally:
    - Python AST parse of every modified file (what we already do ad-hoc).
    - `python -c "import src.<changed_module>"` for each changed module
      to catch circular/missing imports that AST alone misses.
    - Frontend `npm run build` if any .tsx/.ts changed.
    - Diff preview of what's being scp'd.
    - Dry-run summary: "will deploy N files, restart service, expect
      downtime ~12s".
    Fail fast and abort the scp if any step fails. This is the one
    workflow-level fix that would have caught the N+1 misindented-block
    bugs, the missing-import restart loops, and the "I forgot to deploy
    that one file" incidents from the last two weeks.

(B) DEPLOY WITH ROLLBACK (P1) — extend the scp+restart workflow to:
    - Before scp: snapshot current EC2 file (scp ubuntu@... TO local
      backup/<filename>.<timestamp>.bak). Not a "pull-from-EC2"
      violation because the backup is never re-pushed; it's a rollback
      artifact.
    - After scp: systemctl restart alphacent.
    - Health-check curl with a 30s retry window (service can take 12-25s
      to come up fully).
    - If health fails: scp the backup back, restart again, alert in a
      distinct channel ("ROLLBACK FIRED: <file> reverted to <timestamp>
      — investigate").
    - Verify errors.log didn't grow between snapshot and +60s post-start.
    Package as `deploy/safe_deploy.sh` taking a list of local paths.

(C) POST-DEPLOY VERIFICATION CHECKLIST (P2) — a `deploy/verify.sh` that
    runs the standard sanity checks and returns pass/fail:
    - curl /health 3x with 5s spacing (catches partial init).
    - errors.log line count didn't jump > N in the last minute.
    - TSL cycle summary line emitted within last 90s.
    - Latest autonomous_cycle_runs row is either running or completed
      within the last hour (catches "scheduler died silently").
    - Hourly equity snapshot created within the last 2h (catches the
      exact bug we just fixed — hourly tick not firing).
    - MarketDataManager singleton is registered (via a diagnostic
      endpoint we'll add — currently there's no way to tell from
      outside the process).

What "proper" means here:
- No new infrastructure dependencies (no Jenkins, no GitHub Actions
  runner on EC2, no Docker). The scp-based model works; we harden it.
- Scripts live in `deploy/` alongside the existing aws-setup.sh,
  cloudwatch-setup.sh, patch-api-keys.sh.
- Workflow still fits in a single terminal session. No background
  daemons.
- All three scripts compose: `preflight.sh file1 file2 && safe_deploy.sh
  file1 file2 && verify.sh` is the new canonical deploy command.

Rules:
- Proper solutions only. Fix at the root cause.
- No stopgaps — the deploy scripts have to be the single deploy path,
  not "add to the existing scp habit".
- Test each script against a trivial change (e.g. a comment-only edit
  to a Python file) before declaring done.
- Preserve the steering file's "never edit files on EC2" rule. The
  snapshot-to-local for rollback is a backup artifact, not a pull.

If any of the three phases takes 3+ hours, budget for it — this is
infrastructure, not a feature. Do not ship a patched version to "revisit
later". Later never arrives.
```

---

## Reference — DB migrations applied to prod (cumulative)

- `ALTER TABLE orders ADD COLUMN order_metadata JSON;`
- `ALTER TABLE strategy_proposals ADD COLUMN symbols JSON, ADD COLUMN template_name VARCHAR;`
- `CREATE TABLE signal_decisions (...)` with 5 indexes
- `ALTER TABLE autonomous_cycle_runs ADD COLUMN proposals_pre_wf INTEGER;`
- (From today's FMP integration) no schema changes — `historical_price_cache` already supported multi-source via the `source` VARCHAR column.
