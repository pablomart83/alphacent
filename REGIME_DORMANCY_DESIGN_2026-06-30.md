# Regime Dormancy — Design Proposal (for CIO approval)

**Date:** 2026-06-30 · **Status:** DESIGN ONLY — no code shipped · **Decision owner:** CIO
**Replaces:** the "force shorts via directional quotas" idea (B1) and the regime-mismatch *retirement* behavior.

> This is the formal write-up the CIO asked for before any dormancy code. It defines the states, transition rules, hysteresis, re-validation-on-wake, cleanup, and what stays unchanged. Nothing here is implemented yet.

---

## 1. The core decision

**Separate "does this strategy have a proven edge?" (VALIDITY) from "is this strategy's regime happening right now?" (ACTIVITY). Retire only for loss of edge; use a DORMANT state for regime mismatch.**

Today the two are conflated: a validated strategy whose regime isn't current gets **retired** (deleted), then must be re-proposed and re-validated from scratch when its regime returns. Every regime change throws away validated edges and rebuilds them — wasteful, and it leaves the book with nothing to deploy when its one dominant style (long trend) is benched.

With dormancy, the book becomes a **portfolio of regime-tagged, validated strategies**, of which the regime-appropriate subset is ACTIVE at any time and the rest sleep — so the right strategies show up *organically* when their regime arrives, without forcing trades we don't believe in.

---

## 2. Current behavior (verified in code)

- `portfolio_manager.check_retirement_triggers_with_regime` (~line 1914): retires a strategy after **30+ days** of regime mismatch (`activation_regime` "TRENDING" vs market "RANGING", and vice-versa).
- `monitoring_service` (~line 213): retires regime-incompatible **BACKTESTED** strategies on a regime flip.
- Retirement is **destructive** — the strategy leaves the deployable set; the BACKTESTED-TTL cleanup later deletes it. Only `wf_validation_ledger` survives, so the edge must be re-proposed and re-validated to return.
- **Enabler already present:** every template is tagged with `market_regimes` (the regimes it suits), and strategies carry `activation_regime` / `macro_regime` in metadata. We already know which regime each strategy belongs to.
- **Status enum today:** `BACKTESTED / PAPER / LIVE / RETIRED`. There is **no** dormant state. `activation_approved` exists but is the CIO graduation gate — do **not** overload it.

---

## 3. Proposed model

### 3.1 States
Add an explicit, reversible dormancy dimension — a boolean flag + reason, orthogonal to the lifecycle status (preferred over a new status value, so PAPER/LIVE semantics are untouched):

- `regime_dormant: bool` (default `false`) on the strategy (metadata or a column).
- `dormant_reason`, `dormant_since`, `last_active_regime`.

A strategy is **ACTIVE** when `regime_dormant=false` and **DORMANT** when `true`. Dormant = validated, kept, but **excluded from signal generation**.

### 3.2 Transition rules (regime-driven, hysteresis-gated)
On each cycle, after regime detection produces a **confirmed** regime `R`:

- **Sleep:** a strategy whose `market_regimes` does **not** include `R` → set `regime_dormant=true` (if `confirm_sleep_days` of mismatch elapsed).
- **Wake:** a dormant strategy whose `market_regimes` **includes** `R` → set `regime_dormant=false` (after `confirm_wake_days` of the regime holding, and after the re-validation check in §3.4).
- **Never sleep a LIVE pair automatically.** LIVE is CIO-governed real capital; regime dormancy applies to RESEARCH/PAPER. A LIVE pair that no longer fits its regime is surfaced to the CIO (existing divergence/retirement review), not silently dormanted.

