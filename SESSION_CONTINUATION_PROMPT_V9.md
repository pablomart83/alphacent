# AlphaCent Trading System — Session Continuation Prompt V9

Read `#File:.kiro/steering/trading-system-context.md` for full system context, then read this prompt carefully before proceeding.

## What Was Done This Session (April 10, 2026)

Continuation of V8 session. All V8 completed items remain in place. This session was a major infrastructure and architecture upgrade focused on four areas: (1) SQLite → PostgreSQL migration, (2) analytics dashboard performance fixes, (3) backtest avg_loss bug fix, and (4) fundamental shift from strategy-level retirement to position-level risk management.

---

### 1. SQLite → PostgreSQL Migration

**Why:** SQLite's single-writer lock was the #1 infrastructure bottleneck. Trading cycles (4 threads), position sync (125 positions), API endpoints, and trade journal all competed for one writer. PostgreSQL supports true concurrent reads + writes.

**What was done:**

**Database Engine (src/models/database.py):**
- `Database` class now checks `DATABASE_URL` env var — defaults to `postgresql://localhost/alphacent`
- PostgreSQL: 20-connection pool, no PRAGMAs, psycopg2 numpy adapters registered globally
- SQLite: falls back if `DATABASE_URL=sqlite:///alphacent.db` — all SQLite PRAGMAs preserved
- `pool_pre_ping=False` for PostgreSQL (saves ~1ms per query)
- Statement timeout 120s, idle-in-transaction timeout 300s

**ORM Types (src/models/orm.py):**
- `EnumString` TypeDecorator: stores enums as plain strings (PostgreSQL rejects SQLAlchemy `Enum` types when data has values outside the Python enum, e.g., `SUBMITTED`)
- `_EnumValue` wrapper: strings returned from DB have a `.value` property so existing `.value` calls don't break
- `NumpySafeJSON` TypeDecorator: recursively converts numpy types (float64, int64, bool_) to Python natives on write
- `NumpySafeFloat` TypeDecorator: converts numpy scalars to Python floats on write
- `JSON` and `Float` aliased to safe versions — every column in the ORM automatically gets numpy safety
- All `Enum()` columns replaced with `EnumString` (strategies, orders, positions, system_state, etc.)

**psycopg2 Numpy Adapters (src/models/database.py):**
- Registered `psycopg2.extensions.register_adapter` for np.float64, float32, int64, int32, bool_
- Catches numpy types at the driver level before they reach SQLAlchemy
- Without this, `np.float64(1.0)` renders as `np.float64(1.0)` in SQL — PostgreSQL interprets as schema reference

**Correlation Analyzer (src/strategy/correlation_analyzer.py):**
- Removed local `Base = declarative_base()` — now imports from `src.models.orm`
- Uses `_get_database_url()` instead of hardcoded SQLite path

**Data Migration (scripts/utilities/migrate_sqlite_to_postgres.py):**
- Migrates all 31 tables, 780K+ rows
- Boolean column casting (SQLite 0/1 → PostgreSQL true/false)
- Sequence reset for auto-increment IDs
- Row count verification per table
- Imports all ORM models (including trade_journal, performance_tracker, correlation_analyzer, performance_degradation_monitor)

**Dependencies:**
- `psycopg2-binary>=2.9.9` added to setup.py
- PostgreSQL 16 installed via Homebrew, running as service

**Indexes added for PostgreSQL:**
- `ix_positions_strategy_id`, `ix_positions_closed_at`, `ix_positions_opened_at`
- `ix_orders_strategy_id`, `ix_orders_status`
- `ix_strategies_status`
- `ix_trade_journal_strategy_id`
- `ANALYZE` run for query planner statistics

---

### 2. Analytics Dashboard Performance

**Frontend (frontend/src/pages/AnalyticsNew.tsx):**
- Phase 1 (core metrics) now skips re-fetch when data is less than 60s old
- Tab switches only fetch Phase 2 (tab-specific) data — no more 3 redundant API calls per tab click
- `lastFetchedAt` + `performanceMetrics` + `cioDashboard` used as freshness check

**Backend CIO Dashboard Cache (src/api/routers/analytics.py):**
- In-memory cache with 60s TTL for CIO dashboard endpoint
- Cache key: `{mode}:{period}`
- Saves ~2-3s of DB work per request (178 strategies + 120 positions)

