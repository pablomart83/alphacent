# AlphaCent — Intel Page Specification

> Read this document at the start of the implementation session before touching any code.
> All context needed to build Intel end-to-end is here.

---

## 1. What Intel Is

Intel is a manually-triggered analyst that reads all system data — logs, DB, cycle history,
trade journal, signal decisions, errors — applies a comprehensive library of structured checks,
and surfaces findings with enough evidence that you can act immediately or hand them to Kiro
with full context already loaded.

**Key design decisions:**
- Manual trigger only (no background polling). User chooses when to run and the lookback window.
- Findings persist in DB across sessions. Running again updates existing findings (increment
  occurrence_count, update last_seen) rather than creating duplicates.
- Log rotation handled: analyst reads alphacent.log + alphacent.log.1 through alphacent.log.N
  within the lookback window, merging them in chronological order.
- "Ask Kiro" button pre-fills a chat message with the finding title, evidence, and recommended
  action — eliminates the archaeology phase entirely.
- Own page in nav: Command · Book · Strategies · Guard · Research · **Intel** · Settings

---

## 2. Architecture Overview

```
[Run Analysis button] → POST /intel/run?lookback_days=N
                              ↓
                    IntelAnalyst.run(lookback_days)
                              ↓
                    ┌─────────────────────────────┐
                    │  Check library (A-H, ~50 checks) │
                    │  Each check: read DB/logs,   │
                    │  return Finding | None        │
                    └─────────────────────────────┘
                              ↓
                    Upsert into system_findings table
                    (dedup by check_id + key)
                              ↓
                    Return {run_id, findings_count, duration_s}

[Intel page] → GET /intel/findings?status=open&category=A&severity=P0
            → GET /intel/findings/{id}
            → POST /intel/findings/{id}/dismiss
            → POST /intel/findings/{id}/resolve
            → GET /intel/runs  (history of analysis runs)
```

---

## 3. Database Schema

```sql
-- Migration file: migrations/migrate_intel.sql

CREATE TABLE IF NOT EXISTS system_findings (
    id              VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    check_id        VARCHAR NOT NULL,          -- e.g. 'A6', 'B1', 'E5'
    key             VARCHAR NOT NULL,          -- dedup key, e.g. 'strategy:abc123' or 'symbol:ENPH'
    category        VARCHAR NOT NULL,          -- A-H
    severity        VARCHAR NOT NULL,          -- P0, P1, P2, opportunity
    title           VARCHAR NOT NULL,
    detail          TEXT NOT NULL,             -- root cause paragraph
    evidence        TEXT NOT NULL,             -- actual data: query result, log excerpt, metric
    recommended_action TEXT NOT NULL,
    context_links   JSON,                      -- [{label, url}] deep links to other pages
    ask_kiro_prompt TEXT NOT NULL,             -- pre-filled message for "Ask Kiro"
    first_seen      TIMESTAMP NOT NULL DEFAULT NOW(),
    last_seen       TIMESTAMP NOT NULL DEFAULT NOW(),
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    lookback_days   INTEGER NOT NULL DEFAULT 7,
    status          VARCHAR NOT NULL DEFAULT 'open',  -- open, dismissed, resolved
    dismissed_reason VARCHAR,
    resolved_at     TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_system_findings_check_key
    ON system_findings (check_id, key);

CREATE INDEX IF NOT EXISTS idx_system_findings_status
    ON system_findings (status, severity, category);

CREATE INDEX IF NOT EXISTS idx_system_findings_last_seen
    ON system_findings (last_seen DESC);

-- Analysis run history
CREATE TABLE IF NOT EXISTS intel_runs (
    id              VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    started_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMP,
    lookback_days   INTEGER NOT NULL,
    findings_created INTEGER DEFAULT 0,
    findings_updated INTEGER DEFAULT 0,
    findings_total   INTEGER DEFAULT 0,
    duration_s      FLOAT,
    error           TEXT,
    status          VARCHAR NOT NULL DEFAULT 'running'  -- running, complete, error
);
```

---

## 4. Backend Files to Create

```
src/analytics/intel_analyst.py      — check library + run orchestrator
src/analytics/intel_log_reader.py   — log rotation-aware reader
src/api/routers/intel.py            — FastAPI router (/intel/*)
```

### 4.1 intel_log_reader.py

Handles log rotation. EC2 log files:
```
/home/ubuntu/alphacent/logs/alphacent.log       (current)
/home/ubuntu/alphacent/logs/alphacent.log.1     (previous)
/home/ubuntu/alphacent/logs/alphacent.log.2     ...
/home/ubuntu/alphacent/logs/alphacent.log.N     (oldest)
```

Each file is max 10MB. Files rotate when current hits 10MB. The analyst needs to read
all files whose content falls within the lookback window.

```python
class IntelLogReader:
    LOG_DIR = "/home/ubuntu/alphacent/logs"
    LOG_FILES = [
        "alphacent.log", "alphacent.log.1", "alphacent.log.2", ...up to .log.100
        "errors.log", "errors.log.1",
        "strategy.log", "strategy.log.1",
        "cycles/cycle_history.log",
    ]

    def read_lines(self, log_name: str, lookback_days: int,
                   pattern: str = None) -> List[str]:
        """
        Read lines from log_name + all rotated versions (log_name.1, .2, ...)
        that fall within the lookback window. Returns lines in chronological order.
        Pattern: optional grep-style string to filter lines (applied per-line).
        Handles the case where rotated files have no timestamps on every line
        by using file mtime as a proxy for recency.
        """

    def grep_logs(self, pattern: str, lookback_days: int,
                  log_names: List[str] = None) -> List[Dict]:
        """
        Search across all relevant log files for pattern within lookback window.
        Returns [{file, line_number, timestamp, text}] sorted by timestamp.
        """

    def _parse_timestamp(self, line: str) -> Optional[datetime]:
        """Extract timestamp from log line. Format: '2026-05-15 18:38:48 - ...'"""

    def _get_rotated_files(self, base_name: str) -> List[str]:
        """Return [base_name, base_name.1, base_name.2, ...] that exist."""
```

