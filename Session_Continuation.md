# AlphaCent — Session Continuation

> Permanent rules are in `.kiro/steering/trading-system-context.md`. This file holds current system state, recent fixes, and open items.

---

## ⚡ NEXT SESSION KICKOFF

**Frontend rebuild v2 is complete (Sprints 0-12 + polish). All 5 surfaces + Settings are live at https://alphacent.co.uk. The platform is now in active iteration — fixing bugs, improving analytics, and tuning the graduation/live trading pipeline.**

### Frontend rebuild progress

| Sprint | Surface / goal | Status | Commit |
|---|---|---|---|
| 0 | Foundation: design system, primitives, 5-surface IA shell, WS + Query client | ✅ SHIPPED | `1171d41` |
| 1 | Command — Pulse + Equity + Stream | ✅ SHIPPED | `d297d85` |
| 2 | Book / Positions — 4 sub-tabs, allocation panel, detail drill-down | ✅ SHIPPED | `ae2c78f` |
| 3 | Book / Orders + Execution — 3 sub-tabs, slippage heatmap, manual order | ✅ SHIPPED | `c9006ee` |
| 4 | Book / Live — master switch, tiles, mirror strip, divergence cards | ✅ SHIPPED | `f22db70` |
| 5 | Strategies / Library | ✅ SHIPPED | `042c2c5` |
| 6 | Strategies / Cycle (autonomous pipeline + funnel) | ✅ SHIPPED | `6d1aa89` |
| 7 | Strategies / Templates + Symbols + Blacklist + Graduation (flagship) + Lab | ✅ SHIPPED | `b52ea72` |
| 8 | Guard / Risk + Gates | ✅ SHIPPED | `b4b11dc` |
| 9 | Guard / System + Circuit Breakers + Alerts + Audit | ✅ SHIPPED | `3f40f8e` |
| 10 | Research / Performance + Attribution + Trades | ✅ SHIPPED | `aebff39` |
| 11 | Research / Regime + Alpha Edge + Tear Sheet + Stress + Journal | ✅ SHIPPED | `020933c` |
| 12 | Settings (10 tabs) + Command Palette + Shortcuts | ✅ SHIPPED | `e3a8300` |
| 12+ | Polish: notification drawer, ? help, ⌘K strategy/symbol search, tear-sheet backend fix | ✅ SHIPPED | `b89106d` |
| Post-12 | Hedge fund dashboard: 10 analytics improvements across all surfaces | ✅ SHIPPED | `42fdb48` |

### Post-Sprint-12 fixes and improvements (all shipped)

| Commit | What |
|---|---|
| `ebe860b` | Cycle pipeline stuck on Proposals (stage mapping + auto-completion) · Equity chart Realised toggle fix · mode-switch loading state · Execution sub-tabs (Slippage/TCA/Analytics) · Approaching graduation card |
| `f634e06` | Approaching graduation: proper backend endpoint grouping by (template_name, symbol) across all strategy versions |
| `e42958d` | Session timeout: 30min → 480min to match cookie max_age |
| `1f79e6c` | Sessions persisted to DB (user_sessions table) — survive backend restarts |
| `69e4723` | Graduation gate: 3 structural bugs (wrong WF sharpe key, strategy_id grouping, rejection cooldown) |
| `978c6fd` | Graduation queue SQL GroupingError fix (CTE rewrite) + YAML race condition (detect regime before read) |
| `5dfd601` | Win rate threshold 45% → 55% + graduation params surfaced in Settings / Live Trading |
| `42fdb48` | 10 hedge fund analytics improvements (see below) |

### Hedge fund dashboard improvements (commit `42fdb48`)

1. **Command / DEMO vs LIVE split tile** — side-by-side account cards in Pulse panel
2. **Command / Alpha generation tile** — 7d and 30d total return
3. **Strategies / Library status bar** — BACKTESTED · PAPER · LIVE · RETIRED filter badges
4. **Book / Execution summary strip** — 6 execution metrics above sub-tabs
5. **Command / Fund Scorecard** — replaces HealthScoreCard with 6 real metrics (Sharpe, Sortino, max DD, win rate, profit factor, total return)
6. **Research / Performance pipeline funnel** — Proposed → Backtested → Paper → Live with conversion rates
7. **Book / Execution Analytics DEMO vs LIVE split** — side-by-side account summaries
8. **Command / Daily Briefing** — collapsible auto-generated text summary
9. **Research / Attribution strategy deep-dive** — click any row to open trade journal + metrics drawer
10. **Guard / Live trading health card** — virtual equity, real equity, live positions, today's real P&L

## ⚡ NEXT SESSION KICKOFF

**Frontend rebuild v2 is complete (Sprints 0-12 + polish). All 5 surfaces + Settings are live at https://alphacent.co.uk. The platform is now in active iteration — fixing bugs, improving analytics, and tuning the graduation/live trading pipeline.**

**🔴 FIRST LIVE TRADE EXECUTED: 4H EMA Ribbon Trend Long × GOOGL — $850 virtual / $85 real on eToro Agent Portfolio. Position open as of 2026-05-11 14:10 UTC.**

---

## SESSION 2026-05-11 — WHAT WAS DONE

### P0 Frontend fixes (all shipped)

| Commit | What |
|---|---|
| `148e581` | LIVE/DEMO data separation in analytics (account_type filter on equity_snapshots + positions) · equity chart % mode · attribution overlap fix · returns histogram bar width |
| `7a0dc7e` | Equity chart: drawdown sign fix · realized rebase fix · hover alpha double-rebase · stale series on mode switch · DemoLiveSplitTile independent DEMO query |
| `42fc92d` | Graduation: fix paper metrics snapshot (aggregated cross-version) · LIVE badge in library |
| `8a911e5` | Walk-forward data: synthesize from strategy_metadata for autonomous strategies (was showing "No walk-forward data" for all strategies) |

### Live trading architecture (all shipped)

| Commit | What |
|---|---|
| `9634798` | Signal gen: pre-filter scoped to account_type · live-independent pass in scheduler |
| `a8a1883` | Graduation creates new LIVE strategy row (single symbol) instead of promoting source |
| `0f6e22c` | LIVE strategies excluded from DEMO cycle, run exclusively in live-independent pass |
| `6f3108e` | eToro Agent Portfolio endpoints fixed · min order size · routing · retirement guards |
| `8019867` | FMP cache warm threshold 95%→80% |
| `cc52d75` | Graduation paper Sharpe uses aggregated cross-version stats · DB record patched |
| `3e35cd8` | Live authorisations: compact rows + side panel detail (no dialog) |
| `2625ef4` | Live authorisations: prominent cards + WF/Paper/Live deep-dive drawer |

### Current system state (2026-05-11 end of session)

- **DEMO equity:** ~$491K | **Open positions:** 57 | **Regime:** trending_up_strong
- **DEMO strategies:** 47 PAPER + 64 BACKTESTED
- **LIVE strategy:** `4H EMA Ribbon Trend Long GOOGL LIVE` (id: `918b0c99`) — status LIVE, symbols `["GOOGL"]`
- **LIVE positions:** 1 open — GOOGL LONG, entry $394.96, `account_type='live'`
- **live_strategies row:** id=1, conviction_min=73, size=$850, SL=6%, TP=15%
- **Trade journal:** 1,041 closed DEMO trades
- **Latest commit:** `6f3108e`

---

## LIVE TRADING ARCHITECTURE — HOW IT WORKS NOW

### Graduation flow (proper)
1. CIO approves (template, symbol) pair from Graduation tab
2. `approve_graduation()` creates:
   - New `strategies` row: `status=LIVE`, `symbols=[symbol]` (single symbol only), inherits rules/risk from source
   - `graduation_approvals` row with aggregated cross-version paper stats
   - `live_strategies` row with CIO-approved size/SL/TP/conviction_min
3. Source PAPER/BACKTESTED strategy is **untouched** — continues generating DEMO trades
4. New LIVE strategy is excluded from DEMO signal cycle

### Signal generation (two independent paths)
- **DEMO cycle**: runs PAPER + BACKTESTED strategies, `account_type='demo'` pre-filter, fires DEMO orders on eToro Demo
- **Live-independent pass** (Phase 2B): runs after every DEMO cycle, loads LIVE strategies from DB, calls `generate_signals(account_type='live', conviction_override=live_strategies.conviction_min)`, fires live orders on eToro Agent Portfolio

### Key invariants
- DEMO positions never block LIVE entries (pre-filter scoped to account_type)
- LIVE strategies never appear in DEMO cycle (excluded from active_strategies query)
- LIVE strategies never auto-retired by autonomous cycle (explicit skip in `_check_and_retire_strategies`)
- LIVE strategies don't count against DEMO max_active_strategies cap
- Pending closures route to correct eToro client (live vs demo) based on `position.account_type`
- Live order status checked by live_order_monitor (not DEMO monitor)

### eToro Agent Portfolio endpoints (official API v1.158.0)
- **Positions**: `GET /api/v1/trading/info/real/pnl` → `clientPortfolio.positions` (camelCase)
- **Order status**: `GET /api/v1/trading/info/real/orders/{orderId}`
- **Place order**: `POST /api/v1/trading/execution/market-open-orders/by-amount`
- **Close position**: `POST /api/v1/trading/execution/market-close-orders/positions/{positionId}`
- **Min order size**: $10 (eToro actual minimum) — live executor uses `min_position_size=10`

---

## OPEN ITEMS FOR NEXT SESSION

### 🔴 P0 — Critical bugs

**1. Duplicate live orders on pre-market placement**
When a live order is placed pre-market, eToro queues it. The order is marked CANCELLED by the DEMO monitor (wrong client) before the position appears. The live pass fires again next cycle → duplicate orders. Fix needed:
- Live pass must check for existing live pending orders/positions before firing
- Check `orders WHERE account_type='live' AND status='PENDING' AND symbol=_live_sym` before generating signal
- Also check `positions WHERE account_type='live' AND symbol=_live_sym AND closed_at IS NULL`

