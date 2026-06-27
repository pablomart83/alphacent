# AlphaCent — Session Continuation

> Permanent rules are in `.kiro/steering/trading-system-context.md`. This file holds current system state, recent fixes, and open items.

---

## ⚡ NEXT SESSION KICKOFF

**SESSION 2026-06-27 (Auto) — WEEKLY AUDIT of the 9 changes shipped 06-20→27. Read-only review; nothing changed. Full report: `AUDIT_REPORT_2026-06-27.md`.**

**Verdict: all 9 changes deployed and behaving as designed; no regressions. The week was a LOSING week driven by a market pullback (SPY ~−3.4%, regime flipped trending_up_weak→ranging_low_vol), NOT by the changes — and the TSL retune (#6) mitigated the give-back. The confirmed-uptrend has ENDED, so #7/#8 are now correctly inert and their uptrend-calibrated evidence is temporarily stale.**

Per-change status (evidence in the report):
- **#1 meta-label** — re-proof re-run live (3,531 trades): stocks AUC 0.513, etfs 0.542, rest <0.4; all NO EDGE. Not imported on any hot path, no persisted model. DEPLOYED & CORRECTLY DORMANT. Don't revisit.
- **#2 scoreboard** — snapshot fresh (19:06 today), off request-path, reload-on-newer works. Conviction=HELPS still; Pullback now `insufficient_data` (blocks collapsed 16k→652). Passed-cohort fwd return flipped +6.13%→**−1.57%** (caught the pullback). `account_type` populates on signal/gate stages; minor gap: NULL on `order_filled`/partial `order_submitted`. WORKING.
- **#3 recommender** — pending clean (ENPH/MU + new CAT/XLK/2 ETF tightens); no dup pending; ADX/Keltner NOT re-appearing (45cc670 works); SOXL no-rec. New recs are aggressive tightens (1–4% SL) — do NOT bulk-approve. WORKING.
- **#4 DSR** — observe-only firing every cycle, NOT rejecting. **would-filter = 0 EVERY cycle at min_dsr=0.9** → enabling is a no-op (redundant with MC). Recalibrate higher or shelve; do NOT flip enabled at 0.9.
- **#5 approval rail** — overrides match (ADX 9%, Keltner 7.94%, AMD live 7.5%), one active/scope, revert works. Binding PROVEN LIVE (resolve_override + strategy "ADX Trend Following C LONG" 06-23 carries SL=0.09/TP=0.225). WORKING. (No recent binding log = rotation + no ADX/Keltner stock strategy persisted 06-24→27.)
- **#6 TSL retune** (deployed 06-23 15:39 UTC) — give-back HALVED: PRE n=92 MFE+5.09%/realized−1.60%/win26%/51 peaked-then-loss → POST n=80 MFE+2.72%/realized−0.69%/win36%/25. errors=0/3,900 cycles. No whipsaw spike. Confound: short post-window in weaker regime. WORKING; re-measure after an uptrend leg.
- **#7 pullback exemption / #8 live softening** — DEPLOYED but INERT BY REGIME (regime left confirmed-uptrend → never fired; correct). Unproven-live; capture first firings next uptrend before relaxing further.
- **#9 20% cap** — WORKS: pre-fix 15% blocks all on 06-23, none after; live cap now 20% (`symbol_cap_exhausted` $2073); demo unchanged. FINDING: **MU 3 open live positions ~$2,362 ≈ 23% > 20% cap** (cumulative-enforcement gap across cycles), all underwater.

Performance (06-20→27): DEMO **−$4,047** (594 trades, 36.4% win) vs prior +$10,795 (278, 48.9%); LIVE **−$116** (5 trades) vs +$98. DEMO equity −4.4%, LIVE −5.7% (mostly unrealized). Pullback-driven. Live book net-negative lifetime (~−$560; only PANW +$187).

Errors (none from the 9 changes): (a) daily fundamental-exit `InFailedSqlTransaction` ~12:36 — sector-rotation `pending_closure` on aborted session, **silent failure**, pre-existing back to 06-01, **needs session_scope fix (P1)**; (b) 06-22 00:15 UniqueViolation burst ×13 = restart/reconcile A3 cascade, self-resolved, demo-only; (c) size-estimate endpoint `Position.__init__()` broken (strategies.py:4538), not hot path; (d) SPY weekend 1h errors only 06-21/22, none 06-27 (last week's fix holding).

**CIO TODO (decisions, not code):** (1) trim/monitor live MU (23% concentration into a ranging regime); (2) approve MU SL widen if desired, HOLD the aggressive tighten recs (ENPH/CAT/XLK/ETF) until re-evaluated outside the pullback; (3) DSR — recalibrate min_dsr or shelve, don't enable at 0.9; (4) re-validate #6/#7/#8 in the next uptrend.

**FIXES SHIPPED THIS SESSION (deployed + verified + pushed, commits `fedd078`/`d1b3bca`/`853e44a`/`c3bb9a9`):**
- **Fundamental-exit `InFailedSqlTransaction` (root-caused + fixed).** Root cause was NOT a generic session issue: `regime_history.regime_changed` is an Integer(0/1) column and the stability query used `== True`, which on Postgres errors `operator does not exist: integer = boolean`, aborting the txn; the `except` swallowed it without rollback and defaulted `regime_stable=True`, poisoning the session so the daily 12:36 `pending_closure` commit always failed. Fixed `== 1` + `session.rollback()` in except + default `regime_stable=False` on error. **Behavior resumption:** sector-rotation fundamental exits will now actually persist on profitable positions when the regime has been stable ≥3d. Live book currently holds no XLY/XLV/XLE so live is unaffected; mainly affects the demo sandbox. Verified: `regime_changed = 1` query now executes; service healthy; no new errors. (Next natural exercise: 12:36 UTC daily run.)
- **`account_type` threading** on `order_submitted` (order_executor) + `order_filled` (order_monitor) decision writers — scoreboard funnel rows will no longer be NULL for those stages. (Runtime confirmation pending market open / next fills.)
- **Size-estimate endpoint crash** — `Position(...)` was missing `realized_pnl`/`opened_at`/`etoro_position_id`; added. (`strategies.py` get_size_estimate.)
- **#6 stale TSL docstrings** corrected to the deployed retune values (comments only).
- NOT changed (CIO decisions, not bugs): MU concentration, DSR enable, SL/TP rec approvals.

---

**SESSION 2026-06-23 (Auto) — TIER-1 ALL SIX RECOMMENDATIONS SHIPPED: price-history features (meta-label re-proof STILL negative), per-gate observability scoreboard, MAE/MFE→SL/TP recommender, DSR gate (observe-only), full Path-A approval rail + frontend. Deployed, verified, pushed across 6 commits. One change → deploy → verify discipline throughout.**

Executed the prior session's recommended next steps end-to-end. Headline: the meta-label veto is conclusively dead, but the OTHER work (gate scoreboard + MAE/MFE recs + DSR + approval rail) is real, deployed value. **Nothing auto-applies to live — recommendations are proposals; the DSR gate is observe-only; approvals are CIO-gated via the rail.**

### 1. Price-history features → meta-label re-proof (commit `acdb693`..ml1.1.0) — HONEST NEGATIVE, leave disabled
Added 12 pre-entry OHLC features to `src/ml/meta_label_trainer.py` (`build_price_features`: `ph_n_bars`, dir-signed `ph_mom_5/10/20`, `ph_dist_sma20/50`, `ph_sma_slope_10`, plus `ph_realized_vol_20`, `ph_atr_pct_14`, `ph_rsi_14`, `ph_range_pos_20`, `ph_gap_last`). `FEATURE_SPEC_VERSION` ml1.0.0→**ml1.1.0**; train/serve parity preserved (`build_price_features` is pure, used by both paths; `ctx_from_trade` passes `price_history`). Verified `price_history` ends at entry (median |last_close−entry|=1.25% vs first 25.8%) — no leakage.
- **Re-proof on EC2 (3531 trades):** stocks AUC **0.463** (lift −0.050, sep −0.0046 — blocks winners); etfs AUC **0.488** (lift −0.032, sep −0.0023); commodities/indices tiny-n AUC<0.4; forex/crypto SKIP (n<120). **Two independent feature enrichments now both at/below random.** Conclusion: the meta-label-as-veto has no edge — almost certainly because the conviction components are already the entry gate and the strategies are already WF/MC-validated, leaving no residual signal. **Do NOT wire shadow/enforce.** Meta-label state-grid frontend is moot. `scripts/verify_meta_label_edge.py` re-runs it.

### 2. Per-gate observability scoreboard (commits backend+frontend) — DEPLOYED, the high-value finding
`src/analytics/gate_scoreboard.py` measures, per canonical gate, the **direction-aware N-bar forward return of the signals it BLOCKED vs the cohort that PASSED all gates** (apples-to-apples counterfactual from `historical_price_cache`, since blocked signals never trade). `separation = passed − blocked`; positive ⇒ gate blocks worse signals (helps), negative ⇒ blocks better signals (hurts). Capacity gates (balance/dedup/exposure) labelled `capacity` (they don't predict quality). Precomputed in `_run_daily_sync` + manual recompute — never on the request path. Snapshot cached to `config/.gate_scoreboard.json`.
- Added `signal_decisions.account_type` (additive column + index, live ALTER) + threaded through all decision writers (demo/live verified populating).
- Endpoints: `GET /analytics/observability/gate-scoreboard` (instant, cached), `POST .../recompute`. Frontend: **GateScoreboard panel in Guard → Gates tab**. Proof: `scripts/verify_gate_scoreboard.py`.
- **FINDINGS (14d, 40k forward-returns; gross returns are regime-inflated in this uptrend, so read SEPARATION not level):** DEMO passed cohort +6.13% 5d-fwd / 81% win. **Conviction threshold HELPS** (sep +0.024 — blocks +3.7% signals while passing +6.1%). **PULLBACK gate HURTS** (sep −0.0043; it's the biggest blocker at 16k blocks and blocks signals averaging +6.6% vs +6.1% passed — i.e. blocking winners in this regime, matching the steering note that it blocks 78–92% of trend LONGs). LIVE volume ~0 in 14d. **→ CIO action candidate: relax/regime-scope the pullback gate; the conviction gate is earning its keep.**

### 3. MAE/MFE → SL/TP recommender (commit) — DEPLOYED, proposals only
`src/analytics/sl_tp_recommender.py` generalises `diagnose_symbol_edge.py` into a daily+manual job. Over closed trades with TRACKED excursions (MAE/MFE are FRACTIONS; only ~451/3538 tracked, since ~May), per **symbol** and per **(template, asset_class)**: WIDEN SL when winners' MAE p75 > current stop or premature stop-outs >15%; TIGHTEN when MAE p90 ≪ stop; RAISE TP when MFE p50 ≫ TP / capture <50%. Bounded by `sl_cap_pct`. Writes `improvement_recommendations` (pending). Endpoints `GET /analytics/recommendations`, `POST .../recompute`; daily in `_run_daily_sync`. Proof: `scripts/verify_sl_tp_recommendations.py`.
- **5 pending recs verified:** AMD widen 6%→7.5%, MU 6%→8.4%, ENPH tighten 6%→1.2%, ADX Trend Following::stocks 6%→9% (cap), Keltner Channel Breakout::stocks 6%→7.9%. **SOXL correctly produced NO rec** (its live SL is already 15% from the prior fix — the engine doesn't re-widen an already-correct stop), validating the SOXL stop logic generalised to the high-vol semis cohort.

### 4. Deflated Sharpe Ratio gate at WF (commit) — OBSERVE-ONLY
In `strategy_proposer` after the MC block: corrects each strategy's OOS test Sharpe for multiple-testing bias using `compute_dsr` (n_trials = combos WF-tested this cycle). Stores `s.metadata['wf_dsr']` ALWAYS (surfaces beside MC p5). **`backtest.walk_forward.dsr_gate.enabled` defaults FALSE** (observe-only): logs "scored N, K would filter, pass-rate B→A" without rejecting. When enabled, removes DSR<min from the pass set; wf_rejected reason distinguishes `dsr_filtered` vs `mc_bootstrap_filtered`. Verified `compute_dsr` discriminates (Sharpe 0.3→DSR 0.24, 0.8→0.93, 1.5→0.999). **Open: calibrate `min_dsr` from the logged distribution before flipping `enabled: true`** (test-Sharpe annualisation vs DSR's assumption is uncalibrated — observe first).

### 5. Approval rail (Path A) + frontend (commits backend+frontend) — DEPLOYED, CIO-gated
- `template_param_overrides` table + `src/analytics/param_overrides.py`: the running proposer reads ACTIVE overrides each cycle (`resolve_override`, cached ~60s) and applies SL/TP bounded by `sl_cap` — **inert until a row exists, no restart, instantly reversible**. Wired via `_finalize_risk_params` (asset-class floors → approved overrides).
- `approve` → envelope-guarded (SL ≤ sl_cap); LIVE pairs update `live_strategies`, else write an active override; `reject`/`revert` with audit. Endpoints `POST /analytics/recommendations/{id}/approve|reject|revert`, `GET .../active-overrides`.
- Frontend: **Recommendations panel in Strategies → Graduation** (evidence + Approve/Reject/Revert + Run-now; LIVE rows tagged). Verified the full apply→resolve→revert cycle on EC2 (left system clean, rec restored to pending).

**WHAT THE CIO SHOULD DO NEXT (decisions, not code):**
1. Review the **gate scoreboard** in Guard — the pullback gate is blocking winners in the current uptrend; decide whether to relax/regime-scope it.
2. Review the **5 SL/TP recommendations** in Graduation and approve the sound ones (AMD/MU/ADX-stocks widen are well-evidenced; ENPH tighten is conservative).
3. Let the **DSR observe-only** log accrue over a few proposal cycles, then set `min_dsr` from the real distribution and flip `enabled: true`.

**Verified live state:** service healthy across all restarts; new tables `improvement_recommendations` + `template_param_overrides` created; `signal_decisions.account_type` populating; no new errors (only pre-existing FMP rate-limit warnings). All read-only proof scripts present: `verify_meta_label_edge.py`, `verify_gate_scoreboard.py`, `verify_sl_tp_recommendations.py`.

---

**SESSION 2026-06-22 (Opus 4.8) — TIER-1 LEARN-FROM-TRADES, STEP 1: META-LABEL PROVE-FIRST FOUNDATION shipped (read-only) + HONEST NEGATIVE EDGE FINDING. Deployed read-only, run on live data, pushed (commit `1286cdf`). NOT wired to any live path.**

Built the prove-first foundation for the meta-label filter and ran it against all realized trades BEFORE any inference/enforcement wiring (per the mandated rollout: train → prove (CV) → shadow → enforce). 

**Shipped (Path B, read-only — no hot-path wiring, no restart):**
- **`src/ml/meta_label_trainer.py`** — per-asset-class meta-label trainer. Single pure `build_feature_row(ctx)` = the train/serve-parity contract (used by both training-from-`trade_journal` and the future serve path); 22 decision-time features (conviction total + 9 conviction-breakdown components + VIX + entry_persistence + direction + strategy_type + regime family + interval + leverage flag + 5 fundamentals). **No leakage** (realized outcomes only build the label, never features). Label = **cost-net profitable** (`pnl_percent/100 − round_trip_cost_pct`, OUR costs, applied uniformly so demo at-quote fills are judged honestly). **Purged + embargoed walk-forward CV** (López de Prado ch.7 — purge train trades whose label window overlaps a test block, plus a count + time embargo). Persists feature spec + train-medians (imputation) + model inside the artifact, version-pinned (`ml1.0.0`) so a stale serve artifact is refused, not silently mis-served. In-memory `MetaLabelModel.predict_proba(ctx)` + `load_model(asset_class)` for the eventual serve path. `MIN_CLASS_SAMPLES=120`, `MIN_MINORITY_SAMPLES=25` → a class with too little data gets no model (disabled by construction).
- **`scripts/verify_meta_label_edge.py`** — read-only proof: per-asset-class OOS precision/recall/F1/AUC vs base rate, calibration bins, feature importance, and a held-out ECONOMIC backtest (trade-everything vs enforce(P≥.5) vs prob-sized, cost-net) + blocked-vs-passed cohort separation. `--persist` to write `.pkl` (NOT used — no edge to persist).

**HONEST VERDICT — the meta-label model has NO clear OOS edge with the current feature set. Leave it disabled.** Proof run on EC2 against 3,458 closed trades (3,402 demo / 56 live; cost-net labels):
| asset class | n | base WR | OOS precision | LIFT | AUC | trade-all net | enforce net | blocked vs passed sep |
|---|---|---|---|---|---|---|---|---|
| stocks | 2103 | 0.374 | 0.328 | **−0.046** | **0.468** | −0.0009 | −0.0019 | **−0.0025 (filter blocks WINNERS)** |
| etfs | 953 | 0.370 | 0.347 | −0.023 | 0.515 | +0.0051 | +0.0002 | **−0.0069 (filtering destroys ETF edge)** |
| commodities | 172 | 0.267 | 0.077 | −0.19 | 0.379 | −0.008 | −0.003 | +0.005 (tiny n) |
| indices | 140 | 0.350 | 0.333 | −0.017 | 0.452 | −0.001 | +0.005 | +0.007 (tiny n, AUC<0.5 — not credible) |
| forex | 51 | — | — | — | — | — | — | SKIP (n<120) |
| crypto | 38 | — | — | — | — | — | — | SKIP (n<120) |

- **Interpretation (quant):** AUC ≤ 0.515 everywhere with adequate data — at/below random. On the two classes with real samples the **would-block cohort realizes BETTER cost-net returns than the passed cohort** (negative separation), i.e. the model would block winners and destroy edge — exactly the "blind filter destroys edge invisibly" failure the brief warns against. Calibration is broken (stocks: predicted-0.55 bin realizes 0.328). Likely cause: the conviction components are ALREADY used as the entry gate, so conditioning on "we chose to trade" leaves little residual signal; what the RF fits is train-base-rate noise that inverse-correlates OOS. Feature density is also moderate — only 65% of trades carry the rich `conviction_breakdown`, 33% have fundamentals (rest imputed to median).
- **Consequence for the rollout:** there is nothing to shadow yet (no edge), and LIVE-enforce would be locked by the shadow-evidence bar's separation criterion regardless. Do NOT wire enforcement. The infrastructure is sound and ready to re-evaluate as the feature set is enriched and more (esp. LIVE) data accrues.

**RECOMMENDED NEXT (re-prioritised by the negative finding — awaiting CIO direction on scope):**
1. **Richest untapped feature: entry `price_history`** (persisted in `trade_metadata` per trade) → pre-entry momentum/vol/structure features, with matching serve-side computation. Highest-value experiment to see if edge exists at all before building any shadow/enforce machinery. *(proper build, train/serve parity required — not a quick tweak.)*
2. **Per-gate observability scoreboard** (build task #5) — extend `signal_decisions` with per-gate seen/passed/blocked + blocked-vs-passed realized forward-edge per account + blocked-signal counterfactual. Independent of the meta-label result and arguably MORE valuable now: it answers "which of our EXISTING gates (conviction, frequency, VIX C1, trend-consistency C3, MQS) help vs hurt." NOT yet measured.
3. **MAE/MFE → SL/TP recommendation job** (build task #2) and **DSR gate at WF** (build task #3) — both INDEPENDENT of the meta-label edge; valuable regardless (MAE/MFE generalizes the SOXL diagnostic).
4. The approval rail (`improvement_recommendations` / `template_param_overrides` / filter-state store) + frontend surfacing are the delivery layer for #2–#3; build once those produce outputs.

**NOTE:** the full Tier-1 brief is a multi-sprint program; one-change→deploy→verify discipline + the negative headline finding mean the enforcement/shadow/approval-rail machinery should follow a confirmed-edge or a confirmed gate-scoreboard need, not precede it. Verified current state (all confirmed live this session): ML filter dormant (`signal_filter.py`, 8 generic features, `train_model()` called by no job); 3,458 closed trades; `trade_journal`/`trade_metadata` schema as documented; `signal_decisions`, `live_strategies`, `graduation_approvals` exist; no recommendations/overrides/filter-state tables yet.

---

**SESSION 2026-06-21 (Opus 4.8) — #5 CROSS-ASSET SIGNAL DSL PRIMITIVE shipped ("trade the noisy instrument, signal off the clean underlying"). Deployed live, healthy, lint-clean, proof-run, pushed. The SOXL/leveraged-ETF program (#1-#6) is now COMPLETE.**

The missing capability: the DSL could reference another symbol's RETURN (`LAG_RETURN`/`RANK`) but NOT its SMA/indicator. Now it can.

**Shipped (proper, generalizable — a real DSL primitive seen by backtest=WF=paper=live, NOT a runtime gate):**
- **`src/strategy/cross_asset_primitives.py` + `trading_dsl.py` — two new cross-symbol primitives:** `EXT_SMA("SYM", N)` (N-day SMA of SYM's daily close) and `EXT_PRICE("SYM")` (SYM's daily close), each fetched on DAILY bars and reindexed/ffilled to the traded symbol's bar index — the SAME look-ahead-safe alignment `RANK_IN_UNIVERSE` already uses (exact same-bar for a daily equity primary; ffill covers missing bars/weekends/daily→intraday). Compose to a cross-symbol trend gate: `EXT_PRICE("SOXX") > EXT_SMA("SOXX", 50)`. External RETURN reuses the existing `LAG_RETURN` (per the design — no new return primitive). Computed identically in both the backtest and signal-gen paths via the existing `_compute_cross_asset_for_strategy` injection (fast-path now also checks `extract_ext_indicator_references`).
- **Sentinel resolution unified across ALL cross-asset primitives** (`resolve_ext_symbol`): a literal ticker ("SPY"), `"SELF"` (the primary), or **`"UNDERLYING"`** (the leveraged ETF's clean 1x underlying) all resolve at FETCH time; the indicator KEY keeps the literal string so codegen↔compute agree. `LAG_RETURN`/collect-required now resolve `UNDERLYING` too (was SELF-only) — so `LAG_RETURN("UNDERLYING", 20, "1d")` reads the underlying's 20d momentum and the prefetch loads SOXX/QQQ (not a literal "UNDERLYING").
- **Underlying map** (`src/risk/sl_caps.py` `underlying_of`, next to the canonical `_LEVERAGED_ETF_SET` — single source of truth): SOXL/SOXS→SOXX, TQQQ/SQQQ/QLD→QQQ, UPRO/SPXL/SPXU/SSO→SPY, UDOW/SDOW/DDM→DIA, TNA/TZA/UWM→IWM, TECL/TECS/ROM/USD→XLK, FAS/FAZ→XLF, LABU/LABD→XBI, DFEN→ITA. Every underlying is in `symbols.yaml` so the backtest data path can fetch it.
- **`src/strategy/dsl_lint.py` — lint now runs CODEGEN** (not just parse+tautology), so an unknown indicator or a malformed cross-symbol arg shape (e.g. `EXT_SMA("SPY")` missing its period) fails at LOAD time instead of silently backtesting 0 trades. Verified safe: all 391 existing catalog conditions generate code cleanly. The catalog's `_lint_dsl` validator inherits this automatically.
- **NEW template** `config/strategy_catalog/leveraged_etf.yaml` seq 311 — **"Leveraged ETF Trend (Underlying-Signaled)"**: long the 3x ETF when `EXT_PRICE("SPY")>EXT_SMA("SPY",100)` (risk-on) AND `EXT_PRICE("UNDERLYING")>EXT_SMA("UNDERLYING",50)` (underlying uptrend) AND `LAG_RETURN("UNDERLYING",20,"1d")>0` (underlying momentum) AND `ATR(14)/CLOSE<0.12` (SELF vol ceiling). Exit on the underlying losing its 50d trend. Daily, multi-day hold, best_symbols SOXL/TQQQ/UPRO. Inherits the leverage-aware SL/TP clamp + PAPER size haircut already shipped. No skip flags — normal WF/MC/conviction/graduation.
- **Proof:** `scripts/verify_underlying_signaled_edge.py` (production rolling-WF + cost-net, full history, OUR costs) — see PROOF below.

**PROOF (EC2, rolling-WF test-window cost-net Sharpe, full history):**
| symbol | A) Underlying-signaled (NEW) | B) ADX Trend (SELF) | B) EMA Trend (SELF) |
|---|---|---|---|
| SOXL | **1.13** (9t, ok) | 3.04 (28t, ok) | 2.32 (36t, ok) |
| TQQQ | **0.83** (7t, ok) | 2.50 (12t, ok) | 0.70 (21t, ok) |
| UPRO | **0.27** (8t, ok) | 2.46 (5t, ok) | **−0.21 (overfit)** |

**HONEST verdict:** the cross-asset underlying signal is **positive and non-overfit on ALL THREE** leveraged ETFs and is the most *robust/consistent* template (the SELF EMA template is overfit & negative on UPRO), but it does **NOT beat** the already-excellent **ADX Trend Following SELF** template on raw cost-net Sharpe (3.04/2.50/2.46 — the proven top SOXL earner). Its virtue is selectivity (7-9 high-conviction trades vs 28-36) + robustness across the cohort, not peak Sharpe. So: the primitive + underlying-signaled template are sound and now available to the pipeline, but **ADX-SELF daily trend remains the strongest leveraged-ETF edge** — consistent with the prior session's finding. (`diagnose_symbol_edge.py` is a live-trade-journal tool; no before/after delta yet — the new template has not traded.)

**Caches:** no clear needed — the new template has zero prior cache/blacklist entries, and the EXT changes don't alter any existing template's param-keyed WF hash (no existing template uses EXT).

**POST-DEPLOY FIXES (from two live cycle runs, both deployed+verified+pushed):**
1. **`fixed_symbols` not `best_symbols`** (catalog): first cycle proposed the template on SPY/OIL/ASTS/LUNR (generic symbol matching — `best_symbols` is only honored in a few name-keyed scoring branches). On non-leveraged symbols `underlying_of`→None→all-NaN EXT→fail-closed→can never fire. Switched to `fixed_symbols: [SOXL,TQQQ,UPRO]` (authoritative, same mechanism as GOLD/OIL single-symbol templates). Verified next cycle: proposed on `["SOXL","TQQQ","UPRO"]`, one BACKTESTED strategy created, activated.
2. **Per-symbol cross-asset primary resolution** (`strategy_engine._compute_cross_asset_for_strategy` + both call sites): `fixed_symbols` creates ONE multi-symbol strategy `[SOXL,TQQQ,UPRO]`; signal-gen loops all three but the SELF/UNDERLYING sentinels were resolving off `strategy.symbols[0]` (SOXL) for ALL symbols → TQQQ/UPRO would signal off SOXX instead of QQQ/SPY. Added `primary_symbol_override`; signal-gen passes the evaluated `symbol`, backtest passes its `symbols[0]`. VERIFIED: SOXL→SOXX(639), TQQQ→QQQ(740), UPRO→SPY(746). This is a general fix — benefits ANY multi-symbol cross-asset strategy (incl. RANK families). NOTE: a multi-symbol fixed_symbols strategy is still WF-validated only on symbols[0] (SOXL) — the system's standard fixed_symbols behavior; the edge is asserted to generalize across the family (the proof validated all three single-symbol).

**CRYPTO BTC-GATE UNIFICATION — now UNBLOCKED, recommended, NOT done this session (flagged):** the out-of-band runtime gates (`order_executor._check_btc_trend_gate` LIVE-only; `monitoring_service._check_crypto_regime_exits`) — which the steering explicitly calls an anti-pattern (backtest never sees them) — are now expressible in DSL as `EXT_PRICE("BTC") > EXT_SMA("BTC", 50)` on crypto LONG entries (+ the inverse on exits). The data path is proven (crypto templates already fetch BTC daily via `LAG_RETURN("BTC",…)` in backtest). **Plan when done:** add the EXT-BTC gate to the ~30 crypto LONG templates, REMOVE the two runtime gates, clear crypto WF caches (`scripts/clear_crypto_wf_cache.py`), re-run `verify_crypto_trend_edge.py`. Deferred as its own one-change-deploy-verify cycle (touches live code + many templates + re-proof) — the leveraged-ETF deliverable is self-contained and complete.

---

### Earlier 2026-06-21 — GENERALIZED the SOXL leveraged-ETF learnings across the book (CIO-approved "all of it"). Deployed live, healthy, pushed. Items #1-#4 + #6 done; #5 now also done (above).

After the SOXL leveraged-ETF fix, asked whether the learnings generalize. **They do — verified against the book:**
- **Book-wide, win-rate rises monotonically with hold** (<1d 34% → >7d 68%, +4.39%/trade). But intraday is NOT broadly bad (4h book-wide is net +$9.6k) — so the daily-only rule is correctly scoped to the high-vol cohort, NOT all intraday.
- **The SOXL "sub-day bleed / multi-day win" signature recurs across a HIGH-VOLATILITY cohort.** `scripts/diagnose_symbol_edge.py --scan` surfaced **19 names** (SOXL −$2,773, MU −$1,509, AMD −$1,372, AVGO, SOXX, ARM, SMH, TQQQ, ADI, TXN, HUT, …) bleeding **~$11k** on <1d holds while earning strongly on ≥3d holds.
- **Calibrated vol separator:** annualized realized vol ~40% (≈0.025 daily stdev) cleanly splits the cohort (SOXL 135%, MU 82%, AMD 70%, AVGO 50%, SMH 40%) from normal names (MSFT 32%, AAPL 23%, SPY 14%).

**Shipped (generalize the leveraged-ETF policy to leverage OR high-vol via a new shared classifier):**
- **`src/risk/volatility_classifier.py` (NEW):** `is_high_vol(symbol)` — reads the daily-stdev (`volatility`) the proposer already persists to `config/.market_stats_cache.json`, threshold 0.025 (≈40% ann), in-process TTL-cached, fail-safe. Companion to `sl_caps.is_leveraged_etf`.
- **#1 anti-churn (generalized):** `strategy_proposer._is_daily_only_symbol` = leveraged OR high-vol → skipped on 1h/4h templates (daily-only). Removes the cohort's sub-day loss bucket. (Verified: SOXL/MU/AMD/AVGO/ARM/TQQQ daily-only; MSFT/AAPL/SPY/GLD unaffected.)
- **#2 stops (generalized):** proposal SL/TP clamp now 3-tier — leveraged 8-20%/12-45%, **high-vol 5-15%/8-35%**, normal 1.5-12%/3-30%. So high-vol names (MU/AMD/semis) get ATR room instead of a 12% noise-stop, and backtest matches live.
- **#3 paper sizing (generalized):** PAPER flat-size ×0.5 haircut now applies to leveraged OR high-vol (was leveraged-only) — representative graduation data, bounded $ risk.
- **#4 backtest↔live consistency AUDIT (done, read-only):** `per_symbol` cost overrides ARE read by the backtest (fixed 2026-05-03); vectorbt **simulates SL/TP** (so the clamp fix reaches WF); the two known mismatch classes (crypto cost, leveraged SL clamp) are fixed. Residual flag: graduation snapshots a per-pair `sl_pct` that can drift from current proposer logic (minor).
- **#6 diagnostic (NEW):** `scripts/diagnose_symbol_edge.py [--symbol X] [--scan]` — hold-period buckets + exit-reason + MAE/MFE capture + book-wide churn-cohort scan. The reusable form of the analysis that cracked SOXL.

**STILL TO DO — #5 cross-asset signal DSL primitive (the big build):** ✅ **DONE** (see the kickoff section at the top of this file — `EXT_SMA`/`EXT_PRICE` + `UNDERLYING` sentinel + underlying map + leveraged-ETF template + proof, shipped 2026-06-21).

---

**SESSION 2026-06-21 (Opus 4.8) — SOXL / LEVERAGED-ETF trading-edge fix (CIO-approved). Deployed live, healthy, pushed.**

Analysed SOXL (3x leveraged semis, graduated LIVE) end-to-end vs live+demo+backtest data. **The edge is real and large but we were bleeding it on churn + plain-ETF risk handling.** Verified findings:
- **P&L by holding period (demo+live):** <1d hold = 69 trades, 22% win, **−$2,831**; 1-3d = +$939; 3-7d = 23 trades, 78% win, **+$7,118**; >7d = 6 trades, 83% win, **+$4,877**. The entire edge is in ≥3d trend holds; sub-day trading is a pure loss bucket.
- **MAE/MFE (last 60 demo):** avg favorable +10.2% vs avg realized −0.67% — we gave back essentially the whole move.
- **Live:** one 8-day hold made +46%/$927; the rest were quick re-entries that churned or stopped at −12.6%.
- **Root causes (code-verified):** (1) `is_leveraged_etf`/`sl_caps` existed but the **proposal/backtest SL clamp hard-capped SL at 12% for everything**, while LIVE allowed the 20% leveraged cap → WF validated a DIFFERENT (tight-stop) strategy than we trade; on a 3x (~6-10% daily ATR) 12% is <1.5x ATR = guaranteed noise-stopout (the `Max loss exceeded: -12% (2x SL of 6%)` cluster). (2) **No vol/leverage-aware sizing in PAPER** — flat $2,000 on a 3x. (3) **No anti-churn** — 4H templates re-entered and whipsawed.

**Changes shipped (generalizable to all leveraged ETFs — SOXL/TQQQ/SPXL/SOXS/… via `src.risk.sl_caps.is_leveraged_etf`):**
- **`strategy_proposer.py` — leverage-aware SL/TP clamp:** leveraged ETFs now clamp SL to 8–20% (matches the live `sl_caps` 0.20 cap) and TP to 12–45%, so backtest/WF/paper validate the SAME wide-stop strategy live trades. Non-leveraged unchanged (1.5–12% / 3–30%).
- **`risk_manager.py` — PAPER leveraged-ETF size haircut (×0.5):** mirrors the LIVE FIX-03 0.5x so a wider (correct) stop doesn't carry full notional and paper data is representative for graduation. Dollar risk bounded.
- **`strategy_proposer.py` — anti-churn (daily-only):** leveraged ETFs are skipped on 1h/4h templates at match time (`_is_leveraged_etf_symbol`); they trade only daily trend/momentum. Directly removes the −$2,831 sub-day bucket. (Module helper added, fail-safe.)
- **LIVE SOXL pair (DB, CIO-approved):** widened `live_strategies.sl_pct` 6%→15% and `tp_pct` 15%→35% for both SOXL rows (within the 20% cap) — fixes the live whipsaw on the existing graduated pair (read fresh by the live pass, no restart). The monitoring "2× SL" catastrophic guard now scales off the correct wide stop (~30% not 12%).

**VERIFIED live:** SOXL/TQQQ/SOXS → leveraged (20% cap, wide-stop branch, daily-only); SPY/QQQ/AAPL → normal. WF cache is param-keyed so SOXL/TQQQ auto-revalidate at the new stops on next proposal (no manual clear).

**FLAGGED / NOT done (judgment calls):**
- **Cross-asset-signal template** (long SOXL gated on SOXX>50DSMA + SOXX momentum>0 + SPY>100DSMA + vol-ceiling — the user's reference edge): needs **new cross-symbol DSL primitives** (the DSL can't reference another symbol's SMA today; `LAG_RETURN`/`RANK` exist but not cross-symbol SMA). Higher-effort follow-up; the existing daily trend templates (EMA/SMA/ADX Trend — the top SOXL earners) + the risk fixes above capture most of the proven edge now.
- **SOXL daily re-graduation:** the live pair is on the 4H template (now stop-widened). Cleaner long-term is to re-graduate SOXL on a DAILY trend template (anti-churn already blocks new 4H leveraged pairs). Left for CIO — the 4H live pair is net-positive (+$868) and now has leverage-appropriate stops.

---

**SESSION 2026-06-21 (Opus 4.8) — DATA-PIPELINE RELIABILITY: FMP 429 burst fix + SPY 1h weekend false-alarm. Deployed live, healthy, verified, pushed.**

Two data-source error classes from the logs, both root-caused and fixed:

- **FMP 429 rate-limit storms (70/24h, all fundamental endpoints) — FIXED** (`src/data/fundamental_data_provider.py` `RateLimiter`). Root cause: the token bucket held the ENTIRE per-minute budget (`_bucket_max = max_calls = 300`) and started FULL, so after any idle gap a cycle could fire up to 300 calls in the first instant (the cache warmer drives ~8 concurrent threads). FMP enforces a per-second/burst cap below the per-minute budget → bursts 429'd (verified: clusters of ~10–15 calls in 1–2s while the 300/min budget was nowhere near used), which then tripped the circuit breaker and starved fundamentals for 60s. Fix: cap the bucket to a small burst window (`tokens_per_sec × burst_seconds`, default 1s → 5 for 300/min) and start at that cap, so calls pace at ~5/sec (the advertised rate). The rolling-window still enforces the full per-minute budget. **Dual-regime guard:** pacing only applies when `tokens_per_sec ≥ 0.1` (per-minute style); long-period/per-DAY limiters keep the full-budget bucket (the rolling window is their control) — preserves daily-burst semantics + existing tests. **Single uvicorn worker confirmed** (one global limiter; not a multi-process issue). PROVEN on EC2: 300/60 instantaneous burst 300→5, then 5/sec; daily 5/day still bursts 5; `wait_for_token` 8/8 (warmer not starved). The 2 pre-existing unit-test failures (`test_fallback_to_alpha_vantage` — AV fallback intentionally disabled; `test_earnings_calendar_caching`) fail identically on the original file → NOT caused by this change.

- **SPY 1h "All historical data sources failed" — FIXED** (`src/data/market_data_manager.py`). Root cause: SPY is the only symbol fetched as a market benchmark every cycle (regime detector + Market Quality Score). On weekends the analytics do an incremental 1h gap-fill for `today→today`, which has no bars (equities don't trade weekends). The 1d path already degrades gracefully ("likely closed market… returning empty") but the 1h path ran the full Yahoo→FMP→eToro chain (FMP is skipped for non-1d), found all empty, and raised a hard ERROR. So it was SPY-only (only benchmark fetched on schedule) × 1h-only (no closed-market grace) × Sundays-only (6×). Fix: new `_is_recent_market_closed_window()` — when a RECENT window (end within 3d) for a non-24/7 symbol falls in a closed market (via `MarketHoursManager`, eToro 24/5 STOCK schedule), return `[]` gracefully at INFO instead of ERROR+raise. Fail-safe (returns False on uncertainty); crypto/forex (24/7) and old/historical windows are never suppressed, so genuine weekday outages still surface. VERIFIED live (today is Sunday): SPY 1h today→today now returns 0 bars with no exception; guard=True for SPY, False for BTC and for a 400-day-old window; 30-day SPY 1h fetch unaffected (136 bars). (Residual: the per-source WARNING lines on the closed window remain — benign, low-volume, not ERROR.)

---

**SESSION 2026-06-21 (Opus 4.8) — CRYPTO COST RE-BASELINE (0.3%/side) + CATALOG RE-OPEN. Deployed live, healthy, caches cleared, proof re-run. NOT yet pushed at time of writing (see end).**

Account holder confirmed the real eToro Diamond crypto commission is **0.3%/side (0.6% RT)**, NOT the 0.75%/side (1.5% RT) modelled everywhere. Every backtest was ~2.3× too expensive on crypto. Re-baselined the cost everywhere, cleared the wrong-cost caches, relaxed the catalog cull, and let the honest gate re-evaluate. **Crucial verified finding below — the cost fix did NOT resurrect high-frequency mean-reversion.**

**Changes shipped (each verified):**
- **`config/autonomous_trading.yaml`** (synced FROM EC2 first; only a UI timestamp diff): `transaction_costs.per_asset_class.crypto.commission_percent` 0.0075→**0.003**; `per_symbol.BTC`/`ETH` 0.0075→**0.003** (slippage left as-is). **Verified live: `round_trip_cost_pct` now BTC/ETH 0.70%, generic crypto 0.80%** (was 1.60%/1.70%). Because the honest per-trade gate reads `round_trip_cost_pct`, every crypto accept/reject auto-recalibrated.
- **`config/autonomous_trading.yaml` `min_return_per_trade`** crypto floors halved (cost ratio ~0.47): crypto 0.04→0.02, crypto_1d 0.02→0.01, crypto_4h 0.015→0.0075, crypto_1h 0.009→0.0045. **[CIO-adjacent threshold — flagged.]** (Note: PAPER disables this gate via `disable_min_return_per_trade=true`; affects RESEARCH/activation path.)
- **`src/strategy/cost_model.py`** `_FALLBACK_COSTS_PER_SIDE["crypto"]` 0.0058→**0.004** (NOT the literal 0.003 in the handoff — the fallback is a per-SIDE BUNDLE of commission+spread+slippage, so to actually MATCH the config round-trip (0.8%) it must be 0.3%+0.1% = 0.4%/side; 0.003 would only count commission and understate RT to 0.6%. 0.004 reproduces config exactly AND is the more conservative value. Verified: fallback RT = 0.80% == config). Stale "Platinum ~1.16%" docstring also corrected.
- **`.kiro/steering/trading-system-context.md`** — the "0.75%/position, 1.5% round trip" line and the transaction-costs table corrected to 0.3%/side / 0.6–0.8% RT, with the account-holder provenance noted so it can't be re-introduced.
- **`src/strategy/template_catalog.py`** — re-derived the crypto cost-style filter for ~0.8% RT (was tuned to 1.5%): `_MIN_CRYPTO_TP` 0.06→**0.03**; `_CRYPTO_MIN_HOLD_HOURS` 24→**8**; mean-reversion/volatility re-admitted at TP≥**5%** & hold≥**8h** (was a deep-capitulation-only TP≥20%/hold≥7d carve-out). **Verified live: surviving crypto templates 33→52** (mean_reversion 1→16, volatility 0→2, breakout 8→9, momentum 10→11, trend 14 unchanged).
- **`scripts/clear_crypto_wf_cache.py`** — now derives the crypto universe from `DEMO_ALLOWED_CRYPTO` (was a stale hardcoded set with MATIC/DOGE, missing LTC/BCH/ADA/XRP) so it can't leave wrong-cost entries behind. Ran it: cleared 4 validated + 64 failed + 68 rejection-blacklist + 43 zero-trade crypto entries. Restarted to reload.
- **`scripts/verify_crypto_trend_edge.py`** — parametrised (`--templates`/`--symbols`) with a default sample spanning proven trend + re-admitted MR.

**⚠️ KEY VERIFIED FINDING (contradicts the handoff's "expect more crypto passes" for MR):** the proof backtest at the CORRECT 0.7–0.8% cost (production rolling-WF + honest per-trade cost-net gate, full 2023–26) shows the cost fix did **NOT** make high-frequency mean-reversion viable. The re-admitted high-freq MR/intraday templates are **still net-negative** even at the lower cost — they churn 50–160 trades on tiny per-trade gross edge that 0.7–0.8% RT still eats:
  - RSI Dip Buy −0.36% to −1.55%/trade (100–117 trades); BB Mean Reversion −0.27% to −0.98% (55–77); BB Squeeze Breakout −0.42% to −1.04% (55–60); MACD Trend −0.31% to −0.81% (135–164); 4H BB Band Walk −0.09% to −1.27%; Vol-Managed Trend all fail.
  - The genuinely promising re-admits are the **LOW-FREQUENCY DAILY MR** (Daily SMA Snap Back / Oversold Bounce / BB Lower Bounce): they produce **<3 trades/symbol** → can't be judged single-symbol; they need the **cross-sectional/family pooling** path (B-5) to qualify. Left loaded so the family path can reach them.
  - **PASSES at the correct cost (consistent with prior sessions, now with more margin):** 21W MA Trend Follow × ETH (Sharpe 1.08, +6.75%/trade, 10t); Weekly Trend Follow × ETH (0.45, +3.25%, 13t) & × SOL (0.61, +7.20%, 8t); Time-Series Momentum × ETH (0.67, +3.34%, 14t).
  - **Interpretation:** the empty crypto book was PART artifact (PART 1 validator fixes) and PART **real-edge deficit in high-freq MR** — NOT merely a cost error. The cost fix's true benefit is widening the margin for the trend/momentum winners (esp. ETH/SOL) and correctly lowering gates, not resurrecting MR. The discriminator is **trade frequency**, not MR-vs-trend: high-freq churn loses; low-freq large-move wins. The catalog relaxation is kept (handoff intent: "let the gate decide, don't hand-pick") — the gate now correctly rejects the high-freq re-admits, which is the system working as designed (no bad trades, just some extra WF compute/cycle).

**STATE / NEXT:** BTC still in a downtrend (trend-only winners + BTC-trend gate → crypto correctly sits flat today; the proof spans 2023–26 so it's the regime-independent evidence). Crypto book remains dark (0 strategies) — expected. **NEXT:** (a) watch the first BTC-uptrend cycle for crypto wf_validated/activation (expect ETH/SOL trend/momentum, now clearing with more margin); (b) the low-freq daily MR re-admits are candidates for the cross-sectional/family path — verify B-5 quorum can qualify them; (c) consider whether the high-freq MR re-admits (proven cost-losers) should be re-disabled for cycle-compute efficiency — CIO/efficiency call, not a correctness issue.

---

**SESSION 2026-06-21 (Opus 4.8) — CRYPTO UNIVERSE 10 → 12 (XLM, HBAR added). Deployed live, healthy, backfilled, proof-verified, pushed. (User runs the activation cycle.)**

Researched high-volume, institutionally-traded crypto for additions under our hard constraints (UK retail = long-only spot; must be on eToro for execution + Binance for data). Institutional proxies (all June 2026): the SEC-approved **T. Rowe Price Active Crypto ETF** eligible-15 list (BTC/ETH/SOL/XRP/ADA/AVAX/LTC/DOT/DOGE/HBAR/BCH/LINK/XLM/SHIB/SUI), **CME** futures (SOL/XRP/ADA/LINK/XLM + Nasdaq-CME index), live spot ETFs (incl. DOGE). We already held 10 of the 15. Added the two cleanest institutional TREND names not yet held:

- **XLM (Stellar)** — in the T. Rowe ETF list AND has CME futures AND sits in the Nasdaq-CME Crypto Index (the most institutionally-blessed name we lacked).
- **HBAR (Hedera)** — T. Rowe eligible, enterprise/institutional narrative.
- Held back (flagged, not added): **DOGE/SUI** (DOGE meme-noisy, weak trend fit; SUI thin <3yr history) — both already have eToro IDs in `etoro_client.INSTRUMENT_IDS` (DOGE 100043, SUI 100340) if we later want them. **BNB/TRX** (not in the ETF/CME set; BNB eToro-UK availability unclear). **HYPE/SHIB** skipped.

**Wiring (all verified live):** eToro instrument IDs resolved against the LIVE `instrumentsmetadata` API (not guessed): **XLM 100020, HBAR 100061** (type 10 = crypto). Touched:
- `config/symbols.yaml` crypto: +XLM/+HBAR (etoro_id + sector).
- `src/api/binance_ohlc.py` `SYMBOL_MAP`: +XLMUSDT/+HBARUSDT.
- `src/strategy/conviction_scorer.py` `CRYPTO_SCORES`: XLM 11.0, HBAR 10.0 (tiered with LTC/BCH and AVAX/DOT/LINK).
- `src/api/etoro_client.py` `INSTRUMENT_IDS`: +XLM/XLMUSD/HBAR/HBARUSD (fast-path so order exec doesn't fall to search).
- `src/utils/symbol_mapper.py` `SYMBOL_ALIASES` + `YAHOO_FINANCE_TICKERS`: +XLM/HBAR (so the Yahoo fallback resolves XLM-USD/HBAR-USD instead of silently fetching the wrong ticker).
- `config/strategy_catalog/crypto.yaml`: widened the **cross-sectional/family universe 10 → 12** (5 full-universe `family_universe`/`rank_universe` blocks + the inline `RANK_IN_UNIVERSE` list + description). Left the 6-coin BTC-Follower 1H/4H families untouched (intentionally narrower, out of scope). `rank_top_n` kept at 4.

**Backfilled** XLM + HBAR to full **5y depth** across 1d/4h/1h from Binance (`scripts/backfill_crypto_5y.py --symbol`). **PROOF (read-only, production rolling-WF + honest gate, full history):** `21W MA Trend × XLM` PASS (Sharpe 0.48, +2.71%/trade, 19t) and `× HBAR` PASS (0.33, +2.81%, 13t); `Cross-Sectional Momentum × XLM` PASS (0.68, +5.40%, 21t) on the new 12-coin universe — both new coins clear the cost-net bar on the trend templates and the gate discriminates (Weekly/TSMOM fail). The WF caches/blacklists do NOT need clearing for the new coins (no prior entries existed); `clear_crypto_wf_cache.py` already auto-includes them (derives from `DEMO_ALLOWED_CRYPTO`). **NEXT (user): run a cycle** — XLM/HBAR single-name trend strategies and the widened cross-sectional template should propose/validate when BTC turns up.

---

**SESSION 2026-06-20 (Opus 4.8) — PART 3: RESEARCH-DRIVEN EDGES + RISK-OFF EXIT + FUNDING SIGNAL. Deployed, healthy, pushed. Commits `81ce036`,`d45ced0`.** After an online review of 2026 crypto-quant literature + current dynamics (BTC dominance ~58-63% 4yr high, "altcoin rotation selective not gone"; volatility-management is the documented momentum-crash mitigant):

- **New templates** (catalog 27→32, all trend/momentum, cost-viable): **Vol-Managed Trend** (entry gated on ATR(14)<1.3×ATR(50) — stand aside in liquidation spikes), **BTC Relative Strength** (dual momentum — alt must beat BTC over 30d via `LAG_RETURN("SELF")>LAG_RETURN("BTC")`), **Time-Series Momentum** (canonical multi-horizon TSMOM — proof: ETH +2.44%/trade Sharpe 0.49), **Funding-Filtered Trend** (skip entries when BTC funding >4bp/8h = froth), **Capitulation Funding Re-Entry** (re-enter trend-turn when funding<0 = washout).
- **Dominance Rotation fix**: was DEAD (checked absolute `btc_dominance<0.55` but dominance is 0.58-0.63). Added derived `btc_dominance_change` onchain metric (7d Δ); now fires on dominance *falling* ≥1pp/7d — regime-adaptive.
- **NEW onchain metrics** (`src/api/onchain_client.py`): `btc_dominance_change` (CoinGecko-derived) + `btc_funding_rate` (Binance public funding history, daily mean, 2y, backtestable). Funding = leveraged-positioning sentiment; signal-only (can't trade carry on eToro).
- **BTC RISK-OFF EXIT overlay** (`monitoring_service._check_crypto_regime_exits`): symmetric to the entry gate — force-exits LIVE crypto longs when BTC<SMA50; LIVE-only (PAPER unbiased), 30-min cadence, fail-open, `pending_closure` pipeline. **No-op today (0 live crypto) but correctly armed (BTC IS in downtrend).**

**Proof tooling:** `scripts/verify_crypto_trend_edge.py` (production rolling-WF + honest gate on any template×symbol set), `scripts/verify_crypto_catalog.py` (surviving-template list). Gate verified DISCRIMINATING (TSMOM/21W-MA on ETH pass; negative-edge fail; rare-event templates flagged too-few-trades).

**STILL OPEN (flagged, not built):** paid on-chain data (MVRV/NUPL/exchange-netflows — needs Glassnode/CryptoQuant subscription, CIO cost call); open-interest signal (Binance OI history only ~30d on free tier → not backtestable, live-only); 52-week-high breakout + cross-sectional breadth filter (incremental). Venue ceiling unchanged: carry/basis/vol/stat-arb need perps/options/shorting eToro lacks.

---

**SESSION 2026-06-20 (Opus 4.8) — PART 2: CRYPTO STRATEGY REVAMP (CIO-approved). Deployed live, healthy, pushed. Commits `f1c50af`,`bd3ea0c`.** After the R1-R8 validator fixes (PART 1, below) made the funnel honest, a crypto-only cycle proved the catalog ITSELF was the problem: every sampled high-frequency mean-reversion template returned −1.5% to −10% cost-net/trade at eToro's 1.5% round-trip. Pivoted to crypto's real documented edge (trend/momentum):

- **Catalog cost-style policy** (`template_catalog._passes_crypto_cost_style`): only trend_following/momentum/breakout holding ≥24h survive load → **90→27 crypto templates** (12 trend/8 breakout/7 momentum). Drops mean-reversion/volatility + sub-day scalps.
- **Universe 6→10** (XRP/ADA/LTC/BCH added; binance SYMBOL_MAP + symbols.yaml; all backfilled). Family/cross-sectional `family_universe` + RANK universe widened to 10; cross-sectional top-N 3→4; family quorum 4/6 → **50% majority**.
- **BTC-trend signal gate** (`order_executor._check_btc_trend_gate`, LIVE-only, crypto-only, fail-open): blocks crypto LONG when BTC daily < SMA(50). A long-only crypto trend book must be flat in a BTC downtrend.
- **`scripts/clear_crypto_wf_cache.py`** extended to also clear rejection/zero-trade blacklists (ran it: cleared 73 rejection + 23 zero-trade crypto entries — this was why a crypto-only cycle proposed only 1 strategy: 7 key templates were blacklist-blocked).

**PROOF the edge is real** (`scripts/verify_crypto_trend_edge.py`, production rolling-WF + honest gate over full 2023-26 history): **21W MA × ETH = +5.85%/trade (Sharpe 0.94), Weekly Trend × ETH = +2.35%/trade PASS**; negative-edge templates (Donchian −6%, Vol-Compression) correctly FAIL; Golden Cross/BTC-Follower flagged too-few-trades (ultra-low-freq, need cross-sectional pooling). Gate DISCRIMINATES — not all-pass, not all-fail.

**CURRENT STATE (correct, not a bug):** BTC is −14% (63.5k vs SMA50 72.7k) → trending_down → the trend-only catalog proposes 0 crypto = **system correctly sits flat in a BTC bear** (vs the old catalog buying dips into −10%/trade losses). Crypto trend strategies will propose/validate/activate when BTC turns up; the proven-edge ones (21W MA/Weekly Trend on ETH, cross-sectional rotation across 10 coins) are the live candidates. **NEXT: watch the first BTC-uptrend cycle for crypto `wf_validated`/activation; verify R4 family quorum fires when a cross-sectional template is regime-eligible.** Reachable-on-eToro edge is long-only trend/momentum only — carry/basis/vol/stat-arb need derivatives eToro retail lacks (documented in the strategic analysis).

---

## ⚡ PART 1 — VALIDATOR FIXES (R1–R8)

**SESSION 2026-06-20 (Opus 4.8) — CRYPTO PIPELINE end-to-end audit + revamp R1–R8. All deployed live, healthy, pushed. Commits `7efadc2`→`40e83a7`. Audit: `CRYPTO_PIPELINE_AUDIT_2026-06-20.md`.**

**Headline finding (verified live DB/logs):** crypto book was DARK — 0 crypto strategies in any status, last crypto order 2026-05-25. Root cause was a validation ARTIFACT (the crypto analog of the √252 class): crypto WF validated on 1–4 trades/window with per-bar flat-bar-inclusive Sharpes inflated to 2.5–5; equity-calibrated gates (consistency≤1.5, per-bar overfit quorum, unreachable 4/6 family quorum) then rejected on that noise. Data/costs/annualization/24-7 handling/risk caps were all VERIFIED CORRECT (not the bug).

**Fixes shipped (all crypto-only branches; equity path byte-for-byte unchanged):**
- **R1+R3** (`strategy_proposer` acceptance loop): crypto now gates on a per-trade, COST-NET, frequency-annualized Sharpe (`_per_trade_net_sharpe`, pooled across rolling windows) + positive cost-net expectancy; consistency gate applied to that bounded metric. Per-bar `overfitted` AND `het` (rolling trade count, itself per-bar-filtered) bypassed for crypto — they were the artifact carriers.
- **R2** (`autonomous_trading.yaml` asset_class_windows, EC2-authoritative/gitignored): crypto WF test windows lengthened — 1h 45→90, 4h 60→120, 1d 90→180, longhorizon 180→365 (within the ~2.7yr Binance history; rolling-WF auto-fits).
- **R4** (`strategy_proposer`): family cross-validation ("B-5") — force the whole `family_universe` to be proposed together so the 4/6 quorum can form (was 5/6 `not_proposed` every time → 14/14 dead); family clears-bar now uses the same per-trade cost-net metric.
- **R5** (`market_data_manager`): crypto 1d freshness SLA 30h→48h (daily-bar age measured from open; 30h false-flagged stale most of each day). Intraday crypto stays tight.
- **R7**: ran `scripts/clear_crypto_wf_cache.py` (removed 21 failed + 4 validated crypto cache entries) so the funnel re-evaluates fresh.
- **R8a**: MC bootstrap annualizes crypto on 365 (was 252). **R6**: verified the min-hold guard already exists+sound (`strategy_engine.py:5651`) — no action. **R8b**: yaml `symbols:` block is read by the config/UI endpoint (NOT dead) — left as-is.

**LIVE-VERIFIED** (3 forced cycles via a transient schedule slot, since removed/restored to slot_1-only): every crypto rejection is now an HONEST verdict — `crypto_negative_net_expectancy (−1.6% to −2.5% cost-net/trade)`, `mc_bootstrap_filtered`, or `crypto_no_per_trade_sharpe (0 trades)`. The `het=False overfitted=True` artifact reason is **fully eliminated**. R2 windows confirmed live (180/90, 365/180).

**KEY QUANT TAKEAWAY / OPEN ITEM:** the funnel is now economics-driven. It currently says the sampled crypto mean-reversion/dip templates (Hourly ATR Snap, Daily SMA Snap Back, Capitulation, Deep Dip, Crash Recovery, BB Band Walk) have GENUINELY NEGATIVE cost-net edge at eToro's 1.5% round-trip → correctly rejected. So the empty book was PART artifact (now fixed) and PART real-edge deficit. **Still PENDING live confirmation:** (a) R4 family quorum — needs a cycle where a `requires_cross_validation` template (BTC Follower 4H/Daily, Cross-Sectional Momentum) is regime-eligible/scored (none appeared in the 3 verify cycles); (b) whether the TREND/momentum crypto templates (Golden Cross, 21W MA, Vol-Compression, BTC-follower) — which survive costs far better than high-freq mean-reversion — produce positive cost-net edge and activate. Watch next daily 12:15 cycle: `grep "Crypto WF PASS (per-trade net)\|Family cross-validation quorum" logs/strategy.log` + crypto rows in `signal_decisions` stage='wf_validated'. **NOT-done by design:** rejection_blacklist (~73 crypto combos) left to self-heal (14d cooldown + R4a bypass); could clear if faster recovery wanted (CIO call).

---

**SESSION 2026-06-18 (Opus 4.8) — END-TO-END LIVE + GRADUATION audit & fixes. All deployed live, healthy, pushed. Commits `90f2c48`→`1d78a4d`.** Worked the live path then the graduation pipeline end-to-end. Rollup:

1. **Live-path audit (deliverables earlier in this file).** Reconciliation DB⟷eToro clean (8 live positions, all match); G-44 validate_signal IS wired on live; TSL healthy; book is 100% long tech/semis, net-negative ex-PANW (CIO/portfolio item, PARKED — downstream of low graduation throughput, not a risk-mgmt bug).
2. **#5 strategies.status↔live_strategies sync bug — FIXED** (`90f2c48`): live-retire now reverts LIVE→PAPER; 5 stale rows backfilled. `status='LIVE'`==10==active.
3. **CAT recurring $1000-floor ERROR — FIXED** (`a8a2020`): re-floor demo size after the regime multiplier (skip cleanly at INFO when symbol budget exhausted). Verified 0 ERRORs.
4. **Dead nested live-fill route — DISABLED** (`a8a2020`, flag); physical removal is a follow-up.
5. **Exit-slippage capture (Option B) — SHIPPED** (`b65c030`): `src/analytics/execution_cost_backfill.py` reconciles LIVE closed trades to eToro `get_trade_history` ground truth (real close rate), drift-guarded; wired into `_run_daily_sync`. CLI `scripts/backfill_execution_costs.py`.
6. **Graduation alpha-gate $5K-notional bug — FIXED** (`48b3d58`): reads `flat_position_size`.
7. **Dead WF-Sharpe-CI gate — REMOVED** (`5c759b2`): redundant + weaker than the MC bootstrap; never fired (wf_test_trades 0/328).
8. **PAPER health-demote retiring trend strategies too early — FIXED** (`4342b7a`): forward-P&L test proved it (negative-first-5 pairs recovered +$19.91/trade, 67%). Demote now requires graduation `min_trades` (PAPER), catastrophic-loss fast-kill kept, LIVE 5-trade bar untouched. `should_demote_on_health()` + 6 tests.
9. **Graduation counted only 201/694 pairs (history lost on version deletion) — FIXED** (`1a373bd`): the aggregation INNER-joined strategies for the template name, dropping 63% of trades (orphaned deleted versions). Now LEFT JOIN + `COALESCE(strategies template, regexp(name), trade_metadata template)` across all 4 sites. Visible funnel 201→528, eligible 8→11.
10. **Re-graduation of retired pairs (e.g. GOOGL) — FIXED** (`4a5b608`): `latest_strategy` CTE was built from `trade_journal JOIN strategies` → could only pick a rep that had its OWN trades; a retired-from-live/re-proposed pair's surviving version usually has 0 new trades, so it got no rep and was dropped. Now the rep comes from the `strategies` table (most-recent surviving PAPER/BACKTESTED/LIVE version holding the symbol, symbols unnested). **GOOGL now surfaces in the queue** (the "first live strategy, buggy live record" — its 11% live WR was bug-distorted, so re-graduation is reasonable; CIO call). Also fixed alpha-benchmark range→period-return, and made missing-WF **fail-closed** (+6 tests).
11. **Live gate-block badge now shows the reason — FIXED** (`1d78a4d`): `get_live_strategies` discarded `signal_decisions.reason` for the gate_blocked stage. Now e.g. *Triple EMA Alignment MU: "Gate blocked: Position would exceed max position size limit of 15.0%"* (MU already at the 15% per-symbol live cap with 2 open positions — working as intended).

**STILL OPEN / RECOMMENDED NEXT (prioritised):**
- **[FIXED 2026-06-20] Low-frequency factor templates auto-rejected at WF — root cause of the single-factor (long-momentum) monoculture.** Diagnosis (from "why do we always trade the same symbols?"): the proposer proposes broadly (281 symbols) but only momentum/breakout converts; the diversifying factor/rank templates (Low Volatility, Cross-Sectional Momentum, Short-Term Reversal, Dual Momentum, Cross-Asset Trend) convert at ~0%. WF rejection reasons = **74% `het=False` with `tv=True tev=True overfitted=False`** — valid, non-overfit Sharpes killed purely for too few trades. Low-frequency BY CONSTRUCTION (a cross-sectional-rank symbol only trades when top-N), so even the existing non_crypto_1d 365d test window yields <8 trades vs the 8-floor. NOT "no edge" — a validation mis-calibration (same class as √252 / RSI-cap). Fix (a)+(b): route low-frequency templates to a LONG-HORIZON WF window (code fallback train=1095/test=730, ~2y test → ~8-16 entries) so they reach the floor at their natural cadence; the floor is **NOT lowered** (longer multi-regime OOS window, not relaxed rigor). Detection: explicit set ∪ code defaults ∪ alpha_edge monthly types ∪ structural `RANK_*`-in-rules. Extends `_select_wf_window`/`long_horizon_templates` to non-crypto 1d. `strategy_proposer.py`; tests `tests/test_wf_low_frequency_window.py` (7). Deployed + healthy; failed-cache cleared. **Live confirm pending next autonomous cycle (weekend=idle). Verify Mon:** `grep "WF window \[non_crypto_1d_longhorizon\]" logs/strategy.log` + factor-template activation rises.
  - **(c) DONE 2026-06-20 — rank-factor 0-trades root cause was a PROPOSER bug, not basket-validation.** The 3 RANK-based cross-sectional factors (Cross-Sectional Momentum, Short-Term Reversal, Low Volatility) produced exactly 0 trades because the proposer assigned them symbols OUTSIDE their template's fixed ranking universe (e.g. Low-Vol ranks `[PG,KO,JNJ,…]` but was proposed on WFC/DE/XLF). A rank primitive can only place SELF top-N if SELF ∈ universe; otherwise the indicator is all-False → 0 trades (confirmed by the `primary symbol X has no daily data … will be all-False` warnings, and by momentum working on MA∈universe but 0 on ON/EQIX∉universe). Fix: `_cross_sectional_universe(template)` parses the universe from the RANK_* rule; `_match_templates_to_symbols` now skips (template, symbol) when the template is cross-sectional and symbol ∉ universe. Each universe-MEMBER's per-symbol backtest is then a valid timing strategy ("hold X while it's a top-N name") — so the full basket-validation engine change is **no longer required** (optional statistical-efficiency refinement only). `strategy_proposer.py`; tests in `tests/test_wf_low_frequency_window.py` (now 11). Deployed + healthy. **Verify next cycle:** the `RANK[*] … all-False` warnings disappear and the 3 rank templates produce trades / activate on universe members.
  - **Context — PAPER vs LIVE:** factor/correlation RISK limits belong in LIVE (capital preservation), NOT PAPER (PAPER = max data breadth). A LIVE portfolio-construction layer is STARVED until PAPER produces uncorrelated edges — which this WF fix unblocks. Sequence: research breadth (this) → uncorrelated graduated edges → LIVE portfolio layer.
- **[FIXED 2026-06-19] WF-Sharpe robustness across version churn.** Added a durable `wf_validation_ledger` table (no TTL) keyed by **(template_name, symbol)**, persisting the WF test Sharpe so it survives BACKTESTED-TTL deletion of the strategy versions that carried it in `strategy_metadata` JSON — the same root cause as the trade-history loss (`1a373bd`). The proposer upserts it on every WF pass (for **all** the strategy's symbols, not just primary); `get_graduation_queue` now recovers WF Sharpe in order **current-version JSON → pair-level ledger → `best_wf_by_template`** (the ledger sits between, so an established pair recovers its OWN WF Sharpe instead of fail-closing or borrowing a sibling-symbol value). Helper `src/strategy/wf_ledger.py` (`record_wf_validation` / `load_wf_ledger` / `backfill_from_current_state`), CLI `scripts/backfill_wf_ledger.py`, table auto-created via `create_all`. **Deployed + healthy + backfilled live: ledger seeded 324 pairs / 39 templates; all 11 active live pairs covered at the pair level (incl. the previously-transient XLK/MU); all 20 attributable ≥15-trade pairs have positive WF coverage (15 pair-level + 5 via template fallback) → none fail-closed.** Tests `tests/test_wf_ledger.py` (8). NOT entangled with the cost work.
  - **Follow-up same day — `/approaching-graduation` endpoint was a SECOND site still showing "wf_sharpe unavailable".** Root cause: that endpoint's `rows` aggregation recovered the template from `trade_metadata` in its **WHERE** clause (so orphaned-version trades weren't filtered out) but **NOT in its SELECT/GROUP BY** — so deleted-version trades grouped under a **NULL template_name** (e.g. MU 43, TQQQ 37, XLK 34, SPX500 16, DELL 15), which matched no WF source → spurious fail-closed AND defeated the `active_live` exclusion (so live pairs leaked into the "approaching" list). This was the incomplete part of `1a373bd` at this one site. Fix: completed the 3-way template COALESCE in the SELECT (mirrors `get_graduation_queue`) and added the ledger to its WF resolution (pair ledger → template-max). **Verified live (SQL replicating the endpoint query): NULL-template buckets gone — orphaned trades re-attribute to their real templates (MU→1.61/3.57, XLK→2.92, DELL→2.66 WF), all positive; the now-correctly-named live pairs are excluded via `active_live`.** Deployed + healthy. `src/api/routers/strategies.py`.

- **[FIXED 2026-06-19] Paper/WF qualification-ratio graduation gate REMOVED (both bounds) — it was structurally broken AND redundant.** Investigation (prompted by AMD 3.71×/SPY 4.22× rejections) found the ratio divided a **per-trade √252** paper Sharpe by vectorbt's **per-bar, incl-flat-bars, √441** WF Sharpe — incompatible estimators, so the ratio ran ~3× high by construction; the cap was rejecting strong-paper pairs on a measurement artifact. Worse, it was redundant: the *real-edge* bar is already enforced upstream by WF acceptance (OOS) + the **activation `min_sharpe=1.0` absolute bar** + MC bootstrap (p5≥0, consistent per-trade freq-annualized basis); *edge-alive-in-paper* by pnl>0 + win-rate floor + Wilson LB; *small-sample luck* by min_trades + Wilson LB + DSR. The ratio also ignores the ABSOLUTE WF level, so it can't tell "strong WF + strong paper" from "weak WF + lucky paper" (and the weak-WF case is already blocked at activation). Same profile as the WF-CI gate removed in `5c759b2`. Removed the gate in `is_qualified` (kept `wf_sharpe`/`qualification_ratio` as INFORMATIONAL on the CIO card; ledger now serves display + the planned regime check). **Verified live: queue went 0→2 — surfaces AMD (15 trades, 73% WR, +$2,014, WF 1.62, OOS>IS) and SPY (18, 61%, +$464, WF 1.16, OOS>IS); both already cleared WF+MC+the 1.0 activation bar; AMAT/ENPH stay rejected on negative edge; live pairs still excluded.** NOTE: queue is a CIO *recommendation* list — appearing ≠ live capital; live activation is a separate CIO approval. Tests: `tests/test_graduation_gate_wf_ungated.py` (9) + updated `test_wf_ledger.py`. Diagnostic `scripts/show_graduation_queue.py`.
  - **NEXT (proper regime-luck guard, RESEARCH-stage):** add a regime-conditional WF check (does the edge hold outside the current regime? / require the validation window to span >1 regime) as the correct replacement for the concern the ratio cap gestured at. The ledger is the substrate. NOT a blocker for the removal (the removed cap didn't actually measure regime-luck).
  - **STILL SEPARATE/data-gated:** F1/F2 cost-net Sharpe recalibration sharpens the *absolute* `min_sharpe` bar (the gate now doing the real-edge gating) — complementary, still gated on LIVE fills.

- **[FIXED 2026-06-19] Regime-robustness graduation gate — the proper replacement for the removed ratio cap's "don't graduate the regime" concern.** Evidence-based, realized-trade guard (chosen over instrumenting the vectorbt WF engine: the cross-regime evidence that matters for PAPER→LIVE accrues in realized trades w/ ground-truth `market_regime`; the WF OOS train/test split already provides historical regime-robustness; contained to the gate, zero hot-path risk). `is_qualified` rejects a pair ONLY when it has DEMONSTRATED a losing edge — net-negative over ≥ `REGIME_MIN_SAMPLE` (8) trades — in a market-regime *family* it has actually traded enough to judge. Never rejects on ABSENCE of cross-regime data (so trend specialists in a long uptrend aren't blocked); becomes increasingly protective as the book sees corrections/ranging/down. New `_regime_family()` + `load_regime_breakdown()` (one bulk query, families: trending_up/down/ranging/high_vol; NULL/unknown excluded), wired into `get_graduation_queue` AND the `/approaching-graduation` view (same verdict both places). Config: `graduation_gate.regime_min_sample` / `regime_loss_tolerance`. **Bug caught + fixed during deploy:** `text` is imported function-locally in graduation_gate.py, so the new module-level `load_regime_breakdown` hit a `NameError` → swallowed → returned {} AND its `except` `session.rollback()` ran mid-`get_graduation_queue`; added the local import + a mocked-session regression test (SQLite can't run the REGEXP_REPLACE/`->>` SQL). **Verified live: `load_regime_breakdown` returns correct per-family P&L (AMD/SPY trending_up positive), gate does not misfire.** Tests: `tests/test_graduation_regime_robustness.py` (9). Deployed + healthy.
  - **Queue note:** queue now correctly **empty** — AMD + SPY (the two pairs the ratio-cap removal surfaced) were **CIO-approved to LIVE 2026-06-19 11:53** (now in `live_strategies`, active), so they leave the queue. No remaining positive non-live ≥15-trade candidates (AMAT/ENPH negative). This is the gate fix working end-to-end: surfaced → CIO-approved → graduated.

- **[FIXED 2026-06-19] Cycle-log "0 filled" + size-estimate crash + demo-capacity knobs (3 items, from a "we never open a trade during the cycle" report).** Investigation: signal gen is HEALTHY (~1535 signals/24h), trades DO open+fill (~75 demo order fills/24h, 9 opens/33 closes), BACKTESTED signal path works (included in PAPER pass, promoted on first fired signal, TTL-managed). The "never trades" perception = two reporting artifacts + real saturation. Fixes: (1) **Cycle fill reporting** — `[ORDERS] … 0 filled` always showed 0 because fills confirm ASYNC (order_monitor 60s) after the summary is written; now counts orders FILLED with `submitted_at >= previous cycle start` (`autonomous_strategy_manager.py` + `cycle_logger.py` label). (2) **Size-estimate 500** — `get_size_estimate` built `TradingSignal(id=,price=,stop_loss_pct=,take_profit_pct=)` (none exist on the dataclass; missing required `reasoning`/`generated_at`) → always crashed; fixed construction, SL/TP into `metadata` where risk_manager reads them (`strategies.py`). (3) **Demo-capacity now user-tunable** — `MAX_PER_SYMBOL_PER_TIMEFRAME` ← `paper_trading.max_positions_per_symbol_per_timeframe` (default 8), coupled per-symbol CAPITAL cap ← `paper_trading.symbol_cap_pct` (default 0.10); defaults unchanged. The two are COUPLED — raise BOTH for real breadth. Recycling stale positions is NOT a lever (zombie exits work: of 200 open demo only 5 are flat±2% AND >7d). Binding constraint = per-symbol cap on ~12 popular names (CAT 10, SMH/EEM/C/AMD/TSM 9). **Magnitude is USER-OWNED — knobs exposed, defaults left at current.** `trading_scheduler.py` + `risk_manager.py`. Deployed + healthy.
- **[BUNDLED, data-gated] F1/F2 cost-Sharpe recalibration + F3 1d annualization + qualification-ratio basis fix.** The ratio cap compares per-trade paper Sharpe (√252) vs vectorbt vol-scaled WF Sharpe — not apples-to-apples. Verified the current rejects are LARGELY GENUINE (paper really runs ~3× WF); √252 is only ~12% high for 4H pairs but materially high for low-freq DAILY strategies (watch those). Fix = consistent, cost-net Sharpe basis + ONE threshold re-baseline. Gated on Fix D: exit-slippage capture now SHIPPED (#5), needs LIVE fills to accrue (book is small).
- **[CLEANUP] Physically remove the dead nested live-fill route** (`trading_scheduler.py:~1709`, currently flag-disabled `_LIVE_NESTED_ROUTE_ENABLED=False`).
- **[P1 PORTFOLIO/CIO, PARKED] Live book single long-tech-momentum factor** — revisit once graduation throughput grows the book (dev stage; concentration is downstream of few graduations, not a risk-mgmt failure).
- **[P3 CIO] Directional quotas + directional_balance DISABLED**; "never zero short" unenforced.
- **GRADUATION FUNNEL state (06-18):** ~528 visible (template,symbol) pairs, 11 eligible (≥15 trades), queue = GOOGL (1; CIO decision — paper 74% but was a buggy-era live loser, Intel G11 caveat). Throughput bottleneck remains trade-count accumulation (capacity + ~3-month calendar; demo-capacity lever is USER-OWNED, chosen to ride). Gate logic verified sound (Wilson LB, type floors, min_trades all correct).

---

**SESSION 2026-06-16 (PM-3) — END-TO-END LIVE PATH AUDIT (Opus 4.8). 1 proper fix deployed + healthy + pushed (commit `90f2c48`). Rest are findings/designs below.**

Audited the full live book against live DB + eToro + code under the capital-preservation lens. **Most prior P0s verified already-fixed in code** (G-44 `validate_signal` IS wired on the live pass with `is_live=True`; reconciliation clean; TSL healthy; cycle-lock fix live since the 15:19 restart). Live book = **8 open positions, 100% LONG tech/semis** (AMD, DELL, MU×2, PANW, SOXL, TQQQ, XLK), DB ⟷ eToro reconciled exactly (8=8, prices fresh, P&L matches). Aggregate unrealized ≈ **−$92** (only PANW +$96 positive; ex-PANW ≈ −$188). Cumulative realized live_pnl across the 10 active pairs ≈ **−$459** (only PANW positive). The book is a single long-tech-momentum factor bet — this is the headline portfolio risk, not a code bug.

**FIXED THIS SESSION:**
- **#5 `strategies.status` ↔ `live_strategies.retired_at` sync bug (P2, LIVE) — DONE, commit `90f2c48`, deployed + backfilled.** `live.py retire_live_strategy` set `retired_at` but never reverted `strategies.status`, so status stayed `LIVE` forever → any UI/query counting `status='LIVE'` over-reported the live book (was 15 vs 10 active). Fix reverts LIVE→PAPER on retire (the endpoint's own documented intent: "continues paper-trading on DEMO"); scoped to the exact strategy_id, idempotent. Backfilled the 5 stale rows (GOOGL/TXN/COPPER/MU-ATR/SOXL-id2) in prod → `status='LIVE'` now == 10 == active live_strategies.
- **CAT recurring `Order size must be at least $1000` ERROR (P2, PAPER) — DONE, commit `a8a2020`, deployed + VERIFIED live.** Root cause: `validate_signal` floor-bumps the demo size to $1000, but `trading_scheduler`'s regime multiplier (1.2× in `ranging_low_vol`) + the post-regime symbol-concentration recheck run AFTER that bump with no re-floor — so a near-symbol-cap pair (CAT: 9 open positions, ~$819 headroom on the 5% cap) gets shaved to ~$800 and HARD-REJECTED by `order_executor`'s min check every cycle (16×/day at ERROR). Fix (`trading_scheduler.py` ~1556): re-apply the demo floor after the regime block — bump to min when symbol headroom + balance allow, else **skip cleanly at INFO**. Verified live: 0 CAT min-floor ERRORs post-deploy; `Skipping CAT LONG demo entry: sized $819 < demo min $1000 ... skipping cleanly` INFO emitted.
- **Exit-slippage capture (Option B) — DONE, commit `b65c030`, deployed + VERIFIED live + wired daily.** Root cause (above #6): production close paths journal exits with the close-decision price and never capture eToro's actual executed close rate → `exit_slippage` 100% NULL. New `src/analytics/execution_cost_backfill.py` reconciles LIVE closed trades to eToro ground truth via `get_trade_history` — match `trade_journal.entry_order_id == orderId`; compute true exit slippage (recorded decision price vs eToro `closeRate`) with the same 15-min drift guard as entries; correct entry/exit price + P&L to broker `netProfit`; record fees; idempotent (stashes `exit_decision_price`, one-shot per row). Read-only w.r.t. the live close hot path. Wired into `MonitoringService._run_daily_sync` (step 1c) for ongoing daily capture; `scripts/backfill_execution_costs.py` is the CLI wrapper. **One-time backfill captured 4 real exit-slips (AMD 0.08% / DELL 0.15% / PANW 0.05% / AMD 0.09% — realistic ~5–15 bps equity close costs) and correctly drift-nulled 5 queued/overnight closes (e.g. SOXL 3.6h gap = drift, not slippage); exit_price + pnl now reconciled to eToro exactly.** This is the architecture half of Fix D's unblock — the remaining gate is DATA VOLUME (live book is small; only ~9 reconcilable closes so far).
- **Dead nested live-fill route disabled (P2, LIVE cleanup) — DONE, commit `a8a2020`, deployed.** The legacy nested live route at `trading_scheduler.py:~1709` (inside the DEMO loop) is superseded by the independent live pass (`:~2436`), can never fire (live pairs are `status='LIVE'`, never in the DEMO loop at `:325`), and used an inferior conviction gate (YAML default only — no per-pair `conviction_min`, no alpha_edge branch). Gated off via `_LIVE_NESTED_ROUTE_ENABLED=False` to prevent a future DEMO-loop change silently resurrecting the worse path. **Follow-up: physical removal of the ~195 dead lines (kept inert now to minimise live-hot-path blast radius).**

**#6 COSTS (F1/F2/F3) — NOT shipped (correctly): no proper fix ready, data-gated.** F3-in-isolation is forbidden; the bundled cost-Sharpe recalibration is gated on **Fix D** (empirical per-asset costs). The exit-slippage *capture* blocker is now RESOLVED (Option B shipped, commit `b65c030` — see FIXED list). Fix D's remaining gate is **DATA VOLUME**:
  1. Only **16 clean entry-slippage rows since 06-14, all 0.0 bps** — demo fills are at-quote (useless for cost estimation); only **6 clean LIVE entry rows** exist. Need many more market-hours LIVE fills.
  2. exit_slippage capture is now working (eToro-ground-truth backfill, daily) but the live book is small — only ~4 measurable exit-slips so far (the rest drift-nulled). Accrues slowly with the small live book.
  Proper sequence (design, confirm): (a) ~~repair exit-slippage capture~~ DONE; (b) accumulate clean LIVE fills over several market days (the daily backfill now captures them); (c) derive empirical per-asset costs + repair contaminated historical `entry_slippage`; (d) THEN route costs into `from_signals(fees=…)` + add the 1d annualization branch (×√(252/365) equity/index/commodity, √(260/365) forex, none crypto) + re-baseline WF/conviction/graduation in ONE pass.

**STILL OPEN / RECOMMENDED NEXT (prioritised):**
- **[FIXED 2026-06-18, commit `4342b7a`] PAPER health-demote was retiring recovering trend strategies too early.** The `health=0` demote fired at 5 closed trades; on a positively-skewed trend book that benches strategies during normal early drawdowns. **Forward-P&L test (live demo data): negative-first-5-expectancy pairs — the would-be-demoted ones — went on to +$19.91/trade and recovered 67%, vs the positive-start control which mean-reverted to a negative median.** So the 5-trade kill was alpha-destroying AND truncating/biasing the graduation sample. Fix (PAPER only): the negative-expectancy penalty and the `health=0` demote are now gated behind the graduation `min_trades` (15), with a catastrophic-loss fast-kill (>15% realized) preserved; LIVE keeps the 5-trade bar; TSL/TP→BACKTESTED oscillation unaffected. Pure `should_demote_on_health()` helper + 6 unit tests. NOTE: this also helps graduation throughput (pairs no longer benched mid-accumulation). New config (optional): `paper_trading.health.catastrophic_loss_pct` (default 0.15).
- **[P1, PORTFOLIO/CIO] Live book is a single long-tech-momentum factor.** 100% long, 0 shorts, 0 non-tech; SOXL+TQQQ are 3x leveraged. Net-negative ex-PANW. PARKED per CIO: this is downstream of low graduation throughput (dev stage, few pairs graduated since April), not a risk-mgmt failure — a concentration veto now would just block the few graduations. Revisit once the book is bigger.
- **[FIXED 2026-06-18, commit `1a373bd`] Graduation aggregation dropped deleted-version trade history.** The gate INNER-joined `trade_journal`→`strategies` for the template name, so trades from strategy VERSIONS deleted by the BACKTESTED TTL were silently dropped — **63% of demo trades (2073/3277) were orphaned**, defeating the documented "count history across re-activations" design and undercounting every pair whose history spanned a deleted version. Fix: LEFT JOIN + `COALESCE(strategies template, regexp(name), trade_metadata->>'template_name')` across all 4 aggregation sites (get_graduation_queue pair_stats + approval-record stats + qualified P&L series + approaching-graduation view); metadata template verified 100% consistent; unattributable orphans excluded via IS NOT NULL; latest_strategy stays INNER (only graduatable pairs reach the queue). **Verified live: gate-visible funnel 201→528 pairs, eligible (≥15) 8→11; surfaced GOOGL as a real new candidate.** NOTE: queue still 0 — eligible pairs are already-live, held by the qualification-ratio cap (SPY/AMD-4H), or correctly rejected (negative pnl). GOOGL passes core gates but was a prior live loser (11% live WR) — re-graduation would need the paper→live divergence caveat (Intel G11).
- **[P1, RESEARCH] Graduation PAPER-sample selection bias (real, ongoing) — FUNNEL DIAGNOSED 06-16 PM-3.** Full funnel run against live DB: **206 distinct (template,symbol) paper pairs → only 6 reach the 15-trade floor → 0 NEW pairs qualify.** The 5 pairs that pass the full gate are 4 already-live (MU/SOXL/XLK/AMD) + SPY, and SPY is *correctly* blocked by the regime-luck cap (paper Sharpe 5.17 = 4.44× its WF 1.16 > 3.5). **Binding-constraint tally (top-14 near-misses): `paper_trades<15` ×8 (THE bottleneck), `qualification_ratio` ×5, `paper_win_rate` ×4, pnl/avg_pnl ×2.** Conclusion: the gate logic is SOUND and appropriately strict (trend win-rate floor correctly resolves to 0.45 via `template_type`, NOT 0.55; regime-luck + negative-pnl rejections are correct). The bottleneck is **trade-count starvation** — only 6/206 pairs ever accumulate 15 trades because demo saturation spreads paper fills too thin (FCFS balance-bias). Proper fix = simulated shadow paper book (no balance constraint) so every candidate accrues a clean sample. Demo capacity is USER-OWNED; this is the highest-leverage throughput lever. **Bug fixed in passing (commit `48b3d58`): the alpha-vs-benchmark gate used a stale hardcoded $5K notional (→ understated paper return 5× after the 06-15 $1K cut → over-rejected in up markets); now reads `flat_position_size`.** Secondary issue noted (NOT fixed): the queue's SPY benchmark SQL computes `(MAX-MIN)/MIN` (peak-to-trough RANGE), not the period return — overstates the benchmark and makes the alpha gate stricter than intended; low priority since the alpha gate is rarely the binding constraint.
- **[P2, LIVE cleanup — PARTIALLY DONE] Nested live-fill path physical removal.** Disabled this session (`_LIVE_NESTED_ROUTE_ENABLED=False`, commit `a8a2020`); ~195 dead lines at `trading_scheduler.py:~1709` still to be physically removed in a dedicated cleanup (kept inert now to limit live-hot-path blast radius).
- **[P2, COSTS — bundled, data-gated, BLOCKED] F1/F2 (gating Sharpe/WR gross of costs) + F3 (1d Sharpe calendar-annualized ×1.204).** See the #6 block above. **New blocker found this session: exit_slippage capture (06-14 fix `a69cb6b`) is NOT working — 0/127 closes since 06-14 have exit_slippage; a `log_exit` close-path caller isn't passing the new args. Fix/verify that FIRST**, then accumulate clean LIVE fills, then the bundled recalibration.
- **[FIXED 2026-06-18, commit `4a5b608`] Graduation gate: re-graduation of retired pairs + alpha-benchmark + fail-closed WF.** (1) **Re-graduation (main):** `latest_strategy` CTE was built from `trade_journal JOIN strategies`, so it only found a representative that had its OWN trades — a re-proposed/retired-from-live pair's surviving version usually has 0 new trades (history under deleted versions), so it got no rep and was silently dropped. **GOOGL (retired live, 19 trades aggregate, surviving BACKTESTED w/ 0 own trades) could never re-graduate.** Now the rep is picked from the `strategies` table (most-recent surviving PAPER/BACKTESTED/LIVE version holding that symbol, symbols unnested). **Verified: queue now surfaces GOOGL** (ratio 2.24, alpha −0.98%). This is the "retired strategy can come back if PAPER stats support" behavior. (2) **Alpha benchmark:** `spy_return` was `(MAX−MIN)/MIN` peak-to-trough RANGE → overstated benchmark, false-failed the −5% alpha gate; now period return `(last−first)/first`; also fixed the stale $5K notional in the Pass-2 alpha display. (3) **Fail-closed:** missing/zero `wf_sharpe` silently SKIPPED the qualification-ratio gate (pair passed un-validated) → now fails closed (only bites when no WF exists for the pair OR its template, after the best-template-WF fallback). Tests: `test_graduation_gate_failclosed.py` (6). **CIO NOTE: GOOGL is now graduatable but was a live loser (11% live WR) — Intel G11 paper→live-divergence caveat applies; CIO decision.**
- **[GRADUATION-LOGIC review 2026-06-18] (a) Dead WF-Sharpe-CI gate — REMOVED (commit `5c759b2`)** + fail-closed on missing WF added (`4a5b608`). **(c) Alpha-gate benchmark range-vs-return — FIXED (`4a5b608`).** **(b) STILL OPEN — qualification_ratio MAX cap is structurally biased**: paper Sharpe (per-trade, flat paper size, √252 ann.) vs WF Sharpe (vectorbt vol-scaled per-bar) — not apples-to-apples. Verified the rejects (SPY/AMD-4H at ~3.2–3.7×) are LARGELY GENUINE (paper Sharpe really runs ~3× WF in the favorable window), not a miscalc; the √252 annualization is only ~12% high for these high-freq 4H pairs (materially higher for low-freq daily strategies — watch those). Proper fix = compute paper Sharpe consistently with (and net-of-cost vs) WF + ONE threshold re-baseline — bundle with F1/F2, don't patch piecemeal.
- **[P3, CIO] Directional quotas + directional_balance DISABLED** (`ranging_low_vol.min_short_pct: 0.0`); "never zero short" unenforced (organically non-zero only). UI/CIO decision.
- **[INFO] SOXL live stop = −20.2%** (vs CIO sl_pct 6%): by design — `_SL_CAP_LEVERAGED_ETF=0.20` + FIX-03 0.5× leveraged sizing roughly normalizes dollar risk (~$10r). Not a bug; noting because SOXL is the prior outlier name.
- **Verify next market-hours cycle:** retire→PAPER revert fires on the next live retirement (`status_reverted_to_paper:true` in the response + `[status LIVE→PAPER]` log); no new `uq_open_pos`. (CAT min-floor ERROR + dead-nested-route already verified resolved this session.)

---

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
