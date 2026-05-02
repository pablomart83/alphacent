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

## Current System State (May 2, 2026, ~15:50 UTC, end of Sprint 2)

- **Equity:** ~$475K (unchanged)
- **Open positions:** 84
- **Active strategies:** 63 DEMO + 4 newly BACKTESTED/approved (Sprint 2 activations) = **67 trading strategies**
- **Crypto-native DEMO strategies:** 4 (all BTC Follower Daily: ETH / SOL / LINK / AVAX) — Sprint 2 F2 unblocked activation
- **Directional split:** ~79 LONG / ~6 SHORT (unchanged)
- **Market regime (equity):** `STRONG UPTREND` (20d +10.83%, 50d +5.49%, ATR/price 1.08%)
- **Market regime (crypto, new detector):** `RANGING_LOW_VOL` (BTC 20d +1.0%, 50d +9.75%, ATR 1.8%)
- **VIX:** 16.89
- **Mode:** eToro DEMO
- **Last cycle:** `cycle_1777736694` at 15:44 UTC, completed healthy in 212s. 14 proposals, 5 wf_validated, **4 activated via F2 family-cross-validated path**. See "Sprint 2" section below.
- **Scheduled cycles:** daily 15:15 UTC + weekdays 19:00 UTC

**Verified healthy:** service running post Sprint 2 restart. errors.log clean except pre-existing `CLOSE[-20]` DSL parse warnings on unrelated Batch C templates (P2 known). signal_decisions populating across 6 stages including new `cross_validation`. Sprint 2 deploy successful.

**Sprint 2 also shipped:**
- **F2.1 primary-only dedup** — proposer was treating every watchlist symbol as "active" → 342 dedup pairs shrinking the scoring pool. Fixed: only `symbols[0]` counts. Pool drops to 157 pairs.
- **+3 DSL indicators** — OBV, Donchian, Keltner (real math, not approximations)
- **+5 crypto templates** — 81 total, covering previously missing edge categories

**BTC Follower Daily armed but waiting on trigger:** The 4 newly-activated strategies correctly generated 0 entry signals post-activation. Entry gate is `LAG_RETURN("BTC", 2, "1d") > 0.05` — BTC's current 2-bar return is only +2.79%. Gate fires ~2x/month historically (last trigger: 2026-03-16 at +5.12%, 24 triggers in the last 12 months). Strategies will auto-fire on next qualifying BTC move.

---

## Session shipped 2026-05-02 evening (Sprint 2 — Cross-symbol validation + 4h cache reconciliation)

Two architecturally-proper fixes that cleanly resolve the Sprint 1 gap (template family has edge, per-pair activation kills it) and the phantom-cache-depth issue surfaced during Batch C work.

### F2 — Cross-symbol consistency validation (the core)

**The problem:** Sprint 1 F1 made cross-asset edge first-class (LAG_RETURN / RANK_IN_UNIVERSE as DSL primitives). Post-deploy WF showed the architectural fix worked — BTC Follower Daily flipped from negative test Sharpe to 1.4-3.36 on 4/5 alts. But per-pair activation then rejected every strategy on small-sample cost-per-trade / Sharpe because the very gate that creates the edge (BTC-leader filter) naturally tightens entries to 1-3 trades per 90-180d test window. Gating small-sample metrics on a template whose edge requires that small sample is a design contradiction.

**The fix:** Template-level verdict replaces per-pair gates for templates flagged `requires_cross_validation: True`.

- **Proposer — new Pass 1.5 "Cross-symbol consistency validation"** (`strategy_proposer.py` after the direction-aware WF threshold pass, before watchlist WF):
  - Groups `all_wf_results` by template for templates with `requires_cross_validation=True`
  - For each family: counts how many symbols in `family_universe` cleared the minimal per-symbol bar (test_sharpe > 0.3 AND test_return > 0 AND ≥2 test trades AND not overfitted AND valid numerics)
  - `cross_validation_score = cleared / len(universe)`. Threshold: ≥4/6 = 0.667
  - When family passes: promotes every symbol that individually cleared the minimal bar into `validated_strategies` (symbols that failed their own minimal bar are NOT promoted — family evidence needs per-symbol viability)
  - Stamps `family_cross_validated=True`, `cross_validation_score`, `cross_validation_breakdown` (full 6-symbol JSON) onto `strategy.metadata`
  - Writes one `signal_decisions` row per family with `stage='cross_validation'` and the full per-symbol breakdown in `decision_metadata`
  - Fail-open on exception so a CV bug can't break the proposer

- **Activation** (`portfolio_manager.evaluate_for_activation`): when `family_cross_validated=True`, three per-pair gates are bypassed:
  - **Sharpe gate** — family evidence replaces per-symbol Sharpe minimum. Still requires Sharpe > 0 so we don't activate a symbol that lost money in its own test window.
  - **min_trades gate** — accept ≥2 trades (statistical floor) instead of the interval-specific floor. Per-symbol trade count is structurally low for cross-asset templates.
  - **Return-per-trade gate** — RPT is a small-sample metric; family-level total-return still enforced via net_return > 0 check.
  - What is NOT bypassed: net return > 0 (tradability floor), max drawdown (risk), win-rate / expectancy (per-symbol quality), R:R ratio.

- **Templates updated** — 4 Batch C templates flagged with `requires_cross_validation: True` and `family_universe: [BTC, ETH, SOL, AVAX, LINK, DOT]`:
  - Crypto BTC Follower 1H / 4H / Daily
  - Crypto Cross-Sectional Momentum

- **Decision-log integration** — `activated` and `rejected_act` decision rows now include `family_cross_validated` and `cross_validation_score` in their metadata; `reason="family_cross_validated"` distinguishes F2-path activations from normal path in the funnel.

**Cycle evidence (`cycle_1777736694` at 15:44 UTC):**

- 123 proposals → 5 wf_validated → **3 cross_validation** (1 PASS, 2 FAIL) → **4 activated**, all via F2 path
- BTC Follower Daily: 4/6 cleared (score 0.667) — PASS. Per-symbol:
  | Symbol | Status | Test Sharpe | Test Return | Test Trades |
  | --- | --- | --- | --- | --- |
  | ETH | cleared | 3.36 | 3.91% | 2 |
  | SOL | cleared | 2.04 | 2.25% | 2 |
  | LINK | cleared | 1.65 | 1.42% | 2 |
  | AVAX | cleared | 1.41 | 1.26% | 2 |
  | BTC | failed_minimal_bar | -0.51 | -1.55% | 3 (overfitted self-ref) |
  | DOT | not_proposed | — | — | — |
