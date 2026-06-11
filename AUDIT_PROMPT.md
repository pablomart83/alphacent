# AlphaCent — Full Pipeline Forensic Audit Prompt

> Paste the block below into a fresh session to run a complete end-to-end audit.
> Keep this file updated as the system evolves so the audit always reflects reality.
> Last revised 2026-06-11 (added live-position 3-way reconciliation, position-close
> account-scoping, CIO-size authority, erroneous-close→duplicate cascade, ORM→dataclass
> field propagation, and gate-calibration-vs-deployment after a live duplicate-PANW incident).

---

```
You are performing a full end-to-end forensic audit of AlphaCent, a LIVE autonomous
trading platform on EC2 (Ubuntu, PostgreSQL 16, Python 3.11/FastAPI, React/Vite frontend).
REAL MONEY is at risk (~$1,300 real / ~$10K virtual live book, mirror ratio 0.127).
The goal: find every bug, race condition, data-integrity flaw, statistical-validity
error, accounting error, architectural gap, and silent-failure path across the ENTIRE
pipeline — exhaustively, with full investigation. This is a FULL-SYSTEM audit: do NOT stop
at the Intel findings page (the Intel checks are themselves under audit), and do NOT trust
the dashboard UI as ground truth (the UI AND the DB have both been wrong simultaneously
vs the real eToro account — see Ground Rule 2 and Category 1).

## GROUND RULES
1. Read Session_Continuation.md and .kiro/steering/trading-system-context.md FIRST. They
   are the source of truth for state, sprint history, and permanent operating rules.
2. VERIFY, DON'T TRUST — and triangulate three ways for anything live. Every "fix" claimed
   in Session_Continuation must be re-checked against live DB/logs/source — confirm it is
   actually deployed AND actually works. Past "fixes" have been dead code, half-wired, or
   based on a misdiagnosis. Treat the changelog as claims to falsify. For LIVE positions/
   P&L specifically, reconcile THREE sources — eToro (ground truth) ↔ DB ↔ dashboard UI —
   because all three have diverged at once (a buggy endpoint closed live positions in the
   DB while eToro still held them and the UI showed 0).
3. Trace, don't sample. Follow real data end-to-end and prove behavior with a log line,
   a DB query result, or an exact code path. State explicitly what you verified vs assumed.
4. Think like a quant running the book, not a coder. "Would I trade real money on this
   output?" is the bar. Stale data, silent failures, wrong P&L, wrong position size, and a
   DB that disagrees with the broker are existential.
5. PROPER ROOT-CAUSE FIXES ONLY — no patches, stopgaps, or skip-flags (steering rule).
6. Live system. Deploy workflow is mandatory: edit LOCAL → getDiagnostics → scp →
   systemctl restart → curl health → git commit/push. Never edit on EC2. Sync
   config/autonomous_trading.yaml FROM EC2 before reading it (the one file EC2 owns).
   A restart resets in-memory state (consecutive-miss counters, FIX-09 cooldown) — watch
   the first post-restart cycle, which has repeatedly produced transient errors.
7. Do NOT auto-retire live strategies, close/resize live positions, or take irreversible
   real-money actions without explicit confirmation. Flag them instead. (Reopening an
   erroneously-closed DB row to match eToro is a DB-only correction and is allowed.)

## ACCESS
- SSH: ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149
- DB:  ssh ... 'sudo -u postgres psql alphacent -t -A -c "SQL"'
- Logs: logs/errors.log (read FIRST), logs/alphacent.log, logs/cycles/cycle_history.log,
        logs/risk.log, logs/strategy.log
- Config sync: scp -i ~/Downloads/alphacent-key.pem ubuntu@34.252.61.149:/home/ubuntu/alphacent/config/autonomous_trading.yaml config/autonomous_trading.yaml
- Do NOT run inline python on EC2 (ssh ... 'python3 -c'). Use DB queries / log reads.
  To get eToro's live ground truth WITHOUT inline python, triangulate: account_info
  (mode='LIVE') positions_count + equity/balance, the live sync log line
  "Live position sync: N updated/created/closed" and "Syncing N positions from eToro",
  filled entry orders today, and positions.price_updated_at (the sync stamps this on
  positions present on eToro this cycle).

## LIVE POSITION RECONCILIATION (DO THIS EARLY — it is the highest-value P0 check)
Before anything else for live capital, reconcile the live book three ways:
  - eToro: account_info.positions_count (mode='LIVE') and the per-symbol invested ≈
    equity−balance; the live sync's "Syncing N positions from eToro".
  - DB: positions WHERE account_type='live' AND closed_at IS NULL.
  - UI: the dashboard live positions view.
Any mismatch in COUNT, SYMBOL, or SIZE is a P0. Then for each open live position confirm
its size equals the CIO-approved real $ (live_strategies.position_size) ÷ mirror_ratio —
a position smaller/larger than the CIO approval is a sizing bug (see Category 5).

## THE LIFECYCLE (authoritative — audit every transition for correctness & account scoping)
Status flow:  PROPOSED → BACKTESTED → PAPER → LIVE   (terminal: INVALID, RETIRED)
- "Research" is NOT a stage — it is running the autonomous cycle (scheduled ~once/day or
  manual). It emits PROPOSED strategies, runs them through WF → MC → conviction.
- ACTIVATION = passing the autonomous cycle → status BACKTESTED with activation_approved=True.
  Failing the cycle → INVALID.
- A BACKTESTED+activation_approved strategy generates signals against the DEMO account.
  When it OPENS a demo position → status flips to PAPER. When that position CLOSES →
  it flips BACK to BACKTESTED. PAPER means "currently holds an open demo position", NOT a
  distinct multi-trade phase. Trade history accumulates in trade_journal, which SURVIVES
  the BACKTESTED↔PAPER oscillation — that history is what the graduation gate reads.
- GRADUATION = a human (CIO dashboard, POST /strategies/{id}/graduate) promotes a proven
  (template,symbol) paper pair to LIVE. A live_strategies row is created with CIO-set
  position_size (REAL $), sl_pct, tp_pct, conviction_min. Status → LIVE. Retiring a live
  strategy sets live_strategies.retired_at AND flags its open live position for closure.
- LIVE strategies run EXCLUSIVELY in the Phase 2B "live-independent pass" in
  trading_scheduler, against account_type='live' with the live eToro client. The CIO
  position_size is AUTHORITATIVE: validate_signal gates (vetoes) but must NEVER shrink a
  live order below CIO ÷ mirror_ratio.

Two accounts, one DB. DEMO hosts BACKTESTED/PAPER (~$535K, many positions); LIVE hosts LIVE
(~$10K virtual / ~$1.3K real). eToro REUSES numeric position IDs across accounts, so EVERY
positions/orders/account query AND every position-CLOSE path MUST be account_type-scoped.
Two OrderMonitor instances (demo/live). Conviction: PAPER 60/55(crypto); LIVE per-pair from
live_strategies (73/67 default). Sizing: PAPER flat $5K; LIVE = CIO real-$ ÷ mirror_ratio.
Template families: DSL (walk-forward path) and Alpha Edge (fundamental path, ~8/cycle cap).

## TRACE THE PIPELINE END-TO-END (the spine of this audit — prove each hop with evidence)
  autonomous cycle: propose (PROPOSED) → walk-forward → Monte Carlo → direction-aware
  thresholds → conviction scoring → activation (→ BACKTESTED, activation_approved)
  → signal generation (DEMO) → runtime gates (VIX / trend-consistency / MQS / pullback /
  intraday circuit-breaker) → validate_signal (GATE) + sizing → order_executor (ATR SL,
  spread, leverage rules) → eToro submit → order_monitor fill detection → position created
  (BACKTESTED→PAPER) → TSL recalc + breach enforcement → exit (DSL / zombie / fundamental /
  SL) → close (PAPER→BACKTESTED) → trade_journal → P&L → equity snapshot → graduation gate
  → CIO graduate → LIVE → Phase 2B live-independent pass (account_type='live').
For EACH hop: Is it correct? Is it account_type-scoped? Does it honor the CIO size on live?
What happens on stale data, API failure, EMPTY result, or exception? Is any failure
swallowed silently? Does any failure CASCADE (e.g. an erroneous close → re-entry)?

## AUDIT CATEGORIES — investigate each exhaustively

### 1. LIVE CAPITAL SAFETY (P0)
- LIVE POSITION RECONCILIATION (above) — eToro vs DB vs UI count/symbol/size.
- POSITION-CLOSE PATHS — audit EVERY code path that sets closed_at / marks a position
  closed: monitoring sync (order_monitor), the account.py endpoints (GET/POST /positions,
  /positions/sync), strategy retirement, zombie exits, pending-closure processor. EACH must
  be (a) account_type-scoped, and (b) MUST NOT close positions on an EMPTY or partial eToro
  response. Precedent: on 2026-06-11 POST /positions/sync closed live AMD+PANW because its
  "no longer on eToro → close" query had NO account_type filter and ran against the DEMO
  eToro response (loading the demo positions page nuked live positions in the DB).
- ERRONEOUS-CLOSE → DUPLICATE-ENTRY CASCADE — when a live position is wrongly closed in the
  DB, the live pass duplicate guard (reads DB open positions) sees an empty slot and
  RE-ENTERS → a duplicate REAL position on eToro (this happened to PANW on 2026-06-11). The
  DB unique index uq_open_pos_strategy_symbol_acct then prevents reopening the original
  (the re-entry occupies the slot), and the bundled reopen transaction rolls back. Verify:
  no close path can empty the live book on transient data; the duplicate guard is robust.
- CIO SIZE AUTHORITY — live order size MUST equal CIO position_size ÷ mirror_ratio.
  validate_signal must GATE only (veto), never shrink below CIO (a reverted min(pipeline,
  CIO) once opened AMD at $25r vs the approved $100r). Confirm each live position's size.
- Duplicate-order surface: live-pass in-memory symbol guard, the DB unique index, FIX-09
  watchdog, cross-thread races between monitoring_service sync and the live pass.
- Live order write isolation; orphan recovery; pending_* state handling.
- TSL breach enforcement on stale current_price (now guarded by positions.price_updated_at
  freshness + a forced resync; verify it works); the 60s sync delay window.
- Intraday circuit breaker (FIX-01) LIVE-only scoping; equity-snapshot staleness dependence.
- F31 mass-closure guard (≤25 closes/cycle, breach-prioritized) — verify it can't starve
  legitimate stop-outs nor allow a runaway bulk close.
- Search EVERY session.query/execute touching live positions/orders for
  InFailedSqlTransaction exposure and missing account_type scoping.

### 2. STATISTICAL VALIDITY (go deep — this is where edge is real or imagined)
- Walk-forward: train/test split integrity, look-ahead leakage, the (test-train)≤1.5 gate
  on all 3 paths (primary/test-dominant/relaxed-OOS). Are any admitting regime luck?
- Monte Carlo bootstrap: is the resampling valid? Is p5 Sharpe ≥ 0 meaningful at our trade
  counts (min_trades 6–8)?
- Backtest engine: transaction costs (verify against the eToro Diamond fee table in
  steering — no phantom costs on stock/ETF LONG; only backtest.transaction_costs is read,
  the top-level transaction_costs block is dead config), slippage, fill assumptions,
  indicator warmup/look-ahead, DST/resample correctness.
- Graduation gate: the hard min_trades floor (15) over the dynamic Sharpe formula; the
  Wilson lower-bound win-rate gate (type-floor-relative); the max_qualification_ratio_cap.
  Statistical power at these thresholds; does paper performance predict live? (GOOGL
  graduated then went 11% WR / 18 live trades before retirement — re-examine the gate.)
- Conviction scoring: per-asset-class normalization denominators vs achievable max.

### 3. DATA INTEGRITY & ACCOUNTING
- TYPED NOTIONAL (shares vs dollars): positions.quantity is SHARES; invested_amount is the
  canonical DOLLAR field; entry orders store dollars; close/SL/TP orders inherit share-
  valued quantity. src/models/notional.py (position_notional_usd / position_shares) is the
  single source of truth — verify every consumer routes through it, not raw .quantity.
- ORM→DATACLASS FIELD PROPAGATION: every `Position(...)` construction that feeds the risk
  path MUST carry invested_amount. If omitted, _get_position_value falls back to shares×price
  → for dollar-valued demo quantity this inflates exposure to $1M+ and falsely trips the
  position/exposure cap (this blocked demo paper entries on 2026-06-11). Audit ALL Position
  constructions in trading_scheduler, strategies.py, monitoring_service, order_monitor.
- trade_journal vs positions consistency; P&L sign/direction for shorts; realized vs
  unrealized; demo/live separation; does trade history survive the BACKTESTED↔PAPER flip?
- positions.price_updated_at integrity (A2): stamped each sync on positions present on
  eToro; used by breach enforcement. FK constraints, NOT NULL, indexes, orphaned rows.
- Equity snapshot math (equity / balance / invested / pending).

### 4. DATA PIPELINE
- Freshness across 1d/1h/4h for all open-position symbols; market-hours-aware staleness;
  FMP /stable EOD routing (ALUMINUM/ZINC from FMP not Yahoo); Yahoo DST/resample; 1h-vs-1d
  quick-update separation; symbol canonicalization (DB display vs eToro wire vs Yahoo).

### 5. RISK MANAGEMENT
- LIVE sizing: confirm it equals CIO ÷ mirror exactly (Category 1) — validate_signal is a
  veto-gate, not a resizer. Then verify the GATE inputs: vol-scaling equity denominator
  (virtual $10K not demo $500K), drawdown sizing source + account scoping, heat cap, symbol
  cap (cumulative across strategies), sector cap, correlation, conviction-tier, per-pair
  loser penalty, leverage-ETF sizing. Does any cap validate against a different size than
  what trades?
- ATR SL: confirm the 1.5x/2.0x hardcode, asset-class clamps, size-rescale-on-widen,
  the canonical leveraged-ETF set in sl_caps (position_manager now imports it).

### 6. EXECUTION & RECONCILIATION
- Order lifecycle state machine (PENDING/PARTIALLY_FILLED/FILLED/FAILED/CANCELLED); the
  market-closed-deferral FAILED churn; stale-PENDING 404 handling (NEW-08 now marks CANCELLED
  after a 404 when no open position — verify).
- Position sync matching (eToro ID oscillation, cross-account ID reuse, consecutive-miss
  close guard — verify it survives a service restart); reconcile_on_startup correctness.

### 7. MONITORING, OBSERVABILITY & THE INTEL ANALYST ITSELF
- Audit the Intel checks for correctness (false positives/negatives), not just output.
  Precedent: A1/A6 read strategies.performance->>'last_signal_at', a key NEVER written →
  A1 was a 100% false positive ("156 dead strategies" that were actually signalling) and
  A6 never fired. Verify every check reads a populated source. Run a fresh scan, reconcile
  each finding against ground truth.
- Silent-failure audit: run scripts/check_silent_excepts.py (--ci) over src/risk|execution|
  core; triage the dangerous ones (write/risk/execution paths).
- Loop health: [loop-timing] (>30s phase / >45s cycle) and the FIX-09 watchdog; the 76–86min
  monitoring-loop gaps. Cold-start (post-restart) transient errors.

### 8. STRATEGY LIFECYCLE, PORTFOLIO & GATE CALIBRATION
- BACKTESTED↔PAPER flip + demotion/retirement guards; backtested_ttl_cycles; zombie-exit
  account scoping; proposer feedback decay loops (TSLA-audit) — verify they decay, not lock.
- GATE CALIBRATION vs DEPLOYMENT: if capital sits idle, trace the signal→order funnel
  (signal_decisions stages) and the gate_blocked reasons. A gate blocking most signals may
  be correct (defensive) OR mis-calibrated — get forward-return EVIDENCE before deciding.
  Precedent: the pullback gate blocked ~80% of trend LONGs in a moderate pullback; SPY
  2021–26 analysis showed moderate+RSI5<20 bounces +2.0%/88% win, so a deep-oversold daily-
  trend exemption was added. Re-validate that exemption and all gate thresholds.
- Live-book concentration (multiple strategies per symbol); idle-balance vs gate trade-off.

### 9. API / FRONTEND / SECURITY / CONFIG
- API endpoint correctness + account_type scoping — ESPECIALLY any endpoint with a WRITE
  side-effect (position close/create) triggered by a GET/load. Audit account.py exhaustively.
- get_autonomous_status-style crashes on present-but-None config keys.
- auth/session handling; websocket event integrity; config_loader layer precedence
  (autonomous_trading.yaml vs api_keys.yaml); secrets; the patch-api-keys.sh startup step.
- Frontend: any quant-facing number that could be wrong/misleading (P&L, equity, win-rate,
  Sharpe, ages/timestamps, demo vs live display, position COUNT vs eToro).

### 10. CODE QUALITY & ARCHITECTURE
- Duplicate/competing implementations (e.g. the graduation queue inline eligibility vs
  is_qualified); the typed-notional debt (A1 phase 2/3 deferred); unify the staleness
  predicates (D1/D2 + TSL SLA + FIX-09 onto positions.price_updated_at); monitoring-loop
  cadence coupling.

## KNOWN STATE (verify — do not assume still true; from sessions through 2026-06-11)
- LIVE FIXES (verify deployed + correct): account.py /positions/sync now account_type-scoped
  + empty-response guard; live order size = CIO ÷ mirror (P1-1 min() REVERTED); live retire
  flags open position for closure; A2 positions.price_updated_at + breach freshness guard;
  F31 mass-closure guard; pullback deep-oversold daily-trend exemption (_DEEP_OVERSOLD_RSI=20);
  src/models/notional.py accessor + invested_amount carried into all risk-path Position
  dataclasses; graduation hard min_trades=15 + Wilson WR gate; Intel A1/A6 re-pointed to
  signal_decisions/trade_journal; NEW-08 404→CANCELLED; A4 silent-except detector script.
- Earlier (Sprint 13/14): InFailedSqlTransaction root fix (rollback-on-checkout) +
  session_scope(); DB unique index on open positions; FIX-09 watchdog; FMP /stable EOD;
  atomic live_trade_count; leveraged-ETF canonical set in sl_caps.
- LIVE BOOK (2026-06-11): GOOGL, TXN, COPPER retired; SOXL re-graduated. Active live ~11
  (AMD, DELL, INTC, MU×4, PANW, SOXL, TQQQ, XLK). Confirm current open positions reconcile
  to eToro. The under-sized AMD was closed for reposition — verify it re-entered at $100r.
- Genuinely open: A1 phase 2/3 (orders notional column, quantity→shares rename — phase 3
  recommended against on a live DB); ~133 silent excepts (detector tracks them); the
  graduation-queue inline duplicate; staleness-predicate unification.

## OUTPUT FORMAT
Per finding: Category (P0/P1/P2/Architecture/Opportunity) | Location (file:line or subsystem)
| What's wrong (precise ROOT CAUSE, not symptom) | Evidence (log line / DB result / code path
— actually run it) | Proper fix (root-cause, no patches) | Effort (be honest: agent
wall-clock is minutes-to-hours, gated mainly by live-cycle verification, not human-days).
Group by priority, P0 first, ordered by impact within each group.
End with: (1) a sprint plan bundling fixes logically; (2) a watch list (not-yet-bugs); (3)
architectural recommendations. If a proper fix needs research first, say so and do the
research (e.g. forward-return analysis for a gate change) before proposing.

Be exhaustive. Read the actual source and the live system. Reconcile against eToro, not the
UI. Prove every claim.
```
