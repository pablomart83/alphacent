"""
Test script for autonomous status endpoint.

Tests the GET /api/strategies/autonomous/status endpoint.
"""

import asyncio
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_autonomous_status_endpoint():
    """Test the autonomous status endpoint."""
    logger.info("Testing autonomous status endpoint...")
    
    try:
        # Import required modules
        from src.api.routers.strategies import get_autonomous_status
        from src.models.enums import TradingMode
        from src.core.config import get_config
        
        # Check if credentials are configured
        config = get_config()
        credentials = config.load_credentials(TradingMode.DEMO)
        
        if not credentials or not credentials.get("public_key") or not credentials.get("user_key"):
            logger.error("eToro credentials not configured. Please set up credentials first.")
            logger.info("Run: python save_credentials.py")
            return False
        
        logger.info("Credentials found, testing endpoint...")
        
        # Call the endpoint (simulating authenticated user)
        try:
            # Mock username for testing
            username = "test_user"
            
            # Call the endpoint function directly
            response = await get_autonomous_status(username=username)
            
            # Validate response structure
            assert hasattr(response, 'enabled'), "Response missing 'enabled' field"
            assert hasattr(response, 'market_regime'), "Response missing 'market_regime' field"
            assert hasattr(response, 'cycle_stats'), "Response missing 'cycle_stats' field"
            assert hasattr(response, 'portfolio_health'), "Response missing 'portfolio_health' field"
            assert hasattr(response, 'template_stats'), "Response missing 'template_stats' field"
            
            # Log response details
            logger.info("✓ Endpoint response structure valid")
            logger.info(f"  - Enabled: {response.enabled}")
            logger.info(f"  - Market Regime: {response.market_regime}")
            logger.info(f"  - Market Confidence: {response.market_confidence:.2f}")
            logger.info(f"  - Data Quality: {response.data_quality}")
            logger.info(f"  - Last Cycle: {response.last_cycle_time or 'Never'}")
            logger.info(f"  - Next Run: {response.next_scheduled_run or 'Not scheduled'}")
            
            logger.info(f"\n  Cycle Stats:")
            logger.info(f"    - Proposals: {response.cycle_stats.proposals_count}")
            logger.info(f"    - Backtested: {response.cycle_stats.backtested_count}")
            logger.info(f"    - Activated: {response.cycle_stats.activated_count}")
            logger.info(f"    - Retired: {response.cycle_stats.retired_count}")
            
            logger.info(f"\n  Portfolio Health:")
            logger.info(f"    - Active Strategies: {response.portfolio_health.active_strategies}/{response.portfolio_health.max_strategies}")
            logger.info(f"    - Total Allocation: {response.portfolio_health.total_allocation:.1f}%")
            logger.info(f"    - Avg Correlation: {response.portfolio_health.avg_correlation:.2f}")
            logger.info(f"    - Portfolio Sharpe: {response.portfolio_health.portfolio_sharpe:.2f}")
            
            logger.info(f"\n  Template Stats (Top {len(response.template_stats)}):")
            for template in response.template_stats:
                logger.info(f"    - {template.name}: {template.success_rate:.1f}% success, {template.usage_count} uses")
            
            logger.info("\n✓ All tests passed!")
            return True
            
        except Exception as e:
            logger.error(f"✗ Endpoint call failed: {e}", exc_info=True)
            return False
            
    except Exception as e:
        logger.error(f"✗ Test setup failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = asyncio.run(test_autonomous_status_endpoint())
    exit(0 if success else 1)
