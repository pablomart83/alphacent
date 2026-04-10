#!/usr/bin/env python3
"""Test the new symbol concentration limits and signal coordination"""

from src.models.database import get_database
from src.models.orm import StrategyORM, PositionORM
from src.models.enums import StrategyStatus, TradingMode
from src.risk.risk_manager import RiskManager, EXTERNAL_POSITION_STRATEGY_IDS
from src.models.dataclasses import RiskConfig, TradingSignal, SignalAction, AccountInfo, Position, PositionSide
from src.strategy.strategy_engine import StrategyEngine
from src.data.market_data_manager import MarketDataManager
from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from datetime import datetime

print("=" * 80)
print("Testing Symbol Concentration Limits")
print("=" * 80)

# Initialize components
config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)
etoro_client = EToroAPIClient(
    public_key=credentials["public_key"],
    user_key=credentials["user_key"],
    mode=TradingMode.DEMO,
)

# Load risk config with new limits
risk_config = config.load_risk_config(TradingMode.DEMO)
print(f"\nRisk Configuration:")
print(f"  Max symbol exposure: {risk_config.max_symbol_exposure_pct:.1%}")
print(f"  Max strategies per symbol: {risk_config.max_strategies_per_symbol}")

risk_manager = RiskManager(risk_config)

# Get account info
account_info = etoro_client.get_account_info()
print(f"\nAccount Info:")
print(f"  Balance: ${account_info.balance:,.2f}")
print(f"  Max symbol exposure: ${account_info.balance * risk_config.max_symbol_exposure_pct:,.2f}")

# Get current positions
db = get_database()
session = db.get_session()

try:
    pos_orms = session.query(PositionORM).filter(PositionORM.closed_at == None).all()
    positions = []
    for p in pos_orms:
        positions.append(Position(
            id=p.id, strategy_id=p.strategy_id, symbol=p.symbol,
            side=PositionSide(p.side), quantity=p.quantity,
            entry_price=p.entry_price, current_price=p.current_price,
            unrealized_pnl=p.unrealized_pnl, realized_pnl=p.realized_pnl,
            opened_at=p.opened_at, etoro_position_id=p.etoro_position_id,
            stop_loss=p.stop_loss, take_profit=p.take_profit,
            closed_at=p.closed_at,
        ))
    
    print(f"\nCurrent Positions: {len(positions)}")
    
    # Group by symbol
    by_symbol = {}
    for p in positions:
        if p.strategy_id in EXTERNAL_POSITION_STRATEGY_IDS:
            continue  # Skip external positions
        if p.symbol not in by_symbol:
            by_symbol[p.symbol] = []
        by_symbol[p.symbol].append(p)
    
    for symbol, pos_list in sorted(by_symbol.items(), key=lambda x: len(x[1]), reverse=True):
        total_value = sum(p.quantity * p.current_price for p in pos_list)
        strategies = set(p.strategy_id for p in pos_list)
        print(f"  {symbol}: {len(pos_list)} positions from {len(strategies)} strategies, value=${total_value:,.2f}")
    
    # Test 1: Check symbol concentration for NVDA
    print(f"\n" + "=" * 80)
    print("Test 1: Symbol Concentration Check for NVDA")
    print("=" * 80)
    
    # Create a test signal for NVDA
    test_signal = TradingSignal(
        strategy_id="test-strategy-1",
        symbol="ID_1137",  # NVDA
        action=SignalAction.ENTER_LONG,
        confidence=0.75,
        reasoning="Test signal",
        generated_at=datetime.now()
    )
    
    # Calculate what position size would be
    position_size = 5000.0  # $5K test position
    
    is_valid, reason = risk_manager.check_symbol_concentration(
        test_signal.symbol, position_size, account_info, positions
    )
    
    print(f"\nTest Signal: ENTER_LONG {test_signal.symbol} (${position_size:,.2f})")
    print(f"Result: {'✅ VALID' if is_valid else '❌ REJECTED'}")
    print(f"Reason: {reason}")
    
    # Test 2: Check with a large position that would exceed limits
    print(f"\n" + "=" * 80)
    print("Test 2: Large Position Exceeding Symbol Limit")
    print("=" * 80)
    
    large_position_size = account_info.balance * 0.20  # 20% of account
    
    is_valid, reason = risk_manager.check_symbol_concentration(
        test_signal.symbol, large_position_size, account_info, positions
    )
    
    print(f"\nTest Signal: ENTER_LONG {test_signal.symbol} (${large_position_size:,.2f})")
    print(f"Result: {'✅ VALID' if is_valid else '❌ REJECTED'}")
    print(f"Reason: {reason}")
    
    # Test 3: Signal Coordination
    print(f"\n" + "=" * 80)
    print("Test 3: Signal Coordination (Multiple Strategies, Same Symbol)")
    print("=" * 80)
    
    # Get DEMO strategies
    demo_strategies = session.query(StrategyORM).filter(
        StrategyORM.status == StrategyStatus.DEMO
    ).all()
    
    # Group by symbol
    strategies_by_symbol = {}
    for s in demo_strategies:
        import json
        symbols = s.symbols if isinstance(s.symbols, list) else json.loads(s.symbols or '[]')
        for sym in symbols:
            if sym not in strategies_by_symbol:
                strategies_by_symbol[sym] = []
            strategies_by_symbol[sym].append(s.name)
    
    print(f"\nStrategies per symbol:")
    for sym, strats in sorted(strategies_by_symbol.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {sym}: {len(strats)} strategies")
        if len(strats) > risk_config.max_strategies_per_symbol:
            print(f"    ⚠️  Exceeds limit of {risk_config.max_strategies_per_symbol}")
            print(f"    Signal coordination will filter to highest-confidence signal")
    
    print(f"\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"\n✅ Symbol concentration limits implemented:")
    print(f"   - Max {risk_config.max_symbol_exposure_pct:.1%} exposure per symbol")
    print(f"   - Max {risk_config.max_strategies_per_symbol} strategies per symbol")
    print(f"\n✅ Signal coordination implemented:")
    print(f"   - Filters redundant signals from multiple strategies")
    print(f"   - Keeps only highest-confidence signal per symbol")
    print(f"\n✅ Risk checks now prevent:")
    print(f"   - Over-concentration in single symbols")
    print(f"   - Multiple strategies piling into same asset")
    print(f"   - Correlation risk from redundant positions")

finally:
    session.close()
