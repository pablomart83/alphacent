"""
Structured cycle logger for autonomous trading cycles.
Writes detailed logs to logs/cycles/cycle_history.log.
Intercepts ERROR/WARNING from the entire app during active cycles.
Keeps only the last N full cycles (default 10) to prevent unbounded growth.
"""
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)
_cycle_logger: Optional['CycleLogger'] = None


class CycleLogHandler(logging.Handler):
    """Captures errors, warnings, and key INFO from trading modules during a cycle."""

    # Modules whose INFO messages are worth capturing
    KEY_MODULES = {
        'src.strategy.strategy_proposer',
        'src.strategy.autonomous_strategy_manager',
        'src.strategy.portfolio_manager',
        'src.core.trading_scheduler',
        'src.core.order_monitor',
        'src.execution.order_executor',
    }

    # INFO message patterns worth capturing (substring match)
    KEY_PATTERNS = [
        'walk-forward', 'Walk-forward', 'train_sharpe', 'test_sharpe',
        'passed', 'rejected', 'overfitted', 'activated', 'Activated',
        'retired', 'Retired', 'Signal', 'signal', 'Order executed',
        'STAGE', 'Stage', 'Proposals', 'proposals',
        'backtest', 'Backtest', 'Sharpe', 'sharpe',
        'Position duplicate', 'Pending order', 'Symbol limit',
        'Portfolio balance', 'Regime', 'regime',
        'conviction', 'fundamental filter',
        'Opposing SL', 'opposing',
        'failed with error', 'disallowed',
    ]

    def __init__(self, cycle_logger: 'CycleLogger'):
        super().__init__(level=logging.INFO)
        self._cl = cycle_logger
        self._seen: Dict[str, int] = defaultdict(int)

    def emit(self, record: logging.LogRecord):
        try:
            msg = record.getMessage()

            # Always capture ERROR and WARNING
            if record.levelno >= logging.WARNING:
                key = f"{record.name}:{msg[:100]}"
                self._seen[key] += 1
                if self._seen[key] == 1:
                    lvl = "ERROR" if record.levelno >= logging.ERROR else "WARN"
                    src = record.name.replace("src.", "").replace(".", "/")
                    self._cl._write(f"  [{lvl}] {src}: {msg[:250]}")
                return

            # For INFO, only capture from key modules or matching key patterns
            if record.levelno == logging.INFO:
                from_key_module = record.name in self.KEY_MODULES
                matches_pattern = any(p in msg for p in self.KEY_PATTERNS)
                if from_key_module or matches_pattern:
                    key = f"{record.name}:{msg[:100]}"
                    self._seen[key] += 1
                    if self._seen[key] == 1:
                        src = record.name.replace("src.", "").replace(".", "/")
                        self._cl._write(f"  [INFO] {src}: {msg[:250]}")
        except Exception:
            pass

    def flush_counts(self) -> List[str]:
        out = []
        for key, count in self._seen.items():
            if count > 1:
                out.append(f"    (x{count}) {key.split(':', 1)[1][:150]}")
        self._seen.clear()
        return out


