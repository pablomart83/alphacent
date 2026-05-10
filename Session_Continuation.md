# AlphaCent — Session Continuation

> Permanent rules are in `.kiro/steering/trading-system-context.md`. This file holds current system state, recent fixes, and open items.

---

## ⚡ NEXT SESSION KICKOFF — Phase 2B: Live Trading Completeness

**Read this block first.**

### What was completed this session (2026-05-10)

**Phase 2A — Core live trading infrastructure (all 10 original sprints shipped):**

| Sprint | What | Commit |
|---|---|---|
| 1 | DB migrations: `account_type` on positions/orders/equity_snapshots, `graduation_approvals`, `live_strategies` tables + ORM | `9d38017` |
| 2 | `EToroAPIClient` refactor: `account_type='demo'/'live'`, backward-compat `mode=` kwarg, `get_trade_history()`, fixed LIVE endpoints | `d02c731` |
| 3 | Dual-client startup in `app.py`: demo + optional live client, `get_demo/live_etoro_client()` globals | `fa56ca5` |
| 4 | `MonitoringService` dual-sync: live position sync tagged `account_type='live'`, equity snapshots per account | `fa56ca5` |
| 5 | `TradingScheduler` signal routing: after DEMO fill, checks `live_strategies` + `live_trading.enabled`, fires live fill | `fc5fd59` |
| 6 | `autonomous_trading.yaml` `live_trading` section: enabled=false (HARD GATE), all sizing params | `fc5fd59` |
| 7 | `graduation_gate.py` + 4 API endpoints: queue, approve, reject, list live | `fc5fd59` |
| 8 | Graduation Gate UI: tab in AutonomousNew, CIO Decision Card, approve/reject flow | `cb6bed1` |
| 9 | API client methods: `getLiveTradingConfig`, `updateLiveTradingConfig`, graduation methods | `cb6bed1` |
| 10 | MetricsBar live pill: `● LIVE` / `○ LIVE OFF` badge, fetches `/config/live-trading` | `cb6bed1` |
| + | Settings → Live Trading tab: master switch, order sizing, risk params, save/reset | `cb6bed1` |

**eToro LIVE API — confirmed facts (do not re-research):**
- SL update endpoint does NOT exist (all 5 candidates returned 404, confirmed 2026-05-10)
- TSL is DB-side enforcement only; eToro's initial SL is the outage backstop
- eToro widens SL beyond requested level (observed ~10% floor on BTC live account)
- `InstrumentId` (lowercase d) for LIVE close, `InstrumentID` (uppercase D) for DEMO close

### System state entering next session

- **DEMO equity:** ~$491K | **Open positions:** ~65 | **Regime:** `trending_up_strong`
- **DEMO strategies:** 50 PAPER + 66 BACKTESTED
- **LIVE account:** Agent Portfolio | Virtual: $10,000 | Real: $1,000 | Mirror: 10%
- **LIVE positions:** 0 (no live trades fired yet — `live_trading.enabled: false`)
- **Last commits:** `cb6bed1` (Sprints 8-10 + Settings Live tab)
- **errors.log:** clean (stale `promoted_to_demo` entries from 2026-05-09 are pre-rename, not new)
- **Live credentials:** `/home/ubuntu/alphacent/config/live_credentials.json` (encrypted)

### Session start checklist

```bash
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'tail -20 /home/ubuntu/alphacent/logs/errors.log'
ssh ... 'tail -30 /home/ubuntu/alphacent/logs/cycles/cycle_history.log'
ssh ... 'sudo -u postgres psql alphacent -t -A -c "SELECT status, COUNT(*) FROM strategies GROUP BY status ORDER BY status;"'
ssh ... 'sudo -u postgres psql alphacent -t -A -c "SELECT balance, equity, updated_at FROM account_info ORDER BY updated_at DESC LIMIT 1;"'
ssh ... 'sudo -u postgres psql alphacent -t -A -c "SELECT COUNT(*) FROM live_strategies WHERE retired_at IS NULL;"'
```

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
| Portfolio/balance | `GET /api/v1/trading/info/real/pnl` → `clientPortfolio.credit` |
| Order status | `GET /api/v1/trading/info/real/orders/{orderId}` |
| Trade history | `GET /api/v1/trading/info/trade/history?minDate=YYYY-MM-DD` |
| Identity | `GET /api/v1/me` → `{gcid: 48243427, realCid: 48239007, demoCid: 49422123}` |
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
  → LIVE client: real fill (only if live_trading.enabled=true AND live_strategies row exists)

