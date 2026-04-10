#!/usr/bin/env python3
"""
Test if signal generation is working for DEMO strategies.
"""

import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_signal_generation():
    """Test signal generation for one DEMO strategy."""
    
    print("=" * 80)
    print("SIGNAL GENERATION TEST")
    print("=" * 80)
    
    try:
        # Import components
        from src.models.database import get_database
        from src.models.orm import StrategyORM
        from src.models.enums import StrategyStatus, TradingMode
        from src.strategy.strategy_engine import StrategyEngine
        from src.data.market_data_manager import MarketDataManager
        from src.llm.llm_service import LLMService
        from src.api.etoro_client import EToroAPIClient
        from src.core.config import get_config
        from src.models.dataclasses import Strategy, RiskConfig, PerformanceMetrics
        import json
        
        # Initialize components
        config = get_config()
        credentials = config.load_credentials(TradingMode.DEMO)
        etoro_client = EToroAPIClient(
            public_key=credentials["public_key"],
            user_key=credentials["user_key"],
            mode=TradingMode.DEMO
        )
        
        market_data = MarketDataManager(etoro_client)
        llm_service = LLMService()
        strategy_engine = StrategyEngine(llm_service, market_data, None)
        
        # Get one DEMO strategy
        db = get_database()
        session = db.get_session()
        
        strategy_orm = session.query(StrategyORM).filter(
            StrategyORM.status == StrategyStatus.DEMO.value
        ).first()
        
        if not strategy_orm:
            print("❌ No DEMO strategies found")
            return False
        
        print(f"\n✅ Testing strategy: {strategy_orm.name}")
        print(f"   Symbols: {strategy_orm.symbols}")
        print(f"   Rules: {strategy_orm.rules[:200]}...")
        
        # Convert to dataclass
        strategy = Strategy(
            id=strategy_orm.id,
            name=strategy_orm.name,
            description=strategy_orm.description,
            status=StrategyStatus(strategy_orm.status),
            rules=json.loads(strategy_orm.rules) if strategy_orm.rules else {},
            symbols=json.loads(strategy_orm.symbols) if strategy_orm.symbols else [],
            risk_params=RiskConfig(
                max_position_size_pct=0.1,
                max_exposure_pct=0.5,
                max_daily_loss_pct=0.03,
                max_drawdown_pct=0.1,
                position_risk_pct=0.01,
                stop_loss_pct=0.02,
                take_profit_pct=0.04
            ),
            created_at=strategy_orm.created_at,
            activated_at=strategy_orm.activated_at,
            retired_at=strategy_orm.retired_at,
            performance=PerformanceMetrics(
                total_return=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                total_trades=0
            )
        )
        
        # Try to generate signals
        print(f"\n📡 Generating signals...")
        signals = strategy_engine.generate_signals(strategy)
        
        print(f"\n✅ Signal generation completed")
        print(f"   Signals generated: {len(signals)}")
        
        if signals:
            print(f"\n🎯 SIGNALS FOUND:")
            for i, signal in enumerate(signals, 1):
                print(f"\n   Signal {i}:")
                print(f"   - Symbol: {signal.symbol}")
                print(f"   - Action: {signal.action.value}")
                print(f"   - Confidence: {signal.confidence:.2f}")
                print(f"   - Reasoning: {signal.reasoning}")
                print(f"   - Indicators: {signal.indicators}")
        else:
            print(f"\n⏳ No signals generated")
            print(f"   This means current market conditions don't meet entry criteria")
            print(f"   Entry conditions: {strategy.rules.get('entry_conditions', [])}")
            print(f"\n   Let's check current indicator values:")
            
            # Get current market data
            for symbol in strategy.symbols:
                try:
                    print(f"\n   {symbol} current data:")
                    data = market_data.get_historical_data(symbol, days=30, prefer_yahoo=True)
                    if data is not None and not data.empty:
                        latest = data.iloc[-1]
                        print(f"   - Close: ${latest['close']:.2f}")
                        if 'rsi_14' in data.columns:
                            print(f"   - RSI(14): {latest['rsi_14']:.2f}")
                        if 'sma_20' in data.columns:
                            print(f"   - SMA(20): ${latest['sma_20']:.2f}")
                        if 'bb_upper' in data.columns:
                            print(f"   - BB Upper: ${latest['bb_upper']:.2f}")
                            print(f"   - BB Lower: ${latest['bb_lower']:.2f}")
                except Exception as e:
                    print(f"   - Error getting data: {e}")
        
        session.close()
        return True
        
    except Exception as e:
        logger.error(f"Error testing signal generation: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = test_signal_generation()
    sys.exit(0 if success else 1)
