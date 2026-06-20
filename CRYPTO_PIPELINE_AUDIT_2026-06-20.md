# CRYPTO PIPELINE AUDIT — 2026-06-20 (Opus 4.8)

> Phase 1 (evidence-backed findings) + Phase 2 (prioritized revamp plan).
> **No code changed.** Every claim below is tagged **VERIFIED** (live DB / log / code path I read) or **ASSUMED**.
> Methodology lens: "would I trade real capital on this?" — and explicitly separating a **REAL EDGE problem** from a **VALIDATION/CALCULATION ARTIFACT** (this system has a documented history of artifacts silently filtering good strategies: √252 annualization, per-symbol validation of basket strategies, trade-count floors mis-tuned for low-frequency strategies). The crypto equivalents are the core of this audit.

---

## 0. HEADLINE — the crypto book is dark

**VERIFIED (DB):**
- `strategies`: **397 total, 0 crypto in ANY status** (PAPER/LIVE/BACKTESTED). The crypto book is completely empty.
  `SELECT count(*) ... WHERE (symbols->>0) IN ('BTC',...) = 0`.
- Last crypto **order_submitted = 2026-05-25**; last crypto **trade entry = 2026-05-25**. **~26 days with zero crypto trading.**
- Lifetime crypto realized P&L (trade_journal): **ETH −$923 (19 tr, 52.6% WR), BTC −$734 (11 tr, 45.5%), SOL +$186 (4 tr), AVAX +$247 (2 tr), DOT −$57 (1 tr), LINK 1 open.** Net ≈ **−$1.28K**, concentrated in BTC/ETH.
- Recent funnel (signal_decisions, crypto): **proposed 107 → wf_rejected 101 → wf_validated 9 → activated 9 → cross_validation 14 REJECTED (0 passed) → order_submitted 3.**
- Activation trend by week (strategy_proposals, crypto): proposed 3156→2216→1382→124→225→181→26→50; **activated 188→94→146→11→2→3→3→0.** Crypto activation has decayed to **zero** over the last ~5 weeks.

**The pipeline is alive (it proposes ~100 crypto candidates/cycle) but ~95% die at walk-forward, the ones that survive are killed at family cross-validation, and the net result is an empty book.** The interesting part — and the reason this matters under the PAPER-stage "maximise data breadth" mandate — is that **most of the killing is being done by validation artifacts, not by a real-edge verdict.**

---

## 1. WHAT IS ACTUALLY CORRECT (verified — do not "fix" these)

Before the bugs, the things a quant audit confirms are *fine*, so we don't waste a revamp on them:

- **C8 — Crypto Sharpe annualization is CORRECT.** VERIFIED `strategy_engine.py:3618-3651`: 1h crypto passes through vectorbt √8760, 4h passes through √2190, 1d uses vectorbt freq=`1d`→√365. These are the right 24/7 bases; crypto is *not* hit by the equity √252/√365 bug. Equity branches rescale down (1764/8760, 441/2190) — correct. **This is the one place I expected the classic artifact and it isn't there.**
  - *Minor inconsistency (P3):* the MC bootstrap annualizes crypto **per-trade** returns with `trades_per_year=(n/window)*252` (`strategy_proposer.py:2321`), i.e. 252 not 365 — slightly *over-conservative* for crypto. Low impact; note for the recalibration pass.
- **Data quality is excellent.** VERIFIED (DB): all 6 symbols × {1h,4h,1d} from **Binance**, 2023-09 → now, **0 duplicate (symbol,date,interval) rows**, fresh (1h age 2h, 4h age 6h). Source routing is correct (Binance, not Yahoo). No provisional intraday "today" 1d bar (last 1d bar = 2026-06-19, not -06-20) → **no look-ahead on the daily series.** `binance_ohlc.py` is sound.
- **Cost modeling is baked in.** VERIFIED `strategy_engine.py:3547` (`from_signals` fees=0) + manual deduction `:3852` (commission ×2 for entry+exit). `autonomous_trading.yaml` crypto `commission_percent: 0.0075` → **1.5% round-trip is in net `test_return`.** BTC/ETH get a per-symbol slippage override (0.0005). The `_MIN_CRYPTO_TP=0.06` fee-floor (`template_catalog.py:101`) correctly drops sub-3%-round-trip crypto templates at load.
- **Risk caps are coherent.** Crypto SL 8% / TP 20% (`autonomous_trading.yaml:554`), ATR-SL clamp 15% (`sl_caps.py:46`), graduation SL cap 0.08×1.20 (`graduation_gate.py:1399`), vol-scaling ~0.27× for 60%-vol crypto (`risk_manager.py:1119`). Parkinson high-low vol estimator used for crypto, annualized √365 (`risk_manager.py:174`) — correct.
- **24/7 handling is correct in the market-hours layer.** `market_hours_manager` maps CRYPTOCURRENCY→CRYPTO_24_7, `_check_crypto_24_7`→always True; weekend/holiday subtraction explicitly skips crypto (`market_data_manager.py:484`). No equity market-hours gate wrongly blocks crypto signal generation.

