# AlphaCent — Session Continuation

> Permanent rules are in `.kiro/steering/trading-system-context.md`. This file holds current system state, recent fixes, and open items.

---

## ⚡ NEXT SESSION KICKOFF — Phase 2: Live Trading Architecture

**Read this block first. It contains everything needed to continue implementation without re-researching.**

### What was completed last session (2026-05-10)

1. **StrategyStatus.DEMO → PAPER rename** (commit `eea80bc`) — 17 Python files + DB migration
2. **Frontend PAPER fix** (commit `90360cd`) — 8 frontend files, all `status === 'DEMO'` → `'PAPER'`
3. **eToro LIVE API tested and confirmed working** — credentials stored, architecture understood
4. **Full Phase 2 design completed** — see MISSION block below

### System state entering next session

- **DEMO equity:** ~$491K, ~65 open positions, `trending_up_strong`
- **DEMO strategies:** 50 PAPER + 66 BACKTESTED
- **LIVE account:** Agent Portfolio, `credit: $10,000 virtual`, `real_investment: $1,000`, `mirror_ratio: 0.10`
- **LIVE positions:** 0 (test BTC position opened and closed during session)
- **Last commits:** `d0bcd53` (session docs) → `90360cd` (frontend PAPER) → `eea80bc` (StrategyStatus rename)
- **errors.log:** clean as of 2026-05-10 ~09:30 UTC
- **Live credentials:** stored encrypted at `config/live_credentials.json` on EC2

### Session start checklist

```bash
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'tail -20 /home/ubuntu/alphacent/logs/errors.log'
ssh ... 'tail -50 /home/ubuntu/alphacent/logs/cycles/cycle_history.log'
ssh ... 'sudo -u postgres psql alphacent -t -A -c "SELECT status, COUNT(*) FROM strategies GROUP BY status ORDER BY status;"'
ssh ... 'sudo -u postgres psql alphacent -t -A -c "SELECT balance, equity, updated_at FROM account_info ORDER BY updated_at DESC LIMIT 1;"'
```

---

### eToro LIVE API — confirmed facts (do not re-research)

| | Value |
|---|---|
| Base URL | `https://public-api.etoro.com` |
| Auth headers | `x-api-key` + `x-user-key` + `x-request-id` (UUID) |
| Agent virtual balance | `$10,000` (what `credit` field reports) |
| Real investment | `$1,000` (your money at risk) |
| Mirror ratio | `10%` — every agent $1,000 order = $100 real exposure |
| Open order | `POST /api/v1/trading/execution/market-open-orders/by-amount` |
| Close position | `POST /api/v1/trading/execution/market-close-orders/positions/{positionId}` body: `{"InstrumentId": id}` |
| Portfolio/balance | `GET /api/v1/trading/info/real/pnl` → `clientPortfolio.credit` |
| Order status | `GET /api/v1/trading/info/real/orders/{orderId}` |
| Trade history | `GET /api/v1/trading/info/trade/history?minDate=YYYY-MM-DD` |
| Identity | `GET /api/v1/me` → `{gcid: 48243427, realCid: 48239007, demoCid: 49422123}` |
| DEMO open order | `POST /api/v1/trading/execution/demo/market-open-orders/by-amount` |
| DEMO close | `POST /api/v1/trading/execution/demo/market-close-orders/positions/{positionId}` |
| DEMO order status | `GET /api/v1/trading/info/demo/orders/{orderId}` |
| DEMO portfolio | `GET /api/v1/trading/info/demo/pnl` |

**Mirror ratio explained (documented in eToro API docs):** The Agent Portfolio receives a fixed $10,000 virtual balance. Your $1,000 investment from your main account copy-trades it at 10% scale. When the agent places a $1,000 virtual order, your main account mirrors a $100 real position. The API key is scoped to the agent sub-account — it sees and trades the full $10,000 virtual balance. The eToro app shows your main account which sees the 10% mirror.

**Position sizing for 10 trades with $1,000 real:**
- Each agent order: `$1,000 virtual` → `$100 real`
- 10 trades × $1,000 = $10,000 virtual = $1,000 real fully deployed
- `min_order_size`: $200 virtual (= $20 real) | `max_order_size`: $1,500 virtual (= $150 real)
- `symbol_cap`: $2,000 virtual (= $200 real)

**Live credentials location:** `/home/ubuntu/alphacent/config/live_credentials.json` — encrypted with same Fernet key as DEMO. Load via `config.load_credentials(TradingMode.LIVE)`.

---

### Architecture decision: PAPER + LIVE run simultaneously

A strategy promoted to LIVE **continues paper trading on DEMO**. Status `LIVE` means "running on DEMO (paper) AND LIVE (real) simultaneously". DEMO is the permanent validation layer. LIVE is additive.