**2. eToro position ID oscillation**
eToro returns different position IDs for the same position across sync calls (order ID vs position ID). The sync oscillates between IDs causing spurious "closed" events. Fix: match by `(symbol, strategy_id, opened_at proximity)` as fallback when `etoro_position_id` not found.

**3. live_strategies.live_trades / live_pnl not updating**
The `live_strategies` row has `live_trades=0, live_pnl=0` even though a position is open. Need to update these from `positions WHERE account_type='live'` on each sync.

### 🟡 P1 — Important

**4. Conviction threshold not persisted across restarts (YAML vs DB)**
The live pass uses `_appr.conviction_min` from DB (correct). But the YAML `conviction_threshold=74` is still the global default for DEMO. If someone changes conviction in Settings, it writes YAML — that's correct for DEMO. For LIVE, the per-strategy `conviction_min` in `live_strategies` is the source of truth. This is now correct but worth documenting clearly.

**5. Graduation min_trades lowered to 15 (temporary)**
`graduation_gate` YAML section doesn't exist — defaults to hardcoded 20. Was lowered to 15 via Settings for this session. Should add `graduation_gate` section to YAML with `min_trades: 15` to persist across restarts.

**6. P0 frontend items not fully resolved**
- Conviction Score Calibration chart in Execution/Analytics — check if it renders correctly
- Annual Returns chart in Research/Performance — verify with real data
- Attribution tab overlap — verify fix worked

**7. Graduation queue shows "Missing: no WF sharpe on record"**
The approaching graduation panel shows this for strategies without `wf_test_sharpe` in metadata. The WF synthesis fix (commit `8a911e5`) should help but verify.

### 🟢 P2 — Polish / improvements

**8. Live position in UI**
Book → Live should now show the GOOGL position. Verify the live P&L, entry price, SL/TP display correctly. The `live_strategies.live_trades` counter needs wiring to increment when a live position closes.

**9. Session continuation doc update**
Update `graduation_gate` thresholds in YAML to persist the min_trades=15 change.

**10. P1-P6 from previous session**
- P1: Graduation threshold calibration (min time span + min avg P&L per trade) — GOOGL is at 15 trades, 22-day span, $53.59 avg P&L. Consider adding `min_span_days=14` and `min_avg_pnl=10` gates.
- P2: YAML race condition proper fix (store market_regime in DB) — still open
- P3: AutonomousStrategyManager config reload — still open
- P5: Raise DEMO conviction threshold to 74 — still at 65 (DEMO), 73 (LIVE for GOOGL)
- P6: Strategy deep-dive drawer aggregation across versions — still open

---

## GRADUATION GATE STATE

- **Thresholds (active):** min_trades=15 (via Settings, not persisted in YAML), min_win_rate=55%, min_qualification_ratio=0.60, rejection_cooldown=14d
- **Active live pair:** 4H EMA Ribbon Trend Long / GOOGL — 15 trades, 80% WR, Sharpe 6.59, P&L +$803.87
- **live_strategies id=1:** conviction_min=73, size=$850, SL=6%, TP=15%
- **LIVE strategy id:** `918b0c99-c31e-4395-a434-cee5e07163d5`
- **Source BACKTESTED strategy:** `4b777482-4458-406b-ab96-41d2c89ad2eb` (continues running DEMO)

---

## KNOWN ISSUES / TECHNICAL DEBT

- **errors.log**: pre-existing graduation SQL transaction error (graduation_approvals query in failed transaction block) — cosmetic, doesn't affect trading
- **MQS persistence**: `_save_hourly_equity_snapshot` wraps MQS computation in `except: pass` — NULL values in recent snapshots
- **Triple EMA Alignment DSL bug**: `EMA(10) > EMA(10)` always false — Batch 4 fix pending
- **Sector Rotation + Pairs Trading templates**: structurally broken — design session needed
- **Entry order 82% FAILED rate**: cosmetic — market-closed deferrals written as FAILED then re-fired

---

## SESSION START CHECKLIST

```bash
# Health + errors
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'tail -20 /home/ubuntu/alphacent/logs/errors.log'
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'tail -10 /home/ubuntu/alphacent/logs/cycles/cycle_history.log'

# Live position status
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo -u postgres psql alphacent -t -A -c "SELECT id, symbol, side, entry_price, current_price, unrealized_pnl, account_type, opened_at FROM positions WHERE account_type='"'"'live'"'"' AND closed_at IS NULL;"'

# Live strategy signal gen (check for LIVE FILL or conviction gate)
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'grep -n "LIVE FILL\|conviction.*gate\|GOOGL LIVE\|live.*independent" /home/ubuntu/alphacent/logs/alphacent.log | tail -10'

# Strategy counts
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo -u postgres psql alphacent -t -A -c "SELECT status, COUNT(*) FROM strategies GROUP BY status ORDER BY status;"'

# DEMO account state
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo -u postgres psql alphacent -t -A -c "SELECT mode, balance, equity, positions_count, updated_at FROM account_info ORDER BY updated_at DESC;"'

# Sync autonomous_trading.yaml (always do this — Settings page writes it live)
scp -i ~/Downloads/alphacent-key.pem ubuntu@34.252.61.149:/home/ubuntu/alphacent/config/autonomous_trading.yaml config/autonomous_trading.yaml
```

---

## NEXT SESSION PROMPT

Use this prompt to start the next session:

```
Read .kiro/steering/trading-system-context.md and Session_Continuation.md in full before doing anything.

System state:
- DEMO: ~$491K equity, 57 open positions, trending_up_strong, 47 PAPER + 64 BACKTESTED strategies
- LIVE: 1 open position — GOOGL LONG entry $394.96 (4H EMA Ribbon Trend Long, conviction_min=73)
- Latest commit: 6f3108e

Priority items this session:

P0 — Fix duplicate live orders on pre-market placement:
The live-independent pass in trading_scheduler.py fires even when a live order is already pending/filled. Before calling generate_signals for a live strategy, check: (a) positions WHERE account_type='live' AND symbol=_live_sym AND closed_at IS NULL — if exists, skip entry signals; (b) orders WHERE account_type='live' AND symbol=_live_sym AND status='PENDING' — if exists, skip. This prevents the 3-order problem we saw on 2026-05-11.

P0 — Fix eToro position ID oscillation:
The live sync oscillates between position IDs (3438564904 ↔ 3438608761 ↔ 3438627355) for the same GOOGL position. The sync uses etoro_position_id as the match key but eToro returns different IDs. Fix: in sync_positions, when a position is not found by etoro_position_id, also try matching by (symbol, strategy_id, opened_at within ±5 minutes) before creating a new row.

P0 — Wire live_strategies.live_trades and live_pnl:
Currently always 0. Should update from positions/trade_journal WHERE account_type='live' on each sync cycle.

P1 — Persist graduation min_trades=15 in YAML:
Add graduation_gate section to autonomous_trading.yaml: min_trades: 15, min_win_rate_pct: 55, min_qualification_ratio: 0.60, rejection_cooldown_days: 14

P1 — Frontend: verify P0 fixes from last session work correctly:
(a) Conviction Score Calibration chart in Execution/Analytics — does it render?
(b) Annual Returns in Research/Performance — does it show data?
(c) Attribution tab overlap — is it fixed?
(d) Command equity chart % mode — does LIVE show flat line vs DEMO growing?
(e) DemoLiveSplitTile — does it stay stable when switching DEMO/LIVE?

P2 — Live position display in Book/Live:
Verify GOOGL position shows correctly with entry price, current P&L, SL/TP. Check that the live_strategies detail panel in Graduation shows live_trades incrementing when position closes.

P2 — YAML race condition (P2 from previous sessions):
Store market_regime in DB (equity_snapshots or autonomous_cycle_runs) instead of YAML. The autonomous_strategy_manager writes market_regime to autonomous_trading.yaml after every cycle — this creates a race condition with the Settings page.

Ongoing — Watch live signal generation:
Check alphacent.log for "LIVE FILL (independent pass)" entries. The GOOGL position is open so the pre-filter should block new ENTER_LONG signals until it closes. When it closes (via SL/TP/exit condition), the next signal cycle should fire a new live order if conditions are met.
```
- **LIVE account:** Agent Portfolio | Virtual: $10K | Real: $1K | Mirror: 10%
- **LIVE positions:** 0 | **live_trading.enabled:** TRUE | **Live authorisations:** 0
- **Trade journal:** 1,003 closed trades (DEMO) across 380 strategy IDs
- **Graduation queue:** empty (best pair: 4H EMA Ribbon Trend Long / GOOGL at 15/20 trades)
- **errors.log baseline:** last entry 2026-05-11 09:16:52 (pre-existing graduation SQL errors, now fixed)
- **Latest commit:** `42fdb48`

### Graduation gate state

- **Thresholds (as of this session):** min_trades=20, min_win_rate=55%, min_qualification_ratio=0.60, rejection_cooldown=14d
- **Configurable from:** Settings → Live Trading → Graduation gate thresholds (takes effect immediately, no restart)
- **Best approaching pair:** 4H EMA Ribbon Trend Long / GOOGL — 15 trades, 80% WR, Sharpe 6.6, P&L +$804
- **Gate logic:** groups by (template_name, symbol) across ALL strategy versions — historical trades from retired strategies count
- **WF sharpe key:** `wf_test_sharpe` in strategy_metadata (was broken, now fixed)

### Key backend additions since last session doc

- `user_sessions` table — DB-persisted sessions survive restarts
- `GET /strategies/approaching-graduation` — top candidates building toward graduation, grouped by (template_name, symbol)
- `GET /strategies/graduation-queue` — fixed to group by (template_name, symbol) with CTE rewrite
- `GET /config/live-trading` — now returns graduation gate thresholds
- `PUT /config/live-trading` — now writes graduation gate thresholds + patches in-memory constants immediately
- `graduation_gate.py` — reads thresholds from YAML `graduation_gate` section on startup

