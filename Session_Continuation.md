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

## Current System State (May 3, 2026, ~15:20 UTC, post-WF-window-refactor)

- **Equity:** ~$480K (unchanged)
- **Open positions:** 84
- **Active strategies:** 63 DEMO + 5 BACKTESTED/approved = **68 trading strategies**
- **Crypto-native strategies:** 5 (4 BTC Follower Daily ETH/SOL/LINK/AVAX + 1 BTC Follower 4H ETH, the first non-F2-bypass crypto activation)
- **Directional split:** ~82 LONG / ~5 SHORT (unchanged)
- **Market regime (equity):** `STRONG UPTREND` (20d +10.83%, 50d +5.49%, ATR/price 1.08%)
- **Market regime (crypto):** `RANGING_LOW_VOL` (20d +2.3%, 50d +6.6%, ATR 1.7%)
- **VIX:** 16.89
- **Mode:** eToro DEMO
- **Last cycle:** `cycle_1777816532` at 15:15 UTC, 59s, 0 activations (6 rejections — honest output, all on Sharpe/RPT floors), clean errors.log.
- **Scheduled cycles:** daily 15:15 UTC + weekdays 19:00 UTC

**Two sprints shipped today:**

1. **Morning** (commit `b10cb6c`): three cost-math bug fixes — per_symbol precedence in backtest engine, RPT gate unit mismatch, edge_ratio numerator. See "Session shipped 2026-05-03 morning" below. First non-F2-bypass crypto activation (BTC Follower 4H ETH LONG) confirmed in `cycle_1777808795`.

2. **Afternoon** (this session): WF-window single-source-of-truth refactor. The live per-(asset_class, interval, template) walk-forward windows are now in `config/autonomous_trading.yaml` under `backtest.walk_forward.asset_class_windows` + `long_horizon_templates`. The proposer's `_select_wf_window()` helper is the only Python site picking windows, called from both WF call sites. Zero behavioural change — verified via `scripts/verify_wf_window_helper.py` (8 archetypes, identical outputs) and the first post-deploy cycle showing every expected key firing with the exact pre-refactor values. See "Session shipped 2026-05-03 afternoon" below.

**BTC Follower Daily armed but waiting on trigger:** 4 of 5 strategies (activated 2026-05-02) still haven't fired. Entry gate is `LAG_RETURN("BTC", 2, "1d") > 0.05` — BTC's current 2-bar return is below threshold. Gate fires ~2x/month historically.

---

## Session shipped 2026-05-03 afternoon (WF-window single-source-of-truth refactor)

The yaml `backtest.walk_forward.train_days: 365 / test_days: 180` values were misleading — they looked like the live walk-forward windows but were only a fallback. The real windows were overridden per-strategy in `strategy_proposer.py` across five hardcoded branches, duplicated across two call sites (primary WF path at ~1702-1792, watchlist WF path at ~2750-2787). Non-crypto 1h/4h were further capped at `strategy_engine.walk_forward_validate` (~1625-1650) by Yahoo's ~7-month 1h data limit. Operators reading the yaml couldn't tell what actually ran; any future change had to land in two Python sites plus the yaml.

**What shipped:**

- **`config/autonomous_trading.yaml`** — new `backtest.walk_forward.asset_class_windows` block with 7 keys (`crypto_1h`, `crypto_4h`, `crypto_1d`, `crypto_1d_longhorizon`, `non_crypto_1d`, `non_crypto_1h`, `non_crypto_4h`) and a `long_horizon_templates` list (previously a hardcoded set in Python). Header comment documents the Yahoo 7-month 1h cap constraint on `non_crypto_1h` / `non_crypto_4h`. The yaml `train_days` / `test_days` remain editable from the Settings UI as the fallback when no asset-class-window key matches.

- **`src/strategy/strategy_proposer.py`** — new `_select_wf_window(strategy, end_date) -> (train, test, start, end)` helper. Loads the asset_class_windows + long_horizon_templates + fallback once per instance in `_load_wf_window_config()` at `__init__`. Picks the key via `(is_crypto, interval, template_name)` detection, anchors `start = end - (train + test)`, logs selection at INFO (`WF window [<key>]: <name> → train=Xd test=Yd`), fails open to the yaml fallback on any error. Both WF call sites now delegate to the helper — the two 90-line / 40-line override blocks are gone. One place in Python picks windows.

- **`src/strategy/strategy_engine.py`** — Yahoo data-source caps at `walk_forward_validate` retained (180/90 non-crypto 1h, 240/120 non-crypto 4h) as a safety net against future yaml drift. Added INFO log when the cap kicks in so silent truncation is no longer silent: `WF window capped by data-source limit (Yahoo ..., non-crypto): requested train=Xd test=Yd → truncated to train=X'd test=Y'd`.

- **`src/api/routers/config.py`** — extended `AdvancedReadonly` with `wf_asset_class_windows: Dict[str, Dict[str, int]]` and `wf_long_horizon_templates: List[str]`. Populated from the yaml in the GET `/config/autonomous` endpoint. Not added to the PUT schema — these values are tied to data-source constraints; editable surface is still the fallback `wf_train_days` / `wf_test_days` which matter when no key matches.

- **`frontend/src/pages/SettingsNew.tsx`** — Card 6 (Walk-Forward & Direction-Aware) now shows a read-only "Per-Asset-Class Windows" table below the editable train/test inputs. 7 keys × (train, test), the long-horizon template list, and a note pointing operators to the yaml for edits.

- **`scripts/verify_wf_window_helper.py`** — regression check. Instantiates a `StrategyProposer` with mocked deps, calls `_select_wf_window` for 8 archetype strategies (BTC Follower 4H ETH, Weekly Trend Follow BTC, BTC Follower Daily ETH, Hourly RSI Bounce SOL, Fast EMA Crossover AAPL, RSI Dip Buy EURUSD 1h, 4H Bollinger SPY, fallback path). Asserts each returns identical `(train, test)` to the pre-refactor hardcoded branches. All pass.

**Post-deploy verification (`cycle_1777816532` at 15:15 UTC):**

- Config load: `WF window config loaded: 7 asset-class keys, 4 long-horizon templates, fallback=365d train / 180d test`
- Helper firing for every key observed in the cycle:
  ```
  WF window [crypto_1d]:            Crypto Trend Breakout ETH LONG          → train=365d test=365d
  WF window [non_crypto_1d]:        Keltner Channel Breakout TXN LONG       → train=730d test=365d
  WF window [non_crypto_4h]:        4H EMA Ribbon Trend Long AVGO LONG      → train=240d test=120d
  WF window [crypto_1d_longhorizon]: Crypto Vol-Compression Momentum BTC    → train=730d test=730d
  WF window [crypto_4h]:            Crypto 4H MACD Trend LINK LONG          → train=365d test=365d
  WF window [crypto_1h]:            Crypto EMA Ribbon BTC LONG              → train=365d test=365d
  ```
- Cycle outcome: 6 proposals → 6/6 WF passed → 0 activated, 6 rejected on Sharpe/RPT/ex-post floors. Same rejection shape as `cycle_1777808795` earlier today. No regressions.
- errors.log clean since deploy. Service restart clean. Frontend build clean.

**What this unblocks:** future window changes happen in yaml (visible to ops), not Python (invisible). The engine-level Yahoo cap is now observable — when someone widens `non_crypto_1h` in yaml by mistake, the truncation log line makes it obvious.

