# AlphaCent — Full System Audit
**As of 2026-05-17 · trending_up_strong regime · DEMO $479K, LIVE $9.9K**

> Written for a senior quant joining the team. Every claim is grounded in source code (file:line refs). Honest about weaknesses. Not a marketing document.

---

## 0. TL;DR

AlphaCent is a single-binary autonomous trading platform that proposes, validates, activates, monitors and retires trading strategies on its own, executes them through eToro's CFD/equity API, and surfaces every decision through a React dashboard. The system is genuinely live — one CIO-graduated strategy is currently trading real money on `4H EMA Ribbon Trend Long GOOGL` and 70 demo positions are open.

The architecture is sound: walk-forward + Monte-Carlo bootstrap + conviction scoring + graduation gate + DB-side trailing stops, all with a 30-day decision-log audit trail. The known gaps are concentrated in five places:
1. **Walk-forward bypass paths still admit regime-luck** for LONG strategies (test-dominant rescue allows `train_sharpe ≥ −0.1` against a +1.5 consistency cap that only applies to the third "excellent_oos" path).
2. **Correlation management is named but mostly dead config** — `position_management.correlation_adjustment.{enabled,threshold,reduction_factor}` is not consumed; `risk_manager.py` hardcodes 0.7 and 0.5x.
3. **Portfolio VaR is disabled** (97.97% model artefact from young equity curve), and there is no real-time portfolio-level VaR computation.
4. **Slippage is configured per-asset-class but not modelled** — backtests use a static `slippage_percent`; eToro CFDs have no fill-quality model.
5. **Several large config keys are dead** (the most important: `paper_trading.conviction_threshold` and `position_management.correlation_adjustment.*`), so the runtime threshold for paper conviction is not what the YAML or steering file says it is.

Current live state (pulled from EC2 at audit time):

| Metric | Value |
|---|---|
| DEMO equity | $479,224 |
| DEMO open positions | 70 of 1,025 lifetime |
| LIVE equity | $9,903 |
| LIVE open positions | 1 (GOOGL LONG, +$16.63) |
| Active strategies | 47 (PAPER 46 + LIVE 1, plus 267 BACKTESTED) |
| Regime | `trending_up_strong` (confidence 0.87) |
| Last cycle | 383s · 200 proposals → 24 fresh → 19 WF-passed → 9 activated → 0 promoted to PAPER · 0 signals · 0 orders |
| `errors.log` | 15,965 lines since 2026-05-01 (mostly DSL parse errors on bad templates) |

The cycle log shows 24 fresh proposals in the last full autonomous cycle producing 0 signals and 0 orders. That's not a bug per se — strategies with watchlists already saturated by the symbol-cap mechanism produce no entry signals — but it is the system's visible behaviour and any new quant should understand why before changing anything.

---

## 1. Pipeline & Architecture

### 1.1 End-to-end data flow

```
                      ┌────────────────────────────────────────────┐
                      │ External data sources                      │
                      │  Yahoo Finance (1d, 1h, 4h via resample)   │
                      │  FMP (1h/4h native, fundamentals, forex)   │
                      │  Binance (crypto 1h/4h, 2y depth)          │
                      │  Marketaux (per-ticker news sentiment)     │
                      │  FRED (macro)                              │
                      │  eToro Public API (live prices, accounts)  │
                      └──────────────┬─────────────────────────────┘
                                     │
                                     ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  src/data/market_data_manager.py — single read path              │
   │   ─ DB cache (historical_price_cache) → Yahoo → FMP → Binance   │
   │   ─ tz-aware UTC bounds, post-fetch tz_localize(None)           │
   │   ─ schema_version pinning for cache invalidation               │
   └──────────────┬───────────────────────────────────────────────────┘
                  │
                  ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  Autonomous research cycle (≤ ~15 min)                          │
   │                                                                  │
   │  Cleanup ─► Market analysis ─► Proposal (200 candidates)        │
   │      │            │                  │                          │
   │      │            │                  ▼                          │
   │      │            │          Walk-forward (per-asset windows)   │
   │      │            │           + crypto rolling 3-window vote    │
   │      │            │                  │                          │
   │      │            │                  ▼                          │
   │      │            │          Monte Carlo bootstrap (1000×, p5) │
   │      │            │                  │                          │
   │      │            │                  ▼                          │
   │      │            │          Direction-aware threshold pass     │
   │      │            │           + family cross-validation         │
   │      │            │                  │                          │
   │      │            │                  ▼                          │
   │      │            │          Conviction scoring (per-AC denom) │
   │      │            │                  │                          │
   │      │            └─────────────────►│                          │
   │      │                               ▼                          │
   │      └───────────────────► Activation (tiered Sharpe + RPT     │
   │                            + ex-post 730d veto + WR/expectancy) │
   │                                       │                          │
   │                                       ▼                          │
   │                            BACKTESTED → PAPER (on first signal) │
   └─────────────────┬────────────────────────────────────────────────┘
                     │
                     ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  TradingScheduler (signal generation, ~55 min main + 10 min      │
   │   quick) ─ DEMO pass on PAPER strategies + independent LIVE pass │
   │   on LIVE strategies (account_type='live' scoping)               │
   │                                                                  │
   │   Signal ─► Conviction gate (60/65/70/73 by mode+asset)          │
   │           ─► VIX (C1) + momentum-crash (C2) + trend (C3) gates   │
   │           ─► RiskManager.calculate_position_size (11 steps)      │
   │           ─► RiskManager.validate_signal (heat / conc / dir)     │
   │           ─► OrderExecutor.execute_signal                        │
   │              ─► Market-hours gate                                │
   │              ─► ATR floor (1.5×/2.0× ATR) → SL widening +        │
   │                  proportional size shrink                        │
   │              ─► eToro submit → optimistic position write         │
   └─────────────────┬────────────────────────────────────────────────┘
                     │
                     ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  MonitoringService (24/7, separate threads)                     │
   │   ─ Position sync 60s (account_type-scoped)                     │
   │   ─ Trailing stops 60s — DB-side enforcement                     │
   │   ─ Partial exits 5s (currently disabled, see §5.4)             │
   │   ─ Quick price update 10 min (1h bars only)                     │
   │   ─ Full price sync ~55 min (1d + 1h)                           │
   │   ─ Fundamental exits daily (earnings/revenue/sector)            │
   │   ─ Strategy decay (10→0 score) hourly                          │
   │   ─ Strategy health (5→0 score) hourly                          │
   │   ─ Zombie exits 6h (operator review only)                      │
   └─────────────────┬────────────────────────────────────────────────┘
                     │
                     ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  PostgreSQL 16 (single instance on EC2)                         │
   │   strategies · positions · orders · trade_journal               │
   │   live_strategies · graduation_approvals · strategy_proposals   │
   │   signal_decisions (30-day audit trail) · equity_snapshots      │
   │   conviction_score_logs · regime_history · system_findings      │
   │   historical_price_cache · quarterly_fundamentals_cache · ...   │
   └─────────────────┬────────────────────────────────────────────────┘
                     │
                     ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  FastAPI/uvicorn  ←  WebSocket broadcast on every state change   │
   │  React/Vite dashboard (Command, Book, Strategies, Guard,        │
   │   Research, Intel, Settings) behind nginx + Cognito auth        │
   └──────────────────────────────────────────────────────────────────┘
```

### 1.2 Tech stack

| Layer | Technology |
|---|---|
| Backend runtime | Python 3.11, single uvicorn process, asyncio + threadpool |
| Web framework | FastAPI 0.x with `/api/*` routers |
| Database | PostgreSQL 16, SQLAlchemy 2.x ORM (`src/models/orm.py`) |
| Strategy engine | vectorbt (backtest), Lark-based DSL parser, custom indicator library (17 indicators including OBV/Donchian/Keltner) |
| Frontend | React 18, Vite, TypeScript, TanStack Query, Zustand-like, Sonner toasts, Recharts/lightweight-charts |
| Real-time | WebSocket (`src/api/websocket_manager.py`), client polling for nav badge |
| Auth | AWS Cognito-style session cookie, role-based middleware |
| Process supervision | systemd unit `alphacent.service`, `ExecStartPre=deploy/patch-api-keys.sh` patches API keys from AWS Secrets Manager |
| Reverse proxy | nginx 1.18 with Let's Encrypt TLS at `alphacent.co.uk` |
| Host | EC2 t3.medium (`i-035d5576835fcef0a`) eu-west-1, 4GB RAM, 30GB EBS |
| CI/CD | GitHub Actions → SCP/SSH deploy, no container runtime |
| Logs | `logs/errors.log` · `logs/cycles/cycle_history.log` · `logs/strategy.log` · `logs/risk.log` · `logs/alphacent.log` · `logs/service_log.jsonl` (2,000-entry ring buffer) |
| Secrets | `~/.kiro_tmp` never committed; eToro/FMP/Marketaux keys live in AWS Secrets Manager, patched into `config/api_keys.yaml` at boot |

### 1.3 Deployment topology

Single-host deployment. Backend uvicorn, PostgreSQL, and frontend static build all live on the same EC2 instance. The frontend bundle is built with `VITE_API_BASE_URL=https://alphacent.co.uk` and served by nginx. The `MonitoringService` runs as background threads inside the same uvicorn process — no separate worker container, no message queue, no Celery.

**Single point of failure:** any uvicorn crash takes the entire system offline (signal gen, monitoring, trailing stops, position sync). systemd auto-restarts within ~5 seconds; the `_reconciliation_done` flag in `TradingScheduler.__init__` (line 50) ensures startup reconcile runs once before signal generation resumes.


---

## 2. Data Pipeline

The price data pipeline has three layers, each with distinct responsibilities. Confused them in the past produced silent corruption (DST crashes, intraday-provisional 1d bars). Current implementation:

### 2.1 Source-of-truth layers

**Full hourly sync — `MonitoringService._sync_price_data`**
- Writes both 1d and 1h bars to `historical_price_cache` (composite PK: symbol+interval+date).
- Caches DB data into the in-memory `_historical_memory_cache` only when fresh. Stale DB data (gap > 1.2 days excluding weekends for stock markets) queues the symbol for a Yahoo batch fetch.
- Source of truth for end-of-day 1d bars.
- Per-ticker retry capped at 20 misses (defence-in-depth against partial Yahoo batch returns).