### Open items for next session

**P1 — Graduation threshold discussion**
- Current: 20 trades, 55% WR, 0.60 qual ratio
- Best pair (GOOGL) is at 15/20 trades — could reach threshold in ~2 weeks
- Consider: minimum time span (e.g. trades must span ≥14 days) to prevent a single momentum burst graduating a pair
- Consider: minimum avg P&L per trade (e.g. >$10) to filter pairs profitable only by tiny margins

**P2 — YAML race condition (partial fix)**
- The autonomous_strategy_manager writes market_regime to autonomous_trading.yaml after every cycle
- Fix applied: detect regime BEFORE reading the file (shrinks race window from seconds to milliseconds)
- Proper fix: store market_regime in the database instead of YAML — it's already in equity_snapshots and autonomous_cycle_runs
- Worth doing when convenient

**P3 — Live conviction gate wiring (pre-existing)**
- In trading_scheduler.py live fill routing block, the conviction gate reads the threshold but the comparison may not be fully wired
- Check: `_sig_conv < _live_conv_min` block in the live fill routing section

**P4 — Raise DEMO conviction threshold to 74 (pre-existing)**
- Calibration shows 74-76 is first clearly positive-EV bucket
- Change in Settings → Autonomous → Conviction Score Threshold

**P5 — Strategy deep-dive in Research/Attribution**
- The drawer opens but the trade journal query uses `strategyId` (single strategy_id)
- Should ideally aggregate across all strategy versions for the same (template, symbol) pair
- Low priority — the current implementation is honest about what it shows

**P6 — AutonomousStrategyManager config reload**
- The manager loads config once at startup from YAML
- Settings page changes (proposal_count, etc.) take effect on next restart
- Consider: add a `reload_config()` method called by the PUT /config/autonomous endpoint

### Session start checklist

```bash
# Health + errors
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'tail -20 /home/ubuntu/alphacent/logs/errors.log'
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'tail -30 /home/ubuntu/alphacent/logs/cycles/cycle_history.log'

# Strategy counts
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo -u postgres psql alphacent -t -A -c "SELECT status, COUNT(*) FROM strategies GROUP BY status ORDER BY status;"'

# Graduation pipeline
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo -u postgres psql alphacent -t -A -c "SELECT COALESCE(s.strategy_metadata->>'"'"'template_name'"'"', REGEXP_REPLACE(s.name, '"'"' V[0-9]+\$'"'"', '"'"''"'"')) AS tname, tj.symbol, COUNT(*) AS trades, ROUND(100.0*SUM(CASE WHEN tj.pnl>0 THEN 1 ELSE 0 END)/COUNT(*),1) AS wr, ROUND(SUM(tj.pnl)::numeric,2) AS pnl FROM trade_journal tj JOIN strategies s ON s.id=tj.strategy_id WHERE tj.pnl IS NOT NULL AND tj.account_type='"'"'demo'"'"' GROUP BY tname, tj.symbol HAVING COUNT(*) >= 5 ORDER BY trades DESC LIMIT 15;"'

# Active sessions (should survive restarts now)
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo -u postgres psql alphacent -t -A -c "SELECT username, expires_at FROM user_sessions WHERE expires_at > NOW() ORDER BY expires_at DESC;"'
```

### Foundation already in place — do not rebuild

- **Primitives**: Button, Input, Select, Tabs, Dialog, ConfirmDialog, Popover, DropdownMenu, Tooltip, Switch, Checkbox, Badge, Card, Skeleton, Spinner, EmptyState, ErrorState, Label, Separator, **DataTable** (TanStack Table + Virtual, auto-virtualize >100 rows, sort, multi-select, sticky header, density, row menu)
- **Layout**: PageTemplate, PanelHeader, ResizablePanelLayout (Zustand-persisted), SectionLabel, MetricGrid, FilterBar, SaveBar
- **Trading components**: AccountToggle, WebSocketIndicator, TopNavBar, **PnLNumber** (mono tabular-nums + 400 ms flash via keyframes in globals.css), **RegimePill**, **LivePill** (3 states), **ConvictionBar** (mini + default + large, threshold line), **EquityChart** (LWC v5 with drawdown pane, SPY overlay, realised line, period/interval, hover readout), **PriceChart** (LWC candlestick with signal markers), **ModifyRiskDialog**, **SignalFeed**, **OrderFillsTicker**, **LifecycleFeed**, **AlertsBadge**
- **Hooks**: `useWebSocketQueryBridge` (invalidates `positions`, `orders`, `strategies`, `autonomous-status`, `system-status`, `autonomous-cycles`, `fundamental-alerts`, `recent-signals`, `live-summary`, `dashboard`, reconnect toast + full invalidation), `useKeyboardShortcuts` (g c/b/s/g/r/, + ⌘K), `useWebSocketState`
- **Stores**: trading-mode, layout, theme, command-palette, filters, notifications, research
- **Data hooks in `pages/book/useBookData.ts`**: positions (open/pending-open/pending-closures/fundamental-alerts/closed), close / close-all / approve-closure / bulk-approve / dismiss-closure / dismiss-fundamental-alert / sync-positions / modify-position-risk / delete-closed-positions; orders (list/execution-quality/cancel/delete/bulk-delete/close-position-from-order/sync/place); live (summary/config/update-config/divergence/retire-strategy/close-live-position). `AllOrdersTab` accepts `pinMode` so any surface can scope it to DEMO or LIVE without forking.
- **Data hooks in `pages/strategies/useStrategiesData.ts`** (Sprint 5): `useStrategies({ slim, include_retired, status_filter })`, `useStrategy(id)` for detail, `useStrategyBacktest`, `useActivateStrategy`, `useDeactivateStrategy`, `useRetireStrategy`, `useDeleteStrategyPermanent`, `useGraduateStrategy`, `useRejectGraduation`. Derived helpers `isGraduationEligible`, `isIdle7d`, `hasSignalToday`, `hasNegativeLivePnl`, `hasPaper20Plus` for the Library quick-pill filters. Sprint 6 adds `useSystemStatus`, `useAutonomousSchedules`, `useUpdateSchedules`, `useAutonomousCycles`, `useGraduationFunnel`, `useTriggerCycle`, `useSystemStateTransition` + the `SPEC_STAGES` / `mapBackendStageToSpec` helpers that bridge backend stage names onto the spec's 9 business-logic stages. Sprint 7 adds `useTemplates`, `useToggleTemplate`, `useBulkToggleTemplates`, `useTemplateRankings`, `useSymbolStats`, `useBlacklistedCombos`, `useIdleDemotions`, `useGraduationQueue`, `useLiveStrategies`, `useRetireLiveStrategy`, `useVibeCodeTranslate`, `useGenerateStrategy`, `useBootstrap` — plus `liveConvictionThresholdFor` and `assetClassForSymbol` derived helpers for the GraduationCard's live gate lookup.
- **CSV** (`lib/csv.ts`): RFC-4180 quoting, UTF-8 BOM for Excel
- **Market hours** (`lib/market-hours.ts`): client-side classifier for UI hints only — not a trading gate
- **Design tokens** (`lib/design-tokens.ts` + `styles/tokens.css`): every hex from spec §3A plus `regimeColor()` / `convictionColor()` / `pnlColor()` helpers

### Backend additions since rebuild started (all shipped)

- `PUT /account/positions/{id}/risk-levels` — modify SL/TP; server validates asset-class caps, side-sanity, immediate-breach warnings; emits `position_update` WS (commit `fccb40f`)
- `POST /account/positions/trigger-fundamental-check` — existing handler that was missing a `@router.post` decorator (commit `fccb40f`)
- `src/risk/sl_caps.py` — shared SL/TP cap helper (stocks/ETFs 9%, leveraged ETFs 20%, crypto 15%, forex 4%, etc.) — single source of truth for both order_executor and the new endpoint
- `GET /account/dashboard/summary` + `/account/metrics-bar` — every aggregation now scoped by `account_type` (positions, orders, equity_snapshots). LIVE dollar fields are rescaled by `live_trading.mirror_ratio` (0.10) at egress so the Command page shows real money (~$1K on Agent Portfolio) rather than virtual (~$10K). `/live/summary` stays unchanged — it exposes both sides explicitly. Commit `15a5394`.
- `_sync_account_from_etoro` — synchronous companion to the fire-and-forget `_refresh_account_from_etoro`. Dashboard handler blocks briefly on it when `account_info` has no row for the requested mode, so the first LIVE view renders real numbers instead of zeros.
- `MonitoringService._sync_account_info(account_type)` — called for both demo and live alongside the 60s position sync. Keeps `account_info` fresh proactively instead of waiting for the UI to poke it.
- `etoro_client.get_account_info` — unified LIVE + DEMO parsing. eToro returns the same `{"clientPortfolio": {...}}` nested shape for both accounts; the old LIVE branch looked for flat `"Credit"/"Equity"` keys that don't exist, so every LIVE field silently parsed as 0.

### Infra adjustments

- `deploy/nginx-alphacent.conf` (Sprint 5) — SPA routes that share a prefix with backend API paths (`/strategies/*`, `/account/*`, `/orders/*`, etc.) now fall through to `index.html` when the request `Accept` header contains `text/html`. API clients always send `Accept: application/json`, browsers always send `text/html` on top-level navigation, so this cleanly separates the two without forking the IA. Installed at `/etc/nginx/sites-enabled/alphacent` on EC2 (backup at `/tmp/nginx-alphacent.prev.conf`).

### System state entering next session (as of Sprint 7 shipping)