class CycleLogger:
    """Writes structured cycle logs to logs/cycles/cycle_history.log."""

    def __init__(self, log_dir: str = "logs/cycles", max_cycles: int = 10):
        self.log_path = Path(log_dir) / "cycle_history.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_cycles = max_cycles
        self._handler: Optional[CycleLogHandler] = None
        self._active = False
        self._completed_cycles = 0  # Track cycles since last trim

    def _rotate_if_needed(self):
        """Trim log to keep only the last N full cycles.

        A cycle is delimited by lines starting with '=' (the separator).
        We find cycle boundaries, count them, and if there are more than
        max_cycles, we keep only the tail.  Runs after each cycle ends
        (not on every write) to avoid I/O overhead.
        """
        pass  # Actual trimming happens in _trim_to_max_cycles, called from end_cycle

    def _trim_to_max_cycles(self):
        """Keep only the last max_cycles full cycles in the log file."""
        if not self.log_path.exists():
            return
        try:
            with open(self.log_path, 'r') as f:
                lines = f.readlines()

            # Find cycle start boundaries (lines that begin with "CYCLE ")
            # Each cycle starts after a "===..." line, with "CYCLE cycle_xxx | date"
            cycle_starts = []
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('CYCLE ') and '|' in stripped:
                    # The separator line is the one before this
                    sep_line = max(0, i - 1)
                    cycle_starts.append(sep_line)

            if len(cycle_starts) <= self.max_cycles:
                return  # Nothing to trim

            # Keep from the Nth-from-last cycle start to the end.
            # Also keep any signal lines before the first kept cycle
            # (they belong to the inter-cycle period).
            keep_from = cycle_starts[-self.max_cycles]

            # Find the nearest preceding separator or signal line
            # to get a clean cut point
            trimmed_lines = lines[keep_from:]
            with open(self.log_path, 'w') as f:
                f.writelines(trimmed_lines)

            removed_cycles = len(cycle_starts) - self.max_cycles
            logger.info(
                f"Trimmed cycle_history.log: removed {removed_cycles} old cycles, "
                f"kept last {self.max_cycles} ({len(trimmed_lines)} lines)"
            )
        except Exception as e:
            logger.warning(f"Failed to trim cycle_history.log: {e}")

    def _write(self, text: str):
        self._rotate_if_needed()
        with open(self.log_path, 'a') as f:
            f.write(text + '\n')

    # --- Cycle lifecycle ---

    def start_cycle(self, cycle_id: str, regime: str = "unknown", confidence: float = 0.0,
                    active_strategies: int = 0, open_positions: int = 0,
                    account_balance: float = 0, account_equity: float = 0):
        self._active = True
        self._write(f"\n{'='*90}")
        self._write(f"CYCLE {cycle_id} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write(f"{'='*90}")
        self._write(f"Market regime: {regime} (confidence: {confidence:.0%})")
        self._write(f"Account: balance=${account_balance:,.0f} equity=${account_equity:,.0f}")
        self._write(f"Portfolio: {active_strategies} active strategies, {open_positions} open positions")
        self._handler = CycleLogHandler(self)
        logging.getLogger().addHandler(self._handler)

    def end_cycle(self, duration_seconds: float, stats: Dict[str, Any]):
        if self._handler:
            repeated = self._handler.flush_counts()
            if repeated:
                self._write(f"\n  [REPEATED WARNINGS/ERRORS]")
                for line in repeated[:30]:
                    self._write(line)
            logging.getLogger().removeHandler(self._handler)
            self._handler = None
        self._write(f"\n  {'~'*70}")
        self._write(f"  CYCLE COMPLETE in {duration_seconds:.0f}s")
        # 2026-05-03: include pre-WF count if present so the footer matches
        # the [PROPOSALS] line at the top of the cycle.
        _pre_wf = stats.get('proposals_pre_wf')
        _generated = stats.get('proposals_generated', 0)
        if _pre_wf is not None and _pre_wf > _generated:
            self._write(
                f"  Proposals: {_pre_wf} candidates → {_generated} fresh "
                f"(DSL={stats.get('template_count', '?')}, AE={stats.get('alpha_edge_count', '?')})"
            )
        else:
            self._write(f"  Proposals: {_generated} "
                         f"(DSL={stats.get('template_count', '?')}, AE={stats.get('alpha_edge_count', '?')})")
        self._write(f"  Walk-forward: {stats.get('bt_passed', '?')}/{stats.get('bt_total', '?')} passed")
        # 2026-05-04: report both BACKTESTED (activated) and DEMO-promoted
        # counts when they differ. `strategies_activated` = passed activation
        # criteria this cycle. `strategies_promoted_to_demo` = subset that
        # got their first order this cycle. In cycles where signals defer
        # (market closed, gate-blocked, pending) the two diverge — hiding
        # the BACKTESTED count (as the previous implementation did) created
        # false "nothing happened" footers.
        _activated = stats.get('strategies_activated', 0)
        _promoted = stats.get('strategies_promoted_to_demo', _activated)
        if _promoted != _activated:
            self._write(
                f"  Activated: {_activated} (→ {_promoted} promoted to DEMO) | "
                f"Retired: {stats.get('strategies_retired', 0)} | "
                f"Total active: {stats.get('total_active', '?')}"
            )
        else:
            self._write(
                f"  Activated: {_activated} | "
                f"Retired: {stats.get('strategies_retired', 0)} | "
                f"Total active: {stats.get('total_active', '?')}"
            )
        self._write(f"  Signals: {stats.get('signals_generated', 0)} -> "
                     f"Orders: {stats.get('orders_submitted', 0)}")
        errors = stats.get('errors', [])
        if errors:
            self._write(f"  ERRORS ({len(errors)}):")
            for err in errors[:10]:
                self._write(f"    ! {str(err)[:200]}")
        self._write(f"{'='*90}\n")
        self._active = False
        self._completed_cycles += 1
        # Trim every 5 cycles to avoid doing file I/O after every single cycle
        if self._completed_cycles % 5 == 0:
            self._trim_to_max_cycles()

    # --- Stage logging ---

    def log_stage(self, stage: str, summary: str, metrics: Dict[str, Any] = None):
        line = f"\n  [{stage}] {summary}"
        if metrics:
            parts = [f"{k}={v}" for k, v in metrics.items()]
            line += f"\n    {', '.join(parts)}"
        self._write(line)

    # --- Proposals & symbols ---

    def log_proposals(self, total: int, dsl: int, alpha_edge: int,
                      wf_passed: int, wf_total: int, pass_rate: float,
                      regime: str = "", direction_split: str = "",
                      pre_wf_total: Optional[int] = None):
        # 2026-05-03: when pre_wf_total is provided (from proposer's
        # _last_pre_wf_count), show it alongside the post-WF `total` so
        # "I asked for 400 and only 28 show up" ambiguity disappears.
        # pre_wf_total = raw proposer output (all candidates entering WF,
        # including cache-hit rejections). total = candidates that survived
        # WF and entered backtest/activation. cached = the delta.
        if pre_wf_total is not None and pre_wf_total > total:
            cached = pre_wf_total - total
            self._write(
                f"\n  [PROPOSALS] {pre_wf_total} candidates → {total} fresh "
                f"(DSL={dsl}, AE={alpha_edge}), {cached} cached from earlier cycles"
            )
        else:
            self._write(f"\n  [PROPOSALS] {total} generated (DSL={dsl}, AE={alpha_edge})")
        if direction_split:
            self._write(f"    Direction: {direction_split}")
        self._write(f"  [WALK-FORWARD] {wf_passed}/{wf_total} passed ({pass_rate:.1f}%)")

    def log_symbol_analysis(self, symbol: str, score: float, volatility: float = 0,
                            trend_strength: float = 0, rsi: float = 0, asset_class: str = ""):
        self._write(f"    {symbol:8s} score={score:.1f} vol={volatility:.3f} "
                     f"trend={trend_strength:.2f} RSI={rsi:.1f} [{asset_class}]")

    # --- Walk-forward details ---

    def log_wf_results(self, results: List[Dict[str, Any]]):
        passed = [r for r in results if r.get('passed')]
        failed = [r for r in results if not r.get('passed')]
        if passed:
            self._write(f"\n  [WF PASSED] {len(passed)} strategies:")
            for r in passed:
                name = r.get('name', '?')[:42]
                sym = r.get('symbol', '?')[:8]
                ts = r.get('train_sharpe', 0)
                tes = r.get('test_sharpe', 0)
                tr_t = r.get('train_trades', 0)
                te_t = r.get('test_trades', 0)
                te_r = r.get('test_return', 0)
                te_wr = r.get('test_win_rate', 0)
                te_dd = r.get('test_drawdown', 0)
                self._write(f"    + {name:42s} {sym:8s} | train: S={ts:.2f} t={tr_t} | "
                             f"test: S={tes:.2f} ret={te_r:.1%} wr={te_wr:.0%} dd={te_dd:.1%} t={te_t}")
        zero = [r for r in failed if r.get('test_trades', 0) == 0 and r.get('train_trades', 0) == 0]
        overfit = [r for r in failed if r.get('overfitted') and r.get('train_trades', 0) > 0]
        # Split the "failed but has trades" bucket into meaningful sub-categories
        has_trades = [r for r in failed if not r.get('overfitted') and r.get('train_trades', 0) > 0 and r.get('test_trades', 0) > 0]
        low_trades = [r for r in has_trades if r.get('test_trades', 0) < 8 and r.get('test_sharpe', 0) >= 0.3]
        low_winrate = [r for r in has_trades if r.get('test_trades', 0) >= 8 and r.get('test_win_rate', 0) < 0.35 and r.get('test_sharpe', 0) >= 0.3]
        low = [r for r in has_trades if r not in low_trades and r not in low_winrate]
        crashed = [r for r in failed if r.get('error')]
        if zero:
            self._write(f"\n  [WF 0-TRADE] {len(zero)} strategies produced 0 trades:")
            for r in zero[:10]:
                self._write(f"    x {r.get('name', '?')[:50]} ({r.get('symbol', '?')})")
        if overfit:
            self._write(f"\n  [WF OVERFITTED] {len(overfit)} strategies:")
            for r in overfit[:10]:
                self._write(f"    x {r.get('name', '?')[:42]} train={r.get('train_sharpe', 0):.2f} test={r.get('test_sharpe', 0):.2f}")
        if low_trades:
            self._write(f"\n  [WF LOW TRADES] {len(low_trades)} below min_trades threshold:")
            for r in low_trades[:10]:
                self._write(f"    x {r.get('name', '?')[:42]} test_S={r.get('test_sharpe', 0):.2f} wr={r.get('test_win_rate', 0):.0%} t={r.get('test_trades', 0)}")
        if low_winrate:
            self._write(f"\n  [WF LOW WINRATE] {len(low_winrate)} below win rate threshold:")
            for r in low_winrate[:10]:
                self._write(f"    x {r.get('name', '?')[:42]} test_S={r.get('test_sharpe', 0):.2f} wr={r.get('test_win_rate', 0):.0%} t={r.get('test_trades', 0)}")
        if low:
            self._write(f"\n  [WF LOW SHARPE] {len(low)} below Sharpe/return threshold:")
            for r in low[:10]:
                self._write(f"    x {r.get('name', '?')[:42]} test_S={r.get('test_sharpe', 0):.2f} wr={r.get('test_win_rate', 0):.0%}")
        if crashed:
            self._write(f"\n  [WF CRASHED] {len(crashed)} errors:")
            for r in crashed[:5]:
                self._write(f"    x {r.get('name', '?')[:42]} -- {r.get('error', '?')[:100]}")

    # --- Template stats ---

    def log_template_stats(self, template_results: Dict[str, Dict[str, Any]]):
        if not template_results:
            return
        self._write(f"\n  [TEMPLATE PERFORMANCE]")
        sorted_t = sorted(template_results.items(), key=lambda x: x[1].get('pass_rate', 0), reverse=True)
        for name, s in sorted_t[:20]:
            total = s.get('total', 0)
            passed = s.get('passed', 0)
            avg_s = s.get('avg_test_sharpe', 0)
            rate = (passed / total * 100) if total > 0 else 0
            self._write(f"    {name:40s} {passed}/{total} passed ({rate:.0f}%) avg_S={avg_s:.2f}")

    # --- Activation & retirement ---

    def log_activation(self, activated: List[Dict[str, Any]], rejected: List[Dict[str, Any]] = None):
        self._write(f"\n  [ACTIVATION] {len(activated)} activated:")
        for s in activated:
            name = s.get('name', '?')[:42]
            sharpe = s.get('sharpe', 0)
            wr = s.get('win_rate', 0)
            trades = s.get('trades', 0)
            dd = s.get('drawdown', 0)
            syms = s.get('symbols', [])
            sym = syms[0] if syms else '?'
            ae = s.get('is_alpha_edge', False)
            label = 'AE' if ae else 'DSL'
            self._write(f"    + [{label}] {name:42s} {sym:8s} S={sharpe:.2f} wr={wr:.0%} dd={dd:.1%} t={trades}")
        if rejected:
            self._write(f"\n  [ACTIVATION REJECTED] {len(rejected)}:")
            for s in rejected[:20]:
                name = s.get('name', '?')[:42]
                reason = s.get('reason', '?')
                sharpe = s.get('sharpe', 0)
                wr = s.get('win_rate', 0)
                self._write(f"    x {name:42s} S={sharpe:.2f} wr={wr:.0%} -- {reason}")

    def log_retirement(self, retired: List[Dict[str, Any]]):
        if retired:
            self._write(f"\n  [RETIREMENT] {len(retired)} retired:")
            for s in retired:
                self._write(f"    v {s.get('name', '?')[:42]} -- {s.get('reason', '?')}")

    # --- Signals & orders ---

    def log_signals(self, generated: int, coordinated: int, rejected: int,
                    orders_submitted: int, orders_filled: int = 0,
                    rejection_reasons: Dict[str, int] = None):
        self._write(f"\n  [SIGNALS] {generated} generated -> {coordinated} coordinated -> {rejected} rejected")
        if rejection_reasons:
            for reason, count in sorted(rejection_reasons.items(), key=lambda x: -x[1]):
                self._write(f"    filtered: {reason} (x{count})")
        self._write(f"  [ORDERS] {orders_submitted} submitted, {orders_filled} filled")

    def log_order_detail(self, symbol: str, side: str, quantity: float, price: float,
                         strategy_name: str = "", status: str = "", slippage: float = 0):
        slip = f" slip={slippage:.4f}" if slippage else ""
        self._write(f"    -> {side:4s} {symbol:8s} qty={quantity:.2f} @{price:.2f} "
                     f"[{strategy_name[:30]}] {status}{slip}")

    def log_signal_rejection(self, symbol: str, strategy_name: str, reason: str):
        self._write(f"    x {symbol:8s} [{strategy_name[:30]}] -- {reason}")

    # --- Portfolio state ---

    def log_portfolio_state(self, long_exposure_pct: float = 0, short_exposure_pct: float = 0,
                            sector_exposures: Dict[str, float] = None,
                            total_unrealized_pnl: float = 0, positions_count: int = 0,
                            position_details: List[Dict] = None):
        self._write(f"\n  [PORTFOLIO] {positions_count} positions | unrealized P&L: ${total_unrealized_pnl:,.2f}")
        self._write(f"    Exposure: {long_exposure_pct:.1f}% long, {short_exposure_pct:.1f}% short")
        if sector_exposures:
            top = sorted(sector_exposures.items(), key=lambda x: -x[1])[:5]
            self._write(f"    Top sectors: {', '.join(f'{s}={p:.1f}%' for s, p in top)}")
        # Per-position P&L breakdown for debugging profitability
        if position_details:
            winners = [p for p in position_details if p.get('pnl', 0) > 0]
            losers = [p for p in position_details if p.get('pnl', 0) < 0]
            flat = [p for p in position_details if p.get('pnl', 0) == 0]
            self._write(f"    Winners: {len(winners)} | Losers: {len(losers)} | Flat: {len(flat)}")
            # Show top 5 by absolute P&L
            sorted_pos = sorted(position_details, key=lambda p: abs(p.get('pnl', 0)), reverse=True)
            for p in sorted_pos[:5]:
                side = p.get('side', '?')
                symbol = p.get('symbol', '?')
                pnl = p.get('pnl', 0)
                days = p.get('days_held', 0)
                strategy = p.get('strategy', '')[:30]
                sign = '+' if pnl >= 0 else ''
                self._write(f"      {side:5s} {symbol:8s} {sign}${pnl:>8,.2f} ({days}d) {strategy}")

    # --- Data quality ---

    def log_data_quality(self, symbols_checked: int, symbols_ok: int,
                         issues: List[Dict[str, Any]] = None):
        self._write(f"\n  [DATA QUALITY] {symbols_ok}/{symbols_checked} symbols OK")
        if issues:
            for issue in issues[:15]:
                self._write(f"    ! {issue.get('symbol', '?'):8s} {issue.get('issue', '?')}")

    # --- Errors ---

    def log_error(self, stage: str, error: str):
        self._write(f"  [ERROR] {stage}: {error[:250]}")

    # --- Hourly signal cycle ---

    def log_signal_cycle(self, duration_seconds: float, strategies: int,
                         signals: int, orders: int, mode: str = "1h",
                         signal_details: list = None,
                         rejection_details: list = None,
                         order_details: list = None):
        """Log a scheduler signal cycle with optional per-signal breakdown.

        signal_details: list of dicts with keys: symbol, strategy, side, confidence
        rejection_details: list of dicts with keys: symbol, strategy, reason
        order_details: list of dicts with keys: symbol, side, size, strategy
        """
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._write(
            f"[SIGNAL-{mode.upper()}] {ts} | {duration_seconds:.0f}s | "
            f"{strategies} strategies | {signals} signals | {orders} orders"
        )
        if signal_details:
            for s in signal_details:
                sym = s.get('symbol', '?')
                strat = s.get('strategy', '?')[:35]
                side = s.get('side', '?')
                conf = s.get('confidence', 0)
                self._write(f"  -> {side:10s} {sym:8s} conf={conf:.2f}  [{strat}]")
        if rejection_details:
            for r in rejection_details[:20]:
                sym = r.get('symbol', '?')
                strat = r.get('strategy', '?')[:35]
                reason = r.get('reason', '?')[:80]
                self._write(f"  x  {sym:8s} [{strat}] -- {reason}")
        if order_details:
            for o in order_details:
                sym = o.get('symbol', '?')
                side = o.get('side', '?')
                size = o.get('size', 0)
                strat = o.get('strategy', '?')[:35]
                self._write(f"  ✓  {side:10s} {sym:8s} ${size:,.0f}  [{strat}]")


def get_cycle_logger() -> CycleLogger:
    global _cycle_logger
    if _cycle_logger is None:
        _cycle_logger = CycleLogger()
    return _cycle_logger