### 4.2 intel_analyst.py

```python
@dataclass
class Finding:
    check_id: str
    key: str                    # dedup key
    category: str               # A-H
    severity: str               # P0, P1, P2, opportunity
    title: str
    detail: str                 # root cause
    evidence: str               # actual data
    recommended_action: str
    context_links: List[Dict]   # [{label, url}]
    ask_kiro_prompt: str        # pre-filled chat message

class IntelAnalyst:
    def __init__(self, db, log_reader: IntelLogReader):
        self.db = db
        self.log_reader = log_reader

    def run(self, lookback_days: int = 7) -> Dict:
        """Run all checks, upsert findings, return summary."""
        run_id = str(uuid4())
        # ... create intel_runs row, run all checks, upsert findings, update run row
```

---

## 5. Complete Check Library

Each check is a method on IntelAnalyst. Returns Finding or None.
Key format is always specific enough to dedup correctly across runs.

---

### Category A — Strategy Health

**A1 — BACKTESTED strategy with 0 signals for >3 days**
```
key: f"strategy:{strategy.id}"
query: SELECT id, name, status, activated_at, performance->>'last_signal_at'
       FROM strategies
       WHERE status = 'BACKTESTED'
       AND (performance->>'last_signal_at' IS NULL
            OR (performance->>'last_signal_at')::timestamp < NOW() - INTERVAL '3 days')
       AND activated_at < NOW() - INTERVAL '3 days'
severity: P1
evidence: List of strategy names + days since activation + days since last signal
action: "Check entry conditions in strategy_engine logs. Entry conditions may never fire
         for current market data. Consider retiring or adjusting template parameters."
ask_kiro: "Finding A1: [N] BACKTESTED strategies have had 0 signals for >3 days.
           Strategies: [list]. Check if entry conditions are achievable in current regime.
           Evidence: [evidence]. Investigate and recommend action."
```

**A2 — pending_retirement strategy still generating new positions**
```
key: f"strategy:{strategy.id}"
query: SELECT s.id, s.name, COUNT(p.id) as new_positions
       FROM strategies s
       JOIN positions p ON p.strategy_id = s.id
       WHERE s.strategy_metadata->>'pending_retirement' = 'true'
       AND p.opened_at > NOW() - INTERVAL '{lookback_days} days'
       AND p.closed_at IS NULL
       GROUP BY s.id, s.name HAVING COUNT(p.id) > 0
severity: P0
evidence: Strategy name + count of new positions opened while pending retirement
action: "Signal generation is not skipping pending_retirement strategies. Check
         trading_scheduler.py — add filter: skip strategies where
         strategy_metadata->>'pending_retirement' = 'true'."
```

**A3 — live_trade_count=0 after >10 closed positions**
```
key: f"strategy:{strategy.id}"
query: SELECT s.id, s.name, s.live_trade_count, COUNT(p.id) as closed_count
       FROM strategies s JOIN positions p ON p.strategy_id = s.id
       WHERE p.closed_at IS NOT NULL AND s.live_trade_count = 0
       GROUP BY s.id, s.name, s.live_trade_count HAVING COUNT(p.id) > 10
severity: P1
evidence: Strategy name + closed position count
action: "live_trade_count increment is not firing on async fills. Check
         order_monitor.check_submitted_orders fill handler — add increment call there."
```

**A4 — WF test Sharpe >3x train AND trades <8 (regime luck)**
```
key: f"strategy:{strategy.id}"
query: SELECT id, name, strategy_metadata->>'wf_test_sharpe' as test_s,
              strategy_metadata->>'wf_train_sharpe' as train_s,
              backtest_results->>'total_trades' as trades
       FROM strategies WHERE status IN ('BACKTESTED','PAPER')
       AND (strategy_metadata->>'wf_test_sharpe')::float > 0
       AND (strategy_metadata->>'wf_train_sharpe')::float > 0
       AND (strategy_metadata->>'wf_test_sharpe')::float /
           NULLIF((strategy_metadata->>'wf_train_sharpe')::float, 0) > 3
       AND (backtest_results->>'total_trades')::int < 8
severity: P1
evidence: Strategy name, test_sharpe, train_sharpe, ratio, trade count
action: "High test/train ratio with low trade count = regime luck. Consider retiring
         or requiring re-validation with stricter WF thresholds."
```

**A5 — Paper WR diverges from WF WR by >25pp after 10+ paper trades**
```
key: f"strategy:{strategy.id}"
query: SELECT id, name,
              (performance->>'paper_win_rate')::float as paper_wr,
              (backtest_results->>'win_rate')::float as wf_wr,
              (performance->>'paper_trades')::int as paper_trades
       FROM strategies
       WHERE (performance->>'paper_trades')::int >= 10
       AND ABS((performance->>'paper_win_rate')::float -
               (backtest_results->>'win_rate')::float) > 0.25
severity: P1
evidence: Strategy name, WF WR, paper WR, gap, trade count
action: "Edge not translating from backtest to paper. Check if market regime has
         changed since WF period, or if entry conditions are being triggered on
         different bar types than backtested."
```

**A6 — Strategy BACKTESTED >7 days with 0 paper trades**
```
key: f"strategy:{strategy.id}"
query: SELECT id, name, activated_at, performance->>'paper_trades' as pt
       FROM strategies WHERE status = 'BACKTESTED'
       AND activated_at < NOW() - INTERVAL '7 days'
       AND COALESCE((performance->>'paper_trades')::int, 0) = 0
severity: P1
evidence: Strategy name, days since activation
action: "Conviction threshold may be too high for this strategy's asset class or
         direction. Check signal_decisions for this strategy_id — look for
         filter:conviction rejections and compare score to threshold."
```

**A7 — Conviction scores clustered 65-69 (just below threshold)**
```
key: "conviction_threshold_calibration"
query: SELECT COUNT(*) FROM conviction_score_logs
       WHERE conviction_score BETWEEN 65 AND 69
       AND passed_threshold = false
       AND timestamp > NOW() - INTERVAL '{lookback_days} days'
threshold: >20 rejections in band
severity: P1
evidence: Count of rejections in 65-69 band vs total rejections
action: "Many strategies scoring just below threshold. Review conviction scorer
         calibration — particularly normalization denominator and asset-class
         effective maximums."
```