- **DEMO equity:** ~$491K | **Open positions:** ~63 | **Regime:** `trending_up_strong`
- **DEMO strategies:** 49 PAPER + 74 BACKTESTED (counts move cycle-to-cycle; run the diagnostic query below for fresh numbers)
- **LIVE account:** Agent Portfolio | Virtual: $10,000 | Real: $1,000 | Mirror: 10%
- **LIVE positions:** 0 | **live_trading.enabled:** TRUE | **Live authorisations:** 0
- **Sprint 7 bundle:** `Strategies-*.js` ≈ 191 KB raw (44.5 KB gzip), still inside the 250 KB budget. Templates/Symbols/Graduation/Lab all mount on the same route split — revisit code-splitting if Sprint 8 pushes past 250 KB.
- **Latest commits on main:** `b52ea72` (Sprint 7) ← `69fc07e` (Sprint 6 promote pipeline) ← `99157a8` (Session doc: Sprint 6) ← `6d1aa89` (Sprint 6) ← `a97e86f` (Session doc: LIVE dashboard fix) ← `15a5394` (LIVE dashboard fix) ← `042c2c5` (Sprint 5) ← `aa1f171` (Session kickoff restructure) ← `62c55b7` (Sprint 4 session doc) ← `f22db70` (Sprint 4) ← `c9006ee` (Sprint 3) ← `fccb40f` (SL/TP backend) ← `ae2c78f` (Sprint 2) ← `d297d85` (Sprint 1) ← `1171d41` (Sprint 0)
- **errors.log:** clean — most recent entry is still 2026-05-09 23:24 stale `promoted_to_demo` (pre-rename, expected)

### Sprint 12 notes

- **Zero new backend endpoints.** All 10 Settings tabs wire existing /config, /auth, /alerts routes. Same approach as Sprint 9 — "honesty over invention".
- **AutonomousTab schema-driven.** `autonomous-config-schema.ts` defines every editable field (~65 across 16 collapsible sections). Adding a field = one schema row. Search (Fuse.js) hits label + help + section, and matching sections auto-expand so finding a knob is one keystroke away. `pickEditableFields` narrows the 300+-key response to just what the form edits; on save we merge the form onto the full server payload so read-only nested blocks (direction_aware_thresholds, advanced_readonly) round-trip unchanged.
- **Every Autonomous field has a FieldInfoTooltip** with help text and an optional `gates:` pointer — the steering doc's "every threshold is tied to the log line it gates" made concrete.
- **Alerts tab doesn't fork the dialog.** Surfaces the existing AlertPreferencesDialog from Guard so there's exactly one codepath to AlertConfigORM. Saves a lot of duplicate form logic.
- **Users tab degrades gracefully on 403.** Non-admin sessions see a friendly "manage_users permission required" banner instead of a raw 403 error.
- **CommandPalette mounted in AppShell.** Lives in `frontend/src/components/CommandPalette.tsx`. ⌘K anywhere, Fuse fuzzy search across navigation + surface subroutes + theme + logout, recent-commands persisted via the existing command-palette store. Keyboard nav (↑↓ / Enter) parity with mouse.
- **Settings chunk 58 KB raw / 15 KB gzip** (inside budget). index chunk grew ~35 KB because CommandPalette has to mount before any tab loads — acceptable for global keyboard access.

**Polish (post-Sprint-12 commit `b89106d`):**
- **Notification drawer** — `useAutonomousNotifications` hook bridges `autonomous_notifications` + `autonomous_cycle` WS events into the notifications Zustand store. `NotificationDrawer` is a Radix Dialog positioned as a right side-sheet (420px). Groups by Today/Yesterday/date. Bell button in TopNavBar with unread badge.
- **? keyboard shortcut help** — `KeyboardShortcutHelp` dialog opened by `?` / `Shift+/` from anywhere outside a text input. `useKeyboardShortcuts` wired.
- **⌘K strategy + symbol search** — CommandPalette lazy-fetches `/strategies?slim=true` and `/strategies/symbols` when open. Results appear as Strategies and Symbols sections. Each item navigates to the relevant library/symbols route.
- **Backend tear-sheet fix** — `/analytics/tear-sheet` crashed with `autodetected range of [-1.0, inf] is not finite` when equity_snapshots contained rows with equity = 0. Fixed by replacing zero/negative equities with NaN before computing returns, stripping non-finite values via finite_mask, and using `np.fmax.accumulate` (NaN-safe) for the underwater plot.

### Sprint 11 notes

- **Regime tab pulls from the single `/analytics/regime-comprehensive` endpoint.** Four asset-class regime cards, perf-by-regime table, transitions timeline, strategy×regime Visx heatmap, market context (VIX / yield curve / fed funds / CPI / GDP / PMI), crypto cycle, forex carry rates, and MQS card. Regime chips use the existing `regime-*` badge variants so colour semantics are consistent with Command / Guard.
- **Alpha Edge tab uses `/analytics/alpha-edge/*` (fundamental, ML, conviction distribution, template performance, TCA).** ConvictionDistributionChart is a Recharts ComposedChart: Bar for counts, Line for win-rate overlay when present, ReferenceLines at 65 (DEMO) and 74 (LIVE) thresholds, bars coloured by which threshold they cross. Degrades cleanly to a plain BarChart when win_rate isn't available.
- **Tear sheet** is fully wired to `/analytics/tear-sheet`. UnderwaterPlot is Visx AreaClosed + LinePath; ReturnDistribution computes annualised σ from the backend's bucketed histogram so the header stat is consistent with the skew/kurtosis it's paired with. The AnnualReturnsGrid uses one-tile-per-year with a signed mini-bar rather than a traditional column chart — much denser at desktop widths.
- **Stress tab.** Backend returns three hardcoded historical scenarios (COVID / Lehman / SVB) with simulated portfolio curves computed via portfolio-beta ≈ 0.70. The CustomScenarioBuilder is client-side — reads the current open positions from /account/positions, applies `shock × vol × (1+Δρ) × √(H/5)` per-position, and short positions profit on negative shocks. Banner flags this as a what-if, not VaR — we don't pretend it's a Monte Carlo engine.
- **Journal tab.** Virtualised DataTable (500-row client cap; backend supports pagination when needed). MAE/MFE scatter with a 45° break-even guide: dots above = winner that left money on the table, dots below = trailing stop was too tight. CSV export via `buildTradeJournalExportUrl` direct href (same blob-less pattern as Sprint 9 audit).

### Sprint 10 notes

- **Research is read-only.** No mutations, no WS subscriptions — it's cold analytics data, pollers beat events here. Every hook polls on 2min / 5min intervals per the spec.
- **Period + interval** selectors live in the existing `research` Zustand store so switching tabs keeps selection. Only the Performance tab shows the interval selector (spec §Surface 5 defers intraday-resolution on other views). Number keys 1..8 jump between tabs.
- **MonthlyReturnsHeatmap** uses the ParentSize + custom SVG rects pattern from Sprint 8's CorrelationHeatmap rather than @visx/heatmap. Same reason: diverging scale with "no data" cells needs a custom fill path. Reused cleanly by the TearSheet tab (wrapper component, same data shape).
- **Annual returns compounded** via ∏(1+r/100) − 1 from the monthly_returns map rather than summed — simple correctness win, matches how returns work.
- **PerStrategyAttributionTable** renders a signed mini-bar scaled to the portfolio's max |contribution|, centred on a 50% baseline so positives and negatives read at a glance.
- **SectorAttributionPanel** uses a custom stacked horizontal bar rather than Recharts' stacked bar because Brinson decomposition has three signed effects and Recharts' divergence behaviour is awkward; the CumulativeEffects area chart below does use Recharts.
- **HoldingPeriodHistogram bug fix before ship.** Earlier draft synthesised a Gaussian distribution around the mean, which violates the "don't invent data" rule. Rewired to real per-trade buckets from /analytics/trade-journal with the backend mean plotted as a ReferenceLine. Less flashy but honest.

### Sprint 9 notes

- **No new endpoints, no new deps.** Every tab wires an existing route — `/control/system-health` for system + breakers + gates (already used in Sprint 8), `/data/*` for sync/quality/fmp-cache/news, `/alerts/*` for history + config, `/audit/log` + `/audit/trade-lifecycle/{id}` + `/audit/export` for the audit tab.
- **Adaptive polling on data sync.** `useDataSyncStatus` flips `refetchInterval` via a callback: 5s while `sync_running` is true, 30s idle. Keeps the log tail responsive during a full sync without hammering the backend the rest of the time.
- **Trade lifecycle endpoint takes a raw id.** Audit entries come back prefixed (`ord-<uuid>`, `pos-<uuid>`, `sig-<id>`) — only `ord-` / `pos-` rows can drill into `/audit/trade-lifecycle/{id}`, and I strip the prefix before the call. Signal / strategy / rejection rows expand to show inline metadata instead, labelled honestly.
- **Export CSV is a direct href.** `buildAuditExportUrl` turns the filter state into a query string and the Button's child `<a href>` streams the CSV. Avoids blob churn and the click-to-download-url dance.
- **Circuit-breaker reset is honest.** `/control/circuit-breaker/reset` is a single-target endpoint that clears the RiskManager-level CB, not the per-API (eToro/Yahoo/FMP) breakers. The grid renders per-category cards from `system_health.circuit_breakers[]` but the action label says "Reset global breaker" and a footer note flags the extension needed for per-API resets. Not faked.
- **Alert preferences dialog** reads and writes the full `AlertConfigORM` shape — thresholds for PNL loss/gain, drawdown, position loss, margin, plus toggles for cycle-complete and strategy-retired notifications and browser push.
- **System tab** is a single scrollable column. At desktop widths everything fits the 70% right panel without horizontal scroll. EventTimeline24h plots events along a 24h baseline with severity-coded dots at `right: ageInHours/24 * 100%`.

### Sprint 8 notes

