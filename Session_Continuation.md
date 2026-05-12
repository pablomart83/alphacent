# AlphaCent — Session Continuation

> Permanent rules are in `.kiro/steering/trading-system-context.md`. This file holds current system state, recent fixes, and open items.

---

## ⚡ NEXT SESSION KICKOFF

**Frontend rebuild v2 is complete. Platform is in active iteration — fixing bugs, improving analytics, and tuning the graduation/live trading pipeline.**

**🔴 LIVE TRADING ISSUE: GOOGL live position not re-opening after overnight bug. See P0 below.**

---

## SESSION 2026-05-12 — WHAT WAS DONE

### P0 Critical fixes (all shipped)

| Commit | What |
|---|---|
| `a6918de` | P0: duplicate guard, position ID oscillation, miss counter, live_trades wiring |
| `e48f3a6` | reconcile_on_startup scoped to demo account_type only |
| `7aec120` | Untrack autonomous_trading.yaml from git (EC2 authoritative) |
| `2678aaf` | Cycle pipeline stuck on Proposals fix + LiveStream improvements |
| `231dc83` | ManualCycleTrigger selections persist to localStorage |
| `2e5bf16` | Exclude autonomous_trading.yaml from rsync --delete in deploy workflow |
| `86ba298` | Fix cycle pipeline WS events: run_coroutine_threadsafe (root cause of frozen pipeline) |
| `c71f21b` | Fix pipeline stage during WF: emit walk_forward_backtesting not strategy_proposals |
| `27d9637` | LiveStream: show WF progress every 20th iteration + last |
| `910d1d3` | Add Clear caches & blacklists button to ManualCycleTrigger |
| `5518c62` | Disable auto-deploy on push — manual trigger only |
| `1c4cade` | Fix cycle pipeline: green on complete, backend keys direct, no flooding |
| `d0320f3` | Fix directional balance toggle: sync to directional_quotas.enabled |
| `8026dfe` | Add Alpha vs SPY, win rate, PnL to right surfaces; fix pipeline label |
| `3cd6ceb` | Fix pipeline stage compression: minmax(64px,1fr) |
| `e26b07f` | Fix pipeline: always render connector div to hold grid column |
| `cc71f85` | Fix position merge: only oscillation-fix when existing ID gone from eToro |
| `d82399a` | Fix immediate-exit trap: skip entry when exit condition already strongly met |
| `7b4d629` | Fix pending_retirement strategies stuck in PAPER for weeks |
| `d51cf26` | pending_retirement strategies: retire immediately when positions close |
| `07b33be` | Fix live pass duplicate guard: 4h cooldown on recent orders |
| `a5ff668` | ROOT CAUSE FIX: scope OrderMonitor queries to account_type |
| `871bd53` | Fix _submit_close_order: refresh etoro_position_id before closing live positions |
| `1e67485` | Fix live.py close endpoint: refresh etoro_position_id before closing |
| `49d7c00` | Fix circuit breaker: exclude live positions from template win rate check |
| `7d4170a` | Add Portfolio VaR limit to Settings / Risk Limits |

### Root cause of overnight GOOGL disaster

The DEMO `OrderMonitor.check_submitted_orders()` had no `account_type` filter. It picked up live GOOGL orders, called `get_order_status()` with the DEMO eToro client (404 for live orders), and marked them CANCELLED. No position was created in DB. The live pass saw no open position and fired every 10 minutes overnight → 12 GOOGL positions at market open.

**Fixed**: `OrderMonitor` now scoped to `account_type`. DEMO monitor only sees DEMO orders. Live monitor only sees live orders.

**Downstream effect**: 12 positions all closed at a loss → template circuit breaker fired (win rate 10%) → -1.5 decay penalty on conviction → 73.3 - 1.5 = 71.8 < 73 → live pass blocked from re-entering.

**Also fixed**: circuit breaker now excludes `account_type='live'` positions from template win rate calculation.

---

## CURRENT SYSTEM STATE (2026-05-12 end of session)

- **DEMO equity:** ~$484K | **Open positions:** ~69 | **Regime:** trending_up_strong
- **DEMO strategies:** ~47 PAPER + ~63 BACKTESTED
- **LIVE strategy:** `4H EMA Ribbon Trend Long GOOGL LIVE` (id: `918b0c99`) — status LIVE
- **LIVE positions:** 1 open — GOOGL LONG, entry 389.2, SL 365.82, TP 447.53
- **live_trading.enabled:** TRUE
- **Latest commit:** `c603c6d`

---

## ✅ P0 — LIVE GOOGL POSITION RESOLVED (2026-05-12)

### What happened (full chain)
1. Original GOOGL live position closed at 20:27 May 11 (miss counter bug — fixed `a6918de`)
2. DEMO OrderMonitor processed live orders overnight → 12 GOOGL positions at market open (fixed `a5ff668`)
3. All 12 closed at a loss → template circuit breaker fired (win rate 10%) → conviction 71.8 < 73
4. Circuit breaker fix deployed (`49d7c00`) — excludes live positions from template win rate
5. Live pass fired at 13:14 UTC May 12 — conviction 73.1, order `8dbe13a8` FILLED
6. **But position never appeared in DB** — three bugs in `_sync_positions` blocked it

### Root cause of missing DB row (fixed `c603c6d`)
Three bugs in `order_monitor._sync_positions`:

**Bug 1 — `db_by_etoro_id` not scoped to `account_type`**
- `all_db_positions` loaded ALL accounts. Live sync found the DEMO row `bf17f4af` (which had `etoro_position_id='3515044608'`) and updated it instead of creating a live row.
- Fix: scope `all_db_positions` query to `account_type`.

**Bug 2 — Global unique constraint on `etoro_position_id`**
- eToro reuses numeric position IDs across demo/live accounts.
- INSERT failed with `UniqueViolation` on `positions_etoro_position_id_key` when live ID matched a demo row.
- Fix: DB migration replaced global constraint with composite `uq_positions_etoro_id_account (etoro_position_id, account_type)`.

**Bug 3 — `existing_by_id` check didn't filter by `account_type` or `closed_at`**
- A closed DEMO row with the same numeric PK blocked the live INSERT.
- Fix: `existing_by_id` only matches when `account_type` matches AND `closed_at IS NULL`.
- Added `all_pk_ids_in_db` set for PK collision detection; collision path creates position with synthetic UUID.

### Current state (as of 15:07 UTC May 12)
- Live GOOGL position: `id=3439749630`, `account_type=live`, `etoro_position_id=3439749630`, `entry=389.2`, `stop_loss=365.82`, `take_profit=447.53`
- Live position sync: `1 updated` every cycle — clean, no errors
- No UniqueViolation errors since fix deployed
- **Note**: `strategy_id='ad637559'` on the live position (not `918b0c99`) — this is because the orphan reconciler matched it to a different order. Not blocking anything but worth fixing in a future session.

---

## LIVE TRADING ARCHITECTURE — HOW IT WORKS NOW

### Key fixes this session
- `OrderMonitor.__init__` now takes `account_type` param — DEMO monitor only sees DEMO orders, live monitor only sees live orders
- `_submit_close_order` refreshes `etoro_position_id` from eToro before closing (stale ID fix)
- `/live/positions/{id}/close` endpoint also refreshes ID before closing
- `reconcile_on_startup` scoped to `account_type='demo'` — never touches live positions
- Miss counter keyed by DB UUID (not eToro position ID) — prevents oscillation from closing positions
- Circuit breaker excludes live positions from template win rate

### Duplicate guard (trading_scheduler live pass)
Three checks before firing a live entry:
- (a) Open live position for this symbol → skip
- (b) Pending live order for this symbol → skip
- (c) Any live entry order submitted in last 4h → skip (covers pre-market window)

---

## KNOWN ISSUES / TECHNICAL DEBT

- **Live position strategy_id mismatch** — ~~live GOOGL position `3439749630` has `strategy_id='ad637559'` (not `918b0c99`)~~ **FIXED** (`a65b986`). Root cause: Pass 1 and Pass 2 order matching in `_sync_positions` queried orders without `account_type` filter. A recently-filled DEMO order for GOOGL outranked the older live order in the sort. Fix: both passes now filter `OrderORM.account_type == account_type`. DB corrected manually.
- **VaR check disabled** — portfolio VaR was 97.97% (model artefact from young equity curve). Disabled in Settings. Re-enable after 90+ days of equity history.
- **Conviction threshold 73** — many DEMO signals scoring 65-72 are blocked. Intentional — only high-conviction signals trade.
- **Directional quotas disabled** — you disabled in Settings.
- **4h cooldown on live orders** — belt-and-suspenders guard. May delay re-entry after legitimate position close. Consider reducing to 1h once system is stable.
- **MQS persistence** — NULL values in recent equity_snapshots (silent exception in _save_hourly_equity_snapshot) — now fixed (MQS=84 showing in snapshots)
- **Triple EMA Alignment DSL bug** — EMA(10) > EMA(10) always false
- **Sector Rotation + Pairs Trading templates** — structurally broken

---

## SESSION START CHECKLIST

```bash
# Health + errors
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'tail -20 /home/ubuntu/alphacent/logs/errors.log'
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'tail -10 /home/ubuntu/alphacent/logs/cycles/cycle_history.log'

# Live position status
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo -u postgres psql alphacent -t -A -c "SELECT id, symbol, side, entry_price, current_price, unrealized_pnl, account_type, opened_at FROM positions WHERE account_type='"'"'live'"'"' AND closed_at IS NULL;"'

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
- DEMO: ~$484K equity, ~69 open positions, trending_up_strong
- LIVE: 1 open position — GOOGL LONG, entry 389.2, SL 365.82, TP 447.53, strategy 918b0c99 ✅
- live_trading.enabled: TRUE
- Latest commit: a65b986

P2 — Frontend: verify cycle pipeline shows stages correctly during next cycle run
P2 — Frontend: verify Alpha vs SPY tile in Research/Performance shows data

Root causes fixed this session (do not re-patch):
- OrderMonitor scoped to account_type (commit a5ff668)
- reconcile_on_startup scoped to demo (commit e48f3a6)
- Miss counter keyed by DB UUID (commit a6918de)
- Circuit breaker excludes live positions (commit 49d7c00)
- _submit_close_order refreshes etoro_position_id (commit 871bd53)
- live.py close endpoint refreshes etoro_position_id (commit 1e67485)
- _sync_positions scoped to account_type, PK/etoro_id collision fixed (commit c603c6d)
- DB migration: global etoro_position_id unique → composite (etoro_position_id, account_type)
- Order matching Pass 1 + Pass 2 scoped to account_type (commit a65b986)
- DB migration: global etoro_position_id unique → composite (etoro_position_id, account_type)
```