**A8 — 0% short exposure for >3 consecutive cycles**
```
key: "short_exposure_zero"
query: SELECT COUNT(*) FROM positions
       WHERE side = 'SHORT' AND closed_at IS NULL AND account_type = 'demo'
severity: P1
evidence: Current short count, last cycle exposure from cycle_history.log
action: "Directional diversity violated. Check: (1) SHORT strategies in BACKTESTED
         status with 0 signals, (2) conviction scores for SHORT strategies,
         (3) C3 trend-consistency gate blocking all SHORTs."
```

**A9 — Template family with >5 strategies all net negative paper P&L**
```
key: f"template:{template_name}"
query: SELECT strategy_metadata->>'template_name' as tname,
              COUNT(*) as count,
              SUM((performance->>'paper_pnl')::float) as total_pnl
       FROM strategies WHERE status IN ('BACKTESTED','PAPER')
       AND (performance->>'paper_trades')::int > 0
       GROUP BY tname HAVING COUNT(*) > 5
       AND SUM((performance->>'paper_pnl')::float) < 0
severity: P2
evidence: Template name, strategy count, total P&L
action: "Template family systematically losing. Consider disabling template or
         reviewing entry/exit conditions for structural flaw."
```

**A10 — Strategy generating >8 signals in 24h (overtrading)**
```
key: f"strategy:{strategy_id}"
query: SELECT strategy_id, COUNT(*) as signal_count
       FROM signal_decisions
       WHERE stage = 'signal_emitted' AND decision = 'emitted'
       AND timestamp > NOW() - INTERVAL '24 hours'
       GROUP BY strategy_id HAVING COUNT(*) > 8
severity: P2
evidence: Strategy name, signal count in 24h
action: "Frequency filter may be too loose for this strategy. Check
         alpha_edge.max_trades_per_strategy_per_month or add signal cooldown."
```

---

### Category B — Execution Quality

**B1 — Order FAILED rate >30% in last 24h**
```
key: "order_failed_rate"
query: SELECT COUNT(*) FILTER (WHERE status='FAILED') as failed,
              COUNT(*) as total
       FROM orders WHERE created_at > NOW() - INTERVAL '24 hours'
       AND account_type = 'demo'
severity: P1
evidence: Failed count, total count, failure rate %, sample of failed order reasons
action: "High FAILED rate usually means market-closed deferrals written as FAILED.
         Check order_executor.py deferred path — should write DEFERRED not FAILED."
```

**B2 — Same (strategy, symbol, direction) submitted >3 times in 1h**
```
key: f"order_dedup:{strategy_id}:{symbol}:{direction}"
query: SELECT strategy_id, symbol, side, COUNT(*) as count
       FROM orders WHERE created_at > NOW() - INTERVAL '1 hour'
       AND account_type = 'demo'
       GROUP BY strategy_id, symbol, side HAVING COUNT(*) > 3
severity: P0
evidence: Strategy, symbol, direction, count, timestamps
action: "Cross-cycle dedup broken. Check trading_scheduler signal dedup logic.
         May be creating duplicate positions."
```

**B3 — Slippage NULL on >50% of filled orders**
```
key: "slippage_not_populated"
query: SELECT COUNT(*) FILTER (WHERE slippage IS NULL) as null_count,
              COUNT(*) as total
       FROM orders WHERE status = 'FILLED'
       AND filled_at > NOW() - INTERVAL '{lookback_days} days'
severity: P2
evidence: Null count, total filled, null rate %
action: "Execution quality blind. In order_monitor fill handler, compute:
         slippage = (filled_price - expected_price) / expected_price * side_sign
         and save to orders.slippage column."
```

**B4 — Order stuck PENDING >2h during market hours**
```
key: f"order:{order_id}"
query: SELECT id, symbol, side, created_at, status
       FROM orders WHERE status IN ('PENDING','SUBMITTED')
       AND created_at < NOW() - INTERVAL '2 hours'
       AND account_type = 'demo'
severity: P1
evidence: Order ID, symbol, age in hours
action: "Order stuck. Check eToro API for this order ID. May need manual
         cancellation or the order_monitor fill check is not running."
```

**B5 — Position etoro_position_id collision across account_types**
```
key: "etoro_id_collision"
query: SELECT etoro_position_id, COUNT(DISTINCT account_type) as acct_count
       FROM positions WHERE etoro_position_id IS NOT NULL
       GROUP BY etoro_position_id HAVING COUNT(DISTINCT account_type) > 1
severity: P0
evidence: Colliding position IDs and account types
action: "account_type scoping bug. eToro reuses numeric position IDs across
         demo/live. Check OrderMonitor queries — all must filter by account_type."
```

**B6 — Position with strategy_id NULL after >10 min**
```
key: f"position:{position_id}"
query: SELECT id, symbol, opened_at FROM positions
       WHERE strategy_id IS NULL AND closed_at IS NULL
       AND opened_at < NOW() - INTERVAL '10 minutes'
       AND account_type = 'demo'
severity: P1
evidence: Position ID, symbol, age
action: "Race condition: position sync created row before fill set strategy_id.
         Check order_monitor fill handler — strategy_id must be set atomically
         with position creation."
```

**B8 — Order size <$1000 attempted**
```
key: "order_size_below_minimum"
query: grep errors.log for "Order size must be at least" within lookback window
severity: P2
evidence: Log lines with symbol and requested size
action: "Position sizing calculation producing sub-minimum sizes. Check
         risk_manager.calculate_position_size — MINIMUM_ORDER_SIZE guard
         should prevent this reaching order_executor."
```

---

### Category C — Risk & Position Management

