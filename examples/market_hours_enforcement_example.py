"""
Example: Market Hours Enforcement for Orders

This example demonstrates how the OrderExecutor enforces market hours
and automatically queues orders when markets are closed.

Requirements validated:
- 6.9: Order executor respects market hours for different asset classes
- 12.2: Verify target market is open before order submission
- 12.3: Queue orders for closed markets and execute at market open
"""

import logging
import time
from datetime import datetime

from src.api.etoro_client import EToroAPIClient
from src.data.market_hours_manager import MarketHoursManager, AssetClass
from src.execution.order_executor import OrderExecutor
from src.models import TradingSignal, SignalAction, TradingMode

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def example_market_hours_enforcement():
    """Demonstrate market hours enforcement and order queueing."""
    
    logger.info("\n=== Market Hours Enforcement Example ===\n")
    
    # Initialize components
    etoro_client = EToroAPIClient(
        public_key="demo_key",
        user_key="demo_secret",
        mode=TradingMode.DEMO
    )
    market_hours = MarketHoursManager()
    order_executor = OrderExecutor(
        etoro_client=etoro_client,
        market_hours=market_hours
    )
    
    # Example 1: Check market status before creating signals
    logger.info("=== Example 1: Check Market Status ===")
    
    symbols = {
        "AAPL": AssetClass.STOCK,
        "SPY": AssetClass.ETF,
        "BTC-USD": AssetClass.CRYPTOCURRENCY
    }
    
    for symbol, asset_class in symbols.items():
        is_open = market_hours.is_market_open(asset_class)
        status = "OPEN" if is_open else "CLOSED"
        logger.info(f"{symbol} ({asset_class.value}) market is {status}")
        
        if not is_open:
            next_open = market_hours.get_next_open_time(asset_class)
            logger.info(f"  Next open time: {next_open}")
    
    # Example 2: Submit order when market is open
    logger.info("\n=== Example 2: Order Submission (Market Open) ===")
    
    # Cryptocurrency markets are always open
    crypto_signal = TradingSignal(
        strategy_id="crypto_strategy",
        symbol="BTC-USD",
        action=SignalAction.ENTER_LONG,
        confidence=0.85,
        reason="Bullish momentum",
        generated_at=datetime.now(),
        metadata={}
    )
    
    logger.info(f"Submitting order for {crypto_signal.symbol}...")
    crypto_order = order_executor.execute_signal(crypto_signal, position_size=1.0)
    
    if crypto_order.status.value == "SUBMITTED":
        logger.info(f"✓ Order submitted immediately (market open)")
        logger.info(f"  Order ID: {crypto_order.id}")
        logger.info(f"  eToro Order ID: {crypto_order.etoro_order_id}")
    else:
        logger.info(f"✗ Order queued (market closed)")
    
    # Example 3: Submit order when market is closed (will be queued)
    logger.info("\n=== Example 3: Order Queueing (Market Closed) ===")
    
    # Check if stock market is currently closed
    stock_market_open = market_hours.is_market_open(AssetClass.STOCK)
    
    stock_signal = TradingSignal(
        strategy_id="stock_strategy",
        symbol="AAPL",
        action=SignalAction.ENTER_LONG,
        confidence=0.80,
        reason="Technical breakout",
        generated_at=datetime.now(),
        metadata={}
    )
    
    logger.info(f"Submitting order for {stock_signal.symbol}...")
    logger.info(f"Stock market status: {'OPEN' if stock_market_open else 'CLOSED'}")
    
    stock_order = order_executor.execute_signal(stock_signal, position_size=100.0)
    
    if stock_order.status.value == "PENDING":
        logger.info(f"✓ Order queued for market open")
        logger.info(f"  Order ID: {stock_order.id}")
        logger.info(f"  Symbol: {stock_order.symbol}")
        logger.info(f"  Quantity: {stock_order.quantity}")
        
        # Show when market will open
        next_open = market_hours.get_next_open_time(AssetClass.STOCK)
        logger.info(f"  Will execute at: {next_open}")
    else:
        logger.info(f"✓ Order submitted immediately (market open)")
        logger.info(f"  Order ID: {stock_order.id}")
        logger.info(f"  eToro Order ID: {stock_order.etoro_order_id}")
    
    # Example 4: Check queued orders
    logger.info("\n=== Example 4: Queued Orders Status ===")
    
    queued_count = order_executor.get_queued_orders_count()
    logger.info(f"Total queued orders: {queued_count}")
    
    if queued_count > 0:
        queued_orders = order_executor.get_queued_orders()
        for order in queued_orders:
            logger.info(f"  - {order.symbol}: {order.side.value} {order.quantity} @ {order.order_type.value}")
    
    # Example 5: Process queued orders (simulating market open)
    logger.info("\n=== Example 5: Processing Queued Orders ===")
    
    if queued_count > 0:
        logger.info("Simulating market open and processing queued orders...")
        
        # In production, this would be called by:
        # 1. A background scheduler (every 1-5 minutes)
        # 2. Market open event handler
        # 3. Trading engine main loop
        
        processed = order_executor.process_queued_orders()
        logger.info(f"Processed {processed} queued orders")
        
        remaining = order_executor.get_queued_orders_count()
        logger.info(f"Remaining queued orders: {remaining}")
    else:
        logger.info("No queued orders to process")
    
    # Example 6: Integration with trading engine
    logger.info("\n=== Example 6: Trading Engine Integration ===")
    
    logger.info("Example trading engine loop:")
    logger.info("""
    # Pseudo-code for trading engine
    while trading_active:
        # Generate trading signals
        signals = strategy_engine.generate_signals()
        
        # Validate signals through risk manager
        for signal in signals:
            if risk_manager.validate_signal(signal):
                # Execute signal (will queue if market closed)
                order = order_executor.execute_signal(signal, position_size)
        
        # Process queued orders every minute
        if time_to_check_queue():
            processed = order_executor.process_queued_orders()
            if processed > 0:
                logger.info(f"Processed {processed} queued orders at market open")
        
        # Sleep for 60 seconds
        time.sleep(60)
    """)
    
    logger.info("\n=== Example Complete ===")


