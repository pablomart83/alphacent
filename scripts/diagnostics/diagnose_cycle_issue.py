"""
Diagnostic script to trace autonomous cycle execution and identify why only 2 strategies are generated.
"""

import logging
import sys
import yaml
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.enums import TradingMode
from src.strategy.autonomous_strategy_manager import AutonomousStrategyManager
from src.strategy.strategy_engine import StrategyEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Diagnose autonomous cycle configuration and execution."""
    logger.info("=" * 80)
    logger.info("AUTONOMOUS CYCLE DIAGNOSTIC")
    logger.info("=" * 80)
    
    try:
        # 1. Check config file
        logger.info("\n[1] Checking configuration file...")
        config_path = Path("config/autonomous_trading.yaml")
        
        if not config_path.exists():
            logger.error(f"   ✗ Config file not found: {config_path}")
            return False
        
        with open(config_path, 'r') as f:
            file_config = yaml.safe_load(f)
        
        logger.info(f"   ✓ Config file loaded: {config_path}")
        logger.info(f"   Autonomous enabled: {file_config.get('autonomous', {}).get('enabled')}")
        logger.info(f"   Proposal count: {file_config.get('autonomous', {}).get('proposal_count')}")
        logger.info(f"   Max active strategies: {file_config.get('autonomous', {}).get('max_active_strategies')}")
        logger.info(f"   Backtest days: {file_config.get('backtest', {}).get('days')}")
        
        # 2. Initialize components
        logger.info("\n[2] Initializing components...")
        
        config_manager = get_config()
        credentials = config_manager.load_credentials(TradingMode.DEMO)
        
        if not credentials or not credentials.get("public_key"):
            logger.warning("   ⚠ No eToro credentials, using mock client")
            from unittest.mock import Mock
            etoro_client = Mock()
        else:
            etoro_client = EToroAPIClient(
                public_key=credentials["public_key"],
                user_key=credentials["user_key"],
                mode=TradingMode.DEMO
            )
        
        market_data = MarketDataManager(etoro_client)
        llm_service = LLMService()
        strategy_engine = StrategyEngine(llm_service, market_data)
        
        logger.info("   ✓ Components initialized")
        
        # 3. Initialize autonomous manager WITHOUT config (let it load from file)
        logger.info("\n[3] Initializing AutonomousStrategyManager (loading from file)...")
        
        autonomous_manager = AutonomousStrategyManager(
            llm_service=llm_service,
            market_data=market_data,
            strategy_engine=strategy_engine
        )
        
        logger.info("   ✓ AutonomousStrategyManager initialized")
        logger.info(f"   Loaded config proposal_count: {autonomous_manager.config['autonomous']['proposal_count']}")
        logger.info(f"   Loaded config enabled: {autonomous_manager.config['autonomous']['enabled']}")
        logger.info(f"   Loaded config max_active: {autonomous_manager.config['autonomous']['max_active_strategies']}")
        
        # 4. Check strategy proposer
        logger.info("\n[4] Checking strategy proposer...")
        logger.info(f"   Strategy proposer initialized: {autonomous_manager.strategy_proposer is not None}")
        
        # 5. Test strategy proposal directly
        logger.info("\n[5] Testing strategy proposal directly...")
        proposal_count = autonomous_manager.config['autonomous']['proposal_count']
        logger.info(f"   Requesting {proposal_count} strategies...")
        
        try:
            proposals = autonomous_manager.strategy_proposer.propose_strategies(
                count=proposal_count,
                use_walk_forward=False  # Disable walk-forward for faster testing
            )
            
            logger.info(f"   ✓ Generated {len(proposals)} strategies")
            
            if len(proposals) < proposal_count:
                logger.warning(f"   ⚠ Expected {proposal_count} but got {len(proposals)}")
                logger.warning("   This indicates filtering is too aggressive or generation is failing")
            
            # Show first few strategies
            for i, strategy in enumerate(proposals[:5], 1):
                logger.info(f"      {i}. {strategy.name} - {strategy.symbols}")
                
        except Exception as e:
            logger.error(f"   ✗ Strategy proposal failed: {e}", exc_info=True)
            return False
        
        # 6. Check template library
        logger.info("\n[6] Checking template library...")
        from src.strategy.strategy_templates import StrategyTemplateLibrary, MarketRegime
        
        template_library = StrategyTemplateLibrary()
        all_templates = template_library.get_all_templates()
        logger.info(f"   Total templates: {len(all_templates)}")
        
        for regime in MarketRegime:
            templates = template_library.get_templates_for_regime(regime)
            logger.info(f"   {regime.value}: {len(templates)} templates")
        
        # 7. Check market regime detection
        logger.info("\n[7] Checking market regime detection...")
        try:
            regime = autonomous_manager.strategy_proposer.analyze_market_conditions()
            logger.info(f"   Current market regime: {regime}")
        except Exception as e:
            logger.error(f"   ✗ Market regime detection failed: {e}")
        
        # 8. Summary
        logger.info("\n" + "=" * 80)
        logger.info("DIAGNOSTIC SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Config file proposal_count: {file_config.get('autonomous', {}).get('proposal_count')}")
        logger.info(f"Loaded config proposal_count: {autonomous_manager.config['autonomous']['proposal_count']}")
        logger.info(f"Actual strategies generated: {len(proposals)}")
        logger.info(f"Templates available: {len(all_templates)}")
        
        if len(proposals) < proposal_count:
            logger.warning("\n⚠ ISSUE IDENTIFIED:")
            logger.warning(f"   Expected {proposal_count} strategies but only got {len(proposals)}")
            logger.warning("   Possible causes:")
            logger.warning("   1. Walk-forward validation filtering too many strategies")
            logger.warning("   2. Quality scoring filtering too aggressive")
            logger.warning("   3. Template generation failing")
            logger.warning("   4. Market regime has limited templates")
        else:
            logger.info("\n✓ Strategy generation working correctly")
        
        return True
        
    except Exception as e:
        logger.error(f"\n❌ DIAGNOSTIC FAILED: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