- **Route-shadow discipline holds.** Guard's tabs under `/guard/*` never shadow other routes because the surface owns its whole subtree — but the lesson from Sprint 7 (static paths must precede `{id}` catch-alls) is documented in the strategies router and worth carrying forward into any new endpoint.
- **30/70 Guard layout** — `ResizablePanelLayout` `layoutId="guard"` persists. Left panel is permanent: RiskScoreHero + RiskMetricTiles + LimitEditor + KillSwitchCard. Right tabs: Risk (shipped), Gates (shipped), System / Circuit Breakers / Alerts / Audit (ComingSoon with sprint: 9).
- **LimitEditor breach-warning banner** compares every proposed limit against the matching current metric from `/risk/metrics` and lists each breach before Save. Stops the CIO from quietly tightening a ceiling the portfolio already exceeds.
- **KillSwitchCard shows blast radius** — the success toast reports `positions_closed` and `orders_cancelled` from the response, so you see what the button actually did. Also flips to Reset From Emergency when `/control/system/status.state === EMERGENCY_HALT`.
- **CorrelationHeatmap (Visx)** uses the `correlated_pairs` array from `/risk/advanced` — so the axis is just the union of symbols that have at least one correlation entry. Threshold slider fades cells below `|ρ|` instead of hiding them (preserves grid continuity). Unseen pairs render as "no data" not zero.
- **Gates tab** reads `trading_gates[]` from `/control/system-health` directly — no new endpoint. Sorted so blocking gates float to the top and pulse; detail text rendered verbatim above the static descriptor paragraph. 10 gate descriptors ship; unknown gate names fall back to a generic descriptor so adding a gate on the backend just works.

### Sprint 7 notes

- **Flagship is Graduation.** `GraduationCard` renders paper KPIs, conviction decomposition (9-component stacked bar against the 74/68 live threshold), live-config form (size / SL / TP / conviction_min / notes), and an impact preview that turns `$500 virtual` into `$50 real` via the mirror ratio from `/live/summary`. Approval invalidates `graduation-queue`, `live-strategies`, `live-divergence`, `live-summary`, `strategies`.
- **Defaults sourced from `/config/live-trading`**, not hardcoded. The card uses `min_order_size`/`max_order_size` for the sizing slider bounds, and `conviction_threshold`/`conviction_threshold_crypto` for the default live-gate minimum. Equity defaults 6% SL / 15% TP; crypto 8% SL / 20% TP. Asset class inferred from `strategy.metadata.asset_class` and a symbol-pattern fallback.
- **One endpoint gap surfaced honestly.** `/strategies/live` returns `retired_at IS NULL` rows only, so the post-retirement re-graduation countdown has nowhere to pull from. Rather than invent a list I rendered a scoped gap panel on the Graduation tab and flagged it as a backend extension candidate before Sprint 8.
- **Templates tab** uses the full `/strategies/templates` response (active / activated / traded / proposed counts, best/worst symbol, avg perf). Bulk-toggle selects one template at a time via checkboxes in card headers; direction + asset-class + enabled filters; TemplateRankingsTable joins `/strategies/template-rankings` with template metadata for the family/timeframe filter.
- **Symbols tab** ships both Current (active_strategies + usage + open positions) and Lifetime (proposed + traded + Sharpe + P&L + best_template) views as a pill toggle that also updates the default sort. Row click opens a `SymbolDetailDrawer` with a gap section acknowledging the missing per-symbol timeseries endpoint. Blacklists + Idle Demotions render as accordion tables below.
- **Lab tab** hosts `BacktestRunnerPanel`, `VibeCodePanel`, `GenerateStrategyPanel`, `BootstrapPanel`. 2×2 grid at ≥1280px, stacked below. Number keys 1-4 jump between panels. Backtest results render as a KPI grid; the LWC equity curve overlay lands with Sprint 11 when the trade-journal series is wired.
- **Keyboard in Graduation:** j/k moves queue selection, Esc closes the card. Enter is reserved (approval requires the deliberate Approve button to avoid single-keystroke live approvals).
- `sprint: 7` markers removed from the TABS config in `Strategies.tsx`. All six tabs now render real content.

### Session start checklist

```bash
# Health + recent cycles
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'tail -20 /home/ubuntu/alphacent/logs/errors.log'
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'tail -30 /home/ubuntu/alphacent/logs/cycles/cycle_history.log'

# Fresh state counts
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo -u postgres psql alphacent -t -A -c "SELECT status, COUNT(*) FROM strategies GROUP BY status ORDER BY status;"'
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo -u postgres psql alphacent -t -A -c "SELECT balance, equity, updated_at FROM account_info ORDER BY updated_at DESC LIMIT 1;"'
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo -u postgres psql alphacent -t -A -c "SELECT COUNT(*) FROM live_strategies WHERE retired_at IS NULL;"'

# Only sync autonomous_trading.yaml if the session will touch live config
scp -i ~/Downloads/alphacent-key.pem ubuntu@34.252.61.149:/home/ubuntu/alphacent/config/autonomous_trading.yaml config/autonomous_trading.yaml
```

---

## Legacy notes — previous session history

The sections below capture context from earlier sessions (Phase 2A/2B live trading infrastructure, eToro API research). They're preserved for reference but the frontend rebuild is the active track. Scroll past to find the older content if you need it.

---

### What was completed earlier (2026-05-10)

**Phase 2A — Core live trading infrastructure (all 10 sprints shipped):**

| Sprint | What | Commit |
|---|---|---|
| 1 | DB migrations: `account_type` on positions/orders/equity_snapshots, `graduation_approvals`, `live_strategies` + ORM | `9d38017` |
| 2 | `EToroAPIClient` refactor: `account_type='demo'/'live'`, backward-compat `mode=` kwarg | `d02c731` |
| 3 | Dual-client startup in `app.py`: demo + optional live client, global getters | `fa56ca5` |
| 4 | `MonitoringService` dual-sync: live position sync, equity snapshots per account | `fa56ca5` |
| 5 | `TradingScheduler` signal routing: DEMO fill always, LIVE fill if approved + enabled | `fc5fd59` |
| 6 | `autonomous_trading.yaml` `live_trading` section: all sizing params | `fc5fd59` |
| 7 | `graduation_gate.py` + 4 API endpoints: queue, approve, reject, list live | `fc5fd59` |
| 8 | Graduation Gate UI in AutonomousNew, CIO Decision Card | `cb6bed1` |
| 9 | API client methods: live config, graduation, live strategies | `cb6bed1` |
| 10 | MetricsBar live pill, Settings → Live Trading tab | `cb6bed1` |

**Phase 2B — Live trading completeness (all P0 + P1 shipped):**

| Sprint | What | Commit |
|---|---|---|
| 2B-1 | Live RiskManager uses live equity ($10K not $491K), enforces live order bounds | `c4b12db` |
| 2B-2 | Live positions/orders endpoint filtering by `account_type` | `c4b12db` |
| 2B-3 | `trade_journal.account_type` migration — paper/live P&L separation | `c4b12db` |
| 2B-4 | Strategies page `● Live (N)` tab with Retire button (this was frontend_v1) | `814c2a1` |
| 2B-5 | Dedicated `/live` page in frontend_v1: Overview, Positions, Orders, Graduation Gate, Divergence | `814c2a1` |
| 2B-6 | `● Live` nav item, `/live` route, permissions in `auth.py` | `814c2a1` |
| + | Live conviction gate: separate thresholds DEMO vs LIVE (equity 74, crypto 68) | `814c2a1` |
| + | Equity snapshot UniqueViolation fixed (dropped stale `ix_equity_snapshots_date`) | `d76d34c` |
| + | nginx: `index.html` no-cache, `/live/` API proxy routing | `d76d34c` |
| + | `auth.py` ROLE_PERMISSIONS: added `live`, `system-health`, `audit-log` | `d76d34c` |

**eToro LIVE API — confirmed facts (do not re-research):**
- SL update endpoint does NOT exist (all 5 candidates returned 404, confirmed 2026-05-10)
- TSL is DB-side enforcement only; eToro's initial SL is the outage backstop
- eToro widens SL beyond requested level (~10% floor observed on BTC live account)
- `InstrumentId` (lowercase d) for LIVE close, `InstrumentID` (uppercase D) for DEMO close

---

## eToro LIVE API — confirmed facts

| | Value |
|---|---|
| Base URL | `https://public-api.etoro.com` |
| Auth headers | `x-api-key` + `x-user-key` + `x-request-id` (UUID) |
| Agent virtual balance | `$10,000` (what `credit` field reports) |
| Real investment | `$1,000` (your money at risk) |
| Mirror ratio | `10%` — every agent $1,000 order = $100 real exposure |
| Open order | `POST /api/v1/trading/execution/market-open-orders/by-amount` |
| Close position | `POST /api/v1/trading/execution/market-close-orders/positions/{positionId}` body: `{"InstrumentId": id}` (lowercase d) |
| Portfolio/balance | `GET /api/v1/trading/info/real/pnl` |
| Order status | `GET /api/v1/trading/info/real/orders/{orderId}` |
| Trade history | `GET /api/v1/trading/info/trade/history?minDate=YYYY-MM-DD` |
| SL update | **NOT SUPPORTED** — all candidate endpoints return 404 |

**Position sizing for live account:**
- Each agent order: `$200–$1,500 virtual` → `$20–$150 real`
- `min_order_size`: $200 virtual | `max_order_size`: $1,500 virtual | `symbol_cap`: $2,000 virtual

---

## Architecture: PAPER + LIVE run simultaneously

A strategy stays `PAPER` status. Graduation is per **(template, symbol) pair** via `live_strategies` table.

```
PAPER strategy "4H EMA Ribbon Trend Long" — watchlist: [AAPL, MSFT, NVDA]
  AAPL: approved via Graduation Gate → live_strategies row exists
  MSFT: not approved

Signal fires for AAPL:
  → DEMO client: paper fill (always)
  → LIVE client: real fill (only if live_trading.enabled=true AND live_strategies row exists
                            AND signal.conviction_score >= live_trading.conviction_threshold)

Signal fires for MSFT:
  → DEMO client: paper fill only
```

**Conviction thresholds (independent for DEMO and LIVE):**
- DEMO: 70 (equities) / 68 (crypto) — lower to collect more paper data
- LIVE: 74 (equities) / 68 (crypto) — higher bar for real money