**Analytics N+1 Query Fixes (src/api/routers/analytics.py):**
- Strategy attribution: 185 individual position queries → 2 bulk queries + in-memory grouping
- Regime analysis: same N+1 fix — 1 bulk position query, grouped by strategy_id in memory

---

### 3. Backtest avg_loss Bug Fix

**The bug:** `avg_loss` from vectorbt is in dollars (PnL.mean()). The retirement check tried to convert to percentage by dividing by `bt_trades['Size'].mean()`, but vectorbt's `Size` column is shares (not dollars). Result: inflated loss percentages like 258%.

**Fix (src/strategy/portfolio_manager.py):**
- Now computes position value as `Entry Price × Size` (shares × price = dollars)
- Fallback: $10K (10% of $100K backtest capital) — matches actual backtest sizing

**Fix (src/core/monitoring_service.py):**
- Changed fallback divisor from 30000 (arbitrary) to 10000 (matches backtest sizing)

**Note:** This bug never fired in production — the `total_trades >= 20` threshold was never met by active strategies. Fixed for correctness.

---

### 4. Strategy-Level Retirement → Position-Level Risk Management

**The fundamental shift:** Risk management moved from strategy-level (retire the whole strategy, close all positions) to position-level (evaluate each position individually, close bad ones, let winners run).

**Why:** A strategy is just a signal generator. The same RSI Dip Buy template might produce a great AAPL trade and a terrible TSLA trade. Retiring the strategy kills both. A PM manages positions, not strategies.

**What changed:**

**portfolio_manager.check_retirement_triggers() — now a no-op:**
- Returns `None` always
- Strategy-level retirement handled by decay score (gradual) and idle demotion (natural lifecycle)
- Comment documents the new architecture

**portfolio_manager.auto_retire_strategy() — simplified:**
- No longer closes positions or cancels orders
- Just logs the flag — positions managed individually
- Kept for backward compatibility with callers

**New: monitoring_service._check_position_health_individual():**
- Runs alongside trailing stops in the monitoring loop
- Evaluates each open position individually:
  1. **SL gap:** price blew through stop-loss (>2% below SL for longs, >2% above for shorts) — eToro didn't trigger the stop
  2. **Max loss exceeded:** position losing more than 2× configured SL% — something is wrong
  3. **Stale underwater:** losing >5% for 7+ days with no recovery — dead money
- Flags positions via `pending_closure = True` + `closure_reason` — same mechanism as trailing stop breaches
- `_process_pending_closures()` picks them up and submits close orders to eToro

**Decay score live P&L check (monitoring_service._check_strategy_decay):**
- Before retiring a strategy at decay=0, checks live P&L
- Profitable strategies get reprieve (decay reset to 3)
- Losing strategies proceed to retirement

