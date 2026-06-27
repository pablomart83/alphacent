# AlphaCent — Weekly Audit (week ending Sat 2026-06-27)

**Scope:** verify every change shipped 2026-06-20→27 against LIVE DB / logs / code / git, review system performance, judge whether the calls were sound. Read-only review — nothing was changed.

**Headline:** All 9 changes are deployed and behaving as designed. None caused a regression. The week was a **losing week driven by a market pullback** (SPY ~−3.4%, regime flipped trending_up_weak → ranging_low_vol), not by the changes — and the biggest live-behavior change (the trailing-stop retune, #6) appears to have *mitigated* the drawdown. The single most important context for judging the regime-dependent work (#7, #8): **the confirmed-uptrend has ended**, so those two changes are now correctly inert and their uptrend-calibrated evidence is stale until the regime returns.

Git: HEAD = `f2024e5` (matches expected), local == origin/main, all 9 changes present in `git log --since=2026-06-20`. Service `active`, `/health` OK, last cycle (17:27 UTC today) completed successfully. EC2 root is not a git repo (deploy target) — deployed code verified by reading files directly.

---

## (a) Per-change status

| # | Change | Status | Evidence |
|---|---|---|---|
| 1 | Meta-label re-proof (ml1.1.0) | **DEPLOYED & CORRECTLY DORMANT** | Re-proof re-run live (3,531 trades) |
| 2 | Per-gate observability scoreboard | **DEPLOYED & WORKING** | Fresh snapshot, off request-path, verdicts coherent |
| 3 | MAE/MFE → SL/TP recommender | **DEPLOYED & WORKING** | Pending queue clean, no dup-reproposing, SOXL no-rec |
| 4 | DSR gate (observe-only) | **DEPLOYED, OBSERVE-ONLY — but REDUNDANT at min_dsr=0.9** | Fires every cycle, not rejecting, would-filter = 0 always |
| 5 | Approval rail (Path A) | **DEPLOYED & WORKING** | Binding proven live; overrides match; revert works |
| 6 | Trailing-stop ladder retune | **DEPLOYED & WORKING** | Give-back halved; errors=0/3,900 cycles; no whipsaw spike |
| 7 | Pullback dip-buy exemption | **DEPLOYED — INERT BY REGIME** (not observable this week) | Regime left confirmed-uptrend; correctly did not fire |
| 8 | Live-pass dip-buy softening | **DEPLOYED — INERT BY REGIME** (not observable this week) | No live entry in a moderate/severe pullback during uptrend |
| 9 | LIVE 20% symbol cap | **DEPLOYED & WORKING** (with a concentration finding) | 15% blocks all pre-deploy; 20% cap now active; demo unchanged |

### #1 — Meta-label re-proof (ml1.1.0) — DEPLOYED & CORRECTLY DORMANT
Re-ran `scripts/verify_meta_label_edge.py` on EC2 against live trades:

| class | n | base WR | OOS AUC | precision lift | verdict |
|---|---|---|---|---|---|
| stocks | 2,398 | 0.373 | **0.513** | +0.013 | NO CLEAR EDGE |
| etfs | 1,113 | 0.337 | **0.542** | +0.009 | NO CLEAR EDGE |
| commodities | 184 | 0.250 | 0.339 | +0.083 | NO CLEAR EDGE |
| indices | 164 | 0.348 | 0.375 | −0.181 | NO CLEAR EDGE |
| forex / crypto | 55 / 38 | — | — | — | SKIP (n<120) |

AUC is at/near random everywhere; the only class to clear AUC 0.53 (etfs, 0.542) has a negligible +0.009 precision lift and broken calibration. **No hot-path import** of `meta_label_trainer` anywhere in `execution/`, `strategy/`, `core/`, `risk/`; **no persisted `.pkl` model**; `FEATURE_SPEC_VERSION="ml1.1.0"` deployed. Conclusion holds: no edge, nothing loaded or enforced. The model has grown slightly less-bad with more data (stocks 0.463→0.513, etfs 0.488→0.542 vs last week) but remains un-actionable.

### #2 — Per-gate observability scoreboard — DEPLOYED & WORKING
- **Fresh & off the request path:** snapshot `config/.gate_scoreboard.json` computed_at **19:06 today** (`compute_seconds 0.6`, precomputed to file); the reload-on-newer fix (`8e604e2`) is serving it. Endpoint returns 401 to an unauthenticated curl (correct — the frontend authenticates).
- **`account_type` populating:** demo 16,915 / live 1,371 over 7d on `signal_emitted`/`gate_blocked`/`order_submitted`; research stages (`proposed`/`wf_*`/`activated`) are NULL by design (account-agnostic). **Minor gap:** `order_filled` rows are NULL and `order_submitted` is only partially populated — those two writers weren't fully threaded with `account_type`. Low severity (the counterfactual uses `signal_emitted`/`gate_blocked`).
- **Verdicts:** **Conviction = HELPS** still (separation +0.034: blocks −4.9% signals while passing −1.6%). **Pullback is now `insufficient_data`**, not HURTS — its block volume collapsed from ~16k (last week) to **652**, and the blocked cohort has no computable forward return. The collapse is consistent with the regime leaving uptrend + the #7 exemption.
- **Regime signal:** the demo passed-cohort 5-bar forward return **flipped from +6.13%/81% win (last week) to −1.57%/36.8% win** — the scoreboard is correctly capturing the pullback.

### #3 — MAE/MFE → SL/TP recommender — DEPLOYED & WORKING
- **Pending queue is sane:** ENPH (tighten 6%→1.2%), MU (widen 6%→8.8%), plus new CAT (→2.9%), XLK (→4.1%), `ATR Dynamic Trend Follow::etfs` (→3.4%), `EMA Pullback Momentum::etfs` (→4.1%). **No duplicate pending rows. ADX/Keltner are NOT re-appearing** (the `45cc670` current-reads-from-active-override fix works). **SOXL correctly produces no rec** (its 15% live stop is already correct).
- **Minor data-hygiene note:** two *applied* rows exist per ADX/Keltner scope (ids 19+24, 20+25) — an artifact of last week's approve→revert→re-approve testing, not active re-proposing. Harmless (the override table has exactly one active row per scope).
- **Watch item:** the new pending recs are mostly **aggressive tightens (1.2–4.1% SL)**. Tightening stops to 1–4% — especially right after a pullback — risks noise stop-outs. These need CIO scrutiny before approval (see recommendations).

### #4 — DSR gate (observe-only) — DEPLOYED, but REDUNDANT at current calibration
Fires every proposer cycle: `DSR gate (observe-only, n_trials=192, min_dsr=0.9): scored N … 0 below threshold (would filter). pass-rate X→X`. It is **not rejecting** (pass-rate unchanged every cycle) and `wf_dsr` is stored in strategy metadata. **Key finding:** across ~2 weeks of cycles, the would-filter count is **0 in every single cycle** — at `min_dsr=0.9` the gate would remove nothing because every MC-bootstrap survivor already clears DSR 0.9. Enabling it as-is would be a no-op; it only adds value at a materially higher threshold (see recommendations).

### #5 — Approval rail (Path A) — DEPLOYED & WORKING
- **Active overrides match the claim:** `ADX Trend Following::stocks` SL 9.0%/TP 15% (id 5), `Keltner Channel Breakout::stocks` SL 7.94%/TP 15% (id 4); `AMD` → `live_strategies` SL 7.5%. **Exactly one active override per scope_key** (no dup-apply). Revert works (reverted rows present in both tables, and the apply→revert path is correct in `param_overrides.py`).
- **Binding proven live:** `resolve_override()` against the live DB returns the correct SL for every stock template proposed this week (DELL/AMD/GS/PANW → 0.0794/0.09). The ground-truth proof: strategy **"ADX Trend Following C LONG" (created 2026-06-23 12:15) carries SL=0.09, TP=0.225** — exactly the override value plus the R:R guard (TP forced to SL×2.5). Default would be 0.06/0.15.
- **Why no recent binding log:** logs only reach back to 06-24 15:38 (fast rotation); the one provable binding was 06-23. No ADX/Keltner *stock strategy persisted* in the 06-24→27 window (they were proposed but didn't activate), so there was nothing to log. Not a no-op.

### #6 — Trailing-stop ladder retune — DEPLOYED & WORKING (biggest live change, audited hardest)
Deployed 2026-06-23 15:39 UTC. Deployed values match local (breakeven stock 0.02 / leveraged 0.03; profit-lock leveraged 0.05/0.025; ATR mult stock 1.25 / leveraged 1.0).

**Give-back query, TSL-breach exits with tracked MFE:**

| window | n | avg MFE | avg realized | win rate | peaked-then-loss | give-back |
|---|---|---|---|---|---|---|
| PRE (30d before deploy) | 92 | +5.09% | −1.60% | 26.1% | **51** | ≈6.7 pts |
| POST (deploy → now) | 80 | +2.72% | −0.69% | 36.3% | **25** | ≈3.4 pts |

Give-back roughly **halved**; realized improved (−1.60→−0.69), win rate up (+10 pts), peaked-then-loss halved — and this *despite a worse regime post-deploy*. **No mass-stopout/whipsaw regression:** daily TSL-breach counts (32–78/day) track the pullback, not a tightening-induced spike, and TSL-exit outcomes improved. **`errors=0` across all 3,900 TSL cycle summaries.** The Jun-23 ~13:00 UTC stop-out batch (190 exits) occurred *before* the 15:39 deploy under the old ladder; it was mostly small TSL losses plus a few −12 to −18% gap-throughs on legacy wide-stop positions (the retune's earlier breakeven would have protected the moderate give-backs, not the gap-downs).
**Caveat:** the post window is only ~4 days and in a weaker regime, so part of the lower MFE is regime, not the retune. Re-measure after an uptrend stretch.
**Nit:** the docstring still says "+3% → breakeven" while the stock value is now 0.02 (+2%).

### #7 — Pullback confirmed-uptrend dip-buy exemption — DEPLOYED, INERT BY REGIME
Deployed (markers present in `trading_scheduler.py` ×6, `market_analyzer.py` ×3). **No `dip-buy exemption` log fired this week** — and that is correct: the regime moved from `trending_up_weak` (06-19→23) to **`ranging_low_vol` (06-24→27)**, so the confirmed-uptrend precondition (broad 50d ≥ +3%) wasn't met and the exemption stayed inert. This is exactly the "stays inert in non-uptrend regimes" behavior we wanted — but it means we have **no live firing evidence** this week; its only support remains the backtest (would-exempt cohort +6.5% fwd / 78% win).

### #8 — Live-pass dip-buy softening (0.75× floor, NEW-02) — DEPLOYED, INERT BY REGIME
Deployed. Did not fire — no live entry occurred during a moderate/severe pullback while in a confirmed uptrend (the regime had already left uptrend by the time the pullback deepened). Intraday/momentum/shorts retaining full 0.60× and leveraged-skip are coded correctly; not exercised this week.

### #9 — LIVE position-size gate → 20% symbol cap — DEPLOYED & WORKING (+ concentration finding)
`_effective_position_cap_pct(is_live)` returns `live_trading.symbol_cap_pct` (0.20) for live and `max_position_size_pct` (0.15) for demo; `check_position_limits` sums existing same-symbol exposure (cumulative) vs `equity × cap`.
- **Pre-fix proof:** 75 LIVE blocks reading "max position size limit of **15.0%**" — **all on 06-23**, before the 06-24 13:36 deploy. **Zero after deploy.** Post-deploy the live cap operates at **20%** via the symbol-concentration path (`symbol_cap_exhausted (MU at $3575/$2073…)`, where $2073 ≈ 20% of equity). Demo path unchanged.
- **Concentration finding:** **MU has 3 open live positions totalling ~$2,362 ≈ 23% of the $10k virtual book — over the 20% per-name cap.** The cap blocked MU repeatedly, but 3 separate-strategy MU positions stacked across cycles (06-25/06-26) because the per-symbol cap isn't enforced cumulatively when siblings open in different cycles (the pre-existing "concentration cap not enforced cumulatively across strategies" known issue, now sitting at a 20% ceiling). All 3 MU positions are underwater. Not a #9 regression — #9 correctly raised the ceiling — but a live risk to watch.

---

## (b) System performance — week over week

| | This week (06-20→27) | Prior week (06-13→20) |
|---|---|---|
| DEMO closed trades | 594 | 278 |
| DEMO win rate | 36.4% | 48.9% |
| DEMO realized P&L | **−$4,047** | +$10,795 |
| LIVE closed trades | 5 | 2 |
| LIVE win rate | 40% | 50% |
| LIVE realized P&L | **−$116** | +$98 |

- **Market:** SPY peaked ~754–757 (06-04/06-15), fell to **728.99 by 06-26 (~−3.4%)**, with a sharp 744→733 drop 06-22→23. Regime flipped `trending_up_weak` → `ranging_low_vol` (brief `trending_down_strong` 06-20/21).
- **DEMO book:** equity 569k (06-22 peak) → 544k (06-27), **−4.4%**, ~82 positions closed during the pullback; ~$7.7k realized losses booked 06-24→27.
- **LIVE book:** equity 10,865 (06-22 peak) → 10,243 (06-27), **−5.7%**, mostly *unrealized* (open book ~−$238). Still +2.4% vs the $10k virtual base. 10 open positions, ~$7.1k deployed (71%). Concentration: MU ~23%, AMD ~16%; semis/tech cluster (MU/AMD/SOXL/TQQQ + SPY) ~47% of the virtual book. The graduated test strategies are **net-negative lifetime (~−$560 across pairs; only PANW +$187 positive)** — expected for a small, recently-live book in its first real pullback, but worth monitoring.
- **Jun-23 stop-out batch:** 190 exits, the pullback's first leg, under the *old* TSL ladder (retune deployed 2.5h later). The retune would have locked breakeven on the moderate give-backs but not the −12/−18% gap-downs.

### Errors / health
TSL cycles `errors=0` (3,900). New error classes since the changes — **none caused by the 9 changes**:
- **06-22 00:15 UniqueViolation burst (13×)** — coincided with a service restart + `reconcile_on_startup` (the known A3 batch-create / duplicate-guard cascade, also seen 06-11/12). Self-resolved, demo-only signal-exec failures. Pre-existing fragility.
- **Daily fundamental-exit `InFailedSqlTransaction` (~12:36, incl. 06-25/26/27)** — the sector-rotation `pending_closure` batch runs on an already-aborted session → those fundamental exits **silently fail to write**. Pre-existing back to 06-01. Needs a `session_scope()` fix.
- **`Position.__init__() missing 3 args`** in the size-estimate endpoint (`strategies.py:4538`, today 19:03) — broken analytics endpoint, **not on the hot path**.
- **SPY weekend 1h "all sources failed"** — 79× on 06-21/22 only, **none on 06-27** — last week's fix appears to be holding now.
- Otherwise pre-existing noise only: FMP rate-limit pacing, transient eToro ReadTimeouts, ~22 "opening position disallowed for Sell" (eToro short-restricted instruments).

---

## (c) Regressions / silent no-ops / data-integrity issues

1. **None of the 9 changes regressed.** No silent no-op among them: #5's binding is proven live (the "missing logs" were rotation + low persisted-strategy volume, not a no-op).
2. **Data-integrity (pre-existing, not from this week):** the daily sector-rotation fundamental-exit batch fails on an aborted session — those exits are silently not applied. This is exactly the `InFailedSqlTransaction` class the steering flags as most dangerous; fix with `session_scope()`.
3. **Live MU over-concentration (~23% > 20% cap)** — cumulative per-symbol enforcement gap across separate-strategy entries.
4. **Minor:** scoreboard `account_type` not threaded on `order_filled`/`order_submitted` writers; broken size-estimate endpoint; #6 docstring stale (+3% vs code 0.02).

---

## (d) Were the decisions sound?

- **#1 meta-label (leave disabled):** Sound, and re-confirmed. Two independent feature enrichments both land at/below random. No reason to revisit until there's materially more LIVE data or a fundamentally different feature family. Do not wire.
- **#2 scoreboard:** Sound and already earning its keep — it's the instrument that *caught the regime flip* (passed-cohort return going negative). The Conviction=HELPS / Pullback-blocks-winners reads from last week directly motivated #7. Keep.
- **#3 recommender:** Sound design; the current-reads-from-override fix closed the dup-reproposing loop. But the new crop of **aggressive tighten recs (1–4% SL) is regime-sensitive** — they're fit on a window that now includes a pullback, and 1–4% stops would noise-stop trend strategies. Judge each on its own evidence; don't bulk-approve.
- **#4 DSR:** The decision to ship observe-only was right. The *evidence now says do not enable at 0.9* — it filters nothing. Either recalibrate to a threshold that actually discriminates (and re-observe), or accept that MC-bootstrap already covers this and shelve it. Don't flip `enabled:true` at 0.9.
- **#5 approval rail:** Sound. Mechanism verified end-to-end (resolve → bind → revert), envelope-guarded, one-active-per-scope. The right delivery layer for #3.
- **#6 TSL retune:** The highest-value call of the week, and the evidence a week later supports it (give-back halved, win rate up, no whipsaw, errors=0). The one honest caveat: it was validated in backtest then immediately met a pullback, so the live "post" sample is short and regime-skewed favourable-to-the-thesis (less give-back is partly smaller moves). Re-measure after an uptrend leg, but no reason to revert.
- **#7 / #8 (regime-dependent):** Both were sound *given* the confirmed uptrend they were built for — but **the regime has since flipped to ranging_low_vol**, so they're now inert and their backtested edge is unobserved live and temporarily stale. This is the "flag anything that would misbehave if the regime flips" item: they don't misbehave (they correctly go inert), but **do not treat them as validated until they fire and we see real dip-buy outcomes** in the next uptrend. If anything, the pullback is a reminder that loosening pullback protection is only safe while the 50d trend holds — the gating on `confirmed_uptrend` is doing its job.
- **#9 20% cap:** Sound and correctly scoped (live-only, demo untouched, CIO-configured). The raise itself is fine; the cumulative-enforcement gap it exposed (MU 23%) is the real issue to address.

---

## (e) Prioritized recommendations

**Fix (reliability / integrity):**
1. **Fundamental-exit `InFailedSqlTransaction` (daily).** Wrap the sector-rotation exit check in `session_scope()` (or rollback-on-checkout already covers it — confirm the check isn't reusing the poisoned main session). Sector-rotation fundamental exits are currently silently not firing. *(Path B, P1.)*
2. **Live MU concentration (~23% > 20%).** Make the per-symbol cap enforce cumulatively across same-cycle/sibling entries (count pending + just-opened siblings before sizing the next). Until fixed, CIO should consider trimming one MU live position — 3 correlated MU strategies underwater into a ranging regime is the concentration the cap is meant to prevent. *(P1.)*
3. **Thread `account_type` on `order_filled`/`order_submitted` decision writers** so the scoreboard's order-stage funnel is complete. *(P2.)*
4. **Repair the size-estimate endpoint** (`strategies.py:4538` — pass the required `Position` args / route through the typed-notional helper). *(P2, cosmetic but error-logging noise.)*

**Enable / decide:**
5. **DSR gate:** do **not** enable at `min_dsr=0.9` (no-op). Either set `min_dsr` from the observed distribution to a level that actually filters a few percent (then re-observe before enforcing), or formally shelve it as redundant with MC-bootstrap.
6. **SL/TP recs:** approve MU widen (6%→8.8%, well-evidenced, 37 trades) only if you want MU stops wider into a pullback — defensible given MU just took −9% hits; **hold/reject the aggressive tightens** (ENPH 1.2%, CAT 2.9%, XLK 4.1%, the two ETF templates) until they're re-evaluated outside the pullback window — 1–4% stops will noise-stop trend entries.
7. **ENPH** (recommended reject last week) — still reasonable to reject; the new 1.2% tighten is too aggressive to apply.

**Re-validate (regime):**
8. **#6 TSL retune** — re-run the give-back query after the next uptrend leg to separate the retune's effect from the pullback's smaller moves.
9. **#7 / #8 dip-buy exemptions** — keep deployed but treat as unproven-live; capture their first real firings (and the resulting trade outcomes) when the regime returns to a confirmed uptrend before relaxing pullback protection further.

**Watch:**
10. The live test book is net-negative lifetime and concentrated in semis/tech into a ranging/weakening regime. Capital is small, but this is the first real-money pullback for the graduated strategies — worth a close eye on whether the graduated pairs behave like their paper records.
