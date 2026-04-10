#!/usr/bin/env python3
"""
Task 6.4: Validate DSL Rules Produce Signals on Current Market Data

For each DEMO strategy:
- Run signal generation and evaluate entry/exit conditions
- Count entry/exit signals in the last 30 days
- Flag dormant strategies (0 signals in 30 days)
- Produce a summary report

Acceptance: At least 5 of 27 DEMO strategies generate entry signals on current market data.
"""

import sys
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

import pandas as pd

# Setup logging - reduce noise from libraries
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# Only show our own logs at INFO level
logger = logging.getLogger("validate_dsl")
logger.setLevel(logging.INFO)
# Suppress verbose strategy engine logs during bulk validation
logging.getLogger("src.strategy.strategy_engine").setLevel(logging.WARNING)
logging.getLogger("src.data").setLevel(logging.WARNING)
logging.getLogger("src.strategy.trading_dsl").setLevel(logging.WARNING)
logging.getLogger("src.strategy.indicator_library").setLevel(logging.WARNING)


def load_demo_strategies():
    """Load all DEMO strategies from the database."""
    from src.models.database import get_database
    from src.models.orm import StrategyORM
    from src.models.enums import StrategyStatus

    db = get_database()
    session = db.get_session()
    try:
        strategies_orm = session.query(StrategyORM).filter(
            StrategyORM.status == StrategyStatus.DEMO.value
        ).all()
        return strategies_orm
    finally:
        session.close()


def orm_to_strategy(orm_strategy):
    """Convert ORM strategy to dataclass."""
    from src.models.dataclasses import Strategy, RiskConfig, PerformanceMetrics
    from src.models.enums import StrategyStatus

    rules = orm_strategy.rules if isinstance(orm_strategy.rules, dict) else json.loads(orm_strategy.rules or '{}')
    symbols = orm_strategy.symbols if isinstance(orm_strategy.symbols, list) else json.loads(orm_strategy.symbols or '[]')
    risk_data = orm_strategy.risk_params if isinstance(orm_strategy.risk_params, dict) else json.loads(orm_strategy.risk_params or '{}')
    perf_data = orm_strategy.performance if isinstance(orm_strategy.performance, dict) else json.loads(orm_strategy.performance or '{}')

    return Strategy(
        id=orm_strategy.id,
        name=orm_strategy.name,
        description=orm_strategy.description or "",
        status=StrategyStatus(orm_strategy.status) if isinstance(orm_strategy.status, str) else orm_strategy.status,
        rules=rules,
        symbols=symbols,
        risk_params=RiskConfig(
            max_position_size_pct=risk_data.get('max_position_size_pct', 0.1),
            max_exposure_pct=risk_data.get('max_exposure_pct', 0.5),
            max_daily_loss_pct=risk_data.get('max_daily_loss_pct', 0.03),
            max_drawdown_pct=risk_data.get('max_drawdown_pct', 0.1),
            position_risk_pct=risk_data.get('position_risk_pct', 0.01),
            stop_loss_pct=risk_data.get('stop_loss_pct', 0.02),
            take_profit_pct=risk_data.get('take_profit_pct', 0.04),
        ),
        created_at=orm_strategy.created_at or datetime.now(),
        activated_at=orm_strategy.activated_at,
        retired_at=orm_strategy.retired_at,
        performance=PerformanceMetrics(
            total_return=perf_data.get('total_return', 0.0),
            sharpe_ratio=perf_data.get('sharpe_ratio', 0.0),
            sortino_ratio=perf_data.get('sortino_ratio', 0.0),
            max_drawdown=perf_data.get('max_drawdown', 0.0),
            win_rate=perf_data.get('win_rate', 0.0),
            avg_win=perf_data.get('avg_win', 0.0),
            avg_loss=perf_data.get('avg_loss', 0.0),
            total_trades=perf_data.get('total_trades', 0),
        ),
    )