Graduation is per **(template, symbol) pair**, not per strategy. No watchlist on LIVE — only individually approved pairs get live fills.

```
PAPER strategy "4H EMA Ribbon Trend Long" — watchlist: [AAPL, MSFT, NVDA]
  AAPL: 24 paper trades, 87% WF ratio → APPROVED via Graduation Gate → LIVE
  MSFT: 8 paper trades, 29% ratio → not qualified

Signal fires for AAPL:
  → DEMO client: paper fill (always, for all symbols)
  → LIVE client: real fill with graduation overrides (AAPL only)

Signal fires for MSFT:
  → DEMO client: paper fill only
```

---

### MISSION — Phase 2 implementation (10 sprints)

**HARD GATE: No live trade fires until Sprint 8 (Graduation Gate UI) is complete and at least one strategy has been manually approved.**

#### Sprint 1 — DB migrations (START HERE, no restart needed)

Run on EC2 before any code changes:

```sql
-- 1. account_type on positions
ALTER TABLE positions ADD COLUMN account_type VARCHAR(10) NOT NULL DEFAULT 'demo';

-- 2. account_type on orders
ALTER TABLE orders ADD COLUMN account_type VARCHAR(10) NOT NULL DEFAULT 'demo';

-- 3. account_type on equity_snapshots (break old unique constraint, add account_type)
ALTER TABLE equity_snapshots ADD COLUMN account_type VARCHAR(10) NOT NULL DEFAULT 'demo';
DROP INDEX IF EXISTS uq_equity_snapshot_date_type;
CREATE UNIQUE INDEX uq_equity_snapshot_date_type_account
  ON equity_snapshots(date, snapshot_type, account_type);

-- 4. graduation_approvals table
CREATE TABLE graduation_approvals (
    id                      SERIAL PRIMARY KEY,
    strategy_id             VARCHAR(36) NOT NULL,
    symbol                  VARCHAR(20) NOT NULL,
    template_name           VARCHAR(200) NOT NULL,
    approved_at             TIMESTAMP,
    rejected_at             TIMESTAMP,
    notes                   TEXT,
    position_size_override  FLOAT,
    sl_pct_override         FLOAT,
    tp_pct_override         FLOAT,
    conviction_min_override INTEGER,
    paper_trades            INTEGER,
    paper_sharpe            FLOAT,
    paper_win_rate          FLOAT,
    paper_total_pnl         FLOAT,
    wf_sharpe               FLOAT,
    qualification_ratio     FLOAT,
    created_at              TIMESTAMP DEFAULT NOW()
);

-- 5. live_strategies table
CREATE TABLE live_strategies (
    id              SERIAL PRIMARY KEY,
    graduation_id   INTEGER REFERENCES graduation_approvals(id),
    strategy_id     VARCHAR(36) NOT NULL,
    template_name   VARCHAR(200) NOT NULL,
    symbol          VARCHAR(20) NOT NULL,
    activated_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    retired_at      TIMESTAMP,
    position_size   FLOAT NOT NULL,
    sl_pct          FLOAT NOT NULL,
    tp_pct          FLOAT NOT NULL,
    conviction_min  INTEGER NOT NULL DEFAULT 74,
    live_trades     INTEGER NOT NULL DEFAULT 0,
    live_pnl        FLOAT NOT NULL DEFAULT 0.0,
    live_sharpe     FLOAT,
    UNIQUE(strategy_id, symbol)
);
```

Then add ORM classes to `src/models/orm.py`:
- `account_type` column to `PositionORM`, `OrderORM`, `EquitySnapshotORM`
- Fix `UniqueConstraint` on `EquitySnapshotORM` to include `account_type`
- New `GraduationApprovalORM` and `LiveStrategyORM` classes

#### Sprint 2 — EToroAPIClient: remove TradingMode, add account_type

**File:** `src/api/etoro_client.py`

Replace `mode: TradingMode` → `account_type: str` (`"demo"` or `"live"`). Update all 12 internal `self.mode == TradingMode.DEMO` checks. Key endpoint differences:

```python
# place_order:
"demo": "/api/v1/trading/execution/demo/market-open-orders/by-amount"
"live": "/api/v1/trading/execution/market-open-orders/by-amount"

# cancel_order:
"demo": f"/api/v1/trading/execution/demo/market-cancel-orders/{order_id}"
"live": f"/api/v1/trading/execution/market-cancel-orders/{order_id}"

# close_position:
"demo": f"/api/v1/trading/execution/demo/market-close-orders/positions/{position_id}"
"live": f"/api/v1/trading/execution/market-close-orders/positions/{position_id}"
# LIVE body uses "InstrumentId" (lowercase 'd'), DEMO uses "InstrumentID"

# get_order_status:
"demo": f"/api/v1/trading/info/demo/orders/{order_id}"
"live": f"/api/v1/trading/info/real/orders/{order_id}"

# get_account_info / get_positions:
"demo": "/api/v1/trading/info/demo/pnl"
"live": "/api/v1/trading/info/real/pnl"
```

