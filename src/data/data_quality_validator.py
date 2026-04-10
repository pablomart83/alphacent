"""Data quality validation for market data."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.models import MarketData

logger = logging.getLogger(__name__)


@dataclass
class DataQualityIssue:
    """Represents a data quality issue."""
    
    issue_type: str
    severity: str  # "warning" or "error"
    message: str
    timestamp: datetime
    symbol: str
    details: Optional[Dict] = None


@dataclass
class DataQualityReport:
    """Report of data quality validation results."""
    
    symbol: str
    timestamp: datetime
    quality_score: float  # 0-100
    total_points: int
    issues: List[DataQualityIssue]
    metrics: Dict[str, any]
    
    def has_critical_issues(self) -> bool:
        """Check if report has any critical (error) issues."""
        return any(issue.severity == "error" for issue in self.issues)
    
    def has_warnings(self) -> bool:
        """Check if report has any warnings."""
        return any(issue.severity == "warning" for issue in self.issues)


class DataQualityValidator:
    """Validates market data quality and tracks metrics."""
    
    def __init__(self):
        """Initialize data quality validator."""
        self.validation_history: Dict[str, List[DataQualityReport]] = {}
        logger.info("Initialized DataQualityValidator")
    
    def validate_data_quality(
        self,
        data: List[MarketData],
        symbol: str
    ) -> DataQualityReport:
        """Validate data quality and return report.
        
        Args:
            data: List of market data points to validate
            symbol: Symbol being validated
            
        Returns:
            DataQualityReport with issues and metrics
        """
        issues = []
        metrics = {}
        
        if not data:
            issue = DataQualityIssue(
                issue_type="no_data",
                severity="error",
                message="No data available for validation",
                timestamp=datetime.now(),
                symbol=symbol
            )
            issues.append(issue)
            
            report = DataQualityReport(
                symbol=symbol,
                timestamp=datetime.now(),
                quality_score=0.0,
                total_points=0,
                issues=issues,
                metrics=metrics
            )
            self._store_report(symbol, report)
            return report
        
        # Run all quality checks
        issues.extend(self._check_missing_data_gaps(data, symbol))
        issues.extend(self._check_price_jumps(data, symbol))
        issues.extend(self._check_zero_volume(data, symbol))
        issues.extend(self._check_stale_data(data, symbol))
        issues.extend(self._check_duplicate_timestamps(data, symbol))
        issues.extend(self._check_null_values(data, symbol))
        issues.extend(self._check_high_low_inversion(data, symbol))
        
        # Calculate metrics
        metrics = self._calculate_metrics(data, issues)
        
        # Calculate quality score (0-100)
        quality_score = self._calculate_quality_score(data, issues)
        
        # Create report
        report = DataQualityReport(
            symbol=symbol,
            timestamp=datetime.now(),
            quality_score=quality_score,
            total_points=len(data),
            issues=issues,
            metrics=metrics
        )
        
        # Store report in history
        self._store_report(symbol, report)
        self._persist_report_to_db(symbol, report)
        
        # Log summary
        if report.has_critical_issues():
            logger.error(
                f"Data quality validation for {symbol}: "
                f"CRITICAL - Score: {quality_score:.1f}/100, "
                f"Issues: {len(issues)}"
            )
        elif report.has_warnings():
            logger.warning(
                f"Data quality validation for {symbol}: "
                f"Score: {quality_score:.1f}/100, "
                f"Issues: {len(issues)}"
            )
        else:
            logger.info(
                f"Data quality validation for {symbol}: "
                f"PASSED - Score: {quality_score:.1f}/100"
            )
        
        return report
    
    def _check_missing_data_gaps(
        self,
        data: List[MarketData],
        symbol: str
    ) -> List[DataQualityIssue]:
        """Check for missing data gaps > 1 day.
        
        Note: Gap thresholds vary by asset class:
        - Crypto (24/7 markets): Flag gaps > 1 day
        - Stocks/ETFs (weekends/holidays): Flag gaps > 5 days
        - Forex (weekends only): Flag gaps > 3 days
        """
        issues = []
        
        if len(data) < 2:
            return issues
        
        # Determine asset class from symbol
        is_crypto = self._is_crypto_symbol(symbol)
        is_forex = self._is_forex_symbol(symbol)
        
        # Set gap threshold based on asset class
        if is_crypto:
            gap_threshold = timedelta(days=1)  # Crypto trades 24/7
        elif is_forex:
            gap_threshold = timedelta(days=3)  # Forex closed on weekends
        else:
            gap_threshold = timedelta(days=5)  # Stocks closed weekends + holidays
        
        # Sort by timestamp
        sorted_data = sorted(data, key=lambda d: d.timestamp)
        
        for i in range(1, len(sorted_data)):
            prev_ts = sorted_data[i-1].timestamp
            curr_ts = sorted_data[i].timestamp
            
            # Calculate gap
            gap = curr_ts - prev_ts
            
            # Check if gap exceeds threshold
            if gap > gap_threshold:
                issue = DataQualityIssue(
                    issue_type="missing_data_gap",
                    severity="warning",
                    message=f"Data gap of {gap.days} days detected",
                    timestamp=datetime.now(),
                    symbol=symbol,
                    details={
                        "gap_start": prev_ts.isoformat(),
                        "gap_end": curr_ts.isoformat(),
                        "gap_days": gap.days,
                        "asset_class": "crypto" if is_crypto else "forex" if is_forex else "stock"
                    }
                )
                issues.append(issue)
        
        return issues
    
    def _is_crypto_symbol(self, symbol: str) -> bool:
        """Check if symbol is a cryptocurrency."""
        try:
            from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO
            crypto_set = set(DEMO_ALLOWED_CRYPTO)
            # Also match USD-suffixed variants (BTCUSD, ETHUSD, etc.)
            sym = symbol.upper()
            return sym in crypto_set or sym.replace("USD", "") in crypto_set
        except ImportError:
            crypto_symbols = [
                "BTC", "BTCUSD", "ETH", "ETHUSD", "XRP", "XRPUSD",
                "LTC", "LTCUSD", "BCH", "BCHUSD", "ADA", "ADAUSD",
                "DOT", "DOTUSD", "LINK", "LINKUSD", "SOL", "SOLUSD",
                "AVAX", "AVAXUSD", "NEAR", "NEARUSD", "DOGE", "DOGEUSD",
            ]
            return symbol.upper() in crypto_symbols
    
    def _is_forex_symbol(self, symbol: str) -> bool:
        """Check if symbol is a forex pair."""
        try:
            from src.core.tradeable_instruments import DEMO_ALLOWED_FOREX
            return symbol.upper() in set(DEMO_ALLOWED_FOREX)
        except ImportError:
            forex_symbols = [
                "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
                "USDCHF", "NZDUSD", "EURGBP",
            ]
            return symbol.upper() in forex_symbols
    
    def _check_price_jumps(
        self,
        data: List[MarketData],
        symbol: str
    ) -> List[DataQualityIssue]:
        """Check for abnormal price jumps (asset-class-aware thresholds)."""
        issues = []

        if len(data) < 2:
            return issues

        # Asset-class-aware price jump thresholds
        is_crypto = self._is_crypto_symbol(symbol)
        is_forex = self._is_forex_symbol(symbol)

        if is_crypto:
            jump_threshold = 0.50  # 50% - crypto is highly volatile
        elif is_forex:
            jump_threshold = 0.05  # 5% - forex rarely moves more than this
        else:
            jump_threshold = 0.20  # 20% - stocks (potential splits)

        # Sort by timestamp
        sorted_data = sorted(data, key=lambda d: d.timestamp)

        for i in range(1, len(sorted_data)):
            prev_close = sorted_data[i-1].close
            curr_close = sorted_data[i].close

            # Calculate price change percentage
            if prev_close > 0:
                price_change_pct = abs((curr_close - prev_close) / prev_close)

                if price_change_pct > jump_threshold:
                    issue = DataQualityIssue(
                        issue_type="price_jump",
                        severity="warning",
                        message=f"Large price jump of {price_change_pct*100:.1f}% detected (threshold: {jump_threshold*100:.0f}%)",
                        timestamp=datetime.now(),
                        symbol=symbol,
                        details={
                            "prev_close": prev_close,
                            "curr_close": curr_close,
                            "change_pct": price_change_pct * 100,
                            "threshold_pct": jump_threshold * 100,
                            "timestamp": sorted_data[i].timestamp.isoformat()
                        }
                    )
                    issues.append(issue)

        return issues
    
    def _check_zero_volume(
        self,
        data: List[MarketData],
        symbol: str
    ) -> List[DataQualityIssue]:
        """Check for zero volume days."""
        issues = []

        # Skip zero volume check for forex (no volume data available)
        if self._is_forex_symbol(symbol):
            return issues

        zero_volume_count = 0
        for point in data:
            if point.volume == 0:
                zero_volume_count += 1

        # If more than 5% of data has zero volume, flag it
        if len(data) > 0:
            zero_volume_pct = (zero_volume_count / len(data)) * 100

            if zero_volume_pct > 5:
                issue = DataQualityIssue(
                    issue_type="zero_volume",
                    severity="warning",
                    message=f"{zero_volume_pct:.1f}% of data points have zero volume",
                    timestamp=datetime.now(),
                    symbol=symbol,
                    details={
                        "zero_volume_count": zero_volume_count,
                        "total_points": len(data),
                        "zero_volume_pct": zero_volume_pct
                    }
                )
                issues.append(issue)

        return issues
    def _check_high_low_inversion(self, data: List[MarketData], symbol: str) -> List[DataQualityIssue]:
        """Check for high < low (inverted OHLC data, common in FMP forex)."""
        issues = []
        inverted_count = 0
        for point in data:
            if point.high < point.low:
                inverted_count += 1

        if inverted_count > 0 and len(data) > 0:
            pct = (inverted_count / len(data)) * 100
            severity = "error" if pct > 50 else "warning"
            issues.append(DataQualityIssue(
                issue_type="high_low_inversion",
                severity=severity,
                message=f"{pct:.1f}% of bars have high < low (inverted OHLC)",
                timestamp=datetime.now(),
                symbol=symbol,
                details={"inverted_count": inverted_count, "total": len(data), "pct": pct}
            ))
        return issues
    
    def _check_stale_data(
        self,
        data: List[MarketData],
        symbol: str
    ) -> List[DataQualityIssue]:
        """Check for stale data (> 24 hours old for daily data)."""
        issues = []
        
        if not data:
            return issues
        
        # Find most recent data point
        most_recent = max(data, key=lambda d: d.timestamp)
        
        # Check age
        now = datetime.now()
        
        # Handle timezone-aware timestamps
        if most_recent.timestamp.tzinfo is not None:
            from datetime import timezone
            now = datetime.now(timezone.utc)
            if most_recent.timestamp.tzinfo != timezone.utc:
                now = now.astimezone(most_recent.timestamp.tzinfo)
        
        age = now - most_recent.timestamp
        
        # For daily data, flag if > 2 days old (allowing for weekends)
        if age > timedelta(days=2):
            issue = DataQualityIssue(
                issue_type="stale_data",
                severity="warning",
                message=f"Most recent data is {age.days} days old",
                timestamp=datetime.now(),
                symbol=symbol,
                details={
                    "most_recent_timestamp": most_recent.timestamp.isoformat(),
                    "age_days": age.days,
                    "age_hours": age.total_seconds() / 3600
                }
            )
            issues.append(issue)
        
        return issues
    
    def _check_duplicate_timestamps(
        self,
        data: List[MarketData],
        symbol: str
    ) -> List[DataQualityIssue]:
        """Check for duplicate timestamps."""
        issues = []
        
        timestamps = [d.timestamp for d in data]
        unique_timestamps = set(timestamps)
        
        if len(timestamps) != len(unique_timestamps):
            duplicate_count = len(timestamps) - len(unique_timestamps)
            
            issue = DataQualityIssue(
                issue_type="duplicate_timestamps",
                severity="warning",
                message=f"{duplicate_count} duplicate timestamps detected",
                timestamp=datetime.now(),
                symbol=symbol,
                details={
                    "duplicate_count": duplicate_count,
                    "total_points": len(data)
                }
            )
            issues.append(issue)
        
        return issues
    
    def _check_null_values(
        self,
        data: List[MarketData],
        symbol: str
    ) -> List[DataQualityIssue]:
        """Check for null/NaN values in critical fields."""
        issues = []
        
        null_count = 0
        for point in data:
            # Check critical fields
            if (point.open is None or point.high is None or 
                point.low is None or point.close is None):
                null_count += 1
        
        if null_count > 0:
            issue = DataQualityIssue(
                issue_type="null_values",
                severity="error",
                message=f"{null_count} data points have null OHLC values",
                timestamp=datetime.now(),
                symbol=symbol,
                details={
                    "null_count": null_count,
                    "total_points": len(data)
                }
            )
            issues.append(issue)
        
        return issues
    
    def _calculate_metrics(
        self,
        data: List[MarketData],
        issues: List[DataQualityIssue]
    ) -> Dict[str, any]:
        """Calculate data quality metrics."""
        metrics = {
            "total_points": len(data),
            "total_issues": len(issues),
            "error_count": sum(1 for i in issues if i.severity == "error"),
            "warning_count": sum(1 for i in issues if i.severity == "warning"),
            "issue_types": {}
        }
        
        # Count issues by type
        for issue in issues:
            if issue.issue_type not in metrics["issue_types"]:
                metrics["issue_types"][issue.issue_type] = 0
            metrics["issue_types"][issue.issue_type] += 1
        
        # Calculate data coverage
        if data:
            sorted_data = sorted(data, key=lambda d: d.timestamp)
            date_range = (sorted_data[-1].timestamp - sorted_data[0].timestamp).days
            metrics["date_range_days"] = date_range
            metrics["data_points_per_day"] = len(data) / max(date_range, 1)
        
        return metrics
    
    def _calculate_quality_score(
        self,
        data: List[MarketData],
        issues: List[DataQualityIssue]
    ) -> float:
        """Calculate quality score (0-100).
        
        Scoring:
        - Start at 100
        - Deduct 20 points per error
        - Deduct 5 points per warning
        - Minimum score is 0
        """
        score = 100.0
        
        for issue in issues:
            if issue.severity == "error":
                score -= 20.0
            elif issue.severity == "warning":
                score -= 5.0
        
        return max(0.0, score)
    
    def _store_report(self, symbol: str, report: DataQualityReport) -> None:
        """Store report in validation history."""
        if symbol not in self.validation_history:
            self.validation_history[symbol] = []
        
        self.validation_history[symbol].append(report)
        
        # Keep only last 100 reports per symbol
        if len(self.validation_history[symbol]) > 100:
            self.validation_history[symbol] = self.validation_history[symbol][-100:]
    
    def get_latest_report(self, symbol: str) -> Optional[DataQualityReport]:
        """Get latest validation report for symbol."""
        if symbol in self.validation_history and self.validation_history[symbol]:
            return self.validation_history[symbol][-1]
        return None
    
    def get_all_reports(self) -> Dict[str, DataQualityReport]:
        """Get latest report for all symbols."""
        return {
            symbol: reports[-1]
            for symbol, reports in self.validation_history.items()
            if reports
        }

    def get_cached_report(self, symbol: str, max_age_hours: float = 24.0) -> Optional[DataQualityReport]:
        """Get a cached data quality report from DB if fresh enough.
        
        Args:
            symbol: Symbol to check
            max_age_hours: Maximum age in hours for the cached report
            
        Returns:
            DataQualityReport if a fresh cached report exists, None otherwise
        """
        try:
            from src.models.database import get_database
            from src.models.orm import DataQualityReportORM
            
            db = get_database()
            if db is None:
                return None
            session = db.get_session()
            try:
                record = session.query(DataQualityReportORM).filter_by(
                    symbol=symbol
                ).order_by(DataQualityReportORM.validated_at.desc()).first()
                
                if not record:
                    return None
                
                age_hours = (datetime.now() - record.validated_at).total_seconds() / 3600
                if age_hours > max_age_hours:
                    return None
                
                # Reconstruct DataQualityReport from DB record
                issues = []
                if record.issues_json:
                    for issue_data in record.issues_json:
                        issues.append(DataQualityIssue(
                            issue_type=issue_data.get('type', 'unknown'),
                            severity=issue_data.get('severity', 'warning'),
                            message=issue_data.get('message', ''),
                            timestamp=datetime.now(),
                            symbol=symbol,
                        ))
                
                return DataQualityReport(
                    symbol=symbol,
                    timestamp=record.validated_at,
                    quality_score=record.quality_score,
                    total_points=record.total_points,
                    issues=issues,
                    metrics=record.metrics_json or {},
                )
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"Could not get cached DQ report for {symbol}: {e}")
            return None

    def _persist_report_to_db(self, symbol: str, report: DataQualityReport) -> None:
        """Persist a data quality report to the database."""
        try:
            from src.models.database import get_database
            from src.models.orm import DataQualityReportORM
            
            db = get_database()
            if db is None:
                return
            session = db.get_session()
            try:
                # Upsert: update existing or insert new
                existing = session.query(DataQualityReportORM).filter_by(
                    symbol=symbol
                ).first()
                
                issues_json = [
                    {"type": i.issue_type, "severity": i.severity, "message": i.message}
                    for i in report.issues
                ]
                
                if existing:
                    existing.quality_score = report.quality_score
                    existing.total_points = report.total_points
                    existing.issue_count = len(report.issues)
                    existing.error_count = sum(1 for i in report.issues if i.severity == "error")
                    existing.warning_count = sum(1 for i in report.issues if i.severity == "warning")
                    existing.issues_json = issues_json
                    existing.metrics_json = report.metrics
                    existing.validated_at = datetime.now()
                else:
                    record = DataQualityReportORM(
                        symbol=symbol,
                        quality_score=report.quality_score,
                        total_points=report.total_points,
                        issue_count=len(report.issues),
                        error_count=sum(1 for i in report.issues if i.severity == "error"),
                        warning_count=sum(1 for i in report.issues if i.severity == "warning"),
                        issues_json=issues_json,
                        metrics_json=report.metrics,
                        validated_at=datetime.now(),
                    )
                    session.add(record)
                
                session.commit()
            except Exception as e:
                logger.debug(f"Could not persist DQ report for {symbol}: {e}")
                session.rollback()
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"Could not persist DQ report for {symbol}: {e}")