**Quick price update — `MonitoringService._quick_price_update`** (every 10 min)
- Touches **only 1h bars** — never 1d.
- Updates the current 1h bar's OHLC with a live tick OR appends a new bar on hour rollover.
- Rationale (and a previous bug): 1d bars are end-of-day data. Building an intraday "today" 1d bar misled daily indicators (RSI(14) treated it as complete).

**Yahoo / yfinance handling — `src/utils/yfinance_compat.py`**
- All yfinance calls pass tz-aware UTC datetimes. Naive datetimes trigger yfinance's local-tz inference, which crashes on DST-ambiguous hours (e.g. 2025-11-02 01:30 in `America/New_York`).
- Two helpers: `to_tz_aware_utc()` for input conversion, `normalize_yf_index_to_utc_naive()` for post-return safety (DST crashes in `pd.resample` and `Timestamp.to_pydatetime` are prevented by `tz_localize(None)` after the fetch).
- Yahoo returns 1h for 4H requests — `_fetch_historical_from_yahoo_finance` resamples to 4H, normalising tz BEFORE resample.

**FMP for non-crypto intraday — `src/api/fmp_ohlc.py`**
- `is_supported(symbol, interval)` gates whether FMP serves 1h/4h natively for a symbol.
- Used because Yahoo's 1h endpoint has a hard ~7-month cap. FMP-served stocks/ETFs/forex/gold/silver/oil/copper return 5+ years of 1h data.
- This is consulted by `walk_forward_validate` (see §3.3) to decide whether to truncate the WF window.

**Binance for crypto — `src/api/binance_ohlc.py`**
- Used for crypto 1h/4h backtests because Binance has no auth requirement, runs 24/7, and serves ~2 years of 1h depth.
- Fast path through `_fetch_binance_klines` invoked from `walk_forward_validate` when primary symbol ∈ `DEMO_ALLOWED_CRYPTO`.

### 2.2 Symbol canonicalisation — `src/utils/symbol_mapper.py` & `symbol_normalizer.py`

| Format | Where used | Examples |
|---|---|---|
| **Display form (DB)** | `positions`, `orders`, `trade_journal`, `historical_price_cache` | `BTC`, `ETH`, `AAPL`, `EURUSD`, `SPX500`, `GOLD` |
| **eToro wire** | `to_etoro_wire_format()` → only for eToro API calls | `BTC` → `BTCUSD`, `EURUSD` stays `EURUSD` |
| **Yahoo ticker** | `to_yahoo_ticker()` → only for yfinance calls | `BTC` → `BTC-USD`, `SPX500` → `^GSPC`, `OIL` → `CL=F` |

The display form is canonical. Storing eToro wire format anywhere in the DB is forbidden (a previous bug). Two functions named `normalize_symbol` exist for backward compatibility — `symbol_mapper.normalize_symbol` aliases `to_etoro_wire_format`; `symbol_normalizer.normalize_symbol` resolves instrument IDs. New code should call the explicit names.

**Special symbol sets (`src/utils/symbol_mapper.py`):**
- `DAILY_ONLY_SYMBOLS = {ALUMINUM, ZINC, NICKEL, PLATINUM}` — LME metals; no Yahoo intraday data. The strategy_engine and proposer skip these on intraday/4h backtests.
- `NO_1H_SYMBOLS = {OIL, COPPER}` — valid 4h via FMP but no 1h. Filtered out of 1H-only watchlists.

### 2.3 Cache TTL summary

| Cache | TTL | Source |
|---|---|---|
| `historical_price_cache` (DB) | n/a — gap-driven refresh | bar age vs current time minus weekends |
| Yahoo `cache_duration` | 3,600 s (1h) | YAML `data_sources.yahoo_finance.cache_duration` |
| FMP earnings-aware | 7d default / 1d during earnings window / 7d for earnings calendar | YAML `data_sources.financial_modeling_prep.earnings_aware_cache` |
| In-memory `_historical_memory_cache` | per-call invalidation by interval (1.5h for 1h, 4.5h for 4h, 28h for 1d) | `monitoring_service.py:1395` |
| Cache schema version | bumped when crypto thresholds / per-asset costs / WF windows change | `strategy_proposer._compute_wf_cache_schema_version` |

### 2.4 Known data-pipeline gaps

- **FMP insider endpoint returns 403/404** on the current plan. `fundamental_data_provider.calculate_insider_net_buying` uses a momentum-proxy fallback. This degrades the conviction scorer's `_score_fundamental_quality` insider component to a noisier signal; AE strategies that rely on insider buying (Sector Rotation, Insider Buying Long) score lower than they should.
- **FRED endpoint occasionally returns 500** — surfaced as the very first line of `errors.log`. `market_analyzer.get_market_context` fails-open and uses cached values.
- **Marketaux free-tier returns 3 articles per symbol** — a calibration the conviction scorer reflects by capping news sentiment at ±1 (effectively a tiebreaker).
- **`config/.market_stats_cache.json` is persisted to disk** so the 2h market-stats cache survives restarts. Without it, the proposer re-analyses 118 symbols on every cold start (~90 s on a t3.medium).

---

## 3. Strategy Proposer & Walk-Forward

### 3.1 Watchlist construction — `strategy_proposer._build_watchlists`

Each (template, primary_symbol) assignment produces a multi-symbol watchlist used by signal generation. The watchlist size defaults to 10 in code but YAML `autonomous.watchlist_size = 5` is what's actually loaded.

Three-phase construction (`strategy_proposer.py:6481-6612`):

**Phase 1 — WF-validated symbols.** Pulled from `config/.wf_validated_combos.json` (TTL 14 days), restricted to the same asset class as the primary, filtered by:
- Not in `_active_pairs` (template, primary already running in pipeline).
- Not in `_zero_trade_blacklist` at threshold 2 (TTL 3 days).
- Not LME-daily-only on intraday/4h templates.
- Not in `NO_1H_SYMBOLS` on 1H-only templates.

Sorted by Sharpe descending — best performers first.

**Phase 2 — top-scored unvalidated symbols.** Pulled from `_last_scored_pairs` (computed by `_match_templates_to_symbols`).

**Phase 3 — neglected-symbol slot reservation.** `max(1, int(watchlist_size * 0.15))` slots reserved for symbols not seen in any proposal in the last 7 days. `_get_neglected_symbols` reads from `strategy_proposals`; 5-min process cache. This is the explicit fix for the TSLA-style audit case where a negatively-scored symbol gets locked out for weeks while it rallies.

### 3.2 Proposal flow — DSL phase vs Alpha Edge phase

`generate_strategies_from_templates` (`strategy_proposer.py:4211-4995`):

| Cap | Value | Source |
|---|---|---|
| Per-cycle proposals | 200 | YAML `autonomous.proposal_count` |
| Alpha Edge slot cap (when DSL templates exist) | `min(8, len(ae_templates))` | code line 4388 |
| Alpha Edge slot cap (when no DSL) | `len(ae_templates)` | line 4390 |
| Per-template AE watchlist size | 5 symbols | line 4667 |
| Watchlist size per DSL strategy | YAML `autonomous.watchlist_size = 5` | line 4415 |

**Alpha Edge template rotation** (line 4683): `_rotation_offset = int(time.time() // 3600) % len(alpha_edge_templates_filtered)`. Rotates ordering once per hour so all 25 AE templates eventually get a shot. Without this, templates defined later in `strategy_templates.py` never reached the loop and 0 instances were produced for ~5 templates (Sector Rotation, Post-Earnings Drift, 52-Week High Momentum, Analyst Revision, Share Buyback).

**Active-pair dedup is primary-only.** `(template_name, symbols[0])` is treated as "already running"; subsequent watchlist entries remain available as future primary candidates. This is the explicit fix for crypto strategies, which only have 6 symbols total — the previous (whole-watchlist) dedup created a death spiral.

### 3.3 Walk-forward validation — `strategy_engine.walk_forward_validate`

Per-asset/per-interval window selection driven by `_select_wf_window` (`strategy_proposer.py:191-289`). Selection order:

| Key | Train (d) | Test (d) | Notes |
|---|---|---|---|
| `crypto_1d_longhorizon` | 365 | 180 | For Crypto 21W MA Trend Follow / Vol-Compression / Weekly Trend Follow / Golden Cross |
| `crypto_1d` | 180 | 90 | All other 1d crypto |
| `crypto_4h` | 120 | 60 | |
| `crypto_1h` | 90 | 45 | |
| `non_crypto_1d` | 730 | 365 | |
| `non_crypto_4h` | 365 | 365 | |
| `non_crypto_1h` | 365 | 365 | |
| Fallback | YAML `train_days=365` | `test_days=180` | |

**Data-source-aware capping** (`strategy_engine.py:1654-1730`): non-crypto 1h is capped at 180/90 unless the symbol is FMP-supported (in which case `non_crypto_1h` window applies). Non-crypto 4h is capped at 240/120 unless FMP-supported. Crypto goes to Binance — no cap.

**Sharpe annualisation correction** (`strategy_engine.py:3580-3609`):
- Crypto 1h: no correction (8,760 hrs/yr is correct for 24/7).
- Forex 1h: × √(6,240/8,760).
- Stocks/ETFs/indices 1h: × √(1,764/8,760) (252 days × 7 hrs).
- 4h equivalents proportionally scaled.
- This is critical: vectorbt with `freq="1h"` annualises by √8,760 by default; without correction, stock 1h Sharpes were inflated by ~2.2×.

### 3.4 Crypto rolling walk-forward — `walk_forward_validate_rolling`

Crypto strategies use a 3-window majority-vote WF (`strategy_engine.py:1889-2192`):
- Windows evenly spaced across available history (capped at 5 years).
- Pass condition per window: `not is_overfitted AND test_sharpe is not None AND test_sharpe > 0`.
- `overall_overfitted = pass_count < 2` (need majority of 3).
- **Canonical window is the BEST passing one** (highest test Sharpe), not the most recent. This was a bug — using the most recent window when it was the failing one caused activation to see negative returns from a non-passing window while genuine edge sat in another window.
- Aggregated trade counts across passing windows are injected into the canonical `test_results.total_trades` so downstream `min_trades` checks see the full sample.

### 3.5 Monte Carlo bootstrap — `strategy_proposer.py:2072-2284`

| Parameter | Default (equity) | Crypto/commodity (heavy-tail) | 1h equity |
|---|---|---|---|
| `MC_ITERATIONS` | 1,000 | 1,000 | 1,000 |
| Min trades for bootstrap | 15 | 20 | 15 |
| Percentile checked | p5 | p10 | p5 |
| Floor | ≥ 0.0 | ≥ −0.2 | ≥ −0.1 |