New method for LIVE only: `get_trade_history(min_date: str)` → `GET /api/v1/trading/info/trade/history?minDate={min_date}`

#### Sprint 3 — Dual-client startup

**File:** `src/api/app.py`

```python
demo_client = EToroAPIClient(demo_creds["public_key"], demo_creds["user_key"], account_type="demo")
live_client = None
try:
    live_creds = config.load_credentials(TradingMode.LIVE)
    live_client = EToroAPIClient(live_creds["public_key"], live_creds["user_key"], account_type="live")
    logger.info("Live eToro client initialized (Agent Portfolio, $10K virtual)")
except ConfigurationError:
    logger.info("No live credentials — DEMO-only mode")

monitoring_service = MonitoringService(
    demo_etoro_client=demo_client,
    live_etoro_client=live_client,  # None = DEMO-only
    ...
)
```

Add global getters: `get_demo_etoro_client()`, `get_live_etoro_client()`.

**File:** `src/core/config.py` — `load_credentials("live")` already reads `live_credentials.json`. Add `virtual_balance`, `real_investment`, `mirror_ratio` to returned dict.

#### Sprint 4 — MonitoringService: dual-account sync

**File:** `src/core/monitoring_service.py`

Constructor: `demo_etoro_client` + `live_etoro_client=None`. Position sync runs for both clients, tags rows with `account_type`. Equity snapshots write separate rows per account_type. Account info writes separate rows for DEMO and LIVE.

#### Sprint 5 — TradingScheduler + OrderExecutor: strategy routing

**File:** `src/core/trading_scheduler.py`

```python
# For each signal:
live_approval = get_live_approval(strategy.template_name, signal.symbol)  # from live_strategies table

# Always paper fill on DEMO
await submit_order(demo_client, signal, strategy.default_params, account_type='demo')

# Real fill on LIVE only if approved
if live_approval and live_approval.retired_at is None:
    await submit_order(live_client, signal, live_approval.overrides, account_type='live')
```

#### Sprint 6 — Live risk parameters

**File:** `config/autonomous_trading.yaml` — add section:
```yaml
live_trading:
  enabled: true
  virtual_balance: 10000
  real_investment: 1000
  mirror_ratio: 0.10
  base_risk_pct: 0.006
  min_order_size: 200
  max_order_size: 1500
  symbol_cap_pct: 0.20
  portfolio_heat_cap: 0.90
  conviction_threshold: 74
```

Risk manager already takes `AccountInfo` as parameter — pass LIVE account info (equity=$10,000 virtual) when sizing live orders.

#### Sprint 7 — Graduation Gate backend

**New file:** `src/strategy/graduation_gate.py`

Qualification criteria:
- `paper_trades >= 20`
- `paper_sharpe >= 0.6 × wf_sharpe`
- `paper_win_rate >= 0.45`
- `paper_pnl > 0`
- Not already in `live_strategies` (active)
- Not rejected in last 14 days

**New API endpoints** in `src/api/routers/strategies.py`:
```
GET  /strategies/graduation-queue          # qualified (template, symbol) pairs
POST /strategies/{id}/graduate             # approve with overrides
     body: {symbol, position_size, sl_pct, tp_pct, conviction_min, notes}
POST /strategies/{id}/reject-graduation    # reject with 14-day cooldown
     body: {symbol, notes}
GET  /strategies/live                      # active live_strategies rows
```

#### Sprint 8 — Graduation Gate UI (HARD GATE — must complete before any live trade)

**Location:** New "🎓 Graduation Gate" tab in `AutonomousNew.tsx`

**View 1 — Queue table** (qualified candidates):

Columns: Template | Symbol | Paper Trades | Paper Sharpe | WF Sharpe | Ratio | Paper P&L | Win% | Qualified Since

Clicking a row opens the **CIO Decision Card** (slide-over panel) with 7 sections:
1. Strategy identity (template, symbol, direction, interval, proposed date, conviction score, regime)
2. Walk-forward evidence (WF Sharpe, train Sharpe, win rate, trades, avg return, max DD, MC bootstrap p5)
3. Paper trading performance (equity curve chart + trade-by-trade table)
4. Signal quality (avg conviction, avg persistence, avg R:R, gate blocks)
5. Risk profile (SL%, TP%, avg MAE, avg MFE, profit factor, max consecutive losses)
6. **Live sizing controls (editable):** virtual order size (slider, shows real exposure × mirror_ratio), SL% (shows price level), TP% (shows price level), conviction minimum, notes
7. Portfolio context (other live strategies on same symbol, portfolio heat if approved)

Action buttons: `[ ✗ REJECT — keep PAPER ]` `[ ✓ APPROVE → LIVE ]`