**C1 — Symbol at >5% equity across all strategies**
```
key: f"concentration:{symbol}"
query: SELECT symbol, SUM(invested_amount) as total_invested,
              SUM(invested_amount) / (SELECT balance FROM account_snapshots
                                      ORDER BY created_at DESC LIMIT 1) as pct
       FROM positions WHERE closed_at IS NULL AND account_type = 'demo'
       GROUP BY symbol
       HAVING SUM(invested_amount) / (SELECT balance FROM account_snapshots
                                      ORDER BY created_at DESC LIMIT 1) > 0.05
severity: P1
evidence: Symbol, total invested, % of equity, position count
action: "Symbol concentration cap not enforced cumulatively. Check
         order_executor pre-flight — must sum existing exposure for symbol
         across all open positions before allowing new entry."
```

**C2 — Portfolio heat >30%**
```
key: "portfolio_heat"
query: SELECT SUM(invested_amount) / (SELECT balance FROM account_snapshots
                                      ORDER BY created_at DESC LIMIT 1) as heat
       FROM positions WHERE closed_at IS NULL AND account_type = 'demo'
severity: P1
evidence: Current heat %, equity, total invested
action: "Portfolio heat cap breached. New entries should be blocked until
         heat drops below 30%. Check risk_manager heat gate."
```

**C3 — Position profitable >7% with SL still at entry price**
```
key: f"position:{position_id}"
query: SELECT id, symbol, entry_price, current_price, stop_loss,
              (current_price - entry_price) / entry_price as pnl_pct
       FROM positions WHERE closed_at IS NULL AND account_type = 'demo'
       AND side = 'LONG'
       AND stop_loss = entry_price
       AND (current_price - entry_price) / entry_price > 0.07
severity: P2
evidence: Symbol, entry, current, P&L%, SL still at entry
action: "TSL not ratcheting above +7%. Check monitoring_service._check_trailing_stops
         — profit_lock and trail thresholds. Position may have stale price data
         preventing ratchet."
```

**C4 — Zombie position: flat ±1% for >5 days (1D) or >3 days (4H)**
```
key: f"position:{position_id}"
query: SELECT p.id, p.symbol, p.opened_at, p.unrealized_pnl,
              p.invested_amount,
              ABS(p.unrealized_pnl / NULLIF(p.invested_amount, 0)) as pnl_pct,
              s.strategy_metadata->>'interval' as interval
       FROM positions p JOIN strategies s ON s.id = p.strategy_id
       WHERE p.closed_at IS NULL AND p.account_type = 'demo'
       AND ABS(p.unrealized_pnl / NULLIF(p.invested_amount, 0)) < 0.01
       AND (
         (s.strategy_metadata->>'interval' = '1d'
          AND p.opened_at < NOW() - INTERVAL '5 days')
         OR
         (s.strategy_metadata->>'interval' = '4h'
          AND p.opened_at < NOW() - INTERVAL '3 days')
       )
severity: P2
evidence: Symbol, days open, P&L%, strategy interval
action: "Zombie exit threshold not triggering. Check monitoring_service zombie
         exit logic — flat threshold and minimum age for this interval."
```

**C5 — SHORT exposure 0% for >3 cycles in trending_up regime**
```
key: "short_exposure_directional_quota"
(combines with A8 — same check, different framing for regime context)
```

**C7 — Position with stop_loss NULL**
```
key: f"position:{position_id}"
query: SELECT id, symbol, side, entry_price, opened_at
       FROM positions WHERE closed_at IS NULL
       AND stop_loss IS NULL AND account_type = 'demo'
severity: P0
evidence: Position ID, symbol, entry price, age
action: "Unprotected position — no stop loss set. Check order_executor ATR
         stop calculation. Position must be manually reviewed."
```

---

### Category D — Data Pipeline

**D1 — Open position symbol with 1D bars >2 days stale**
```
key: f"data_stale:{symbol}:1d"
query: SELECT p.symbol,
              MAX(h.date) as latest_bar,
              NOW() - MAX(h.date) as staleness
       FROM positions p
       LEFT JOIN historical_price_cache h
         ON h.symbol = p.symbol AND h.interval = '1d'
       WHERE p.closed_at IS NULL AND p.account_type = 'demo'
       GROUP BY p.symbol
       HAVING NOW() - MAX(h.date) > INTERVAL '2 days'
severity: P1
evidence: Symbol, latest bar date, staleness in hours
action: "Signal generation running on stale data for open position. Check
         _sync_price_data for this symbol — may be Yahoo ticker mapping issue
         or DST crash. Run manual full sync."
```

**D2 — Open position symbol with 4H bars >6h stale**
```
key: f"data_stale:{symbol}:4h"
(same pattern as D1 but for 4h interval and 6h threshold)
severity: P1
```

**D3 — Yahoo "possibly delisted" errors for liquid symbols**
```
key: f"yahoo_delisted:{symbol}"
source: grep errors.log + alphacent.log for "possibly delisted" within lookback
severity: P2
evidence: Symbol names, frequency, last occurrence
action: "Yahoo ticker mapping wrong for this symbol. Check symbol_mapper.py
         to_yahoo_ticker() — may need explicit override for this symbol."
```

**D4 — FMP rate limit hit**
```
key: "fmp_rate_limit"
source: grep errors.log for "FMP rate limit exceeded" within lookback
severity: P1
evidence: Count of rate limit hits, timestamps
action: "FMP Starter plan: 300 calls/min. Rate limit hit means fundamental data
         unavailable for part of cycle. Consider spreading FMP calls across
         cycle phases or upgrading plan."
```

**D7 — Duplicate rows in historical_price_cache**
```
key: f"data_duplicate:{symbol}:{interval}"
query: SELECT symbol, interval, DATE(date) as day, COUNT(*) as count
       FROM historical_price_cache
       WHERE interval = '1d'
       GROUP BY symbol, interval, DATE(date)
       HAVING COUNT(*) > 1
       LIMIT 20
severity: P2
evidence: Symbol, interval, date, duplicate count
action: "Duplicate 1d bars. Run: DELETE FROM historical_price_cache WHERE id NOT IN
         (SELECT MIN(id) FROM historical_price_cache GROUP BY symbol, interval,
         DATE(date)). Then add upsert logic in _save_historical_to_db."
```

