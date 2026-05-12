# AlphaCent — Session Continuation

> Permanent rules are in `.kiro/steering/trading-system-context.md`. This file holds current system state, recent fixes, and open items.

---

## ⚡ NEXT SESSION KICKOFF

**Platform is in active iteration — live trading is running, graduation pipeline is working, analytics surfaces are being refined.**

---

## SESSION 2026-05-12 — WHAT WAS DONE

### Live trading infrastructure (all shipped)

| Commit | What |
|---|---|
| `a6918de` | P0: duplicate guard, position ID oscillation, miss counter, live_trades wiring |
| `e48f3a6` | reconcile_on_startup scoped to demo account_type only |
| `a5ff668` | ROOT CAUSE FIX: scope OrderMonitor queries to account_type |
| `871bd53` | Fix _submit_close_order: refresh etoro_position_id before closing live positions |
| `1e67485` | Fix live.py close endpoint: refresh etoro_position_id before closing |
| `49d7c00` | Fix circuit breaker: exclude live positions from template win rate check |
| `c603c6d` | Fix live position tracking: scope sync to account_type, fix PK/etoro_id collision |
| `a65b986` | Fix order matching: scope Pass 1 and Pass 2 to account_type |
| `c48ef27` | Fix all 6 post-investigation items (circuit breaker, orphan position, startup reconcile, gitignore, migrations/) |

### Graduation pipeline

| Commit | What |
|---|---|
| `0b9f993` | Fix approaching-graduation: add wf_test_sharpe to WF sharpe SQL lookup |
| `abde7ff` | Graduation: fix WR bar, add max_qualification_ratio cap (2.0×), update labels |
| `231e140` | Add Promoted Today, Activated Today, Live Today pill filters to Library |

### Analytics & UI

| Commit | What |
|---|---|
| `c2bd491` | Fix pending-open and pending-closures endpoints: add account_type filter |
| `c59500c` | Fix Library pill filters: add last_signal_at and live_pnl to slim metadata |
| `b2d8183` | Add total_return_dollars to performance analytics |
| `1c79447` | Add realized P&L, alpha vs SPY, dollar returns across Fund Scorecard, Research tiles, chart hover |
| `5d81da7` | Move Execution tab Book→Research, fix Attribution overlap, add Realised alpha vs SPY to chart hover |
| `e4ab95b` | Guard: fix slow load (N+1 batch queries), UUID display, tab order, Risk tab layout |

### Other fixes

| Commit | What |
|---|---|
| `7aec120` | Untrack autonomous_trading.yaml from git (EC2 authoritative) |
| `07b33be` | Fix live pass duplicate guard: 4h cooldown on recent orders |
| `7d4170a` | Add Portfolio VaR limit to Settings / Risk Limits |

---

## CURRENT SYSTEM STATE (2026-05-12 end of session)

- **DEMO equity:** ~$484K | **Open positions:** ~66 | **Regime:** trending_up_strong
- **DEMO strategies:** ~47 PAPER + ~63 BACKTESTED
- **LIVE strategy:** `4H EMA Ribbon Trend Long GOOGL LIVE` (id: `918b0c99`) — status LIVE
- **LIVE positions:** 1 open — GOOGL LONG, entry 389.2, SL 365.82, TP 447.53 ✅
- **live_trading.enabled:** TRUE
- **Latest commit:** `e4ab95b`

---

## LIVE TRADING ARCHITECTURE — HOW IT WORKS NOW

### Key invariants (do not re-patch)
- `OrderMonitor` takes `account_type` param — DEMO monitor only sees DEMO orders/positions, live monitor only sees live
- `_sync_positions` scoped to `account_type` — live sync never finds DEMO rows by etoro_position_id
- `positions.etoro_position_id` unique constraint is **composite** `(etoro_position_id, account_type)` — eToro reuses numeric IDs across accounts
- PK collision path: if eToro position ID already exists as a PK in DB (from different account), a synthetic UUID is used
- Order matching Pass 1 + Pass 2 both filter `OrderORM.account_type == account_type` — DEMO orders never match live positions
- `reconcile_on_startup` is account_type-aware — live monitor runs its own startup reconcile via `monitoring_service._live_reconcile_done`
- Circuit breaker excludes `account_type='live'` positions from template win rate

### Duplicate guard (trading_scheduler live pass)
Three checks before firing a live entry:
- (a) Open live position for this symbol → skip
- (b) Pending live order for this symbol → skip
- (c) Any live entry order submitted in last 4h → skip (covers pre-market window)

### DB schema changes (migrations/)
- `migrations/migrate_etoro_id_constraint.sql` — replaced global `positions_etoro_position_id_key` with composite `uq_positions_etoro_id_account`

---

## GRADUATION PIPELINE — HOW IT WORKS NOW

### Thresholds (from `autonomous_trading.yaml` graduation_gate section)
- `min_trades: 15` (lowered from 20 to enable GOOGL test graduation)
- `min_win_rate_pct: 55.0`
- `min_qualification_ratio: 0.6` (paper Sharpe ≥ 60% of WF Sharpe)
- `max_qualification_ratio_cap: 2.0` (paper Sharpe must not exceed 2× WF Sharpe — regime-luck guard)
- `rejection_cooldown_days: 14`

### Key fix: wf_test_sharpe lookup
The approaching-graduation SQL was looking for `wf_sharpe` and `walk_forward_sharpe`. All 120 active strategies store WF Sharpe under `wf_test_sharpe`. Fixed in `strategies.py` — COALESCE priority: `wf_test_sharpe → wf_sharpe → walk_forward_sharpe`.

