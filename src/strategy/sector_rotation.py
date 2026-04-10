"""
Sector Rotation Strategy implementation.

This strategy rotates into sectors that outperform in current economic regimes.
It trades sector ETFs based on macro conditions detected by MarketStatisticsAnalyzer.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger(__name__)


class SectorRotationStrategy:
    """
    Sector Rotation Strategy implementation.
    
    Rotates into sectors that historically outperform in current market regimes.
    Uses sector ETFs for diversified exposure with lower risk than individual stocks.
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        market_analyzer,
        market_data_manager
    ):
        """
        Initialize the Sector Rotation Strategy.
        
        Args:
            config: Configuration dictionary with alpha_edge.sector_rotation section
            market_analyzer: MarketStatisticsAnalyzer instance for regime detection
            market_data_manager: MarketDataManager instance for price data
        """
        self.config = config.get('alpha_edge', {}).get('sector_rotation', {})
        self.market_analyzer = market_analyzer
        self.market_data_manager = market_data_manager
        
        # Configuration parameters
        self.enabled = self.config.get('enabled', True)
        self.max_positions = self.config.get('max_positions', 3)
        self.rebalance_frequency_days = self.config.get('rebalance_frequency_days', 30)
        self.sectors = self.config.get('sectors', [
            'XLE',  # Energy
            'XLF',  # Financials
            'XLK',  # Technology
            'XLU',  # Utilities
            'XLV',  # Healthcare
            'XLI',  # Industrials
            'XLP',  # Consumer Staples
            'XLY'   # Consumer Discretionary
        ])
        
        # Sector metadata
        self.sector_names = {
            'XLE': 'Energy',
            'XLF': 'Financials',
            'XLK': 'Technology',
            'XLU': 'Utilities',
            'XLV': 'Healthcare',
            'XLI': 'Industrials',
            'XLP': 'Consumer Staples',
            'XLY': 'Consumer Discretionary'
        }
        
        # Track last rebalance date
        self.last_rebalance_date = None
        
        logger.info(f"SectorRotationStrategy initialized - Enabled: {self.enabled}")
    
    def get_regime_to_sector_mapping(self) -> Dict[str, List[str]]:
        """
        Map market regimes to optimal sectors.
        
        Returns:
            Dictionary mapping regime descriptions to sector ETF lists
        """
        return {
            # High inflation + rising rates
            'high_inflation_rising_rates': ['XLE'],  # Energy, Commodities
            
            # Low inflation + falling rates
            'low_inflation_falling_rates': ['XLK'],  # Tech, Growth
            
            # Recession fears (high unemployment, risk-off)
            'recession_fears': ['XLU', 'XLP', 'XLV'],  # Utilities, Staples, Healthcare
            
            # Economic expansion (low unemployment, risk-on)
            'economic_expansion': ['XLF', 'XLI', 'XLY'],  # Financials, Industrials, Discretionary
            
            # Neutral/Transitional
            'neutral': ['XLV', 'XLP'],  # Defensive sectors
        }
    
    def detect_current_regime(self) -> str:
        """
        Detect current market regime based on macro indicators.
        
        Returns:
            Regime key string
        """
        try:
            market_context = self.market_analyzer.get_market_context()
            
            inflation_rate = market_context.get('inflation_rate', 3.0)
            fed_stance = market_context.get('fed_stance', 'neutral')
            unemployment_trend = market_context.get('unemployment_trend', 'stable')
            macro_regime = market_context.get('macro_regime', 'transitional')
            vix = market_context.get('vix', 20.0)
            
            # High inflation + rising rates
            if inflation_rate > 4.0 and fed_stance == 'tightening':
                return 'high_inflation_rising_rates'
            
            # Low inflation + falling rates
            if inflation_rate < 3.0 and fed_stance == 'accommodative':
                return 'low_inflation_falling_rates'
            
            # Recession fears
            if unemployment_trend == 'rising' or macro_regime == 'risk_off' or vix > 25:
                return 'recession_fears'
            
            # Economic expansion
            if unemployment_trend == 'falling' and macro_regime == 'risk_on' and vix < 20:
                return 'economic_expansion'
            
            # Default to neutral
            return 'neutral'
            
        except Exception as e:
            logger.error(f"Error detecting regime: {e}")
            return 'neutral'
    
    def calculate_sector_momentum(self, lookback_days: int = 60) -> Dict[str, float]:
        """
        Calculate momentum score for each sector ETF.
        
        Args:
            lookback_days: Number of days to calculate momentum over
            
        Returns:
            Dictionary mapping sector ETF to momentum score (0-100)
        """
        momentum_scores = {}
        
        for sector in self.sectors:
            try:
                # Get historical data
                df = self.market_data_manager.get_historical_data(
                    sector,
                    period_days=lookback_days + 50  # Extra for MA calculation
                )
                
                if df is None or len(df) < lookback_days:
                    logger.warning(f"Insufficient data for {sector}")
                    momentum_scores[sector] = 0.0
                    continue
                
                # Calculate momentum metrics
                current_price = df['close'].iloc[-1]
                price_60d_ago = df['close'].iloc[-lookback_days] if len(df) >= lookback_days else df['close'].iloc[0]
                
                # Price momentum (60-day return)
                price_momentum = ((current_price - price_60d_ago) / price_60d_ago) * 100
                
                # Relative strength vs 200-day MA
                ma_200 = df['close'].rolling(window=200).mean().iloc[-1]
                if pd.notna(ma_200) and ma_200 > 0:
                    relative_strength = ((current_price - ma_200) / ma_200) * 100
                else:
                    relative_strength = 0.0
                
                # Combine metrics (weighted average)
                momentum_score = (price_momentum * 0.7) + (relative_strength * 0.3)
                momentum_scores[sector] = momentum_score
                
            except Exception as e:
                logger.error(f"Error calculating momentum for {sector}: {e}")
                momentum_scores[sector] = 0.0
        
        return momentum_scores
    
    def should_rebalance(self) -> bool:
        """
        Check if it's time to rebalance based on frequency setting.
        
        Returns:
            True if rebalancing is due
        """
        if not self.enabled:
            return False
        
        if self.last_rebalance_date is None:
            return True
        
        days_since_rebalance = (datetime.now() - self.last_rebalance_date).days
        return days_since_rebalance >= self.rebalance_frequency_days
    
    def get_recommended_sectors(self) -> List[Dict[str, Any]]:
        """
        Get recommended sectors based on current regime and momentum.
        
        Returns:
            List of sector recommendations with metadata
        """
        if not self.enabled:
            return []
        
        try:
            # Detect current regime
            current_regime = self.detect_current_regime()
            regime_mapping = self.get_regime_to_sector_mapping()
            regime_sectors = regime_mapping.get(current_regime, ['XLV', 'XLP'])
            
            # Calculate momentum for all sectors
            momentum_scores = self.calculate_sector_momentum()
            
            # Filter to regime-appropriate sectors and sort by momentum
            regime_sector_scores = {
                sector: momentum_scores.get(sector, 0.0)
                for sector in regime_sectors
            }
            
            # Sort by momentum (highest first)
            sorted_sectors = sorted(
                regime_sector_scores.items(),
                key=lambda x: x[1],
                reverse=True
            )
            
            # Take top N sectors (up to max_positions)
            top_sectors = sorted_sectors[:self.max_positions]
            
            # Build recommendations
            recommendations = []
            for sector, momentum in top_sectors:
                recommendations.append({
                    'symbol': sector,
                    'sector_name': self.sector_names.get(sector, sector),
                    'momentum_score': momentum,
                    'regime': current_regime,
                    'reason': f"Top momentum sector for {current_regime} regime"
                })
            
            logger.info(f"Recommended {len(recommendations)} sectors for regime: {current_regime}")
            return recommendations
            
        except Exception as e:
            logger.error(f"Error getting recommended sectors: {e}")
            return []
    
    def generate_rebalancing_signals(
        self,
        current_positions: List[str]
    ) -> Dict[str, List[str]]:
        """
        Generate rebalancing signals (sectors to add/remove).
        
        Args:
            current_positions: List of currently held sector ETFs
            
        Returns:
            Dictionary with 'add' and 'remove' lists
        """
        if not self.should_rebalance():
            return {'add': [], 'remove': []}
        
        # Get recommended sectors
        recommendations = self.get_recommended_sectors()
        recommended_sectors = [rec['symbol'] for rec in recommendations]
        
        # Determine what to add and remove
        sectors_to_add = [s for s in recommended_sectors if s not in current_positions]
        sectors_to_remove = [s for s in current_positions if s not in recommended_sectors]
        
        # Update last rebalance date
        self.last_rebalance_date = datetime.now()
        
        logger.info(f"Rebalancing: Add {sectors_to_add}, Remove {sectors_to_remove}")
        
        return {
            'add': sectors_to_add,
            'remove': sectors_to_remove
        }
    
    def get_strategy_metadata(self) -> Dict[str, Any]:
        """Get strategy metadata for logging and tracking."""
        return {
            'strategy_type': 'sector_rotation',
            'max_positions': self.max_positions,
            'rebalance_frequency_days': self.rebalance_frequency_days,
            'sectors': self.sectors,
            'enabled': self.enabled
        }