---

## 2. FINDINGS — ranked, with evidence, root cause, and ARTIFACT vs EDGE

### C1 — [P0 · ARTIFACT] Crypto walk-forward validates on 1–3 trades per window with wildly inflated per-bar Sharpes
**Root cause:** The crypto WF test windows are short (`asset_class_windows`: crypto_1d test=90d, crypto_4h=60d, crypto_1h=45d) and the per-window Sharpe is vectorbt's **per-bar, flat-bar-inclusive** Sharpe. For low-frequency crypto templates that fire 1–6×/window, the equity curve is flat on most bars, so mean/std per-bar is tiny-over-tiny and ×√365 explodes into Sharpe 2.5–5 **on 1–4 trades**. That number is not a tradeable Sharpe — it is the crypto analog of the √252 / flat-bar artifact.

**Evidence (VERIFIED, log + DB):** `Crypto Crash Recovery SOL` rolling WF, 2026-06-20 13:43:
```
Window 1/3 (2023-09→2024-02): train_S=0.51 test_S=3.45 overfitted=False trades=1
Window 2/3 (2024-11→2025-04): train_S=-0.01 test_S=4.08 overfitted=False trades=3
Window 3/3 (2026-02→2026-06): train_S=-3.23 test_S=2.57 overfitted=False trades=1
```
Family-rescue breakdowns show the same: BTC `test_sharpe 5.04 on 4 trades, test_return 2.0%`; ETH `2.83 on 2 trades`; LINK `2.91 on 1 trade`. **A Sharpe of 3–5 attached to 1–4 trades and ~2% return is noise dressed as signal.**

