# AlphaCent — Full Pipeline Forensic Audit Prompt

> Paste the block below into a fresh session to run a complete end-to-end audit.
> Keep this file updated as the system evolves so the audit always reflects reality.

---

```
You are performing a full end-to-end forensic audit of AlphaCent, a LIVE autonomous
trading platform on EC2 (Ubuntu, PostgreSQL 16, Python 3.11/FastAPI, React/Vite frontend).
REAL MONEY is at risk (~$1,300 real / ~$10K virtual live book, mirror ratio 0.127).
The goal: find every bug, race condition, data-integrity flaw, statistical-validity
error, accounting error, architectural gap, and silent-failure path across the ENTIRE
pipeline — exhaustively, with full investigation. Do NOT stop at surface scans or at the
Intel findings page; the Intel checks are themselves under audit.

## GROUND RULES
1. Read Session_Continuation.md and .kiro/steering/trading-system-context.md FIRST. They
   are the source of truth for state, sprint history, and permanent operating rules.
2. VERIFY, DON'T TRUST. Every "fix" claimed in Session_Continuation must be re-checked
   against live DB/logs/source — confirm it is actually deployed AND actually works.
   Past "fixes" have been dead code, half-wired, or based on a misdiagnosis. Treat the
   changelog as claims to falsify, not facts.
3. Trace, don't sample. Follow real data end-to-end and prove behavior with a log line,
   a DB query result, or an exact code path. State explicitly what you verified vs assumed.
4. Think like a quant running the book, not a coder. "Would I trade real money on this
   output?" is the bar. Stale data, silent failures, and wrong P&L are existential.
5. PROPER ROOT-CAUSE FIXES ONLY — no patches, stopgaps, or skip-flags (steering rule).
6. Live system. Deploy workflow is mandatory: edit LOCAL → getDiagnostics → scp →
   systemctl restart → curl health → git commit/push. Never edit on EC2. Sync
   config/autonomous_trading.yaml FROM EC2 before reading it (the one file EC2 owns).
7. Do NOT auto-retire live strategies, close live positions, or take irreversible
   real-money actions without explicit confirmation. Flag them instead.

## ACCESS
- SSH: ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149
- DB:  ssh ... 'sudo -u postgres psql alphacent -t -A -c "SQL"'
- Logs: logs/errors.log (read FIRST), logs/alphacent.log, logs/cycles/cycle_history.log,
        logs/risk.log, logs/strategy.log
- Config sync: scp -i ~/Downloads/alphacent-key.pem ubuntu@34.252.61.149:/home/ubuntu/alphacent/config/autonomous_trading.yaml config/autonomous_trading.yaml
- Do NOT run inline python on EC2 (ssh ... 'python3 -c'). Use DB queries / log reads.

## THE LIFECYCLE (authoritative — audit every transition for correctness & account scoping)
Status flow:  PROPOSED → BACKTESTED → PAPER → LIVE   (terminal: INVALID, RETIRED)
- "Research" is NOT a stage — it is running the autonomous cycle (scheduled ~once/day or
  manual). It emits PROPOSED strategies, runs them through WF → MC → conviction.
- ACTIVATION = passing the autonomous cycle → status BACKTESTED with activation_approved=True.
  activation_approved=True means the strategy IS considered during signal-generation cycles.
  Failing the cycle → INVALID.
- A BACKTESTED+activation_approved strategy generates signals against the DEMO account.
  When it OPENS a demo position → status flips to PAPER. When that position CLOSES →
  it flips BACK to BACKTESTED. PAPER therefore means "currently holds an open demo
  position", NOT a distinct multi-trade phase. Trade history accumulates in trade_journal,
  which SURVIVES the BACKTESTED↔PAPER oscillation — that history is what the graduation
  gate reads. (So demoting a flat PAPER strategy to BACKTESTED is BY DESIGN; the 24h
  cooldown only prevents thrashing in the brief flat window — verify it does.)
- GRADUATION = a human (CIO dashboard, POST /strategies/{id}/graduate) promotes a proven
  (template,symbol) paper pair to LIVE. A live_strategies row is created with CIO-set
  position_size (real $), sl_pct, tp_pct, conviction_min. Status → LIVE.
- LIVE strategies run EXCLUSIVELY in the Phase 2B "live-independent pass" in
  trading_scheduler, against account_type='live' with the live eToro client and the full
  risk framework. They are NOT in the DEMO cycle.

Two accounts, one DB. DEMO hosts BACKTESTED/PAPER strategies (~$535K, many positions);
LIVE hosts LIVE strategies (~$10K virtual / ~$1.3K real). eToro REUSES numeric position
IDs across accounts, so EVERY positions/orders/account query MUST be account_type-scoped.
Two OrderMonitor instances (demo/live). Conviction thresholds: PAPER 60/55(crypto); LIVE
73/67 per-pair from live_strategies. Sizing: PAPER flat $5K; LIVE = CIO real-$ ÷ mirror_ratio.
Template families: DSL (walk-forward path) and Alpha Edge (fundamental path, ~8/cycle cap).

## TRACE THE PIPELINE END-TO-END (the spine of this audit — prove each hop with evidence)
  autonomous cycle: propose (PROPOSED) → walk-forward → Monte Carlo → direction-aware
  thresholds → conviction scoring → activation (→ BACKTESTED, activation_approved)
  → signal generation (DEMO) → runtime gates (VIX / trend-consistency / MQS / pullback /
  intraday circuit-breaker) → validate_signal + 11-step sizing → order_executor (ATR SL,
  spread, leverage rules) → eToro submit → order_monitor fill detection → position created
  (BACKTESTED→PAPER) → TSL recalc + breach enforcement → exit (DSL / zombie / fundamental /
  SL) → close (PAPER→BACKTESTED) → trade_journal → P&L → equity snapshot → graduation gate
  → CIO graduate → LIVE → Phase 2B live-independent pass (account_type='live').
For EACH hop: Is it correct? Is it account_type-scoped? What happens on stale data, API
failure, empty result, or exception? Is any failure swallowed silently?

## AUDIT CATEGORIES — investigate each exhaustively

### 1. LIVE CAPITAL SAFETY (P0)
- Re-verify the duplicate-order surface: live-pass in-memory symbol guard, DB unique index
  on open (strategy_id,symbol,account_type), FIX-09 watchdog, cross-thread races between
  monitoring_service sync and the trading_scheduler live pass. Confirm they hold under failure.
- Live order write isolation; orphan recovery; pending_* state handling.
- TSL breach enforcement with stale current_price; the 60s sync delay window.
- Intraday circuit breaker (FIX-01) LIVE-only scoping; does it depend on equity snapshots
  that can go stale?
- Search EVERY session.query/execute touching live positions/orders for
  InFailedSqlTransaction exposure and missing account_type scoping.

### 2. STATISTICAL VALIDITY (go deep — this is where edge is real or imagined)
- Walk-forward: train/test split integrity, look-ahead leakage, the (test-train)≤1.5 gate,
  the test-dominant and relaxed-OOS rescue paths. Are any admitting regime luck?
- Monte Carlo bootstrap: is the resampling valid? Is p5 Sharpe ≥ 0 meaningful at our trade
  counts (min_trades 6–8)?
- Backtest engine: transaction costs (verify against the eToro Diamond fee table in
  steering — no phantom costs on stock/ETF LONG), slippage, fill assumptions, indicator
  warmup/look-ahead, DST/resample correctness.
- Graduation gate: statistical power of the qualification_ratio at min_trades=3; the
  max_qualification_ratio_cap regime-luck guard.
- Conviction scoring: per-asset-class normalization denominators vs achievable max
  (Tier-1 asset score 15 vs a denominator assuming 12 → systematic inflation?).

### 3. DATA INTEGRITY & ACCOUNTING
- The `quantity` unit ambiguity: etoro_client.get_positions writes quantity=units (shares)
  + invested_amount=amount (dollars); entry orders store dollars; close/SL/TP orders inherit
  share-valued quantity. invested_amount is the canonical dollar field. Audit EVERY consumer
  of positions.quantity / orders.quantity for unit-correctness (sizing, caps, P&L, VaR, heat,
  balance, slippage).
- trade_journal vs positions consistency; P&L sign/direction for shorts; realized vs
  unrealized; demo/live separation; does trade history survive the BACKTESTED↔PAPER flip?
- FK constraints, NOT NULL, indexes, orphaned rows; historical_price_cache integrity.
- Equity snapshot math (equity / balance / invested / pending).

### 4. DATA PIPELINE
- Freshness across 1d/1h/4h for all open-position symbols; market-hours-aware staleness;
  the FMP /stable EOD routing (verify ALUMINUM/ZINC actually source from FMP now, not Yahoo);
  Yahoo DST/resample; 1h-vs-1d quick-update separation; symbol canonicalization (DB display
  form vs eToro wire vs Yahoo ticker).

### 5. RISK MANAGEMENT
- Full 11-step sizing for LIVE: vol-scaling equity denominator (virtual $10K not demo $500K),
  drawdown sizing source table + account scoping, heat cap, symbol cap (cumulative across
  strategies), sector cap, correlation adjustment, conviction-tier, per-pair loser penalty,
  leverage-ETF sizing. Verify each fires with correct inputs.
- ATR SL: confirm the 1.5x/2.0x hardcode, asset-class clamps, size-rescale-on-widen.

### 6. EXECUTION & RECONCILIATION
- Order lifecycle state machine (PENDING/PARTIALLY_FILLED/FILLED/FAILED/CANCELLED); the
  market-closed-deferral FAILED churn; stale-PENDING 404 dead-end (NEW-08, still unbuilt).
- Position sync matching (eToro ID oscillation, cross-account ID reuse, consecutive-miss
  close guard); reconcile_on_startup correctness.

### 7. MONITORING, OBSERVABILITY & THE INTEL ANALYST ITSELF
- Audit the Intel checks for correctness (false positives/negatives), not just their output.
  Freshness checks, E5 loop classification, the auto-resolution guard, severity assignments.
  Run a fresh scan and reconcile every finding against ground truth.
- Silent-failure audit: enumerate `except: pass` / `except: logger.debug` in critical
  write/risk/execution paths (~423 total, ~28% of handlers). List the dangerous ones.

### 8. STRATEGY LIFECYCLE & PORTFOLIO
- BACKTESTED↔PAPER flip correctness + demotion/retirement guards; backtested_ttl_cycles
  wall-clock; zombie-exit account scoping; live-book concentration (MU×4, COPPER); proposer
  feedback decay loops (TSLA-audit mechanisms) — verify they actually decay, not lock out.

### 9. API / FRONTEND / SECURITY / CONFIG
- API endpoint correctness + account_type scoping; auth/session handling; websocket event
  integrity; config_loader layer precedence (autonomous_trading.yaml vs api_keys.yaml — any
  value read from the wrong layer?); secrets handling; the patch-api-keys.sh startup step.
- Frontend: any quant-facing number that could be wrong/misleading (P&L, equity, win-rate,
  Sharpe, ages/timestamps, demo vs live display).

### 10. CODE QUALITY & ARCHITECTURE
- Duplicate/competing implementations; the typed-notional debt (quantity units); unify the
  three staleness predicates (D1/D2 + TSL SLA + FIX-09); monitoring-loop cadence coupling.

## KNOWN STATE (verify — do not assume still true)
- Recently fixed (Sprint 13/14): InFailedSqlTransaction root fix (session rollback on
  checkout) + session_scope(); live duplicate guards + DB unique index on open positions;
  FIX-09 cooldown/self-heal/threshold; FMP /stable EOD routing; atomic live_trade_count;
  balance-gate (entry-orders-as-dollars, no ×price); leveraged-ETF sizing (dead 4% cap
  removed, 0.5× sizing kept, canonical set in sl_caps.is_leveraged_etf); Intel auto-resolve
  + D1/D2 business-day staleness + A1→P2 + E5 balance-exclusion. CONFIRM each is deployed
  and correct.
- Genuinely open: COPPER live strategies diverging from WF (G5 — retirement candidate, real
  money); NEW-08 stale-order cancel path; ~423 silent excepts; typed-notional refactor.
- NOT a problem (do not re-flag): TQQQ/SOXL live (positive performance: SOXL live 4 trades
  +$868/50% WR, demo +$8.9K; TQQQ demo +$7.5K) — monitor via G5 only.

## OUTPUT FORMAT
Per finding: Category (P0/P1/P2/Architecture/Opportunity) | Location (file:line or subsystem)
| What's wrong (precise ROOT CAUSE, not symptom) | Evidence (log line / DB result / code path
— actually run it) | Proper fix (root-cause, no patches) | Effort.
Group by priority, P0 first, ordered by impact within each group.
End with: (1) a sprint plan bundling fixes logically; (2) a watch list (not-yet-bugs); (3)
architectural recommendations for the next evolution. If a proper fix needs research first,
say so and do the research before proposing.

Be exhaustive. Read the actual source and the live system. Prove every claim.
```
