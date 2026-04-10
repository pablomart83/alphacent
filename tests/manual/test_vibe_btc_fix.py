#!/usr/bin/env python3
"""Test vibe coding with BTC fix"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.llm.llm_service import LLMService
from src.execution.order_executor import OrderExecutor
from src.api.etoro_client import EToroAPIClient
from src.data.market_hours_manager import MarketHoursManager
from src.core.config import get_config
from src.models import TradingMode, SignalAction, TradingSignal
from datetime import datetime

def test_vibe_btc():
    print("=" * 70)
    print("Testing Vibe Coding with BTC Fix")
    print("=" * 70)
    
    # Load credentials
    config = get_config()
    creds = config.load_credentials(TradingMode.DEMO)
    
    client = EToroAPIClient(creds["public_key"], creds["user_key"], TradingMode.DEMO)
    market_hours = MarketHoursManager()
    order_executor = OrderExecutor(client, market_hours)
    llm_service = LLMService()
    
    # Test 1: Vibe code for BTC
    print("\n1. Translating 'buy $100 of BTC'...")
    try:
        command = llm_service.translate_vibe_code("buy $100 of BTC")
        print(f"   ✅ Translation successful:")
        print(f"      Symbol: {command.symbol}")
        print(f"      Quantity: ${command.quantity:.2f}")
        
        # Try to execute it
        print(f"\n   Attempting to execute order...")
        signal = TradingSignal(
            strategy_id="manual",
            symbol=command.symbol,
            action=SignalAction.ENTER_LONG,
            confidence=1.0,
            reason="Manual vibe code",
            generated_at=datetime.now()
        )
        
        order = order_executor.execute_signal(signal, command.quantity)
        print(f"   ❌ Order was accepted (shouldn't happen!)")
        
    except Exception as e:
        print(f"   ✅ Order blocked:")
        print(f"      {e}")
    
    # Test 2: Vibe code for AAPL
    print("\n2. Translating 'buy $100 of AAPL'...")
    try:
        command = llm_service.translate_vibe_code("buy $100 of AAPL")
        print(f"   ✅ Translation successful:")
        print(f"      Symbol: {command.symbol}")
        print(f"      Quantity: ${command.quantity:.2f}")
        
        print(f"\n   Attempting to execute order...")
        signal = TradingSignal(
            strategy_id="manual",
            symbol=command.symbol,
            action=SignalAction.ENTER_LONG,
            confidence=1.0,
            reason="Manual vibe code",
            generated_at=datetime.now()
        )
        
        order = order_executor.execute_signal(signal, command.quantity)
        print(f"   ✅ AAPL order accepted! ID: {order.id}")
        
    except Exception as e:
        print(f"   ❌ Order failed: {e}")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    test_vibe_btc()