Bootstrap method: `numpy.random.choice(arr, size=len(arr), replace=True)` — sample with replacement. Sharpe per iteration = `(sample.mean() / sample.std()) * sqrt(trades_per_year)` where `trades_per_year = (n_trades / test_window_days) * 252` derived from the actual `test_results.backtest_period`.

**Heavy-tail bypass for n < min_trades**: requires `(train_S > 0.2 AND test_S > 0.2) OR (test_S ≥ 1.0 AND train_S ≥ −0.1) OR (train_S ≥ 1.0 AND test_S ≥ −0.1)`. Equity bypass: pass-through (no consistency check) — this is a known asymmetry; LONG equity strategies with n < 15 trades skip MC entirely.

### 3.6 WF validation paths (post-MC)

| Path | Conditions | Source |
|---|---|---|
| Primary | `train_S > min_S AND test_S > min_S AND test_return ≥ min_return AND test_WR ≥ min_WR` | `strategy_proposer.py:2400-2402` |
| Test-dominant | `train_S ≥ −0.1 AND test_S ≥ min_S AND test_return ≥ min_return AND test_WR ≥ min_WR AND (NOT short OR test_trades ≥ 4)` | 2406-2412 |
| Excellent-OOS (LONG only) | `train_S ≥ −0.3 AND test_S ≥ 2×min_S AND test_trades ≥ 5 AND test_WR ≥ min_WR AND NOT short AND (test_S − train_S) ≤ 1.5` | 2418-2425 |
| SHORT relaxed-OOS | **rejected** (no rescue path for shorts) | 2426-2432 |
| Pass-2 relaxed | Only when `len(validated) < 10`; requires `train_S > 0.1 AND test_S > 0.1 AND s.id ∈ mc_passed_ids` | 2702-2727 |
| Family cross-validation | ≥4/6 symbols cleared `S > 0.3 AND return > 0 AND ≥2 trades`; promoted symbols must clear minimal bar themselves | 2486-2675 |

**SHORT-side tightening** (lines 2367-2375): `min_sharpe = max(min_sharpe, min_sharpe + 0.3)` and `short_min_trades = 4`. This is the explicit fix from the TSLA audit (Apr 2026): SHORT templates were systematically overfitting to recent down-legs and firing into reversals. Removing the relaxed-OOS path for SHORTs alone has produced the desired effect — current paper trades on SHORT are non-zero again post-conviction-fairness fixes (May 15).

**Direction-aware thresholds (`backtest.walk_forward.direction_aware_thresholds`):**

| Regime | LONG (return / Sharpe / WR) | SHORT (return / Sharpe / WR) |
|---|---|---|
| Default | 0.0 / 0.30 / 0.45 | 0.0 / 0.30 / 0.45 |
| Ranging | −0.02 / 0.15 / 0.40 | 0.0 / 0.30 / 0.45 |
| Trending up | 0.0 / 0.30 / 0.45 | −0.02 / 0.15 / 0.40 |
| Trending down | −0.02 / 0.15 / 0.40 | 0.0 / 0.30 / 0.45 |
| High vol | −0.01 / 0.20 / 0.42 | −0.01 / 0.20 / 0.42 |

These can only loosen, never tighten (only `min(base, relaxed)` is taken).

### 3.7 Caches & blacklists

| Cache | Threshold / TTL | Path |
|---|---|---|
| WF results cache | TTL 24h, key `(template_name, primary_symbol)` | in-memory `_wf_results_cache` |
| WF failed cache | persisted, TTL 24h | `config/.wf_failed_cache.json` |
| WF validated combos | persisted, TTL 14 days | `config/.wf_validated_combos.json` |
| Zero-trade blacklist | threshold 2, TTL 3 days | `config/.zero_trade_blacklist.json` |
| Rejection blacklist | threshold 3, cooldown 14 days, regime-scoped early expiry after 3d age | `config/.rejection_blacklist.json` |
| Market stats | 2h TTL, persisted | `config/.market_stats_cache.json` |

The rejection blacklist is **regime-scoped**: entries recorded under `trending_down` expire when current regime is `trending_up` and vice versa (after a 3-day minimum age). This is the explicit fix for the lockout problem identified in the TSLA audit.

### 3.8 Performance feedback — `apply_performance_feedback`

Reads `trade_journal.get_performance_feedback()` and produces three state dicts:

**Template weights** (lines 7847-7878):
- `wr_component = 1.0 + (wr − 50.0) / 50.0`
- `pnl_component = 1.0 + max(−0.5, min(0.5, avg_pnl / 100.0))`
- `raw_weight = 0.6 × wr_component + 0.4 × pnl_component`
- Confidence scaling: `weight = 1.0 + (raw_weight − 1.0) × min(1.0, total_trades / 20.0)`
- Clamped to `[0.4, 1.5]`.

**Symbol scores** (lines 7886-7929):
- `recency_weight` from trade_journal (14-day half-life exponential), floor 0.2.
- `score = (wr − 50) × 0.5 + avg_ret × 10`
- + P&L bonus `min(10, total_pnl / 50)` (or `max(−10, total_pnl / 50)` for losses)
- × confidence `min(1, total_trades / 15)`
- × recency
- Capped at ±15.

**Regime-specific template preferences**: `feedback["regime_performance"][regime]["best_template_win_rates"]` copied directly.

This feedback flows into `_match_templates_to_symbols` as a multiplicative adjustment on `base_score` for templates and an additive ±15 bonus for symbols, plus a `+8` directional-rebalance bonus when a symbol has all-one-side losing history and the template is counter-direction.

### 3.9 Known proposer gaps

- **Pass-2 relaxed path bypasses MC bootstrap** — but only when `len(validated) < 10`. In practice this fires every 2-3 cycles and admits strategies with `test_S > 0.1` (very loose).
- **The "excellent_oos" path's consistency gate `(test_S − train_S) ≤ 1.5` does not apply to the test-dominant path** — a strategy with `train_S = −0.1, test_S = 1.4` passes test-dominant cleanly. Consider adding the gate to test-dominant for symmetry.
- **`alpha_edge.rejection_blacklist.threshold=3, cooldown_days=30`** in YAML is **not consumed**; the proposer hardcodes 3 / 14 days. Dead config.
- **`bootstrap_service.py`** is unrelated to MC bootstrap — it's a CLI starter-strategy generator wrapping `LLMService`. Not invoked by the autonomous cycle.


---

## 4. Conviction Scorer

`src/strategy/conviction_scorer.py` (1,455 lines). Two scoring paths chosen at `score_signal` based on `strategy.metadata.strategy_category == 'alpha_edge'`.

### 4.1 Per-asset-class effective denominators

The 111-point DSL theoretical max includes carry(5) and crypto cycle(5) that only apply to forex and crypto respectively. Normalising stock/etf/commodity/index strategies against 111 structurally depressed their scores by ~9 pts vs what they could actually earn. Per-asset effective denominators (lines 102-110):

| Path | Components | Denominator |
|---|---|---|
| DSL stock/ETF | WF(40) + Sig(25) + Reg(20) + Asset(15) + News(1) | 101 |
| DSL forex | WF(40) + Sig(25) + Reg(20) + Asset(13) + Carry(5) + News(1) | 104 |
| DSL crypto | WF(40) + Sig(25) + Reg(20) + Asset(15) + Crypto(5) + News(1) | 106 |
| DSL commodity | WF(40) + Sig(25) + Reg(20) + Asset(12) + News(1) | 98 |
| DSL index | WF(40) + Sig(25) + Reg(20) + Asset(14) + News(1) | 100 |
| Alpha Edge | DSL(111) + Fundamental(15) + Factor(6) | 132 |

Final normalisation: `total_score = min(100.0, total_score * (100.0 / theoretical_max))`.

### 4.2 The 9 components

**1. Walk-forward edge (max 40)** — `_score_walkforward_edge`
- OOS Sharpe × trade-confidence (0–20): `sharpe_pts = min(20.0, 8.0 + 6.0 * log(1 + test_sharpe))` × `min(1.0, sqrt(trades / denom))`. Denominator is 8 for low-freq SHORT mean_reversion/volatility (Parabolic, Exhaustion Gap, BB Squeeze Reversal, Volume Climax) — these setups fire 3–6× per year by design and 15 was halving their score. 15 for everything else.
- Trade count additive bonus (0–7): ≥15→7; ≥8→5; ≥4→3; ≥2→1.
- Win rate quality (0–8): ≥0.65→8; ≥0.55→6; ≥0.48→4; ≥0.40→2.
- Train/test consistency (0–5): both positive → 2 + ratio×3; test positive but train negative → 1.
- WF degradation penalty (0 to −7), gated by trade count: trades ≥ 8 absorbs softer penalty (−3 / −1.5 / 0); trades < 8 uses full (−7 / −4 / −2). This was the May 15 fix — PFE SHORT 100% WR, deg=−470 was a 4-trade rare setup, not regime luck.

**2. Signal quality (max 25)** — `_score_signal_quality`
- AE path: `min(1.0, signal.confidence) * 15.0` (genuine confidence from FMP analyst-revision count etc.).
- DSL path: signal persistence (bars in entry condition over last 10), strategy-type-aware:
  - Mean-reversion: 1 bar→12, 2-3→15, 4-5→8, 6+→3 (fresh oversold = best).
  - Other: 1→5, 2-3→9, 4-6→12, 7-8→14, 9-10→15 (longer = stronger trend).
- R:R quality (both paths, 0–10): rr=tp/sl; ≥2.5→10, ≥2.0→8, ≥1.5→5, ≥1.0→2, <1.0→0.

**3. Regime fit (max 20)** — `_score_regime_fit`
- Strong match→20, neutral→12, weak→**5 floor (never 0)** because WF already validated the strategy.
- **Uptrend SHORT exemption** (lines 580-586): SHORT mean_reversion/volatility/trend_following templates score **20/20** in any `trending_up*` regime. They are the hedge waiting for the correction.
- **C2 momentum-crash penalty** (lines 626-644): when SPY 5d return < −3% AND VIX 1d change > +10%, LONG momentum/trend_following/breakout strategies get `−10` (floor at 5). 5-min TTL cache.