---

## Current System State (May 10, 2026)

- **DEMO Equity:** ~$491K | **Open positions:** ~65 | **Regime:** `trending_up_strong`
- **DEMO Strategies:** 50 PAPER + 66 BACKTESTED
- **LIVE Account:** Agent Portfolio | Virtual: $10,000 | Real: $1,000 | Mirror: 10%
- **LIVE positions:** 0 | **live_trading.enabled:** TRUE
- **Service:** healthy | **errors.log:** clean

---

## Key Parameters

### Risk per asset class
Stock/ETF: SL 6%, TP 15% | Forex: SL 2%, TP 5% | Crypto: SL 8%, TP 20% | Index: SL 5%, TP 12% | Commodity: SL 4%, TP 10%

### Position sizing (DEMO)
- `BASE_RISK_PCT`: 0.6% | `MINIMUM_ORDER_SIZE`: $2,000 | Symbol cap: 5% | Sector soft cap: 30% | Portfolio heat: 30%
- Drawdown sizing: 50% reduction >5% DD, 75% >10% DD (30d rolling peak)
- Vol scaling: 0.10x–1.50x (target vol 16%)

### Position sizing (LIVE)
- `BASE_RISK_PCT`: 0.6% of virtual equity ($10K) | `MIN_ORDER`: $200 virtual ($20 real) | `MAX_ORDER`: $1,500 virtual ($150 real)
- Symbol cap: 20% of virtual balance | Portfolio heat cap: 90%
- Conviction threshold: 74 equities / 68 crypto

### Activation thresholds
- `min_sharpe`: 1.0 | `min_sharpe_crypto`: 0.3 | `min_sharpe_commodity`: 0.5
- `min_trades_dsl`: 8 (1d/4h) | 15 (1h) | `min_trades_alpha_edge`: 8
- Conviction threshold: 70 (DEMO) | 74 (LIVE fills)

### ATR stop floor (order_executor, hardcoded)
- 1.5× ATR for daily strategies | 2.0× ATR for 4H strategies
- Max SL clamps: stocks/ETFs 9%, crypto 15%, forex 4%

### Trailing Stop System
- Per-class ATR multiplier: stock/etf/commodity 2.0x, crypto/index 1.5x, forex 1.0x
- Timeframe-aware ATR (4H strategies use 4H bars)
- **LIVE:** DB-side enforcement only (eToro LIVE API has no SL-update endpoint)

### Signal-time gates
- **C1 VIX**: blocks LONG when VIX>25 AND VIX_5d>+15% (crypto exempt)
- **C2 Momentum Crash**: regime_fit −10 for LONG trend/momentum/breakout when SPY_5d<−3% AND VIX_1d>+10%
- **C3 Trend Consistency**: blocks SHORT above rising 50d SMA or oversold-bounce; blocks LONG below falling 50d SMA

### Directional quotas (trending_up regimes)
- `trending_up_strong`: min_long 85%, min_short 3%
- `trending_up`: min_long 80%, min_short 5%

---

## Observability & Logs

| File | Use |
|---|---|
| `logs/errors.log` | ERROR + CRITICAL only — **check first every session** |
| `logs/cycles/cycle_history.log` | Structured cycle summaries |
| `logs/strategy.log` | Signal gen, WF, conviction |
| `logs/risk.log` | Position sizing, risk validation |
| `logs/alphacent.log` | Full INFO+ audit trail |

---

## Diagnostic Queries

```sql
-- Strategy status counts
SELECT status, COUNT(*) FROM strategies GROUP BY status ORDER BY status;

-- Live strategies
SELECT ls.template_name, ls.symbol, ls.activated_at, ls.live_trades, ls.live_pnl,
       ga.qualification_ratio, ga.paper_sharpe, ga.wf_sharpe
FROM live_strategies ls
JOIN graduation_approvals ga ON ga.id = ls.graduation_id
WHERE ls.retired_at IS NULL ORDER BY ls.activated_at DESC;

-- Graduation queue candidates
SELECT s.name, tj.symbol, COUNT(*) AS trades,
       ROUND((AVG(tj.pnl) / NULLIF(STDDEV(tj.pnl), 0) * SQRT(252))::numeric, 2) AS sharpe,
       ROUND(100.0 * SUM(CASE WHEN tj.pnl > 0 THEN 1 ELSE 0 END) / COUNT(*)::numeric, 1) AS win_pct
FROM trade_journal tj JOIN strategies s ON s.id = tj.strategy_id
WHERE s.status = 'PAPER' AND tj.pnl IS NOT NULL AND tj.account_type = 'demo'
GROUP BY s.id, s.name, tj.symbol HAVING COUNT(*) >= 20 ORDER BY sharpe DESC;

-- Decision-log funnel (last cycle)
SELECT stage, decision, COUNT(*) FROM signal_decisions
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY stage, decision ORDER BY COUNT(*) DESC;

-- Conviction score vs P&L
SELECT FLOOR(conviction_score / 5) * 5 AS bucket, COUNT(*) AS trades,
       ROUND(AVG(pnl)::numeric, 2) AS avg_pnl,
       ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_pct
FROM trade_journal
WHERE conviction_score IS NOT NULL AND pnl IS NOT NULL AND account_type = 'demo'
GROUP BY bucket ORDER BY bucket;
```

---

## Open Items

### P1 — Live conviction gate wiring (3-line fix)
In `trading_scheduler.py` live fill routing block, check `signal.metadata.conviction_score` against `_live_cfg.get("conviction_threshold")` before calling `_live_order_executor.execute_signal`. Currently the gate reads the threshold but doesn't block — the check was added but the `else:` block structure needs the actual comparison wired in.

### P2 — Raise DEMO conviction threshold to 74
Calibration monitor shows 74–76 is first clearly positive-EV bucket (+$21.72 avg, 49 trades). 70–74 range is negative EV. Change in Settings → Autonomous → Conviction Score Threshold.

### P3 — Cross-cycle signal dedup (~1h)
TXN ENTER_LONG fires every 10 minutes for hours. 30-min TTL map on `(strategy_id, symbol, direction)` in `trading_scheduler`.

### P4 — WF test-dominant regime-luck gate for LONG (~1h)
Add `(test_sharpe - train_sharpe) ≤ 1.5` consistency check to test-dominant bypass path.

### P5 — GET /strategies 422 (pre-existing)
Some component calls `/strategies` without `mode` param. Logs 422. Not crashing.

### Deferred
- **Frontend rebuild** — see prompt below (Track A)
- **Pairs Trading template rebuild** — needs cross-asset spread primitives in DSL first
- **Overview chart panel rewrite** — 3 chart components with misaligned axes
- **CI/CD hardening** — GitHub Actions pipeline
- **SignalDecisionLogORM table drop** — scheduled 2026-06-03
- **Commodity 1h coverage** — blocked on FMP Starter upgrade

---

## DB Migrations Applied to Prod (cumulative)

```sql
-- 2026-05-10: Phase 2B-3
ALTER TABLE trade_journal ADD COLUMN account_type VARCHAR(10) NOT NULL DEFAULT 'demo';
CREATE INDEX idx_trade_journal_account_type ON trade_journal(account_type);
DROP INDEX ix_equity_snapshots_date;  -- stale unique index causing UniqueViolation on live snapshots

-- 2026-05-10: Phase 2A
ALTER TABLE positions ADD COLUMN account_type VARCHAR(10) NOT NULL DEFAULT 'demo';
ALTER TABLE orders ADD COLUMN account_type VARCHAR(10) NOT NULL DEFAULT 'demo';
ALTER TABLE equity_snapshots ADD COLUMN account_type VARCHAR(10) NOT NULL DEFAULT 'demo';
ALTER TABLE equity_snapshots DROP CONSTRAINT uq_equity_snapshot_date_type;
CREATE UNIQUE INDEX uq_equity_snapshot_date_type_account ON equity_snapshots(date, snapshot_type, account_type);
CREATE TABLE graduation_approvals (...);
CREATE TABLE live_strategies (...);

-- 2026-05-10: StrategyStatus rename
UPDATE strategies SET status='PAPER' WHERE status='DEMO';
ALTER TABLE autonomous_cycle_runs RENAME COLUMN promoted_to_demo TO promoted_to_paper;

-- 2026-05-04: Signal decisions + proposals
ALTER TABLE orders ADD COLUMN order_metadata JSON;
ALTER TABLE strategy_proposals ADD COLUMN symbols JSON, ADD COLUMN template_name VARCHAR;
CREATE TABLE signal_decisions (...);
ALTER TABLE autonomous_cycle_runs ADD COLUMN proposals_pre_wf INTEGER;

-- Earlier
ALTER TABLE positions ADD COLUMN invested_amount FLOAT;
ALTER TABLE orders ADD COLUMN order_action VARCHAR, slippage FLOAT, fill_time_seconds FLOAT;
```

---

## New session kickoff prompt

Use this prompt to start the next session:

```
Start this session by reading, in this exact order:
(1) .kiro/steering/trading-system-context.md — permanent rules
(2) Session_Continuation.md — current system state (read the NEXT SESSION KICKOFF block carefully)

Confirm you've read both, then begin.

==========================================================================
CONTEXT
==========================================================================

AlphaCent is a live autonomous trading platform. The frontend v2 rebuild
is complete (Sprints 0-12 + post-sprint polish). We are now in active
iteration — fixing bugs, improving analytics, and tuning the graduation
and live trading pipeline.

Production: https://alphacent.co.uk
Latest commit: 42fdb48

System state:
- DEMO equity: ~$9,995 | Open positions: 61 | Regime: trending_up_strong
- DEMO strategies: 48 PAPER + 56 BACKTESTED
- LIVE account: Agent Portfolio | Virtual $10K / Real $1K / Mirror 10%
- LIVE positions: 0 | live_trading.enabled: TRUE | Live authorisations: 0
- Trade journal: 1,003 closed DEMO trades across 380 strategy IDs
- Graduation queue: empty (best pair: 4H EMA Ribbon Trend Long / GOOGL at 15/20 trades)
- errors.log baseline: last entry 2026-05-11 09:16:52

==========================================================================
OPERATING RULES (non-negotiable)
==========================================================================

1. Proper solutions only — no stopgaps, ever.
2. Local is source of truth. EC2 is a deploy target.
3. Deploy after every meaningful change. Verify before moving on:
   - npm run typecheck passes
   - npm run build succeeds clean
   - curl https://alphacent.co.uk/ returns 200
   - errors.log has no NEW entries post-deploy
4. Push with -c core.hooksPath=/dev/null (git-defender pre-push hook).
5. Think like a trader. Every feature evaluated through "would a CIO trust this?"
6. Don't create markdown files unless asked.
7. Backend route order: static paths BEFORE dynamic {id} catch-alls.

==========================================================================
DEPLOY COMMAND (copy-paste)
==========================================================================

cd frontend
VITE_API_BASE_URL=https://alphacent.co.uk \
VITE_WS_BASE_URL=wss://alphacent.co.uk \
npm run build

scp -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no -r \
dist ubuntu@34.252.61.149:/home/ubuntu/alphacent/frontend/dist_next

# Verify assets landed BEFORE swapping
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no \
ubuntu@34.252.61.149 \
'ls /home/ubuntu/alphacent/frontend/dist_next/assets/ | grep -E "index|Command|Guard" | head -3'

ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no \
ubuntu@34.252.61.149 \
'cd /home/ubuntu/alphacent/frontend && rm -rf dist_prev && mv dist dist_prev && mv dist_next dist && echo "swapped"'

curl -sf -o /dev/null -w "prod %{http_code}\n" https://alphacent.co.uk/
curl -sf -o /dev/null -w "health %{http_code}\n" https://alphacent.co.uk/health

==========================================================================
WHAT'S BUILT — FULL SURFACE INVENTORY
==========================================================================

Frontend directory: frontend/
Backend: src/ (FastAPI/Python)

SURFACES (all live):
- / (Command) — Pulse panel (DEMO/LIVE split, alpha gen, fund scorecard,
  daily briefing, pipeline counts, regime, cycle status) + Equity chart
  (LWC v5, SPY overlay, drawdown, realised) + Stream panel
- /book — Positions (4 sub-tabs) · Orders · Execution (Slippage/TCA/Analytics
  with DEMO vs LIVE split) · Live
- /strategies — Cycle (pipeline visual, funnel, scheduler) · Library
  (status bar, detail panel, compare) · Templates · Symbols · Blacklist ·
  Graduation (queue + approaching-graduation card + GraduationCard) · Lab
- /guard — Risk · Gates · System · Circuit Breakers · Alerts · Audit +
  Live trading health card in left panel
- /research — Performance (fund scorecard tiles, equity curve, pipeline
  funnel, monthly heatmap) · Attribution (deep-dive drawer) · Trades ·
  Regime · Alpha Edge · Tear Sheet · Stress · Journal
- /settings — Trading Mode · API Config · Risk Limits · Position Management ·
  Autonomous (65-field schema-driven form) · Alpha Edge · Alerts · Live
  Trading (incl. graduation gate thresholds) · Users · Shortcuts
- /login

GLOBAL:
- ⌘K command palette (navigation + strategy/symbol search)
- Notification drawer (WS autonomous_notifications + cycle events)
- ? keyboard shortcut help
- Bell badge in TopNavBar with unread count

KEY PRIMITIVES (frontend/src/components/):
- primitives/: Button, Input, Select, Tabs, Dialog, ConfirmDialog, Popover,
  DropdownMenu, Tooltip, Switch, Checkbox, Badge, Card, Skeleton, Spinner,
  EmptyState, ErrorState, Label, Separator, DataTable (TanStack + Virtual)
- layout/: PageTemplate, PanelHeader, ResizablePanelLayout, SectionLabel,
  MetricGrid, FilterBar, SaveBar
- trading/: AccountToggle, WebSocketIndicator, TopNavBar, PnLNumber,
  RegimePill, LivePill, ConvictionBar, EquityChart (LWC v5), PriceChart,
  ModifyRiskDialog, SignalFeed, OrderFillsTicker, LifecycleFeed, AlertsBadge

KEY BACKEND ENDPOINTS (all registered, all working):
- /account/dashboard/summary, /account/metrics-bar, /account/positions/*
- /analytics/performance, /analytics/strategy-attribution, /analytics/tca,
  /analytics/tear-sheet, /analytics/regime-comprehensive,
  /analytics/alpha-edge/*, /analytics/trade-journal, /analytics/stress-tests,
  /analytics/conviction-calibration, /analytics/rolling-statistics
- /strategies/graduation-queue, /strategies/approaching-graduation,
  /strategies/live, /strategies/{id}/graduate, /strategies/{id}/reject-graduation
- /config/autonomous, /config/live-trading (incl. graduation gate thresholds),
  /config/risk, /config/alpha-edge, /config/credentials
- /control/system/status, /control/autonomous/cycles, /control/autonomous/schedules
- /auth/login, /auth/logout, /auth/users (CRUD)
- /alerts/history, /alerts/config, /audit/log, /audit/trade-lifecycle/{id}

KEY DATABASE TABLES (PostgreSQL):
- strategies, positions, orders, trade_journal, equity_snapshots
- graduation_approvals, live_strategies, user_sessions (new — persists sessions)
- autonomous_cycle_runs, signal_decisions, strategy_proposals
- users, alerts, audit_log

==========================================================================
OPEN ITEMS (prioritised)
==========================================================================

P1 — Graduation threshold calibration (discuss before implementing)
  Current: 20 trades, 55% WR, 0.60 qual ratio
  Best pair (GOOGL) at 15/20 trades — could reach threshold in ~2 weeks
  Consider: minimum time span (trades must span ≥14 days)
  Consider: minimum avg P&L per trade (>$10) to filter tiny-margin pairs
  Configurable from Settings → Live Trading → Graduation gate thresholds

P2 — YAML race condition (partial fix applied)
  autonomous_strategy_manager writes market_regime to autonomous_trading.yaml
  after every cycle. Partial fix: detect regime BEFORE reading the file.
  Proper fix: store market_regime in DB (already in equity_snapshots +
  autonomous_cycle_runs) instead of YAML.

P3 — AutonomousStrategyManager config reload
  Manager loads config once at startup. Settings page changes (proposal_count
  etc.) take effect on next restart only.
  Fix: add reload_config() called by PUT /config/autonomous.

P4 — Live conviction gate wiring (pre-existing)
  In trading_scheduler.py live fill routing, verify _sig_conv < _live_conv_min
  comparison is fully wired and blocking correctly.

P5 — Raise DEMO conviction threshold to 74
  Calibration shows 74-76 is first clearly positive-EV bucket.
  Change in Settings → Autonomous → Conviction Score Threshold.

P6 — Strategy deep-dive drawer (Research/Attribution)
  Currently shows single strategy_id trades. Should aggregate across all
  strategy versions for the same (template, symbol) pair.

==========================================================================
TECHNICAL DECISIONS LOCKED IN
==========================================================================

- React 19 + TypeScript 5.9 + Vite 6 + Tailwind 4
- TanStack Query 5 + Zustand 5
- TradingView Lightweight Charts v5 (LWC) for equity/price charts
- Recharts 3.x for analytics charts
- Visx 4.0.0-alpha.11 for bespoke layouts (heatmaps, underwater plots, scatter)
- TanStack Table 8 + TanStack Virtual 3 for all tables
- Fuse.js 7 for fuzzy search (command palette, autonomous form)
- No --legacy-peer-deps. Every dep resolves cleanly.
- Native fetch, not axios.
- Sessions: DB-persisted (user_sessions table), 8h rolling timeout
- YAML: autonomous_trading.yaml is the authoritative config for the running
  system. Settings page writes it via PUT /config/autonomous. The autonomous
  manager reads it at startup only (P3 above).
- Nginx SPA routing: browser nav (Accept: text/html) falls through to
  index.html. API client sets Accept: application/json. No conflict.
- Push with: git -c core.hooksPath=/dev/null push origin main

==========================================================================
PROCEED
==========================================================================

Read the session continuation file, check errors.log and strategy counts,
then ask what to work on or proceed with the highest-priority open item.
```

**Before starting the spec session, run this on EC2 to backup the deployed frontend:**
```bash
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 \
  'cp -r /home/ubuntu/alphacent/frontend /home/ubuntu/alphacent/frontend_v1_backup && echo "Backup done"'
```

**Then archive the local frontend in git (do this at the START of the spec session, not before):**
```bash
git mv frontend frontend_v1
git commit -m "Archive frontend v1 before rebuild — preserved in git history and EC2 backup"
```

The new frontend goes in `frontend/`. Nginx serves `frontend/dist` — that path stays identical. Instant rollback: swap `frontend_v1_backup` back on EC2.

---

**PROMPT:**

