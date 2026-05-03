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

## Current System State (May 3, 2026, ~21:00 UTC, post-FMP-primary-all-intervals)

- **Equity:** ~$480K
- **Open positions:** 84
- **Active strategies:** 63 DEMO + 5 BACKTESTED/approved = **68 trading**
- **Crypto-native strategies:** 5 (4 BTC Follower Daily alts + 1 BTC Follower 4H ETH)
- **Directional split:** ~82 LONG / ~5 SHORT
- **Market regime (equity):** `STRONG UPTREND` (20d +10%, 50d +5%)
- **Market regime (crypto):** `RANGING_LOW_VOL`
- **VIX:** 16.89
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

### Ready-to-run (data fully primed)

Trigger a full autonomous cycle when ready. Data is in place:
- Crypto 1d/1h/4h on Binance, full depth.
- Non-crypto 1d/1h/4h on FMP Starter, 5y depth for 286-287 symbols.
- Yahoo fallback ready for the 8-11 premium-blocked (symbol, interval) combos.

Cross-timeframe OHLC consistency guaranteed for FMP-served symbols (raw-close across 1d/1h/4h) — no more day-boundary phantom gaps from Yahoo 1d adjusted-close vs FMP intraday raw-close.

### Verification after next cycle

1. **FMP coverage**: grep `FMP (primary` and `Binance (primary` across all 3 intervals. No symbol should hit Yahoo unless it's in the premium-blocked set. Engine-cap truncation log (`WF window capped by data-source limit`) should only fire for those same 8-11 combos.
2. **WF window selection**: every strategy emits `WF window [<key>]:` at INFO. Expect all 7 keys to fire across the cycle.
3. **Activation health**: crypto activations should continue at normal rate (post-per-position-RPT-fix); non-crypto at normal rate.
4. **errors.log**: should stay near-empty. The forex weekend `possibly delisted` noise is gone. The only remaining known-noise is the `CLOSE[-20]` parse error on a template with unsupported syntax (P2).

### Deferred / still open

- **Triple EMA Alignment DSL bug** (P1): `EMA(10) > EMA(10)` tautology from regex param collapse in `strategy_proposer.customize_template_parameters`. ~30 min fix to add explicit positional-EMA-period handling.
- **MQS persistence** (P1): `_save_hourly_equity_snapshot` wraps MQS compute in bare `except: pass`, hiding the real error. Recent `equity_snapshots.market_quality_score` rows are NULL. ~45 min fix to log the error signature.
- **WF bypass-path tightening for LONG** (P1): primary + test-dominant paths admit regime-luck on LONG side. Consider `(test_sharpe - train_sharpe) ≤ 1.5` consistency gate. SHORT already tightened (Sprint 1).
- **Cross-cycle signal dedup for market-closed deferrals** (P1): entry-order 82% FAILED rate is cosmetic — market-closed deferrals re-fire each cycle. 30-min TTL map on `(strategy_id, symbol, direction)` in trading_scheduler.
- **trade_id convention unification** (P2): `log_entry` uses `position.id`; `log_exit` uses order UUID. Migrate `order_monitor.check_submitted_orders` to `position.id`.
- **Sector Rotation + Pairs Trading template rewrites** (P2): both structurally broken. Design-first, then rewrite.
- **Monday Asia Open template** (P2): needs DSL `HOUR()` primitive.
- **On-chain metrics** (P1, Sprint 4): BTC dominance, stablecoin supply momentum. `ONCHAIN("metric", lookback_days)` DSL primitive. CoinGecko + DeFi Llama free tiers to start.
- **Forex on-demand via new `fmp_ohlc` client**: the legacy `_fetch_historical_from_fmp` path for forex 1d still uses the dead v3 `historical-price-full` endpoint — returns empty, falls through. Not breaking anything because `_fetch_historical_from_yahoo_finance`'s new FMP-first branch now covers forex 1d too. Cleanup task only; ~15 min.
- **Overview chart panel rewrite** (P2): 3 chart components with misaligned axes; design-first.

---

## Next-session kickoff prompt

Copy this as-is into a new session when you're ready:

```
Start this session by reading, in this exact order: (1) .kiro/steering/trading-system-context.md — pay special attention to "Think Like a Trader, Not a Software Engineer" and "Proper Solutions Only — No Patches, No Stopgaps". (2) Session_Continuation.md — focus on the "Current System State" and "Session shipped 2026-05-03" block. (3) AUDIT_REPORT_2026-05-02.md if the context needs the audit baseline. Confirm you've read them and begin.

Context: the data pipeline is now production-grade. Crypto routes through Binance (5y+ depth). Non-crypto 1d/1h/4h routes through FMP Starter (5y depth for 286-287 symbols). Yahoo is strictly the fallback for the 8-11 premium-blocked combos (DAX, CAC, oil-1h, copper-1h, US indices at 4h, UK100/STOXX50 at 4h). Cross-timeframe OHLC consistency is guaranteed for FMP-served symbols. WF windows are yaml-managed single-source-of-truth; per-position-RPT math is correct. Non-crypto 1h/4h WF windows are widened to 365/365 (parity with crypto), giving swing templates 24+ OOS trades.

Your mission this session: [pick the one that matches current priority]

(A) RUN AUTONOMOUS CYCLE + VERIFY — Trigger a full cycle across all symbols/intervals. Grep for `FMP (primary` and `Binance (primary` log lines to confirm routing. Grep for `WF window [<key>]` to confirm all 7 asset-class windows fire. Check errors.log stays clean (no yfinance forex-weekend noise). Check activation count and rejection reasons are consistent with pre-cycle baseline.

(B) TRIPLE EMA + MQS PERSISTENCE FIXES — Two ~30 min proper fixes from the deferred queue. Triple EMA Alignment regex bug produces `EMA(10) > EMA(10)` tautology; MQS persistence silent except-pass is hiding the real NULL cause. Both fixes are scoped to their root cause with verification via SQL.

(C) WF BYPASS-PATH TIGHTENING FOR LONG — Add `(test_sharpe - train_sharpe) ≤ 1.5` consistency gate to the test_dominant + excellent_oos paths for LONG. Mirror the SHORT rigor from Sprint 1. Verify via WF-live-divergence drop 2+ weeks post-deploy.

(D) SPRINT 4 — BINANCE ON-CHAIN + LIBRARY REBUILD — Pull the Sprint 4 prompt from the previous Session_Continuation archive. Covers `ONCHAIN()` DSL primitive, BTC dominance + stablecoin supply signals, retire 6 redundant templates, add 3 research-backed templates.

Rules:
- Proper solutions only. Fix at the root cause.
- Verify via post-deploy cycle before moving on.
- If a proper fix takes 3+ hours, budget for it — don't ship a patch with a "fix later" note.
```

---

## Reference — DB migrations applied to prod (cumulative)

- `ALTER TABLE orders ADD COLUMN order_metadata JSON;`
- `ALTER TABLE strategy_proposals ADD COLUMN symbols JSON, ADD COLUMN template_name VARCHAR;`
- `CREATE TABLE signal_decisions (...)` with 5 indexes
- `ALTER TABLE autonomous_cycle_runs ADD COLUMN proposals_pre_wf INTEGER;`
- (From today's FMP integration) no schema changes — `historical_price_cache` already supported multi-source via the `source` VARCHAR column.
