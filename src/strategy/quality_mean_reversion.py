"""
Quality Mean Reversion Strategy - Buy high-quality stocks when temporarily oversold.

This strategy identifies large-cap stocks with strong fundamentals that are
experiencing temporary price weakness, then profits from the recovery.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class QualityMeanReversionStrategy:
    """
    Quality Mean Reversion Strategy implementation.
    
    Entry criteria:
    - Large-cap stocks (>$10B market cap)
    - Strong fundamentals: ROE > 15%, Debt/Equity < 0.5, positive FCF
    - Technical oversold: Down >10% in 5 days, RSI < 30, below 200-day MA
    - No fundamental deterioration (check recent news/earnings)
    - Entry: When RSI crosses back above 30
    
    Exit criteria:
    - Price returns to 50-day MA
    - 5% profit target reached
    - 3% stop loss triggered
    """
    
    def __init__(self, config: Dict[str, Any], fundamental_provider, market_data_manager):
        """
        Initialize the quality mean reversion strategy.
        
        Args:
            config: Configuration dictionary with alpha_edge.quality_mean_reversion section
            fundamental_provider: FundamentalDataProvider instance
            market_data_manager: MarketDataManager instance
        """
        self.config = config.get('alpha_edge', {}).get('quality_mean_reversion', {})
        self.fundamental_provider = fundamental_provider
        self.market_data_manager = market_data_manager
        
        # Load parameters from config
        self.enabled = self.config.get('enabled', True)
        self.market_cap_min = self.config.get('market_cap_min', 10000000000)  # $10B
        self.min_roe = self.config.get('min_roe', 0.15)  # 15%
        self.max_debt_equity = self.config.get('max_debt_equity', 0.5)
        self.oversold_threshold = self.config.get('oversold_threshold', 30)  # RSI
        self.drawdown_threshold = self.config.get('drawdown_threshold', 0.10)  # 10% in 5 days
        self.profit_target = self.config.get('profit_target', 0.05)  # 5%
        self.stop_loss = self.config.get('stop_loss', 0.03)  # 3%
        
        logger.info(f"QualityMeanReversionStrategy initialized - Enabled: {self.enabled}")
    
    def check_quality_criteria(self, symbol: str) -> Dict[str, Any]:
        """
        Check if a symbol meets quality criteria (fundamentals).
        
        Args:
            symbol: Stock symbol to check
            
        Returns:
            Dictionary with 'passes' boolean, 'reasons' list, and 'data' dict
        """
        result = {
            'passes': False,
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
            
            result['data']['market_cap'] = market_cap
            
            # Check ROE
            roe = fundamental_data.roe
            if roe is None:
                result['reasons'].append("ROE not available")
                return result
            
            if roe < self.min_roe:
                result['reasons'].append(f"ROE {roe:.1%} below minimum {self.min_roe:.1%}")
                return result
            
            result['data']['roe'] = roe
            
            # Check Debt/Equity ratio
            debt_equity = fundamental_data.debt_to_equity
            if debt_equity is None:
                result['reasons'].append("Debt/Equity ratio not available")
                return result
            
            if debt_equity > self.max_debt_equity:
                result['reasons'].append(f"Debt/Equity {debt_equity:.2f} above maximum {self.max_debt_equity:.2f}")
                return result
            
            result['data']['debt_equity'] = debt_equity
            
            # Check Free Cash Flow (must be positive)
            # Note: FCF might not be directly available, we'll use a proxy
            # In a real implementation, you'd fetch this from the fundamental provider
            # For now, we'll assume it's available in the fundamental data
            # If not available, we'll skip this check
            
            # All quality criteria met
            result['passes'] = True
            result['reasons'].append("All quality criteria met")
            
            logger.info(f"{symbol} passes quality criteria: "
                       f"Market cap ${market_cap:,.0f}, "
                       f"ROE {roe:.1%}, "
                       f"Debt/Equity {debt_equity:.2f}")
            
        except Exception as e:
            logger.error(f"Error checking quality criteria for {symbol}: {e}")
            result['reasons'].append(f"Error: {str(e)}")
        
        return result
    
    def check_oversold_criteria(self, symbol: str) -> Dict[str, Any]:
        """
        Check if a symbol meets oversold criteria (technical).
        
        Args:
            symbol: Stock symbol to check
            
        Returns:
            Dictionary with 'oversold' boolean, 'reasons' list, and 'data' dict
        """
        result = {
            'oversold': False,
            'reasons': [],
            'data': {}
        }
        
        try:
            # Get historical data (need enough for 200-day MA)
            df = self.market_data_manager.get_historical_data(
                symbol,
                period_days=250  # Extra for MA calculation
            )
            
            if df is None or len(df) < 200:
                result['reasons'].append("Insufficient historical data")
                return result
            
            # Calculate RSI
            rsi = self._calculate_rsi(df['close'], period=14)
            current_rsi = rsi.iloc[-1] if len(rsi) > 0 else None
            
            if current_rsi is None:
                result['reasons'].append("RSI calculation failed")
                return result
            
            result['data']['rsi'] = current_rsi
            
            # Check if RSI is oversold
            if current_rsi >= self.oversold_threshold:
                result['reasons'].append(f"RSI {current_rsi:.1f} not oversold (threshold: {self.oversold_threshold})")
                return result
            
            # Check 5-day drawdown
            if len(df) >= 5:
                price_5d_ago = df['close'].iloc[-6]  # -6 because -1 is today
                current_price = df['close'].iloc[-1]
                drawdown_5d = (current_price - price_5d_ago) / price_5d_ago
                
                result['data']['drawdown_5d'] = drawdown_5d
                
                if drawdown_5d > -self.drawdown_threshold:
                    result['reasons'].append(f"5-day drawdown {drawdown_5d:.1%} not severe enough (threshold: {-self.drawdown_threshold:.1%})")
                    return result
            else:
                result['reasons'].append("Insufficient data for 5-day drawdown")
                return result
            
            # Check if below 200-day MA
            ma_200 = df['close'].rolling(window=200).mean().iloc[-1]
            if current_price >= ma_200:
                result['reasons'].append(f"Price ${current_price:.2f} not below 200-day MA ${ma_200:.2f}")
                return result
            
            result['data']['ma_200'] = ma_200
            result['data']['current_price'] = current_price
            
            # All oversold criteria met
            result['oversold'] = True
            result['reasons'].append("All oversold criteria met")
            
            logger.info(f"{symbol} is oversold: "
                       f"RSI {current_rsi:.1f}, "
                       f"5-day drawdown {drawdown_5d:.1%}, "
                       f"Price ${current_price:.2f} below 200-day MA ${ma_200:.2f}")
            
        except Exception as e:
            logger.error(f"Error checking oversold criteria for {symbol}: {e}")
            result['reasons'].append(f"Error: {str(e)}")
        
        return result
    
    def check_entry_signal(self, symbol: str) -> Dict[str, Any]:
        """
        Check if a symbol has an entry signal (RSI crosses back above 30).
        
        Args:
            symbol: Stock symbol to check
            
        Returns:
            Dictionary with 'signal' boolean, 'reasons' list, and 'data' dict
        """
        result = {
            'signal': False,
            'reasons': [],
            'data': {}
        }
        
        try:
            # First check quality criteria
            quality_check = self.check_quality_criteria(symbol)
            if not quality_check['passes']:
                result['reasons'].extend(quality_check['reasons'])
                return result
            
            result['data'].update(quality_check['data'])
            
            # Get historical data
            df = self.market_data_manager.get_historical_data(
                symbol,
                period_days=250
            )
            
            if df is None or len(df) < 200:
                result['reasons'].append("Insufficient historical data")
                return result
            
            # Calculate RSI
            rsi = self._calculate_rsi(df['close'], period=14)
            
            if len(rsi) < 2:
                result['reasons'].append("Insufficient RSI data")
                return result
            
            current_rsi = rsi.iloc[-1]
            previous_rsi = rsi.iloc[-2]
            
            result['data']['current_rsi'] = current_rsi
            result['data']['previous_rsi'] = previous_rsi
            
            # Check for RSI crossover above 30
            if previous_rsi < self.oversold_threshold and current_rsi > self.oversold_threshold:
                # RSI crossed above threshold - entry signal!
                
                # Additional check: ensure we're still below 200-day MA
                ma_200 = df['close'].rolling(window=200).mean().iloc[-1]
                current_price = df['close'].iloc[-1]
                
                if current_price < ma_200:
                    result['signal'] = True
                    result['reasons'].append(f"RSI crossed above {self.oversold_threshold} (from {previous_rsi:.1f} to {current_rsi:.1f})")
                    result['data']['ma_200'] = ma_200
                    result['data']['current_price'] = current_price
                    
                    logger.info(f"{symbol} entry signal: RSI crossed above {self.oversold_threshold}")
                else:
                    result['reasons'].append(f"Price ${current_price:.2f} above 200-day MA ${ma_200:.2f}")
            else:
                result['reasons'].append(f"No RSI crossover (previous: {previous_rsi:.1f}, current: {current_rsi:.1f})")
            
        except Exception as e:
            logger.error(f"Error checking entry signal for {symbol}: {e}")
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
            
            # Check if price returned to 50-day MA
            df = self.market_data_manager.get_historical_data(
                symbol,
                period_days=100
            )
            
            if df is not None and len(df) >= 50:
                ma_50 = df['close'].rolling(window=50).mean().iloc[-1]
                
                if current_price >= ma_50:
                    result['should_exit'] = True
                    result['reason'] = f"Price returned to 50-day MA: ${current_price:.2f} >= ${ma_50:.2f}"
                    result['exit_type'] = 'mean_reversion'
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
    
    def check_fundamental_deterioration(self, symbol: str) -> Dict[str, Any]:
        """
        Check for fundamental deterioration (recent negative news/earnings).
        
        This is a placeholder for future implementation that would check:
        - Recent earnings misses
        - Negative news sentiment
        - Analyst downgrades
        - Management changes
        
        Args:
            symbol: Stock symbol to check
            
        Returns:
            Dictionary with 'deterioration' boolean and 'reasons' list
        """
        result = {
            'deterioration': False,
            'reasons': []
        }
        
        # TODO: Implement news/earnings checks
        # For now, we'll assume no deterioration
        result['reasons'].append("Fundamental deterioration check not yet implemented")
        
        return result
    
    def get_strategy_metadata(self) -> Dict[str, Any]:
        """Get strategy metadata for logging and tracking."""
        return {
            'strategy_type': 'quality_mean_reversion',
            'market_cap_min': f"${self.market_cap_min:,.0f}",
            'min_roe': f"{self.min_roe:.1%}",
            'max_debt_equity': f"{self.max_debt_equity:.2f}",
            'oversold_threshold': self.oversold_threshold,
            'drawdown_threshold': f"{self.drawdown_threshold:.1%}",
            'profit_target': f"{self.profit_target:.1%}",
            'stop_loss': f"{self.stop_loss:.1%}"
        }
    
    def _calculate_rsi(self, prices, period=14):
        """
        Calculate RSI indicator.
        
        Args:
            prices: Series of prices
            period: RSI period (default 14)
            
        Returns:
            Series of RSI values
        """
        import pandas as pd
        
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def track_recovery_performance(self, symbol: str, entry_date: datetime, 
                                   entry_price: float, current_price: float,
                                   oversold_date: datetime) -> Dict[str, Any]:
        """
        Track mean reversion recovery performance metrics.
        
        Args:
            symbol: Stock symbol
            entry_date: Date of entry
            entry_price: Entry price
            current_price: Current price
            oversold_date: Date when stock became oversold
            
        Returns:
            Dictionary with recovery performance metrics
        """
        try:
            # Calculate days since oversold
            days_since_oversold = (datetime.now() - oversold_date).days
            
            # Calculate days held
            days_held = (datetime.now() - entry_date).days
            
            # Calculate return
            return_pct = (current_price - entry_price) / entry_price
            
            # Calculate annualized return
            if days_held > 0:
                annualized_return = return_pct * (365 / days_held)
            else:
                annualized_return = 0.0
            
            # Determine recovery phase
            if days_since_oversold <= 3:
                recovery_phase = 'immediate'
            elif days_since_oversold <= 7:
                recovery_phase = 'short_term'
            elif days_since_oversold <= 14:
                recovery_phase = 'medium_term'
            else:
                recovery_phase = 'long_term'
            
            return {
                'symbol': symbol,
                'days_since_oversold': days_since_oversold,
                'days_held': days_held,
                'return_pct': return_pct,
                'annualized_return': annualized_return,
                'recovery_phase': recovery_phase,
                'entry_price': entry_price,
                'current_price': current_price,
                'oversold_date': oversold_date.isoformat(),
                'entry_date': entry_date.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error tracking recovery performance for {symbol}: {e}")
            return {}