**D8 — MQS NULL in equity_snapshots for >3 consecutive days**
```
key: "mqs_null_snapshots"
query: SELECT COUNT(*) FROM equity_snapshots
       WHERE market_quality_score IS NULL
       AND created_at > NOW() - INTERVAL '3 days'
severity: P2
evidence: Count of NULL MQS snapshots, date range
action: "MQS persistence broken. Check _save_hourly_equity_snapshot in
         monitoring_service.py — MQS computation wrapped in except:pass.
         Fix the silent failure."
```

---

### Category E — Cycle & Signal Pipeline

**E1 — Cycle duration >1200s**
```
key: "cycle_duration_regression"
source: parse cycle_history.log for "CYCLE COMPLETE in Xs" within lookback
severity: P2
evidence: Last 5 cycle durations, trend
action: "Cycle slowing down. Check: (1) WF cache hit rate dropping,
         (2) new 1h strategies added (large WF windows), (3) DB query performance."
```

**E2 — WF cache hit rate <40%**
```
key: "wf_cache_hit_rate"
source: grep strategy.log for "WF cache hit" and "WF window [" within lookback
severity: P2
evidence: Hit count, miss count, hit rate %
action: "WF cache not effective. Check wf_cache_ttl in autonomous_trading.yaml
         (should be 1h). Cache may be invalidated too aggressively."
```

**E3 — <10 fresh proposals in a cycle**
```
key: "proposal_count_low"
source: parse cycle_history.log for "fresh (DSL=" within lookback
severity: P2
evidence: Last 5 cycle proposal counts
action: "Template pool may be exhausted or rejection blacklist too aggressive.
         Check: (1) .wf_failed_cache.json size, (2) .rejection_blacklist.json,
         (3) .zero_trade_blacklist.json."
```

**E4 — 0 SHORT proposals passing WF for >5 cycles**
```
key: "short_wf_pass_rate"
source: grep strategy.log for "✓.*SHORT" within lookback
severity: P1
evidence: Count of SHORT WF passes in lookback window, total SHORT proposals
action: "SHORT strategies not passing WF. Check: (1) min_sharpe threshold for
         SHORTs (+0.3 tightening), (2) trade count requirements vs typical
         SHORT setup frequency, (3) whether SHORT templates are being proposed."
```

**E5 — Signal emitted but gate_blocked >10 times for same strategy in 24h**
```
key: f"gate_loop:{strategy_id}"
query: SELECT strategy_id, COUNT(*) as blocked_count,
              MAX(reason) as last_reason
       FROM signal_decisions
       WHERE stage = 'gate_blocked'
       AND timestamp > NOW() - INTERVAL '24 hours'
       GROUP BY strategy_id HAVING COUNT(*) > 10
severity: P1
evidence: Strategy name, block count, gate reason
action: "Strategy permanently blocked by gate. Either the gate logic is wrong
         for this strategy type, or the strategy should be retired. Review
         gate logic vs conviction scorer — they should be consistent."
```

**E8 — Cycle started while previous cycle still running**
```
key: "concurrent_cycles"
source: grep alphacent.log for "Starting autonomous cycle" — check if two
        cycle IDs appear without "DB lock released" between them
severity: P0
evidence: Cycle IDs and timestamps showing overlap
action: "Cycle lock broken. Check _db_cycle_lock in strategies.py — lock
         must be acquired before cycle starts and released in finally block."
```

**E10 — signal_decisions table not written for a cycle**
```
key: f"signal_decisions_missing:{cycle_id}"
query: Check if signal_decisions has rows with timestamp in cycle window
       by comparing cycle_history.log cycle start/end times
severity: P2
evidence: Cycle ID, start/end time, signal_decisions count in window
action: "Decision log not writing. Check decision_log.py record_decision —
         may be silently failing. Verify DB permissions on signal_decisions table."
```

---

### Category F — System Health

**F1 — New ERROR entries in errors.log since last run**
```
key: "errors_log_new"
source: grep errors.log for lines newer than last intel run timestamp
severity: P0 if SQLAlchemy/P0 keywords, P1 otherwise
evidence: Last 10 error lines with timestamps
action: "Review errors above. P0 keywords: UniqueViolation, InFailedSqlTransaction,
         duplicate key, account_type collision."
```

**F2 — SQLAlchemy InFailedSqlTransaction**
```
key: "sqlalchemy_failed_transaction"
source: grep errors.log for "InFailedSqlTransaction" within lookback
severity: P0
evidence: Error lines, affected SQL, frequency
action: "Transaction not rolled back after error. Find the DB session that
         raised the original error and ensure session.rollback() is called
         in the except block before any subsequent queries."
```

**F3 — Postgres idle connections >8**
```
key: "postgres_connections"
query: SELECT COUNT(*) FROM pg_stat_activity
       WHERE datname = 'alphacent' AND state = 'idle'
severity: P2
evidence: Idle connection count, total connections
action: "Connection pool may be leaking. Check that all DB sessions are closed
         in finally blocks. Consider adding pool_pre_ping=True to engine."
```

**F5 — Service restart detected (uptime <30 min)**
```
key: "service_restart"
source: grep alphacent.log for "AlphaCent backend starting" within lookback
severity: P1
evidence: Restart timestamps, count in lookback window
action: "Unexpected service restart. Check: (1) cycle_error.log for crash,
         (2) errors.log around restart time, (3) systemd journal for OOM killer."
```

**F7 — External API rate limit errors**
```
key: f"api_rate_limit:{provider}"
source: grep errors.log for "rate limit" OR "429" within lookback
severity: P1
evidence: Provider (eToro/FMP/Yahoo), error count, timestamps
action: "API rate limit hit. Check call frequency and add backoff. For FMP:
         300 calls/min on Starter plan. For eToro: check circuit breaker state."
```

**F8 — cycle_error.log non-empty**
```
key: "cycle_error_log"
source: read /home/ubuntu/alphacent/cycle_error.log — non-empty = crash
severity: P0
evidence: Full contents of cycle_error.log
action: "Autonomous cycle crashed with unhandled exception. Fix the root cause
         before running next cycle."
```