def evaluate_strategy_signals(strategy_engine, strategy, data_cache: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """
    Evaluate a single strategy's DSL rules against current market data.
    
    Returns a dict with:
    - latest_entry: bool (entry condition on latest data point)
    - latest_exit: bool (exit condition on latest data point)
    - entry_signals_30d: int (entry signals in last 30 days)
    - exit_signals_30d: int (exit signals in last 30 days)
    - is_dormant: bool
    - dormant_reason: str or None
    - error: str or None
    """
    result = {
        "name": strategy.name,
        "symbols": strategy.symbols,
        "entry_conditions": strategy.rules.get("entry_conditions", []),
        "exit_conditions": strategy.rules.get("exit_conditions", []),
        "indicators": strategy.rules.get("indicators", []),
        "latest_entry": False,
        "latest_exit": False,
        "entry_signals_30d": 0,
        "exit_signals_30d": 0,
        "is_dormant": True,
        "dormant_reason": None,
        "error": None,
        "indicator_values": {},
    }

    for symbol in strategy.symbols:
        try:
            # Get or fetch data
            if symbol not in data_cache:
                end = datetime.now()
                start = end - timedelta(days=220)  # 120 + 100 warmup
                data_list = strategy_engine.market_data.get_historical_data(
                    symbol, start, end, interval="1d", prefer_yahoo=True
                )
                if not data_list or len(data_list) < 50:
                    result["error"] = f"Insufficient data for {symbol}: {len(data_list) if data_list else 0} points"
                    result["dormant_reason"] = "insufficient_data"
                    continue

                df = pd.DataFrame([
                    {
                        "timestamp": d.timestamp,
                        "open": d.open,
                        "high": d.high,
                        "low": d.low,
                        "close": d.close,
                        "volume": d.volume,
                    }
                    for d in data_list
                ])
                df.set_index("timestamp", inplace=True)
                data_cache[symbol] = df
            
            df = data_cache[symbol]

            # Calculate indicators
            indicators = strategy_engine._calculate_indicators_from_strategy(strategy, df, symbol)
            if not indicators:
                result["error"] = f"No indicators calculated for {symbol}"
                result["dormant_reason"] = "no_indicators"
                continue

            # Parse rules to get entry/exit boolean series
            close = df["close"]
            high = df["high"]
            low = df["low"]

            entries, exits = strategy_engine._parse_strategy_rules(
                close, high, low, indicators, strategy.rules
            )

            if len(entries) == 0 or len(exits) == 0:
                result["error"] = f"No signal data produced for {symbol}"
                result["dormant_reason"] = "no_signal_data"
                continue

            # Latest data point evaluation
            result["latest_entry"] = bool(entries.iloc[-1])
            result["latest_exit"] = bool(exits.iloc[-1])

            # Count signals in last 30 days
            # Use the last 30 data points (trading days) to avoid timezone comparison issues
            n_recent = min(30, len(entries))
            recent_entries = entries.iloc[-n_recent:]
            recent_exits = exits.iloc[-n_recent:]

            result["entry_signals_30d"] = int(recent_entries.sum())
            result["exit_signals_30d"] = int(recent_exits.sum())

            # Capture latest indicator values for diagnostics
            for key, values in indicators.items():
                if len(values) > 0 and not values.isna().all():
                    latest_val = values.iloc[-1]
                    if not pd.isna(latest_val):
                        result["indicator_values"][key] = round(float(latest_val), 4)

            result["indicator_values"]["price"] = round(float(close.iloc[-1]), 2)

            # Determine dormancy
            if result["entry_signals_30d"] > 0 or result["exit_signals_30d"] > 0:
                result["is_dormant"] = False
                result["dormant_reason"] = None
            else:
                result["dormant_reason"] = "no_signals_30d"

        except Exception as e:
            result["error"] = str(e)
            result["dormant_reason"] = f"error: {str(e)[:100]}"

    return result


def analyze_dormancy(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze why strategies are dormant and suggest fixes."""
    dormant = [r for r in results if r["is_dormant"]]
    active = [r for r in results if not r["is_dormant"]]
    
    # Categorize dormant reasons
    reason_counts = {}
    for r in dormant:
        reason = r.get("dormant_reason", "unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    
    # Analyze entry condition restrictiveness
    restrictive_conditions = []
    for r in dormant:
        for cond in r.get("entry_conditions", []):
            if "RSI(14) < 25" in cond:
                restrictive_conditions.append(("RSI < 25 (very oversold)", r["name"]))
            elif "RSI(14) < 30" in cond:
                restrictive_conditions.append(("RSI < 30 (oversold)", r["name"]))
            elif "STOCH(14) < 20" in cond:
                restrictive_conditions.append(("STOCH < 20 (extreme oversold)", r["name"]))
            elif "BB_LOWER" in cond and "RSI" in cond:
                restrictive_conditions.append(("BB_LOWER + RSI combo (very restrictive)", r["name"]))
    
    return {
        "total": len(results),
        "active_count": len(active),
        "dormant_count": len(dormant),
        "dormant_pct": len(dormant) / len(results) * 100 if results else 0,
        "reason_counts": reason_counts,
        "restrictive_conditions": restrictive_conditions,
    }


def print_report(results: List[Dict[str, Any]], analysis: Dict[str, Any]):
    """Print a formatted validation report."""
    print("\n" + "=" * 100)
    print("TASK 6.4: DSL SIGNAL VALIDATION REPORT")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    # Summary
    print(f"\n{'─' * 100}")
    print(f"SUMMARY: {analysis['active_count']}/{analysis['total']} strategies generate signals, "
          f"{analysis['dormant_count']}/{analysis['total']} are dormant "
          f"({analysis['dormant_pct']:.0f}% dormant)")
    print(f"{'─' * 100}")

    # Detailed per-strategy results
    print(f"\n{'─' * 100}")
    print(f"{'Strategy':<55} {'Entry Today':<12} {'Exit Today':<11} {'Entry 30d':<10} {'Exit 30d':<9} {'Status'}")
    print(f"{'─' * 100}")

    for r in sorted(results, key=lambda x: x["entry_signals_30d"], reverse=True):
        entry_today = "✅ YES" if r["latest_entry"] else "❌ NO"
        exit_today = "✅ YES" if r["latest_exit"] else "❌ NO"
        status = "🟢 ACTIVE" if not r["is_dormant"] else "🔴 DORMANT"
        name = r["name"][:53]
        print(f"{name:<55} {entry_today:<12} {exit_today:<11} {r['entry_signals_30d']:<10} {r['exit_signals_30d']:<9} {status}")

    # Dormant strategy details
    dormant = [r for r in results if r["is_dormant"]]
    if dormant:
        print(f"\n{'─' * 100}")
        print("DORMANT STRATEGY DETAILS:")
        print(f"{'─' * 100}")
        for r in dormant:
            print(f"\n  📋 {r['name']}")
            print(f"     Symbols: {r['symbols']}")
            print(f"     Entry: {r['entry_conditions']}")
            print(f"     Exit: {r['exit_conditions']}")
            print(f"     Reason: {r['dormant_reason']}")
            if r.get("error"):
                print(f"     Error: {r['error']}")
            if r.get("indicator_values"):
                vals = r["indicator_values"]
                print(f"     Current indicators: ", end="")
                parts = []
                for k, v in sorted(vals.items()):
                    parts.append(f"{k}={v}")
                print(", ".join(parts))

    # Dormancy analysis
    if analysis["dormant_pct"] > 50:
        print(f"\n{'─' * 100}")
        print("⚠️  WARNING: >50% of strategies are dormant!")
        print(f"{'─' * 100}")
        print("\nDormancy reasons:")
        for reason, count in analysis["reason_counts"].items():
            print(f"  - {reason}: {count} strategies")
        
        if analysis["restrictive_conditions"]:
            print("\nRestrictive entry conditions found:")
            for cond, name in analysis["restrictive_conditions"][:10]:
                print(f"  - {cond} ({name})")
        
        print("\nRECOMMENDATION: Entry conditions are too restrictive for current market conditions.")
        print("Most strategies require RSI < 25 (deeply oversold) which rarely occurs in trending markets.")
        print("Consider relaxing thresholds or adding momentum-based strategies.")

    # Acceptance criteria check
    entry_today_count = sum(1 for r in results if r["latest_entry"])
    entry_30d_count = sum(1 for r in results if r["entry_signals_30d"] > 0)
    
    print(f"\n{'=' * 100}")
    print("ACCEPTANCE CRITERIA CHECK")
    print(f"{'=' * 100}")
    print(f"Strategies with entry signal TODAY: {entry_today_count}/{len(results)}")
    print(f"Strategies with entry signals in last 30 days: {entry_30d_count}/{len(results)}")
    print(f"Requirement: At least 5 strategies generate entry signals on current market data")
    
    # Use 30-day window for acceptance (more realistic than single day)
    if entry_30d_count >= 5:
        print(f"\n✅ ACCEPTANCE CRITERIA MET: {entry_30d_count} strategies generated entry signals in last 30 days")
        return True
    else:
        print(f"\n❌ ACCEPTANCE CRITERIA NOT MET: Only {entry_30d_count} strategies generated entry signals")
        print("   Action needed: Relax entry thresholds or add new strategy templates")
        return False


def main():
    """Main validation function."""
    print("Initializing components...")
    
    from src.models.enums import TradingMode
    from src.strategy.strategy_engine import StrategyEngine
    from src.data.market_data_manager import MarketDataManager
    from src.llm.llm_service import LLMService
    from src.api.etoro_client import EToroAPIClient
    from src.core.config import get_config

    config = get_config()
    credentials = config.load_credentials(TradingMode.DEMO)
    etoro_client = EToroAPIClient(
        public_key=credentials["public_key"],
        user_key=credentials["user_key"],
        mode=TradingMode.DEMO,
    )
    market_data = MarketDataManager(etoro_client)
    llm_service = LLMService()
    strategy_engine = StrategyEngine(llm_service, market_data, None)

    # Load DEMO strategies
    print("Loading DEMO strategies...")
    strategies_orm = load_demo_strategies()
    print(f"Found {len(strategies_orm)} DEMO strategies")

    if not strategies_orm:
        print("❌ No DEMO strategies found. Cannot validate.")
        return False

    # Convert to dataclass
    strategies = [orm_to_strategy(s) for s in strategies_orm]

    # Shared data cache (fetch each symbol once)
    data_cache: Dict[str, pd.DataFrame] = {}

    # Pre-fetch data for all unique symbols
    unique_symbols = set()
    for s in strategies:
        unique_symbols.update(s.symbols)
    
    print(f"\nPre-fetching data for {len(unique_symbols)} unique symbols: {sorted(unique_symbols)}")
    end = datetime.now()
    start = end - timedelta(days=220)
    
    for symbol in sorted(unique_symbols):
        t0 = time.time()
        try:
            data_list = market_data.get_historical_data(
                symbol, start, end, interval="1d", prefer_yahoo=True
            )
            if data_list and len(data_list) >= 50:
                df = pd.DataFrame([
                    {
                        "timestamp": d.timestamp,
                        "open": d.open,
                        "high": d.high,
                        "low": d.low,
                        "close": d.close,
                        "volume": d.volume,
                    }
                    for d in data_list
                ])
                df.set_index("timestamp", inplace=True)
                data_cache[symbol] = df
                elapsed = time.time() - t0
                print(f"  ✅ {symbol}: {len(df)} data points ({elapsed:.1f}s)")
            else:
                print(f"  ❌ {symbol}: insufficient data ({len(data_list) if data_list else 0} points)")
        except Exception as e:
            print(f"  ❌ {symbol}: error fetching data: {e}")

    # Evaluate each strategy
    print(f"\nEvaluating {len(strategies)} strategies...")
    results = []
    
    for i, strategy in enumerate(strategies, 1):
        try:
            result = evaluate_strategy_signals(strategy_engine, strategy, data_cache)
            results.append(result)
            status = "🟢" if not result["is_dormant"] else "🔴"
            entry_str = f"entry_30d={result['entry_signals_30d']}"
            print(f"  {status} [{i}/{len(strategies)}] {strategy.name}: {entry_str}")
        except Exception as e:
            results.append({
                "name": strategy.name,
                "symbols": strategy.symbols,
                "entry_conditions": strategy.rules.get("entry_conditions", []),
                "exit_conditions": strategy.rules.get("exit_conditions", []),
                "indicators": strategy.rules.get("indicators", []),
                "latest_entry": False,
                "latest_exit": False,
                "entry_signals_30d": 0,
                "exit_signals_30d": 0,
                "is_dormant": True,
                "dormant_reason": f"error: {str(e)[:100]}",
                "error": str(e),
                "indicator_values": {},
            })
            print(f"  🔴 [{i}/{len(strategies)}] {strategy.name}: ERROR - {e}")

    # Analyze and report
    analysis = analyze_dormancy(results)
    passed = print_report(results, analysis)
    
    return passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