**What this is NOT:** a calibration change. Every window value is identical to the pre-refactor effective runtime value. Any future widening requires its own sprint with data.

---

## Session shipped 2026-05-03 morning (per-position RPT / per_symbol cost / edge_ratio unit fix)

After 10 cycles producing 0 crypto activations despite 8/8 WF passes, the user asked for a forensic audit of cost math + MC bootstrap. Investigation (INVESTIGATION_2026-05-03.md) found three interlocked bugs. **MC bootstrap math is clean.** The bugs are in the activation gate and cost-config plumbing.

### Bug #1 — `per_symbol` cost overrides silently ignored in backtest engine

**Code path:** `src/strategy/strategy_engine.py:1247-1249` (+ spread/overnight resolution at ~3347 and ~3398)

The yaml has `transaction_costs.per_symbol.BTC` and `.ETH` blocks with tighter-than-altcoin costs (2.18% / 2.20% round-trip vs 2.96% altcoin default), plus a `cost_model.py` comment documenting precedence "per_symbol > per_asset_class > global." But only `cost_model.round_trip_cost_pct` (observability) honored that precedence. The backtest engine read `per_asset_class` only.

Impact: BTC and ETH backtests paid altcoin-rate 2.96% round-trip instead of their configured 2.18-2.20%. ~0.76% phantom cost per round-trip on every BTC/ETH backtest. Verified with real log numbers: `Spread cost: $545.18` on 6 trades × $12K avg matches 0.38% spread (altcoin default), not the 0.05% per-symbol override for ETH.

**Fix:** added precedence lookup (`per_symbol > per_asset_class > global`) at all three config read sites. Matches the precedence documented in cost_model.py.

### Bug #2 — RPT gate unit mismatch (THE dominant killer)

**Code path:** `src/strategy/portfolio_manager.py:1307`

`return_per_trade = backtest_results.total_return / backtest_results.total_trades`

`total_return` is vectorbt's `(final_value − init_cash) / init_cash` — a fraction of init_cash. At fractional position sizing (avg 10-30% of init_cash per trade), this understates per-position return by `1 / position_size_pct` (3-10x).

But `min_return_per_trade: 0.030` was derived in Sprint 1 F3 as a **per-position** floor: "round_trip_cost (2.96%) + 50bps edge = 3.5%". The gate was comparing a per-init_cash metric against a per-position threshold.

Concrete example from `cycle_1777803232` (BTC Follower 4H ETH LONG):
- Position size: $11,956 (12% of init_cash)
- Net return: 4.99% of init_cash, 6 trades
- Gate computed `return_per_trade = 0.831% of init_cash` → FAIL vs 1.8% threshold
- Real per-position net: **6.96% per position**, edge_ratio **3.35×** over cost

Effective gate demand was `3% / 0.12 = 25% gross per position` — 8-10x the real round-trip cost, which is why legitimate swing templates with comfortable per-position edge (BTC Follower 4H ETH, Cross-Sectional Momentum) were being silently rejected.

**Fix:** Extended `BacktestResults` with `avg_trade_value` + `init_cash` fields (populated by strategy_engine `_run_vectorbt_backtest`). At activation, RPT gate divides raw metric by `avg_trade_value / init_cash` to get per-position return before comparison. AE path writes `avg_trade_value == init_cash` so no scaling (AE already stores per-position returns directly). Legacy cached entries with `avg_trade_value == 0` fall through to the old math so we never silently pass a bad strategy.

### Bug #3 — `cost_model.edge_ratio` same unit mismatch (observability-only)

**Code path:** `src/strategy/cost_model.py:225-260`

Same numerator/denominator-on-different-bases shape as Bug #2. Reported `edge_ratio=0.54` for BTC Follower 4H ETH when real per-position edge_ratio was 3.35. Observability metric, didn't gate — but misleading on the Data Page.

**Fix:** `edge_ratio(...)` now accepts optional `avg_trade_value` + `init_cash` and scales the numerator to per-position before dividing by `round_trip_cost`. Both callers (portfolio_manager activation path, strategy_proposer WF audit) pass these from BacktestResults.

### Monte Carlo bootstrap — clean

Walked through `src/strategy/strategy_proposer.py:2002-2103`. Uses vectorbt's `records_readable.Return` which is per-position return (verified against vectorbt GitHub discussion #264 — `Return = PnL / (size × entry_price)`). Annualization factor is `sqrt(trades_per_year)` which is textbook. Asset-class-aware percentiles (p5 for equity, p10 for crypto, post-S3.0c) are defensible against Efron-Tibshirani heavy-tail guidance. **MC is not part of the problem.**

### WF cache schema version bump

Bumped `rpt_per_position_2026_05_03` marker and added `per_symbol` costs to the schema version hash. Stale cached WF entries from pre-fix math are invalidated on next cycle so the corrected numbers are used everywhere. Also ran `scripts/clear_crypto_wf_cache.py` at deploy time to force a cold cycle — 138 crypto entries dropped (23 validated + 115 failed).

### Files changed

- `src/models/dataclasses.py` — `BacktestResults.avg_trade_value` + `.init_cash` added with safe defaults
- `src/strategy/strategy_engine.py` — per_symbol cost precedence at 3 call sites; `avg_trade_value` hoisted + persisted on BacktestResults return; to_dict / from_dict serialize/deserialize the new fields; AE backtest writes `avg_trade_value == init_cash` as no-op marker
- `src/strategy/portfolio_manager.py` — RPT gate per-position normalization with legacy fallback; pass through avg_trade_value + init_cash to edge_ratio; rejection reason now includes `basis=per-position @ X.X% sizing`; cost-check-passed log shows the per-position RPT
- `src/strategy/cost_model.py` — `edge_ratio` takes optional avg_trade_value + init_cash and scales accordingly
- `src/strategy/strategy_proposer.py` — edge_ratio call at WF audit passes the new params; WF cache schema version bumped with `per_symbol` included

Added: `INVESTIGATION_2026-05-03.md` (full audit write-up), `scripts/investigate_2026_05_03_cost_math.py` (log-number arithmetic reproduction), `scripts/investigate_2026_05_03_verify_fix.py` (unit tests).

### Post-deploy verification (cycle_1777808795, 2026-05-03 11:52 UTC)

**Activation funnel:** 8 proposals → 8/8 WF passed → 1 activated + 7 rejected.

```
[ACTIVATION] 1 activated:
    + [DSL] Crypto BTC Follower 4H ETH LONG    ETH  S=1.44 wr=67% dd=-1.8% t=6

[ACTIVATION REJECTED] 7:
  x Crypto Weekly Trend Follow ETH LONG  S=0.57 wr=30%
    Return/trade 0.809% < 2.500% min (crypto_1d+template_override, 10 trades,
                                       gross 0.8%, basis=per-position @ 9.6% sizing)
  x Sector Rotation XLF LONG             S=0.17 wr=40% -- Sharpe 0.17 < 0.5
  x Crypto EMA Ribbon BTC LONG           S=-0.01 wr=33% -- Sharpe -0.01 < 0.201
  x Crypto SMA Reversion DOT LONG        S=-0.12 wr=46% -- Sharpe -0.12 < 0.201
  x Crypto SMA Reversion LINK LONG       S=-0.23 wr=50% -- Sharpe -0.23 < 0.201
  x Crypto EMA Ribbon ETH LONG           S=-0.78 wr=25% -- Sharpe -0.78 < 0.201
  x Crypto Keltner Range Trade LINK LONG S=-0.61 wr=33% -- Sharpe -0.61 < 0.201
```