Signal fires for MSFT:
  → DEMO client: paper fill only
```

**HARD GATE:** `live_trading.enabled: false` in `config/autonomous_trading.yaml` blocks ALL live fills regardless of graduation approvals. Flip to `true` only after Phase 2B is complete.

---

## MISSION — Phase 2B: Live Trading Completeness (7 sprints)

These sprints fix correctness bugs and build the operational visibility needed to actually run the live account safely. **Do not flip `live_trading.enabled: true` until Sprint 2B-3 (trade_journal migration) is complete.**

### Sprint 2B-1 — P0: Live RiskManager uses correct equity

**Problem:** `TradingScheduler._initialize_components` creates one `RiskManager` using DEMO credentials. When a live fill fires, `_order_executor` (live) calls `execute_signal` which internally calls `risk_manager.calculate_position_size(account_info)`. But `account_info` is fetched from the DEMO client (equity=$491K). Live position sizing should use live equity ($10K virtual), not DEMO equity.

**Fix:** In `trading_scheduler.py`, when routing a live fill, pass the live `AccountInfo` (fetched from `live_etoro_client.get_account_info()`) to the live `OrderExecutor`. The live `OrderExecutor` already exists (`self._live_order_executor`) — it just needs the right account context.

**Also:** The live `OrderExecutor` should enforce `min_order_size=200` and `max_order_size=1500` from `live_trading` yaml, not the DEMO `MINIMUM_ORDER_SIZE=2000`. Read these from `autonomous_trading.yaml` `live_trading` section at signal time.

**File:** `src/core/trading_scheduler.py` — live fill routing block (around the `_live_order_executor.execute_signal` call added in Sprint 5).

### Sprint 2B-2 — P0: Live positions/orders endpoint filtering

**Problem:** `GET /account/positions?mode=LIVE` and `GET /orders?mode=LIVE` currently return DEMO data because the routers don't filter by `account_type`. The `account_type` column exists on both tables (added Sprint 1) but the query doesn't use it.

**Fix:** In `src/api/routers/account.py` and `src/api/routers/orders.py`, add `account_type` filter:
- `mode=DEMO` → `filter(PositionORM.account_type == 'demo')`
- `mode=LIVE` → `filter(PositionORM.account_type == 'live')`

**Also:** `GET /account/info?mode=LIVE` should return the live client's balance/equity. Currently `account_info` table has one row (DEMO). The live account sync (Sprint 4) writes a separate `account_id='live_account_001'` row — the endpoint needs to query by `account_id` based on mode.

**Files:** `src/api/routers/account.py`, `src/api/routers/orders.py`

### Sprint 2B-3 — P0: trade_journal account_type migration

**Problem:** `trade_journal` has no `account_type` column. When live positions close, their P&L entries will mix into paper analytics — conviction calibration, performance metrics, Sharpe calculations, everything. This contaminates the paper validation layer.

**DB migration (run before any live trades fire):**
```sql
ALTER TABLE trade_journal ADD COLUMN account_type VARCHAR(10) NOT NULL DEFAULT 'demo';
CREATE INDEX idx_trade_journal_account_type ON trade_journal(account_type);
```

**ORM:** Add `account_type = Column(String(10), nullable=False, default='demo')` to `TradeJournalORM` (or equivalent).

**Write paths to update:**
- `order_monitor.py` — when writing trade_journal on fill, tag with `account_type` from the order's `account_type` column
- `portfolio_manager.py` — retirement close path
- `monitoring_service.py` — pending closure path

**Read paths to update:**
- `graduation_gate.get_paper_stats_for_strategy()` — must filter `account_type='demo'` (paper stats only)
- `trade_journal.get_performance_feedback()` — must filter `account_type='demo'` (don't penalise proposer based on live trades)
- `conviction_scorer` calibration queries — `account_type='demo'` only

**Files:** DB migration, `src/models/orm.py`, `src/core/order_monitor.py`, `src/strategy/portfolio_manager.py`, `src/core/monitoring_service.py`, `src/strategy/graduation_gate.py`, `src/strategy/trade_journal.py`

### Sprint 2B-4 — P1: Strategies page — Live tab

**Problem:** The Strategies page has tabs for Active (PAPER), Backtested, Retired, etc. There is no tab showing which (template, symbol) pairs are live-authorized. The `live_strategies` table exists but is only visible in the Graduation Gate tab inside Autonomous.

**Fix:** Add a `Live (N)` tab to `StrategiesNew.tsx` — the 3rd tab after Active and Backtested.

**Tab content — table with columns:**
- Template | Symbol | Activated | Virtual Size | Real Size ($) | SL% | TP% | Conviction Min
- Live Trades | Live P&L | Live Sharpe | Paper Sharpe | Divergence %
- Status badge: `● Active` / `○ Retired`
- Actions: `Retire` button (sets `retired_at` via new `POST /strategies/live/{id}/retire` endpoint)

**Data source:** `GET /strategies/live` (already exists, returns `live_strategies` rows with paper stats).

**New backend endpoint:** `POST /strategies/live/{id}/retire` — sets `retired_at = NOW()` on the `live_strategies` row. Stops live fills for that pair immediately.

**Files:** `frontend/src/pages/StrategiesNew.tsx`, `src/api/routers/strategies.py`

### Sprint 2B-5 — P1: Dedicated Live Trading page (`/live`)

A top-level page in the nav for operational visibility of the live account. This is where real money is managed.

**Route:** `/live` | **Nav label:** `● Live` (green dot when enabled, gray when disabled)

**Layout:** Same 2-panel pattern as other pages (65/35 split).

**Main panel — 5 tabs:**

**Tab 1: Overview**
- Live account summary card: virtual balance, real investment, mirror ratio, today's P&L (virtual + real)
- Master kill switch: toggle `live_trading.enabled` without going to Settings (calls `PUT /config/live-trading`)
- Live vs DEMO equity curve on same chart (two lines, different colors) — shows divergence visually
- Active live authorizations count, live positions count, deployed capital %

**Tab 2: Positions**
- Live positions table filtered to `account_type='live'`
- Columns: Symbol | Side | Virtual Size | Real Size | Entry | Current | P&L (virtual) | P&L (real) | SL | TP | Strategy | TSL Status
- TSL Status: shows DB stop vs eToro backstop SL gap
- Close button: fires `close_position` against live client

**Tab 3: Orders**
- Live order history filtered to `account_type='live'`
- Columns: Symbol | Side | Virtual Size | Real Size | Status | Fill Price | Slippage | Fill Time | Strategy

**Tab 4: Graduation Gate** (moved from Autonomous page)
- Qualification queue with CIO Decision Card (same as current implementation)
- Active live authorizations table (same as Strategies → Live tab but with more detail)
- Rejection history with cooldown countdown

**Tab 5: Live vs Paper Divergence**
- Per-strategy: paper equity curve (blue) vs live equity curve (green) on same chart
- Divergence metric: `live_sharpe / paper_sharpe × 100%`
- Flag red when divergence < 50% (live underperforming paper badly)
- Table: Template | Symbol | Paper Sharpe | Live Sharpe | Divergence | Paper Trades | Live Trades | Recommendation

**Side panel:**
- Live account health: balance, equity, unrealized P&L, positions count
- Recent live fills (last 10 orders)
- Divergence alerts (strategies where live < 50% of paper)

**New backend endpoints needed:**
- `GET /live/summary` — live account balance, P&L, positions count, deployed capital
- `GET /live/positions` — alias for `GET /account/positions?mode=LIVE` (after Sprint 2B-2)
- `GET /live/orders` — alias for `GET /orders?mode=LIVE` (after Sprint 2B-2)
- `GET /live/divergence` — per live_strategies row: paper Sharpe vs live Sharpe from trade_journal
- `POST /live/positions/{id}/close` — close a live position
- `POST /strategies/live/{id}/retire` — retire a live authorization

**Files:** New `frontend/src/pages/LiveNew.tsx`, `src/api/routers/live.py` (new router), `frontend/src/App.tsx` (add route), nav component (add link)

### Sprint 2B-6 — P1: Existing pages DEMO/LIVE awareness

**Problem:** Portfolio, Orders, Analytics, Performance pages all show DEMO data only. When live positions exist, they're invisible on these pages.

**Pattern:** Each page already has `tradingMode` from `useTradingMode()`. The fix is to pass `account_type` to the backend queries and filter accordingly (Sprint 2B-2 makes this work).

**Changes per page:**

**PortfolioNew** — positions query already passes `mode=tradingMode`. After Sprint 2B-2, `mode=LIVE` will return live positions. No frontend change needed beyond ensuring the mode toggle is visible. Add `[DEMO] [LIVE]` toggle button if not already present.

**OrdersNew** — same as Portfolio. Mode toggle already exists. After Sprint 2B-2, `mode=LIVE` returns live orders.

**AnalyticsNew** — equity curve, daily P&L chart, drawdown chart all query `equity_snapshots`. After Sprint 2B-3, these are per `account_type`. Add mode toggle so LIVE shows the live equity curve (will be flat until first live trade, then grows).

**PerformanceNew** — Sharpe, win rate, return metrics query `trade_journal`. After Sprint 2B-3, filter by `account_type`. Add mode toggle.

**OverviewNew / Dashboard** — the main equity number is DEMO. When live is active, show both: `DEMO $491K | LIVE $10K virtual / $1K real`. This is a display-only change — read from `account_info` table which has separate rows per account after Sprint 4.

**Note:** Most of these pages already have `mode` in their API calls. The backend filtering (Sprint 2B-2 and 2B-3) is the real work. Frontend changes are minimal — mostly ensuring the mode toggle is visible and wired.

**Files:** `src/api/routers/account.py`, `src/api/routers/orders.py`, `src/api/routers/performance.py`, `src/api/routers/analytics.py` — add `account_type` filter to queries. Frontend pages: add mode toggle where missing.

### Sprint 2B-7 — P2: Graduation Gate improvements

**Remove from Autonomous page:** The graduation tab in `AutonomousNew.tsx` should be removed now that it has a proper home in the Live page (Sprint 2B-5). The Autonomous page is for strategy research, not live operations.

**CIO Decision Card enhancements:**
- Paper equity curve chart (actual trade-by-trade equity, not just summary stats) — shows consistency over time, not just aggregate numbers
- Qualification ratio trend: is the ratio improving or degrading over the last 30 days?
- Portfolio context: if approved, what % of live portfolio heat does this add?

**Re-graduation flow:**
- When a live strategy is retired, it should be removable from `live_strategies` (set `retired_at`) and re-enter the graduation queue after a 7-day cooldown
- `POST /strategies/live/{id}/retire` endpoint (also needed for Sprint 2B-4)

**Rejection history tab:** Show all rejected pairs with cooldown countdown (`rejected_at + 14 days`). Currently rejections are recorded but not visible anywhere.

---

## Sprint 2B Sequencing

| Sprint | What | Priority | Blocking? |
|---|---|---|---|
| **2B-1** | Live RiskManager uses live equity | 🔴 P0 | Blocks correct live sizing |
| **2B-2** | Live positions/orders endpoint filtering | 🔴 P0 | Blocks 2B-5, 2B-6 |
| **2B-3** | trade_journal account_type migration | 🔴 P0 | **Do before first live trade** |
| **2B-4** | Strategies page — Live tab | 🟡 P1 | After 2B-2 |
| **2B-5** | Dedicated Live Trading page | 🟡 P1 | After 2B-2, 2B-3 |
| **2B-6** | Existing pages DEMO/LIVE awareness | 🟡 P1 | After 2B-2, 2B-3 |
| **2B-7** | Graduation Gate improvements | 🟢 P2 | After 2B-5 |

**Start next session with 2B-1, 2B-2, 2B-3 in order. These are correctness bugs that exist right now even before the first live trade fires.**

---

## Current System State (May 10, 2026)

- **DEMO Equity:** ~$491K | **Open positions:** ~65 | **Regime:** `trending_up_strong`
- **DEMO Strategies:** 50 PAPER + 66 BACKTESTED
- **LIVE Account:** Agent Portfolio | Virtual: $10,000 | Real: $1,000 | Mirror: 10%
- **LIVE positions:** 0 | **live_trading.enabled:** false (HARD GATE — do not flip until 2B-3 done)
- **Service:** healthy | **errors.log:** clean

---

## Key Parameters

### Risk per asset class
Stock/ETF: SL 6%, TP 15% | Forex: SL 2%, TP 5% | Crypto: SL 8%, TP 20% | Index: SL 5%, TP 12% | Commodity: SL 4%, TP 10%

### Position sizing (DEMO)
- `BASE_RISK_PCT`: 0.6% | `MINIMUM_ORDER_SIZE`: $2,000 | Symbol cap: 5% | Sector soft cap: 30% | Portfolio heat: 30%
- Drawdown sizing: 50% reduction >5% DD, 75% >10% DD (30d rolling peak)
- Vol scaling: 0.10x–1.50x (target vol 16%)
- Per-pair loser penalty: (template, symbol) with ≥3 net-losing trades halves size

### Position sizing (LIVE)
- `BASE_RISK_PCT`: 0.6% of virtual equity ($10K) | `MIN_ORDER`: $200 virtual ($20 real) | `MAX_ORDER`: $1,500 virtual ($150 real)
- Symbol cap: 20% of virtual balance ($2,000 virtual / $200 real)
- Portfolio heat cap: 90% of virtual balance
- Conviction threshold: 74 (higher than DEMO 70)

### Activation thresholds
- `min_sharpe`: 1.0 | `min_sharpe_crypto`: 0.3 | `min_sharpe_commodity`: 0.5
- `min_trades_dsl`: 8 (1d/4h) | 15 (1h) | `min_trades_alpha_edge`: 8
- Conviction threshold: 70 (DEMO) | 74 (LIVE fills)

### ATR stop floor (order_executor, hardcoded)
- 1.5× ATR for daily strategies | 2.0× ATR for 4H strategies
- Max SL clamps: stocks/ETFs 9%, crypto 15%, forex 4%
- **LIVE note:** eToro may widen SL beyond requested level (~10% floor observed on BTC)

### Trailing Stop System
- Per-class ATR multiplier: stock/etf/commodity 2.0x, crypto/index 1.5x, forex 1.0x
- Timeframe-aware ATR (4H strategies use 4H bars)
- Breach enforcement independent of historical-bar freshness
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

-- Live strategies (graduation approvals)
SELECT ls.template_name, ls.symbol, ls.activated_at, ls.live_trades, ls.live_pnl,
       ga.qualification_ratio, ga.paper_sharpe, ga.wf_sharpe
FROM live_strategies ls
JOIN graduation_approvals ga ON ga.id = ls.graduation_id
WHERE ls.retired_at IS NULL
ORDER BY ls.activated_at DESC;

-- Graduation queue candidates (quick check)
SELECT s.name, tj.symbol, COUNT(*) AS trades,
       ROUND((AVG(tj.pnl) / NULLIF(STDDEV(tj.pnl), 0) * SQRT(252))::numeric, 2) AS sharpe,
       ROUND(100.0 * SUM(CASE WHEN tj.pnl > 0 THEN 1 ELSE 0 END) / COUNT(*)::numeric, 1) AS win_pct
FROM trade_journal tj
JOIN strategies s ON s.id = tj.strategy_id
WHERE s.status = 'PAPER' AND tj.pnl IS NOT NULL
GROUP BY s.id, s.name, tj.symbol
HAVING COUNT(*) >= 20
ORDER BY sharpe DESC;

-- Decision-log funnel for the last cycle
SELECT stage, decision, COUNT(*) FROM signal_decisions
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY stage, decision ORDER BY COUNT(*) DESC;

-- Why didn't we trade <SYMBOL>? (7-day lookback)
SELECT timestamp, stage, decision, template_name, reason
FROM signal_decisions
WHERE symbol='AAPL' AND timestamp > NOW() - INTERVAL '7 days'
ORDER BY timestamp DESC LIMIT 30;

-- Conviction score vs P&L (validation loop)
SELECT
  FLOOR(conviction_score / 5) * 5 AS bucket,
  COUNT(*) AS trades,
  ROUND(AVG(pnl)::numeric, 2) AS avg_pnl,
  ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_pct
FROM trade_journal
WHERE conviction_score IS NOT NULL AND pnl IS NOT NULL
GROUP BY bucket ORDER BY bucket;
```

