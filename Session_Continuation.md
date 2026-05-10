# AlphaCent — Session Continuation

> Permanent rules are in `.kiro/steering/trading-system-context.md`. This file holds current system state, recent fixes, and open items.

---

## ⚡ NEXT SESSION KICKOFF

**Read this block first. Two parallel tracks are open.**

### What was completed this session (2026-05-10)

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
| 2B-4 | Strategies page `● Live (N)` tab with Retire button | `814c2a1` |
| 2B-5 | Dedicated `/live` page: Overview, Positions, Orders, Graduation Gate, Divergence | `814c2a1` |
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

### System state entering next session

- **DEMO equity:** ~$491K | **Open positions:** ~65 | **Regime:** `trending_up_strong`
- **DEMO strategies:** 50 PAPER + 66 BACKTESTED
- **LIVE account:** Agent Portfolio | Virtual: $10,000 | Real: $1,000 | Mirror: 10%
- **LIVE positions:** 0 | **live_trading.enabled:** TRUE
- **Last commits:** `d76d34c` (bug fixes: equity snapshot, nav permissions, nginx, live switch)
- **errors.log:** clean (stale `promoted_to_demo` entries from 2026-05-09 are pre-rename, not new)
- **Live credentials:** `/home/ubuntu/alphacent/config/live_credentials.json` (encrypted)

### Session start checklist

```bash
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'tail -20 /home/ubuntu/alphacent/logs/errors.log'
ssh ... 'tail -30 /home/ubuntu/alphacent/logs/cycles/cycle_history.log'
ssh ... 'sudo -u postgres psql alphacent -t -A -c "SELECT status, COUNT(*) FROM strategies GROUP BY status ORDER BY status;"'
ssh ... 'sudo -u postgres psql alphacent -t -A -c "SELECT balance, equity, updated_at FROM account_info ORDER BY updated_at DESC LIMIT 1;"'
ssh ... 'sudo -u postgres psql alphacent -t -A -c "SELECT COUNT(*) FROM live_strategies WHERE retired_at IS NULL;"'
# IMPORTANT: sync autonomous_trading.yaml from EC2 before any session that touches it
scp -i ~/Downloads/alphacent-key.pem ubuntu@34.252.61.149:/home/ubuntu/alphacent/config/autonomous_trading.yaml config/autonomous_trading.yaml
```

---

## Two Open Tracks

### Track A — Frontend Rebuild (new spec, next major initiative)

The frontend has been built incrementally over many sessions. It works but is architecturally inconsistent — components added piecemeal, no unified design system, charts misaligned, pages with different patterns. The decision has been made to rebuild it from scratch as a proper spec.

**See the frontend rebuild prompt at the bottom of this file.** This is a full spec session: requirements document first, then design, then implementation sprints.

### Track B — Remaining Phase 2B items (small, can be done any session)

| Item | Priority | Effort |
|---|---|---|
| Live conviction gate wiring: check `signal.conviction_score` against `live_trading.conviction_threshold` before firing live fill | P1 | 3 lines in `trading_scheduler.py` live fill block |
| 2B-7: Remove Graduation Gate tab from Autonomous page (it has a proper home in `/live`) | P2 | 10 min |
| 2B-7: Paper equity curve in CIO Decision Card | P2 | ~1h |
| 2B-7: Re-graduation flow after retirement | P2 | ~1h |
| P3: Cross-cycle signal dedup (TXN fires every 10 min) | P2 | ~1h |
| P4: WF test-dominant regime-luck gate for LONG | P2 | ~1h |

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

---

**PROMPT:**