**Decay score penalties — all live data now:**
- Stop-loss ineffectiveness penalty (#4) rewritten to use live closed positions
- Checks if >30-50% of closed losers lost more than 2× configured SL%
- No more backtest `perf` dict references in decay computation

**Position sync batch optimization (src/core/order_monitor.py):**
- All existing positions loaded in ONE query into dicts at start of sync
- Per-position lookups use O(1) dict gets instead of individual DB queries
- Saves ~124 round-trips to PostgreSQL per sync cycle
- Position sync: 1 second for 123 positions (was 30+ seconds with SQLite lock contention)

**SQLite contention workarounds removed:**
- 0.2s sleep between close orders (monitoring_service.py) — removed
- Trade journal retry-on-locked blocks (trade_journal.py) — removed
- These were SQLite-specific workarounds, unnecessary with PostgreSQL

---

### 5. Bug Fixes

**Trailing stop preservation in position sync:**
- Position sync batch-loads all positions into dicts
- Trailing stop preservation logic unchanged — still compares DB SL vs eToro SL

**EnumString .value compatibility:**
- `_EnumValue(str)` class has `.value` property returning `str(self)`
- All existing `.value` calls across 100+ files continue working without changes

---

## Key Files Modified This Session (V9)

- `src/models/database.py` — PostgreSQL support, numpy adapters, connection pooling
- `src/models/orm.py` — EnumString, NumpySafeJSON, NumpySafeFloat type decorators
- `src/api/routers/analytics.py` — CIO dashboard cache, N+1 query fixes
- `src/strategy/portfolio_manager.py` — Retirement → position-level risk, avg_loss fix
- `src/core/monitoring_service.py` — Position health checks, decay live data, SQLite workaround removal
- `src/core/order_monitor.py` — Position sync batch optimization
- `src/analytics/trade_journal.py` — SQLite retry removal
- `src/strategy/correlation_analyzer.py` — Shared Base, DATABASE_URL support
- `src/strategy/strategy_engine.py` — _save_strategy allocation_percent fix
- `src/strategy/autonomous_strategy_manager.py` — Retirement call updated
- `frontend/src/pages/AnalyticsNew.tsx` — Phase 1 freshness check
- `setup.py` — psycopg2-binary dependency
- `scripts/utilities/migrate_sqlite_to_postgres.py` — NEW: migration script
- `tests/manual/test_portfolio_manager.py` — Retirement tests rewritten for live data

## Current System State

- Database: PostgreSQL 16 (local, Homebrew) — 31 tables, 780K+ rows migrated
- Account: balance=$124K, equity=$465K+
- Active strategies: ~95 (DEMO)
- Open positions: ~123 (all healthy — 0 flagged by position health checks)
- Decay-0 strategies: 10 (2 profitable → saved, 8 losing → will retire)
- Sharpe ratio: showing 0 (only 7 trading days of data, needs 10)
- Position sync: 1 second for 123 positions
- All trailing stops, SL/TP, partial exits working normally

## Next Steps — V10 Priority

### PRIORITY 1: Git Commit & Push

Commit all V9 changes to GitHub. Major changes:
- PostgreSQL migration
- Position-level risk management
- Analytics performance
- ORM type safety (EnumString, NumpySafeJSON, NumpySafeFloat)

### PRIORITY 2: AWS Deployment

Move from local Mac to AWS for 24/7 operation:
- EC2 or ECS for the backend + monitoring service
- RDS PostgreSQL (or keep local PostgreSQL on EC2)
- Frontend: S3 + CloudFront (static hosting)
- Environment variables for DATABASE_URL, eToro credentials
- Systemd service or Docker container for backend
- Log aggregation (CloudWatch)
- Consider: is the eToro API latency acceptable from AWS? (currently ~25s for position fetch)

### From V8 Audit (Still Open)

1. **Signal Generation** — Are conviction scores using meaningful inputs?
6. **Template-Symbol Matching** — Should template weights from performance feedback decay over time?
7. **Risk Controls** — Portfolio-level VaR check before new positions
8. **Order Execution** — Is signal coordination too aggressive?
10. **Performance Feedback Loop** — Is it chasing past winners?

### From V8 (Still Open)

- **Forex carry bias** — FRED rate data available but not wired into forex strategy scoring
- **Transcript sentiment wiring** — Module built but not integrated into AE signal generation
- **Daily P&L timezone** — Dates in DB are UTC, frontend displays as-is

### Analytics/Risk Page — Remaining Items

- Historical named stress tests (COVID, Lehman, SVB)
- Drawdown recovery analysis
- R-Multiple distribution
- SPY benchmark comparison on equity curve
- Activation rejection reasons tracking

## How to Troubleshoot

1. Read `logs/cycles/cycle_history.log` for cycle summaries
2. Read `logs/alphacent.log` for detailed backend logs
3. Check PostgreSQL logs: `tail -f /opt/homebrew/var/log/postgresql@16.log`
4. Check trailing stops: Look for "trailing stop:" — shows asset class and distance %
5. Check position health: Look for "[PositionHealth]" — shows flagged positions and reasons
6. Check position closures: Look for "CLOSED:" — shows inferred reason
7. Check CIO dashboard: `GET /analytics/cio-dashboard?mode=DEMO&period=3M`
8. Check decay scores: Look for "[StrategyDecay]" — shows penalties and scores
9. Check DB connection: `venv/bin/python3 -c "from src.models.database import get_database; db = get_database(); print(f'PostgreSQL: {db.is_postgres}')"`
10. Switch to SQLite: `export DATABASE_URL=sqlite:///alphacent.db`
11. Re-migrate to PostgreSQL: `venv/bin/python3 scripts/utilities/migrate_sqlite_to_postgres.py`