---

## Open Items

### 🔴 P0 — Phase 2B (start next session)
See MISSION block above. 2B-1, 2B-2, 2B-3 are correctness bugs that exist right now.
**Do not flip `live_trading.enabled: true` until 2B-3 (trade_journal migration) is complete.**

### P1 — Raise conviction threshold to 74
Calibration monitor shows 74–76 is first clearly positive-EV bucket (+$21.72 avg, 49 trades). 70–74 range is negative EV. Change in Settings → Autonomous → Conviction Score Threshold. Monitor 1–2 weeks to confirm.

### P2 — Conviction scorer component reweighting (needs 3-4 more weeks of data)
`signal_quality` collapses to ~4-5 pts variance for 85% of DSL signals. `regime_fit` saturated at 20/20 in trending_up_strong. Wait until ~500+ scored trades per bucket, then regression-fit weights on live P&L.

### P3 — Cross-cycle signal dedup (~1h)
TXN ENTER_LONG fires every 10 minutes for hours. 30-min TTL map on `(strategy_id, symbol, direction)` in `trading_scheduler`.

### P4 — WF test-dominant regime-luck gate for LONG (~1h)
Add `(test_sharpe - train_sharpe) ≤ 1.5` consistency check to test-dominant bypass path. SHORT already tightened.