---

### Category G — Alpha & Improvement Opportunities

**G1 — Template with WF Sharpe >2.0 in cache but never activated in 7 days**
```
key: f"template_blocked:{template_name}:{symbol}"
query: SELECT DISTINCT template_name, symbol, score
       FROM signal_decisions
       WHERE stage = 'wf_validated' AND decision = 'accepted'
       AND (decision_metadata->>'wf_test_sharpe')::float > 2.0
       AND timestamp > NOW() - INTERVAL '{lookback_days} days'
       AND (template_name, symbol) NOT IN (
         SELECT strategy_metadata->>'template_name', symbols->>0
         FROM strategies WHERE status IN ('BACKTESTED','PAPER','LIVE')
         AND activated_at > NOW() - INTERVAL '7 days'
       )
severity: opportunity
evidence: Template name, symbol, WF Sharpe, rejection reason from signal_decisions
action: "Strong WF edge not activating. Check activation criteria rejection reason
         in signal_decisions (stage=rejected_act). May be avg_loss gate, min_sharpe,
         or MC bootstrap failing."
```

**G2 — Asset class with >60% live WR but <15% of active strategies**
```
key: f"underweighted_asset_class:{asset_class}"
query: Compare live WR by asset_class from trade_journal vs
       strategy count by asset_class from strategies table
severity: opportunity
evidence: Asset class, live WR, strategy count, % of total
action: "High-WR asset class underweighted. Increase proposal quota for this
         class in strategy_proposer or raise asset tradability score."
```

**G3 — Symbol with strong forward return but 0 captured P&L**
```
key: f"missed_alpha:{symbol}"
source: per_symbol_opportunity_cost() from existing observability.py
severity: opportunity
evidence: Symbol, forward return %, captured %, opportunity cost %
action: "System not trading this symbol despite strong move. Check rejection
         blacklist and WF cache for this symbol."
```

**G5 — Strategy with live Sharpe <0.3x WF Sharpe after 10+ trades**
```
key: f"strategy:{strategy.id}"
source: wf_live_divergence() from existing observability.py
severity: P2
evidence: Strategy name, WF Sharpe, live Sharpe, ratio, trade count
action: "Edge not translating. Consider retiring strategy. Check if market
         regime has changed since WF validation period."
```

**G7 — Regime×template cell with >10 trades and <30% WR**
```
key: f"regime_template:{regime}:{template}:{direction}"
source: regime_template_pnl_matrix() from existing observability.py
severity: opportunity
evidence: Regime, template, direction, trade count, WR, total P&L
action: "This template/regime combination is a systematic loser. Add to
         regime suppression list in strategy_proposer."
```

**G9 — Strategies with wf_performance_degradation < -500% still active**
```
key: f"strategy:{strategy.id}"
query: SELECT id, name, strategy_metadata->>'wf_performance_degradation' as deg,
              strategy_metadata->>'wf_test_sharpe' as test_s,
              strategy_metadata->>'wf_train_sharpe' as train_s
       FROM strategies WHERE status IN ('BACKTESTED','PAPER')
       AND (strategy_metadata->>'wf_performance_degradation')::float < -500
severity: P2
evidence: Strategy name, degradation %, test/train Sharpe
action: "Extreme regime luck — test Sharpe 6x+ above train. Strategy likely
         captured a single regime event. Consider retiring or requiring
         re-validation with stricter consistency gate."
```

---

### Category H — Config & Code Integrity

**H1 — Config value doesn't match hardcoded code value**
```
key: "config_code_divergence"
checks:
  - autonomous_trading.yaml atr_sl_multiplier vs order_executor.py hardcoded 1.5
  - autonomous_trading.yaml min_trades vs code defaults
  - graduation_gate.min_trades (should be raised back to 20 from 15)
severity: P2
evidence: Config key, config value, code location, code value
action: "Either wire config to code or remove dead config key. Dead config
         creates false confidence that the value is being used."
```

**H3 — graduation_gate.min_trades still at 15**
```
key: "graduation_min_trades_low"
source: read autonomous_trading.yaml graduation_gate.min_trades
severity: P2
evidence: Current value (15), intended value (20)
action: "min_trades was lowered to 15 to enable GOOGL test graduation.
         Raise back to 20 now that live system is stable. Update via
         Settings UI or direct YAML edit on EC2."
```

**H4 — PAPER conviction threshold at 70 (was temporarily lowered)**
```
key: "paper_conviction_threshold"
source: read autonomous_trading.yaml alpha_edge.min_conviction_score
severity: P2 (informational)
evidence: Current value, date lowered, 70-72 band performance stats
action: "Monitor 70-72 band performance. If win rate holds after 15+ trades
         per strategy, threshold is correctly calibrated. If WR <50%, raise
         back to 73."
```

---

## 6. Backend Router — intel.py

```python
# src/api/routers/intel.py
# Mount in app.py: app.include_router(intel_router, prefix="/intel")

from fastapi import APIRouter, Depends, Query
from typing import Optional

router = APIRouter(prefix="/intel", tags=["intel"])

@router.post("/run")
async def run_analysis(
    lookback_days: int = Query(default=7, ge=1, le=90),
    username: str = Depends(get_current_user)
):
    """
    Trigger a full analysis run. Returns immediately with run_id.
    Analysis runs synchronously (fast enough — all DB queries, no external calls).
    Typical duration: 5-15 seconds for full check library.
    """

@router.get("/runs")
async def get_runs(limit: int = 20, username: str = Depends(get_current_user)):
    """List recent analysis runs with status, duration, finding counts."""

@router.get("/findings")
async def get_findings(
    status: Optional[str] = Query(default="open"),   # open|dismissed|resolved|all
    category: Optional[str] = None,                   # A|B|C|D|E|F|G|H
    severity: Optional[str] = None,                   # P0|P1|P2|opportunity
    limit: int = 200,
    username: str = Depends(get_current_user)
):
    """Get findings with optional filters."""

@router.get("/findings/{finding_id}")
async def get_finding(finding_id: str, username: str = Depends(get_current_user)):
    """Get single finding with full detail."""

@router.post("/findings/{finding_id}/dismiss")
async def dismiss_finding(
    finding_id: str,
    body: DismissBody,  # {reason: str}
    username: str = Depends(get_current_user)
):
    """Dismiss a finding with a reason."""

@router.post("/findings/{finding_id}/resolve")
async def resolve_finding(finding_id: str, username: str = Depends(get_current_user)):
    """Mark a finding as resolved."""

@router.get("/summary")
async def get_summary(username: str = Depends(get_current_user)):
    """
    Summary counts for nav badge and top tiles:
    {p0_open, p1_open, p2_open, opportunities_open, resolved_this_week,
     last_run_at, last_run_duration_s, last_run_findings}
    """
```

