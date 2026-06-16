# AlphaCent — Session Continuation

> Permanent rules are in `.kiro/steering/trading-system-context.md`. This file holds current system state, recent fixes, and open items.

---

## ⚡ NEXT SESSION KICKOFF

**SESSIONS 2026-06-12 → 06-15 (Opus 4.8) — all deployed live + verified healthy + pushed. Latest commit `e8d68c7`.** Rollup of everything done across these sessions (detailed entries below):
1. **AE / crypto / SHORT generation-bias audit + fixes** — AE effective denominator 132→122; AE-calibrated conviction threshold (paper 55 / live 67); AE fundamental-data fetch decoupled from the reject gate (was always 0); SHORT WF tightening regime-scoped to `trending_up*` only; crypto confirmed regime-appropriate (BTC −22%/mo); `conviction_threshold_alpha_edge` exposed in Settings UI. Commits `92550c1`, `2b5c4c4`.
2. **P0 — `uq_open_pos` UniqueViolation** in `order_monitor.check_submitted_orders` (recurring, real-money duplicate risk): pair-level `_open_slot_taken()` guard on strategy_id reassigns + savepoint-isolated create. Commit `4701700`.
3. **Slippage measurement fix (A+B+C)** — `exit_slippage` was 100% NULL; `entry_slippage` contaminated by overnight drift (13–17h queued fills). New `compute_execution_slippage()` with 15-min drift guard; exit slippage now captured. Commit `a69cb6b`.
4. **F3 verified** — vectorbt `freq='1D'` annualizes Sharpe by 365 (calendar) not 252 → daily Sharpe overstated ~1.204×. `scripts/verify_sharpe_annualization.py`. NOT fixed (bundle with F1/F2 cost-Sharpe recalibration). Commit `c361a9d`.
5. **Conviction-score badge** — "Blocked: conviction" live badge now shows the actual score (`_log_filter_rejection` populates `score`; badge `.1f`). Commit `9319d2d`.
6. **LIVE multi-strategy-per-symbol** — live-pass guard changed symbol-level → pair-level (duplicate) + distinct-strategy concentration cap (default 3, `live_trading.max_positions_per_symbol`). MU strategies can now coexist. Commit `7e2c104`.
7. **PAPER research breadth** — flat paper size $5K→$1K + config-driven demo min order ($1K, the validated eToro floor: indices/commodity CFDs need $1K, stocks/ETF/crypto $10). ~100→~500 concurrent paper slots > 370 strategies, killing the balance-exhaustion sampling bias. Commit `e8d68c7`.

**STILL OPEN / NEXT:**
- **Backtest F1/F2 + F3 recalibration (bundled):** Sharpe & win-rate are GROSS of costs (F1/F2), and daily Sharpe is calendar-annualized (F3). Fix = route validated per-trade costs into `from_signals(fees=…)` + correct the 1d annualization, THEN re-baseline WF/conviction/graduation thresholds against the measured gross→net shift. Prereq: **Fix D** — derive empirical per-asset costs from the now-clean slippage data (a few market-hours days needed) and repair historical contaminated `entry_slippage` rows.
- **`strategies.status` ↔ `live_strategies.retired_at` sync bug** — `strategies.status` stays `LIVE` after a pair is retired in `live_strategies` (misled a query; any UI reading `strategies.status` overstates the live book).
- **C-2 (CIO decision):** directional quotas + directional_balance are DISABLED in the yaml; "never zero short" unenforced (empirically non-zero). Enable + set a `ranging_low_vol` short floor, or formally make the rule regime-conditional.
- **Live Portfolio & Alpha audit (recommended):** active live book is net-negative ex the retired SOXL outlier (27% live WR) and concentrated long-tech-momentum — worth a P&L-attribution + factor-concentration pass.
- **B-5:** crypto cross-validation family rescue is dormant (no template sets `requires_cross_validation`).
- **demo 604s:** the demo `604 insufficient funds` were the saturation symptom — should subside as the $1K paper sizing recycles the book; confirm.
- **Verify Monday+ (market-hours):** AE `signal_emitted=emitted`>0 + AE orders fire; SHORT WF pass-rate rises in ranging; conviction badge shows scores; multiple MU live positions coexist (watch `concentration cap reached`); clean (non-drift) slippage rows accumulate; demo paper positions open at ~$1K.