### Graduation pipeline state
- No pairs currently qualify at 15-trade threshold with the 2.0× ratio cap
- MU / 4H EMA Ribbon is closest: 13 trades, 76.9% WR, ratio 2.46 (blocked by ratio cap)
- XLK / 4H EMA Ribbon: 10 trades, 90% WR, ratio 2.94 (blocked by ratio cap)
- Pipeline will fill ~July-August as 4H strategies accumulate 15+ trades per pair

---

## UI NAVIGATION — CURRENT STRUCTURE

### Book page tabs
Positions · Orders · Live  
(Execution moved to Research)

### Research page tabs
Performance · **Execution** · Attribution · Trades · Regime · Alpha Edge · Tear Sheet · Stress · Journal

### Guard page tabs
**System** · Risk · Gates · Circuit Breakers · Alerts · Audit  
(System is now first tab and default landing)

### Key analytics surfaces
- **Fund Scorecard (Command)**: 3×3 grid — Sharpe · Sortino · Max DD / Win rate · Profit factor · Alpha vs SPY / Total return (% + $) · Realised P&L (% + $) · Unrealised P&L ($)
- **Research/Performance headline tiles**: Total return (% + $) · Realised P&L (% + $) · Alpha vs SPY · Sharpe · Sortino · Max DD · Win rate · Profit factor · Daily returns
- **Equity chart hover**: Equity · Realised · Realised α SPY (when SPY toggle on) · Drawdown · Alpha vs SPY
- **Library pills**: Signals today · Idle 7d+ · Negative live P&L · Graduation eligible · Paper ≥20 trades · Promoted today · Activated today · Live today

---

## KNOWN ISSUES / TECHNICAL DEBT

- **min_trades=15 in graduation_gate** — intentionally lowered to enable GOOGL test graduation. Raise back to 20 once live system is stable and you want stricter graduation criteria.
- **VaR check disabled** — portfolio VaR was 97.97% (model artefact from young equity curve). Disabled in Settings. Re-enable after 90+ days of equity history.
- **Conviction threshold 73** — many DEMO signals scoring 65-72 are blocked. Intentional — only high-conviction signals trade live.
- **Directional quotas disabled** — disabled in Settings.
- **4h cooldown on live orders** — belt-and-suspenders guard. May delay re-entry after legitimate position close. Consider reducing to 1h once system is stable.
- **Triple EMA Alignment DSL bug** — `EMA(10) > EMA(10)` always false, generates 0 trades.
- **Sector Rotation + Pairs Trading templates** — structurally broken, need design session.
- **Walk-forward bypass paths admit regime-luck** — LONG test-dominant path still loose. Consider consistency gate `(test_sharpe - train_sharpe) ≤ 1.5`.
- **Entry order 82% FAILED rate** — cosmetic: market-closed deferrals written as FAILED then re-fired each cycle.
- **Cycle-error observability gap** — stage failures log silently, no `signal_decisions` row written.

---

## SESSION START CHECKLIST

```bash
# Health + errors
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'tail -20 /home/ubuntu/alphacent/logs/errors.log'
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'tail -10 /home/ubuntu/alphacent/logs/cycles/cycle_history.log'

# Live position status
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo -u postgres psql alphacent -c "SELECT id, symbol, side, entry_price, current_price, unrealized_pnl, account_type, opened_at, stop_loss FROM positions WHERE account_type='"'"'live'"'"' AND closed_at IS NULL;"'

# Live pass activity
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'grep "Live pass\|LIVE FILL\|UniqueViolation\|PK collision" /home/ubuntu/alphacent/logs/system.log | tail -10'

# Strategy counts
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo -u postgres psql alphacent -t -A -c "SELECT status, COUNT(*) FROM strategies GROUP BY status ORDER BY status;"'

# Sync autonomous_trading.yaml (always do this)
scp -i ~/Downloads/alphacent-key.pem ubuntu@34.252.61.149:/home/ubuntu/alphacent/config/autonomous_trading.yaml config/autonomous_trading.yaml
```

---

## NEXT SESSION PROMPT

```
Read .kiro/steering/trading-system-context.md and Session_Continuation.md in full before doing anything.

System state:
- DEMO: ~$484K equity, ~66 open positions, trending_up_strong
- LIVE: 1 open position — GOOGL LONG, entry 389.2, SL 365.82, TP 447.53, strategy 918b0c99 ✅
- live_trading.enabled: TRUE
- Latest commit: e4ab95b

Root causes fixed this session (do not re-patch):
- OrderMonitor scoped to account_type (a5ff668)
- reconcile_on_startup account_type-aware, live startup reconcile wired (c48ef27)
- Miss counter keyed by DB UUID (a6918de)
- Circuit breaker excludes live positions (49d7c00)
- _submit_close_order + live.py close endpoint refresh etoro_position_id (871bd53, 1e67485)
- _sync_positions scoped to account_type, PK/etoro_id collision fixed (c603c6d)
- DB migration: global etoro_position_id unique → composite (etoro_position_id, account_type)
- Order matching Pass 1 + Pass 2 scoped to account_type (a65b986)
- pending-open and pending-closures endpoints scoped to account_type (c2bd491)
- /risk/metrics and /risk/advanced scoped to account_type (e4ab95b)
- /risk/advanced N+1 queries replaced with batch queries (e4ab95b)
```
