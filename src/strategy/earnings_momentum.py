"""
Earnings Momentum Strategy - Captures post-earnings drift in small-cap stocks.

This strategy identifies small-cap stocks with positive earnings surprises and
captures the momentum that follows earnings announcements.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class EarningsMomentumStrategy:
    """
    Earnings Momentum Strategy implementation.
    
    Entry criteria:
    - Market cap between $300M and $2B
    - Earnings surprise > 5%
    - Revenue growth > 10% YoY
    - 2-3 days after earnings announcement
    
    Exit criteria:
    - Next earnings date approaching (within 7 days)
    - Profit target of 10% reached
    - Stop loss of 5% triggered
    - Hold period of 30-60 days reached
    """
    
    def __init__(self, config: Dict[str, Any], fundamental_provider, market_data_manager):
        """
        Initialize the earnings momentum strategy.
        
        Args:
            config: Configuration dictionary with alpha_edge.earnings_momentum section
            fundamental_provider: FundamentalDataProvider instance
            market_data_manager: MarketDataManager instance
        """
        self.config = config.get('alpha_edge', {}).get('earnings_momentum', {})
        self.fundamental_provider = fundamental_provider
        self.market_data_manager = market_data_manager
        
        # Load parameters from config
        self.enabled = self.config.get('enabled', True)
        self.market_cap_min = self.config.get('market_cap_min', 300000000)
        self.market_cap_max = self.config.get('market_cap_max', 2000000000)
        self.earnings_surprise_min = self.config.get('earnings_surprise_min', 0.05)
        self.revenue_growth_min = self.config.get('revenue_growth_min', 0.10)
        self.entry_delay_days = self.config.get('entry_delay_days', 2)
        self.hold_period_days = self.config.get('hold_period_days', 45)
        self.profit_target = self.config.get('profit_target', 0.10)
        self.stop_loss = self.config.get('stop_loss', 0.05)
        self.exit_before_earnings_days = self.config.get('exit_before_earnings_days', 7)
        
        logger.info(f"EarningsMomentumStrategy initialized - Enabled: {self.enabled}")
    
    def check_entry_criteria(self, symbol: str) -> Dict[str, Any]:
        """
        Check if a symbol meets entry criteria for earnings momentum strategy.
        
        Args:
            symbol: Stock symbol to check
            
        Returns:
            Dictionary with 'eligible' boolean and 'reasons' list
        """
        result = {
            'eligible': False,
            'reasons': [],
            'data': {}
        }
        
        if not self.enabled:
            result['reasons'].append("Strategy is disabled")
            return result
        
        try:
            # Get fundamental data
            fundamental_data = self.fundamental_provider.get_fundamental_data(symbol)
            if not fundamental_data:
                result['reasons'].append("No fundamental data available")
                return result
            
            # Check market cap
            market_cap = fundamental_data.market_cap
            if not market_cap:
                result['reasons'].append("Market cap not available")
                return result
            
            if market_cap < self.market_cap_min:
                result['reasons'].append(f"Market cap ${market_cap:,.0f} below minimum ${self.market_cap_min:,.0f}")
                return result
            
            if market_cap > self.market_cap_max:
                result['reasons'].append(f"Market cap ${market_cap:,.0f} above maximum ${self.market_cap_max:,.0f}")
                return result
            
            result['data']['market_cap'] = market_cap
            
            # Get earnings data
            earnings_data = self.fundamental_provider.get_earnings_calendar(symbol)
            if not earnings_data:
                result['reasons'].append("No earnings data available")
                return result
            
            # Check earnings surprise
            surprise_pct = earnings_data.get('surprise_pct')
            if surprise_pct is None:
                result['reasons'].append("Earnings surprise not available")
                return result
            
            if surprise_pct < self.earnings_surprise_min:
                result['reasons'].append(f"Earnings surprise {surprise_pct:.1%} below minimum {self.earnings_surprise_min:.1%}")
                return result
            
            result['data']['earnings_surprise'] = surprise_pct
            
            # Check revenue growth
            revenue_growth = fundamental_data.revenue_growth
            if revenue_growth is None:
                result['reasons'].append("Revenue growth not available")
                return result
            
            if revenue_growth < self.revenue_growth_min:
                result['reasons'].append(f"Revenue growth {revenue_growth:.1%} below minimum {self.revenue_growth_min:.1%}")
                return result
            
            result['data']['revenue_growth'] = revenue_growth
            
            # Optional: Check institutional ownership if enabled
            if self.config.get('check_institutional_ownership', False):
                # This would require additional API integration
                # For now, we'll log that it's not implemented
                logger.debug(f"Institutional ownership check requested for {symbol} but not yet implemented")
            
            # Check days since earnings
            days_since = self.fundamental_provider.get_days_since_earnings(symbol)
            if days_since is None:
                result['reasons'].append("Cannot determine days since earnings")
                return result
            
            if days_since < self.entry_delay_days:
                result['reasons'].append(f"Only {days_since} days since earnings, need {self.entry_delay_days}")
                return result
            
            if days_since > 10:  # Don't enter too late
                result['reasons'].append(f"{days_since} days since earnings, too late to enter")
                return result
            
            result['data']['days_since_earnings'] = days_since
            result['data']['earnings_date'] = earnings_data.get('last_earnings_date')
            
            # All criteria met
            result['eligible'] = True
            result['reasons'].append("All entry criteria met")
            
            logger.info(f"{symbol} eligible for earnings momentum: "
                       f"Market cap ${market_cap:,.0f}, "
                       f"Earnings surprise {surprise_pct:.1%}, "
                       f"Revenue growth {revenue_growth:.1%}, "
                       f"{days_since} days since earnings")
            
        except Exception as e:
            logger.error(f"Error checking entry criteria for {symbol}: {e}")
            result['reasons'].append(f"Error: {str(e)}")
        
        return result
    
    def check_exit_criteria(self, symbol: str, entry_price: float, 
                           entry_date: datetime, current_price: float) -> Dict[str, Any]:
        """
        Check if a position should be exited.
        
        Args:
            symbol: Stock symbol
            entry_price: Entry price
            entry_date: Entry date
            current_price: Current price
            
        Returns:
            Dictionary with 'should_exit' boolean, 'reason' string, and 'exit_type'
        """
        result = {
            'should_exit': False,
            'reason': None,
            'exit_type': None,
            'pnl_pct': 0.0
        }
        
        try:
            # Calculate P&L
            pnl_pct = (current_price - entry_price) / entry_price
            result['pnl_pct'] = pnl_pct
            
            # Check profit target
            if pnl_pct >= self.profit_target:
                result['should_exit'] = True
                result['reason'] = f"Profit target reached: {pnl_pct:.1%}"
                result['exit_type'] = 'profit_target'
                return result
            
            # Check stop loss
            if pnl_pct <= -self.stop_loss:
                result['should_exit'] = True
                result['reason'] = f"Stop loss triggered: {pnl_pct:.1%}"
                result['exit_type'] = 'stop_loss'
                return result
            
            # Check hold period
            days_held = (datetime.now() - entry_date).days
            if days_held >= self.hold_period_days:
                result['should_exit'] = True
                result['reason'] = f"Maximum hold period reached: {days_held} days"
                result['exit_type'] = 'max_hold_period'
                return result
            
            # Check if next earnings approaching
            days_since = self.fundamental_provider.get_days_since_earnings(symbol)
            if days_since is not None:
                # Typical earnings cycle is ~90 days
                days_until_next = 90 - days_since
                if days_until_next <= self.exit_before_earnings_days:
                    result['should_exit'] = True
                    result['reason'] = f"Next earnings approaching in ~{days_until_next} days"
                    result['exit_type'] = 'earnings_approaching'
                    return result
            
        except Exception as e:
            logger.error(f"Error checking exit criteria for {symbol}: {e}")
            result['reason'] = f"Error: {str(e)}"
        
        return result
    
    def calculate_position_size(self, symbol: str, account_value: float, 
                               current_price: float) -> float:
        """
        Calculate position size based on risk parameters.
        
        Args:
            symbol: Stock symbol
            account_value: Total account value
            current_price: Current stock price
            
        Returns:
            Number of shares to buy
        """
        try:
            # Risk 1% of account per trade
            risk_amount = account_value * 0.01
            
            # Calculate position size based on stop loss
            stop_loss_amount = current_price * self.stop_loss
            
            if stop_loss_amount > 0:
                shares = risk_amount / stop_loss_amount
                # Round down to whole shares
                shares = int(shares)
                
                # Ensure position doesn't exceed 5% of account
                max_position_value = account_value * 0.05
                max_shares = int(max_position_value / current_price)
                
                shares = min(shares, max_shares)
                
                logger.info(f"Position size for {symbol}: {shares} shares "
                           f"(${shares * current_price:,.2f})")
                
                return shares
            
        except Exception as e:
            logger.error(f"Error calculating position size for {symbol}: {e}")
        
        return 0
    
    def get_strategy_metadata(self) -> Dict[str, Any]:
        """Get strategy metadata for logging and tracking."""
        return {
            'strategy_type': 'earnings_momentum',
            'market_cap_range': f"${self.market_cap_min:,.0f} - ${self.market_cap_max:,.0f}",
            'earnings_surprise_min': f"{self.earnings_surprise_min:.1%}",
            'revenue_growth_min': f"{self.revenue_growth_min:.1%}",
            'entry_delay_days': self.entry_delay_days,
            'hold_period_days': self.hold_period_days,
            'profit_target': f"{self.profit_target:.1%}",
            'stop_loss': f"{self.stop_loss:.1%}"
        }
    
    def track_post_earnings_drift(self, symbol: str, entry_date: datetime, 
                                  entry_price: float, current_price: float,
                                  earnings_date: datetime) -> Dict[str, Any]:
        """
        Track post-earnings drift performance metrics.
        
        This method calculates performance metrics relative to the earnings announcement
        to measure the effectiveness of the post-earnings drift strategy.
        
        Args:
            symbol: Stock symbol
            entry_date: Date of entry
            entry_price: Entry price
            current_price: Current price
            earnings_date: Date of earnings announcement
            
        Returns:
            Dictionary with drift performance metrics
        """
        try:
            # Calculate days since earnings
            days_since_earnings = (datetime.now() - earnings_date).days
            
            # Calculate days held
            days_held = (datetime.now() - entry_date).days
            
            # Calculate return
            return_pct = (current_price - entry_price) / entry_price
            
            # Calculate annualized return
            if days_held > 0:
                annualized_return = return_pct * (365 / days_held)
            else:
                annualized_return = 0.0
            
            # Determine drift phase
            if days_since_earnings <= 5:
                drift_phase = 'immediate'
            elif days_since_earnings <= 30:
                drift_phase = 'short_term'
            elif days_since_earnings <= 60:
                drift_phase = 'medium_term'
            else:
                drift_phase = 'long_term'
            
            return {
                'symbol': symbol,
                'days_since_earnings': days_since_earnings,
                'days_held': days_held,
                'return_pct': return_pct,
                'annualized_return': annualized_return,
                'drift_phase': drift_phase,
                'entry_price': entry_price,
                'current_price': current_price,
                'earnings_date': earnings_date.isoformat(),
                'entry_date': entry_date.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error tracking post-earnings drift for {symbol}: {e}")
            return {}