---

## 7. Frontend Files to Create

```
frontend/src/pages/intel/
  Intel.tsx                    — page shell, tab-less (single view)
  IntelPage.tsx                — main layout: run controls + summary tiles + findings
  FindingsList.tsx             — left panel: filterable list of findings
  FindingDetail.tsx            — right panel: full finding with evidence + actions
  useIntelData.ts              — React Query hooks for all intel endpoints
  IntelSummaryTiles.tsx        — P0/P1/P2/Opportunity count tiles at top
  RunHistoryPanel.tsx          — collapsible run history
```

---

## 8. Frontend Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Intel                                                    [Run Analysis ▼]│
│                                                          Lookback: [7d ▼]│
├──────────────┬──────────────┬──────────────┬──────────────┬─────────────┤
│  P0 Open     │  P1 Open     │  P2 Open     │ Opportunities│ Resolved 7d │
│  [red]  2    │ [amber]  5   │ [yellow]  8  │ [blue]  4    │ [green]  3  │
├─────────────────────────────────────────────────────────────────────────┤
│ Last run: 2 min ago · 19 findings · 14.2s                               │
├──────────────────────────┬──────────────────────────────────────────────┤
│ FINDINGS                 │ FINDING DETAIL                               │
│                          │                                              │
│ [All] [Open] [Dismissed] │ A6 · P1 · Strategy Health                   │
│ [Resolved]               │                                              │
│                          │ Parabolic Move Short Uptrend ENPH SHORT      │
│ Filter: [Category ▼]     │ BACKTESTED 7 days with 0 paper trades        │
│         [Severity ▼]     │                                              │
│                          │ ROOT CAUSE ─────────────────────────────     │
│ ● P0  B5  etoro_id...    │ Conviction threshold (70) too high for this  │
│ ● P0  F8  cycle_error... │ strategy. Signal_decisions shows scores of   │
│ ● P1  A6  ENPH SHORT...  │ 60.9 consistently rejected.                  │
│ ● P1  A8  0% short exp.. │                                              │
│ ● P1  E5  ENPH gate...   │ EVIDENCE ───────────────────────────────     │
│ ● P1  D1  AAPL 1d stale  │ signal_decisions (last 7d):                  │
│ ● P2  A4  SHOP SHORT...  │   rejected: 47 times                         │
│ ● P2  C3  NSDQ100 TSL... │   reason: filter:conviction (60.9 < 70)      │
│ ○ opp G2  Indices 85%... │   wf_edge=20.6, signal=15.0, regime=20.0    │
│ ○ opp G3  NVDA missed... │                                              │
│                          │ RECOMMENDED ACTION ─────────────────────     │
│                          │ Check conviction scorer for SHORT strategies. │
│                          │ Run: SELECT * FROM conviction_score_logs      │
│                          │ WHERE symbol='ENPH' ORDER BY timestamp DESC   │
│                          │ LIMIT 10;                                     │
│                          │                                              │
│                          │ CONTEXT ────────────────────────────────     │
│                          │ → Guard / Audit  → Research / Attribution    │
│                          │                                              │
│                          │ [Dismiss]  [Mark Resolved]  [Ask Kiro →]    │
└──────────────────────────┴──────────────────────────────────────────────┘
```

**"Ask Kiro" button** copies this to the chat input:
```
Intel finding [A6]: "Parabolic Move Short Uptrend ENPH SHORT — BACKTESTED 7 days
with 0 paper trades."

Evidence: signal_decisions shows 47 conviction rejections in 7 days, score 60.9
consistently below threshold 70. Breakdown: wf_edge=20.6, signal=15.0, regime=20.0,
asset=12.0.

Recommended action: Check conviction scorer calibration for SHORT strategies.
Investigate and fix.
```

**Run Analysis button** opens a small popover:
```
┌─────────────────────────┐
│ Run Analysis            │
│                         │
│ Lookback window         │
│ ○ 1 day                 │
│ ● 7 days                │
│ ○ 14 days               │
│ ○ 30 days               │
│ ○ 90 days               │
│                         │
│ [Cancel]  [Run →]       │
└─────────────────────────┘
```

---

## 9. Nav Integration

### TopNavBar.tsx — add Intel to NAV_ITEMS

```typescript
const NAV_ITEMS = [
  { path: '/', label: 'Command', shortcut: 'G C' },
  { path: '/book', label: 'Book', shortcut: 'G B' },
  { path: '/strategies', label: 'Strategies', shortcut: 'G S' },
  { path: '/guard', label: 'Guard', shortcut: 'G G' },
  { path: '/research', label: 'Research', shortcut: 'G R' },
  { path: '/intel', label: 'Intel', shortcut: 'G I' },   // ← ADD THIS
] as const
```

Add badge on Intel nav item showing P0+P1 open count (red if P0 exists, amber otherwise).
Fetch from GET /intel/summary on a 60s interval.

### App.tsx — add route

```typescript
const Intel = lazy(() => import('./pages/intel/Intel').then((m) => ({ default: m.Intel })))

// In routes:
<Route
  path="intel/*"
  element={
    <Suspense fallback={<PageFallback />}>
      <Intel />
    </Suspense>
  }