**4. Asset tradability (max 15)** — `_score_asset_tradability`
- Tier 1 = 15: SPY, QQQ, AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, BTC, ETH, EURUSD, GBPUSD, USDJPY, SPX500, NSDQ100.
- Tier 2 = 13: large-caps, major sector ETFs, SOL/XRP, indices DJ30/GER40/UK100.
- Tier 3 = 13 ETFs / 13 forex / **14 indices** / **12 commodities** / **12 stocks** (post May 15 rebalancing — stocks bumped 10→12, commodities 11→12, indices 12→14).
- Tier 5 (NEAR) = 8.
- Bonus +2/+1 for stocks with passing fundamental report.

**5. Fundamental quality direction (±15)** — Alpha Edge only
- 5 components × ±3 each: earnings surprise, revenue growth, insider net buying, ROE, share dilution.
- Direction-aware: LONG signals add raw_score; SHORT signals add −raw_score. Quality SHORT on weak company → bonus.

**6. Carry bias (±5)** — forex only
- |carry_diff| ≥ 3% → ±5; ≥ 1% → ±3; else ±1. Sign by direction (long base + positive diff = with carry).

**7. Crypto cycle (±5)** — crypto only
- `accumulate→+5, hold→+2, reduce→−3, avoid→−5` from `market_analyzer.get_crypto_cycle_phase()`.

**8. News sentiment (±1)** — stocks only, tiebreaker
- Marketaux 3-article free tier. Direction-aware sign flip. Pure DB lookup at signal time (no API call).

**9. Factor exposure (±6)** — Alpha Edge only
- Regime-aware tilts: ranging → favour low-beta defensive; trending-up LONG → favour high-beta + revenue-growth offensive. Universal `pe_ratio > 60 → −2` LONG penalty.

### 4.3 Conviction thresholds

| Mode / Asset | YAML key | Effective threshold |
|---|---|---|
| DSL paper (default) | `alpha_edge.min_conviction_score` | **70** |
| DSL paper crypto | `alpha_edge.min_conviction_score_crypto` | **62** |
| Live (default) | `live_trading.conviction_threshold` | **73** |
| Live crypto | `live_trading.conviction_threshold_crypto` | **67** |
| Per-LIVE pair override | `live_strategies.conviction_min` | CIO-set at graduation (default 73) |

**Wiring status — `paper_trading.conviction_threshold` separation is partial:**
- YAML carries `paper_trading.conviction_threshold: 60` and `paper_trading.conviction_threshold_crypto: 55`.
- Settings → Paper Trading page round-trips correctly via `GET/PUT /config/paper-trading` (`src/api/routers/config.py:1815-1885`).
- **`strategy_engine.generate_signals` (line 5573-5576) reads only `alpha_edge.min_conviction_score` / `alpha_edge.min_conviction_score_crypto`** — the signal-time runtime gate doesn't branch on `account_type` for the threshold value.
- The Risk Limits Settings page writes `conviction_threshold` to `alpha_edge.min_conviction_score` (`config.py:1553-1558`); this is what's actually controlling the runtime DEMO/PAPER threshold today, despite the visual separation.
- Intel `H4` (`intel_analyst.py:2009-2040`) flags this divergence directly — the check exists because the separation is intentional but not yet plumbed to the runtime.
- **What's needed to complete the separation**: in `strategy_engine.generate_signals`, branch the threshold by `account_type` (or by `is_paper` resolved from strategy status), reading `paper_trading.conviction_threshold` for paper and `alpha_edge.min_conviction_score` for everything else. The LIVE pass already overrides via `conviction_override` — paper just needs the same plumbing.

---

## 5. Activation Pipeline — `evaluate_for_activation`

`src/strategy/portfolio_manager.py:612-1606`. The longest single function in the codebase (~1,000 lines) and the most consequential — a strategy passes here, it goes live next signal cycle.

### 5.1 Tier system

| Tier | Sharpe | Max allocation |
|---|---|---|
| 1 (high confidence) | ≥ 1.0 | 30% |
| 2 (medium) | ≥ 0.5 | 15% |
| 3 (low) | ≥ 0.3 (DSL) / ≥ 0.2 (AE) | 10% |
| Reject | below | 0 |

### 5.2 Threshold resolution chain

The function reads YAML `activation_thresholds` then merges `paper_trading.activation_thresholds` over it (paper overlay). Then applies, in order:

1. **Asset-class Sharpe override** (lines 781-842): crypto → `min_sharpe_crypto`, commodity → `min_sharpe_commodity`, index → `min_sharpe_index`.
2. **Timeframe multipliers** (lines 854-885): 1h/2h × 0.67 + WR−0.05; 4h × 0.80 + WR−0.03; 15m/30m × 0.44 + WR−0.07.
3. **Direction-aware regime relaxation** (lines 891-939): only loosens.
4. **VIX-aware adjustment** (lines 941-977): VIX>25 → Sharpe × 1.4, drawdown × 0.75; VIX<15 → unchanged.

YAML live values:

| Key | Live | Paper overlay |
|---|---|---|
| `min_sharpe` | 1.0 | 0.5 |
| `min_sharpe_crypto` | 0.3 | 0.2 |
| `min_sharpe_commodity` | 0.5 | 0.3 |
| `min_sharpe_index` | 0.7 | (no overlay) |
| `min_win_rate` | 0.45 | 0.4 |
| `min_win_rate_crypto` | 0.3 | 0.25 |
| `max_drawdown` | 0.25 | (no overlay) |
| `disable_min_return_per_trade` | false | **true** |
| `disable_avg_loss_gate` | false | **true** |

### 5.3 Gate sequence (in order applied)

1. **Ex-post 730d veto** (lines 715-756): if `expost_730d_trades ≥ 10` and `expost_730d_sharpe < floor` → reject. Floor is `−0.5` for crypto primary, `0.0` otherwise. Fail-open if metadata missing.
2. **Tier check + Sharpe gate** (lines 980-998): `tier == 0 OR sharpe < threshold` → reject UNLESS family-cross-validated and `sharpe > 0`.
3. **Drawdown gate** (lines 1001-1006): `max_drawdown > drawdown_threshold` → reject (`>`, not `≥`).
4. **Expectancy / win-rate gate** (lines 1015-1077):
   - Paper mode (`disable_avg_loss_gate=true`): skip expectancy; enforce raw `WR < min_WR` floor only.
   - Otherwise, if `total_trades ≥ 15 AND avg_win > 0`: compute `expectancy = (avg_win × WR) − (|avg_loss| × (1−WR))`. Pass if positive, hard floor 25% WR. Reject if negative regardless of WR.
   - If `total_trades < 15`: fall back to raw WR gate.