**View 2 — Live strategies table** (already approved):

Columns: Template | Symbol | Activated | Live Trades | Live P&L | Live Sharpe | Paper Sharpe | Divergence | Status

#### Sprint 9 — Frontend: DEMO/LIVE separation

**Pattern:** Every page that shows account data gets a `DEMO | LIVE` account toggle. When LIVE selected, all API calls pass `mode=LIVE`.

**New component:** `AccountToggle.tsx` — shows `[DEMO $491K] [LIVE $10K virtual / $1K real]`. Only shows LIVE option when live client is configured.

**Pages that need the toggle:** PortfolioNew, OrdersNew, AnalyticsNew, StrategiesNew, MetricsBar, OverviewNew.

**Key display rule for live data:** Always show both virtual and real:
```
Position: AAPL LONG  |  Virtual: $1,000  |  Real: $100  (10% mirror)
```

**New "Live vs Paper" tab in Analytics:** For each live strategy, paper equity curve (blue) vs live equity curve (green). Divergence metric: `(live_sharpe / paper_sharpe) × 100%`. Flag if < 50%.

#### Sprint 10 — MetricsBar live pill

Add live account summary alongside DEMO: `[LIVE: $10K virtual / $1K real | $0 today]`. Only shows when live client is configured.

#### Sprint sequencing

| Sprint | What | Blocking? |
|---|---|---|
| 1 | DB migrations | Blocks everything |
| 2 | EToroAPIClient refactor | Blocks 3,4,5 |
| 3 | Dual-client startup | Blocks 4,5 |
| 4 | MonitoringService dual-sync | After 3 |
| 5 | TradingScheduler routing | After 3 |
| 6 | Live risk params in yaml | Independent |
| 7 | Graduation gate backend | Blocks 8 |
| **8** | **Graduation Gate UI** | **HARD GATE — blocks all live trades** |
| 9 | Frontend DEMO/LIVE separation | After 1 |
| 10 | MetricsBar live pill | After 9 |

---

## Current System State (May 10, 2026)

- **DEMO Equity:** ~$491K | **Open positions:** ~65 | **Regime:** `trending_up_strong`
- **DEMO Strategies:** 50 PAPER + 66 BACKTESTED
- **LIVE Account:** Agent Portfolio | Virtual: $10,000 | Real: $1,000 | Mirror: 10%
- **Conviction threshold:** 70 (raise to 74 when data confirms — see P1 below)
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

### Activation thresholds
- `min_sharpe`: 1.0 | `min_sharpe_crypto`: 0.3 | `min_sharpe_commodity`: 0.5
- `min_trades_dsl`: 8 (1d/4h) | 15 (1h) | `min_trades_alpha_edge`: 8
- Conviction threshold: 70 (DSL/AE split, persistence-based signal quality)

### ATR stop floor (order_executor, hardcoded)
- 1.5× ATR for daily strategies | 2.0× ATR for 4H strategies
- Max SL clamps: stocks/ETFs 9%, crypto 15%, forex 4%

### Trailing Stop System
- Per-class ATR multiplier: stock/etf/commodity 2.0x, crypto/index 1.5x, forex 1.0x
- Timeframe-aware ATR (4H strategies use 4H bars)
- Breach enforcement independent of historical-bar freshness

### Signal-time gates
- **C1 VIX**: blocks LONG when VIX>25 AND VIX_5d>+15% (crypto exempt)
- **C2 Momentum Crash**: regime_fit −10 for LONG trend/momentum/breakout when SPY_5d<−3% AND VIX_1d>+10%
- **C3 Trend Consistency**: blocks SHORT above rising 50d SMA or oversold-bounce; blocks LONG below falling 50d SMA

### WF windows (yaml-managed)
- `non_crypto_1d`: 730/365 | `non_crypto_1h/4h`: 365/365
- `crypto_*`: 365/365 | `crypto_1d_longhorizon`: 730/730

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

-- Decision-log funnel for the last cycle
SELECT stage, decision, COUNT(*) FROM signal_decisions
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY stage, decision ORDER BY COUNT(*) DESC;

-- Why didn't we trade <SYMBOL>? (7-day lookback)
SELECT timestamp, stage, decision, template_name, reason
FROM signal_decisions
WHERE symbol='AAPL' AND timestamp > NOW() - INTERVAL '7 days'
ORDER BY timestamp DESC LIMIT 30;

-- Live account balance
SELECT credit, unrealized_pnl FROM (
  SELECT 10000 AS credit, 0 AS unrealized_pnl  -- placeholder until live sync implemented
) t;

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

### 🔴 P0 — Phase 2 Live Trading (10 sprints, see MISSION block above)
Start with Sprint 1 (DB migrations). Full plan at the top of this file.

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

**Next migrations (Sprint 1 of Phase 2):** See SQL block in MISSION section above.