**Edge vs artifact:** Pure artifact in the *metric*. It does NOT mean these strategies have edge (they mostly don't — see C5); it means the **gating metric is too noisy to discriminate edge from luck for crypto**, so the funnel's verdicts are driven by noise in both directions.

---

### C2 — [P0 · ARTIFACT] The `(test−train) ≤ 1.5` consistency gate structurally rejects crypto's own best-window picks
**Root cause:** For crypto, the engine runs *rolling* WF and deliberately reports the **best passing window's test Sharpe** as `rep_test_sharpe` paired with **that window's train Sharpe** (`strategy_engine.py:2156-2196`). The proposer then applies a `(tes − ts) ≤ 1.5` consistency gate on the primary/test-dominant/excellent-OOS paths (`strategy_proposer.py:2560,2588,2606`). Because crypto per-bar Sharpes are noisy (C1), the best window almost always has a large test-vs-train spread, so **the engine's selection and the proposer's gate fight each other** — the engine hands the proposer exactly the spread the proposer rejects.

**Evidence (VERIFIED):** Crash Recovery SOL passed rolling WF `3/3 windows … → PASS`, produced `rep_test=4.08 rep_train=-0.01`, then was logged in signal_decisions as
`wf_rejected … below_thresholds (train=-0.01 test=4.08 ret=0.24% wr=66.67%)` — i.e. killed solely because 4.08−(−0.01)=4.09 > 1.5. The consistency gate is calibrated for the equity Sharpe range (~0.5–2); on crypto's noisy 2.5–5 it is a near-deterministic reject.

**Edge vs artifact:** Artifact (the gate is reacting to C1's noisy metric, not to a real regime-luck signal). The *intent* (catch regime luck) is valid; the *implementation on a per-bar crypto Sharpe* is not.

---

### C3 — [P0 · ARTIFACT + ARCHITECTURE] The crypto family cross-validation rescue ("B-5") is structurally impossible to pass
**Root cause (two compounding):**
1. **Quorum can't form.** The family gate requires **≥4 of 6** universe symbols to clear a minimal bar *in the same cycle* (`strategy_proposer.py:2705`, `FAMILY_MIN_PCT=4/6`). But the proposer's per-(template,symbol) dedup + round-robin emits **~1 family symbol per cycle**, so the other 5 are `not_proposed` and can never count. 4/6 is unreachable by construction.
2. The 1 symbol that *is* proposed gets `overfitted=true` on the C1 noisy Sharpe.

**Evidence (VERIFIED, signal_decisions.decision_metadata):** **14/14 cross_validation rows REJECTED, 0 passed, all-time.** Every breakdown shows 5/6 `"status":"not_proposed"`, e.g.:
- `Crypto BTC Follower 4H` — `0/6 cleared`; only BTC has a result (`overfitted:true`), ETH/SOL/AVAX/LINK/DOT `not_proposed`.
- `Crypto BTC Follower Daily` — `1/6 cleared` (BTC cleared, test 3.42/train 1.35/4 trades), other 5 `not_proposed`.
- `Crypto Cross-Sectional Momentum` — `0/6`, only ETH present (`2.83 on 2 trades, overfitted:true`).

**Edge vs artifact:** Architecture bug (quorum design vs proposer emission cadence) layered on the C1 artifact. This is the direct analog of the documented **"per-symbol validation of basket strategies"** failure. The BTC-follower / cross-sectional templates are *exactly* the diversifying, basket-level edges PAPER should be collecting, and they are 100% blocked.

---

### C4 — [P1 · ARTIFACT] Rolling-WF overfit verdict is driven by the same noisy per-window Sharpe
**Root cause:** `overall_overfitted` = weighted vote where each window "passes" iff `not is_overfitted AND test_sharpe>0` (`strategy_engine.py:2077-2093`), and per-window `is_overfitted` is the train-vs-test degradation rule (`:1839-1869`) computed on the C1 per-bar Sharpe. With 1–4 trade windows the train Sharpe routinely flips negative (e.g. window train=−3.23), so the degradation/`train>0 & test<0` rules mis-fire and the recency-weighted 3/4 quorum fails. The dominant recent crypto WF reason in DB is literally `tv=True tev=True het=False overfitted=True`.

**Evidence (VERIFIED):** recent `wf_rejected` reasons cluster on `overfitted=True` and `het=False` (insufficient trades) together — both downstream of C1 (short windows → few trades → noisy Sharpe → flips the overfit/quorum logic).

**Edge vs artifact:** Artifact. Same root as C1/C2.

---

### C5 — [P1 · REAL-EDGE blind spot] The funnel never gates crypto on cost-adjusted per-trade edge — only on the noisy Sharpe
**Root cause:** `edge_ratio` (gross-per-trade vs round-trip-cost) **is computed but is explicitly observability-only — it gates nothing** (`strategy_proposer.py:2452-2470`, comment: "does NOT gate any acceptance decision"). So the crypto accept/reject decision rests on Sharpe + consistency + win-rate (all C1-contaminated) and a `min_return ≥ 0` floor. Net `test_return` IS cost-inclusive (1.5% round-trip is deducted), but a *total* return floor of ~0 over a 90d window does not enforce **edge-per-trade > cost-per-trade**.

**Why it matters (the trader's point):** Crash Recovery SOL had net `test_return 0.24%` over 90 days — genuinely **no real edge** (0.24% gross can't survive 1.5% round-trip). It *was* rejected — but by the C2 Sharpe-consistency artifact, not by economics. The danger is symmetric: (a) a thin-economics strategy with a lucky high per-bar Sharpe can *pass* gates it shouldn't, and (b) a real-edge low-frequency strategy with a noisy Sharpe gets *rejected*. **We currently cannot tell "thin economics" from "noisy Sharpe" anywhere in the crypto funnel.**

**Edge vs artifact:** This is the *fix that lets us distinguish the two.* Proper crypto gating must be **per-trade, cost-net** (the MC bootstrap already uses per-trade returns — it's the right substrate), with the per-bar Sharpe demoted to observability.

---

### C6 — [P2 · DATA] Crypto 1d freshness SLA (30h) is tighter than a daily bar's natural age; age measured from bar OPEN not CLOSE
**Root cause:** `_FRESHNESS_MAX_AGE_HOURS[("1d","crypto")] = 30` (`market_data_manager.py:373`, rationale "24/7 shouldn't lag"). But a daily bar is published once/day and is timestamped at its **open** (00:00 UTC). The freshest *closed* daily bar is therefore 24h + time-of-day old → up to ~48h just before the next close. **VERIFIED:** BTC 1d `last_bar=2026-06-19 00:00`, age **38.0h > 30h** right now. A crypto-daily strategy would be marked stale and blocked for most of each UTC day.

**Edge vs artifact:** Validation artifact (false-stale). Secondary today (no crypto-daily strategies are live), but it would silently suppress crypto-daily signals the moment C1–C3 are fixed and crypto-daily strategies activate. Fix = measure age from bar **close** (open+interval) and/or set crypto 1d SLA to ~48h like `stock_etf_index`.

---

### C7 — [P2 · EXECUTION] Crossover-entry / state-exit asymmetry still closes crypto positions within one bar
**Root cause:** Mixed entry/exit conditions (entry `CROSSES_ABOVE`, exit state `EMA(8)<EMA(21)`) close a freshly-opened position on the next quick-update cycle — the exact Stage-2 defect from the 2026-05-25 audit. The min-hold guard proposed there is **not visibly effective.**

**Evidence (VERIFIED, trade_journal):** ETH LONG 2026-05-25, **hold_time 0.2h (12 min)**, exit reason `Strategy exit signal: EMA(8) < EMA(21) OR RSI(14) < 40`, P&L −0.05%. Also `weak_watchlist_loser` force-closures (×3) and a 12-min flip indicate exit logic still mis-fires intrabar.

**Edge vs artifact:** Execution/template defect (destroys the data point and biases paper stats). Verify whether the 2026-05-25 min-hold guard was ever deployed.

---

### C8 — [P3 · INFO] Self-reinforcing blacklist lockout (TSLA-class), downstream of the artifacts
**Evidence (VERIFIED, EC2 config):** `.rejection_blacklist.json` holds **~73 crypto (template,symbol) combos** (12–13 per symbol, 14-day cooldown); `.zero_trade_blacklist.json` ~15. Not the *binding* constraint today (proposals still flow), but every artifact-driven rejection (C1–C4) feeds the blacklist, which then suppresses re-proposal — the same recency-lockout pattern the equity side already fixed with decay. Once C1–C5 land, the crypto blacklist should be cleared so good combos aren't serving a cooldown earned by an artifact.

---

### C9 — [P3 · CONFIG HYGIENE] Stale/duplicate crypto universe in autonomous_trading.yaml
**Evidence (VERIFIED, code):** the proposal universe comes from `get_tradeable_symbols(DEMO)` → SymbolRegistry → `config/symbols.yaml` = **6 symbols** (BTC/ETH/SOL/AVAX/LINK/DOT). The `symbols: … crypto: [BTC, ETH]` block in `autonomous_trading.yaml:529` is **not** read by `_load_trading_symbols` (`strategy_proposer.py:1504`) — it's legacy/inconsistent. Confirm no other consumer trusts it (e.g. a regime/universe helper) before deleting, but it's a footgun. Crypto-cycle ±5 and crypto conviction are correctly BTC/ETH-only via `get_crypto_cycle_phase` — that scoping is intentional, not this block.

---

## 3. ROOT-CAUSE SUMMARY (one sentence)

> **The crypto data, costs, annualization, 24/7 handling, and risk caps are sound. The crypto pipeline is empty because the RESEARCH-stage validation layer evaluates crypto on a per-bar, flat-bar-inclusive Sharpe over windows so short that strategies are judged on 1–4 trades — and then a stack of equity-calibrated gates (consistency ≤1.5, rolling-overfit quorum, and an unreachable 4/6 family quorum) react to that noise. The system is filtering on a noisy metric instead of on cost-net per-trade edge, so it can neither admit good low-frequency crypto edges nor honestly reject thin ones.** This is a validation/calculation-artifact failure (the documented AlphaCent failure class), not a "crypto has no edge" verdict.

---

## 4. PHASE 2 — PRIORITIZED REVAMP PLAN (proper, root-cause; no stopgaps)

Stage tags per the steering lifecycle: **PAPER** items widen data breadth (the immediate need — the book is empty); **RESEARCH** items fix the statistical bar itself; **LIVE** items touch real capital. None of the below changes CIO-owned sizing/quotas/graduation thresholds — those are flagged where relevant.

| # | Fix (root cause) | Stage | Blast radius | Sign-off needed? |
|---|---|---|---|---|
| **R1** | **Gate crypto WF on a per-trade, cost-net Sharpe + edge-ratio, not the per-bar flat-inclusive Sharpe.** Reuse the MC per-trade machinery as the canonical crypto WF statistic; demote the vectorbt per-bar Sharpe to observability for crypto. Makes C1/C2/C4 verdicts meaningful. | RESEARCH | Medium — crypto WF acceptance path only (branch by asset class; equity untouched). | **Yes — architectural.** |
| **R2** | **Lengthen crypto WF test windows so strategies are judged on a real trade sample.** Move daily/4h crypto to long-horizon windows by default (the low-freq long-horizon plumbing already exists: `_LONGHORIZON_WINDOW_FALLBACK train=1095/test=730`); require a minimum trade sample at the strategy's natural cadence rather than a short calendar window. Directly fixes C1's "1–4 trades/window". | RESEARCH | Medium — `_select_wf_window` crypto keys + rolling-window spans. | **Yes — architectural.** |
| **R3** | **Make the consistency gate scale-aware (or apply it on the per-trade Sharpe from R1).** A fixed `≤1.5` absolute spread is invalid on a metric that ranges 2.5–5; express it as a ratio or compute it on the R1 statistic. Fixes C2. | RESEARCH | Small — one predicate, branch for crypto. | **Yes (couples to R1).** |
| **R4** | **Fix the family cross-validation quorum so it can actually form.** Either (a) evaluate the family across the rolling **WF ledger / cached results** for all 6 symbols (not just symbols proposed this cycle), or (b) propose the whole `family_universe` together when a `requires_cross_validation` template is selected. Fixes C3's "5/6 not_proposed". | RESEARCH | Medium — proposer emission for cross-val templates + the family aggregation read path. | **Yes — architectural.** |
| **R5** | **Crypto 1d freshness: measure age from bar close (open+interval); set crypto-1d SLA to ~48h.** Fixes C6 false-stale before crypto-daily strategies come back online. | PAPER/LIVE (signal-gen + TSL) | Small — `_FRESHNESS_MAX_AGE_HOURS` + age computation. | No (but verify TSL freshness path). |
| **R6** | **Enforce the crossover/state exit-symmetry + an effective min-hold guard for crypto.** Audit all 90 crypto templates for `CROSSES_ABOVE` entry paired with state `<` exit; confirm/repair the 2026-05-25 min-hold guard. Fixes C7 intrabar flips. | PAPER (data quality) | Medium — template catalog + engine exit path. | No (template), **Yes if engine exit logic changes.** |
| **R7** | **Clear artifact-earned crypto blacklist entries after R1–R4 deploy** so good combos aren't serving a cooldown from an artifact rejection. Fixes C8. | PAPER | Small — one-time prune + let decay run. | No. |
| **R8** | **Config hygiene:** confirm-then-remove the dead `crypto:[BTC,ETH]` block (C9); align MC crypto annualization to 365 (C8-minor). | RESEARCH | Trivial. | No. |

**Suggested sequencing (smallest-blast-first, each verified live before the next):**
1. **R1 + R3 together** (the metric + the gate that consumes it) — this is the keystone; it makes every downstream verdict trustworthy.
2. **R2** (windows) — gives R1 a real sample to work on.
3. **R4** (family quorum) — unblocks the diversifying basket edges.
4. **R7** (blacklist clear) — let the now-correct funnel re-evaluate.
5. **R5, R6, R8** — independent hardening, can land any time.

**Explicitly NOT proposed:** lowering `min_trades_crypto_*`, `min_sharpe_crypto`, or relaxing MC floors as a shortcut — that would be a stopgap that admits noise. The proper fix is a *better metric over a longer window* (R1+R2), not a *lower bar on a bad metric*.

---

## 5. WHAT I VERIFIED vs ASSUMED
- **VERIFIED via live DB:** empty crypto book; funnel counts; per-symbol P&L; proposal/activation weekly trend; cross-validation breakdowns; data coverage/freshness/no-dupes; execution/exit-reason detail.
- **VERIFIED via live logs:** rolling-WF per-window Sharpes & trade counts; the Crash Recovery SOL PASS→below_thresholds sequence.
- **VERIFIED via code (local workspace):** Sharpe annualization branches; consistency/overfit gates; family-rescue quorum; cost deduction; freshness SLA table; direction-aware thresholds (no crypto branch); proposal-universe source.
- **ASSUMED / to confirm in Phase 3 before touching:** that the 2026-05-25 min-hold guard is deployed (C7); that nothing else consumes the dead yaml crypto block (C9); exact rolling-window span behavior on the long-horizon path for 4h/1h crypto (R2 design).