```
Start this session by reading, in this exact order:

(1) .kiro/steering/trading-system-context.md

(2) Session_Continuation.md — full file

Confirm you've read both, then begin.

==========================================================================

CONTEXT

==========================================================================

System: ~$491K DEMO equity, 65 open positions, trending_up_strong.

Live Agent Portfolio: $10K virtual / $1K real / 10% mirror ratio.
check last commmits

Service: healthy. errors.log: clean.

This session shipped (all working and deployed):

- StrategyStatus.DEMO → PAPER (17 Python files + DB migration)

- Frontend PAPER fix (8 files)

- eToro LIVE API tested and confirmed working

- Live credentials stored encrypted at config/live_credentials.json

- Full Phase 2 architecture designed (10 sprints)

==========================================================================

MISSION — I want to build a brand new AlphaCent frontend from scratch. The existing frontend is being archived — no code, no components, no patterns carry forward. This is a greenfield design.

## WHAT WE'RE BUILDING

AlphaCent is an autonomous trading platform. The backend is a FastAPI/Python system that:
- Runs 50+ PAPER strategies simultaneously on a $491K eToro DEMO account (65 open positions)
- Has a LIVE trading account (Agent Portfolio, $10K virtual / $1K real, 10% mirror ratio) with a Graduation Gate for promoting paper-validated (template, symbol) pairs to real fills
- Uses a full autonomous cycle: propose → walk-forward validate → Monte Carlo bootstrap → conviction score → activate → signal → execute
- Connects to eToro's public API for order execution, position sync, and market data
- Uses TradingView Lightweight Charts (npm package already available)
- Has WebSocket for real-time updates (positions, orders, signals, cycle events)
- Exposes ~80 REST endpoints

The goal: the best autonomous trading dashboard ever built. State of the art design, best-in-class charts, consistent design system, every component built from scratch.

## PHASE 1 — AUDIT THE EXISTING SYSTEM (extract the WHAT, not the HOW)

Read the existing codebase to build a complete inventory of capabilities. We are not preserving any of this code — we are extracting knowledge. Every feature, every data flow, every user action, every edge case that exists today must be captured so nothing gets missed in the new design.

### 1A. Backend API surface — read every router
Read every file in `src/api/routers/`:
`account.py`, `orders.py`, `strategies.py`, `control.py`, `performance.py`, `analytics.py`, `risk.py`, `signals.py`, `config.py`, `live.py`, `alerts.py`, `market_data.py`, `dashboard.py`, `data_management.py`, `audit.py`

For each endpoint, extract:
- Path, method, query params
- Response shape (key fields)
- What business concept it serves
- How frequently it should be called (real-time, polling, on-demand)

### 1B. WebSocket event system
Read `src/api/websocket_manager.py` and `frontend/src/services/websocket.ts`.
Extract every event type, its payload shape, and what UI element it should update.

### 1C. Existing pages — extract features, not code
Read every file in `frontend/src/pages/`.
For each page, extract:
- Every piece of data displayed (what fields, what aggregations)
- Every user action (buttons, forms, filters, toggles)
- Every edge case handled (empty states, loading states, errors)
- What's currently broken or incomplete (note these as gaps to fix in the new design)

### 1D. Data models and types
Read `frontend/src/types/` and `frontend/src/contexts/`.
Extract the complete data model: what entities exist, their fields, their relationships.

### 1E. Current package.json
Read `frontend/package.json`.
List all current dependencies and versions.

**Output of Phase 1:** A structured feature inventory — every capability the system has, organized by domain (account, positions, orders, strategies, autonomous cycle, live trading, analytics, risk, settings, system health).

## PHASE 2 — RESEARCH (define the HOW)

Research the state of the art in trading platform UI/UX design (2024-2026). Use web search.

### 2A. Professional trading terminals
Research: Bloomberg Terminal, Refinitiv Eikon, TradingView platform (not just charts).
Extract: information hierarchy patterns, how they handle data density, color systems, typography choices, layout patterns for multi-panel views.

### 2B. Algorithmic and autonomous trading platforms
Research: QuantConnect (algorithm research + live trading), Composer (autonomous investing), Collective2 (strategy marketplace), Alpaca dashboard.
Extract: how they make algorithmic decisions transparent to humans, how they show strategy performance, how they handle paper vs live account separation.

### 2C. Modern fintech dashboards
Research: best-in-class examples of dark-theme financial dashboards (search for "trading dashboard design 2024", "fintech dark UI", "algorithmic trading interface").
Extract: design patterns that work for extended use, micro-interaction patterns, chart integration patterns.

### 2D. Chart library evaluation
Research and compare for our specific use cases:
- **Price/OHLC charts:** TradingView Lightweight Charts (already available) vs alternatives
- **Analytics charts (equity curves, drawdown, returns distribution):** Recharts vs Visx vs Nivo vs Observable Plot
- **Real-time data visualization:** how to handle 65 positions updating every 60s without jank
- **Heatmaps and matrices:** for regime-conditional performance, correlation matrices

### 2E. Component library and design system
Research: building a custom design system vs adopting one.
Evaluate: Radix UI primitives (headless, full control) vs shadcn/ui vs Ark UI vs Mantine.
The requirement: every component must be purpose-built for trading data — tables that handle 200 rows smoothly, numbers that flash on update, charts that render without layout shift.

### 2F. State management and data fetching
Research: TanStack Query vs SWR for the hybrid polling/WebSocket pattern we need.
Research: Zustand vs Jotai vs Context for trading state (account, positions, regime).

**Output of Phase 2:** Technology decisions with justification, design language definition, reference examples for each major UI pattern.

## PHASE 3 — DESIGN THE NEW PLATFORM

Using the feature inventory from Phase 1 and the research from Phase 2, design the new platform from scratch. Every decision is made here. Nothing is left as "TBD".

### 3A. Design system specification
Define completely:
- **Color palette:** exact hex values for every token — background layers (3 levels), surface, border, text (4 levels), green/red P&L, regime colors (trending_up/down/ranging/high_vol), conviction heat gradient (0-100), live account accent, demo account accent, warning/error/success
- **Typography:** font stack (consider JetBrains Mono for numbers, Inter/Geist for UI), size scale (10px to 24px), weight usage, line heights
- **Spacing system:** base unit, scale
- **Component states:** every interactive component has default, hover, active, focus, loading, error, empty, disabled states defined
- **Animation principles:** what animates (P&L number flash on update, new signal pulse, cycle stage progress), duration, easing. What never animates (tables, charts — performance first)
- **Layout system:** grid, panel split ratios, responsive breakpoints (this is a desktop-first trading app — mobile is secondary)

### 3B. Page architecture
For each page, define:
- **Purpose:** one sentence — what decision does this page help the user make?
- **Primary layout:** panel configuration, tab structure
- **Data sources:** exact endpoints + WebSocket events, polling intervals
- **Key components:** what goes where
- **Empty/loading/error states:** what the user sees before data arrives
- **User actions:** every button, form, filter — what it does, what API call it makes

Pages to design:
1. **Overview / Command Centre** — real-time portfolio health, regime, active cycle status, recent signals
2. **Portfolio** — DEMO + LIVE positions, TSL status, sector exposure, P&L attribution
3. **Orders** — DEMO + LIVE order history, execution quality, slippage analysis
4. **Strategies** — PAPER/BACKTESTED/LIVE tabs, strategy detail panel, walk-forward evidence, conviction decomposition
5. **Autonomous** — cycle pipeline visualization, signal funnel, scheduler, cycle history
6. **Live Trading** — master switch, graduation gate (CIO workflow), live positions, paper vs live divergence
7. **Analytics** — equity curve, drawdown, Sharpe by regime, returns distribution, MAE/MFE
8. **Risk** — portfolio heat map, sector exposure, VaR, signal-time gates status, directional quotas
9. **Settings** — API config, risk limits, autonomous params, live trading params (all in one place, tabbed)
10. **System Health** — background threads, circuit breakers, data freshness, error log

### 3C. Component library specification
Define every reusable component:
- **Name and purpose**
- **Props interface** (TypeScript)
- **Visual specification** (size, color, states)
- **Usage examples** (which pages, in what context)

Required components include (but are not limited to):
- `MetricsBar` — top bar with real-time account metrics
- `AccountToggle` — DEMO / LIVE switcher
- `RegimePill` — colored badge for market regime
- `LivePill` — ● LIVE / ○ LIVE OFF indicator
- `ConvictionBar` — stacked bar showing conviction score components
- `PnLNumber` — number that flashes green/red on update
- `EquityChart` — TradingView or Recharts equity curve with drawdown overlay
- `PriceChart` — TradingView Lightweight Charts OHLC with signal markers
- `StrategyCard` — compact strategy summary with key metrics
- `GraduationCard` — CIO decision card for live approval
- `SignalFunnel` — visual pipeline from proposed → filled
- `DataTable` — high-performance table with sorting, filtering, virtual scroll
- `HeatMap` — for regime-conditional performance matrix
- `GateStatus` — traffic-light indicator for signal-time gates

### 3D. Technical stack decision
Make final decisions:
- Framework: React 18 + TypeScript + Vite (keep)
- Styling: Tailwind CSS (keep) + CSS variables for design tokens
- Component primitives: [decision from research]
- Data fetching: [decision from research]
- State management: [decision from research]
- Price charts: TradingView Lightweight Charts (keep)
- Analytics charts: [decision from research]
- Tables: TanStack Table (keep — best in class)
- Animations: Framer Motion (keep)
- Toasts: Sonner (keep)
- Icons: Lucide (keep)

### 3E. Implementation plan
Ordered sprints where each delivers a shippable increment:

**Sprint 0 — Foundation (must complete before any page work)**
- Scaffold new `frontend/` with chosen stack
- Implement complete design system (tokens, CSS variables)
- Build all primitive components (Button, Input, Badge, Card, Tabs, Select, Switch, Dialog, etc.)
- Build layout shell (AppShell, TopNav, MetricsBar, routing)
- Deploy empty shell to EC2 — verify it renders

**Sprint 1-N — Pages**
- One page per sprint, built entirely on the foundation
- Each sprint: page is complete, deployed, and verified before moving on
- Order: Overview → Portfolio → Strategies → Autonomous → Live Trading → Orders → Analytics → Risk → Settings → System Health

## DELIVERABLE

A single document that answers every question a developer would have before writing the first line of code:
- What does every page show and do?
- What does every component look like and how does it behave?
- What is the exact color of a positive P&L number?
- What happens when the WebSocket disconnects?
- How does the graduation gate CIO workflow work step by step?
- What chart library renders the equity curve and what are its exact props?

No ambiguity. No "similar to current". No "TBD". Every decision made.

Do not write any code. Produce the requirements document only.
```