### 3.3 Hysteresis (anti-flapping)
Regime confidence is low and noisy (currently ~0.52). Toggling on every wobble would churn the book.
- Require the regime to be **confirmed stable** before any toggle: reuse `regime_history` + a confirmation window.
- Suggested defaults (CIO-tunable): `confirm_wake_days = 3`, `confirm_sleep_days = 5` (sleep slightly slower than wake, so a brief counter-move doesn't bench a still-relevant cohort). Asymmetric on purpose: waking fast captures the new regime's edge; sleeping slow avoids prematurely benching a cohort during a head-fake.
- A minimum dwell time per state (e.g. 2 days) to prevent rapid oscillation at a regime boundary.

### 3.4 Re-validation on wake (keeps rigor — no stale edges)
A strategy validated months ago shouldn't be trusted blindly when its regime returns (microstructure/parameter drift).
- Give dormancy a **max warm age** (e.g. 45–60 days). On wake:
  - if last validation is **within** max age → wake directly;
  - if **older** → route through a fast WF re-check (reuse the existing WF/MC pipeline) before activating; fail → retire (edge no longer holds).
- This preserves the steering "prove it through the normal path" rule — dormancy parks edges, it never resurrects an unproven one.

### 3.5 Cleanup exemption
The BACKTESTED-TTL cleanup must **skip `regime_dormant=true`** strategies (otherwise they'd be garbage-collected and we'd lose exactly what we're trying to keep warm). Dormant strategies are exempt from TTL deletion but **not** from edge-decay retirement (§3.6).

### 3.6 What stays unchanged
- **Performance / edge-decay retirement stays.** A strategy that, active, stops working on its own terms (Sharpe/DD/win-rate triggers in `check_retirement_triggers`) is still retired. Dormancy ≠ immortality.
- **Graduation (PAPER→LIVE) unchanged.** Dormancy is a RESEARCH/PAPER mechanism; it doesn't touch the graduation gate or live sizing.
- **Only the regime-mismatch *retirement* is replaced** — `check_retirement_triggers_with_regime`'s regime branch and the monitoring-service regime-retirement become the dormant toggle. The standard (non-regime) retirement path is untouched.

---

## 4. Why this replaces B1 (forcing shorts)

B1 (directional quotas / short floor) forces the book to hold shorts regardless of conviction. Dormancy achieves the goal — *the most appropriate strategies at any given time* — without forcing anything:
- Short and mean-reversion strategies that are **already validated** sit dormant during an uptrend and **wake on their own** when the regime turns to ranging/down — at the size their conviction earns, not a quota.
- No artificial short floor; no trading edges we don't believe in. The short book grows organically exactly when shorts are appropriate.

This depends on the proposer actually *producing* validated short/MR/regime-diverse edges to keep warm — i.e. the C1–C3 coverage work (regime-conditional validation + proposer coverage objective). Dormancy keeps them alive between their seasons; the proposer stocks the bench.

---

## 5. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Flapping at regime boundaries | Confirmation windows + min dwell time (§3.3) |
| Waking a stale edge | Re-validation-on-wake with max warm age (§3.4) |
| Dormant strategies silently rot | Edge-decay retirement still applies; max warm age forces re-proof |
| Mislabeled regime benches the wrong cohort | Asymmetric sleep>wake timing; LIVE never auto-dormanted; CIO review for LIVE divergence |
| Bench grows unbounded | Cap warm bench per (regime, style); proposer coverage objective targets gaps, not volume |
| Regime detector disagreement (the §1.6 incoherence in the investigation) | Dormancy must read ONE regime authority — fold this into the C4 single-authority work; do not wire dormancy to four conflicting signals |

---

## 6. Dependencies & sequencing

1. **Prereq (data):** fix proposal regime-stamping (`market_regime='unknown'` bug) and `regime_history` population — dormancy needs a trustworthy regime signal and per-strategy regime tagging.
2. **Prereq (coherence):** a single regime authority (C4) so dormancy toggles off one decision, not four conflicting ones. Until then, dormancy can run off `market_regime.current` (the 20d/50d detector) with the confirmation window as the guard.
3. **This design (dormancy mechanism):** states, toggles, hysteresis, re-validation, cleanup exemption.
4. **Pairs with:** proposer regime-coverage objective (C2) + regime-conditional validation (C1) — they stock the bench dormancy keeps warm.

---

## 7. Validation before shipping (per no-stopgaps rule)

- **Backtest:** replay the 2026-06-23 regime flip (and 2–3 historical flips across 2021–2026) and show the dormant→active rotation deploys regime-appropriate edges instead of going to cash — measured as capital utilization and forward risk-adjusted return vs the current retire-and-rebuild behavior.
- **Shadow:** run the toggle in observe-only mode first (log would-sleep/would-wake decisions without acting) for a few regime transitions; confirm no flapping and that the cohorts toggled match expectation.
- **Acceptance:** equal-or-better Sharpe/drawdown with materially higher deployment in non-uptrend regimes, and zero unintended LIVE toggles.

---

## 8. Decision requested

Approve this dormancy model (validity ⊥ activity; regime-mismatch → DORMANT not RETIRED; keep edge-decay retirement; re-validate-on-wake) as the direction, so it can be specced into a phased, backtested implementation. Confirm the CIO-tunable defaults to start from: `confirm_wake_days`, `confirm_sleep_days`, min dwell, and max warm age. Implementation will follow the normal one-change→deploy→verify flow and ship only after the §7 backtest/shadow passes.