**SESSION 2026-06-16 (PM-2) — edge-roadmap continuation: 3 new rank/carry primitives+templates + momentum-aware validator (Opus 4.8). All deployed live, healthy, pushed. Commits `a88951b` (#1+#3), `cec4e0a` (#2). Runtime catalog 216→219.**

Continued the validate-then-ship edge roadmap. Each new template validated end-to-end (load+DSL-lint+golden, indicator-compute, >0 trades on real data via `scripts/validate_new_templates.py`) before shipping; golden delta-verified each time (only intended adds, zero survivor mutations, order preserved).

1. **Tier 1/2 cross-sectional rank primitives (#3 low-vol, #5 short-term reversal) — SHIPPED.** Two new DSL rank primitives, same architecture as RANK_IN_UNIVERSE:
   - `RANK_IN_UNIVERSE_BOTTOM` (Lehmann reversal — long bottom-N by short-window return) and `RANK_LOW_VOL` (Frazzini-Pedersen — long lowest-N realized vol). Shared key builder `_rank_key(params, prefix)` in `trading_dsl.py` (distinct prefixes); regex extractors + `compute_short_term_reversal_series` / `compute_low_vol_rank_series` in `cross_asset_primitives.py`, wired via **kind-tagged `rank_refs`** `(kind, self, universe, window, n)` + a dispatch table in `compute_cross_asset_indicators`. The `RANK_IN_UNIVERSE\(` regex cannot match `RANK_IN_UNIVERSE_BOTTOM(` (the `_` blocks the `\(`), so no double-count. **Verified codegen key == compute key for all 3 rank kinds** (the exact-match invariant; mismatch → silent 0-trade). Catalog templates: **Short-Term Reversal Long** (NVDA 32/TSLA 36/META 23 trades) + **Low Volatility Factor Long** (PG/KO/JNJ/COST trade). `config/strategy_catalog/factor_price.yaml`. Tests `tests/test_cross_asset_rank_primitives.py` (10).
2. **Tier 4 Forex Carry — SHIPPED.** New `Forex Carry Trend` alpha-edge template (`alpha_edge_type=forex_carry`) in `alpha_edge.yaml`. Dedicated handler keyed by `alpha_edge_type` (mirrors `end_of_month_momentum`), NOT the DSL path. Carry+trend overlay (long when rate spread base-quote ≥ +0.5pp AND price>SMA50; short on the mirror; exit on stop/target, trend reversal, or carry decaying < 0.1pp).
   - `market_analyzer.get_historical_carry(pair)` — daily FRED rate-differential history (monthly policy rates ffilled), the **WF-capable analog** of the live `get_carry_rates()` snapshot → backtest sees the same edge live fires on. `_backtest_forex_carry` + `_simulate_forex_carry_trades` routed **early** in `backtest_alpha_edge_strategy` (before the FMP-quarterly reject); `_handle_forex_carry` live handler (direction-aware exits via `PositionSide`).
   - `strategy_proposer` AE watchlist scorer: added an explicit `'carry'` branch (the fall-through `else` was skipping ALL non-equity → 0 candidates → the template would never get a forex pair).
   - **Root-cause data fix:** the OECD immediate-rate FRED series for **GBP/AUD** (`IRSTCB01xxM156N`) were DISCONTINUED (~2023, return empty) — silently zeroing their carry-conviction bias AND producing 0 carry trades. Switched GBP/AUD/CHF to the maintained 3-month interbank series (`IR3TIB01xxM156N`). Validated: EURUSD 18 / USDJPY 21 / AUDUSD 13 / USDCAD 17 trades over 730d. GBPUSD has ~0 GBP-USD differential (rates near parity) → correctly 0 trades (no edge, not a bug). Tests `tests/test_forex_carry.py` (7).
3. **Latent validator bug (RSI oversold cap) — FIXED.** `strategy_engine.validate_rule_semantics` (codegen path) AND the sibling `_validate_rsi_thresholds` (prose-path, `validate_strategy_rules`) treated any `RSI<X` ENTRY as oversold and capped at ~55, silently dropping momentum templates using `RSI<X` as a blow-off ceiling filter (rule dropped → entries all-False → 0 trades, no error). Now **momentum-aware**: the cap is skipped when the condition also carries a trend/breakout/momentum component (`DONCHIAN`, `ADX`, `MACD`, `LAG_RETURN`, `RANK_*`, `CLOSE>SMA`, …) or an RSI lower bound. NOTE: `_validate_rsi_thresholds` uses prose-style regex (`rsi_14 below X`) and never matched DSL `RSI(14)<X` anyway — the codegen `validate_rule_semantics` was the real DSL culprit; both fixed for consistency. The 4 prior momentum templates still validate; `Multi-Month High Momentum` left on its RSI-range form (changing it would be an unnecessary golden survivor-mutation now that the validator is fixed). Tests `tests/test_rsi_momentum_validator.py` (4).

**EDGE-GAP STATUS now:** Tier 1 #1/#2/#3, Tier 2 #4/#5/#6, Tier 4 forex-carry all SHIPPED. **#7 Sector Rotation** already fixed (stale known-issue). **#8 Pairs Trading** — STILL dormant, needs a design session (per steering, NOT rushed): engine exists (`PAIRS_MAP`, rolling-OLS z-score) but no catalog template. Crypto funding carry NOT feasible (no funding data). F3 Sharpe-annualization still bundled with the data-gated F1/F2 cost-Sharpe recalibration.

**RESIDUAL / FOLLOW-UPS (not blocking):**
- `relative_value`-style direction mislabel pattern now also applies to forex_carry: the template is labeled `direction: long` (so the proposer's LONG selection path is used) but the handler emits LONG **or** SHORT by carry sign. Blast radius LOW (carry uses its own handler, not the DSL `_short_tightening` path). A proper direction-label design pass would cover relative_value + carry together.
- GBPUSD carry ~0 (UK/US rate parity) so the carry template won't trade it now — expected, no action.
- VERIFY on a market-hours cycle: the 3 new templates get proposed (factor_price rank templates need the rank universe symbols in the watchlist; carry needs a forex pair assigned via the new proposer branch) and pass/fail WF+MC organically; carry strategies reach PAPER on EURUSD/USDJPY/USDCAD/AUDUSD.

**OPERATIONAL HARDENING (2026-06-16 PM-2, follow-on) — errors.log triage + fixes. Deployed, healthy, pushed. Commits `b079ebd`, `d5cb471`.** Dug into every non-PAPER-balance error class in `errors.log`:
- **Cycle DB-lock "scheduler may be stuck" (12 ERRORs):** false alarm — the is_alive() pre-checks race, two triggers reach the lock, the loser RAISED instead of skipping. `_acquire_cycle_lock` now returns `'acquired'`/`'busy'`; `'busy'` is a quiet INFO skip (genuine wedge self-heal unchanged). `b079ebd`.
- **404 "Order not found" (133 ERRORs):** lifecycle was already correct (marks CANCELLED); only the raw HTTP layer logged the expected order/position/cancel 404 as ERROR. Now INFO. `b079ebd`.
- **Stale test (NOT a regression):** `test_walk_forward_validated_uses_existing_backtest_results` predated Sprint-5-F2's 730d ex-post sanity backtest; rewrote to match intent (WF result still gates; one ex-post call stamps `expost_730d_*`). `b079ebd`.
- **604/789 (12+ ERRORs) = the excluded demo-saturation symptom, but two real sub-bugs fixed:** the pre-submission balance guard (a) had NO account-mode filter (demo monitor could read the funded LIVE balance → wave through doomed demo orders) and (b) reserved nothing across a pass (a burst all approved against one stale snapshot) and (c) failed CLOSED on a balance-read error (blocked all submissions). Now: mode-filtered, reads once + reserves committed value per pass, fails OPEN. Expected 604/789 reject codes → WARNING. `d5cb471`.
- **SPY data outage (transient 06-14/15, recovered):** fallback chain (DB→Yahoo→FMP→eToro) and `detect_sub_regime` (per-benchmark try/except) were already resilient; only logging was wrong. eToro last-resort misses → WARNING (one ERROR only when ALL sources fail, then raises — no silent stale-data fallback); suppressed yfinance's redundant "possibly delisted" ERROR (500+ lines in the outage). `d5cb471`.
- Tests: `test_order_submission_balance_guard.py` (4). NOTE: pre-existing RED tests in `test_order_monitor.py` (cancel_stale_orders) + `test_pending_order_duplicate_prevention.py` + `test_redundant_dsl_validation_skip` (now fixed) exist independent of this work — the suite is not green on HEAD.



EDGE EXPANSION (2026-06-16) — added 4 validated price-factor templates (216 total). Each validated end-to-end (parse + indicator-compute + produces trades on real data via `scripts/validate_new_templates.py`) before shipping; each still must clear WF+MC to trade. New file `config/strategy_catalog/factor_price.yaml`:
- **Multi-Month High Momentum** (#1) — George-Hwang high-proximity momentum; `CLOSE>=DONCHIAN_UPPER(120)*0.98 AND ADX>20 AND RSI 50-80`. Lookback 120d (252 is all-NaN in a 365d WF test split); RSI as a RANGE (the semantic validator treats any RSI<X entry as oversold and silently skips it — latent issue, see below). Commit `1fd103b`.
- **Dual Momentum Trend Long** (#4) — Antonacci; `CLOSE>SMA(200) AND LAG_RETURN("SELF",126,"1d")>0`.
- **Cross-Asset Trend Follow Long** (#6) — MOP TSMOM; `CLOSE>SMA(200) AND LAG_RETURN("SELF",252,"1d")>0`; targets indices/commodities/broad-ETFs.
- **Cross-Sectional Momentum Long** (#2) — Jegadeesh-Titman; `RANK_IN_UNIVERSE("SELF",[20 mega-caps],126,8)>0 AND CLOSE>SMA(200)`. Commit `88c7232`.

EDGE-GAP STATUS (Tier 1-4):
- **Tier 1/2 shipped:** #1 #2 #4 #6 (above). 
- **#7 Sector Rotation — already fixed** (catalog template already lists all 11 SPDR sectors; dated known-issue is stale).
- **#3 Low-Vol factor + #5 Short-Term Reversal — NEED a primitive-build increment** (NOT rushed): RANK_IN_UNIVERSE only does top-N-by-return. #5 needs a bottom-rank variant; #3 needs a vol-rank (rank by inverse realized vol). Each = new key in `trading_dsl.INDICATOR_MAPPING` + extractor/compute in `cross_asset_primitives.py` + wiring, with exact key-matching (code warns key-mismatch → silent 0-trade). Do as a focused increment with its own tests + the validate harness.
- **#8 Pairs — dormant, needs design session** (per steering): the pairs ENGINE exists (`_simulate_pairs_trading_trades`, rolling-OLS z-score, PAIRS_MAP) but NO catalog template proposes it. Adding requires defining PAIRS_MAP pairs + end-to-end validation.
- **Tier 4 investigated:** Forex carry FEASIBLE (FRED rate data already integrated — earlier "data-gated" was wrong); crypto funding carry NOT feasible (onchain_client only has btc_dominance, no funding); seasonality feasible via dedicated calendar handlers (end_of_month pattern; DSL has no date primitive).

LATENT ISSUE surfaced: `strategy_engine.validate_rule_semantics` treats ANY `RSI(14) < X` entry as an oversold (mean-reversion) signal and caps it at 65 — silently SKIPPING momentum templates that use RSI<X as a blow-off filter (the rule is dropped, entries go all-False, 0 trades, no error). Worked around in #1 by using an RSI range; the validator itself should be made momentum-aware (a real refinement).



After the template-catalog migration (above), ran a full forensic pass on autonomous cycle `cycle_1781595884` (regime trending_up_strong 97%, 518s, completed clean). The template layer is clean (200 proposed → 50 distinct, all resolve in catalog; zero catalog/DSL errors). Findings beyond the migration + fixes:

- **#1 Demo saturation (USER-OWNED, not fixed here):** balance $0, 559/597 gate-blocks = `insufficient_balance`, 8 activated → 0 PAPER → 0 orders. User is doubling PAPER balance. Only 12/176 demo positions are at the new ~$1K size; recycling is slow. Capital-recycling / shadow-book remains the proper long-term fix.
- **#2 Alpha Edge — FIXED (P1+P2):**
  - **P1 (`conviction_scorer._score_regime_fit`):** AE strategies now score neutral **12.0** regime fit instead of running the DSL technical-alignment map, which floored mean_reversion/value/quality-typed AE at **5.0** in trending regimes (analog of the 06-12 carry/crypto AE-denominator fix). This was a primary reason AE capped at conviction 46.3 < 55.
  - **P2 (catalog):** disabled **Share Buyback Momentum** + **Shareholder Yield Long** — `scripts/ae_field_coverage.py` proved FMP `shares_outstanding` = **0% coverage** on the current plan → deterministic 0-trade backtests. Added first-class `disabled_reason` to the catalog schema. Golden re-baselined 214→212 (delta-verified). `sue` is 7.5% (sparse) → `Earnings Momentum Combo` flagged, left enabled.
  - **OPEN/VERIFY → RESOLVED (2026-06-16, instrumentation):** the suspected "AE fundamental component = 0" bug was a **measurement error on my part** (bad log grep). Temporary `[AE-FUND-DIAG]` instrumentation proved the fundamental conviction component computes **correctly**: `Relative Value ASML LONG` emits a SHORT (ASML overvalued at PE 75); ASML's strong fundamentals (+6 raw) are correctly penalised to **−6** on a short, landing conviction 52<55 — correct trading logic, not a bug. Diagnostics removed (commit `83078d5`). P1 (regime 5→12) remains a valid, deployed fix that lifts all AE.
  - **NEW finding (direction mislabeling, NOT yet fixed):** `relative_value` is a long/short template (enter LONG if undervalued, SHORT if overvalued) but the proposer labels the strategy `...LONG` and sets `metadata.direction='long'`. The fundamental scorer correctly used `signal.action` (SHORT), but other direction-keyed logic (SHORT WF tightening, regime-hedge detection, position sizing direction) keys off `metadata.direction='long'` — so a relative_value SHORT can slip through long-side gates. Worth a design pass (same family as the known-broken Sector Rotation / Pairs Trading templates).
  - **AE breadth is UPSTREAM-limited:** only 1 AE strategy (ASML) reached conviction this cycle; the rest died at WF / trades<4 / factor-validation. AE's problem is surviving to conviction, not the conviction score itself. Next AE lever is upstream (factor-validation breadth / min-trades for quarterly-firing fundamentals), not conviction.
- **#3 Zero short (P3 — DONE, Option A, deployed `83b7f13`):** root cause was the SHORT WF tightening rejecting ~100% of shorts in trending_up* (30/30 this cycle), and the uptrend-hedge exemption being applied in 3 places (regime filter, conviction regime-fit, min_trades floor) but NOT the WF tightening. Fix: uptrend-SPECIFIC short templates (market_regimes include a trending_up variant) now skip the +0.3 min_sharpe penalty and regain the excellent-OOS rescue, capped at `backtest.walk_forward.max_uptrend_hedge_shorts` (default 3) per cycle. NOT a bypass — MC bootstrap + (test-train)≤1.5 consistency + signal-time C3 still enforced. 9 enabled uptrend-hedge templates available (Exhaustion Gap, BB Squeeze Reversal, MACD Divergence, Parabolic, Double Top, EMA Rejection, ...). NOTE: 3 short templates remain user-disabled (OBV Bearish, Triple EMA Bearish, Volume Climax Reversal Short) — re-enable via Settings UI if desired. CIO follow-up still open: directional_quotas remain disabled (C-2); the hedge slot provides the floor organically now.
- **#4 Regime vs MQS (INVESTIGATED — NO CHANGE):** regime 97% trending_up_strong vs MQS 50.8 normal. Read `detect_sub_regime`: confidence = `0.5 + trend_score*5` measures trend **magnitude**; MQS measures **quality/consistency**. Orthogonal by design — not a bug. Hacking MQS into regime confidence would be a patch. The monoculture risk is #3's job.
- **#5 PLATINUM data — FIXED (P5):** `scripts/refetch_symbol.py PLATINUM` purged 7,800 contaminated rows, extended 1d 439→757 bars (2023-06→2026-06, full window). FLAG: Yahoo PL=F max close ~$2,852 looks implausibly high for platinum — data-quality spot-check recommended.
- **#6 Cycle-summary exposure blind at balance=$0 — FIXED (`3b3a3ac`).** The portfolio-exposure block was guarded by `account_balance > 0`; with the demo book fully deployed (balance=$0, equity $567k, 184 positions) it skipped entirely → summary falsely showed `Exposure: 0.0% long, 0.0% short` and no Winners/Losers, blinding directional-balance observability exactly when concentration is highest. Guard now uses `(account_equity or account_balance)` (denominator already did); in-loop fallback cap switched to equity; swallowed exception upgraded debug→WARNING. VERIFY next cycle: summary shows real long/short % at balance=$0.
- **Residual low-priority (not cycle-breakers):** (a) `relative_value` direction mislabel — AE template labeled LONG can emit SHORT; blast radius confirmed LOW (AE uses factor-validation, not the DSL `_short_tightening_active` path; P1 makes regime-fit flat 12); only cosmetic direction-miscount. (b) PLATINUM ~$2,852 price spot-check. (c) 1h data sparseness (MU 1h ~5h spacing → strategy correctly skipped; known 1h limitation). (d) AE upstream breadth (trades<4 / factor-validation), not conviction.

---

**STRATEGY TEMPLATE SYSTEM REDESIGN — DONE (2026-06-16, Opus 4.8). Deployed live, healthy, pushed. Commit `8b2b34c`.** Migrated `strategy_templates.py` from an 8,567-line single file (259 inline `StrategyTemplate(...)` in `_create_templates()`, policy in `__post_init__`, load-time culling) to a **strategy-as-data catalog**. Behavior-preserving: same **214** effective templates, byte-identical, same order — proven by a round-trip golden gate.
- **`config/strategy_catalog/*.yaml`** — authored templates, one file per category (alpha_edge/crypto/dsl_core/ranging_specialist/gap_reversal/obv_divergence/vix_regime/volume_climax_reversal/statistical). AUTHORED form (pre-normalization); `seq` preserves order.
- **`template_catalog.py`** — Pydantic-validated, order-preserving, cached loader. **`dsl_lint.py`** — load-time DSL validation (catches unparseable + always-false tautologies like `EMA(10)>EMA(10)`; skips fundamental-prose AE/`alpha_edge_type` templates). **`NormalizationPolicy`** (in strategy_templates) — SL/TP floors, R:R, crypto ADX-gate, sizing defaults extracted from `__post_init__` into an explicit testable layer.
- **Provenance:** `REMOVE_TEMPLATES` set → first-class `enabled:false`/`deprecated_by` in YAML; `_MIN_CRYPTO_TP` → named catalog fee-floor policy. `StrategyTemplateLibrary` public API unchanged (thin adapter); all 9 consumers untouched.
- **`strategy_templates.py` 8,567 → 295 lines.** Tests: `test_template_catalog_roundtrip.py` (golden-master gate, 214 byte-identical + order) + `test_dsl_lint.py` (9 unit tests). Both green local + EC2.
- **Verified:** EC2 loads 214 (45 ADX-injected), health OK, no new errors; all 115 distinct template names proposed in the last 7d still resolve in the catalog (zero DB-history orphans). **PENDING:** confirm an autonomous cycle proposes the same template universe (user to trigger a manual cycle — query `signal_decisions stage='proposed'` for the new cycle, all template_names must be in the 214).
- **Future (not done, no-stopgap):** surface `enabled`/`deprecated_by` in the Settings template UI (currently `.disabled_templates.json` is the runtime override on top of catalog `enabled`); optionally split `dsl_core.yaml` (127 templates) further; consider a typed DSL grammar (Phase-2 lint covers the safety gap for now).

---

**SESSION 2026-06-12 (PM-2) — AE / CRYPTO / SHORT generation-bias audit + fixes (Opus 4.8). Code deployed + verified live, healthy. Local commit `92550c1` — NOT pushed yet (git push needs the hardware security-key PIN; key locked after failed attempts — re-insert key and `git -c core.hooksPath=/dev/null push`).**

Audit of why AlphaCent under-generates Alpha-Edge / crypto / SHORT. Triangulated the `signal_decisions` funnel (since 05-30) vs live code + DB. **Live regime is `ranging_low_vol`** (conf 0.61, not `trending_up_strong` as assumed). Found WHERE each class dies:

- **ALPHA EDGE → dies 100% at the conviction gate.** 104 proposed, 9 activated, 1,401 signals generated, **0 orders EVER**. Max AE conviction score ever = **56 < 60 PAPER floor**. Two root causes, both fixed:
  - **A-1 (deployed):** AE normalized against the 132 theoretical max, which includes carry(5, forex-only) + crypto-cycle(5, crypto-only) — unearnable by equity-only AE. Exact bias the 2026-05-15 DSL per-asset-denominator fix removed, but AE was left at 132. Added `_EFFECTIVE_MAX_AE = 122` (`conviction_scorer.py`) + routed AE normalization through it.
  - **A-2 (deployed):** AE used the flat equity PAPER floor 60 despite a structural ceiling (like crypto). Added `paper_trading.conviction_threshold_alpha_edge: 55` + `live_trading.conviction_threshold_alpha_edge: 67` (yaml) and an AE branch in `strategy_engine.generate_signals` (`min_conviction_alpha_edge`, used in `_effective_threshold`; per-pair `conviction_override` still wins for live AE). Mirrors the crypto structural-ceiling precedent — NOT a boost. Expect the 53→57.4 and 56→60.6 clusters (~449 sig/13d) to start clearing on the next market-hours cycle.
- **SHORT → dies at WF.** Proposed 1,216 (19%), WF pass **2.6% vs LONG 8.9%**. Shorts DO fill (11) so "never zero short" holds empirically.
  - **C-1 (deployed):** the +0.3 min_sharpe floor and removed relaxed-OOS rescue (TSLA *trending_up* audit) applied in EVERY regime → over-suppressed legitimate shorts in ranging/down. Scoped both to `trending_up*` only via `_short_tightening_active` (`strategy_proposer.py`). In ranging/down, shorts now use standard bars + are eligible for the excellent-OOS rescue. C3 signal-time trend-consistency gate + MC bootstrap + consistency gate still protect against TSLA-style shorts-into-uptrends.
- **CRYPTO → NO code change (regime-appropriate, NOT a bug).** Only 1 crypto strategy in the active book. Crypto dies at WF (272/279, mostly `het=False` = <4 test trades). **BUT BTC is −22%/month** (82,210 May-10 → 63,626 Jun-11) — crypto is in a genuine downtrend, the mean-reversion/bounce crypto template pool is correctly matched, and thin-evidence rejections are correct discipline. Forcing trend templates / generation here would be wrong (think-like-a-trader). Confirmed: XRP/ADA/NEAR/LTC/BCH are *commented out* in `symbols.yaml` (intended liquidity/cost decision — the prompt's "fall to Yahoo" premise was wrong). `min_sharpe_crypto` IS wired (at activation, `portfolio_manager.py:776`) — not dead; only absent from the WF acceptance pass (harmless, would be stricter anyway). Crypto conviction denom (106) + threshold (55) already correct.

**CIO / decisions (not changed — UI-owned / rule #7):**
- **C-2 — directional quotas are DISABLED.** `position_management.directional_quotas.enabled: false` AND `directional_balance.enabled: false` in the live yaml → the "never run zero short exposure" steering rule is **not enforced by any mechanism** (shorts are non-zero today only organically). Also `ranging_low_vol.min_short_pct: 0.0`. This is a UI/CIO-owned setting — decide whether to enable quotas (and set a ranging_low_vol short floor > 0) or formally make the rule regime-conditional.

**Follow-ups (not done):**
- **UI exposure:** `conviction_threshold_alpha_edge` is read by code + persists across UI saves (PUT `/config/autonomous` is read-modify-write, preserves unknown keys) but is NOT yet a Settings field. Add to `SettingsNew.tsx`/schema for editability (crypto threshold is the template). Until then it's ops-managed in yaml.
- **B-5:** crypto cross-validation family rescue (`requires_cross_validation`) barely fires (3/13d) — investigate whether crypto-optimized templates should opt in (would help thin-per-symbol crypto when crypto regime turns up). Enhancement, not a bug.
- **Steering doc** `trading-system-context.md` still says AE denom 132 / `min_sharpe_crypto: 0.5` — update to AE 122 + note WF uses direction-aware thresholds.
- Verify on the next market-hours cycle: AE `signal_emitted` with `decision=emitted` > 0, and SHORT WF pass-rate rises in ranging.

**Pre-existing OPEN (unchanged this session):** ~~`order_monitor.check_submitted_orders` `uq_open_pos_strategy_symbol_acct` UniqueViolation~~ **FIXED 2026-06-13** (see P0 entry below); cycle lock-leak self-heal; Marketaux/FRED/insider audit; retention prune.

**P0 FIX (2026-06-13) — `check_submitted_orders` `uq_open_pos_strategy_symbol_acct` UniqueViolation (deployed, healthy).** Root cause: the method reassigns a position's `strategy_id` from the `'etoro_position'` placeholder to `order.strategy_id` (3 sites) and creates new positions — but never checked whether an OPEN position already held `(order.strategy_id, symbol, account_type)`. The bad UPDATE staged in-memory and only violated the partial unique index at the **final batch `session.commit()`**, aborting the WHOLE cycle's fill processing → recurred every cycle (firing 06-12 07:49 on AMD/demo). Fix: added `_open_slot_taken()` guard before all 3 `strategy_id` reassignments (skip + WARN if the slot is taken, leave as `etoro_position`) and savepoint-isolated (`begin_nested()`+flush+guard) the new-position create (A3 pattern). Proper root-cause fix, not a patch. Verify Monday (market-hours order flow) that the guard WARN lines appear and no `uq_open_pos` errors recur.

---

**PAPER capacity / research-breadth fix (2026-06-15) — deployed, healthy.** The demo book saturates (~$538K / 172 positions of the legacy $5K flat size = ~100 slots) but there are ~370 active strategies → ~270 starved each cycle, and *which* get a paper trade is first-come-first-served (balance-exhaustion bias in the graduation sample), surfacing as `604 insufficient funds`. Fix: cut `paper_trading.flat_position_size` $5000→$1000 and lower the demo minimum (was hardcoded $2000 in 3 risk_manager spots + $2000 in the scheduler pre-flight) to a config-driven `paper_trading.min_order_size` (default $1000). **$1000 is the validated floor**: eToro per-instrument minimums are $10 (stocks/ETFs/crypto) but **$1000 for indices/commodity CFDs (SPX500/GER40/ALUMINUM…)** — verified from our own 604 logs — and the order_executor demo `_min_position_size` is also $1000; going lower would silently drop indices/commodities from research. $500K/$1K = ~500 slots > 370 strategies. Graduation gate is scale-invariant (WR/Sharpe/PnL-sign/ratio) so data quality is unchanged. New `RiskManager._get_demo_min_order_size()` (cached, reads `paper_trading.min_order_size`). NOTE: benefit phases in as the existing 172 oversized positions exit and are replaced by $1K entries (saturation persists until capital recycles). Follow-ups if breadth grows again: capital recycling (close data-complete pairs first) and/or a simulated shadow book (paper data with no demo-balance constraint). Optional: raise eToro demo balance for extra headroom.

 The live-pass duplicate guard (`trading_scheduler.py`) was SYMBOL-level (`PositionORM.symbol == sym`), so any one live strategy holding a symbol blocked ALL others — defeating the intended multi-strategy-per-symbol design and idling e.g. `4H Strong Uptrend Momentum MU LIVE` (emitted conviction-80 on 06-05, blocked 10d because `Triple EMA Alignment MU LIVE` held the one MU slot). The DB constraint is already `(strategy_id, symbol, account_type)` and the risk framework caps cumulative per-symbol exposure, so the symbol-level block was redundant + overly blunt. Fix: split DUPLICATE (pair-level: block only if THIS `(strategy_id, symbol)` has an open position / pending order / same-cycle submission) from CONCENTRATION (symbol-level: cap distinct strategies per symbol at `_max_live_per_symbol`, default 3, from `live_trading.max_positions_per_symbol`). Verified the safety chain: `validate_signal` (run on the live pass) calls `check_position_limits` (dollar cap) + the `uq_open_pos_strategy_symbol_acct` DB index backstops true pair-duplicates; the per-cycle in-memory set is now keyed `(strategy_id, symbol)` and feeds the concentration count so same-cycle siblings are counted even if a DB write fails. NOTE: `check_position_limits` is filled-only/pending-blind, which is WHY the explicit live-pass concentration count (incl. same-cycle) is needed. **Watch Mon+:** multiple MU live positions can now coexist (up to 3); look for `concentration cap reached` logs and confirm no duplicate same-pair entries.

**SLIPPAGE-MEASUREMENT FIX (2026-06-14) — deployed, healthy.** Audit of the backtest cost model found the cost config is web-researched, not measured, and our own realized-cost data was broken: (1) `exit_slippage` was 100% NULL (no `log_exit` caller ever computed/passed it); (2) `entry_slippage` was contaminated by overnight DRIFT — `expected_price` is captured at signal time and the worst "slippage" values (SOXL 1528 bps = 15%) were orders eToro queued to the next session and filled 13–17h later (verified: submit→fill gap 13.3–15.8h). Fixes (A+B+C): new `trade_journal.compute_execution_slippage()` helper with a **drift guard** (`SLIPPAGE_MAX_FILL_GAP_S=900s` → records None when submit→fill gap is too large, since the price delta is drift not execution). `log_entry` now takes `entry_submitted_at` and uses the guard; `log_exit` now derives `exit_slippage` from `expected_exit_price`/`exit_order_side`/`exit_submitted_at` with the same guard. Wired the entry/exit fill sites in `order_executor` (long+short open/close) and the primary `order_monitor.check_submitted_orders` entry path; also guarded the `orders.slippage` column write. Unit-tested the helper (adverse buy/sell→positive, overnight→None, improvement→negative, back-compat preserved). **NEXT:** after a few days of clean fills, do Fix D (derive empirical per-asset slippage from quick fills; repair/null historical contaminated rows) then Fix F1 (route validated costs into `from_signals(fees=…)` so the gating Sharpe is net of costs + recalibrate WF/conviction thresholds). Backtest audit findings F1/F2 (Sharpe/win-rate gross of costs) and F3 (daily Sharpe annualization 365-vs-252 — **CONFIRMED 2026-06-14** via `scripts/verify_sharpe_annualization.py`: vectorbt 0.28.5 `freq='1D'` annualizes by 365, exact match to manual×√365; daily Sharpe overstated ~1.204× / +20% vs the √252 trading-day convention. 1h/4h are already correctly trading-hours-annualized, so daily strategies also get a ~20% Sharpe edge over intraday — a cross-timeframe ranking bias. Crypto 1d is correctly 365. Fix: add a 1d branch to the annualization-correction block (×√(252/365) equity/index/commodity, √(260/365) forex, none for crypto) — bundle with F1 because both change the gating Sharpe and need ONE threshold re-baseline) remain open.

**Follow-up batch (same session, 2026-06-13):** worked the 5 open items.
- **A-3 (deployed):** AE fundamental component was *always 0* (verified: 0/2080 AE rows ever showed a `fundamental=` term) because `alpha_edge.fundamental_filters.enabled=false` → no fundamental_report fetched. Root fix in `strategy_engine.generate_signals`: **decoupled** the AE fundamental-data fetch from the fundamental *rejection* gate — AE strategies now fetch fundamentals for the ±15 conviction component even when the gate is off; the hard reject still only fires when the gate is globally enabled (so the DSL equity book is never fundamental-gated). Fail-open.
- **#3 UI (deployed):** added `conviction_threshold_alpha_edge` to the paper-trading + live-trading config endpoints (`config.py` GET/PUT/models) and the Settings UI (`PaperTradingSettingsTab`, `LiveTradingSettingsTab`, `useSettingsData`). Frontend rebuilt on EC2 (✓ 25s). CIO can now tune the AE floor from Settings.
- **#4 steering doc (committed):** updated `trading-system-context.md` — AE denom 132→122, AE conviction thresholds, `min_sharpe_crypto` is applied at activation (not WF), SHORT WF tightening now regime-scoped, directional-quotas-disabled state.
- **B-5 (no change, documented):** `requires_cross_validation`/`family_universe` are set by NO template → the cross-validation family rescue is dormant. Enabling needs per-template `family_universe` design and would admit thin-evidence crypto in the current downtrend — deferred as a design item, not shipped (no-stopgap rule).
- **#5 verification — PENDING (market closed, Sat).** No signal cycle has run since deploy. On the next market-hours cycle confirm: `SELECT decision,count(*) FROM signal_decisions WHERE reason LIKE '%path=alpha_edge%' AND timestamp > '<deploy>' GROUP BY decision` shows `emitted>0`; AE `order_submitted/order_filled` go positive; SHORT WF pass-rate rises in ranging. Commit `92550c1` (A-1/A-2/C-1) + this batch.

---

**SESSION 2026-06-12 — DATA-PIPELINE P2 batch + FMP-warm fix + live-pass observability (Opus 4.8). All deployed, verified live, pushed. Latest commit `8d8d566`.**

Continued from the data-pipeline audit. Completed the remaining flagged items + two user-reported issues:

- **FMP cache warm "Failed" (System tab)** — was coverage 68.8% (<80% gauge). Root cause: 20 non-fundamental instruments (sector/thematic/leveraged ETFs CIBR COPX DBA DFEN EEM EWZ KWEB PALL SMH SOXL SOXX SPXU SQQQ TQQQ UPRO URA WEAT + forex NZDUSD + foreign RHM.DE/RR.L) returned None every warm AND, sorted first as "never fetched", **starved the 30/cycle budget so 58 real stocks went stale**. Added them to `FMPCacheWarmer.SKIP_FUNDAMENTALS`; drained backlog via `scripts/warm_fundamentals.py` → **coverage 100% (230/230, 0 failed)**. `scripts/fund_gap.py` is the read-only coverage-gap diagnostic.
- **DST P2** — `fmp_ohlc._parse_bars` now catches `pytz.AmbiguousTimeError`/`NonExistentTimeError` (NOT ValueError subclasses — would have escaped the parse except and crashed a 24/7 FMP fetch on the Nov fold). Resolves fold→standard time, shifts spring-forward gap.
- **Holiday-aware staleness P2** — `_subtract_weekend_hours` (signal-gen freshness SLA) and the `_sync_price_data` 1d gap test now subtract US-holiday days via the canonical `market_hours_manager.US_HOLIDAYS` (was weekend-only → false-stale the trading day after a holiday, could block signals / trigger pointless refetch).
- **Loop-timing P1** — decoupled demo+live `get_account_info` (equity/balance) from the 60s position-sync phase onto a **5-min cadence** (`_account_info_interval`), removing 2 serialized eToro calls from the critical current_price path. Added per-call demo/live `sync_positions` timing (>15s WARNING). Confirmed steady-state slip is **cumulative sub-phase work + DB contention from the one-time backfill**, not a single slow call (per-call timers never fired).
- **FMP LME/commodity honesty** — re-probe: Starter serves only GOLD/SILVER 1d; OIL/COPPER/PLATINUM/NATGAS/ALUMINUM/ZINC premium-blocked at all intervals (FIX-D "FMP primary for LME" was DEAD). Marked them all `EXPLICIT_BLOCKED` so they skip FMP without a wasted 402 and route to Yahoo (=F).
- **Cleanup** — removed dead+buggy duplicate `get/set_market_data_manager` singleton (top pair passed config as etoro_client, shadowed by bottom). `data_management.py` sync-status now queries `fetched_at` (was non-existent `updated_at`). Full-sync summary escalates to WARNING when errors>0.
- **LIVE-pass observability (user-reported "Signal emitted 170h ago")** — diagnosed: `4H Strong Uptrend Momentum MU LIVE` emitted 06-05 at conviction 80 but never filled because `Triple EMA Alignment MU LIVE` held the **one live MU slot** (live pass enforces one open position per SYMBOL across all strategies) and the symbol-level duplicate guard skipped all MU entries — **silently** (no funnel row). After the slot freed (13:55) the momentum setup had passed → genuinely idle since. NOT a bug. Added `record_decision()` writes at every live-pass skip/fail (duplicate guard, conviction, validate_signal raise/reject, mirror-missing×2, exec exception) so live signals that don't convert are now visible in the funnel as `gate_blocked`/`order_failed`.

**New scripts:** `scripts/repair_eod_bars.py`, `scripts/refetch_symbol.py SYMBOL`, `scripts/fund_gap.py`, `scripts/warm_fundamentals.py`. All run on EC2 with `set -a && . ./.env.production && set +a` for DB creds.

**STILL OPEN (flagged, not done):**
- **`order_monitor.check_submitted_orders` UniqueViolation** (`uq_open_pos_strategy_symbol_acct`, firing 06-12 07:47–07:49) — a THIRD position-create path not wrapped in `begin_nested()` (A3 only covered `reconcile_on_startup` + `_sync_positions`). Same bug class; wrap it. Position-sync scope.
- **Cycle lock-leak self-heal** — `_db_cycle_lock` (threading.Lock in strategies.py) is only released on normal return; a hung `run_strategy_cycle` (e.g. cache-warming stall during heavy DB/FMP contention, which happened 06-11 23:46 under the backfill load) leaks it permanently → all future cycles fail "Could not acquire DB lock" until restart. No watchdog. Add holder-thread/acquired-at tracking + force-release on dead/over-max-duration holder. Also time-box the cache-warming cycle stage.
- **Marketaux / FRED / insider proxy** — NOT yet audited with evidence (Category 8 of the data-pipeline prompt was under-covered; only FMP fundamentals done).
- **Retention prune** — 439K/1.66M 1h rows >730d, 0 LIVE 1h consumers, WF cap 730d. Prune `WHERE interval='1h' AND date < now()-'760 days'` in batches off-peak. Awaiting go-ahead.

**NEXT — user wants an audit of Alpha Edge / crypto / short-trade generation (system isn't producing many). See `ALPHA_EDGE_CRYPTO_SHORT_AUDIT_PROMPT.md`.**

---

**SESSION 2026-06-11 (PM-2) — DATA-PIPELINE forensic audit (Opus 4.8). P0 + P1 fixed, deployed, repaired, verified live, pushed. Commit `7a86071`.**

- **P0 — frozen provisional 1d bars (data integrity).** `_save_historical_to_db` was INSERT-ONLY: today's still-forming 1d bar (written ~market-open by the full sync each morning) froze permanently and was never corrected to the real EOD close. **Verified live: AAPL 1d 06-10 stored 290.31 vs true close ~291.58; ~8,552 daily bars corrupted since the FMP-1d go-live (05-03).** Root fix: PostgreSQL `ON CONFLICT DO UPDATE` upsert + new `_bar_is_complete()` forming-bar exclusion (never persist an unclosed bar — 1d uses 21:00 UTC / crypto next-00:00 UTC; intraday uses open+interval). This also kills the no-savepoint batch-abort on unique collisions. **Repaired** existing bars: `scripts/repair_eod_bars.py` (305 symbols, 0 fail; AAPL 06-10 290.31→291.58). Upsert-only, no deletes; 1d total unchanged (~371K).
- **P1 — NSDQ100 wrong instrument (ALUMINUM-class).** `fmp_ohlc.SYMBOL_MAP` routed `NSDQ100 → ^IXIC` (Nasdaq **Composite**) while eToro/Yahoo use `^NDX` (Nasdaq-**100**). **FMP Starter doesn't serve `^NDX` at all** (probe-confirmed 402 at 1d+1h), so NSDQ100 must use Yahoo `^NDX`. Fixed map → `^NDX`, marked `^NDX` premium-blocked on FMP (avoids 402 roundtrip), and fixed the intraday dead-end branch (`elif interval in (1h,4h): return []`) so US indices fall through to Yahoo instead of returning empty (was about to silently zero-out NSDQ100 1h/4h). **Purged + re-fetched** NSDQ100 all intervals via `scripts/refetch_symbol.py` — now single-source `^NDX` (1d 2023-06→now, close [14109,30660] = genuine NDX levels). Only NSDQ100 was mismapped (SPX500/DJ30/UK100/GER40 verified consistent).

**Data-pipeline audit findings NOT yet actioned (see full report in session log / `DATA_PIPELINE_AUDIT_PROMPT.md` thread):**
- **P1 loop-timing still firing** (`47.7s > 45s` at 22:41 live) — root-cause the slow eToro position-sync call; instrumentation exists, fix doesn't.
- **P2 DST landmine** — `fmp_ohlc._parse_bars` `is_dst=None` raises `AmbiguousTimeError` (not caught by `except (KeyError,ValueError,TypeError)`); latent (forex fold is during weekend close) but will crash a 24/7 FMP fetch on the Nov fold. Catch pytz ambiguous/nonexistent.
- **P2 staleness predicates ignore holidays** — 4 divergent freshness checks subtract weekends only; `market_hours_manager` (holiday-aware) is the canonical primitive but the data path doesn't use it → false-stale on US holidays. Unify.
- **P2 `/data/quality`** — 2553ms full seq-scan (EXPLAIN-confirmed); 60s cache is in-process (per-worker). Make process-shared or background-computed.
- **P2 fetch/save failures logged at `debug`** — invisible/unalerted; add per-cycle failed-symbol count + one greppable summary line.
- **P2 `_save_historical_to_db` upsert now rewrites all completed bars in data_list each call** — fine at steady state (incremental = ~2 bars); only the rare shallow-cache 5y refetch upserts in bulk.
- **Architecture** — duplicate shadowing singleton getters/setters in `market_data_manager.py` (top pair is dead + buggy: `MarketDataManager(config)` passes config as etoro_client). `data_management.py:105` queries non-existent `updated_at` column (use `fetched_at`).
- **LME note** — `ALIUSD`/`ZNUSD` 1d are ALSO premium-blocked on the current Starter plan (log: "premium-blocked: ALIUSD 1day") → ALUMINUM/ZINC fall back to thin Yahoo `ALI=F`/`ZNC=F`. FIX-D's "FMP primary for LME" may be dead on the current plan — re-verify coverage.
- **RETENTION (flagged, not done)** — 439,014 / 1,656,592 (26.5%) of 1h rows are >730d old; 0 LIVE 1h strategies, WF cap = 730d. Prune candidate `WHERE interval='1h' AND date < now()-'760 days'` in batches off-peak — awaiting go-ahead.
- **Watch** — `20:58:49` DELL `UniqueViolation` aborted the whole startup reconcile despite the A3 savepoint claim; re-verify A3 is deployed/working (position-sync, out of data-pipeline scope).

**New scripts:** `scripts/repair_eod_bars.py` (one-time EOD repair), `scripts/refetch_symbol.py SYMBOL` (purge+refetch a wrong-instrument symbol). Both run on EC2 with `set -a && . ./.env.production && set +a` for DB creds.

---

**SESSION 2026-06-11 (PM) — 3rd forensic audit (Opus 4.8) + architecture pass + frontend/perf fixes. All deployed, verified live, pushed. Latest commit `e6ef408`.**

Full audit re-verified the live book 3-way (eToro `account_info` LIVE positions_count = DB open live = sync log, reconciled cleanly). Then fixed, in order:

- **P0 — account.py close-path scoping.** `POST /positions/close-all` and `POST /positions/trigger-fundamental-check` had NO `account_type` filter (same incident class as the 06-11 sync bug, but those two endpoints were never scoped) → a demo-mode call would close/flag the LIVE book. Both scoped; live fundamental check now emits `[LIVE-REVIEW]` instead of auto-`pending_closure`.
- **P1 — TSL ratchet** (`monitoring_service`/`position_manager`): breakeven + profit-lock are price-only and now run even when historical bars are stale; only the ATR-trail step is gated by bar freshness (was: stale bars skipped the WHOLE ratchet → SOXL sat +8% with SL=entry). **P1 — breach enforcement decoupled** onto its own isolated session + 5s `lock_timeout` so a blocked recalc read can't skip stop enforcement (the 11:20 statement_timeout incident). **P1 — exit-signal close** moved to a fresh session (the 11:22 DIA `InFailedSqlTransaction`). **P1 — graduation gate**: docs corrected (type-aware WR floors 0.45/0.50/0.55, NOT a flat 55%) + new Intel **G11** post-graduation live-WR probation (Wilson-upper < type floor over ≥10 live trades → flags for CIO; fires on GOOGL 2/15).
- **P2** — `_resolve_mirror_ratio` guard (skip live order if mirror_ratio missing, never guess 0.10); NEW-02 regime SL/TP tightening skipped for leveraged ETFs (noise stop-outs); slippage now recovers `filled_price` from the matched position (~75% of fills had NULL slippage); dropped duplicate `idx_positions_strategy_id`/`idx_positions_closed_at`.
- **Architecture A1–A5** (each its own deploy+verify): **A1** new `src/core/position_close.py` (canonical `finalize_position_close` with cross-account REFUSAL + `positions_absent_from_etoro` with empty-guard) — API close surface routed through it. **A3** wrapped both `order_monitor` batch-create sites in `begin_nested()` savepoints (one `UniqueViolation` no longer aborts the whole reconcile — verified: hit a real demo-DELL collision, logged `SKIPPED create`, reconcile COMPLETED). **A2** new `src/core/staleness.py` (canonical `PRICE_FRESHNESS_SLA_S` + helpers; TSL guard/breach unified onto it). **A4** triaged silent excepts (critical-path ones are benign fail-opens; tagged 4 `# silent-ok`). **A5** `/approaching-graduation` routes eligibility through the authoritative `is_qualified` (was a drifted inline copy).
- **Frontend** — fixed `o.getTime is not a function` crash in the System tab: `formatTimestamp`/`formatAge` assumed non-string == Date and crashed on an epoch number; added `coerceToDate()` (string|number|Date→Date|null). Rebuilt + live (`index-BT4izZFM.js`).
- **Perf** — `/data/quality` cached 60s in-process (was a 1.2s full seq-scan over ~2.5M `historical_price_cache` rows on every System-tab load).

**OUTSTANDING (CIO / decisions):**
- **PANW live oversized** — $1,000v ($127r) vs CIO-approved $100r ($787.4v); legacy from the old 0.10 mirror. Reposition is a CIO call (rule #7). (AMD already repositioned correctly to $787.4v.)
- **GOOGL** — retired, but G11 flags it (2/15 live WR) as the worked example; confirm no other live pair trips G11 as trade counts grow.
- **Data-pipeline retention** — ~1.66M of 2.5M `historical_price_cache` rows are 1h bars back to 2023-09 for ~300 symbols, but WF only uses 730d and ~1 live 1h strategy exists. Likely-prunable; needs confirmation no backtest reads >730d of 1h. **See the data-pipeline audit prompt: `DATA_PIPELINE_AUDIT_PROMPT.md`.**
- **Group-2 uncommitted local files** (audit docs, `scripts/test_live_sl_update.py`, `nginx.conf`, `config/.wf_cache_schema_version` → gitignore).

**Earlier 06-11 entries below (live incident, pullback exemption, phantom-exposure, Sprints A–D) remain valid history.**

---

**LIVE INCIDENT resolved (Jun 11 2026, ~15:40 UTC) + Sprint-A P1-1 REVERTED. (1) `POST /positions/sync` (account.py) had NO account_type filter on its "no longer on eToro → close" check — syncing/viewing the DEMO positions page closed the LIVE AMD+PANW (not in the demo eToro response). That emptied the live book in DB → live pass duplicate-guard saw no PANW → re-entered → DUPLICATE PANW on eToro. FIXED: scoped account.py sync by account_type + empty-response guard (deployed). (2) Recovery: closed the $25r/$200v duplicate PANW (3479037258), reopened the $1,000v original PANW (3476115401) + AMD (3478913304) in DB. Live book now AMD + PANW = matches eToro. (3) Sprint-A P1-1 `min(pipeline, CIO/mirror)` REVERTED (commit f34acb3) — it shrank AMD to $25r vs the CIO-approved $100r (pipeline hit $200v floor on a drawn-down book). Live size now = CIO/mirror exactly; validate_signal gates but never shrinks below CIO. OUTSTANDING: the existing AMD live position is $25r (under-sized from the bug) — CIO to decide leave-or-reposition.**

**Pullback gate — deep-oversold dip exemption (Jun 11 2026, ~15:20 UTC). DIAGNOSIS: idle ~$300K demo balance was NOT a bug — strategies emit 5–9K signals/day, but the pullback gate blocked ~78–92% of trend LONG entries because SPY is in a moderate pullback (5d −2.9%, RSI(5)=18). EVIDENCE (SPY 2021–26, `.kiro_tmp/pullback_analysis.py`): moderate pullback ALONE ≈ baseline fwd returns (nothing to protect), but moderate + RSI(5)<20 → fwd 5d +2.0% avg / 88% win (n=24), 8× baseline. FIX: pullback gate moderate branch now exempts DAILY trend-following (interval=1d, broad-trend, not intraday/momentum) when RSI(5)<20 so it buys the oversold dip; intraday/momentum still blocked (C2 covers momentum-crash); mean-reversion unaffected. `_DEEP_OVERSOLD_RSI=20` hardcoded in the gate. VERIFIED: exemption firing, orders flowing (17 submitted in 8 min vs 27 all prior day), demo deployed $237K→$282K, 64→75 open positions, 0 errors.**

**Post-change verification (Jun 11 2026, market open ~14:50 UTC) — caught + fixed a phantom-exposure regression. `check_position_limits` was computing AMD/QQQ demo exposure as $1.17M/$1.76M (vs real $7,370/$5,500), falsely tripping the position cap and blocking paper entries. Root cause: ORM→Position dataclass conversions never set `invested_amount`, so `_get_position_value` hit the `shares×price` fallback — and some demo positions store `quantity` in DOLLARS (~2500) → 2500×price ≈ $1.17M. (Sprint C introduced the fallback; A1 carried it; LIVE unaffected — its quantity is genuinely shares.) Fixed by passing `invested_amount` in all 4 risk-feeding Position constructions (demo cycle, both live-pass sites, graduation size-estimate). Verified: post-fix demo cycle ran with NO false rejections. Full system clean: 0 errors since 14:52 (excl benign websocket-disconnect), 0 FIX-09 storms all day post-12:05, TSL every ~60s, price_updated_at fresh (<60s), equity snapshots fresh, no loop-timing/F31/freshness warnings. Commit `91e148d`.**

**A1 phase 1 (typed notional) IMPLEMENTED + deployed (Jun 11 2026, ~12:06 UTC). New `src/models/notional.py` (`position_notional_usd` / `position_shares`) — single source of truth for shares↔dollars. `RiskManager._get_position_value` delegates to it (the hub for all risk consumers: symbol/sector/heat/exposure/position caps + VaR), behavior-preserving (reconciliation demo $236,180.94 / live $2,574.80 unchanged; unit tests pass). Fixed a PAPER-sizing bug in passing (pending exposure was `quantity×price` on dollar-valued entry orders → ~price× over-count → wrongly blocked paper entries; now uses canonical `_get_pending_entry_exposure`). Phase 2 (orders notional column) + Phase 3 (rename quantity→shares) deliberately NOT done — see `docs/DESIGN_A1_typed_notional.md §9` (phase 3 recommended against on a live DB). Zero post-deploy errors.**

**Architecture pass 1 (Jun 11 2026, ~11:20 UTC): F31 + A2 + A4 deployed.**

**Sprint C + D complete + follow-ups (Jun 11 2026). A1 now interval-aware (1h/2h→2d, 4h→5d, 1d→10d; 81→39 genuinely-stuck); INTEL_SPEC A1 doc corrected; fixed pre-existing graduation size-estimate 500 (AccountInfo missing mode/updated_at). LIVE BOOK CLEANED UP (CIO actions done): GOOGL, COPPER, TXN retired (losers); SOXL re-graduated (winner, new live_strategies row id 15, position_size 100.4 / conviction_min 72). Active live: AMD, DELL, INTC, MU×4, PANW, SOXL, TQQQ, XLK. COPPER live fully wound down (strategy retired + $1,000 position closed 09:59 UTC via the pending-closure pass). Live-retire endpoint now flags open live positions for closure automatically (commit `8474f3e`).**

**Sprint B complete (Jun 11 2026, 07:36 UTC). Graduation-gate statistical-power fixes deployed & verified live (P0-2).**

---

## SESSION 2026-06-11 — SPRINT C + D

### Sprint C — P2 correctness / quick wins (deployed, commit `65f1e9a`)
| Fix | What |
|---|---|
| market_regime crash | `strategies.py` `get_autonomous_status`: `(full_config.get('market_regime') or {})` — the `{}` default only applied when the key was absent; a present-but-None value crashed the endpoint (errors.log 06-10 11:48). |
| `_get_position_value` units | `risk_manager`: when `invested_amount` missing, value = `quantity × price` (shares→dollars) instead of raw share count (was under-counting exposure, defeating symbol/heat caps). Docstring corrected. |
| Leveraged-ETF consolidation | `position_manager._classify_symbol` now routes through canonical `sl_caps.is_leveraged_etf`; added the previously-divergent NAIL/CURE/DFEN/WANT/HIBL/HIBS to the canonical set (finishes P0-4 consolidation — nothing regresses). |
| NEW-08 404 dead-end | `order_monitor.cancel_stale_orders`: on a 404 cancelling an already-stale (>24h) order with NO open position, mark CANCELLED instead of leaving PENDING forever (status-poll also 404s → infinite churn). If an open position exists, leave for the fill/reconcile path. |
| Graduation queue consistency | `strategies.py` approaching-graduation view now mirrors `is_qualified`'s Wilson WR lower-bound gate, so a Wilson-blocked pair doesn't vanish from both the queue and the approaching list. |
| (verified, no change) | LIVE strategies are already skipped at the top of the autonomous retirement loop (rule #7 satisfied); `auto_retire_strategy` is a legacy no-op. Clarifying comment only. |

### Sprint D — RESEARCH: the "156 zero-signal BACKTESTED strategies" (Intel A1) — FALSIFIED
**Conclusion: A1 was a 100% false positive. There are NO structurally-dead strategies. No mass retirement is warranted.** (commit `<intel>`)

Ground truth (live DB, signal_decisions):
- All 300 BACKTESTED strategies had `performance->>'last_signal_at'` = NULL — not "stale", *never populated*.
- The `performance` JSON only ever contains `{avg_loss, sharpe_ratio, avg_win, sortino_ratio, max_drawdown, win_rate, total_return, total_trades}` — **`last_signal_at` and `paper_trades` keys are never written**.
- Real signal history (signal_decisions): **188/300 BACKTESTED strategies emitted signals in the last 7 days** (22,111 `signal_emitted` rows, 554 orders submitted, 48 fills).
- Of the 171 strategies A1 flagged as "0 signals": **138 emitted in the last 7d, 160 ever, and all 171 submitted orders.**

Root cause: A1 read `strategies.performance->>'last_signal_at'`, a field nothing writes. The `/strategies` API computes last-signal correctly from `signal_decisions` (`strategies.py:667`) — A1 just used the wrong source. **Same root cause broke A6** (its `last_signal_at IS NOT NULL` guard was never true → A6 never fired → a dead "signals firing but not converting to trades" detector, a false negative).

Fix deployed (both checks re-pointed at the real sources):
- **A1** now reads `signal_decisions` (stage=`signal_emitted`). Flagged count drops 171 → **81** (the genuinely-idle-3d+ set, mostly low-frequency daily strategies — not broken). Title reworded "no signal in 3d+", stays P2.
- **A6** now reads `signal_decisions` for signals + `trade_journal` (account_type=demo) for paper trades. Restored from dead → working; currently **0 findings** (signals are converting fine — fires only when a real conviction/gate conversion problem appears).

Minor follow-up (not done): A1's 3-day idle threshold is aggressive for daily strategies (a daily trend strategy idle 3d is normal); consider an interval-aware idle threshold. INTEL_SPEC.md still documents A1 as P1 — stale doc.

**Sprint A complete (Jun 10 2026, 23:27 UTC). Second forensic audit (Opus 4.8) + live-capital correctness fixes deployed & verified live. Service healthy, no post-deploy errors, TSL clean. See "SESSION 2026-06-10 — SPRINT A" below.**

---

## SESSION 2026-06-11 — SPRINT B: GRADUATION RIGOR (P0-2) + LIVE BLEEDER FLAGGING (P0-1)

Deployed `graduation_gate.py` + `config/autonomous_trading.yaml`, restarted 07:36 UTC, health green, zero post-deploy errors.

### P0-2 — graduation gate statistical power (deployed)
Root cause of GOOGL/TXN reaching live: the gate had no real min-trades floor and a point-estimate win-rate gate with no statistical power.

| Fix | What |
|---|---|
| **Hard min_trades floor = 15** | `_get_min_trades_for_interval` used a dynamic Sharpe formula `max(5, ceil((1.96/sharpe)²))` as the PRIMARY path, which collapses to **3–5 trades** for paper_sharpe ≥ 1.0 — i.e. a strategy could graduate to real money on 5 paper trades. The YAML `graduation_gate.min_trades: 15` was LOADED into `MIN_PAPER_TRADES` but never used in this function. Now `MIN_PAPER_TRADES` is enforced as a hard floor the dynamic formula AND the high-conviction exception cannot undercut. (User-set floor = 15.) |
| **Wilson lower-bound win-rate gate** | The point-estimate WR gate (≥55%/type floor) has no power at small n — a sub-floor strategy clears it by luck; with ~300 candidates (multiple testing) false positives are expected (GOOGL 11% WR/18 live, TXN 0%/3). Added a 90%-confidence Wilson lower-bound check on win rate, taken RELATIVE to the strategy-type floor (`lower_bound ≥ type_floor − 0.10`). Type-relative so the all-trend-following live book (legitimately low WR) is not blocked — only small-sample flukes whose lower bound collapses below the floor. Config: `graduation_gate.wr_ci_confidence: 0.9`, `wr_ci_floor_tolerance: 0.1`. Both gates live in `is_qualified` (the authoritative gate via `get_graduation_queue`). |

Verification: py_compile + YAML valid; service restarted healthy; `graduation_gate` imports at startup (strategies router) with no error; no U+2500/import errors on 06-11. A legitimate trend strategy (type floor 0.35, 55% WR over 18 trades, Sharpe 1.2) still passes both gates (worked example confirmed); a 5-trade or barely-above-floor fluke now fails.

### P0-1 — live bleeders: FLAGGED for CIO (NOT auto-retired, per steering rule)
Live book is +$73v total **only** because of one SOXL outlier (+$868, n=4). Ex-SOXL: **−$795v ≈ −$101 real (~7.8% of the $1.3K stake)** across 48 trades. Recommend CIO retire:
- **GOOGL** (4H EMA Ribbon Trend Long) — 11% WR over **18** live trades, −$105v. Statistically broken, not a small sample.
- **TXN** (Keltner Channel Breakout) — 0% WR / 3, −$196v (worst dollar loss).
- **COPPER** (Dual MA Volume Surge) — G5 WF-divergence retirement candidate, −$19v.

**Why not auto-retired:** steering rule #7 (no irreversible real-money actions without CIO confirmation). Note discovered during Sprint B: `portfolio_manager.auto_retire_strategy` is a **legacy no-op** (logs only; "risk managed at position level"), so the autonomous cycle's retirement path does NOT actually retire live strategies — yet it still broadcasts a "Strategy Retired" notification, which is misleading. Real retirement is CIO-driven / position-level. **Watch item:** the no-op auto-retire + misleading broadcast means performance-retirement triggers never act — worth a proper fix next (make the LIVE path emit a real `[LIVE-REVIEW]` flag + accurate notification rather than a phantom "retired" broadcast).

### Still open after Sprint B
- CIO action: retire GOOGL/TXN/COPPER via dashboard.
- Graduation queue endpoint (`strategies.py:~1955`) has an inline eligibility duplicate that applies the min_trades floor (via `_get_min_trades_for_interval`) but NOT the Wilson gate — secondary display only; authoritative `is_qualified` gate is correct. Route through `is_qualified` in a future cleanup (duplicate-logic debt).
- Sprint C (P2 quick wins): `strategies.py:3174` market_regime None crash; NEW-08 404 churn; `position_manager._classify_symbol` leveraged-ETF set consolidation; `_get_position_value` share-fallback.

**Sprint 14 complete (Jun 10 2026). Forensic audit P0+P1 fixes deployed & verified live. Service healthy, trading cycle + live pass running clean, position sync clean, fresh live snapshot, zero post-deploy errors. See "SESSION 2026-06-10 — SPRINT 14" below.**

---

## SESSION 2026-06-10 — SPRINT A: LIVE-CAPITAL CORRECTNESS (2nd audit)

Second full forensic audit (Opus 4.8) re-verified every Sprint 14 claim against live DB/logs/source. Most infra fixes held. Sprint A executed the four live-capital *correctness* findings. Deployed `trading_scheduler.py` + `monitoring_service.py`, restarted 23:27 UTC, health green, zero post-deploy errors, TSL running clean.

| Fix | What | Root cause |
|---|---|---|
| **P1-1** | Live order size now `min(pipeline, CIO/mirror)` (was raw `CIO/mirror`, pipeline discarded as "advisory"). | `validate_signal` computed vol/drawdown/heat-adjusted size + validated symbol/exposure/VaR caps against it, then the live pass threw it away and traded a *different* number — caps validated one size, executed another. Now executed ≤ validated, so caps hold and the risk framework can scale live DOWN in adverse regimes (never above CIO cap → risk only decreases). |
| **P1-2** | `_adjust_opposing_position_sl`: deleted dead duplicate def (was shadowed), removed the no-op positional call site, added `account_type` filter to the query. | Two methods same name/different signatures; call site 1896 passed positional args → `new_tp=None` → silent no-op; effective method (3554) queried positions with NO account_type filter → a DEMO short on MU/AMD could widen a LIVE position's DB stop (the value TSL breach reads). |
| **P1-3** | Price-freshness guard at top of `_check_trailing_stops`: if a monitor's last *successful* sync (`_last_full_sync`) > 180s, force a resync before breach enforcement so stops act on fresh `current_price`. | Breach enforcement trusted `current_price` with only a `>0` check. During the 76–86 min loop gaps (observed 2026-06-10), price went stale → real breach missed / ghost breach on live capital. Self-heals the exact gap scenario; never disables stops on outage. |
| **P1-4** | Per-phase + per-cycle timing instrumentation in the monitoring loop (`[loop-timing]` WARNING when position-sync/trailing phase >30s or cycle >45s). | The 76–86 min loop gaps (root cause of the FIX-09 storms) were invisible — only surfaced downstream as staleness storms. Now greppable in real time so the offending eToro call can be fixed with evidence. Note: eToro calls already have a 30s timeout + bounded retry, so the proper next step was instrumentation, not a guessed timeout change. |

**Verified-correct during audit (no action):** session-rollback-on-checkout; both unique indexes live; P0-2 in-memory live symbol guard; live-pass account scoping; WF (test−train)≤1.5 gate on all 3 paths; transaction costs read `backtest.transaction_costs` (no phantom costs; top-level `transaction_costs` block is dead/unread); conviction normalization denominators internally consistent (no Tier-1 inflation — the `Asset(12)` comment is a typo, denom 101 assumes 15); Intel auto-resolution logic correct; MQS persisting (52.8); P0-4 leveraged SL (20% cap, 0.5× sizing, dead 4% cap gone).

**Still open from 2nd audit (NOT done in Sprint A):**
- **Sprint B (P0-1/P0-2):** Live book +$73v total is ENTIRELY one SOXL outlier (+$868, n=4, one +46% hold). Ex-SOXL: −$795v ≈ −$101 real (~7.8% of $1.3K stake) across 48 trades. GOOGL 11% WR/18 trades, TXN 0%/3, COPPER (G5). Root cause: graduation gate min_trades 10/15/25 + 55% WR gives a ~±23% WR CI → sub-50% strategies pass by luck; ~300 candidates (multiple testing) ⇒ expected false graduations. Fix: Wilson-lower-bound WR≥0.50 gate, raise min_trades→20, cumulative live-loss/WR auto-halt. Then CIO-flag GOOGL/TXN/COPPER for retirement (NOT auto-retired — rule).
- **P2 quick wins:** `strategies.py:3174` `(full_config.get('market_regime') or {})` crash; NEW-08 stale-order 404 churn; `position_manager._classify_symbol` still has its own leveraged-ETF set (P0-4 consolidation incomplete); `risk_manager._get_position_value` falls back to share count when `invested_amount` missing.
- **P1-1 follow-up:** `check_position_limits`/`check_exposure_limits` still use demo `self.config.max_position_size_pct` as the live gate threshold (conservative, not a hole — left untouched to avoid destabilizing the working live gate).

**Sprint 13 complete (Jun 10 2026). 14 crash-audit fixes + 6 Intel fixes + 6 P1 improvements + 3 session-corruption fixes deployed. Live account updated to $1,300 real / 0.127 mirror ratio. Pullback gate recalibrated. System actively trading again.**

---

## SESSION 2026-06-10 — SPRINT 14: FORENSIC AUDIT P0 + P1 EXECUTION

Full forensic audit (Opus 4.8) + execution of every P0 and P1 finding. All deployed to EC2 and verified.

### Research outcomes (root causes confirmed)
- **`quantity` unit ambiguity**: `etoro_client.get_positions` writes `quantity=units` (shares) and `invested_amount=amount` (dollars). Entry orders store dollars (`position_size`); close/SL/TP orders inherit share-valued `position.quantity`. `invested_amount` is the only reliable dollar field. FIX-B's `quantity × price` premise was a misdiagnosis (entry orders are already dollars).
- **Intel never auto-resolves**: `_upsert_finding` only INSERT/UPDATEs — findings stay `open` forever. Root cause of the 244-open-P1 pileup and stale E5/A1/D2 noise.
- **E5 false positives**: balance-exclusion only matched the `$0` variant, so `$409/$1059/$1432` balance blocks survived as "structural". D1/D2 measured raw wall-clock staleness (no market-hours awareness) → fired for every open position every overnight/Monday.

### P0 — live capital (all deployed + verified)
| Fix | What |
|---|---|
| P0-1 | FIX-09 watchdog rewrite. Cooldown stamp now set BEFORE remediation (the 5s storm was caused by the stamp being after a raising sync). Remediation now WRITES a fresh live snapshot (the thing the check reads) — a position resync never refreshed it. Threshold 60m→90m (> 60m snapshot cadence) kills boundary aliasing. CRITICAL only after 2× threshold. Verified: fresh snapshot at startup, no storms. |
| P0-2 | Live pass in-memory per-cycle symbol guard (`_live_symbols_submitted_this_cycle`). Added the instant `execute_signal` returns, BEFORE the DB write — closes the MU×4 duplicate window where a failed order-row write (DELL-orphan path) let strategies 2..N re-fire. |
| P0-3 | Partial unique index `uq_open_pos_strategy_symbol_acct (strategy_id, symbol, account_type) WHERE closed_at IS NULL`. DB-level enforcement of one-open-position-per-pair (was code-only; had already failed → PLATINUM demo ×2). Resolved the existing demo dup via pending_closure first. `migrations/migrate_open_position_unique.sql`. |
| P0-4 | Leveraged-ETF SL: removed the dead FIX-03 4% cap (it was silently overwritten by the ATR floor → TQQQ/SOXL actually got up to 20% stops; forcing 4% guarantees noise-stopouts on a 3× ETF). Risk is bounded by the 0.5× sizing (kept) + small CIO size + ATR-realistic stop clamped at the leveraged cap. Canonical leveraged set now in `sl_caps.is_leveraged_etf` (was duplicated 4× with drift). **NEW-07 escalated**: 3× ETFs are still the wrong instrument for a medium-term live book — CIO decision to retire TQQQ/SOXL from live. |

### P1 (all deployed)
| Fix | What |
|---|---|
| P1-1 | Balance gate (FIX-B) corrected: pending = sum of ENTRY-order `quantity` (already dollars), no `× price`. Old formula computed $21.8M pending for a $3K index order → `max(0,…)`=0 → `>0` guard → silent no-op. |
| P1-2 | `_fetch_historical_from_fmp` now delegates to `fmp_ohlc.fetch_klines` (correct `/stable/historical-price-eod/full` + SYMBOL_MAP) instead of the legacy `/api/v3/historical-price-full` (empty on Starter). Fixes the dead LME/forex FMP primary path (FIX-D part 2). |
| P1-3 | `live_trade_count` now atomic `UPDATE … SET col = col + 1` in both order_executor + order_monitor (was read-modify-write → lost updates; needed the Sprint-13 backfill). |
| P1-4 | Zombie exits no longer auto-close LIVE positions — LIVE candidates logged `[ZombieExit][LIVE-REVIEW]` WARNING for CIO; demo keeps auto-flag. (Real-money exits are a CIO decision, not a demo-tuned gate.) |
| P1-5 | D1/D2 freshness now measured in BUSINESS days (`_business_days_stale`) — kills the weekend/overnight false-positive storm; still catches genuine multi-day gaps. |
| P1-6 | `signal_decisions` stage-aware prune (`prune_old(30)`) now CALLED in `_run_daily_sync` (was "manual schedule TBD" — audit rows had grown to 44d). |
| P1-7 | A1 (BACKTESTED-0-signals) downgraded P1→P2 — it was 213 of 244 P1s, burying real P1s. RESEARCH-stage, not a capital risk. |
| P1-8 | Intel auto-resolution: findings not re-seen in a clean run are auto-resolved (guarded — skipped if any check raised). Fixes the write-only-log accumulation. Plus E5 balance-exclusion broadened to any amount. |

Intel changes (P1-5/7/8) take effect on the next `/intel/run`; P1-6 prune runs on the next daily sync.

**Intel validation (run 21:20, post-deploy) — CONFIRMED:** open P1 244→1 (only A7 remains, a real finding), P2 14→169 (A1's 156 reclassified here), 104 stale findings auto-resolved. D1/D2/E5/B4 false positives gone; genuine findings (G5 COPPER, G9) persisted — no over-resolution. Run clean in 70s. All observability fixes verified live.

### Verified resolved during audit (no action needed)
- No dual `risk_manager` / `monitoring_service` files (only `src/risk/risk_manager.py`, `src/core/monitoring_service.py`).
- WF `(test−train) ≤ 1.5` consistency gate wired on all 3 paths (primary/test-dominant/relaxed-OOS).
- MQS null snapshot fixed (showing 52.8/normal).
- historical_price_cache duplicate-bar constraint working.
- Startup demotion properly guarded (60-min fill + 24h trade cooldown).

### Still open (deferred — trading/CIO decisions, not code)
- **NEW-07 (CORRECTED — do NOT retire)**: TQQQ/SOXL live performance is positive, not broken. SOXL live: 4 trades, +$868, 50% WR, +15.8% avg (one +46% hold). SOXL demo: 102 trades +$8,948. TQQQ demo: 80 trades +$7,530 (TQQQ has 0 live trades yet). The genuine defect was the dead 4% SL cap (now fixed). Action: **monitor** via G5 divergence as live_trade_count accumulates; the +46% trade means SOXL's live edge is promising but n=4 (not yet proven). Revisit only if G5 shows decay.
- **P1-9 / G5 (genuine retirement candidate)**: COPPER live diverging hard from WF — RSI Midrange COPPER live −2.37 vs WF 1.72; Dual MA Volume Surge COPPER −3.58 vs 1.37. Real-money underperformance. Recommend CIO review for retirement.
- 423 silent `except: pass`/`logger.debug` handlers (28% of all) — systemic; lint rule + targeted audit recommended.

---

## SESSION 2026-06-10 — SPRINT 13: POST-CRASH AUDIT + DEEP FIXES

### Context
Platform ran unattended for 7+ days. Two market crashes (Jun 5 and Jun 9). Full forensic audit via Intel page + DB queries. System had fundamental issues that prevented crash response. All are now fixed.

---

### SPRINT 13a — Crash Audit Fixes (commit `2ba01e0`)

| Fix | What |
|---|---|
| FIX-01 | Intraday circuit breaker — LIVE only, halts new entries if equity drops >1.5% in 2h |
| FIX-03 | Leveraged ETF rules — SOXL/TQQQ/UPRO: 4% SL cap, 0.5× sizing on LIVE entries |
| FIX-04 | `_check_fundamental_exits` uses isolated session + explicit rollback (InFailedSqlTransaction) |
| FIX-05 | Guard `pending_*` etoro_position_id before close — force sync, CRITICAL log if unresolvable |
| FIX-06 | Intraday stress flag — SPY open→current < -1.5% logs WARNING each cycle |
| FIX-07 | TSL minimum lock buffer — 0.5× ATR min distance prevents noise-level breaches |
| FIX-08a | SHORT signal priority queue — SHORTs evaluated before LONGs for demo balance access |
| FIX-08b | activation_approved BACKTESTED bypass — newly-approved strategies bypass interval filter |
| FIX-09 | Live equity staleness watchdog — CRITICAL + force-resync if LIVE snapshot >60min stale |
| FIX-10 | FRED rate limit backoff — 429 detected → 300s backoff, no retry storm |
| FIX-11 | DB-computed balance gate — `equity-invested-pending` replaces eToro spot credit |
| FIX-14 | Removed stale `market_regime: trending_up_strong` from May 18 in autonomous_trading.yaml |
| FIX-15 | Fixed `MACD().shift(1)` DSL syntax → `MACD() CROSSES_ABOVE MACD_SIGNAL()` |

### SPRINT 13b — Intel Findings Fixes (commit `581362d`)

| Fix | What |
|---|---|
| Intel-A2 | SQL now compares `opened_at > pending_retirement_at` (false positive fix) |
| Intel-A3 | `live_trade_count` uses isolated session in order_monitor + backfilled 162 strategies |
| Intel-A4/G9 | WF primary path consistency gate `(test-train ≤ 1.5)` added; 24 regime-luck strategies retired |
| Intel-E5 | E5 no longer flags market-condition gates (pullback/MQS/drawdown) as permanent loops |
| Intel-A10 | Overtrading check counts entry orders only, not exits |
| Intel-C2 | Real portfolio heat formula (invested×SL_pct/equity), downgraded to P2 for paper |
| Intel-F7 | Yahoo batch download: 3-attempt retry with 5s/25s backoff |
| Intel-F7 | FRED: 429 → 300s backoff (commit `df4b0d9`) |
| DB cleanup | `signal_decisions`: pruned 294k stale rows (70%), added composite index `(strategy_id, stage, timestamp)` |
| DB cleanup | 24 regime-luck strategies retired directly in DB |
| DB cleanup | Backfilled `live_trade_count` for 162 strategies from filled orders |

### SPRINT 13c — P1 Improvements (commit `2b44eee`)

| Fix | What |
|---|---|
| NEW-01 | Intraday regime detection: MQS grade capped at "normal" if SPY intraday <-1.5%, forced "low" if <-2.5% |
| NEW-02 | Live SL/TP regime multiplier: tightens stops at signal time (0.75× mild, 0.60× severe) |
| NEW-03 | TSL activation lower for LIVE: 3% stock (vs 5% paper), 1.8% breakeven (vs 3% paper) |
| NEW-04 | Retirement gate: `min_live_trades_before_evaluation: 3` (was 5); dollar-loss threshold 30% of CIO size |
| NEW-05 | COPPER live SL fixed: 6% → 4% (commodity). Graduation gate validates SL vs asset-class max |
| NEW-06 | `signal_decisions` stage-aware retention: 14d for high-volume diagnostic stages, 30d for audit stages |

### Pullback Gate Recalibration (commit `b1b8481`)

**Root cause of system sitting idle with $364K free balance and 302 BACKTESTED strategies:**
- Mild pullback (-1.4%, RSI 36) was blocking ALL trend entries — 172 blocks per cycle
- 228/302 strategies are trend_following — the gate was blocking 75% of the universe on routine weekly oscillation
- Keyword match `'trend'` caught nearly every template name

**Fix:** Severity-aware blocking:
- **Mild** (-1% to -2%): only block intraday/aggressive templates (breakout, momentum, ATR dynamic)
- **Moderate** (-2% to -3.5%): block intraday + broad trend (EMA ribbon, ADX)
- **Severe** (>-3.5%): block all trend LONGs (unchanged)

Daily trend strategies now correctly enter on mild pullbacks — that's when they're supposed to.

### Live Session Corruption Fixes (commits `7d0aae4`, `28911e1`, `42aa454`)

**Root cause identified:** `InFailedSqlTransaction` cascade. The FMP call at 12:37 UTC leaves the shared DB session in an aborted state. All subsequent queries in the same session fail silently or raise. This caused:
1. DELL orphan position (Jun 10 10:43) — live order committed to eToro but DB write failed
2. PANW triple-position — duplicate guard read stale/no data, 3 separate entries placed

Three layers of defense deployed:
1. **Live order write**: isolated session (can't be rolled back by main cycle exceptions)
2. **Duplicate guard**: isolated session (always reads fresh position data)
3. **Root fix** (`database.py`): `get_session()` now calls `session.rollback()` on checkout — aborted transaction state is cleared before any caller sees the connection. Cost: 0.1ms. Also added `session_scope()` context manager for new code.

---

### Operational Changes

**Live account updated:**
- Real investment: $1,000 → $1,300 (added $300 to Agent Portfolio)
- Mirror ratio: 0.10 → 0.127 (recalculated as $1,300 / $10,239 virtual equity)
- UI now shows correct real equity (~$1,300)

**PANW duplicate positions closed:**
- Closed: `3473111498` (Jun 8 entry $267.83, -$7) and `3476155097` (Jun 10 13:33 entry $258.75, +$21)
- Kept: `3476115401` (Jun 10 13:16 entry $255.2, breakeven stop, +$39)

---

## CURRENT SYSTEM STATE (2026-06-11 end of session)

- **DEMO equity:** ~$533K | **Open positions:** ~75 PAPER | **Deployed:** ~$282K (deploying again after the pullback deep-oversold exemption; was idle ~$300K free)
- **Regime:** moderate pullback (SPY 5d −2.9%, RSI(5)=18, deeply oversold)
- **LIVE strategies:** ~11 active — AMD, DELL, INTC, MU×4, PANW, SOXL, TQQQ, XLK. (GOOGL, TXN, COPPER RETIRED 2026-06-11; SOXL RE-GRADUATED.)
- **LIVE equity:** ~$10,260 virtual / ~$1,300 real | **Mirror ratio:** 0.127
- **LIVE open positions (reconciled to eToro):** PANW ($1,000v original) + AMD (re-entering at approved $100r after reposition). Verify next session that AMD re-entered at $100r and the book matches eToro.
- **BACKTESTED strategies:** ~301 (approved; emitting 5–9K signals/day — NOT idle/broken)
- **Pullback gate:** ACTIVE (moderate) — blocks intraday/momentum + broad trend, BUT exempts daily trend-following when RSI(5)<20 (deep-oversold buy-the-dip, evidence-based).
- **Latest commits (2026-06-11):** `2679ec3` (Sprint B graduation rigor) → `65f1e9a` (Sprint C P2) → `503a39f` (Sprint D Intel A1/A6) → `fa8ec84` (A1 interval + size-estimate fix) → `8474f3e` (retire→flag closure) → `da3f032` (F31+A2+A4+A1-doc) → `91e148d` (A1 phase1 + phantom-exposure fix) → `3c4dc42` (pullback deep-oversold exemption) → `f34acb3` (REVERT P1-1 min, honor CIO size) → `54fca40` (live incident docs)
- **eToro vs DB vs UI:** all three diverged today (account.py cross-account close bug) — now reconciled + fixed. ALWAYS reconcile live 3-way (see steering).

---

## SESSION 2026-06-10 — POST-SPRINT-13 VERIFICATION FIXES (commit `8f733c2`)

Full post-deploy verification run confirmed all 10 Sprint 13 checks. Five
remaining issues identified and fixed:

| Fix | What |
|---|---|
| FIX-A | E5 gate-loop check: `MAX(reason)` → `ARRAY_AGG(DISTINCT reason)`. Old code picked lexicographically largest reason, so "Insufficient balance: $0" masked "Pullback gate" and skipped the filter. Now checks ALL reasons; strategy only flagged if ≥1 is structural. Added transient-balance ($0 settlement window) and symbol-cap to the temporary-exclusion list. |
| FIX-B | DB balance formula: pending order deduction used `quantity` (shares) not `quantity × price` (dollars). 50 shares at $396 was deducted as $50. Now uses `expected_price` with fallback to `price`. |
| FIX-C | EEM ADX retired in DB (`ADX Trend Following EEM LONG` → INVALID). G9 finding: -57838% degradation. Slipped Sprint 13 batch because A4 and G9 use different degradation metrics. |
| FIX-D | ALUMINUM/ZINC FMP routing: (1) `fmp_ohlc.SYMBOL_MAP` now maps ALUMINUM→ALIUSD, ZINC→ZNUSD. Added ALIUSD/ZNUSD intraday to `EXPLICIT_BLOCKED` (LME metals are EOD-only on FMP Starter). (2) `market_data_manager` LME/forex primary path was passing `normalized_symbol` (Yahoo wire form `ALI=F`) instead of `db_symbol` (display form `ALUMINUM`) to `_fetch_historical_from_fmp` — bypassed SYMBOL_MAP entirely, fell through to thin Yahoo data silently. Root cause of ALUMINUM 1d bars being 162h stale. |
| FIX-E | `VACUUM ANALYZE signal_decisions` + `strategies`. Reclaimed dead tuple bloat from Sprint 13's 294K row deletion. |

**Note on signal_decisions disk size:** VACUUM ran successfully. `pg_relation_size` (live data) = 262 MB, `pg_total_relation_size` (including indexes/toast) = 398 MB. Size has not shrunk because VACUUM marks pages as reusable but does not return them to the OS — that requires `VACUUM FULL` which locks the table. The live data is 262 MB which is correct for 130K rows. No further action needed; new rows will use reclaimed pages.

---

## OPEN ITEMS (P1/P2)

### P2 — This Month
- **NEW-07**: TQQQ in live book — review whether 3× leveraged ETF belongs in medium-term strategy. FIX-03 applies 4% SL / 0.5× sizing but may still be wrong instrument.
- **NEW-08**: `cancel_stale_orders` 404 dead end — after 404 on cancel, schedule 4h re-check; if still PENDING + no fill, mark CANCELLED.
- **NEW-09**: `backtested_ttl_cycles: 168` — review whether 72 is more appropriate (currently 3.5 days, effectively 10.5 days for 4H).
- **NEW-10**: TSL breach enforcement — add price freshness check before breach evaluation (stale `current_price` can cause missed or ghost breaches).

### Architecture (no rush)
- **G-01**: WF test-dominant consistency gate (already partially added in Sprint 13)
- **G-09**: Correlation dedup at graduation approval (LIVE only) — already removed from concern given multi-strategy-per-symbol is intentional
- **G-19**: Real slippage model from trade_journal data

---

## KEY NUMBERS TO TRACK NEXT SESSION

When checking logs/DB next session, verify:
1. **ALUMINUM 1d data fresh** — after next price sync, confirm `historical_price_cache` has recent ALUMINUM 1d bars from FMP (ALIUSD). Check errors.log for "FMP (forex/LME primary)" log line.
2. **E5 Intel count near zero** — run fresh Intel scan; E5 should show 0 after ARRAY_AGG fix.
3. **Demo orders executing** — moderate pullback should resolve; once SPY 5d return moves above -2%, daily trend strategies should start submitting orders again.
4. **signal_decisions size stable** — 130K rows / 262 MB live. New retention policy should keep it from growing back.
5. **FIX-B in effect** — if any PENDING orders exist during settlement, confirm balance log shows `invested + pending_dollars` not `invested + pending_shares`.

---

## SESSION 2026-05-25 — (earlier history below, unchanged)

### Trade Journal Integrity Fix
`log_exit` fallback had no account_type filter — corrupted demo/live P&L separation. Fixed commit `f79fbec`. 0 mismatches after fix.

## SESSION 2026-05-18 — Watchlist Elimination
Every strategy is now a single (template, symbol) pair. Commits `e70a2f5`, `3bd873f`, `b291073`. 0 multi-symbol strategies remaining.

## SESSION 2026-05-17 — G-43 + G-44/G-45 + P1 Batch
- G-43: Paper conviction threshold 60/55 (was 73/67) — commit `b1378e1`
- G-44/G-45: LIVE pass wired to full risk framework — commit `8d07eef`
- P1 batch: G-46/G-48/G-50 PAPER gate relaxations — commit `c158650`

## CURRENT LIVE STRATEGIES (as of Jun 10)
14 LIVE strategies. All trend-following. All LONG. No shorts yet in live book (graduation pipeline needs more short paper trades to accumulate).

| Strategy | Symbol | CIO Size | SL | Status |
|---|---|---|---|---|
| EMA Ribbon Expansion Long DELL LIVE | DELL | $100r | 6% | open |
| 4H EMA Ribbon Trend Long MU LIVE | MU | $100r | 6% | open |
| 4H Strong Uptrend Momentum MU LIVE | MU | $100r | 6% | no position |
| ATR Expansion Breakout MU LIVE | MU | $100r | 6% | no position |
| Triple EMA Alignment MU LIVE | MU | $100r | 6% | no position |
| Dual MA Volume Surge COPPER LIVE | COPPER | $100r | **4%** (fixed) | open |
| EMA Trend Following PANW LIVE | PANW | $100r | 6% | open (1 position) |
| EMA Ribbon Expansion Long TQQQ LIVE | TQQQ | $100r | 6% | no position |
| 4H EMA Ribbon Trend Long SOXL LIVE | SOXL | $100r | 6% | no position |
| Keltner Channel Breakout TXN LIVE | TXN | $100r | 6% | no position |
| ADX Trend Following INTC LIVE | INTC | $100r | 6% | open |
| 4H EMA Ribbon Trend Long XLK LIVE | XLK | $100r | 6% | no position |
| Triple EMA Alignment MU LIVE | MU | $100r | 6% | no position |
| 4H EMA Ribbon Trend Long GOOGL LIVE | GOOGL | $100r | 6% | no position |
| EMA Trend Following AMD LIVE | AMD | $100r | 6% | open |