### P5 — GET /strategies 422 (pre-existing)
Some component calls `/strategies` without `mode` param. Logs 422. Not crashing.

### P6 — Settings page auto-revert on restart (low priority)
Settings page re-fetches config on mount. If open during restart, may re-send stale values.

### Deferred
- **Pairs Trading template rebuild** — needs cross-asset spread primitives (z-score of A/B ratio) in DSL first
- **NATGAS 1h stale** — add to explicit-blocked set in fmp_ohlc.py
- **trade_id convention unification** — `log_entry` uses `position.id`; `log_exit` uses order UUID
- **Monday Asia Open template** — needs DSL `HOUR()` primitive
- **ONCHAIN DSL primitive** — BTC dominance, stablecoin supply
- **Overview chart panel rewrite** — 3 chart components with misaligned axes
- **CI/CD hardening** — GitHub Actions pipeline, automated deploy on push to main
- **SignalDecisionLogORM table drop** — scheduled 2026-06-03
- **Commodity 1h coverage** — blocked on FMP Starter upgrade
- **Forex 1d legacy FMP path cleanup** — ~15 min

---

## DB Migrations Applied to Prod (cumulative)

```sql
-- 2026-05-10: Phase 2A migrations
ALTER TABLE positions ADD COLUMN account_type VARCHAR(10) NOT NULL DEFAULT 'demo';
ALTER TABLE orders ADD COLUMN account_type VARCHAR(10) NOT NULL DEFAULT 'demo';
ALTER TABLE equity_snapshots ADD COLUMN account_type VARCHAR(10) NOT NULL DEFAULT 'demo';
ALTER TABLE equity_snapshots DROP CONSTRAINT uq_equity_snapshot_date_type;
CREATE UNIQUE INDEX uq_equity_snapshot_date_type_account ON equity_snapshots(date, snapshot_type, account_type);
CREATE TABLE graduation_approvals (...);  -- see Sprint 1 SQL block
CREATE TABLE live_strategies (...);       -- see Sprint 1 SQL block

-- 2026-05-10: StrategyStatus rename
UPDATE strategies SET status='PAPER' WHERE status='DEMO';
ALTER TABLE autonomous_cycle_runs RENAME COLUMN promoted_to_demo TO promoted_to_paper;

-- 2026-05-04: Signal decisions + proposals
ALTER TABLE orders ADD COLUMN order_metadata JSON;
ALTER TABLE strategy_proposals ADD COLUMN symbols JSON, ADD COLUMN template_name VARCHAR;
CREATE TABLE signal_decisions (...);
ALTER TABLE autonomous_cycle_runs ADD COLUMN proposals_pre_wf INTEGER;

-- Earlier: positions/orders enrichment
ALTER TABLE positions ADD COLUMN invested_amount FLOAT;
ALTER TABLE orders ADD COLUMN order_action VARCHAR, slippage FLOAT, fill_time_seconds FLOAT;
```

**Next migrations (Sprint 2B-3):**
```sql
ALTER TABLE trade_journal ADD COLUMN account_type VARCHAR(10) NOT NULL DEFAULT 'demo';
CREATE INDEX idx_trade_journal_account_type ON trade_journal(account_type);
```