/>
```

### KeyboardShortcutHelp.tsx — add G I shortcut

---

## 10. useIntelData.ts — React Query Hooks

```typescript
export function useIntelSummary() {
  return useQuery({
    queryKey: ['intel-summary'],
    queryFn: () => api.get('/intel/summary'),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

export function useIntelFindings(filters: {
  status?: string
  category?: string
  severity?: string
}) {
  return useQuery({
    queryKey: ['intel-findings', filters],
    queryFn: () => api.get('/intel/findings', filters),
    staleTime: 30_000,
  })
}

export function useIntelFinding(id: string | null) {
  return useQuery({
    queryKey: ['intel-finding', id],
    queryFn: () => api.get(`/intel/findings/${id}`),
    enabled: !!id,
    staleTime: 30_000,
  })
}

export function useRunAnalysis() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (lookback_days: number) =>
      api.post('/intel/run', {}, { params: { lookback_days } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['intel-findings'] })
      qc.invalidateQueries({ queryKey: ['intel-summary'] })
      qc.invalidateQueries({ queryKey: ['intel-runs'] })
    },
  })
}

export function useDismissFinding() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api.post(`/intel/findings/${id}/dismiss`, { reason }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['intel-findings'] }),
  })
}

export function useResolveFinding() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post(`/intel/findings/${id}/resolve`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['intel-findings'] }),
  })
}
```

---

## 11. Log Rotation Handling — Implementation Detail

EC2 log rotation config: each file max 10MB, up to 100 rotated copies.
Files are named `alphacent.log`, `alphacent.log.1`, ..., `alphacent.log.100`.
Newer content is in lower-numbered files. `alphacent.log` is current.

**Algorithm for IntelLogReader.read_lines(log_name, lookback_days, pattern):**

```python
def read_lines(self, log_name: str, lookback_days: int, pattern: str = None):
    cutoff = datetime.now() - timedelta(days=lookback_days)
    base = os.path.join(self.LOG_DIR, log_name)
    
    # Collect all rotated files that might contain data in window
    files_to_read = []
    for suffix in [''] + [f'.{i}' for i in range(1, 101)]:
        path = base + suffix
        if not os.path.exists(path):
            break  # rotated files are sequential — stop at first gap
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        # Include file if its mtime is within lookback (proxy for content recency)
        # Always include current file (no suffix) and .1
        if suffix in ('', '.1') or mtime >= cutoff:
            files_to_read.append(path)
        else:
            break  # files get older as number increases — stop early
    
    lines = []
    for path in reversed(files_to_read):  # oldest first for chronological order
        try:
            with open(path, 'r', errors='replace') as f:
                for line in f:
                    if pattern and pattern not in line:
                        continue
                    ts = self._parse_timestamp(line)
                    if ts and ts < cutoff:
                        continue
                    lines.append(line.rstrip())
        except (IOError, PermissionError):
            continue
    
    return lines
```

**Timestamp parsing:** Log format is `2026-05-15 18:38:48 - src.module - LEVEL - message`
Parse with: `datetime.strptime(line[:19], '%Y-%m-%d %H:%M:%S')`

**cycle_history.log** has a different format — parse cycle blocks by looking for
`CYCLE cycle_XXXXXXXXXX | YYYY-MM-DD HH:MM:SS` as block headers.

---

## 12. Implementation Order

Do this in a single session in this order:

1. **DB migration** — create system_findings + intel_runs tables on EC2
2. **intel_log_reader.py** — log rotation reader, test with a grep call
3. **intel_analyst.py** — IntelAnalyst class + all checks (A1-H4)
4. **intel.py router** — 6 endpoints, wire into app.py
5. **Deploy backend** — scp + restart + verify /intel/run returns findings
6. **useIntelData.ts** — all hooks
7. **Intel.tsx + IntelPage.tsx** — page shell + layout
8. **FindingsList.tsx** — left panel with filters
9. **FindingDetail.tsx** — right panel with evidence + Ask Kiro button
10. **IntelSummaryTiles.tsx** — top tiles
11. **Nav integration** — TopNavBar + App.tsx + shortcut help
12. **Build + deploy frontend**
13. **Verify end-to-end**: run analysis, see findings, dismiss one, resolve one

---

## 13. Key Files to Read Before Starting

```bash
# Backend
src/analytics/observability.py          — existing checks to reuse (mae_at_stop,
                                          wf_live_divergence, regime_template_pnl_matrix,
                                          template_graduation_funnel, per_symbol_opportunity_cost)
src/api/routers/data_management.py      — pattern for data endpoints
src/models/orm.py                       — existing ORM models to reference
src/models/database.py                  — get_database() pattern

# Frontend
frontend/src/pages/guard/Guard.tsx      — tab page pattern to follow
frontend/src/pages/guard/useGuardData.ts — hook pattern to follow
frontend/src/components/trading/TopNavBar.tsx — nav to modify
frontend/src/App.tsx                    — routing to modify
```

---

## 14. Session Kickoff Prompt

```
Read .kiro/steering/trading-system-context.md and Session_Continuation.md in full.
Then read INTEL_SPEC.md in full — this is the complete spec for the Intel page.

Build Intel end-to-end following the implementation order in section 12.
Key constraints:
- Manual trigger only, no background polling
- Log rotation handled via IntelLogReader (section 11)
- Reuse existing observability.py functions for G-category checks
- "Ask Kiro" button copies pre-filled text to clipboard (not to chat API)
- Nav badge shows P0+P1 open count, fetched every 60s from /intel/summary
- All DB queries scoped to account_type='demo' unless explicitly cross-account

Do not start implementing until you have read all 4 documents above.
```

---

## 15. What This Changes

**Before Intel:**
"Check what's happening with SHORT strategies" → 2 hours log archaeology → 5-minute fix.

**After Intel:**
Open Intel page → see findings A6 (0 paper trades), A7 (conviction 65-69 band),
E5 (gate blocking same strategy 47×) → click "Ask Kiro" on each → 15 minutes total.

The findings page becomes the session kickoff. Instead of running the checklist manually,
open Intel, triage open findings, work through them in priority order.
Every bug we've ever fixed is now a check that runs automatically on demand.