5. **R:R gate** (lines 1081-1095): `rr = |avg_win/avg_loss|`; `min_rr = max(0.4, 1.0 − win_rate)`. 67% WR → 0.4:1; 50% → 0.5:1; 40% → 0.6:1.
6. **min_trades resolution** (lines 1101-1136): chain — commodity → crypto+4h → AE → crypto+1h → crypto+1d → 4h → 1h → 1d. SHORT relax: `min_trades = max(2, min_trades − 1)`.
7. **Sharpe-exception bypass** (lines 1137-1170): `total_trades ≥ 3 AND wf_test_sharpe ≥ 2.0` bypasses min_trades. Family-CV: `total_trades ≥ 2`.
8. **Net-return gate** (line 1219): `total_return < 0` → reject. (vectorbt's `total_return` is already net of cost.)
9. **Avg-loss gate** (`autonomous_strategy_manager.py:2258-2317`, **runs separately before this function**): when `total_trades ≥ 20`, computes `avg_loss_pct = avg_loss_dollars / avg_position_size`, with sanity guard skipping >100%. Multiplier 5×/4×/3× for 1h/4h/1d. **No paper-mode disable here** — this gate fires regardless of `disable_avg_loss_gate`.
10. **RPT (return-per-trade) gate** (lines 1240-1546):
    - Paper mode (`disable_min_return_per_trade=true`): skip entirely.
    - Otherwise: read per-asset-class `min_return_per_trade.{asset_class[_interval]}` from YAML.
    - **Regime-aware crypto floor**: only for crypto. `_crypto_rtc = 0.0116`; multiplier ranges 0.6× (ranging) to 1.5× (trending strong). Resolves regime via `strategy.metadata.market_regime` or live `MarketAnalyzer.detect_sub_regime(['BTC','ETH'])`.
    - **Per-template override**: `strategy.metadata.min_rpt_override` can lower (never raise) the floor; safety floor at 60% of config value.
    - **Per-position normalisation** (lines 1411-1480): `position_size_pct = avg_trade_value / init_cash`; `return_per_trade = raw_rpt / position_size_pct`. The pre-fix raw_rpt was understated by 1/position_size_pct (typically 3-10×).
11. **Edge-ratio observability** (lines 1239-1294): persists `edge_ratio / gross_per_trade / cost_per_trade` to `strategy.strategy_metadata`. **Does not gate.**

### 5.4 Auto-activation tier allocations

`auto_activate_strategy` (`portfolio_manager.py:1608+`):
- Sharpe > 1.5 + confidence > 0.7 → 3.0% allocation
- Sharpe > 0.8 → 2.0%
- Else (≥ 0.3) → 1.0%

These percentages drive `strategy_allocation_pct` which `RiskManager.calculate_position_size` Step 5 reads as a concurrent-position cap (`max_concurrent = max(1, round(allocation_pct / 0.5))`). 1% → 2 concurrent, 2% → 4, 3% → 6.

### 5.5 Known activation gaps

- **Avg-loss gate has no paper-mode disable** (`autonomous_strategy_manager.py:2258`). Paper strategies with 20+ trades and avg_loss > N×SL are still rejected at activation regardless of `paper_trading.activation_thresholds.disable_avg_loss_gate`.
- **Family-cross-validation bypass admits strategies with as little as 2 test trades** (line 1156). The family-level evidence is supposed to compensate, but a 2-trade test sample crossed with family score 0.67 is statistically very thin.
- **The `min_trades_alpha_edge=6` resolution is now correct** — the May 1 fix moved the AE branch above the interval branches so 4h AE strategies don't hit `min_trades_dsl_4h=8`.

---

## 6. Position Sizing — `RiskManager.calculate_position_size`

`src/risk/risk_manager.py:757-1370`. The 11-step pipeline (paper has its own short-circuit path).

### 6.1 The 11 steps

| Step | What | Formula / value |
|---|---|---|
| 0 | Live balance refresh | Re-read latest `AccountInfoORM.balance` from DB (per-order, not stale account object) |
| 1 | Base risk per trade | `BASE_RISK_PCT = 0.006` (0.6% of equity) |
| 2 | Confidence scalar | floor 0.30; `0.5 + 0.5 × (conf − 0.30) / 0.70`; range 0.5×–1.0× |
| 3 | Vol scaling | `min(1.5, max(0.10, 0.16 / realized_vol))`; Yang-Zhang/Parkinson/EWMA via `estimate_realized_volatility` |
| 4 | Risk → size | `position_size = (equity × risk_pct × vol_scalar) / stop_loss_pct` |
| 5 | Strategy concurrent cap | `max_concurrent = max(1, round(strategy_allocation_pct / 0.5))` |
| 6 | Symbol cap | 5% of equity (was 3%, raised May 2). Counts both filled positions and pending entry orders. |
| 7 | Sector soft cap | 30% of equity → halve size |
| 8 | Heat cap | 30% portfolio (was 8%). `current_heat = Σ(position_value × 0.06)` proxy. |
| 9 | Drawdown sizing + MQS | DD>10% → ×0.25; DD>5% → ×0.5; MQS<40 → ×0.7; MQS=normal → ×0.85 |
| 10 | Available balance cap | `min(size, available_balance)` |
| 10b | Per-pair loser penalty | `(template, symbol) ≥ 3 closed trades AND net P&L < 0` → ×0.5 |
| 10c | Conviction-tier sizing | score ≥80 → ×1.30; ≥75 → ×1.15. Suppressed if any penalty fired. |
| 11 | Minimum floor | $2,000. Penalised strategies don't get bumped (return 0). |

### 6.2 Paper flat sizing

When `is_paper=True` (called from `TradingScheduler` for non-LIVE strategies):
- Bypass all scaling, use `paper_trading.flat_position_size = $5,000`.
- Only enforce: 5% symbol cap and available balance.
- Rationale: every paper strategy gets equal data quality. Graduation gate is the quality filter.

### 6.3 LIVE virtual/real mirror sizing

YAML `live_trading`:
- `virtual_balance: 10000` (configured live account size)
- `real_investment: 1000` (actual capital deployed)
- `mirror_ratio: 0.1` (virtual sizes scaled by 0.1 to fit real capital)
- `base_risk_pct: 0.006` (0.6%, same as DEMO)
- `min_order_size: 200` / `max_order_size: 1500`
- `symbol_cap_pct: 0.20` (LIVE allows 20% per symbol vs 5% on DEMO)
- `portfolio_heat_cap: 0.90` (LIVE much looser than DEMO 30% — small account, single position dominates)

### 6.4 ATR floor at order time — `order_executor.py:233-330`

After sizing, the order executor applies a final ATR floor:
- Fetches 14-period ATR at the strategy's own timeframe (4h for 4h strategies, 1d for daily).
- Multiplier: **1.5×** for daily, **2.0×** for 4h (matches the trail multiplier; the `atr_sl_multiplier` YAML key is unused — code is the source of truth).
- Max SL clamps: stock/ETF 9%, leveraged ETF 20%, crypto 15%, forex 4%.
- When SL widens beyond the strategy's configured value: `new_size = old_size × old_sl / new_sl` to preserve dollar risk. Floor at $2,000 before this re-sizing.
- Spread adjustment: SL extended by spread%, TP scaled to maintain R:R.

---

## 7. Signal Generation & Order Execution

### 7.1 Signal-time runtime gates

Three gates sit between signal emission and order submission, all in `OrderExecutor.execute_signal`:

**C1 — VIX entry gate** (lines 492-555):
- Block ENTER_LONG when VIX > 25 AND VIX 5d change > +15%.
- Crypto (BTC/ETH) exempt.
- 5-min TTL cache.
- Fail-open on data error.

**C2 — Momentum-crash penalty** (in `conviction_scorer._score_regime_fit`):
- Already discussed in §4.2. Scoring penalty, not a hard gate.

**C3 — Trend-consistency gate** (lines 558-665):
- Block ENTER_SHORT when stock above rising 50d SMA OR 1-ATR-drop in 3d AND within 3% of 20d low (oversold bounce).
- Symmetric block on ENTER_LONG when below falling 50d SMA.
- Crypto/forex exempt.
- 5-min TTL cache per (symbol, action).
- Catches the TSLA-style late-stage downtrend SHORT setups.

### 7.2 Order execution flow

`OrderExecutor.execute_signal` (lines 106-470):
1. C1 VIX gate (LONG only).
2. C3 trend-consistency gate.
3. Min order size check.
4. Determine side/order_type from `SignalAction`.
5. Fetch live price via `get_market_data` (eToro `sapi/trade-real/rates` first, Yahoo fallback).
6. Compute SL/TP rates from percentages.
7. ATR floor logic + spread adjustment + size proportional shrink.
8. Create `Order` object with `etoro_order_id=None`, `status=PENDING`.
9. Market hours gate (`market_hours_manager.is_market_open`).
10. Submit to eToro.
11. Optimistic position write (placeholder `etoro_position_id=pending_<order_id>`).
12. Decision-log write (`stage="order_submitted"`).

### 7.3 Trading scheduler — `_run_trading_cycle`

`src/core/trading_scheduler.py`:
- `MIN_GAP_SECONDS = 3300` (55 min) between signal generation runs.
- `MAX_ORDERS_PER_RUN = 15` hard cap.
- `MAX_PER_SYMBOL_PER_TIMEFRAME = 4` — independent for 1d/4h/1h buckets.
- Pre-flight: skip ENTRY signals if balance < $2,000 (EXIT signals still run).
- Active strategies query: `status IN (PAPER, BACKTESTED)`. **LIVE strategies never appear here** — they're handled by the live-independent pass.

### 7.4 LIVE pass architecture — `_run_trading_cycle:1949+`

A separate signal-gen path scoped to `account_type='live'`:
- Iterates `live_strategies WHERE retired_at IS NULL` (`get_all_live_approvals`).
- For each `(strategy_id, symbol)`:
  - **Duplicate guard (a)**: open live position for symbol → skip.
  - **Duplicate guard (b)**: pending live order for symbol → skip.
  - **Duplicate guard (c)**: any live entry order in last 4h → skip (covers pre-market window).
- Calls `strategy_engine.generate_signals(strategy, account_type='live', conviction_override=approval.conviction_min)`.
- Live conviction gate: per-pair `conviction_min` from `live_strategies` overrides config; otherwise 73 (67 crypto).
- Submits via `_live_order_executor` — separate `OrderExecutor` instance pointed at LIVE eToro client.
- Persists with `account_type='live'` on the order row.

### 7.5 eToro API client — `src/api/etoro_client.py`

Key facts:
- **`update_position_stop_loss` is a no-op stub** returning `{"status": "db_only"}`. eToro public API does not expose SL modification for open positions.
- **Trailing stops are enforced DB-side** — every `except EToroAPIError` around SL updates is dead code.
- Composite uniqueness: eToro reuses numeric position IDs across DEMO and LIVE accounts. The DB constraint is `(etoro_position_id, account_type)`, not global. Migration `migrations/migrate_etoro_id_constraint.sql`.
- Circuit breaker: trips on consecutive failures, recovers via timed half-open.
- `partial_close_position` exists but is currently disabled (see §8.3).

### 7.6 Cycle log signature

Every cycle emits a structured summary (`cycle_history.log`):
```
CYCLE COMPLETE in 383s
  Proposals: 200 candidates → 24 fresh (DSL=16, AE=8)
  Walk-forward: 19/24 passed
  Activated: 9 (→ 0 promoted to PAPER) | Retired: 0 | Total active: 47
  Signals: 0 -> Orders: 0
```

Plus per-10-minute `[SIGNAL-1H]` lines tracking the quick-update path:
```
[SIGNAL-1H] 2026-05-17 14:03:07 | 2s | 5 strategies | 0 signals | 0 orders
```


---

## 8. Risk Management

### 8.1 Risk validation — `RiskManager.validate_signal`

Pre-sizing checks (`risk_manager.py:557-755`):
- Portfolio heat cap (30%, hardcoded).
- Symbol concentration (5%).
- Sector soft cap (30% → halve via sizing, not reject).
- Directional balance (`would_signal_improve_balance`/`worsen_balance`).
- Circuit breaker / kill switch active → reject.
- VaR — currently disabled (`portfolio_var.enabled: false` in YAML; the function `check_portfolio_var` exists at line 440 but no caller invokes it because the `enabled` flag gates all callers).

### 8.2 Circuit breaker & kill switch

`RiskManager.check_circuit_breaker` (line 2089): trips on daily P&L loss > N% of equity. `activate_circuit_breaker` halts new trades but lets existing positions run. `is_kill_switch_active` is checked on every signal — when active, all entries are blocked; exits still execute.

LIVE-position fix (`autonomous_strategy_manager.py:2160+`): circuit breaker excludes `account_type='live'` positions from template win-rate checks so a single losing live position doesn't trigger circuit breaker on all DEMO strategies of the same template.

### 8.3 Correlation management — naming gaps

The system has **two `CorrelationAnalyzer` classes** doing different things:

- `src/strategy/correlation_analyzer.py` — strategy-level multi-dimensional correlation (returns × signal × drawdown × volatility, weighted composite). Used by `/analytics/correlation` endpoints in `src/api/routers/performance.py` for the Research → Attribution tab.
- `src/utils/correlation_analyzer.py` — symbol-pair price correlation. Used by `strategy_engine._are_symbols_correlated` in similarity-detection paths.

**Where correlation actually gates trading:**
- **At sizing time** (`risk_manager.calculate_correlation_adjusted_size`, line 1646): same-symbol open position → `0.5 × base`; correlated strategy positions (threshold 0.7, hardcoded) → `(1 − max_correlation × 0.5) × base`.
- **At activation time** (`autonomous_strategy_manager.py:2155-2210`): rejects new strategies whose backtest `daily_returns` correlate with any active strategy's returns above `advanced.correlation_threshold` (0.7). Catches "different rules, same bet".

**Dead config:**
- `position_management.correlation_adjustment.{enabled, threshold, reduction_factor}` — exposed in Settings UI but **not consumed**. risk_manager hardcodes 0.7 and 0.5.
- `alpha_edge.portfolio_risk.{max_correlated_positions: 3, correlation_threshold: 0.75}` — **not consumed anywhere**.
- `similarity_detection` block — gated off by `enabled: false`.

### 8.4 Transaction costs (`config/autonomous_trading.yaml backtest.transaction_costs`)

Per-asset-class costs after the May 14 eToro Diamond+ correction:

| Asset | Commission | Spread | Slippage | Overnight |
|---|---|---|---|---|
| Stock | 0% | 0% | 2 bps | 0% |
| ETF | 0% | 0% | 2 bps | 0% |
| Forex | 0% | 1 bp | 0.5 bps | 1 bp/day |
| **Crypto** | **0.75%** | **0%** | 10 bps | 0% |
| Index | 0% | 1.5 bps | 1 bp | 1.5 bps/day |
| Commodity | 0% | 4 bps | 2 bps | 2 bps/day |

Per-symbol overrides for BTC/ETH match crypto class (Diamond tier 0.75% commission). Crypto round-trip: 1.5%.

**No real slippage model.** `slippage_percent` is a static per-asset-class number applied uniformly. eToro CFD fills aren't modelled with a price-impact function (no √volume scaling, no spread-of-spread).

---

## 9. Position Monitoring

### 9.1 Trailing stops — `MonitoringService._check_trailing_stops`

60s cycle (`monitoring_service.py:2526+`). **Two-stage architecture:**

**Stage 1 — SL recalculation.** Gated by market-open AND freshness-SLA. Stale bars keep the existing SL; ratchet only moves favourably so a preserved SL is always safe.

Ratchet ladder (stock as example, configurable per asset class):
- +3% profit → SL to entry (breakeven).
- +5% profit → SL to entry × 1.02 (profit lock).
- +5% activation → trail SL = current × (1 − effective_distance).

`effective_distance = max(fixed_pct, ATR_pct × ATR_MULTIPLIER_BY_ASSET_CLASS[class])`. ATR multipliers (per the steering file, hardcoded in `monitoring_service.py`):

| Asset class | ATR multiplier |
|---|---|
| stock / etf / commodity | 2.0× |
| crypto / index | 1.5× |
| forex | 1.0× |

ATR uses the strategy's **own interval** (`position_intervals` dict): 4h strategies use 4h ATR, daily use daily.

**Stage 2 — Breach enforcement.** Runs for ALL open positions regardless of bar freshness — only needs `current_price` + `stop_loss` (both in DB from the 60s position sync). A Yahoo outage cannot disable stop enforcement.

**Per-cycle summary log** at INFO:
```
TSL cycle: total=90 recalc_eligible=88 skipped_market=0 skipped_stale=0 breakeven=1 lock=0 trail=3 db_updated=3 breach=0 errors=0
```

### 9.2 Position sync — `OrderMonitor._sync_positions`

60s cycle. Critical invariant: **every query is scoped to `account_type`** so DEMO sync never finds LIVE positions by `etoro_position_id`:
- `all_db_positions` query filtered.
- Pass 1 (existing eToro position match) and Pass 2 (orphan-by-symbol match) both filter `OrderORM.account_type == account_type`.
- `reconcile_on_startup` is account_type-aware. LIVE monitor runs its own startup reconcile via `monitoring_service._live_reconcile_done`.

Optimistic position write: order submission creates a position row with `etoro_position_id=pending_<order_id>`. Fill detection (`check_submitted_orders`) updates to the real eToro position ID. Synthetic UUID fallback if PK collision.

### 9.3 Partial exits — currently disabled

`MonitoringService._check_partial_exits` (line 2978) returns immediately with `{"checked": 0, "skipped": "disabled"}`. Reason: depends on eToro position-modification API which is not exposed. The full implementation is preserved as unreachable code below the early return, ready to re-enable.

YAML `position_management.partial_exits.levels` configures the schedule (`profit_pct: 0.18, exit_pct: 0.33`) but has no runtime effect.

### 9.4 Fundamental exits — `_check_fundamental_exits`

Runs daily (`_fundamental_check_interval`). Three checks, all gated by profitability guards:
- **Earnings miss**: `surprise < −5%`. Only fires if position is profitable OR SL ≥ 50% consumed.
- **Revenue decline**: `revenue_growth < 0`.
- **Sector rotation**: position's sector not in optimal sectors for current regime. Only fires if (a) regime stable for 3+ days (no `regime_history.regime_changed=True` rows in last 3 days) AND (b) position is profitable.

Action: `pos.pending_closure = True` with descriptive reason. **Does NOT auto-close** — operator review.

### 9.5 Zombie exits

`_check_zombie_exits` (`monitoring_service.py:4121-4248`). Runs every 6 hours.

**Category 1 — retirement blocker**: position in pending_retirement strategy, flat ±2% for 5+ days. Reason: `Retirement blocker: strategy pending retirement, position flat for {days}`.

**Category 2 — stale by class/type**:

| Strategy type | 1D threshold | 4H threshold |
|---|---|---|
| Forex (any) | ±2% / 14 days | ±2% / 7 days |
| Alpha Edge | ±1% / 14 days | ±1% / 7 days |
| Mean reversion | ±1% / 7 days | ±1% / 4 days |
| Trend-following / other | ±1% / 5 days | ±1% / 3 days |

Sets `pending_closure=True` with reason `Stale: {1D|4H} {label} position flat ({pnl_pct}%) for {days} days`. Operator review only — never auto-close.

---

## 10. Graduation Pipeline

`src/strategy/graduation_gate.py`. Promotes a (template, symbol) paper pair to live trading.

### 10.1 Qualification criteria (all must pass)

| Criterion | Threshold | YAML key |
|---|---|---|
| Min trades | **15** (overrides hardcoded 20 via YAML) | `graduation_gate.min_trades` |
| Per-interval min trades | 1d=10, 4h=15, 1h=25 | `paper_trading.graduation_gate.min_trades_*` |
| Win rate | ≥ 55% | `graduation_gate.min_win_rate_pct` |
| Total P&L | > 0 | hardcoded `MIN_PAPER_PNL` |
| Avg P&L per trade | > 0 | `paper_trading.graduation_gate.min_avg_pnl_per_trade` |
| Qualification ratio | `paper_sharpe / wf_sharpe ≥ 0.60` | `graduation_gate.min_qualification_ratio` |
| Max ratio cap (regime-luck guard) | `paper_sharpe / wf_sharpe ≤ 2.0` | `graduation_gate.max_qualification_ratio_cap` |
| Cooldown after rejection | 14 days | `graduation_gate.rejection_cooldown_days` |
| Not already in `live_strategies` | — | enforced by SQL excluding active live pairs |

### 10.2 Aggregation

Stats are aggregated **across all strategy IDs for a (template_name, symbol) pair**, not per single strategy. Template name resolution: `COALESCE(strategy_metadata->>'template_name', REGEXP_REPLACE(name, ' V[0-9]+$', ''))`. This survives strategy retirement/re-proposal — historical trades from earlier `strategy_id`s still count.

### 10.3 Approval flow — `approve_graduation`

CIO approves via `POST /strategies/{id}/graduate`. The function:
1. Loads source strategy, resolves `template_name` and `wf_sharpe`.
2. Checks `(template_name, symbol)` not already active in `live_strategies`.
3. **Creates a NEW LIVE `StrategyORM`** with `status=LIVE`, `symbols=[symbol]` only (the source PAPER strategy is not mutated).
4. Carries over rules + risk_params from source, overrides with CIO-approved `position_size, sl_pct, tp_pct, conviction_min`.
5. Stamps `parent_strategy_id`, `graduated_from`, `graduated_at` on the LIVE strategy's metadata for lineage.
6. Inserts `graduation_approvals` snapshot row.
7. Inserts `live_strategies` authorization row.

The LIVE strategy then runs through the dedicated live-independent signal pass on the next scheduler cycle.

### 10.4 Current state

GOOGL × 4H EMA Ribbon Trend Long is the only LIVE strategy. As of audit time:
- LIVE position open: GOOGL LONG, entry $389.20, current $396.82, +$16.63 unrealized, SL $389.20.
- Closest paper-side approaching graduation: MU × 4H EMA Ribbon (13 trades, 76.9% WR, ratio 2.46) — blocked by ratio cap (>2.0).
- No queue qualifications expected until July-August as 4H strategies accumulate 15+ trades per pair.

---

## 11. Retirement & Decay

### 11.1 Decay scoring — `MonitoringService._check_strategy_decay`

Counts down 10→0. Hourly run. `monitoring_service.py:4665-5113`.

**Penalty factors (per check cycle):**

| Factor | Trigger | Penalty |
|---|---|---|
| Regime mismatch — major shift | up↔down regime change | −2.0 |
| Regime drift — minor | ranging→trending or trending→ranging | −1.0 |
| Live P&L — severe | live_return < −10% | −3.0 |
| Live P&L — negative | live_return < −5% | −2.0 |
| Live P&L — warning | live_return < −2% | −1.0 |
| All positions red | 100% underwater, ≥2 positions | −2.0 |
| Mostly red | >70% positions underwater | −1.0 |
| Stop-loss ineffective | severe losses (loss > 2× SL) > 50% of closers | −2.0 |
| Stop-loss ineffective (light) | severe losses 30-50% | −1.0 |
| Idle | no positions, age ≥ 1 week | `min(weeks × idle_decay_rate, 5.0)` |
| Live win-rate low | ≥5 closed positions, WR < threshold | −1.0 |
| Factor spread narrow (AE) | gate3.spread < 20 | −2.0 |
| Factor spread warning (AE) | gate3.spread 20-30 | −1.0 |
| Wrong quintile (AE) | factor_details.gate3.in_right_quintile == False | −1.5 |
| Template circuit breaker | template family WR < 30% on last 10 closed | −1.5 |

**Decay arithmetic:**
- `total_penalty = Σ penalties`
- If > 0: `decay_step = min(total_penalty / 3, 3.0)`; `new_decay = decay_score − decay_step`.
- If 0: `new_decay = decay_score + 0.5` (recovery).
- Clamp `[0, 10]`, round.

**Probation periods (timeframe-aware):**
- Sector rotation / monthly templates / weekly: 35 days.
- 4h / pairs trading / relative value: 14 days.
- 1h/2h/15m/30m: 7 days.
- Daily default: 7 days.
- Halved when `decay=0 AND health_score ≤ 2` (doubly broken).

**At decay=0, past probation:**
- "Genuine winner override": if `live_pnl > 0.02 × live_invested` (>2% of deployed capital), reset decay to 3 and skip retirement.
- Open positions exist → `pending_retirement=True`, removes `activation_approved` flag, stays PAPER.
- No open positions → demote to BACKTESTED with `demotion_ttl_days=14`.

### 11.2 Health scoring — `_check_strategy_health` (separate, hourly)

5→0 score from +/−1 components: PnL positive, expectancy, all-positions-red, severe realized loss, near SL. Retires only when `health_score == 0 AND closed_count ≥ 5`.

### 11.3 Cleanup & TTL — `autonomous_strategy_manager._cleanup_inactive_strategies`

Runs at cycle start. Deletes:
- `PROPOSED` / `INVALID` rows (always).
- `BACKTESTED` rows that are unapproved AND not demoted-from-active.
- `BACKTESTED` rows demoted-from-active past `demotion_ttl_days`.
- `RETIRED` rows (legacy, shouldn't exist anymore).

Never touches DEMO/LIVE.

### 11.4 Dead retirement code

- `portfolio_manager.check_retirement_triggers` returns `None` (no-op).
- `portfolio_manager.auto_retire_strategy` only logs.
- `_check_and_retire_strategies` (cycle stage) routes through the dead `check_retirement_triggers`, so cycle-time retirement is regime-mismatch-only.

Active retirement happens entirely in `_check_strategy_decay` and `_check_strategy_health`.

---

## 12. Analytics

### 12.1 `signal_decisions` funnel

Every template × symbol × stage decision per cycle is persisted to `signal_decisions`. Stages:

| Stage | Written from |
|---|---|
| `proposed` | `track_proposals` → `decision_log.record_batch` |
| `wf_validated` / `wf_rejected` | `strategy_proposer.py:2435-2440` (batch write) |
| `cross_validation` | family-CV pass (proposer.py:2625-2652) |
| `activated` / `rejected_act` | `autonomous_strategy_manager` activation pass |
| `signal_emitted` (rejected) | `strategy_engine.generate_signals` filter rejections (frequency, low_confidence, fundamental, conviction) |
| `gate_blocked` | `OrderExecutor.execute_signal` C1/C3 gates |
| `order_submitted` | successful submit path |
| `order_filled` | `OrderMonitor.check_submitted_orders` with slippage + fill_time |
| `order_failed` | reserved (not yet wired) |

Writer: `src/analytics/decision_log.py` `record_decision` / `record_batch`. Fire-and-forget — never raises. Retention 30 days via `prune_old(30)`.

### 12.2 Observability endpoints — `src/analytics/observability.py`

Five functions, all read-only and cached:

- **`mae_at_stop_analysis`** — per-symbol MAE/MFE with pattern detection: `entry_bad_or_stop_hit` (|MAE| > 0.8×SL), `exit_late_gave_back` (positive avg P&L but mfe > 3× pnl), `trail_tight_leaving_money`, `entry_bad_immediate_reversal`.
- **`wf_live_divergence`** — strategies where `|wf_sharpe − live_sharpe| > 1.0`. Top 50.
- **`regime_template_pnl_matrix`** — (regime, template, direction) → {trades, pnl, win_rate}.
- **`template_graduation_funnel`** — proposal → fill funnel with per-stage drop-off %.
- **`per_symbol_opportunity_cost`** — `symbol_forward_return − captured_pct`. Top-50 missed movers.

Endpoints under `/analytics/observability/*` and `/health/trading-gates`.

### 12.3 Trade journal & performance feedback

`src/analytics/trade_journal.py` (1,682 lines). `get_performance_feedback` returns:
- `template_performance`: per-template `{win_rate, total_pnl, total_trades, avg_pnl_per_trade}`.
- `symbol_performance`: per-symbol same + `recency_weight` (14-day half-life exponential).
- `regime_performance`: per-regime `best_template_win_rates`.
- `slippage_analytics`: `slippage_by_symbol`.

`record_trade` writes to `trade_journal` on every position close (and partial close, were partials enabled).

### 12.4 Intel analyst — `src/analytics/intel_analyst.py`

50 checks across 8 categories:

| Category | Checks | Description |
|---|---|---|
| **A — Strategy Health** | A1-A10 | BACKTESTED with 0 signals, pending_retirement opening positions, live_trade_count=0 mismatch, WF regime luck, paper/WF WR divergence, BACKTESTED 0 paper trades, conviction cluster 65-69, zero short exposure, template family negative, overtrading |
| **B — Execution Quality** | B1-B6 | Order failed rate, duplicate orders, slippage NULL, order stuck pending, eToro ID collision demo/live, position with NULL strategy_id |
| **C — Risk** | C1-Cn | Heat cap breach, symbol concentration, equity drawdown |
| **D — Data Pipeline** | D1-D8 | Stale 1d bars, stale 4h bars, Yahoo delisted, FMP rate limit, duplicate price bars, MQS NULL snapshots |
| **E — Cycle/Signal** | E1-E8 | Cycle duration regression, WF cache hit rate <40%, low proposal count, zero SHORT WF passes, gate-blocked loop (E5), concurrent cycles |
| **F — System Health** | F1-F7 | New errors.log lines, SQLAlchemy InFailedSqlTransaction, postgres idle connections, service restarts, API rate limits |
| **G — Alpha Opportunities** | G1-G9 | Strong WF never activated, underweighted asset class, missed alpha (forward return − captured), GOOGL LIVE divergence, WF cache low hit rate, etc. |
| **H — Config Integrity** | H1-Hn | Paper conviction threshold mismatch, dead config detection |

Findings persist to `system_findings` table (dedup by `(check_id, key)`). Background thread polling — manual trigger via `POST /intel/run` (returns immediately with `run_id`; results polled via `GET /intel/findings`). Lookback configurable (1/7/14/30/90 days).

Recent calibration fixes (May 15):
- C1/C2: use `equity_snapshots WHERE account_type='demo'` not bare `account_info.balance`.
- A7: COUNT(DISTINCT strategy_id) not raw row count.
- A10/E5: measure `order_submitted` not `signal_emitted` (signals fire every 10 min by design — quick update).
- A6: only fires when signals ARE generating but not converting (otherwise A1 catches it).
- G9: threshold −1000% + train_S > 0 + trades ≥ 8 (genuine regime luck, not thin-train artefact).

---

## 13. Frontend

### 13.1 Page structure

| Page | Path | Tabs |
|---|---|---|
| Command | `/` | Single page (Fund Scorecard 3×3 + key tiles) |
| Book | `/book/*` | Positions · Orders · Live |
| Strategies | `/strategies/*` | Cycle · Library · Templates · Symbols · Blacklist · Graduation · Lab |
| Guard | `/guard/*` | System · Risk · Gates · Circuit Breakers · Alerts · Audit · Sync Log |
| Research | `/research/*` | Performance · Execution · Attribution · Trades · Regime · Alpha Edge · Tear Sheet · Stress · Journal |
| Intel | `/intel/*` | Single page (101 calibrated findings, severity badges, "Ask Kiro →" copy-prompt) |
| Settings | `/settings/*` | Trading mode · API config · ... (grouped by Account / Trading / Risk / Notifications) |
| Login | `/login` | Cognito-style session form |

### 13.2 Architecture

- **Stack**: React 18, Vite, TypeScript, TanStack Query 5 (`staleTime: 30s`, `refetchOnWindowFocus: false`).
- **State**: queryClient + small per-page Zustand-like stores (no global Redux).
- **Routing**: BrowserRouter, lazy-loaded page bundles (Suspense + Spinner fallback).
- **Auth**: `ProtectedRoute` wrapper in App.tsx; 401/403/404 don't retry; global `setAuthErrorHandler` on session-invalidation events.
- **WebSocket**: `wsManager` from `src/services/websocket.ts`. Disconnects on auth invalidation.
- **Toasts**: Sonner (bottom-right, dark theme).
- **Charts**: Recharts (most pages), lightweight-charts for the equity/drawdown overview.

### 13.3 Real-time updates

- WebSocket events broadcast from `src/api/websocket_manager.py`: `cycle_progress`, `autonomous_strategy_event`, `autonomous_notification`, `position_update`, `order_update`.
- Frontend stores subscribe and invalidate the relevant TanStack Query keys.
- Polling for nav badge: every 60s for P0/P1 open count.
- Sync Log tab polls `/data/service-log` every 5 s; service log persisted to disk (`logs/service_log.jsonl`, 2,000-entry ring buffer).

### 13.4 Key analytics surfaces

- **Fund Scorecard** (Command): 3×3 grid — Sharpe · Sortino · Max DD / Win rate · Profit factor · Alpha vs SPY / Total return · Realised P&L · Unrealised P&L.
- **Research/Performance headline tiles**: Total return (% + $) · Realised P&L · Alpha vs SPY · Sharpe · Sortino · Max DD · Win rate · Profit factor · Daily returns.
- **Equity chart hover**: Equity · Realised · Realised α SPY · Drawdown · Alpha vs SPY.
- **Library pills**: Signals today · Idle 7d+ · Negative live P&L · Graduation eligible · Paper ≥20 trades · Promoted today · Activated today · Live today.

---

## 14. Infrastructure

| Resource | Detail |
|---|---|
| Dashboard | `https://alphacent.co.uk` |
| EC2 instance | `i-035d5576835fcef0a` (t3.medium, eu-west-1) — IP `34.252.61.149` |
| OS | Ubuntu 22.04 |
| Compute | 2 vCPU, 4 GB RAM, 30 GB EBS |
| Database | PostgreSQL 16 (single instance, same host) |
| Reverse proxy | nginx 1.18 with Let's Encrypt TLS |
| Process supervision | systemd unit `alphacent.service` |
| Service start hook | `ExecStartPre=/home/ubuntu/alphacent/deploy/patch-api-keys.sh` (writes API keys from AWS Secrets Manager into `config/api_keys.yaml`) |
| Backend port | uvicorn on `localhost:8000`, proxied by nginx |
| CI/CD | GitHub Actions → `scp` deploy |
| Frontend build | Static bundle served from `/home/ubuntu/alphacent/frontend/dist` |
| Logs | `/home/ubuntu/alphacent/logs/` (errors.log, alphacent.log, strategy.log, risk.log, cycles/cycle_history.log, service_log.jsonl) |
| Backups | `data/backups/` cron-driven (hourly, 7-day retention) |
| Monitoring | CloudWatch agent for memory + disk; no APM |
| Secrets | AWS Secrets Manager: eToro public_key/user_key, FMP API key, Marketaux API key, FRED API key |

### 14.1 Single-host risks

- Backend, DB, monitoring, and frontend share the same host. RAM saturation (e.g. WF cache + indicator cache + market_stats cache combined > 1 GB) has historically caused OOM kills.
- No secondary failover. systemd auto-restarts within ~5 s but a position-modification request mid-restart is silently dropped.
- DB backups are local only — disk loss = data loss.

---

## 15. Current System State (pulled at audit time)

```
Strategies:    267 BACKTESTED · 46 PAPER · 1 LIVE
Positions:     70 DEMO open / 1,025 lifetime · 1 LIVE open / 15 lifetime
Equity (DEMO): $479,224 · Balance $94,311 · Realised cumulative $45,511
Equity (LIVE): $9,903 · 1 GOOGL LONG +$16.63 unrealised
Regime:        trending_up_strong (confidence 0.87)
MQS:           84 (high)
PAPER conv:    70 (default), 62 (crypto)  ← effective from alpha_edge.min_conviction_score
LIVE conv:     73 (default), 67 (crypto)  ← from live_trading.conviction_threshold
graduation_gate.min_trades:  15 (lowered from 20 to enable GOOGL graduation)
Latest cycle:  383s · 200 proposals → 24 fresh → 19 WF-passed → 9 activated → 0 paper-promoted · 0 signals · 0 orders
Latest commit: 9ad34ad (Intel page calibration fixes)
errors.log:    15,965 lines since 2026-05-01 (most recent: DSL parse errors on MACD().shift(1))
```

### 15.1 Known issues / technical debt

- **Walk-forward bypass paths admit regime-luck for LONG strategies**. Test-dominant path: `train_S ≥ −0.1` is too loose. Excellent-OOS consistency gate `(test_S − train_S) ≤ 1.5` should also apply to test-dominant for symmetry.
- **`paper_trading.conviction_threshold` / `_crypto` separation is partially wired** — YAML and Settings UI round-trip correctly, `paper_trading.activation_thresholds` and `paper_trading.graduation_gate` and `paper_trading.flat_position_size` ARE consumed by their respective gates, but the signal-time conviction gate in `strategy_engine.generate_signals:5573` still reads `alpha_edge.min_conviction_score` only. The deliberate paper/live separation in YAML hasn't reached the signal-gen runtime yet. Intel H4 flags this. See G-43.
- **`position_management.correlation_adjustment.{enabled, threshold, reduction_factor}` are dead config** — risk_manager hardcodes 0.7 / 0.5×.
- **`alpha_edge.portfolio_risk.{max_correlated_positions, correlation_threshold}` are dead config** — no code reads these.
- **Avg-loss gate has no paper-mode disable** — paper strategies with 20+ trades and avg_loss > N×SL are still rejected.
- **Partial exits disabled** — depends on eToro position-modification API which is not exposed.
- **Triple EMA Alignment template generates 0 trades** — regex-based positional substitution collapses to `EMA(10) > EMA(10)` when fast/mid/slow params don't match the literal template values.
- **Sector Rotation + Pairs Trading templates structurally broken** — Sector Rotation `fixed_symbols` covers only 5 of 11 SPDR sectors; Pairs Trading Market Neutral DSL conditions are momentum-long signals not pairs.
- **15,965 errors.log lines** — mostly DSL parse errors on bad templates (`MACD().shift(1)` is unparseable) and FRED 500s. Cleanup or template fixes pending.
- **VaR check disabled** — model artefact at 97.97% from young equity curve. Re-enable after 90+ days of equity history.
- **Cycle stage-error observability gap** — when a cycle stage throws, only logs `Error proposing strategies:` and continues. No `signal_decisions cycle_error` row written.
- **`directional_quotas.enabled: false`** — the steering file documents 80/5 LONG/SHORT minimums for trending_up but the config flag is off; the regime gate is the only directional control.
- **Two `CorrelationAnalyzer` classes in the codebase** — name collision risk.


---

## 16. Strategy Lifecycle — RESEARCH → PAPER → LIVE

This is the operating model that drives everything else in the system. The audit was originally written without this lens; this section corrects it.

### 16.1 The three stages

| Stage | DB status | Account | Purpose | Discipline |
|---|---|---|---|---|
| **RESEARCH** | `BACKTESTED` (or `PROPOSED`/`INVALID` if not yet through WF) | n/a | Validate edge offline (WF, MC, conviction). | Statistical |
| **PAPER** | `PAPER` (after first signal fires) or `BACKTESTED` with `activation_approved=True` | DEMO | **Gather trade data** so the graduation gate has a sample to qualify pairs for live | Maximise data quality and breadth |
| **LIVE** | `LIVE` | LIVE | **Generate alpha** with real capital under risk discipline | Capital preservation + alpha |

The transitions: WF/MC pass → BACKTESTED/activation_approved → first signal fires → PAPER. Then `(template, symbol)` accumulates trades in `trade_journal`. When the graduation gate's qualification ratio passes, CIO approves → new LIVE strategy created.

### 16.2 What this means for the system's gates

Every gate in the system needs to be classified into one of:

- **RESEARCH-only** — affects whether a strategy reaches PAPER (WF, MC, activation criteria, ex-post 730d veto). Already correct: relaxed in `paper_trading.activation_thresholds`.
- **PAPER-relevant** — runs while gathering data on demo capital. Ideally relaxed (more trades = more data).
- **LIVE-relevant** — runs only on real capital. Must be tight (capital preservation, alpha discipline).
- **Both** — same logic both stages, but parameterised differently per stage.

### 16.3 Current state — what is already differentiated

What the YAML and code already separate by stage:

| Item | RESEARCH | PAPER | LIVE | Wiring |
|---|---|---|---|---|
| Activation Sharpe / WR / drawdown | strict (`activation_thresholds.*`) | relaxed (`paper_trading.activation_thresholds.*`) | strict (uses `activation_thresholds.*`) | ✅ portfolio_manager.evaluate_for_activation:702 |
| `disable_min_return_per_trade` | n/a | true | false | ✅ portfolio_manager.py:1301 |
| `disable_avg_loss_gate` (expectancy path) | n/a | true | false | ✅ portfolio_manager.py:1020 |
| Position sizing | n/a | flat $5,000 | clamped CIO size | ✅ risk_manager.calculate_position_size:858 (PAPER); LIVE bypasses entirely |
| Conviction threshold | gates entry | should be 60 | should be 73 (per-pair) | ❌ **G-43**: paper still uses alpha_edge value |
| Min trades for graduation | n/a | per-interval (10/15/25) | n/a | ✅ paper_trading.graduation_gate.* |

What runs in PAPER but ideally shouldn't (data-collection bias):

| Gate | Current state | Why it shouldn't run in PAPER |
|---|---|---|
| `MAX_PER_SYMBOL_PER_TIMEFRAME = 4` | applies to PAPER and LIVE | Limits how many strategies can show up on the same symbol — caps the diversity of paper trades |
| Symbol cap 5% of equity | applies to PAPER (via `risk_manager` Step 6) | Capital preservation makes no sense on demo capital |
| Sector soft cap 30% → halve | applies to PAPER | Same — over-concentration only matters with real money |
| Heat cap 30% portfolio | applies to PAPER | Same |
| Drawdown sizing 5%/10% reduction | applies to PAPER | Punishes data collection during exactly the regime where we'd learn the most |
| MQS sizing multiplier (×0.7 in choppy) | applies to PAPER | Same |
| Correlation-adjusted sizing | applies to PAPER (via Step 6 + same-symbol 0.5×) | Same |
| Per-pair loser penalty (Step 10b ×0.5) | applies to PAPER | Useful for capital preservation, but in PAPER it slows down data collection on losing pairs that might rotate back into a better regime |
| Conviction-tier sizing (×1.15/×1.30) | applies to PAPER (Step 10c) | Distorts the data — graduation should compare like-for-like sizes |
| C1 VIX gate | applies to PAPER and LIVE | Blocks LONG entries during VIX spikes — but in PAPER we want exactly that data point to learn from |
| C3 trend-consistency gate | applies to PAPER and LIVE | Same — blocks data we want to collect |
| Trade frequency limiter (AE only) | applies to PAPER | Caps AE strategies at 4/month — slows data accumulation |
| Circuit breaker | applies to PAPER and LIVE | Reasonable guardrail, but on demo capital halting is a data-collection loss |
| Avg-loss gate (`autonomous_strategy_manager.py:2258`) | applies to PAPER (no disable flag) | Rejects strategies before they can accumulate paper trades |

What runs in LIVE but doesn't (alpha-generation gap):

| Gate | Current LIVE behaviour | What it should be |
|---|---|---|
| `RiskManager.validate_signal` (heat / sector / directional / VaR / correlation) | **bypassed** — LIVE pass calls `_live_order_executor.execute_signal` directly with CIO size | Must run; LIVE without portfolio risk validation is single-position-only by design (1 LIVE strategy today, but breaks when there are 5+) |
| `RiskManager.calculate_position_size` (11-step pipeline) | **bypassed** — LIVE uses CIO `position_size` clamped to `[min_order_size, max_order_size]` | At a minimum: vol-scaled sizing, sector cap, heat cap, drawdown sizing should apply |
| Vol-targeting | **not applied** — flat CIO size | Critical for LIVE; per-strategy-type vol target |
| Correlation-cluster cap | **not applied** | Critical for LIVE |
| Per-pair loser penalty | **not applied** | Useful for LIVE (real capital preservation) |
| Conviction-tier sizing | **not applied** | Useful for LIVE (deploy more on high-conviction signals) |
| Drawdown sizing | **not applied** | Critical for LIVE |
| MQS sizing | **not applied** | Critical for LIVE |

### 16.4 The structural realisation

The system was originally built **research → paper** as a single pipeline. Risk machinery (sizing, heat cap, sector cap, correlation, vol scaling) was added across the whole thing because there was no LIVE stage to differentiate. Then LIVE was added as a separate signal pass that bypasses the whole risk framework.

The result: **PAPER inherits LIVE-grade risk discipline it doesn't need (slowing data collection), and LIVE bypasses the risk framework that would help it (concentrating risk).**

Both directions are wrong. The correct shape:

- **PAPER**: relaxed entry gates, flat sizing (already correct), fewer rejections, more breadth. Treat it as a data-collection sandbox.
- **LIVE**: the full risk framework. Vol-scaled sizing, correlation-cluster caps, heat cap, sector cap, drawdown sizing, MQS multiplier, conviction-tier sizing all apply.

This is the single highest-leverage architectural realisation in the audit. Most of the P1 gaps in the gap analysis are now reframed by it (see GAP_ANALYSIS_2026-05.md).