**Fix verification:**
- ✅ `basis=per-position @ X.X% sizing` label appears in RPT rejection messages
- ✅ `rpt=7.712% (per-position @ 12.0% sizing)` on pass path — matches the fixed math
- ✅ `edge_ratio=4.51` at activation log — Fix #3 producing correct per-position edge
- ✅ First non-F2-bypass crypto activation since 2026-05-02 20:04 (BTC Follower 4H ETH LONG)
- ✅ Weekly Trend Follow ETH honestly rejected: 0.8% gross over 10 trades = genuinely no edge
- ✅ Non-crypto (Sector Rotation XLF) unchanged on the Sharpe gate
- ✅ Negative-Sharpe strategies still correctly rejected
- ✅ errors.log clean since deploy (last error at 11:45 was pre-existing forex-weekend yfinance)

**What this means strategically:**

The Phase 6 verdict from the original investigation was wrong. The correct ranking:
1. **(b) STRUCTURAL BUG — dominant driver** (now fixed)
2. **(a) HONEST OUTPUT — meaningful secondary** — even after fix, Weekly Trend Follow and other genuinely-thin strategies correctly fail
3. **(c) LIBRARY DESIGN — minor** — some templates are still structurally uneconomic on alts at 2.96% round-trip (1h mean-reversion templates firing 180×/year at 1% commission can't work)
4. **(d) REGIME MISMATCH — minor**

Expected activation rate going forward: 1-3 additional crypto activations per cycle where the rejected strategy has strong per-position edge but was being mis-rejected on the unit-mismatched RPT. Templates with genuinely thin edge still correctly reject.

---

## Session shipped 2026-05-02 late evening (Sprint 3 S3.0d — DSL grammar + template design rewrites + library audit)

After S3.0c proved the MC filter was being silently bypassed, user pushed back: "what are we doing wrong, what are we missing, it can't be the market." The bucket-level funnel tells the real story — ~130 strategies evaluated per cycle, of which ~41 WF OVERFITTED + ~47 WF LOW_SHARPE + ~18 WF 0-TRADE + ~13 LOW_TRADES + ~6 LOW_WINRATE = ~125 rejected, leaving 4-7 reaching activation. The library has structural quality issues that no gate tuning can fix.

### S3.0d-1 — DSL grammar bug: `arith_expr CROSSOVER arith_expr` not supported

The DSL grammar allowed `indicator CROSSOVER indicator` and `indicator CROSSOVER NUMBER` but not `indicator CROSSOVER (indicator * number)`. This blocked legitimate event-style entries like `CLOSE CROSSES_BELOW SMA(50) * 0.75` (crossing into deep-dip zone) and `VOLUME CROSSES_ABOVE VOLUME_MA(20) * 2.0` (volume spike event).

**Fix (`src/strategy/trading_dsl.py`):**
- Grammar: `arith_expr CROSSOVER arith_expr -> crossover` (merges the scalar and Series cases into one rule, avoiding LALR reduce/reduce conflict)
- `_handle_crossover_number` removed — redundant with the unified rule
- `_handle_crossover` now wraps both sides in `pd.Series(..., index=data.index)` before `.shift(1)`, so `(indicators['X'] * 2.0).shift(1)` parses correctly; RHS scalars (bare numbers) stay unwrapped so `.shift()` isn't applied to a float (which would raise AttributeError)

Verified via parse+codegen smoke test: 15 expressions including `VOLUME CROSSES_ABOVE VOLUME_MA(20) * 2.0`, `CLOSE CROSSES_BELOW SMA(50) * 0.75`, `RSI(14) CROSSES_ABOVE 30`, `SMA(50) CROSSES_BELOW SMA(200)` — all pass. Existing scalar-crossover codegen byte-identical to pre-change (regression safe).

### S3.0d-2 — PRICE_CHANGE_PCT(N) auto-detection period bug

User report via errors.log: `Crypto 20D MA Variable Cross Daily` (Sprint 2 template) failed with `Missing indicators: PRICE_CHANGE_PCT_5`. Template declared `required_indicators=["SMA", "Price Change %"]` (no period); DSL used `PRICE_CHANGE_PCT(5) > 0.03`. Auto-detection code at `strategy_engine.py:3618` had a guard `not any(i == spec or i == "Price Change %" for i in indicator_list)` that blocked adding period-specific `"Price Change %:5"` whenever the bare-name `"Price Change %"` was already in the list. Only `PRICE_CHANGE_PCT_1` was computed; DSL eval failed with the missing key.

**Fix (`src/strategy/strategy_engine.py`):**
- Auto-detect block: removed the bare-name short-circuit. Each period-specific reference in DSL conditions now registers its own `"Price Change %:N"` spec, independent of whether the generic `"Price Change %"` is declared.
- Indicator-dispatch block: added explicit `expected_keys = [f"PRICE_CHANGE_PCL_{period}"]` branch for `Price Change %` (previously the generic branch only handled `RSI/SMA/EMA/ATR/Volume MA/ADX`).

### S3.0d-3 — 8 crypto template design rewrites: state-condition → event-condition entries

Root cause of the persistent OVERFITTED / LOW_WINRATE buckets: several templates had entry conditions that were **states** (e.g. `CLOSE > SMA(50)`) where the design intent was an **event** (e.g. "buy when price first crosses above"). In uptrends, state-entries fire every bar the condition holds, producing many trades with low win rate and high noise. The template's own description ("buy when price crosses above SMA(50)") was correct but the DSL didn't match.

Concrete example: `Crypto Weekly Trend Follow BTC` test window produced 28 trades with WR 21%, vs design's "1-2 trades/year with 50%+ WR". The whipsaw pattern — enters on every dip+bounce pair — matches the state-condition leak exactly.

**Rewrites (`src/strategy/strategy_templates.py`):**

| Template | Old (state) | New (event) |
|---|---|---|
| Crypto Weekly Trend Follow | `CLOSE > SMA(50) AND ADX > 20 AND RSI > 45 AND RSI < 70` | `CLOSE CROSSES_ABOVE SMA(50) AND ADX > 20 AND RSI > 45 AND RSI < 70` |
| Crypto Deep Dip Accumulation | `CLOSE < SMA(50)*0.75 AND RSI < 30` | `CLOSE CROSSES_BELOW SMA(50)*0.75 AND RSI < 30` |
| Crypto Golden Cross (exit) | `CLOSE < SMA(200)` | `SMA(50) CROSSES_BELOW SMA(200)` (true death cross) |
| Crypto Volume Spike Entry | `VOLUME > VOLUME_MA(20)*2.0 AND CLOSE > SMA(20)` | `VOLUME CROSSES_ABOVE VOLUME_MA(20)*2.0 AND CLOSE > SMA(20)` |
| Crypto EMA Ribbon | `EMA(8) > EMA(13) AND EMA(13) > EMA(21) AND RSI > 40` (3 lines) | `EMA(8) CROSSES_ABOVE EMA(13) AND EMA(13) > EMA(21) AND RSI > 40` (1 line; event is the cross) |
| Crypto Hourly BB Expansion Ride | `CLOSE > BB_MIDDLE AND bandwidth > 3*ATR AND RSI > 50` | `CLOSE CROSSES_ABOVE BB_MIDDLE AND bandwidth > 3*ATR AND RSI > 50` |
| Crypto 21W MA Trend Follow | `CLOSE > EMA(147) AND CLOSE[-1] <= EMA(147)[-1]` (DSL parse error — `[-N]` not in grammar) | `CLOSE CROSSES_ABOVE EMA(147)` (native primitive; same semantics) |
| Crypto Vol-Compression Momentum | `(CLOSE / CLOSE[-20] - 1) > 0.03 AND ATR(20) < ATR(90)` (parse error) | `PRICE_CHANGE_PCT(20) > 3.0 AND ATR(20) < ATR(90)` |

The last two templates were producing zero trades every cycle due to DSL parse errors on `CLOSE[-N]` syntax (which the grammar doesn't support). Rewriting with native primitives (`CROSSES_ABOVE`, `PRICE_CHANGE_PCT(N)`) restores them to a functional state.

### S3.0d-4 — `scripts/clear_crypto_wf_cache.py` format-mismatch bug

The clear-cache script referenced `entry["key"][1]` to detect crypto symbols, but the actual JSON format (post-some-earlier-refactor) stores `template` and `symbol` as top-level fields, not a `key` array. The script ran "successfully" every time but removed 0 entries, silently. Fixed to read `entry.get("symbol")` with a legacy-fallback for any old entries that still carry a `key` tuple.

Verified: on the post-S3.0d run, the fixed script removed 25 validated + 107 failed crypto entries (132 total) from the caches. Confirming the script had been a no-op for at least the past several WF-related sessions.

### Cycle verification after S3.0d

Service restarted ~18:30 UTC and healthy. First post-S3.0d cycle to arrive on the 19:00 UTC schedule. Expected visible changes:
- `Crypto 20D MA Variable Cross Daily` should no longer appear in `[WF 0-TRADE]` bucket (ETH/DOT/SOL) — should generate signals on the 20-SMA crossover.
- `Crypto 21W MA Trend Follow` and `Crypto Vol-Compression Momentum` should stop throwing DSL parse errors in errors.log.
- `Crypto Weekly Trend Follow`, `Crypto Deep Dip Accumulation`, `Crypto EMA Ribbon`, `Crypto Volume Spike Entry`, `Crypto Hourly BB Expansion Ride` should all show **materially lower trade counts** and **different Sharpe/WR numbers** (since the cache was cleared, fresh WF runs on each).
- Some previously "overfitted" templates may now pass WF honestly (because they're no longer running on noise trades from state-condition leaks).

Whether activation count rises is an empirical question — structural fix, not permissiveness change.

### Library audit vs hedge-fund research (deferred to Sprint 4)

Reviewed 52 crypto templates against 2024-2025 hedge-fund practice (arxiv 2602.11708 AdaptiveTrend Sharpe 2.41; Habeli et al. 2025 on vol-scaling; cryptofundresearch.com showing quant crypto funds at Sharpe 2.51 / BTC-beta 0.27; navnoorbawa/blofin on basis + funding strategies). Findings:

- **Over-represented:** mean_reversion (22 of 52 templates; 5-6 near-duplicates on 1h/4h). Research supports 1-2 per timeframe.
- **Under-represented / missing:** on-chain signals (MVRV, NUPL, exchange netflow, stablecoin netflow), derivatives-proxied signals (funding-rate proxy, basis proxy), BTC dominance regime rotation, vol-scaled momentum composite, seasonality/hour-of-day.
- **Structurally unreachable:** basis/funding-rate arbitrage (requires perps — eToro is spot-only).

Full breakdown with prune/add list lives in the Sprint 4 prompt below; nothing shipped this session on the audit — it's a design doc that needs its own sprint.

---

Following the post-S3.0b user prompt to investigate the crypto backtest → WF → activation pipeline for formula/approach bugs before any further gate changes. Phase 1 investigation traced Crypto Weekly Trend Follow × BTC end-to-end (train_sharpe=1.94, test_sharpe=0.38, 28 test trades, WR 21%, expectancy +$73.64/trade, net return −4.2%).

**Arithmetic is correct:** Sharpe formula, cost application, net_return conversion, WR/expectancy internal consistency all check out. 28 trades × $73.64 expectancy ≈ 2% gross; 28 round-trips × 2.96% × avg $10k position ≈ 8% cost → net ≈ −6%, matching logs within rounding/overnight-rate noise.

**Two architectural bugs found and fixed.**

### S3.0c Bug 1 — Pass 2 relaxed bypassed the MC bootstrap filter

`strategy_proposer.py` line 2430 (the "if fewer than 10 passed strict, add relaxed" branch) only checked `id not in strict_ids`, not `id in mc_passed_ids`. Strategies that the MC filter rejected as "edge likely noise" were re-added on every crypto-heavy cycle (≤10 crypto strategies usually pass strict), then reached activation before being caught on unrelated per-pair gates. The MC filter — the one that's specifically designed to catch regime-luck and heavy-tail noise — was silently unrun in exactly the cases it was built for.

**Fix:** Pass 2 now requires `s.id in mc_passed_ids`. Blocked count is logged each cycle so the filter's effect is visible.

**Cycle evidence (cycle_1777743964, first post-deploy):**
```
17:49:17  MC bootstrap FAIL: Crypto Weekly Trend Follow BTC LONG — p10=-1.10 < -0.2 (n=28)
17:49:18  Walk-forward validation (relaxed): blocked 3 candidates already rejected by MC bootstrap
```
Compared to pre-fix cycle_1777742566 which showed `added 3 more strategies (total: 7)` for the same 3 Weekly Trend Follow strategies. The swap is the fix.

### S3.0c Bug 2 — MC annualization used hardcoded 180d test window

Long-horizon crypto 1d templates (Weekly Trend Follow, Golden Cross, 21W MA, Vol-Compression) run WF with `test_days=730` per the P1-extra extension. But the MC bootstrap block hardcoded `test_window_days=180`, inflating the annualization factor by sqrt(730/180) ≈ 2.01x. This skewed bootstrap p-value tails by the same factor — not enough to flip pass/fail on these specific strategies (their MC would have failed either way), but definitionally wrong and a risk for templates near the boundary.

**Fix:** Read the window off `test_results.backtest_period`. Falls back to 180d if period missing or span <30d.

**Evidence:** Weekly Trend Follow p10 values post-deploy match predicted sqrt(180/730) scale-down:
```
Strategy                      pre-deploy p10   post-deploy p10   ratio
Crypto Weekly Trend Follow BTC    -2.42             -1.10          2.2x
Crypto Weekly Trend Follow ETH    -1.75             -0.93          1.9x
Crypto Weekly Trend Follow LINK   -1.20             -0.58          2.1x
```
Theoretical ratio is 2.01x; bootstrap noise accounts for the spread. All three still fail the -0.2 floor — these strategies genuinely don't have MC-supported edge in this window. The fix makes the rejection numbers honest.

### Net effect

**Zero change in activation count.** Cycle funnels before/after:
```
                     pre-S3.0c (1777742566)   post-S3.0c (1777743964)
Proposals                9                         6
WF validated             8  (88.9%)                5  (83.3%)
Activated                0                         0
Weekly Trend Follow BTC  reaches activation,       caught at WF stage
                         fails WR 21% < 25%        (LOW WINRATE bucket)
```
S3.0c is a correctness fix, not a permissiveness fix. The strategies it blocks were going to fail activation anyway; catching them at WF stage is just cleaner observability and proves the MC filter is actually filtering.

**Non-crypto regression check:** Sector Rotation XLF evaluated through normal path, correctly rejected on Sharpe -0.04. F2 cross-validation path (Cross-Sectional Momentum SOL/LINK on n<20 consistency bypass) still working. No new errors in errors.log from the proposer.

### What this confirms about crypto activations

The math is right. The pipeline is correctly rejecting strategies that lost money in their test window. The 4 already-active crypto strategies (BTC Follower Daily ETH/SOL/LINK/AVAX, armed) plus the 0 new activations is **honest output**, not a hidden filter bypass. When BTC's regime shifts (next +5% 2-bar move, or the templates find trend continuation), the pipeline will propagate activations through honest numbers.

**What should NOT happen next:**
- More gate loosens. The gates are doing their job.
- Another round of "why didn't X activate" investigations on individual strategies. The answer for each one will be the same: no edge in current window.

**What SHOULD happen next:**
Phase 1 verification continued (from pre-investigation plan): wait for BTC to fire the +5% trigger OR let a regime shift move crypto trend templates past the net-return floor. Alternately Phase 2 work on S3.1-S3.5 (WF bypass-path tightening for LONG, Triple EMA DSL bug, MQS persistence, cross-cycle signal dedup, trade_id unification).

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

## Session shipped 2026-05-02 late afternoon (Sprint 3 partial — S3.0 + S3.0b)

### S3.0 — Asset-class-aware MC bootstrap calibration (commit `6e5530f`)

**Diagnosis:** Post Sprint 2, cycles produced near-zero crypto activations. Funnel analysis over 5 cycles (15:00-17:00 UTC): 665 proposed → 603 wf_rejected (91%) → 40 wf_validated (6%) → 6 activated (0.9%). Of the 603 rejections, 207 were Monte Carlo bootstrap filtered (34%). 166 of 207 MC rejections (80%) were crypto.

Sampled crypto MC rejections showed a mix:
- Genuine regime-luck (correctly rejected): `Volume Spike Entry × SOL` train Sharpe -1.71, test 3.26.
- **Genuine edge lost**: `Weekly Trend Follow × BTC` (train 1.94, test 0.38), `Weekly Trend Follow × LINK` (train 0.23, test 0.39). Consistent positive train+test, small N, killed by equity-calibrated `p5 ≥ 0.0`.

**Root cause:** Equity-calibrated MC bootstrap is structurally wrong for heavy-tail asset classes. Crypto/commodity return distributions are power-law (Grobys 2024, Habeli et al. 2025). Bootstrap `p5` under heavy tails needs ~25+ samples for stable estimation (Efron & Tibshirani 1993). Applying equity's `p5 ≥ 0.0` to crypto with n=15-20 rejects real edge whose lower tail is structurally wider.

**Fix (strategy_proposer.py MC block):**
- Equity (default, unchanged): `p5 ≥ 0.0`, min 15 trades, unconditional pass-through for n<15.
- Crypto / commodity (heavy-tail): `p10 ≥ -0.2`, min 20 trades. Habeli 2025 documents `p20 of -0.3` as the proper cutoff for vol-scaled crypto momentum at Sharpe 0.8-1.2; we stay modestly stricter with `p10 ≥ -0.2`.
- Heavy-tail pass-through (n<20) gated by consistency check: require train AND test Sharpe both > 0.2, OR one side ≥ 1.0 with other ≥ -0.1. Closes the regime-luck loophole in the bypass branch for heavy-tail asset classes specifically (equity pass-through unchanged so as not to tighten equity behavior).

Detection of heavy-tail uses `DEMO_ALLOWED_CRYPTO | DEMO_ALLOWED_COMMODITIES` from tradeable_instruments. Code is fail-open on detection error (passes through equity calibration).

### S3.0b — DEMO loosen crypto gates for live signal data collection (commit `25c9051`)

Post-S3.0 cycle still showed 0 crypto activations. Analysis of `cycle_1777741379` funnel:
- 134 pre-WF → 4 wf_validated → 0 activated
- 4 wf_validated breakdown: 2 rejected on `Sharpe < 0.5` (Cross-Sectional LINK 0.46, Weekly Trend LINK 0.39), 2 rejected on net return < 0 (SMA Reversion SOL, 1H RSI Extreme Bounce DOT), 1 on RPT < 3.5% (Cross-Sectional SOL gross 2.8% / 3 trades = 0.94%/trade).

Of those 4 rejects, 2 strategies (the Sharpe rejects) showed genuine but thin edge — they'd lose money live but would generate valid signal data on DEMO. Since we're on eToro paper-trading and the goal this week is proving Sprint 1+2 end-to-end with live signal data, an explicit DEMO-only loosen is warranted. Documented in yaml header with exact revert values for live deployment.

**Changes (`config/autonomous_trading.yaml` activation_thresholds):**
- `min_sharpe_crypto`: 0.5 → **0.3** — accepts Sharpe 0.3-0.5 crypto (revert to 0.5 for live)
- `min_return_per_trade.crypto_1d/4h/1h`: 0.035 → **0.030** — 40bps edge over 2.96% round-trip cost vs 54bps before (revert to 0.035 for live)

**What stays enforced:** net_return > 0 after costs (per-symbol tradability floor), drawdown, win_rate/expectancy, R:R ratio. Strategies that genuinely lost money in test still correctly rejected.

**This is explicitly marked as a DEMO-only learning calibration, NOT a proper cost-model fix.** Per steering rule, the revert path is documented inline in the yaml; there is no ambiguity about what "fixing this for live" means.

### Post-S3.0b verification — S3.0b fired correctly but deeper blockers surface

`cycle_1777742566` at 17:22 UTC — 134 pre-WF, 4 wf_validated, **0 activated**. Same 0-activation outcome, but the visible rejection reasons changed — which is the diagnostic we needed:

| Strategy | Pre-S3.0b reject | Post-S3.0b reject |
| --- | --- | --- |
| Cross-Sectional Momentum SOL | Return/trade 0.945% < **3.500%** | Return/trade 0.945% < **3.000%** (new floor visible) |
| Cross-Sectional Momentum LINK | Sharpe 0.46 < **0.5** | **Net return -1.1%** (Sharpe now passes; net-return is the true blocker) |
| Weekly Trend Follow LINK | Sharpe 0.39 < **0.5** | **Net return -4.2%** on 28 trades |
| Weekly Trend Follow BTC | Sharpe 0.38 < **0.5** | **WinRate 21% < 25% hard floor** (expectancy $73.64 positive) |
| Weekly Trend Follow ETH | Sharpe 0.23 < **0.5** | Sharpe 0.23 < **0.3** (still below new floor) |

S3.0b unlocked 3 of 5 Sharpe gates — and all three strategies that passed Sharpe then revealed their **actual problem: negative net return in test window** (Cross-Sectional LINK -1.1%, Weekly Trend LINK -4.2%) or **win rate below the 25% hard floor** (Weekly Trend BTC at 21%).

**Conclusion:** There is no further "gate loosen" that unlocks real crypto activation in this market regime. The system is correctly filtering out strategies that lost money in their test window. The crypto edge the templates are designed to capture (BTC lead-lag, cross-sectional momentum, trend-follow) simply isn't present in the current 90-730d test windows because BTC is ranging_low_vol and has been sideways since mid-March. When the regime shifts, these same strategies will show positive net return and activate.

**What's NOT productive to change:**
- Net-return-after-costs floor — strategies losing money must reject. Bypass = paper-losing DEMO trades teaching the conviction scorer bad priors.
- 25% WR hard floor — below 25% win rate, even a positive-expectancy strategy is unreliable to trade.
- Round-trip cost model — eToro charges are what they are.

**What SHOULD happen in the next investigation:**
1. Examine **why specific templates produce negative net return** in current window — is it template design (e.g. Weekly Trend Follow BTC enters 28 times but only wins 21% — maybe entry threshold needs regime calibration)? Or is it regime-wrong (template expects trend, regime is range)?
2. Check whether **the 5 new Sprint 2 crypto templates** (Donchian, Keltner 4H, OBV, 20D MA, BB Volume) are WF'ing at all — if they consistently fail WF in ranging-low-vol, consider adding a **regime-gated proposer** that only proposes trend templates when BTC's ADX > 20.
3. **Time-based bypass**: the 4 already-activated strategies (BTC Follower Daily ETH/SOL/LINK/AVAX) are armed for BTC's next +5% 2-bar move. That IS live signal data capability — it's just waiting on market action.

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

### Next sprint (Sprint 3 continuation) — Verification + WF tightening + quality fixes

**Rule in effect:** Proper solutions only. See `.kiro/steering/trading-system-context.md` → "Proper Solutions Only — No Patches, No Stopgaps". Exception: S3.0b (crypto DEMO loosen) is explicitly marked as a reversible learning calibration with revert-for-live path documented — not a stopgap masquerading as a fix.

**Context after Sprint 2 + S3.0 + S3.0b:** Cross-asset DSL primitives (Sprint 1), cost floors (Sprint 1), cross-symbol consistency validation (Sprint 2 F2), primary-only dedup (Sprint 2 F2.1), 4h cache honesty (Sprint 2 F10), 5 new crypto templates, 3 new DSL indicators, asset-class-aware MC bootstrap (S3.0), DEMO crypto gate loosen (S3.0b). 4 crypto strategies active (BTC Follower Daily ETH/SOL/LINK/AVAX), armed waiting on BTC +5% 2-bar trigger.

**Remaining Sprint 3 work is split into two phases:**

#### Phase 1 — Verify Sprint 1 + Sprint 2 + S3.0 + S3.0b in live cycles (~30-60 min)

Before any further code, prove the full signal→order path works on crypto with the loosened DEMO gates:

1. **New activations via S3.0b**: run crypto-focused cycle, expect 1-3 new activations on Sharpe 0.3-0.5 crypto strategies that were previously blocked. Check `signal_decisions` funnel; confirm `rejected_act` counts drop for Sharpe 0.3-0.5 cases.
2. **Signal emission → order → fill**: any newly-activated or already-armed strategy should produce `signal_emitted` → `order_submitted` → `order_filled` (crypto is 24/7 so no market-closed deferral). Verify in DB: `SELECT symbol, template_name, entry_time, entry_price, pnl FROM trade_journal WHERE symbol IN ('BTC','ETH','SOL','AVAX','LINK','DOT') ORDER BY entry_time DESC LIMIT 20`. Populate MAE/MFE within 60s of fill.
3. **5 new Sprint 2 crypto templates in flight**: Donchian Breakout, Keltner Breakout 4H, OBV Accumulation, 20D MA Variable Cross, BB Volume Breakout — each should appear in `signal_decisions` as `proposed` at minimum. OBV Accumulation already passed WF via excellent_oos on ETH in cycle_1777739783.
4. **Live-vs-backtest divergence tracking**: once ≥5 closed crypto trades, query `/analytics/observability/wf-live-divergence` and confirm divergence is measurable.
5. **Non-crypto regression check**: equity/ETF/forex/commodity/AE paths unchanged. 15:15 UTC scheduled cycle should produce ~100-200 pre-WF proposals across all asset classes.

Don't proceed to Phase 2 until at least one complete crypto signal→order→fill path has fired, OR the user explicitly says the market regime is too quiet and to move on.

#### Phase 2 — Remaining Sprint 3 code (S3.1-S3.5, ordered by P&L impact)

**S3.1 — WF bypass path tightening for LONG** (~2h) — **priority P0**
- `strategy_proposer.py` test_dominant + excellent_oos paths: `ts >= -0.1 AND tes >= min_sharpe` or `ts >= -0.3 AND tes >= min_sharpe*2`. A strategy with train -0.1 and test 0.5 passes = regime luck, not edge.
- SHORT was tightened in Sprint 1 (SHORT relaxed-OOS path removed; primary needs +0.3 min_sharpe). LONG still loose.
- **Fix:** Add consistency gate `(test_sharpe - train_sharpe) ≤ 1.5` on test_dominant + excellent_oos paths for LONG. Mirror SHORT rigor.
- **Verification:** before/after wf_validated count diff; `/analytics/observability/wf-live-divergence` drop 2+ weeks post-deploy.

**S3.2 — DSL wiring bugs in templates** (~30 min remaining) — **priority P1**
- **PARTIALLY DONE** in S3.0d (2026-05-02 late evening):
  - ✅ `Crypto 20D MA Variable Cross Daily` PRICE_CHANGE_PCT(5) auto-detect bug — fixed at `strategy_engine.py:3611-3637` (bare-name spec no longer short-circuits period-specific additions; `Price Change %` mapping now produces period-specific expected_keys).
  - ✅ `Crypto 21W MA Trend Follow` and `Crypto Vol-Compression Momentum` CLOSE[-N] parse errors — resolved by rewriting to native `CROSSES_ABOVE` / `PRICE_CHANGE_PCT(N)` primitives.
- **STILL OPEN:** `Triple EMA Alignment` produces `EMA(10) > EMA(10)` tautology from regex param substitution collapse in `strategy_proposer.customize_template_parameters`. Correct output should be `EMA(10) > EMA(20) AND EMA(20) > EMA(50)`.
- **Fix:** audit the regex in `customize_template_parameters`; add explicit positional-EMA-period tuple handling for the Triple EMA Alignment template (single-symbol DSL pattern where 3 distinct periods are substituted into `EMA(period_1) > EMA(period_2) AND EMA(period_2) > EMA(period_3)`).
- **Verification:** template produces >0 WF trades on at least one symbol post-fix.

**S3.3 — Market Quality Score persistence** (~45 min) — **priority P1**
- Recent `equity_snapshots.market_quality_score` rows are NULL. `_save_hourly_equity_snapshot` swallows MQS compute error in bare `except: pass`.
- **Fix:** replace bare except with specific exception handler + WARNING log capturing error signature.
- **Verification:** `SELECT COUNT(*) FROM equity_snapshots WHERE market_quality_score IS NOT NULL AND date > NOW() - INTERVAL '1 day'` returns >0 next hour.

**S3.4 — Cross-cycle signal dedup for market-closed deferrals** (~90 min) — **priority P1**
- Entry-order 82% FAILED rate cosmetic: 9 cycles × 11 signals = 99 DB rows for 11 intended signals.
- **Fix:** trading_scheduler 30-min TTL map `{(strategy_id, symbol, direction): expires_at}`. Market-closed deferral writes; next cycle skips duplicates.
- **Verification:** overnight cycle produces 0 FAILED-entry duplicates for same (strategy, symbol, direction) inside 30 min.

**S3.5 — trade_id convention unification** (~90 min) — **priority P2**
- `log_entry` uses `position.id`; `log_exit` uses order UUID. Mismatch → orphan rows in `trade_journal`.
- **Fix:** migrate `order_monitor.check_submitted_orders` to use `position.id` for `log_exit`. Retire fallback match.
- **Verification:** after 1 week, orphan count stays at zero.

**Do not ship Sprint 3 until:**
- Phase 1 verification complete (crypto signal→order→fill path proven on at least one fill, OR market regime confirmed too quiet by user).
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

### Next-session kickoff prompt (Sprint 4 — Binance data + on-chain + library rebuild)

Copy this as-is into a new session:

```
Start this session by reading, in this exact order: (1) .kiro/steering/trading-system-context.md — pay special attention to "Think Like a Trader, Not a Software Engineer" and "Proper Solutions Only — No Patches, No Stopgaps". (2) Session_Continuation.md — focus on the "Session shipped 2026-05-02 late evening (Sprint 3 S3.0d …)" block which documents the DSL design-bug rewrites + library audit findings. (3) AUDIT_REPORT_2026-05-02.md. Do not summarize them back — confirm you've read them and begin.

Context: Sprints 1/2/3 shipped. The stack is now architecturally correct end-to-end. Sprint 3 S3.0d fixed the last remaining DSL design bugs (8 crypto templates rewritten from state-condition entries to event-condition entries; DSL grammar extended so `CROSSES_ABOVE` accepts arith_expr on both sides; the broken `scripts/clear_crypto_wf_cache.py` JSON-format bug). The crypto WF cache was fully cleared (132 entries) at S3.0d deploy so every crypto template gets evaluated against the corrected DSL on the next cycle.

But the library-level audit surfaced three structural gaps that no amount of DSL or gate-tuning will close. Real crypto hedge funds (arxiv 2602.11708 AdaptiveTrend Sharpe 2.41; Habeli et al. 2025; navnoorbawa on basis trading; cryptofundresearch.com showing quant-crypto funds at Sharpe 2.51/BTC-beta 0.27) rely on three data sources we don't have:
  1. Historical 1h/4h crypto OHLCV beyond Yahoo's 7-month cap (Binance public API fills this)
  2. On-chain metrics (MVRV Z, NUPL, exchange netflow, stablecoin flow) — completely missing from our stack
  3. Derivatives-proxied signals (funding rate regime, basis spread) — usable as spot-entry gates even though we can't trade perps on eToro

Sprint 4 fixes these and rebuilds the crypto library on top. The mission is correctness and coverage, not throughput-chasing.

---

PHASE 1 — Verify S3.0d didn't regress anything (~30 min)

Before any new code, confirm S3.0d is healthy in a full cycle:
  (1) Run the 19:00 UTC scheduled cycle (or trigger manually).
  (2) Check errors.log: the `CLOSE[-20]` and `CLOSE[-1] <= EMA(147)[-1]` parse errors should be gone. The `PRICE_CHANGE_PCT_5 missing` error should be gone.
  (3) Check the cycle's `[WF 0-TRADE]` bucket: `Crypto 20D MA Variable Cross Daily`, `Crypto 21W MA Trend Follow`, `Crypto Vol-Compression Momentum` should no longer appear there.
  (4) Check trade counts on the rewritten state→event templates: `Crypto Weekly Trend Follow` should show <10 test trades (was 28), same for Deep Dip, Volume Spike, EMA Ribbon, Hourly BB Expansion, Golden Cross (exit). If any are still high, the fix didn't bind — investigate before proceeding.
  (5) Net activation count may rise, fall, or stay at 0 — any outcome is acceptable as long as the WF bucket distribution is healthier.

Only proceed to Phase 2 after Phase 1 confirms the DSL rewrites took effect.

---

PHASE 2 — S4.0: Binance public API adapter for 1h/4h crypto historical data (~3-4h, P0)

Yahoo caps crypto 1h data at ~7 months. Our 4h cache is resampled from 1h, so it inherits the same cap. This means 4h crypto WF windows of 180/180 are effectively running on 0-60 days of training data depending on cache drift. Binance public `/api/v3/klines` endpoint serves 1h and 4h candles back to 2017 for BTCUSDT, ETHUSDT, SOLUSDT, AVAXUSDT, LINKUSDT, DOTUSDT — no authentication, reasonable rate limits for our scale.

Work:
  (1) Create `src/api/binance_ohlc.py` — pure-function fetcher: `fetch_klines(symbol_display: str, start: datetime, end: datetime, interval: str) -> List[PriceBar]`. Symbol mapping: `BTC` → `BTCUSDT`, etc. Handle Binance's 1000-candle-per-request limit with pagination. Interval mapping: our `"1h"` → Binance `"1h"`, our `"4h"` → Binance `"4h"`, our `"1d"` → Binance `"1d"` (optional; Yahoo 1d is already unlimited so 1d not a priority).
  (2) Wire into `src/core/market_data_manager._fetch_historical_from_yahoo_finance` — for `asset_class == 'crypto' and interval in ('1h', '4h')`, try Binance first; fall back to Yahoo on failure. Log the source used. Preserve timestamp/timezone conventions (tz-aware UTC input, naive UTC output per the existing pipeline rules).
  (3) Update `scripts/reconcile_crypto_4h_cache.py` to tolerate the new depth: 4h cache can now legitimately go back 2+ years. Write a follow-up `scripts/backfill_crypto_4h_from_binance.py` that one-shot backfills the DB cache for all 6 crypto symbols from Binance (1 year of 4h = ~2200 bars per symbol; very fast).
  (4) Increase crypto 4h WF window from 180/180 to 365/365 (or 540/540 — evaluate cached bar count and pick the largest window that fits in 90% of 6 symbols' caches post-backfill). Extend crypto 1h WF window from 90/90 to 180/180 or 365/180.
  (5) Clear crypto WF cache on deploy (the now-functional `scripts/clear_crypto_wf_cache.py`) so next cycle re-evaluates every crypto template against the richer windows.

Verification: log lines show "Binance 4h: fetched N bars for BTC (range …)" across all 6 symbols. `historical_price_cache` shows 4h first-bar date ≥2-3 years old post-backfill. A cycle run after deploy shows Weekly Trend Follow / Golden Cross / 21W MA running on materially longer train windows with trade counts matching their design intent (1-3/year on the 730d+ windows).

---

PHASE 3 — S4.1: On-chain metrics data source (~6-10h, P0 — biggest alpha unlock)

Missing alpha source #1 per the Sprint 3 audit. Quant crypto funds use MVRV Z-score, NUPL, exchange netflow, stablecoin netflow as core signals. Free sources: CoinGecko (market cap, dominance), Glassnode free tier (limited MVRV/NUPL), CryptoQuant free tier, DeFi Llama (stablecoin supply). For BTC specifically Alternative.me fear&greed is free and daily.

Start with the two highest-leverage signals that have the cleanest free-tier access:
  A. **BTC Dominance** — `BTC_market_cap / total_crypto_market_cap`. Free via CoinGecko `/api/v3/global`. Signal used in the altcoin rotation regime (2026 market structure per ainvest — BTC.D >60% = BTC-favored, <55% = alt-favored).
  B. **Stablecoin Supply Momentum** — total USDT+USDC market cap 7d delta. Free via DeFi Llama `/stablecoins/stablecoinchains`. Signal: rising supply + BTC uptrend = risk-on expansion; falling supply = defensive.

Work:
  (1) `src/api/onchain_client.py` — adapter with two methods: `get_btc_dominance(end: datetime, days: int) -> pd.Series` and `get_stablecoin_supply(end: datetime, days: int) -> pd.Series`. Daily granularity is sufficient. 24h TTL in-memory cache; fail-open with WARNING log if source unavailable.
  (2) New DSL primitive: `ONCHAIN("metric_name", lookback_days)`. Registration pattern mirrors Sprint 1 F1 cross-asset primitives (regex extraction in condition strings; series merged into indicators dict before DSL eval). Valid metric names start as {`"btc_dominance"`, `"stablecoin_supply_pct"`}. Return is a series aligned to the primary symbol's index, ffilled.
  (3) Smoke test via `scripts/test_onchain_primitives.py` — confirms parse + fetch + codegen work. DO NOT add templates until the primitive is proven on a small standalone test.
  (4) After smoke-test passes, add one template — `Crypto Weekly Dominance Rotation` — as the first real-world use:
      entry: `ONCHAIN("btc_dominance", 7) < 0.55 AND ADX(14) > 20` (rotate to alts when dominance falls below 55% in uptrend)
      exit: `ONCHAIN("btc_dominance", 7) > 0.60` (rotate back to BTC when dominance recovers)
      1d interval; family_universe = ETH/SOL/AVAX/LINK (not BTC — this template specifically trades alts).

Defer MVRV/NUPL/exchange-netflow to S4.2 (requires Glassnode/CryptoQuant tier evaluation — may need a paid tier; don't spend credits this sprint).

---

PHASE 4 — S4.2: Remove the 6 redundant crypto templates (~30 min, P0)

Pure library quality cleanup. These 6 are near-duplicates of other templates and consume proposer slots each cycle without adding orthogonal alpha:
  - `Crypto Hourly ATR Snap`
  - `Crypto Hourly Capitulation ATR Snap`
  - `Crypto Hourly Capitulation RSI`
  - `Crypto Hourly Capitulation BB Crush`
  - `4H Crypto Downtrend Bounce`
  - `4H Crypto Downtrend ATR Snap`

Check the `signal_decisions` table for the past 30 days before deleting — confirm none of these have ever produced a `signal_emitted` that resulted in a profitable `order_filled`. If any have >3 profitable fills, keep and remove a different near-duplicate.

---

PHASE 5 — S4.3: Add 3 research-backed templates (~2-3h, P1)

After S4.0 (Binance data) and S4.1 (BTC dominance primitive) land, add:
  (1) **`Crypto BTC Vol-Scaled Momentum Composite`** (1d) — three-window TSMOM: long when `PRICE_CHANGE_PCT(20) > 0 AND PRICE_CHANGE_PCT(60) > 0 AND PRICE_CHANGE_PCT(120) > 0`. Research: AdaptiveTrend Sharpe 2.41. Requires no new primitives beyond PRICE_CHANGE_PCT(N) which already works post-S3.0d. Symbol-specific position sizing comes later (S4.4).
  (2) **`Crypto Pi Cycle Top/Bottom`** (1d, BTC only) — entry on `SMA(111) CROSSES_BELOW SMA(350) * 2` (historical cycle top marker). Single symbol, very low frequency (1-2 trades per 3-year cycle), high conviction. Research: documented since 2019, fired at every major BTC top.
  (3) **`Crypto Realized-Price Proxy`** (1d) — requires S4.1 on-chain data OR 200d VWAP fallback. Entry when `CLOSE / SMA(200) < 0.70` (deep discount to long-term trend) AND RSI(14) < 35. Conservative mean-reversion that only triggers at extreme drawdowns.

---

PHASE 6 — S4.4: Vol-scaled position sizing binding (~4-6h, P2)

Templates currently can't say "size me by vol-target" — position sizing is a 0.6% BASE_RISK × confidence formula applied uniformly. Research (Habeli et al. 2025, Barroso & Santa-Clara 2015) shows vol-scaling nearly doubles Sharpe on momentum strategies.

Work:
  (1) New template flag `metadata.vol_scale_target: 0.30` (30% annualized vol target — tune per asset class).
  (2) `risk_manager.calculate_position_size` reads the flag and replaces the confidence-scaling step with `position_size = (vol_scale_target / realized_vol) × base_risk`. Fallback to current behavior if flag absent.
  (3) Apply to `Crypto BTC Vol-Scaled Momentum Composite` first (from S4.3); verify backtest Sharpe improvement; extend to Cross-Sectional Momentum and BTC Follower templates if delta is positive.

---

PHASE 7 — S4.5: (optional, time permitting) Rolling-window WF for long-horizon crypto 1d templates (~1-2h, P2)

`rolling_window_validate` exists at `strategy_engine.py:1747` but isn't wired into the proposer for long-horizon templates. Single-split 730/730 WF on 4 years of crypto data captures one specific regime pair (2022 bear → 2024 bull); a strategy that happens to fit that transition gets passed while one that works across 3 of 4 regimes fails. Rolling windows give more honest overfit detection.

Work:
  (1) In `strategy_proposer.propose_strategies` WF dispatch, for the 4 long-horizon crypto 1d templates (Weekly Trend Follow, Golden Cross, 21W MA, Vol-Compression), call `strategy_engine.rolling_window_validate` with 4 overlapping 365d train / 180d test windows instead of single 730/730.
  (2) Pass criterion: ≥3 of 4 windows show positive test Sharpe AND aggregate test Sharpe ≥ 0.3.
  (3) This will likely reject more templates, not fewer — but the ones that pass will have real cross-regime edge.

---

WHAT NOT TO DO THIS SPRINT:
  - Don't loosen any activation gate. S3.0b remains the last acceptable relaxation.
  - Don't add templates in Phase 5 before Phase 2 and Phase 3 are landed — they depend on Binance data and the on-chain primitive.
  - Don't skip Phase 1 verification. The S3.0d DSL rewrites were a structural change to 8 templates; we need to confirm they didn't introduce new issues before layering more work on top.
  - Don't attempt MVRV/NUPL/exchange-netflow in S4.1 — defer to S4.2 after evaluating paid-tier options.

SUCCESS CRITERIA (end of sprint):
  - Binance data serves 2+ years of 4h crypto OHLCV for all 6 tradeable crypto symbols
  - `ONCHAIN("btc_dominance", …)` primitive parses, fetches live data, integrates into backtest
  - 6 redundant templates retired; 3 new research-backed templates shipped
  - Post-deploy cycle shows at least 1-2 new crypto activations OR the funnel buckets are materially healthier (OVERFITTED <20, 0-TRADE <5, fewer repeat offenders)
  - Zero regressions on non-crypto paths (equity/ETF/forex/commodity/AE cycles evaluated unchanged)
  - No new errors in errors.log from the new data sources (fail-open behavior verified)
```

### Previous — Sprint 3 kickoff (2026-05-02 evening, first version) — S3.0 through S3.0d SHIPPED, kept for context

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