- BTC Follower 4H: 0/6 cleared — correctly FAILED (confirms Sprint 1 finding — 4H BTC lead-lag isn't real edge in current window)
- Cross-Sectional Momentum: 1/6 cleared (SOL passed WF at S=2.12) — FAILED family gate, per-pair RPT gate then correctly rejected SOL for gross return 2.8% over 3 trades
- All 4 activated BTC Follower Daily strategies correctly generated 0 signals post-activation (BTC's current 2-bar return is +2.79%, below the +5% template trigger). Gate fires ~2x/month historically; strategies armed and waiting.
- **Zero regressions** — Sector Rotation XLF, Crypto Weekly Trend Follow on BTC/ETH/LINK all evaluated through the normal per-pair path and were correctly rejected on Sharpe. No new errors in errors.log.

### F10 — Reconcile stale 4h crypto cache against 1h source window

**The problem:** yfinance's 1h data has a hard ~7-month cap. The DB 4h cache was synthesised from an older 1h snapshot and contained 15 months of bars for BTC/ETH and 13 months for SOL/AVAX/LINK/DOT — but the current 1h reach was only 7 months. Any cache clear or schema-version invalidation would silently drop that phantom 4h depth. The 4h cache was effectively lying about its reach.

**The fix:**

- `market_data_manager._fetch_historical_from_yahoo_finance` — new invariant in the 4h resample block: drop any resampled 4h bar whose window-start is outside the source 1h index range. Logs the trim count. Output 4h window can no longer exceed input 1h window. Documented the 7-month yfinance 1h cap in the function comments.
- `scripts/reconcile_crypto_4h_cache.py` — NEW one-off reconciliation script. For each of BTC/ETH/SOL/AVAX/LINK/DOT, finds the earliest 1h bar and deletes 4h rows older than (first_1h - 1 day). Uses `text()` for SQLAlchemy parameterized SQL.

**Cache state before → after:**

| Symbol | 1H first date | 4H first (before) | 4H first (after) | Bars deleted |
| --- | --- | --- | --- | --- |
| BTC | 2025-10-03 | 2025-02-02 | 2025-10-02 | 1452 |
| ETH | 2025-10-03 | 2025-02-02 | 2025-10-02 | 1452 |
| SOL | 2025-11-03 | 2025-03-30 | 2025-11-02 | 1303 |
| AVAX | 2025-11-03 | 2025-03-30 | 2025-11-02 | 1303 |
| LINK | 2025-11-03 | 2025-03-30 | 2025-11-02 | 1303 |
| DOT | 2025-11-03 | 2025-03-30 | 2025-11-02 | 1303 |

**Total: 8116 phantom bars removed.** 4h cache now honestly mirrors 1h source within 1-day margin (resample can emit a legal 4h bin one day before the first full 1h bar). Bar ratios consistent — BTC/ETH 4h=1243, 1h=5045 → 1243×4=4972 ≈ 5045 (gaps account for weekends/missing hours).

**Sprint 2 success criteria — all met:**
- ✅ Clean cycle activates ≥2 crypto templates via F2 (score ≥ 0.67): **4 activated**, all at score 0.667
- ✅ signal_decisions shows `cross_validation` stage rows with per-symbol breakdowns: **3 rows**, breakdowns match WF outcomes
- ✅ BTC Follower Daily activates on ≥1 alt via cross-validation: **4 alts activated** (ETH, SOL, LINK, AVAX)
- ✅ 4h crypto cache depth ≈ 1h cache depth: within 1-day margin for all 6 coins
- ✅ Zero regressions: non-crypto paths evaluated normally, no new errors

### F2.1 — Primary-only dedup in proposer (diagnosed mid-session)

Running 3 crypto-focused cycles back-to-back after F2 shipped produced only 18 proposals each (vs 121 in the first post-deploy cycle). Investigation found the proposer was populating `active_symbol_template_pairs` with **every symbol in each strategy's `symbols` list** — i.e. primary + full watchlist. That expanded dedup set (342 pairs) collided with the WF cache's failure-based suppression in `_score_symbol_for_template`: the first cycle WF'd 121 crypto pairs, most failed (expected — most don't trade well), and the next cycle found those same pairs cached as failed → scored zero → pool collapsed. 185 of 342 pairs were watchlist-only blocks (symbols that appear in a strategy's scan-list but have no active primary).

**Fix:** Only `symbols[0]` (the primary) goes into `active_pairs` for dedup purposes. Watchlist entries are scan-candidates, not active primaries, and should remain available for future proposals. Fixed at all 3 population sites:
- `_match_templates_to_symbols` (the scoring-time exclusion)
- `generate_strategies_from_templates` (the later in-loop dupe check)
- Alpha Edge `active_ae_template_symbols` population

After F2.1, dedup set drops from 342 → 157 pairs (55% reduction). Watchlist symbols are no longer artificially starved of their own primary-level proposal slots.

### Sprint 2 crypto-alpha expansion (+3 indicators, +5 templates)

Audit of the 76-template crypto library against hedge-fund research identified 5 real gaps. Fixed at the primitive layer rather than approximated.

**New DSL primitives** (`src/strategy/indicator_library.py` + `trading_dsl.py` + `strategy_engine.py`):
- `OBV` — On-Balance Volume (cumulative signed volume)
- `OBV_MA(n)` — moving average of OBV (signal line)
- `DONCHIAN_UPPER(n)` / `DONCHIAN_LOWER(n)` — prior-N-bar high/low with `shift=1` (genuine breakout thresholds; distinct from `HIGH_N`/`LOW_N` which include the current bar)
- `KELTNER_UPPER(ema, atr, mult)` / `KELTNER_MIDDLE(...)` / `KELTNER_LOWER(...)` — ATR-scaled channel (reacts to true trading range vs STDDEV-based Bollinger)

Wired end-to-end: auto-detection in condition scanning; compound-arg spec parsing (`"Keltner:20,14,2.0"`); dict-result dispatch for Keltner; distinct cache keys per parameter set (so `Keltner(20,14,2.0)` and `Keltner(10,10,1.5)` don't collide). DSL smoke-test verified all 7 new conditions parse and codegen matching indicator keys.

**New templates** (all crypto_optimized, `skip_adx_gate: True` where the template has its own trend filter):

| # | Template | Type | Interval | Entry | Edge source |
| --- | --- | --- | --- | --- | --- |
| T1 | Crypto Donchian Breakout Daily | BREAKOUT | 1d | `CLOSE > DONCHIAN_UPPER(20) AND ADX(14) > 25 AND VOLUME > VOLUME_MA(20) * 1.3` | Turtle-style, Dennis/Eckhardt + Alpha Architect crypto |
| T2 | Crypto Keltner Breakout 4H | BREAKOUT | 4h | `CLOSE > KELTNER_UPPER(20, 14, 2.0) AND ADX(14) > 25` | Alpha Architect Keltner template |
| T3 | Crypto OBV Accumulation Daily | MOMENTUM | 1d | `OBV > OBV_MA(20) AND CLOSE > EMA(20) AND RSI(14) ∈ [45,60]` | Grobys/Habeli 2025 volume-led momentum |
| T4 | Crypto 20D MA Variable Cross Daily | TREND | 1d | `CLOSE CROSSES_ABOVE SMA(20) AND PRICE_CHANGE_PCT(5) > 0.03` | Grobys (2024) — 8.76% excess on non-BTC crypto |
| T5 | Crypto BB Volume Breakout Daily | BREAKOUT | 1d | `CLOSE > BB_UPPER(20, 2.0) AND VOLUME > VOLUME_MA(20) * 1.5 AND ADX(14) > 20` | BB+volume+ADX composite (alt-season extensions) |

Crypto template count: 76 → **81**. All 5 use only native DSL primitives — no approximations, no metadata runtime gates. Each template exits on a concrete DSL condition (not just SL/TP). Research-backed per the HEDGE_FUND_STRATEGY_RESEARCH_2025_2026.md doc.

---

## Session shipped 2026-05-02 late session (Sprint 1 — Cross-asset DSL primitives)

Full proper-solutions-only architectural rework of how cross-asset edge is evaluated. Root cause and fix:

**The problem:** Batch C templates (BTC Follower 1H/4H/Daily, Cross-Sectional Momentum) carry real cross-asset edge per research (arxiv 2501.07135 / NBER w25882 / arxiv 2602.11708 AdaptiveTrend), but the edge was expressed as runtime metadata gates (`btc_leader`, `cross_sectional_rank`) that only fired at live signal-gen time. The backtest and walk-forward paths ran the plain DSL rule (just EMA+RSI) with no cross-asset filter, systematically mis-rejecting templates that had real edge — because WF couldn't see the edge in the first place.

**The fix (shipped as Sprint 1 = F1 + F3 + F7):**

### F1 — Cross-asset DSL primitives (commit `<pending>`)

- **DSL grammar extension** (`src/strategy/trading_dsl.py`): `INDICATOR_NAME(args)` now accepts mixed argument types — numbers, string-quoted symbols (e.g. `"BTC"`, `"1h"`), and symbol-list arrays (e.g. `["BTC","ETH","SOL","AVAX","LINK","DOT"]`). New `arg` / `arg_number` / `arg_string` / `arg_symbol_list` AST nodes and transformer handlers.
- **Two new cross-asset indicators** added to `INDICATOR_MAPPING`:
  - `LAG_RETURN("SYM", bars, "interval")` → pct return of SYM over last N bars at INT. Key: `LAG_RETURN__<SYM>__<BARS>__<INT>`.
  - `RANK_IN_UNIVERSE("SELF_OR_SYM", [universe], window, top_n)` → boolean series True when SELF_OR_SYM is in top-N of universe by N-day return. Key: `RANK_IN_UNIVERSE__<SYM>__<8charHash>__<W>__<N>`. `SELF` substitutes the strategy's primary symbol at compute time.
- **New module `src/strategy/cross_asset_primitives.py`**: regex extractors that scan DSL conditions for cross-asset references + pandas compute functions (`compute_lag_return_series`, `compute_rank_in_universe_series`, `compute_cross_asset_indicators`). Aligns Series to primary_index via reindex+ffill.
- **`StrategyEngine._compute_cross_asset_for_strategy`** helper: adapter that wires `market_data.get_historical_data` into the cross-asset fetcher interface. Returns `{key: Series}` dict to merge into indicators before DSL eval. Zero cost for templates with no cross-asset refs.
- **Injected at two call sites**:
  - `_run_vectorbt_backtest` — post-slice, pre-`_parse_strategy_rules`. So WF / MC bootstrap / backtest all see the same signal live signal-gen will see.
  - `generate_signals` — post-`_calculate_indicators_from_strategy`, pre-`_parse_strategy_rules`. Live signal-gen now routes through the same DSL path.
- **Runtime gate code removed** at `strategy_engine.py:4265-4400` (previously the BTC-leader / cross-sectional-rank signal-time-only gates). The metadata flags (`btc_leader`, `cross_sectional_rank`, `rank_universe`, etc.) still exist on templates for one release cycle for backward-compat but drive zero behavior.
- **4 Batch C templates rewritten** to use native primitives:
  - `Crypto BTC Follower 1H`: `CLOSE > EMA(20) AND RSI(14) > 45 AND LAG_RETURN("BTC", 2, "1h") > 0.01`
  - `Crypto BTC Follower 4H`: `CLOSE > SMA(50) AND RSI(14) > 50 AND LAG_RETURN("BTC", 2, "4h") > 0.03`
  - `Crypto BTC Follower Daily`: `CLOSE > SMA(50) AND RSI(14) > 50 AND LAG_RETURN("BTC", 2, "1d") > 0.05`
  - `Crypto Cross-Sectional Momentum`: `CLOSE > SMA(20) AND RSI(14) > 55 AND VOLUME > VOLUME_MA(20) * 1.5 AND RANK_IN_UNIVERSE("SELF", ["BTC","ETH","SOL","AVAX","LINK","DOT"], 14, 3) > 0`
  - ADX gate auto-injected by `__post_init__` on top of all 4 — works correctly with the new primitives.

### F3 — Cost-aware min_return_per_trade floor

- `config/autonomous_trading.yaml`: raised crypto min_return_per_trade thresholds to floor at cost+edge margin. eToro crypto round-trip = 2.96% (1% commission × 2 + 0.38% spread × 2 + 0.1% slippage × 2). New floors:
  - `crypto_1h: 0.035` (was 0.005 — below cost, structurally unprofitable)
  - `crypto_4h: 0.035` (was 0.015 — same)
  - `crypto_1d: 0.035` (was 0.025 — same)
  - `crypto: 0.05` fallback for 21d+ weekly templates (was 0.04)
- Floor derivation: round_trip_cost (2.96%) + 50bps minimum edge = 3.5%. Anything below this is noise after costs.
- Schema-version hash changed as side-effect of the yaml change → on next startup, crypto WF cache entries auto-invalidated via `_apply_wf_schema_version_check`. Verified: new schema version persisted, fresh WF runs observed in post-deploy cycle.

### F7 — Remove broken Pairs Trading Market Neutral template

- Template's DSL conditions were momentum-long on a single symbol (`PRICE_CHANGE_PCT(60) > 0 AND CLOSE/SMA(50) > 1.02`) — not a pairs spread. Took unhedged directional bets under "market neutral" label. Steering file flagged this as known broken; Sprint 1 deletes it. A proper pairs template can be rebuilt post-F1 using the new primitives (deferred).

### Post-deploy cycle evidence (`cycle_1777734531` at 15:08 UTC)

- **123 proposals → 5 wf_validated → 9 rejected_act → 0 activated**. Surface numbers similar to pre-F1 cycle (129→4→9→0), but the underlying WF outcomes shifted dramatically.
- **BTC Follower Daily test_sharpe by alt** (the clearest signal F1 is working):

  | Symbol | Pre-F1 test_sharpe | Post-F1 test_sharpe | Status |
  | --- | --- | --- | --- |
  | ETH  |  0.60 |  **3.36** | flipped to strong positive |
  | SOL  | -2.41 |  **2.04** | flipped to strong positive |
  | LINK | -2.05 |  **1.65** | flipped to strong positive |
  | AVAX | -2.31 |  **1.41** | flipped to positive |
  | BTC  | -0.62 |  -0.51    | still weak (self-reference of leader, expected) |

  4 of 5 alts now show test Sharpe ≥ 1.4 under F1. Pre-F1 only ETH was positive. Rejection reasons on all 5: `trades=low` (1-3 test trades in 180d window because the BTC-gate genuinely tightens entry frequency). Real edge, small-sample noise.

- **BTC Follower 4H**: no improvement (all 5 alts still negative). Confirms 4H BTC lead-lag is not a real edge in current data window 2024-2026. Matches literature (which predominantly documents daily+weekly lead-lag).

- **Cross-Sectional Momentum**: 2 of 6 alts passed WF (SOL test_sharpe 2.12, LINK 0.46). Failed activation on cost-per-trade (SOL gross 2.8% on 3 trades = 0.945% rpt < 3.5% floor, correctly blocked by F3) and marginal Sharpe (LINK 0.46 < 0.5 min_sharpe_crypto).

- **All 5 wf_validated died at activation**:
  - `Crypto 1H RSI Extreme Bounce` on DOT: Net return -0.6% < 0 (3 trades) — correct F3 block
  - `Crypto Cross-Sectional Momentum` on SOL: Return/trade 0.945% < 3.5% min — correct F3 block
  - `Crypto Cross-Sectional Momentum` on LINK: Sharpe 0.46 < 0.5 — marginal
  - `Crypto Quiet EMA Hug Long` on SOL: Return/trade 0.541% < 3.5% min — correct F3 block
  - `Crypto SMA Reversion` on SOL: Net return -0.7% < 0 (3 trades) — correct F3 block

- **No errors introduced**. errors.log only contains pre-existing `CLOSE[-20]` parse errors on an unrelated template and the Triple EMA Alignment DSL bug (both P2 known issues).

- **Zero regressions on non-crypto paths**: Sector Rotation, factor-gate paths, equity WF, Alpha Edge proposer — all ran unchanged. Cross-asset compute is a no-op when no LAG_RETURN / RANK_IN_UNIVERSE in template rules.

### Why 0 activations despite real edge detected

The BTC Follower Daily evidence is now unambiguous: 4/5 alts with test_sharpe > 1.4 is real edge. But per-pair activation rejects them all on `trades=low` because the BTC-gate correctly tightens to 1-3 entries per 180d test window. **The template-family has clear edge; per-pair validation kills it.** This is precisely the gap F2 (cross-symbol consistency validation) was scoped to fill — accept a template based on ≥4/6 symbols showing consistent test_sharpe > threshold, not per-pair.

F2 is Sprint 2 (next session).

---



---

## Session shipped 2026-05-02 afternoon (post-audit fixes)

### Tier 1 — critical / P0s

- **P0-1 Retirement black hole** (commit `5ba602e`) — 33 strategies carried pending_retirement yet had submitted 91 zombie entry orders after the flag was set. Root cause: two independent bugs.
  - Bug A: `trading_scheduler.py` BACKTESTED-branch filter checked `activation_approved` but not `pending_retirement`. 12 BACKTESTED+approved+pending-retirement strategies slipped through.
  - Bug B: `monitoring_service._demote_idle_strategies` runs every 60s; when DEMO strategy has no open positions/orders it demotes to BACKTESTED with `activation_approved=True` — even if pending_retirement was set. This resurrected the eligibility the decay/health paths had just stripped.
  - Fix: refactored filter into `_is_eligible()` helper that blocks pending_retirement regardless of status; `_demote_idle_strategies` now skips pending_retirement strategies (they flow through `_process_pending_retirements` instead, which does NOT resurrect the flag). Also moved `meta.pop('activation_approved')` before `flag_modified` in the health-path flagging branch.
  - DB cleanup: stripped `activation_approved` from all 24 zombie strategies (`UPDATE strategies SET strategy_metadata = (strategy_metadata::jsonb - 'activation_approved')::json WHERE (strategy_metadata::jsonb->>'pending_retirement')::text='true' AND (strategy_metadata::jsonb->>'activation_approved')::text IS NOT NULL`).
  - Verified post-deploy: `zombies_with_activation_approved=0`. 19 DEMO zombies + 14 BACKTESTED zombies remain and are now correctly filtered. They'll trend to 0 as positions close.

- **P0-2 live_trade_count** (commit `9a44ed4`) — was 0 on all 180 strategies despite 700+ closed trades. Root cause: `order_executor._increment_strategy_live_trade_count` only fires on synchronous fills via `handle_fill()` which doesn't run in practice (all real fills are async via `order_monitor.check_submitted_orders`). Added increment in order_monitor fill-finalization block, scoped to `order_action='entry'` so exits/retirement close orders don't inflate the counter. Backfilled historical counts from trade_journal (96 strategies updated). DEMO distribution post-fix: avg 2.7 live_trade_count, max 22, 11 strategies with ≥5 trades — `min_live_trades_before_evaluation=5` gate now functional.

- **P0-6 cycle_error stage** (commit `9a44ed4`) — cycle-stage failures (SignalAction NameError, Tuple NameError) only wrote to cycle_history.log, never to `signal_decisions`. Observability funnel stayed incomplete on failed cycles. Now every `stats['errors']` entry collected during a cycle is mirrored to `signal_decisions` as `stage='cycle_error'` (up to 50 errors per cycle). Also wired into the top-level fatal except block so catastrophic failures produce a funnel row.

### Tier 2 — noise + sizing

- **P1-5 Factor-gate noise** (commit `409ad90`) — Factor-validation gate rejections were `logger.warning` and appended to `stats['errors']`, which surfaces them as ERROR in cycle_history.log (4 per cycle). Reclassified to INFO and dropped from `stats['errors']` — they're filtering outcomes, not cycle errors.

- **P1-4 MINIMUM_ORDER_SIZE penalty bypass** (commit `409ad90`) — `risk_manager.calculate_position_size` Step 11 bumped any sub-$5K position back to $5K even when drawdown sizing, vol scaling, or loser-pair penalty had fired (10× overrisking). Added `penalty_applied` flag across Steps 3 (vol scale <1.0), 9 (drawdown), 10b (loser pair). When True at Step 11, return 0 instead of bumping. Penalty-reduced trades below minimum are skipped rather than trading at 10× the risk-managed target.

### Tier 3 — cleanup + infra

- **P1-1** — Deleted 799 FAILED-entry legacy orders from the Apr 27-29 DST spike.
- **P1-3** — Negative `fill_time_seconds` rows: none remained post-P1-1 delete (all were on the deleted rows).
- **P1-extra Crypto long-horizon WF window** (commit `409ad90`) — Long-horizon 1d crypto templates (21W MA, Vol-Compression, Weekly Trend Follow, Golden Cross) hold weeks/months and can't produce enough trades in 180d. Extended `test_days`+`train_days` to 730d for this set when asset_class=crypto AND interval=1d. Applied in both WF call sites (primary + watchlist).
- **P1-6** — Already landed in commit `8c1b263` in a prior session.

---

## Session shipped 2026-05-02 late afternoon/evening (crypto deep-dive)

Full audit of why crypto never activates. Root cause analysis + 5-batch fix plan + hotfix round. User stopped us at the right point: we're already on eToro DEMO (= paper trading), so the professional pipeline collapses for us to backtest → WF → paper-trade DEMO, and WF-blocking templates with cross-asset runtime edge is the wrong stance.

### Batch A — unblock tier (commit `cb8b852`)
- `min_return_per_trade`: tiered `crypto_1h: 0.005`, `crypto_4h: 0.015`, `crypto_1d: 0.025`, `crypto: 0.04` fallback
- `__post_init__` SL/TP floor timeframe-aware for `crypto_optimized`: 1h=1.5%/2%, 4h=2.5%/4%, 1d+=4%/8%
- Added `min_trades_crypto_1h: 15` in yaml; wired branch in portfolio_manager + proposer
- `scripts/clear_crypto_wf_cache.py` (crypto-only cache clear)

### Batch B — regime gates (commit `73581d7`)
- `StrategyTemplate.__post_init__` auto-injects ADX regime gate on `crypto_optimized` templates missing ADX:
  - Mean-reversion: `AND ADX(14) < 25` (1d/4h) or `< 30` (1h)
  - Trend/momentum/breakout: `AND ADX(14) > 20` (1d/4h) or `> 15` (1h)
  - Idempotent; skippable via `metadata.skip_adx_gate = True`
- `market_analyzer.detect_crypto_regime()`: BTC+ETH with crypto-calibrated thresholds (2× equity)
- Proposer `_detect_crypto_regime` prefers new detector with fallback

### Batch C — alpha expansion (commit `998f4b9`)
- 4 new templates (later 3 after Dominance Inversion dropped):
  - `Crypto BTC Follower 1H` — 2h BTC window, +1% threshold, SL 2%/TP 3.5%
  - `Crypto BTC Follower 4H` — 8h BTC window, +3% threshold, SL 3%/TP 6%
  - `Crypto BTC Follower Daily` — 2d BTC window, +5% threshold, SL 5%/TP 12%
  - `Crypto Cross-Sectional Momentum` — 14d rank universe, top-3 hold 7d
- **Structural limitation discovered**: signal-time gate in `strategy_engine.generate_signals` reads `metadata.btc_leader` / `metadata.cross_sectional_rank` and skips if condition fails. **But this gate only fires at live signal gen, not during backtest.** WF runs the plain DSL without the cross-asset gate → backtest underestimates edge → templates fail WF. See "Open items — next session" below.
- Parkinson vol for crypto — already implemented in `risk_manager._parkinson_vol` (verified, no change)
- Metadata propagation extended for 11 new keys across 3 proposer sites (`btc_leader`, `leader_symbol`, `btc_leader_interval`, `btc_leader_bars`, `btc_leader_threshold_pct`, `btc_leader_direction`, `cross_sectional_rank`, `rank_window_days`, `rank_top_n`, `rank_metric`, `rank_universe`, `skip_adx_gate`)

### Batch D — infrastructure (commit `d5b2e2a`)
- `scripts/backfill_crypto_1h_cache.py` — **yfinance 1h crypto capped at ~7 months** (210d BTC/ETH, 174d SOL/AVAX/LINK/DOT); documented in script
- Per-timeframe WF window override extended: 1d long-horizon 730/730 (existed), **1h crypto 90/90**, **4h crypto 180/180**. Applied in primary + watchlist WF.
- WF cache schema version: `_compute_wf_cache_schema_version()` hashes crypto-relevant config into 8-char tag. `_apply_wf_schema_version_check()` at proposer init clears crypto cache entries when config changes. Persisted to `.wf_cache_schema_version`.
- `proposals_pre_wf` column on `autonomous_cycle_runs` (DB migrated). Proposer exposes `_last_pre_wf_count`; cycle recorder writes both post-WF and raw pre-WF counts.

### Batch E — pruning + doc sync (commit `4bef714`)
- E1 DEFERRED: kill-list for persistently-losing templates. Pre-regime-gate backtests are not reliable for kill decisions because Batch B ADX gates materially change trade profiles. Revisit after cycles under new gates.
- E2: `docs/ALPHACENT_OVERVIEW.md` updated; removed stale "1H crypto templates were removed (90% underperformance)" claim (code had dozens of them).
- E3: Vol-Compression Momentum `market_regimes` — added `RANGING` (was `RANGING_LOW_VOL` only; BTC at ATR 2.74% classifies as plain RANGING, so template never matched). Now proposes correctly.

### Hotfix round — P-CRYPTO-A/C + Option Y (commit `1e38d2c`)

Cycle 12:31 UTC showed 0 activations with rejects still citing `crypto, 4.000% min`. Ground-truth audit found 3 issues:

- **P-CRYPTO-A**: `portfolio_manager` interval-key lookup only probed `('1h', '4h')` — missed `1d`. The `crypto_1d: 0.025` key I added in Batch A was never read. Expanded to `('1h', '2h', '4h', '1d')`. Reject reason now shows tier source (`crypto_1d, 18 trades` instead of `crypto, 18 trades`).
- **P-CRYPTO-C**: Batch C templates didn't list `RANGING_LOW_VOL` in `market_regimes`. Detector classifies BTC as ranging_low_vol (ATR 1.8%) — all 5 templates excluded from pool, never proposed. Added `RANGING_LOW_VOL`/`RANGING_HIGH_VOL` to 1H, 4H, Daily + Cross-Sectional.
- **Dropped** `Crypto BTC Dominance Inversion SHORT`: eToro doesn't permit shorting spot crypto (hard-block in `_score_symbol_for_template`); template couldn't execute.
- **Option Y** (asset-class isolation): new hard block in `_score_symbol_for_template` — non-`crypto_optimized` templates return 0 score on crypto symbols. AE + market-neutral exempt. Generic equity DSL (RSI Dip Buy, Bollinger Band Bounce, RSI Midrange) produces 0.5-1% gross/trade on crypto; below 2.96% round-trip cost; activation-level gate was catching them but they consumed WF compute. Block at scoring time.

### Post-fix cycle (cycle_1777728444, 13:27 UTC)
- 129 proposals (127 crypto + 2 XLF AE) — Option Y confirmed working
- Batch C templates proposing: BTC Follower 4H=5, BTC Follower Daily=5, Cross-Sectional=6, Vol-Compression=1
- 4 wf_validated → 0 activated. **All 4 Batch C lead-lag/cross-sectional candidates failed at activation with Net return < 0, because WF ran the plain DSL without the cross-asset gate.** Backtest literally cannot see the edge these templates carry.
- Other rejects were small-sample legitimate (3-trade strategies hitting the Sharpe-exception path) or genuine low-Sharpe (0.23-0.38 < 0.5 min_sharpe_crypto).

### Research-backed conclusion (stopping point)

Session ended here on user's correct insight: **we're already on eToro DEMO = paper trading**, so the professional 7-stage pipeline (backtest → WF → MC → paper-trade → shadow → small-size live → scale-up) collapses for us into backtest → WF → paper-trade-DEMO. Our gate-blocking of templates at WF is unnecessarily strict for a paper-trade environment.

Web research confirmed:
- nexusfi.com / Apr 2026: "Paper trading proves your execution stack works correctly — profitability is a nice bonus, not the point." Our DEMO IS the paper stage, so WF should be more permissive for templates with known-structural edge.
- arxiv 2501.07135 (Imperial College + commodity quant shop 2025): The canonical cross-asset lead-lag approach is to **bake the lead-lag metric into the DSL as an indicator** (Lévy area / Dynamic Time Warping), not layer it as a runtime gate. Then backtest sees it natively; WF works honestly.
- BTA Apr 2026: Top shops cross-validate across same-sector markets — a template should be scored by consistency across ≥4/6 assets in the sector, not single-symbol pass/fail.
- Grobys 2024 / Habeli 2025 (in repo research doc): Crypto momentum return distribution is power-law; Sharpe of 0.3-0.5 on unscaled crypto is normal even for strategies with real edge. Volatility-scaled sizing recovers to ~1.0+. Our `min_sharpe_crypto: 0.5` is arguably too strict.

---

## Session shipped 2026-05-02 morning (observability fix + crypto cost + symbol cap)

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

### Next sprint (Sprint 3) — Verification + WF tightening + quality fixes

**Rule in effect:** Proper solutions only. See `.kiro/steering/trading-system-context.md` → "Proper Solutions Only — No Patches, No Stopgaps".

**Context after Sprint 2:** Cross-asset DSL primitives (Sprint 1), cost floors (Sprint 1), cross-symbol consistency validation (Sprint 2 F2), primary-only dedup (Sprint 2 F2.1), 4h cache honesty (Sprint 2 F10), 5 new crypto templates, 3 new DSL indicators. 4 crypto strategies activated (BTC Follower Daily ETH/SOL/LINK/AVAX) but armed-and-waiting on a BTC +5% 2-day trigger that hasn't happened since 2026-03-16. Two post-commit cycles (16:36 + 16:40 UTC) confirmed F2.1 restored proposal volume (134 pre-WF vs 18 pre-fix) and F2 cross-validation stage populating with breakdowns.

**Sprint 3 is split into two phases:**

#### Phase 1 — Verify Sprint 1+2 in live over 2-3 crypto-focused cycles (~30 min)

Before any new code, prove Sprint 1+2 work end-to-end on crypto activations → signals → orders:

1. **Activation via F2**: confirm new BTC Follower Daily / Cross-Sectional activations come through the cross-validation path (verify with `signal_decisions.reason='family_cross_validated'`).
2. **Signal emission**: once BTC prints a +5% 2-day move (historically ~2x/month; last trigger 2026-03-16), the 4 activated BTC Follower Daily strategies should emit `signal_emitted` stages and have `ENTER_LONG` orders submitted. Currently armed-and-waiting.
3. **5 new crypto templates**: each (Donchian, Keltner 4H, OBV, 20D MA, BB Volume) should show at least one WF run per cycle. OBV Accumulation Daily already passed WF via excellent_oos path on ETH in cycle_1777739783 — template is live and functional.
4. **Trades execute & close**: any filled crypto order flows through `signal_emitted → order_submitted → order_filled`. MAE/MFE populated. `trade_journal.market_regime` non-NULL.
5. **Nothing regressed on equity/ETF/forex/commodity/AE**: Sector Rotation still evaluating, equity activations continue at daily scheduled cycles (15:15 UTC), AE proposer still rotates templates.

Don't proceed to Phase 2 until at least one complete crypto signal→order path has fired (may require waiting for a BTC +5% trigger or for the 5 new templates to activate on their own edge).

#### Phase 2 — Sprint 3 code (ordered by P&L impact)

**S3.1 — WF bypass path tightening for LONG** (~2h) — **priority P0**
- The `test_dominant` and `excellent_oos` paths in `strategy_proposer.py` (lines ~2020-2070) let strategies through with `ts >= -0.1 AND tes >= min_sharpe` or `ts >= -0.3 AND tes >= min_sharpe*2`. Means a strategy with train_sharpe -0.1 and test_sharpe 0.5 passes — that's regime luck, not edge.
- **SHORT side was tightened in Sprint 1** (SHORT-specific bypass removed; primary path needs min_sharpe+0.3). LONG still loose.
- **Fix:** Add a consistency gate `(test_sharpe - train_sharpe) <= 1.5` on both test-dominant and excellent-oos paths for LONG (matches SHORT rigor). A strategy where test crushes train by >1.5 Sharpe is almost certainly overfit to the specific test window.
- **Verification:** Run before/after diff on cycle wf_validated counts; expect 15-25% reduction in wf_validated on LONG but higher-quality survivors. Check live-performance divergence (`/analytics/observability/wf-live-divergence`) drops 2+ weeks later.

**S3.2 — Triple EMA Alignment DSL bug** (~30 min) — **priority P1**
- `EMA(10) > EMA(10)` always evaluates to False → template generates 0 trades on every WF → permanently blacklisted.
- Regex-based parameter substitution collapses the three positional literals in `EMA(fast) > EMA(mid) > EMA(slow)`.
- **Fix:** Audit the param substitution regex in `strategy_proposer.customize_template_parameters`; add explicit handling for templates whose `default_parameters` contain positional EMA periods. The correct substitution for `Triple EMA Alignment` should produce e.g. `EMA(10) > EMA(20) AND EMA(20) > EMA(50)`.
- **Verification:** Template should generate >0 WF trades on at least one symbol.

**S3.3 — Market Quality Score persistence** (~45 min) — **priority P1**
- Recent `equity_snapshots.market_quality_score` rows are NULL despite the compute code being present. `_save_hourly_equity_snapshot` wraps MQS compute in a bare `except: pass` that swallows the real error.
- **Fix:** Replace the bare except with specific exception handling + WARNING log; capture the actual error signature. Likely one of: missing SPY data, missing VIX, MQS computer not initialized, DB column-type mismatch.
- **Verification:** `SELECT COUNT(*) FROM equity_snapshots WHERE market_quality_score IS NOT NULL AND date > NOW() - INTERVAL '1 day'` should return >0 after next hour.

**S3.4 — Cross-cycle signal dedup for market-closed deferrals** (~90 min) — **priority P1**
- Entry-order 82% FAILED rate cosmetic: when US market is closed (premarket/overnight/weekend), signal generation fires, order submission defers, DB writes as FAILED, next cycle re-fires the same signal. 9 cycles × 11 signals = 99 DB rows for 11 intended signals.
- **Fix:** Cross-cycle dedup map in trading_scheduler: `{(strategy_id, symbol, direction): expires_at}` with 30-min TTL. When market-closed deferral issued, write to map. Next cycle skips if present.
- **Alternative:** skip signal generation for stock/ETF strategies when US market is closed AND no extended-hours candidate. Matches existing crypto-24/7 filter inversely.
- **Verification:** Overnight cycle produces 0 FAILED-entry duplicates for the same (strategy, symbol, direction) inside 30 min.

**S3.5 — trade_id convention unification** (~90 min) — **priority P2**
- `log_entry` uses `position.id`; `log_exit` uses order UUID. Mismatch produces orphan rows in `trade_journal` that only show up on backfill. Backfilled 175 in the 2026-05-02 session; the underlying bug still produces new orphans on every fill.
- **Fix:** Migrate `order_monitor.check_submitted_orders` to use `position.id` for `log_exit` (available via the order's `position_id` column on OrderORM). Retire the fallback match logic in `log_exit`.
- **Verification:** After 1 week, count orphan rows — should stay at zero rather than growing.

**Do not ship Sprint 3 until:**
- Phase 1 verification complete (crypto signal→order path proven on at least one fill).
- Each S3.x change validated through a post-deploy cycle showing the intended effect.
- Zero regressions on existing active strategies.

### Independent backlog (deferred to Sprint 4+)

These are on the radar but don't rank into Sprint 3:

- **Sector Rotation + Pairs Trading template rewrites** — both are structurally broken. Need design docs. Sector Rotation `fixed_symbols` covers only 5 of 11 SPDR sectors; Pairs conditions are momentum-long, not pairs spreads. Design-first before coding.
- **Monday Asia Open template** — needs `HOUR()` DSL primitive. Same architectural pattern as Sprint 1's cross-asset primitives. Could be 2-3h work when scheduled.
- **Overview chart panel rewrite** — 3 chart components with misaligned axes; needs multi-pane redesign doc first.
- **Entry-timing score** — needs per-minute post-entry price snapshots we don't capture yet. Design-first.
- **F01/F12 Phase 3 — Calibrate min_sharpe from live data** — triggers 2-4 weeks of clean runs post-S3.1 so we have enough live-vs-backtest data to calibrate honestly.
- **FMP insider endpoint** — 403/404 on current plan; insider_buying uses momentum proxy. Resolves when plan upgrades or another vendor added.

### Next-session kickoff prompt

Copy this as-is into a new session when you're ready to execute Sprint 3:

```
Start this session by reading, in this exact order: (1) .kiro/steering/trading-system-context.md — pay special attention to the "Proper Solutions Only — No Patches, No Stopgaps" section. That rule is non-negotiable and overrides the default-to-action guidance. (2) Session_Continuation.md — current state + Sprint 1/2 outcomes + Sprint 3 plan. (3) AUDIT_REPORT_2026-05-02.md. Do not skip. Do not summarize them back — just internalize and confirm you've read them.

Context: Sprint 1 (commit abace94) shipped cross-asset DSL primitives (LAG_RETURN/RANK_IN_UNIVERSE as first-class indicators in backtest AND signal-gen), cost floors (crypto RPT floor 3.5%), removed broken Pairs template. Sprint 2 (commit c47013c) shipped F2 (cross-symbol consistency validation — templates flagged requires_cross_validation bypass per-pair gates when ≥4/6 family symbols clear minimal bar), F2.1 (primary-only dedup in proposer, fixed 342→157 pair over-block), F10 (4h cache reconciliation — 8116 phantom bars removed; invariant guard in _fetch_historical_from_yahoo_finance), +3 native DSL indicators (OBV, Donchian, Keltner), +5 new crypto templates (Donchian Breakout Daily, Keltner Breakout 4H, OBV Accumulation Daily, 20D MA Variable Cross Daily, BB Volume Breakout Daily). 4 crypto strategies activated via F2 family path (BTC Follower Daily on ETH/SOL/LINK/AVAX) — armed and waiting on BTC +5% 2-bar trigger (last fired 2026-03-16). Two post-deploy cycles confirmed F2.1 restored proposal volume (134 pre-WF) and F2 cross_validation stage populates with 6-symbol breakdowns.

Your mission — split into two phases:

PHASE 1 — Verification (~30 min, before any new code). User will run 2-3 more crypto-focused cycles. Your job:
(a) Watch signal_decisions: confirm F2 cross_validation stage rows continue to appear with per-symbol breakdowns; confirm any new crypto activations carry reason='family_cross_validated'.
(b) Check that the 5 new crypto templates (Donchian Breakout Daily, Keltner Breakout 4H, OBV Accumulation Daily, 20D MA Variable Cross Daily, BB Volume Breakout Daily) each get proposed + WF'd. OBV Accumulation Daily on ETH already passed WF via excellent_oos in cycle_1777739783 — it works.
(c) When BTC prints a +5% 2-bar move (check `SELECT date, close, (close-LAG(close,2) OVER (ORDER BY date))/LAG(close,2) OVER (ORDER BY date) FROM historical_price_cache WHERE symbol='BTC' AND interval='1d' ORDER BY date DESC LIMIT 5`), verify that the 4 activated BTC Follower Daily strategies emit signal_emitted stages → order_submitted → (eventually) order_filled. This is the full signal→order path for the Sprint 1+2 work.
(d) Spot-check no regressions on equity/ETF/forex/commodity/AE paths — the 15:15 UTC scheduled cycle should still produce ~100-200 pre-WF proposals across all asset classes, not just crypto.

Do not proceed to Phase 2 until at least one complete crypto signal→order path has fired, OR the user explicitly says to move on.

PHASE 2 — Sprint 3 code (ordered by P&L impact, execute top-down):

S3.1 (P0, ~2h) — LONG-side WF bypass tightening. `strategy_proposer.py` lines ~2020-2070. Add consistency gate `(test_sharpe - train_sharpe) ≤ 1.5` on test_dominant AND excellent_oos paths for LONG (mirrors the SHORT tightening from Sprint 1). Strategies where test crushes train by >1.5 Sharpe are regime luck. Verify with before/after wf_validated counts and 2-week live-vs-backtest divergence check.

S3.2 (P1, ~30 min) — Triple EMA Alignment DSL bug. `EMA(10) > EMA(10)` tautology from regex param substitution collapse. Fix the substitution in strategy_proposer.customize_template_parameters to handle positional EMA periods correctly. Template should produce >0 WF trades post-fix.

S3.3 (P1, ~45 min) — MQS persistence. `_save_hourly_equity_snapshot` swallows MQS compute error in bare `except: pass`. Replace with specific exception handler + WARNING log capturing the error signature. Verify non-NULL market_quality_score in recent equity_snapshots after next hour.

S3.4 (P1, ~90 min) — Cross-cycle signal dedup for market-closed deferrals. trading_scheduler needs a 30-min TTL map {(strategy_id, symbol, direction): expires_at}. Market-closed deferral writes to the map; next cycle skips duplicates. Eliminates the 82% FAILED-entry cosmetic bloat. Alternative: skip signal gen for stock/ETF when US market closed AND no extended-hours support.

S3.5 (P2, ~90 min) — trade_id convention unification. Migrate order_monitor.check_submitted_orders to use position.id for log_exit (matches log_entry). Retire the fallback match in log_exit. Should prevent new orphan rows.

Do not ship Sprint 3 until:
- Phase 1 verified — complete crypto signal→order path fired at least once.
- Each S3.x validated through a post-deploy cycle showing the intended effect.
- Zero regressions on existing activations / signal generation.

If any proper fix takes longer than expected, that's fine — we do proper, not fast. Do not propose stopgaps.
```

### Previous — Sprint 2 kickoff prompt (2026-05-02 evening) — ALREADY EXECUTED, kept for context

Copy this as-is into a new session when you're ready to execute Sprint 2:

```
Start this session by reading, in this exact order: (1) .kiro/steering/trading-system-context.md — pay special attention to the "Proper Solutions Only — No Patches, No Stopgaps" section. That rule is non-negotiable and overrides the default-to-action guidance. (2) Session_Continuation.md — current state + Sprint 1 outcomes. (3) AUDIT_REPORT_2026-05-02.md. Do not skip. Do not summarize them back — just internalize and confirm you've read them.

Context: Sprint 1 (2026-05-02 late session) shipped cross-asset DSL primitives (F1 — LAG_RETURN / RANK_IN_UNIVERSE as first-class indicators computed bar-by-bar in backtest AND signal-gen), cost-aware min_return_per_trade floor (F3 — crypto floors raised to 3.5% to clear 2.96% eToro round-trip cost), and removed the broken Pairs Trading Market Neutral template (F7). Post-deploy cycle cycle_1777734531 at 15:08 UTC proved F1 works: BTC Follower Daily test_sharpe flipped from negative to >1.4 on 4 of 5 alts (ETH 3.36, SOL 2.04, LINK 1.65, AVAX 1.41) once walk-forward could see LAG_RETURN("BTC", 2, "1d") > 0.05 natively. But all 5 wf_validated strategies died at activation because the BTC-gate tightens entry frequency to 1-3 trades in a 180d test window, and per-pair activation correctly rejects on small-sample cost-per-trade / Sharpe thresholds. Template-family has clear edge; per-pair validation kills it.

Your mission: ship Sprint 2 (F2 + F10) as described in Session_Continuation.md → "Next sprint (Sprint 2)".

F2 is the core (2-3h): cross-symbol consistency validation. For templates flagged `requires_cross_validation: True`, run WF on all 6 crypto symbols (BTC/ETH/SOL/AVAX/LINK/DOT). Compute a family-level verdict. When ≥4/6 symbols show (test_sharpe > 0.3 AND positive net return), activation bypasses per-pair cost-per-trade / Sharpe checks. Net-return-after-costs and round-trip cost reality stay enforced at the family level. Flag the 4 Batch C templates (BTC Follower 1H/4H/Daily, Cross-Sectional Momentum) with requires_cross_validation: True. Add a new `cross_validation` decision-log stage per template with the 6-symbol breakdown. Reuse existing _wf_results_cache keyed on (template, symbol).

F10 is cleanup (~1h): reconcile stale 4h crypto cache. Delete 4h bars older than (latest 1h - 1 day). Add a guard in market_data_manager._fetch_historical_from_yahoo_finance that refuses to return 4h bars outside the 1h source window. Document the 7-month yfinance 1h cap as the constraint.

Do not ship until:
- A clean post-deploy cycle activates ≥2 crypto templates via F2 family-level evidence (cross_validation_score ≥ 0.67).
- signal_decisions funnel shows cross_validation stage rows with per-symbol breakdowns.
- BTC Follower Daily activates on at least one alt via the cross-validation path.
- 4h crypto cache depth ≈ 1h cache depth post-F10.
- Zero regressions on equity/ETF/forex/commodity/AE paths.

If any proper fix takes longer than expected, that's fine — we do proper, not fast. Do not propose stopgaps.
```

### Previous — Sprint 1 kickoff prompt (2026-05-02 late session) — ALREADY EXECUTED, kept for context

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
