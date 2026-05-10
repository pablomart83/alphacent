# AlphaCent — Session Continuation

> Permanent rules are in `.kiro/steering/trading-system-context.md`. This file holds current system state, recent fixes, and open items.

---

## ⚡ NEXT SESSION KICKOFF

**Frontend rebuild is Sprints 8-12 next. Read `.kiro/steering/trading-system-context.md` and `FRONTEND_REBUILD_SPEC.md` before touching code.**

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
| 7 | Strategies / Templates + Symbols + Graduation (flagship) + Lab | ✅ SHIPPED | `b52ea72` |
| 8 | Guard / Risk + Gates | **Next** |  |
| 9 | Guard / System + Circuit Breakers + Alerts + Audit | Pending |  |
| 10 | Research / Performance + Attribution + Trades | Pending |  |
| 11 | Research / Regime + Alpha Edge + Tear Sheet + Stress + Journal | Pending |  |
| 12 | Settings + cross-cutting polish (palette, shortcuts, a11y) | Pending |  |

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

## Frontend Rebuild — Spec Session Prompt

Use this prompt to kick off the frontend rebuild as a new spec in the next session.

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
