"""
Fundamental Filter - Validates stocks against fundamental criteria.

Implements 5 fundamental checks:
1. Profitable: EPS > 0
2. Growing: Revenue growth > 0%
3. Reasonable valuation: P/E ratio within acceptable range
4. No excessive dilution: Share count change < 10%
5. Insider buying: Net insider buying > 0

Requires configurable number of checks to pass (default: 4 out of 5).
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from src.data.fundamental_data_provider import FundamentalData, FundamentalDataProvider

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """Result of a fundamental filter check."""
    check_name: str
    passed: bool
    value: Optional[float]
    threshold: Optional[float]
    reason: str


@dataclass
@dataclass
class FundamentalFilterReport:
    """Comprehensive report of fundamental filtering."""
    symbol: str
    passed: bool
    checks_passed: int
    checks_total: int
    min_required: int
    results: List[FilterResult]
    fundamental_data: Optional[FundamentalData]
    data_quality_score: float = 0.0  # 0-100, percentage of checks with valid data
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'symbol': self.symbol,
            'passed': self.passed,
            'checks_passed': self.checks_passed,
            'checks_total': self.checks_total,
            'min_required': self.min_required,
            'data_quality_score': self.data_quality_score,
            'results': [
                {
                    'check': r.check_name,
                    'passed': r.passed,
                    'value': r.value,
                    'threshold': r.threshold,
                    'reason': r.reason
                }
                for r in self.results
            ]
        }


class FundamentalFilter:
    """
    Filters stocks based on fundamental criteria.
    
    Uses cross-sectional tercile ranking from FundamentalRanker when available,
    falling back to absolute thresholds when ranking data isn't present.
    This ensures stocks are evaluated relative to peers, not against fixed
    cutoffs that break in different market regimes.
    """
    
    def __init__(self, config: Dict[str, Any], data_provider: FundamentalDataProvider):
        """
        Initialize filter.
        
        Args:
            config: Configuration dictionary with fundamental_filters section
            data_provider: FundamentalDataProvider instance
        """
        self.config = config
        self.data_provider = data_provider
        
        # Get database instance for logging
        from src.models.database import get_database
        self.database = get_database()
        
        # Get filter configuration
        filter_config = config.get('alpha_edge', {}).get('fundamental_filters', {})
        self.enabled = filter_config.get('enabled', True)
        self.min_checks_passed = filter_config.get('min_checks_passed', 3)
        self.min_market_cap = filter_config.get('min_market_cap', 500_000_000)
        
        # Individual check configurations
        checks_config = filter_config.get('checks', {})
        self.check_profitable = checks_config.get('profitable', True)
        self.check_growing = checks_config.get('growing', True)
        self.check_valuation = checks_config.get('reasonable_valuation', True)
        self.check_dilution = checks_config.get('no_dilution', True)
        self.check_insider = checks_config.get('insider_buying', True)
        
        # Cross-sectional ranking data (populated by set_ranker_results)
        self._ranker_results: Optional[Dict[str, Dict]] = None
        
        logger.info(f"FundamentalFilter initialized - Enabled: {self.enabled}, "
                   f"Min checks: {self.min_checks_passed}/5, Min market cap: ${self.min_market_cap:,.0f}")
    
    def set_ranker_results(self, rankings: Dict[str, Dict]) -> None:
        """
        Inject cross-sectional ranking results from FundamentalRanker.
        
        When set, the filter uses tercile-based pass/fail instead of absolute
        thresholds for valuation and quality checks. A stock in the top tercile
        (composite_score >= 66.7) passes; bottom tercile fails.
        
        Args:
            rankings: Output from FundamentalRanker.rank_universe()
        """
        self._ranker_results = rankings
        if rankings:
            logger.info(f"FundamentalFilter: loaded cross-sectional rankings for {len(rankings)} symbols")
    
    def filter_symbol(self, symbol: str, strategy_type: str = "default") -> FundamentalFilterReport:
        """
        Filter a symbol based on fundamental criteria.
        
        Args:
            symbol: Stock symbol to filter
            strategy_type: Type of strategy (affects valuation thresholds)
            
        Returns:
            FundamentalFilterReport with detailed results
        """
        if not self.enabled:
            # If filtering is disabled, pass everything
            return FundamentalFilterReport(
                symbol=symbol,
                passed=True,
                checks_passed=5,
                checks_total=5,
                min_required=self.min_checks_passed,
                results=[],
                fundamental_data=None,
                data_quality_score=100.0
            )
        
        # Asset classes without traditional fundamental data (earnings, P/E, revenue)
        # should bypass fundamental filtering entirely
        NON_FUNDAMENTAL_SYMBOLS = {
            # ETFs
            'SPY', 'QQQ', 'IWM', 'DIA', 'GLD', 'SLV', 'VTI', 'VOO',
            'XLE', 'XLF', 'XLK', 'XLU', 'XLV', 'XLI', 'XLP', 'XLY',
            'EFA', 'EEM', 'TLT', 'AGG', 'HYG',
            # Crypto
            'BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'AVAX', 'DOT', 'LINK',
            'NEAR', 'LTC', 'BCH', 'DOGE', 'SHIB', 'MATIC', 'UNI',
            # Forex
            'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF',
            'EURGBP', 'EURJPY', 'GBPJPY', 'NZDUSD',
            # Indices
            'SPX500', 'NSDQ100', 'DJ30', 'UK100', 'GER40',
            # Commodities
            'GOLD', 'SILVER', 'OIL', 'COPPER', 'NATGAS',
        }
        
        if symbol in NON_FUNDAMENTAL_SYMBOLS or strategy_type == "sector_rotation":
            logger.info(f"Exempting {symbol} from fundamental filter (non-stock asset class)")
            return FundamentalFilterReport(
                symbol=symbol,
                passed=True,
                checks_passed=5,
                checks_total=5,
                min_required=self.min_checks_passed,
                results=[
                    FilterResult(
                        check_name="etf_exemption",
                        passed=True,
                        value=None,
                        threshold=None,
                        reason="ETF or sector rotation strategy - fundamental checks not applicable"
                    )
                ],
                fundamental_data=None,
                data_quality_score=100.0
            )
        
        # Fetch fundamental data
        fundamental_data = self.data_provider.get_fundamental_data(symbol)
        
        if not fundamental_data:
            # Pass-through for well-known large-cap stocks when API data is unavailable
            # These stocks are too well-known to block on data availability alone
            LARGE_CAP_PASS_THROUGH = {
                'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'NVDA', 'META', 'TSLA',
                'BRK.B', 'JPM', 'V', 'JNJ', 'WMT', 'PG', 'MA', 'HD', 'UNH',
                'DIS', 'PYPL', 'NFLX', 'ADBE', 'CRM', 'INTC', 'CSCO', 'PEP',
                'KO', 'MCD', 'NKE', 'COST', 'BA', 'GE', 'AMD', 'QCOM', 'TGT',
                'LOW', 'SBUX', 'GS', 'MS', 'UBER', 'ABNB', 'PLTR', 'SNAP',
                'SPY', 'QQQ', 'IWM', 'DIA', 'VOO', 'VTI',
            }
            if symbol.upper() in LARGE_CAP_PASS_THROUGH:
                logger.info(
                    f"Fundamental data unavailable for {symbol} but it's a known large-cap stock. "
                    f"Passing filter with reduced confidence (data_availability pass-through)."
                )
                return FundamentalFilterReport(
                    symbol=symbol,
                    passed=True,
                    checks_passed=3,
                    checks_total=5,
                    min_required=self.min_checks_passed,
                    results=[
                        FilterResult(
                            check_name="data_availability",
                            passed=True,
                            value=None,
                            threshold=None,
                            reason="Large-cap pass-through: fundamental data unavailable but stock is well-known"
                        )
                    ],
                    fundamental_data=None,
                    data_quality_score=50.0
                )
            logger.warning(f"No fundamental data available for {symbol}, failing filter")
            return FundamentalFilterReport(
                symbol=symbol,
                passed=False,
                checks_passed=0,
                checks_total=5,
                min_required=self.min_checks_passed,
                results=[
                    FilterResult(
                        check_name="data_availability",
                        passed=False,
                        value=None,
                        threshold=None,
                        reason="No fundamental data available"
                    )
                ],
                fundamental_data=None,
                data_quality_score=0.0
            )
        
        # Calculate data quality score (% of critical fields with valid data)
        data_quality_score = self._calculate_data_quality_score(fundamental_data)
        
        # Skip fundamental filter if data quality is too low (<40%)
        if data_quality_score < 40.0:
            logger.warning(f"Data quality too low for {symbol} ({data_quality_score:.1f}%), skipping fundamental filter")
            return FundamentalFilterReport(
                symbol=symbol,
                passed=True,  # Pass by default when data quality is insufficient
                checks_passed=0,
                checks_total=5,
                min_required=self.min_checks_passed,
                results=[
                    FilterResult(
                        check_name="data_quality",
                        passed=True,
                        value=data_quality_score,
                        threshold=40.0,
                        reason=f"Data quality {data_quality_score:.1f}% < 40% - insufficient data to judge, passing by default"
                    )
                ],
                fundamental_data=fundamental_data,
                data_quality_score=data_quality_score
            )
        
        # Check minimum market cap (avoid micro-caps)
        if fundamental_data.market_cap is not None and fundamental_data.market_cap < self.min_market_cap:
            logger.info(f"{symbol} failed market cap filter: ${fundamental_data.market_cap:,.0f} < ${self.min_market_cap:,.0f}")
            return FundamentalFilterReport(
                symbol=symbol,
                passed=False,
                checks_passed=0,
                checks_total=5,
                min_required=self.min_checks_passed,
                results=[
                    FilterResult(
                        check_name="market_cap",
                        passed=False,
                        value=fundamental_data.market_cap,
                        threshold=self.min_market_cap,
                        reason=f"Market cap ${fundamental_data.market_cap:,.0f} < ${self.min_market_cap:,.0f} (micro-cap)"
                    )
                ],
                fundamental_data=fundamental_data,
                data_quality_score=data_quality_score
            )
        
        # Run all checks
        results = []
        
        if self.check_profitable:
            results.append(self._check_profitable(fundamental_data))
        
        if self.check_growing:
            results.append(self._check_growing(fundamental_data))
        
        if self.check_valuation:
            results.append(self._check_valuation(fundamental_data, strategy_type))
        
        if self.check_dilution:
            results.append(self._check_dilution(fundamental_data))
        
        if self.check_insider:
            results.append(self._check_insider_buying(fundamental_data))
        
        # Calculate pass/fail
        checks_passed = sum(1 for r in results if r.passed)
        checks_total = len(results)
        passed = checks_passed >= self.min_checks_passed
        
        report = FundamentalFilterReport(
            symbol=symbol,
            passed=passed,
            checks_passed=checks_passed,
            checks_total=checks_total,
            min_required=self.min_checks_passed,
            results=results,
            fundamental_data=fundamental_data,
            data_quality_score=data_quality_score
        )
        
        if passed:
            logger.info(f"{symbol} passed fundamental filter ({checks_passed}/{checks_total} checks, "
                       f"data quality: {data_quality_score:.1f}%)")
        else:
            logger.info(f"{symbol} failed fundamental filter ({checks_passed}/{checks_total} checks, "
                       f"need {self.min_checks_passed}, data quality: {data_quality_score:.1f}%)")
        
        # Log to database
        self._log_filter_result(symbol, strategy_type, report)
        
        return report
    
    def _log_filter_result(self, symbol: str, strategy_type: str, report: FundamentalFilterReport) -> None:
        """Log filter result to database."""
        try:
            from src.models.orm import FundamentalFilterLogORM
            from datetime import datetime
            
            # Extract individual check results
            check_results = {r.check_name: r.passed for r in report.results}
            failure_reasons = [r.reason for r in report.results if not r.passed]
            
            log_entry = FundamentalFilterLogORM(
                symbol=symbol,
                strategy_type=strategy_type,
                passed=report.passed,
                checks_passed=report.checks_passed,
                checks_failed=report.checks_total - report.checks_passed,
                profitable=check_results.get('profitable'),
                growing=check_results.get('growing'),
                valuation=check_results.get('valuation'),
                dilution=check_results.get('dilution'),
                insider_buying=check_results.get('insider_buying'),
                failure_reasons=failure_reasons if failure_reasons else None,
                data_quality_score=report.data_quality_score,
                timestamp=datetime.now()
            )
            
            session = self.database.get_session()
            try:
                session.add(log_entry)
                session.commit()
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Failed to log fundamental filter result: {e}")
    
    def _calculate_data_quality_score(self, data: FundamentalData) -> float:
        """
        Calculate data quality score (0-100) based on availability of critical fields.
        
        Critical fields checked:
        - EPS (20%)
        - Revenue growth (20%)
        - P/E ratio (20%)
        - ROE (15%)
        - Market cap (15%)
        - Debt/Equity (10%)
        
        Args:
            data: FundamentalData object
            
        Returns:
            Quality score from 0-100
        """
        score = 0.0
        
        # Critical fields (20% each)
        if data.eps is not None:
            score += 20.0
        if data.revenue_growth is not None:
            score += 20.0
        if data.pe_ratio is not None:
            score += 20.0
        
        # Important fields (15% each)
        if data.roe is not None:
            score += 15.0
        if data.market_cap is not None:
            score += 15.0
        
        # Nice-to-have fields (10%)
        if data.debt_to_equity is not None:
            score += 10.0
        
        return score
    
    def _check_profitable(self, data: FundamentalData) -> FilterResult:
        """Check if company is profitable (EPS > 0)."""
        if data.eps is None:
            # EPS is critical - fail if missing
            return FilterResult(
                check_name="profitable",
                passed=False,
                value=None,
                threshold=0.0,
                reason="EPS data not available (critical check)"
            )
        
        passed = data.eps > 0
        return FilterResult(
            check_name="profitable",
            passed=passed,
            value=data.eps,
            threshold=0.0,
            reason=f"EPS {data.eps:.2f} {'>' if passed else '<='} 0"
        )
    
    def _check_growing(self, data: FundamentalData) -> FilterResult:
        """Check if company is growing (revenue growth > 0%)."""
        if data.revenue_growth is None:
            # Revenue growth is important - if missing, we can't verify growth
            # However, don't auto-fail - pass by default to avoid over-restriction
            return FilterResult(
                check_name="growing",
                passed=True,
                value=None,
                threshold=0.0,
                reason="Revenue growth data not available (passed by default)"
            )
        
        passed = data.revenue_growth > 0
        return FilterResult(
            check_name="growing",
            passed=passed,
            value=data.revenue_growth * 100,  # Convert to percentage
            threshold=0.0,
            reason=f"Revenue growth {data.revenue_growth*100:.1f}% {'>' if passed else '<='} 0%"
        )
    
    def _check_valuation(self, data: FundamentalData, strategy_type: str) -> FilterResult:
        """
        Check valuation using cross-sectional ranking (preferred) or absolute thresholds (fallback).
        
        When ranker results are available, a stock passes if its composite score
        is in the top two terciles (>= 33rd percentile). This automatically adapts
        to market conditions — in a high-P/E market, relatively cheap stocks still pass.
        
        Falls back to absolute P/E thresholds when ranking data isn't available.
        """
        # --- Cross-sectional ranking path (preferred) ---
        if self._ranker_results and data.symbol in self._ranker_results:
            ranking = self._ranker_results[data.symbol]
            composite = ranking.get("composite_score", 50.0)
            value_rank = ranking.get("value_rank", 50.0)
            quality_rank = ranking.get("quality_rank", 50.0)
            f_score = ranking.get("raw_metrics", {}).get("piotroski_f_score")
            
            # Tercile gate: bottom tercile (< 33.3) fails for value strategies
            # For non-value strategies, use a more lenient threshold (< 20)
            if strategy_type in ["value", "mean_reversion", "quality_mean_reversion"]:
                # Value strategies: must be in top 2 terciles by value rank
                # AND pass F-Score quality gate (>= 7) when available
                if value_rank < 33.3:
                    return FilterResult(
                        check_name="reasonable_valuation",
                        passed=False,
                        value=value_rank,
                        threshold=33.3,
                        reason=f"Value rank {value_rank:.1f} in bottom tercile (< 33.3) — "
                               f"relatively expensive vs peers"
                    )
                # F-Score quality gate for value stocks
                if f_score is not None and f_score < 7:
                    return FilterResult(
                        check_name="reasonable_valuation",
                        passed=False,
                        value=f_score,
                        threshold=7,
                        reason=f"Piotroski F-Score {f_score}/9 < 7 — "
                               f"value stock fails quality gate (value rank {value_rank:.1f})"
                    )
                return FilterResult(
                    check_name="reasonable_valuation",
                    passed=True,
                    value=value_rank,
                    threshold=33.3,
                    reason=f"Value rank {value_rank:.1f} (top {100-value_rank:.0f}%), "
                           f"F-Score {f_score if f_score is not None else 'N/A'}/9, "
                           f"composite {composite:.1f} — cross-sectional pass"
                )
            
            # Momentum/trend: skip valuation (price action driven)
            if strategy_type in ["momentum", "trend_following", "breakout"]:
                return FilterResult(
                    check_name="reasonable_valuation",
                    passed=True,
                    value=composite,
                    threshold=None,
                    reason=f"Valuation check skipped for {strategy_type} (composite {composite:.1f})"
                )
            
            # Growth/earnings momentum: use composite score, lenient threshold
            if strategy_type in ["growth", "earnings_momentum"]:
                passed = composite >= 20.0  # Only reject bottom quintile
                return FilterResult(
                    check_name="reasonable_valuation",
                    passed=passed,
                    value=composite,
                    threshold=20.0,
                    reason=f"Composite score {composite:.1f} {'≥' if passed else '<'} 20 "
                           f"(growth strategy, cross-sectional)"
                )
            
            # Default: composite score must be above bottom tercile
            passed = composite >= 33.3
            return FilterResult(
                check_name="reasonable_valuation",
                passed=passed,
                value=composite,
                threshold=33.3,
                reason=f"Composite score {composite:.1f} {'≥' if passed else '<'} 33.3 "
                       f"(cross-sectional tercile)"
            )
        
        # --- Absolute threshold fallback (no ranking data) ---
        if data.pe_ratio is None:
            return FilterResult(
                check_name="reasonable_valuation",
                passed=True,
                value=None,
                threshold=None,
                reason="P/E ratio data not available (passed by default)"
            )
        
        # Momentum/trend strategies: Skip P/E check
        if strategy_type in ["momentum", "trend_following", "breakout"]:
            return FilterResult(
                check_name="reasonable_valuation",
                passed=True,
                value=data.pe_ratio,
                threshold=None,
                reason=f"P/E check skipped for {strategy_type} strategy (price action driven)"
            )
        
        if strategy_type == "sector_rotation":
            return FilterResult(
                check_name="reasonable_valuation",
                passed=True,
                value=data.pe_ratio,
                threshold=None,
                reason="P/E check not applicable for sector ETFs"
            )
        
        # Value/mean reversion: strict
        if strategy_type in ["value", "mean_reversion", "quality_mean_reversion"]:
            threshold = 30.0
            if data.pe_ratio < 0:
                return FilterResult(
                    check_name="reasonable_valuation",
                    passed=False,
                    value=data.pe_ratio,
                    threshold=threshold,
                    reason=f"P/E ratio {data.pe_ratio:.1f} is negative (unprofitable)"
                )
            passed = 0 < data.pe_ratio < threshold
            return FilterResult(
                check_name="reasonable_valuation",
                passed=passed,
                value=data.pe_ratio,
                threshold=threshold,
                reason=f"P/E {data.pe_ratio:.1f} {'<' if passed else '>='} {threshold} "
                       f"(value strategy, absolute fallback)"
            )
        
        # Growth/earnings momentum: flexible
        if strategy_type in ["growth", "earnings_momentum"]:
            threshold = 70.0
            if data.pe_ratio < 0:
                return FilterResult(
                    check_name="reasonable_valuation",
                    passed=False,
                    value=data.pe_ratio,
                    threshold=threshold,
                    reason=f"P/E ratio {data.pe_ratio:.1f} is negative (unprofitable)"
                )
            passed = 0 < data.pe_ratio < threshold
            return FilterResult(
                check_name="reasonable_valuation",
                passed=passed,
                value=data.pe_ratio,
                threshold=threshold,
                reason=f"P/E {data.pe_ratio:.1f} {'<' if passed else '>='} {threshold} "
                       f"(growth strategy, absolute fallback)"
            )
        
        # Default: moderate
        threshold = 50.0
        if data.pe_ratio < 0:
            return FilterResult(
                check_name="reasonable_valuation",
                passed=False,
                value=data.pe_ratio,
                threshold=threshold,
                reason=f"P/E ratio {data.pe_ratio:.1f} is negative (unprofitable)"
            )
        
        passed = 0 < data.pe_ratio < threshold
        return FilterResult(
            check_name="reasonable_valuation",
            passed=passed,
            value=data.pe_ratio,
            threshold=threshold,
            reason=f"P/E {data.pe_ratio:.1f} {'<' if passed else '>='} {threshold} (absolute fallback)"
        )
    
    def _check_dilution(self, data: FundamentalData) -> FilterResult:
        """Check for excessive share dilution (share count change < 10%)."""
        if data.shares_change_percent is None:
            # If we don't have dilution data, we'll pass this check
            # (conservative approach - don't reject without evidence)
            return FilterResult(
                check_name="no_dilution",
                passed=True,
                value=None,
                threshold=10.0,
                reason="Share dilution data not available (passed by default)"
            )
        
        threshold = 10.0
        passed = abs(data.shares_change_percent) < threshold
        return FilterResult(
            check_name="no_dilution",
            passed=passed,
            value=data.shares_change_percent,
            threshold=threshold,
            reason=f"Share count change {data.shares_change_percent:.1f}% "
                   f"{'<' if passed else '>='} {threshold}%"
        )
    
    def _check_insider_buying(self, data: FundamentalData) -> FilterResult:
        """Check for insider buying (net insider buying > 0)."""
        if data.insider_net_buying is None:
            # If we don't have insider data, we'll pass this check
            # (conservative approach - don't reject without evidence)
            return FilterResult(
                check_name="insider_buying",
                passed=True,
                value=None,
                threshold=0.0,
                reason="Insider trading data not available (passed by default)"
            )
        
        passed = data.insider_net_buying > 0
        return FilterResult(
            check_name="insider_buying",
            passed=passed,
            value=data.insider_net_buying,
            threshold=0.0,
            reason=f"Net insider buying ${data.insider_net_buying:,.0f} "
                   f"{'>' if passed else '<='} $0"
        )
    
    def filter_symbols(self, symbols: List[str], strategy_type: str = "default") -> Dict[str, FundamentalFilterReport]:
        """
        Filter multiple symbols.
        
        Args:
            symbols: List of stock symbols
            strategy_type: Type of strategy
            
        Returns:
            Dictionary mapping symbols to filter reports
        """
        results = {}
        for symbol in symbols:
            results[symbol] = self.filter_symbol(symbol, strategy_type)
        return results
    
    def get_passed_symbols(self, symbols: List[str], strategy_type: str = "default") -> List[str]:
        """
        Get list of symbols that pass the filter.
        
        Args:
            symbols: List of stock symbols
            strategy_type: Type of strategy
            
        Returns:
            List of symbols that passed
        """
        results = self.filter_symbols(symbols, strategy_type)
        return [symbol for symbol, report in results.items() if report.passed]