def example_automatic_execution_scheduler():
    """Example of automatic execution scheduler for queued orders."""
    
    logger.info("\n=== Automatic Execution Scheduler Example ===\n")
    
    # Initialize components
    etoro_client = EToroAPIClient(
        public_key="demo_key",
        user_key="demo_secret",
        mode=TradingMode.DEMO
    )
    market_hours = MarketHoursManager()
    order_executor = OrderExecutor(
        etoro_client=etoro_client,
        market_hours=market_hours
    )
    
    logger.info("Starting automatic execution scheduler...")
    logger.info("This would run continuously in production")
    logger.info("Checking for queued orders every 60 seconds\n")
    
    # Simulate scheduler loop (in production, this would run continuously)
    for iteration in range(3):
        logger.info(f"--- Iteration {iteration + 1} ---")
        
        # Check queued orders
        queued_count = order_executor.get_queued_orders_count()
        logger.info(f"Queued orders: {queued_count}")
        
        if queued_count > 0:
            # Process queued orders
            processed = order_executor.process_queued_orders()
            
            if processed > 0:
                logger.info(f"✓ Processed {processed} orders at market open")
            else:
                logger.info("Markets still closed, orders remain queued")
        else:
            logger.info("No queued orders")
        
        # In production, sleep for 60 seconds
        logger.info("Sleeping for 60 seconds...\n")
        # time.sleep(60)  # Commented out for example
    
    logger.info("Scheduler example complete")


if __name__ == "__main__":
    # Run examples
    example_market_hours_enforcement()
    print("\n" + "="*80 + "\n")
    example_automatic_execution_scheduler()