```
I want to rebuild the AlphaCent frontend from scratch as a proper spec-driven project.

AlphaCent is an autonomous trading platform. The backend is a FastAPI/Python system running on EC2 that:
- Runs 50+ PAPER strategies simultaneously on a $491K eToro DEMO account (65 open positions)
- Uses a full autonomous cycle: propose → walk-forward validate → Monte Carlo bootstrap → conviction score → activate → signal → execute
- Has a LIVE trading account (Agent Portfolio, $10K virtual / $1K real, 10% mirror ratio) with a Graduation Gate for promoting paper-validated (template, symbol) pairs to real fills
- Connects to eToro's public API for order execution, position sync, and market data
- Uses TradingView Lightweight Charts for price charts (already integrated via npm package)
- Has WebSocket for real-time updates (positions, orders, signals, cycle events)
- Exposes ~80 REST endpoints covering: account, positions, orders, strategies, autonomous cycle, analytics, performance, risk, signals, config, live trading, graduation gate

The current frontend was built incrementally over many sessions — it works but is architecturally inconsistent. I want to rebuild it from scratch as the best autonomous trading dashboard ever built.

Before writing any code, I want you to:

1. Research the state of the art in trading platform UI/UX design (2024-2026). Look at:
   - Professional trading terminals (Bloomberg, Refinitiv Eikon, TradingView)
   - Algorithmic trading dashboards (QuantConnect, Alpaca, Interactive Brokers TWS)
   - Modern fintech dashboards (Robinhood, Webull, Composer, Collective2)
   - Design systems optimized for data-dense financial interfaces
   Focus on: information hierarchy for autonomous systems, real-time data visualization patterns, dark theme best practices for trading, how to surface AI/autonomous decision-making clearly to a human operator.

2. Produce a comprehensive requirements document covering:

   A. DESIGN PRINCIPLES
   - Visual language: dark theme, typography, color system (green/red P&L, regime colors, conviction heat)
   - Information density: how to show 65 positions + 50 strategies without overwhelming
   - Real-time feel: what updates live vs what polls, flash animations, WebSocket integration
   - Autonomous system transparency: making the AI's decisions legible to a human CIO

   B. PAGE ARCHITECTURE (what pages exist and their purpose)
   - Overview / Command Centre
   - Portfolio (DEMO + LIVE accounts, positions, TSL status)
   - Orders (DEMO + LIVE, execution quality, slippage)
   - Strategies (PAPER/BACKTESTED/LIVE tabs, strategy detail, walk-forward evidence)
   - Autonomous (cycle pipeline, signal funnel, conviction decomposition, scheduler)
   - Live Trading (master switch, graduation gate, live positions, paper vs live divergence)
   - Analytics (equity curve, drawdown, Sharpe, regime-conditional performance)
   - Risk (portfolio heat map, sector exposure, VaR, signal-time gates status)
   - Settings (API config, risk limits, autonomous params, live trading params)
   - System Health (background threads, circuit breakers, data freshness)

   C. COMPONENT LIBRARY
   - What reusable components are needed (MetricsBar, DataTable, EquityChart, ConvictionBar, RegimePill, LivePill, GraduationCard, etc.)
   - TradingView chart integration patterns (Lightweight Charts for price, custom overlays for signals/stops)
   - Real-time update patterns (WebSocket subscriptions, optimistic updates, flash-on-change)

   D. TECHNICAL STACK DECISIONS
   - Keep: React 18, TypeScript, Vite, Tailwind CSS, TradingView Lightweight Charts, react-query or SWR for data fetching, Sonner for toasts
   - Evaluate: whether to keep current component library (shadcn/ui) or switch
   - State management: Context vs Zustand vs Jotai for trading state
   - Table library: TanStack Table (keep) vs alternatives
   - Chart library: TradingView Lightweight Charts (keep for price) + what for analytics charts

   E. AUTONOMOUS SYSTEM SPECIFIC REQUIREMENTS
   - How to visualize the full cycle pipeline (propose → validate → activate → signal → execute) as a live funnel
   - Conviction score decomposition (stacked bar per strategy showing component weights)
   - Walk-forward evidence display (train/test Sharpe, MC bootstrap distribution)
   - Signal decision audit trail ("why didn't we trade AAPL today?")
   - Regime-conditional performance matrix
   - Graduation Gate CIO workflow (paper equity curve, qualification ratio trend, approve/reject)

   F. LIVE TRADING SPECIFIC REQUIREMENTS
   - DEMO vs LIVE account separation throughout (account toggle, separate equity curves)
   - Mirror ratio display (always show virtual + real amounts)
   - TSL status (DB stop vs eToro backstop gap)
   - Divergence monitoring (live Sharpe vs paper Sharpe per authorized pair)

3. Produce a prioritized implementation plan broken into sprints, where each sprint delivers a shippable increment.

The backend API is fully functional. The rebuild is frontend-only. The existing backend endpoints, WebSocket events, and data models do not change.

Start with the research and requirements document. Do not write any code yet.
```
