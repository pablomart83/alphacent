"""Strategy Proposer for autonomous strategy generation."""

import logging
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.dataclasses import Strategy, RiskConfig, PerformanceMetrics
from src.models.enums import StrategyStatus
from src.strategy.market_analyzer import MarketStatisticsAnalyzer
from src.strategy.performance_tracker import StrategyPerformanceTracker
from src.strategy.strategy_templates import StrategyTemplateLibrary, StrategyTemplate, MarketRegime, StrategyType
from src.utils.symbol_mapper import DAILY_ONLY_SYMBOLS as _DAILY_ONLY_SYMBOLS

logger = logging.getLogger(__name__)


class DataQuality(str, Enum):
    """Data quality classifications based on available days (for 2-year lookback)."""
    EXCELLENT = "excellent"  # 600+ days (~2 years)
    GOOD = "good"            # 365-599 days (~1 year)
    FAIR = "fair"            # 180-364 days (~6 months)
    POOR = "poor"            # <180 days


class StrategyProposer:
    """Autonomously proposes new trading strategies based on market analysis."""
    
    def __init__(self, llm_service: Optional[LLMService], market_data: MarketDataManager):
        """
        Initialize Strategy Proposer.

        Args:
            llm_service: LLM service for strategy generation
            market_data: Market data manager for regime detection
        """
        self.llm_service = llm_service
        self.market_data = market_data
        self.market_analyzer = MarketStatisticsAnalyzer(market_data)
        self.performance_tracker = StrategyPerformanceTracker()
        self.template_library = StrategyTemplateLibrary()
        self._trading_symbols = self._load_trading_symbols()
        # Performance feedback state (populated by apply_performance_feedback)
        self._template_weights: Dict[str, float] = {}
        self._symbol_scores: Dict[str, float] = {}
        self._regime_template_preferences: Dict[str, Dict[str, float]] = {}
        # Cache for market statistics (avoids re-analyzing 118 symbols every cycle)
        self._market_stats_cache = None  # Dict with 'market_statistics', 'indicator_distributions', 'timestamp'
        self._market_stats_cache_ttl = 7200  # 2 hours
        self._market_stats_cache_path = "config/.market_stats_cache.json"
        self._load_market_stats_from_disk()  # Restore cache from disk on startup
        # Zero-trade blacklist: tracks template+symbol combos that produce 0 trades
        # in walk-forward. Prevents wasting proposal slots on dead combinations.
        # Persisted to JSON with per-entry TTL (7 days) so it survives restarts
        # but auto-expires as market conditions change.
        self._zero_trade_blacklist: Dict[Tuple[str, str], int] = {}
        self._zero_trade_blacklist_timestamps: Dict[Tuple[str, str], str] = {}  # ISO timestamps
        self._zero_trade_blacklist_threshold = 2  # Blacklist after 2 consecutive 0-trade results (not 1)
        self._zero_trade_blacklist_ttl_days = 3   # Entries expire after 3 days (was 7 — markets change fast)
        self._zero_trade_blacklist_path = "config/.zero_trade_blacklist.json"
        self._load_blacklist_from_disk()
        # Rejection blacklist: tracks template+symbol combos that are repeatedly
        # rejected at activation. Prevents wasting proposal slots on dead strategies.
        # Persisted to JSON with per-entry cooldown (30 days) so it survives restarts
        # but auto-expires to allow re-evaluation.
        self._rejection_blacklist: Dict[Tuple[str, str], int] = {}  # (template, symbol) -> consecutive rejections
        self._rejection_blacklist_timestamps: Dict[Tuple[str, str], str] = {}  # ISO timestamps
        self._rejection_blacklist_threshold = 3  # Blacklist after 3 consecutive rejections
        self._rejection_blacklist_cooldown_days = 30  # Entries expire after 30 days
        self._rejection_blacklist_path = "config/.rejection_blacklist.json"
        self._load_rejection_blacklist_from_disk()
        # Walk-forward results cache: avoids re-running expensive WF validation
        # on the same (template, symbol) combo when data hasn't changed.
        # Key: (template_name, primary_symbol), Value: (wf_results_tuple, timestamp)
        self._wf_results_cache: Dict[Tuple[str, str], Tuple[tuple, float]] = {}
        self._wf_cache_ttl = 172800  # 2 days (was 7 — give templates another shot sooner as data shifts)
        # WF failed cache: persisted to disk so failures survive restarts.
        # Without this, every restart re-proposes the same combos, re-runs WF,
        # they fail again, wasting compute and blocking new combos from slots.
        self._wf_failed_path = "config/.wf_failed_cache.json"
        self._load_wf_failed_from_disk()
        # WF validated combos: persisted record of (template, symbol) pairs that
        # passed walk-forward with positive Sharpe. Used to build watchlists from
        # proven combos rather than just scored guesses. TTL 14 days.
        self._wf_validated_path = "config/.wf_validated_combos.json"
        self._wf_validated: Dict[Tuple[str, str], Dict] = {}  # (template, symbol) -> {sharpe, trades, timestamp}
        self._wf_validated_ttl_days = 14
        self._load_wf_validated_from_disk()
        # Fundamental scoring cache: caches quarterly data and insider net purchases
        # for AE symbol scoring. TTL 24h to avoid excessive FMP API calls.
        self._fundamental_scoring_cache: Dict[str, Dict] = {}  # symbol -> {data, timestamp}
        self._fundamental_scoring_cache_ttl = 86400  # 24 hours
        self._fundamental_data_provider = None  # Lazy init
        # Phase 2: Cross-sectional fundamental ranker
        self._fundamental_ranker = None  # Lazy init
        self._ranker_results: Optional[Dict[str, Dict]] = None  # Cached ranking results
        # Proposal tracking: persistent counters for how many times each template
        # has been proposed (pre-WF) and approved (post-WF). Used for the Templates
        # dashboard and for research/troubleshooting.
        self._proposal_tracker_path = "config/.proposal_tracker.json"
        self._proposal_tracker: Dict[str, Dict] = {}  # template_name -> {proposed: N, approved: N, last_proposed: iso, last_approved: iso}
        self._load_proposal_tracker()
        logger.info(f"StrategyProposer initialized with {len(self._trading_symbols)} trading symbols, {len(self._wf_validated)} validated combos")

    def _load_blacklist_from_disk(self):
        """Load zero-trade blacklist from JSON, expiring stale entries."""
        import json
        from pathlib import Path
        try:
            path = Path(self._zero_trade_blacklist_path)
            if not path.exists():
                return
            with open(path, 'r') as f:
                data = json.load(f)
            
            now = datetime.now()
            loaded = 0
            expired = 0
            for entry in data.get('entries', []):
                # Support both old (asset_class) and new (symbol) format
                symbol = entry.get('symbol', entry.get('asset_class', 'unknown'))
                key = (entry['template'], symbol)
                ts = datetime.fromisoformat(entry['timestamp'])
                age_days = (now - ts).days
                if age_days < self._zero_trade_blacklist_ttl_days:
                    self._zero_trade_blacklist[key] = entry['count']
                    self._zero_trade_blacklist_timestamps[key] = entry['timestamp']
                    loaded += 1
                else:
                    expired += 1
            
            if loaded or expired:
                logger.info(f"Loaded {loaded} blacklist entries from disk ({expired} expired)")
        except Exception as e:
            logger.debug(f"Could not load blacklist from disk: {e}")

    def _save_blacklist_to_disk(self):
        """Persist zero-trade blacklist to JSON."""
        import json
        from pathlib import Path
        try:
            entries = []
            for (template, symbol), count in self._zero_trade_blacklist.items():
                ts = self._zero_trade_blacklist_timestamps.get(
                    (template, symbol), datetime.now().isoformat()
                )
                entries.append({
                    'template': template,
                    'symbol': symbol,
                    'count': count,
                    'timestamp': ts,
                })
            
            path = Path(self._zero_trade_blacklist_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                json.dump({'entries': entries, 'updated': datetime.now().isoformat()}, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not save blacklist to disk: {e}")
    def _load_rejection_blacklist_from_disk(self):
        """Load rejection blacklist from JSON, expiring stale entries."""
        import json
        from pathlib import Path
        try:
            path = Path(self._rejection_blacklist_path)
            if not path.exists():
                return
            with open(path, 'r') as f:
                data = json.load(f)

            now = datetime.now()
            loaded = 0
            expired = 0
            for entry in data.get('entries', []):
                symbol = entry.get('symbol', 'unknown')
                key = (entry['template'], symbol)
                ts = datetime.fromisoformat(entry['timestamp'])
                age_days = (now - ts).days
                if age_days < self._rejection_blacklist_cooldown_days:
                    self._rejection_blacklist[key] = entry['count']
                    self._rejection_blacklist_timestamps[key] = entry['timestamp']
                    loaded += 1
                else:
                    expired += 1

            if loaded or expired:
                logger.info(f"Loaded {loaded} rejection blacklist entries from disk ({expired} expired)")
        except Exception as e:
            logger.debug(f"Could not load rejection blacklist from disk: {e}")
    def _save_rejection_blacklist_to_disk(self):
        """Persist rejection blacklist to JSON."""
        import json
        from pathlib import Path
        try:
            entries = []
            for (template, symbol), count in self._rejection_blacklist.items():
                ts = self._rejection_blacklist_timestamps.get(
                    (template, symbol), datetime.now().isoformat()
                )
                entries.append({
                    'template': template,
                    'symbol': symbol,
                    'count': count,
                    'timestamp': ts,
                })

            path = Path(self._rejection_blacklist_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                json.dump({'entries': entries, 'updated': datetime.now().isoformat()}, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not save rejection blacklist to disk: {e}")
    def record_rejection(self, template_name: str, symbol: str) -> None:
        """Increment rejection counter for a template+symbol combo. Called by Autonomous_Manager after activation rejection."""
        key = (template_name, symbol)
        self._rejection_blacklist[key] = self._rejection_blacklist.get(key, 0) + 1
        self._rejection_blacklist_timestamps[key] = datetime.now().isoformat()
        self._save_rejection_blacklist_to_disk()
        count = self._rejection_blacklist[key]
        if count >= self._rejection_blacklist_threshold:
            logger.info(f"Rejection blacklisted: {template_name} on {symbol} ({count} consecutive rejections)")
        else:
            logger.debug(f"Rejection recorded: {template_name} on {symbol} ({count}/{self._rejection_blacklist_threshold})")
    def reset_rejection(self, template_name: str, symbol: str) -> None:
        """Reset rejection counter on successful activation."""
        key = (template_name, symbol)
        if key in self._rejection_blacklist:
            logger.info(f"Rejection counter reset: {template_name} on {symbol} (was {self._rejection_blacklist[key]})")
            self._rejection_blacklist.pop(key, None)
            self._rejection_blacklist_timestamps.pop(key, None)
            self._save_rejection_blacklist_to_disk()
    def is_rejection_blacklisted(self, template_name: str, symbol: str) -> bool:
        """Check if a template+symbol combo is rejection-blacklisted (threshold reached and not past cooldown)."""
        key = (template_name, symbol)
        count = self._rejection_blacklist.get(key, 0)
        if count < self._rejection_blacklist_threshold:
            return False
        # Check cooldown — if enough time has passed, allow one re-try
        ts = self._rejection_blacklist_timestamps.get(key)
        if ts:
            age_days = (datetime.now() - datetime.fromisoformat(ts)).days
            if age_days >= self._rejection_blacklist_cooldown_days:
                return False  # Cooldown expired, allow re-proposal
        return True

    def _ensure_fundamental_data_provider(self):
        """Get the shared FundamentalDataProvider singleton."""
        if self._fundamental_data_provider is None:
            from src.data.fundamental_data_provider import get_fundamental_data_provider
            self._fundamental_data_provider = get_fundamental_data_provider()

    def _ensure_fundamental_ranker(self):
        """Lazily initialize the FundamentalRanker."""
        if self._fundamental_ranker is None:
            from src.strategy.fundamental_ranker import FundamentalRanker
            self._ensure_fundamental_data_provider()
            self._fundamental_ranker = FundamentalRanker(
                fundamental_data_provider=self._fundamental_data_provider,
                market_data_manager=self.market_data,
            )

    def get_fundamental_rankings(
        self, symbols: list, market_statistics: Dict = None
    ) -> Dict[str, Dict]:
        """
        Get cross-sectional fundamental rankings for all symbols.
        Cached per cycle (2h TTL via the ranker's internal cache).
        """
        self._ensure_fundamental_ranker()
        # Filter to stock symbols only (fundamentals don't apply to forex/crypto/etc)
        stock_symbols = [s for s in symbols if self._get_asset_class(s) == 'stock']
        if len(stock_symbols) < 5:
            return {}
        rankings = self._fundamental_ranker.rank_universe(stock_symbols, market_statistics)
        self._ranker_results = rankings
        return rankings

    def _get_cached_quarterly_data(self, symbol: str) -> List[Dict]:
        """Fetch quarterly fundamental data from cache or FundamentalDataProvider.

        Returns list of quarterly dicts with revenue, eps, dividend_yield, roe, etc.
        Cached for 24h to avoid excessive FMP API calls during scoring.
        """
        import time
        cache_key = f"quarterly_{symbol}"
        cached = self._fundamental_scoring_cache.get(cache_key)
        if cached and (time.time() - cached['timestamp']) < self._fundamental_scoring_cache_ttl:
            return cached['data']

        try:
            self._ensure_fundamental_data_provider()
            quarters = self._fundamental_data_provider.get_historical_fundamentals(symbol, quarters=8)
            self._fundamental_scoring_cache[cache_key] = {
                'data': quarters,
                'timestamp': time.time(),
            }
            return quarters
        except Exception as e:
            logger.debug(f"Could not fetch quarterly data for {symbol}: {e}")
            return []

    def _get_cached_insider_net(self, symbol: str) -> Optional[Dict]:
        """Fetch insider net purchases from cache or FundamentalDataProvider.

        Returns dict with net_shares, buy_count, sell_count, last_buy_date, etc.
        Cached for 24h.
        """
        import time
        cache_key = f"insider_{symbol}"
        cached = self._fundamental_scoring_cache.get(cache_key)
        if cached and (time.time() - cached['timestamp']) < self._fundamental_scoring_cache_ttl:
            return cached['data']

        try:
            self._ensure_fundamental_data_provider()
            insider_net = self._fundamental_data_provider.get_insider_net_purchases(symbol, lookback_days=90)
            self._fundamental_scoring_cache[cache_key] = {
                'data': insider_net,
                'timestamp': time.time(),
            }
            return insider_net
        except Exception as e:
            logger.debug(f"Could not fetch insider data for {symbol}: {e}")
            return None

    def _is_template_disabled(self, template) -> tuple:
        """Check if a template is disabled due to insufficient data, config, or user toggle.

        Returns (is_disabled: bool, reason: Optional[str]).
        Checks: 1) user-disabled list, 2) metadata disabled flag, 3) config for specific types.
        """
        # Check user-disabled list (from Template Manager UI)
        import json
        from pathlib import Path
        try:
            disabled_path = Path("config/.disabled_templates.json")
            if disabled_path.exists():
                with open(disabled_path, 'r') as f:
                    disabled_set = set(json.load(f))
                if template.name in disabled_set:
                    return True, 'disabled_by_user'
        except Exception:
            pass

        # Check metadata disabled flag
        if template.metadata and template.metadata.get('disabled'):
            return True, template.metadata.get('disable_reason', 'unknown')

        # Check config-based disable for specific template types
        ae_type = (template.metadata or {}).get('alpha_edge_type', '')
        if ae_type == 'end_of_month_momentum':
            import yaml
            from pathlib import Path
            try:
                config_path = Path("config/autonomous_trading.yaml")
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f) or {}
                    enabled = config.get('alpha_edge', {}).get('end_of_month_momentum', {}).get('enabled', True)
                    if not enabled:
                        return True, 'disabled_by_config'
            except Exception:
                pass

        return False, None

    def _load_wf_validated_from_disk(self):
        """Load WF validated combos from JSON, expiring stale entries."""
        import json
        from pathlib import Path
        try:
            path = Path(self._wf_validated_path)
            if not path.exists():
                return
            with open(path, 'r') as f:
                data = json.load(f)
            now = datetime.now()
            loaded = 0
            for entry in data.get('entries', []):
                key = (entry['template'], entry['symbol'])
                ts = datetime.fromisoformat(entry['timestamp'])
                if (now - ts).days < self._wf_validated_ttl_days:
                    self._wf_validated[key] = {
                        'sharpe': entry['sharpe'],
                        'trades': entry['trades'],
                        'timestamp': entry['timestamp'],
                    }
                    loaded += 1
            if loaded:
                logger.info(f"Loaded {loaded} WF validated combos from disk")
        except Exception as e:
            logger.debug(f"Could not load WF validated combos: {e}")

    def _save_wf_validated_to_disk(self):
        """Persist WF validated combos to JSON."""
        import json
        from pathlib import Path
        try:
            entries = [
                {
                    'template': t,
                    'symbol': s,
                    'sharpe': v['sharpe'],
                    'trades': v['trades'],
                    'timestamp': v['timestamp'],
                }
                for (t, s), v in self._wf_validated.items()
            ]
            path = Path(self._wf_validated_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                json.dump({'entries': entries, 'updated': datetime.now().isoformat()}, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not save WF validated combos: {e}")

    def _load_wf_failed_from_disk(self):
        """Load WF failed cache from disk, expiring entries older than TTL.
        
        This ensures that combos which failed WF in a previous process lifetime
        are still blocked, preventing the system from re-proposing and re-testing
        the same failing combos every restart.
        """
        import json, time
        from pathlib import Path
        try:
            path = Path(self._wf_failed_path)
            if not path.exists():
                return
            with open(path, 'r') as f:
                data = json.load(f)
            now = time.time()
            loaded = 0
            for entry in data.get('entries', []):
                cached_at = entry.get('cached_at', 0)
                if now - cached_at >= self._wf_cache_ttl:
                    continue  # Expired — allow re-testing
                key = (entry['template'], entry['symbol'])
                result_tuple = tuple(entry['result'])
                # Pad to 7 elements if loaded from old 4-element format:
                # (train_sharpe, test_sharpe, has_enough_trades, is_overfitted,
                #  train_sharpe_valid, test_sharpe_valid, wf_results)
                if len(result_tuple) == 4:
                    ts_val, tes_val, het_val, ov_val = result_tuple
                    tv_val = not (isinstance(ts_val, float) and (ts_val != ts_val or ts_val == float('inf')))
                    tev_val = not (isinstance(tes_val, float) and (tes_val != tes_val or tes_val == float('inf')))
                    result_tuple = (ts_val, tes_val, het_val, ov_val, tv_val, tev_val, None)
                elif len(result_tuple) == 6:
                    # New format: 6 scalars, wf_results not stored (can't serialize)
                    result_tuple = result_tuple + (None,)
                self._wf_results_cache[key] = (result_tuple, cached_at)
                loaded += 1
            if loaded:
                logger.info(f"Loaded {loaded} WF failed combos from disk (TTL {self._wf_cache_ttl}s)")
        except Exception as e:
            logger.debug(f"Could not load WF failed cache: {e}")

    def _save_wf_failed_to_disk(self):
        """Persist WF failed results to disk so they survive restarts."""
        import json, time
        from pathlib import Path
        try:
            now = time.time()
            entries = []
            for (t, s), (result, cached_at) in self._wf_results_cache.items():
                if now - cached_at >= self._wf_cache_ttl:
                    continue  # Don't persist expired entries
                # Only persist failures — passes are handled by _wf_validated
                test_sharpe = result[1] if len(result) > 1 else 0
                has_trades = result[2] if len(result) > 2 else False
                is_overfitted = result[3] if len(result) > 3 else False
                if test_sharpe < 0.15 or is_overfitted or not has_trades:
                    entries.append({
                        'template': t,
                        'symbol': s,
                        'result': list(result[:6]),  # Store 6 scalar fields (skip wf_results dict)
                        'cached_at': cached_at,
                    })
            path = Path(self._wf_failed_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                json.dump({'entries': entries, 'updated_at': now}, f, indent=2)
            if entries:
                logger.debug(f"Persisted {len(entries)} WF failed combos to disk")
        except Exception as e:
            logger.debug(f"Could not save WF failed cache: {e}")

    def _load_proposal_tracker(self):
        """Load proposal tracking counters from disk."""
        import json
        from pathlib import Path
        try:
            path = Path(self._proposal_tracker_path)
            if not path.exists():
                return
            with open(path, 'r') as f:
                self._proposal_tracker = json.load(f)
            logger.info(f"Loaded proposal tracker: {len(self._proposal_tracker)} templates tracked")
        except Exception as e:
            logger.debug(f"Could not load proposal tracker: {e}")

    def _save_proposal_tracker(self):
        """Persist proposal tracking counters to disk."""
        import json
        from pathlib import Path
        try:
            path = Path(self._proposal_tracker_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                json.dump(self._proposal_tracker, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not save proposal tracker: {e}")

    def track_proposals(self, strategies: list):
        """Record that these strategies were proposed (pre-WF) in this cycle.
        
        Called from generate_strategies_from_templates after the proposal batch
        is assembled but before WF validation.
        """
        now = datetime.now().isoformat()
        for strategy in strategies:
            tname = ''
            if hasattr(strategy, 'metadata') and strategy.metadata:
                tname = strategy.metadata.get('template_name', '')
            if not tname and hasattr(strategy, 'name'):
                import re
                tname = re.sub(r'\s+V\d+$', '', strategy.name or '').strip()
            if not tname:
                continue
            if tname not in self._proposal_tracker:
                self._proposal_tracker[tname] = {'proposed': 0, 'approved': 0, 'last_proposed': None, 'last_approved': None}
            self._proposal_tracker[tname]['proposed'] += 1
            self._proposal_tracker[tname]['last_proposed'] = now
        self._save_proposal_tracker()

    def track_approvals(self, strategies: list):
        """Record that these strategies passed WF and were approved.
        
        Called after WF validation filters the proposals.
        """
        now = datetime.now().isoformat()
        for strategy in strategies:
            tname = ''
            if hasattr(strategy, 'metadata') and strategy.metadata:
                tname = strategy.metadata.get('template_name', '')
            if not tname and hasattr(strategy, 'name'):
                import re
                tname = re.sub(r'\s+V\d+$', '', strategy.name or '').strip()
            if not tname:
                continue
            if tname not in self._proposal_tracker:
                self._proposal_tracker[tname] = {'proposed': 0, 'approved': 0, 'last_proposed': None, 'last_approved': None}
            self._proposal_tracker[tname]['approved'] += 1
            self._proposal_tracker[tname]['last_approved'] = now
        self._save_proposal_tracker()

    def get_proposal_counts(self) -> Dict[str, Dict]:
        """Return the proposal tracker for the templates API."""
        return dict(self._proposal_tracker)

    def _load_market_stats_from_disk(self):
        """Load market stats cache from disk if fresh enough (within TTL)."""
        import json
        from pathlib import Path
        try:
            path = Path(self._market_stats_cache_path)
            if not path.exists():
                return
            
            with open(path, 'r') as f:
                data = json.load(f)
            
            cached_at = data.get('timestamp', 0)
            import time as _time
            age = _time.time() - cached_at
            
            if age > self._market_stats_cache_ttl:
                logger.info(f"Disk market stats cache expired (age: {age/3600:.1f}h, TTL: {self._market_stats_cache_ttl/3600:.0f}h)")
                return
            
            self._market_stats_cache = {
                'market_statistics': data.get('market_statistics', {}),
                'indicator_distributions': data.get('indicator_distributions', {}),
                'timestamp': cached_at,
                'symbols_hash': data.get('symbols_hash', ''),
            }
            n_symbols = len(data.get('market_statistics', {}))
            logger.info(f"Loaded market stats cache from disk: {n_symbols} symbols (age: {age/60:.0f}min)")
        except Exception as e:
            logger.debug(f"Could not load market stats from disk: {e}")

    def _save_market_stats_to_disk(self):
        """Persist market stats cache to disk."""
        import json
        from pathlib import Path
        if not self._market_stats_cache:
            return
        try:
            path = Path(self._market_stats_cache_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Market stats contain numpy floats — convert to plain Python types
            def _sanitize(obj):
                if isinstance(obj, dict):
                    return {k: _sanitize(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [_sanitize(v) for v in obj]
                elif hasattr(obj, 'item'):  # numpy scalar
                    return obj.item()
                elif isinstance(obj, float) and (obj != obj):  # NaN
                    return None
                return obj
            
            data = {
                'market_statistics': _sanitize(self._market_stats_cache.get('market_statistics', {})),
                'indicator_distributions': _sanitize(self._market_stats_cache.get('indicator_distributions', {})),
                'timestamp': self._market_stats_cache.get('timestamp', 0),
                'symbols_hash': self._market_stats_cache.get('symbols_hash', ''),
            }
            
            with open(path, 'w') as f:
                json.dump(data, f)
            
            n_symbols = len(data.get('market_statistics', {}))
            logger.info(f"Saved market stats cache to disk: {n_symbols} symbols")
        except Exception as e:
            logger.debug(f"Could not save market stats to disk: {e}")

    def _get_direction_aware_thresholds(self, direction: str, market_regime) -> Dict[str, float]:
        """
        Get walk-forward validation thresholds adjusted for strategy direction and market regime.

        In ranging markets, LONG strategies naturally underperform (market is flat/slightly down),
        so we relax their thresholds to prevent systematic rejection. Similarly for SHORT in
        trending-up markets.

        Args:
            direction: 'LONG' or 'SHORT'
            market_regime: Current MarketRegime enum value

        Returns:
            Dict with 'min_return', 'min_sharpe', 'min_win_rate' thresholds
        """
        import yaml
        from pathlib import Path

        # Default strict thresholds
        defaults = {'min_return': 0.0, 'min_sharpe': 0.3, 'min_win_rate': 0.45}

        try:
            config_path = Path("config/autonomous_trading.yaml")
            if not config_path.exists():
                return defaults

            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            da_config = config.get('backtest', {}).get('walk_forward', {}).get('direction_aware_thresholds', {})
            if not da_config:
                return defaults

            # Map market regime to config key
            regime_str = market_regime.value if hasattr(market_regime, 'value') else str(market_regime)

            # Determine which regime bucket applies
            if 'ranging' in regime_str:
                regime_key = 'ranging'
            elif 'trending_up' in regime_str:
                regime_key = 'trending_up'
            elif 'trending_down' in regime_str:
                regime_key = 'trending_down'
            elif 'high_vol' in regime_str or 'ranging_high_vol' in regime_str:
                regime_key = 'high_vol'
            else:
                return da_config.get('default', defaults)

            # Override: ranging_high_vol maps to high_vol bucket
            if regime_str == 'ranging_high_vol':
                regime_key = 'high_vol'

            regime_thresholds = da_config.get(regime_key, {})
            direction_key = direction.lower()

            if direction_key in regime_thresholds:
                thresholds = regime_thresholds[direction_key]
                logger.info(
                    f"Using relaxed {direction} thresholds for {regime_key} regime "
                    f"(min_return: {thresholds.get('min_return', 0):.0%}, "
                    f"min_sharpe: {thresholds.get('min_sharpe', 0.3)}, "
                    f"min_win_rate: {thresholds.get('min_win_rate', 0.45):.0%})"
                )
                return {
                    'min_return': thresholds.get('min_return', defaults['min_return']),
                    'min_sharpe': thresholds.get('min_sharpe', defaults['min_sharpe']),
                    'min_win_rate': thresholds.get('min_win_rate', defaults['min_win_rate']),
                }

            return da_config.get('default', defaults)

        except Exception as e:
            logger.warning(f"Failed to load direction-aware thresholds: {e}")
            return defaults

    def _detect_strategy_direction(self, strategy) -> str:
        """Detect whether a strategy is LONG or SHORT from its metadata or rules."""
        direction = 'LONG'
        if hasattr(strategy, 'metadata') and strategy.metadata:
            stored = strategy.metadata.get('direction', '')
            if stored.upper() == 'SHORT':
                return 'SHORT'
        # Fallback: check entry conditions for SHORT indicators
        if hasattr(strategy, 'rules') and strategy.rules:
            rules = strategy.rules if isinstance(strategy.rules, dict) else {}
            for cond in rules.get('entry_conditions', []):
                if isinstance(cond, str) and any(kw in cond.upper() for kw in ('SHORT', 'SELL', 'OVERBOUGHT')):
                    return 'SHORT'
        return direction

    def _detect_strategy_type(self, strategy) -> str:
        """Detect strategy type (trend_following, mean_reversion, breakout, momentum) from name/metadata."""
        if hasattr(strategy, 'metadata') and strategy.metadata:
            st = strategy.metadata.get('template_type') or strategy.metadata.get('strategy_type')
            if st:
                return st
        name = (strategy.name or '').lower() if hasattr(strategy, 'name') else ''
        if any(kw in name for kw in ['ema crossover', 'ema ribbon', 'atr dynamic', 'adx trend',
                                      'dual ma', 'sma trend', 'trend follow', 'macd trend',
                                      'momentum burst', 'vwap trend', 'fast ema']):
            return 'trend_following'
        if any(kw in name for kw in ['breakout', 'keltner', 'squeeze', 'volume spike',
                                      'bb squeeze', 'momentum surge']):
            return 'breakout'
        if any(kw in name for kw in ['momentum', 'macd signal', 'stochastic momentum',
                                      'macd momentum', 'crypto.*macd']):
            return 'momentum'
        if any(kw in name for kw in ['rsi dip', 'bb middle', 'mean reversion', 'pullback',
                                      'reversion', 'dip buy', 'oversold', 'proximity',
                                      'stochastic swing', 'weak uptrend']):
            return 'mean_reversion'
        return 'unknown'


    def _compute_adaptive_risk_config(
        self,
        strategy_type: StrategyType,
        symbols: List[str],
        market_statistics: Optional[Dict] = None,
        template_params: Optional[Dict] = None,
    ) -> RiskConfig:
        """
        Compute strategy-appropriate SL/TP based on template type and instrument volatility.

        Priority: template_params > ATR-adjusted type defaults > static type defaults.
        
        IMPORTANT: Even when template specifies SL/TP, we enforce an ATR-based minimum
        floor. A template's 2% SL is fine for low-vol stocks but will get stopped out
        on normal noise for high-beta names like MELI (ATR ~3%). The ATR floor ensures
        the SL always gives the trade enough room to breathe.

        Args:
            strategy_type: The strategy classification (mean_reversion, breakout, etc.)
            symbols: Symbols the strategy will trade (uses first for volatility lookup)
            market_statistics: Per-symbol analysis dicts from MarketStatisticsAnalyzer
            template_params: Customized parameters from the template (may contain stop_loss_pct, take_profit_pct)

        Returns:
            RiskConfig with adaptive stop_loss_pct and take_profit_pct
        """
        # --- Per-type baseline SL/TP (before volatility adjustment) ---
        type_profiles = {
            StrategyType.MEAN_REVERSION: {"sl": 0.03, "tp": 0.08, "trailing": False},
            StrategyType.TREND_FOLLOWING: {"sl": 0.05, "tp": 0.15, "trailing": True},
            StrategyType.BREAKOUT:        {"sl": 0.04, "tp": 0.10, "trailing": True},
            StrategyType.VOLATILITY:      {"sl": 0.04, "tp": 0.10, "trailing": False},
        }
        profile = type_profiles.get(strategy_type, type_profiles[StrategyType.MEAN_REVERSION])

        # Use template-specific params if provided (highest priority for starting point)
        has_template_sl = template_params and template_params.get('stop_loss_pct')
        has_template_tp = template_params and template_params.get('take_profit_pct')
        
        if has_template_sl:
            sl = template_params['stop_loss_pct']
        else:
            sl = profile["sl"]
        
        if has_template_tp:
            tp = template_params['take_profit_pct']
        else:
            tp = profile["tp"]
        
        trailing = profile["trailing"]

        # --- Volatility adjustment using ATR ratio ---
        # ALWAYS apply ATR-based floor, even when template specifies SL/TP.
        # A template's 2% SL is a reasonable default for average-vol instruments,
        # but high-beta stocks (MELI, SMCI, SHOP) need more room.
        # The ATR floor = 1.5x ATR-ratio ensures SL > 1 day's average range.
        atr_ratio = None
        if market_statistics and symbols:
            sym = symbols[0]
            stats = market_statistics.get(sym, {})
            atr_ratio = stats.get("volatility_metrics", {}).get("atr_ratio", None)

        if atr_ratio and atr_ratio > 0:
            # ATR-based minimum: SL must be at least 2x ATR to survive normal noise
            atr_floor_sl = atr_ratio * 2.0
            # Preserve the template's R:R ratio when widening
            original_rr = tp / sl if sl > 0 else 2.5
            
            if has_template_sl:
                # Template specified SL — use it as starting point but enforce ATR floor
                if sl < atr_floor_sl:
                    old_sl = sl
                    sl = atr_floor_sl
                    tp = sl * original_rr  # Widen TP proportionally to maintain R:R
                    logger.info(
                        f"ATR floor applied for {symbols[0]}: template SL {old_sl:.3%} < "
                        f"ATR floor {atr_floor_sl:.3%} (ATR-ratio={atr_ratio:.4f}). "
                        f"Widened to SL={sl:.3%}, TP={tp:.3%} (R:R={original_rr:.1f}x preserved)"
                    )
                else:
                    logger.info(
                        f"Template SL {sl:.3%} >= ATR floor {atr_floor_sl:.3%} for {symbols[0]} — "
                        f"keeping template params"
                    )
            else:
                # No template SL — blend ATR with type baseline (original behavior)
                vol_sl = atr_ratio * 2.0
                vol_tp = atr_ratio * 5.0
                sl = (sl + vol_sl) / 2
                tp = (tp + vol_tp) / 2
                logger.info(
                    f"Adaptive risk for {strategy_type.value} on {symbols[0]}: "
                    f"ATR-ratio={atr_ratio:.4f}, SL={sl:.3%}, TP={tp:.3%}"
                )
        elif has_template_sl:
            logger.info(
                f"Using template params for {strategy_type.value}: "
                f"SL={sl:.3%}, TP={tp:.3%} (template-specified, no ATR data)"
            )
        else:
            logger.info(
                f"Adaptive risk for {strategy_type.value} (no ATR data): "
                f"SL={sl:.3%}, TP={tp:.3%}"
            )

        # Clamp to sane bounds
        sl = max(0.015, min(sl, 0.12))   # 1.5% – 12%
        tp = max(0.03, min(tp, 0.30))    # 3% – 30%

        # Ensure TP > SL (at least 2:1 reward-to-risk)
        if tp < sl * 2.0:
            tp = sl * 2.5

        return RiskConfig(
            stop_loss_pct=round(sl, 4),
            take_profit_pct=round(tp, 4),
            trailing_stop=trailing,
        )

    def _get_asset_class(self, symbol: str) -> str:
        """Determine asset class for a symbol (stock, etf, forex, crypto, index, commodity).

        Uses the tradeable instruments lists to classify symbols.
        """
        from src.core.tradeable_instruments import (
            DEMO_ALLOWED_ETFS, DEMO_ALLOWED_FOREX, DEMO_ALLOWED_CRYPTO,
            DEMO_ALLOWED_INDICES, DEMO_ALLOWED_COMMODITIES
        )
        sym = symbol.upper()
        if sym in DEMO_ALLOWED_FOREX:
            return "forex"
        if sym in DEMO_ALLOWED_CRYPTO:
            return "crypto"
        if sym in DEMO_ALLOWED_ETFS:
            return "etf"
        if sym in DEMO_ALLOWED_INDICES:
            return "index"
        if sym in DEMO_ALLOWED_COMMODITIES:
            return "commodity"
        return "stock"

    def _apply_asset_class_overrides(self, risk_config: RiskConfig, symbol: str) -> RiskConfig:
        """Apply asset-class-specific parameter overrides to a strategy's risk config.

        Loads overrides from config/autonomous_trading.yaml asset_class_parameters section.
        Forex gets tighter stops (pip-based), crypto gets wider stops (high volatility),
        stocks/ETFs use standard parameters.

        Args:
            risk_config: The base RiskConfig computed from strategy type + volatility
            symbol: The primary symbol to determine asset class

        Returns:
            RiskConfig with asset-class-specific overrides applied
        """
        import yaml
        from pathlib import Path

        asset_class = self._get_asset_class(symbol)

        config_path = Path("config/autonomous_trading.yaml")
        if not config_path.exists():
            return risk_config

        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Failed to load asset class config: {e}")
            return risk_config

        ac_params = config.get('asset_class_parameters', {}).get(asset_class)
        if not ac_params:
            return risk_config

        # Apply asset class as a FLOOR — only widen SL/TP if the asset class
        # minimum is larger than what the template/adaptive system computed.
        # This prevents tight template-specific params from being blown out,
        # while ensuring crypto/forex get at least their minimum breathing room.
        override_sl = ac_params.get('stop_loss_pct')
        override_tp = ac_params.get('take_profit_pct')

        if override_sl is not None and override_sl > risk_config.stop_loss_pct:
            risk_config.stop_loss_pct = round(override_sl, 4)

        if override_tp is not None and override_tp > risk_config.take_profit_pct:
            risk_config.take_profit_pct = round(override_tp, 4)

        # Ensure TP > SL (at least 2:1 reward-to-risk)
        if risk_config.take_profit_pct < risk_config.stop_loss_pct * 2.0:
            risk_config.take_profit_pct = round(risk_config.stop_loss_pct * 2.5, 4)

        logger.info(
            f"Asset class override for {symbol} ({asset_class}): "
            f"SL={risk_config.stop_loss_pct:.3%}, TP={risk_config.take_profit_pct:.3%}, "
            f"signal_hours={ac_params.get('signal_hours', 'market_hours')}"
        )

        return risk_config

    def _load_trading_symbols(self) -> List[str]:
        """Load trading symbols from tradeable_instruments.py.

        Uses the verified tradeable symbols for the current trading mode.
        This ensures strategies are only generated for symbols that can actually be traded.
        """
        from src.core.tradeable_instruments import get_tradeable_symbols
        from src.models.enums import TradingMode

        # Use DEMO mode symbols (most restrictive)
        # In production, this could be parameterized based on actual trading mode
        symbols = get_tradeable_symbols(TradingMode.DEMO)
        
        logger.info(
            f"Loaded {len(symbols)} verified tradeable symbols from tradeable_instruments.py"
        )
        
        return symbols
    
    def analyze_market_conditions(self, symbols: List[str] = None) -> tuple:
        """
        Analyze current market to determine regime.
        
        Uses simple price change analysis:
        - Calculate 20-day and 50-day price change
        - If both positive → TRENDING_UP
        - If both negative → TRENDING_DOWN
        - Otherwise → RANGING
        
        Args:
            symbols: List of symbols to analyze (defaults to major indices)
        
        Returns:
            Tuple of (MarketRegime, confidence, DataQuality)
        """
        if symbols is None:
            # Use major market indices for regime detection (broad market representation)
            symbols = ["SPY", "QQQ", "DIA", "IWM"]
        
        logger.info(f"Analyzing market conditions using symbols: {symbols}")
        
        try:
            # Load analysis period from config
            import yaml
            from pathlib import Path
            config_path = Path("config/autonomous_trading.yaml")
            analysis_period_days = 365  # Default to 1 year for regime detection
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    # Use backtest days for market analysis (730 days = 2 years)
                    analysis_period_days = config.get('backtest', {}).get('days', 730)
            
            logger.info(f"Using {analysis_period_days} days of historical data for market regime analysis")
            
            # Calculate average price changes across symbols
            changes_20d = []
            changes_50d = []
            data_days = []  # Track data availability per symbol
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=analysis_period_days)
            
            for symbol in symbols:
                try:
                    # Fetch historical data from Yahoo Finance
                    historical_data = self.market_data.get_historical_data(
                        symbol=symbol,
                        start=start_date,
                        end=end_date,
                        interval="1d",
                        prefer_yahoo=True  # Use Yahoo Finance consistently
                    )
                    
                    days_available = len(historical_data)
                    data_days.append(days_available)
                    
                    logger.info(f"{symbol}: {days_available} days of data available")
                    
                    if days_available < 30:
                        logger.warning(f"Insufficient data for {symbol} ({days_available} days), skipping")
                        continue
                    
                    # Calculate 20-day and 50-day price changes (or best available)
                    current_price = historical_data[-1].close
                    
                    # Use 20-day change if available
                    if days_available >= 20:
                        price_20d_ago = historical_data[-20].close
                        change_20d = (current_price - price_20d_ago) / price_20d_ago
                        changes_20d.append(change_20d)
                        logger.debug(f"{symbol}: 20d change={change_20d:.2%}")
                    
                    # Use 50-day change if available
                    if days_available >= 50:
                        price_50d_ago = historical_data[-50].close
                        change_50d = (current_price - price_50d_ago) / price_50d_ago
                        changes_50d.append(change_50d)
                        logger.debug(f"{symbol}: 50d change={change_50d:.2%}")
                
                except Exception as e:
                    logger.warning(f"Failed to analyze {symbol}: {e}")
                    continue
            
            # Determine data quality based on average days available
            # Updated thresholds for 2-year lookback period
            if data_days:
                avg_days = sum(data_days) / len(data_days)
                if avg_days >= 600:  # ~2 years
                    data_quality = DataQuality.EXCELLENT
                elif avg_days >= 365:  # ~1 year
                    data_quality = DataQuality.GOOD
                elif avg_days >= 180:  # ~6 months
                    data_quality = DataQuality.FAIR
                else:
                    data_quality = DataQuality.POOR
                
                logger.info(f"Data quality: {data_quality.value} (avg {avg_days:.0f} days, requested {analysis_period_days} days)")
            else:
                data_quality = DataQuality.POOR
                logger.warning("No data available for any symbol")
            
            # Only default to RANGING if data quality is POOR
            if data_quality == DataQuality.POOR or (not changes_20d and not changes_50d):
                logger.warning("Poor data quality or no valid data, defaulting to RANGING")
                return MarketRegime.RANGING, 0.0, data_quality
            
            # Calculate average changes
            avg_change_20d = sum(changes_20d) / len(changes_20d) if changes_20d else 0
            avg_change_50d = sum(changes_50d) / len(changes_50d) if changes_50d else 0
            
            logger.info(f"Market analysis: 20d avg change={avg_change_20d:.2%}, 50d avg change={avg_change_50d:.2%}")
            
            # Determine regime with confidence
            confidence = 0.0
            
            if avg_change_20d > 0 and avg_change_50d > 0:
                regime = MarketRegime.TRENDING_UP
                # Confidence based on magnitude and agreement
                confidence = min(abs(avg_change_20d) + abs(avg_change_50d), 1.0)
            elif avg_change_20d < 0 and avg_change_50d < 0:
                regime = MarketRegime.TRENDING_DOWN
                confidence = min(abs(avg_change_20d) + abs(avg_change_50d), 1.0)
            else:
                regime = MarketRegime.RANGING
                # Lower confidence when signals disagree
                confidence = 0.5
            
            logger.info(f"Market regime detected: {regime.value} (confidence: {confidence:.2f}, quality: {data_quality.value})")
            return regime, confidence, data_quality
        
        except Exception as e:
            logger.error(f"Error analyzing market conditions: {e}")
            # Default to RANGING on error with poor quality
            return MarketRegime.RANGING, 0.0, DataQuality.POOR
    
    def propose_strategies(
        self,
        count: int = 5,
        symbols: List[str] = None,
        market_regime: Optional[MarketRegime] = None,
        use_walk_forward: bool = True,
        strategy_engine = None,
        optimize_parameters: bool = False,
        progress_callback = None,  # callable(phase: str, pct: int)
        filters: Dict = None  # {'asset_classes': [...], 'intervals': [...], 'strategy_types': [...]}
    ) -> List[Strategy]:
        """
        Generate strategy proposals based on current market conditions.
        
        Args:
            count: Number of strategies to propose (default 3-5)
            symbols: List of symbols to trade (if None, LLM will choose)
            market_regime: Market regime (if None, will be detected)
            use_walk_forward: Whether to use walk-forward validation (default True)
            strategy_engine: StrategyEngine instance for walk-forward validation
            optimize_parameters: Whether to optimize template parameters using grid search
            filters: Optional filters to restrict proposals by asset class, interval, strategy type
        
        Returns:
            List of proposed strategies with status=PROPOSED
        """
        self._proposal_filters = filters or {}
        if self._proposal_filters:
            logger.info(f"Proposal filters active: {self._proposal_filters}")
        logger.info(f"Proposing {count} strategies (walk-forward: {use_walk_forward}, optimize: {optimize_parameters})")
        
        # Detect market sub-regime if not provided
        if market_regime is None:
            # Use sub-regime detection for more precise template selection
            # If proposal filters restrict to a specific asset class, use appropriate benchmarks
            regime_symbols = None  # Default: SPY/QQQ/DIA
            filter_asset_classes = self._proposal_filters.get('asset_classes', []) if hasattr(self, '_proposal_filters') else []
            if filter_asset_classes and len(filter_asset_classes) == 1:
                if 'crypto' in filter_asset_classes:
                    regime_symbols = ['BTC', 'ETH']
                elif 'forex' in filter_asset_classes:
                    regime_symbols = ['EURUSD', 'GBPUSD', 'USDJPY']
            sub_regime, confidence, data_quality, metrics = self.market_analyzer.detect_sub_regime(symbols=regime_symbols)
            market_regime = sub_regime
            logger.info(f"Market sub-regime: {market_regime.value}, confidence: {confidence:.2f}, data quality: {data_quality}")
            logger.info(f"Sub-regime metrics: 20d={metrics.get('avg_change_20d', 0):.2%}, "
                       f"50d={metrics.get('avg_change_50d', 0):.2%}, "
                       f"ATR/price={metrics.get('avg_atr_ratio', 0):.2%}")
            
            # Warn if proposing strategies with poor data quality
            if data_quality == "POOR":
                logger.warning("Proposing strategies with POOR data quality - results may be unreliable")
        
        # Get available indicators
        available_indicators = self._get_available_indicators()
        
        # Analyze market statistics for the symbols (with caching)
        symbols_to_analyze = symbols or self._trading_symbols
        
        # Check if we have a fresh cache
        import time as _time
        cache_valid = False
        if self._market_stats_cache is not None:
            cache_age = _time.time() - self._market_stats_cache.get('timestamp', 0)
            cached_symbols = self._market_stats_cache.get('symbols_hash', '')
            current_hash = str(sorted(symbols_to_analyze))
            if cache_age < self._market_stats_cache_ttl and cached_symbols == current_hash:
                cache_valid = True
                market_statistics = self._market_stats_cache['market_statistics']
                indicator_distributions = self._market_stats_cache['indicator_distributions']
                logger.info(
                    f"Using cached market statistics for {len(market_statistics)} symbols "
                    f"(age: {cache_age/3600:.1f}h, TTL: {self._market_stats_cache_ttl/3600:.0f}h) — "
                    f"skipping {len(symbols_to_analyze)}-symbol analysis"
                )
                if progress_callback:
                    progress_callback(f"Using cached analysis ({len(market_statistics)} symbols)", 85)
        
        if not cache_valid:
            logger.info(f"Analyzing market statistics for {len(symbols_to_analyze)} symbols (no valid cache)")
            market_statistics = {}
            indicator_distributions = {}
            
            # Load config once (not per-symbol)
            import yaml
            from pathlib import Path
            config_path = Path("config/autonomous_trading.yaml")
            analysis_period_days = 730
            try:
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                        analysis_period_days = config.get('backtest', {}).get('days', 730)
            except Exception:
                pass
            
            # Parallelize market analysis — 4 workers to avoid overwhelming Yahoo Finance
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            def _analyze_one_symbol(symbol):
                """Analyze a single symbol's market stats and indicator distributions."""
                try:
                    stats = self.market_analyzer.analyze_symbol(symbol, period_days=analysis_period_days)
                    distributions = self.market_analyzer.analyze_indicator_distributions(symbol, period_days=analysis_period_days)
                    return symbol, stats, distributions, None
                except Exception as e:
                    return symbol, None, None, str(e)
            
            completed = 0
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(_analyze_one_symbol, sym): sym for sym in symbols_to_analyze}
                for future in as_completed(futures):
                    symbol, stats, distributions, error = future.result()
                    completed += 1
                    if error:
                        logger.warning(f"Failed to analyze market statistics for {symbol}: {error}")
                    else:
                        market_statistics[symbol] = stats
                        indicator_distributions[symbol] = distributions
                    
                    # Progress callback every 10 symbols
                    if progress_callback and completed % 10 == 0:
                        pct = int((completed / len(symbols_to_analyze)) * 100)
                        progress_callback(f"Analyzing symbols... ({completed}/{len(symbols_to_analyze)})", pct)
            
            logger.info(f"Parallel market analysis complete: {len(market_statistics)}/{len(symbols_to_analyze)} symbols analyzed")
            
            # Save to cache
            self._market_stats_cache = {
                'market_statistics': market_statistics,
                'indicator_distributions': indicator_distributions,
                'timestamp': _time.time(),
                'symbols_hash': str(sorted(symbols_to_analyze)),
            }
            logger.info(f"Cached market statistics for {len(market_statistics)} symbols (TTL: {self._market_stats_cache_ttl/3600:.0f}h)")
            self._save_market_stats_to_disk()  # Persist to disk for restart survival
        
        # Get market context (VIX, rates, etc.)
        try:
            market_context_data = self.market_analyzer.get_market_context()
            logger.info(f"Market context: VIX={market_context_data.get('vix', 'N/A')}, "
                       f"risk_regime={market_context_data.get('risk_regime', 'N/A')}")
        except Exception as e:
            logger.warning(f"Failed to get market context: {e}")
            market_context_data = {}
        
        # Generate exactly the requested count — the autonomous manager does its
        # own backtest + activation filtering downstream, so no need to inflate here.
        generation_count = count
        
        logger.info(f"Generating {generation_count} strategies for filtering (target: {count})")
        
        if progress_callback:
            progress_callback(f"Generating {generation_count} strategies...", 90)
        
        # Generate strategies using templates (NO LLM)
        strategies = []
        
        # Use template-based generation — pass pre-computed market data to avoid redundant analysis
        strategies = self.generate_strategies_from_templates(
            count=generation_count,
            symbols=symbols or self._trading_symbols,
            market_regime=market_regime,
            optimize_parameters=optimize_parameters,
            strategy_engine=strategy_engine,
            market_statistics=market_statistics,
            indicator_distributions=indicator_distributions
        )
        
        logger.info(f"Generated {len(strategies)} strategies from templates")
        
        # Track all proposals (pre-WF) for the templates dashboard
        self.track_proposals(strategies)
        
        # Apply walk-forward validation if requested
        if use_walk_forward and strategy_engine and len(strategies) > 0:
            logger.info(f"Running walk-forward validation on {len(strategies)} strategies")
            
            # Load walk-forward config
            import yaml
            from pathlib import Path
            config_path = Path("config/autonomous_trading.yaml")
            backtest_days = 730  # Default to 2 years
            train_days = 480  # Default to 16 months
            test_days = 240  # Default to 8 months
            
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    backtest_config = config.get('backtest', {})
                    backtest_days = backtest_config.get('days', 730)
                    wf_config = backtest_config.get('walk_forward', {})
                    train_days = wf_config.get('train_days', 480)
                    test_days = wf_config.get('test_days', 240)
            
            # Calculate date range for validation (730 days total: 480 train + 240 test)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=backtest_days)
            
            # Separate Alpha Edge strategies from DSL strategies
            # Alpha Edge uses fundamental signals — walk-forward (DSL-based) does not apply.
            # They get their own fundamental validation and backtest in _backtest_proposals.
            alpha_edge_strategies = []
            dsl_strategies = []
            for strategy in strategies:
                if (hasattr(strategy, 'metadata') and strategy.metadata 
                    and strategy.metadata.get('strategy_category') == 'alpha_edge'):
                    # Alpha Edge strategies skip walk-forward (DSL cannot evaluate fundamental conditions)
                    # They'll be validated and backtested via the fundamental path in _backtest_proposals
                    alpha_edge_strategies.append(strategy)
                    logger.info(f"[OK] Alpha Edge strategy routed to fundamental validation: {strategy.name}")
                else:
                    dsl_strategies.append(strategy)

            logger.info(f"Walk-forward: {len(dsl_strategies)} DSL strategies to validate, {len(alpha_edge_strategies)} Alpha Edge bypassed")

            # No pre-WF dedup needed — uniqueness is guaranteed during generation
            # (seen_conditions check in generate_strategies_from_templates)

            # Run walk-forward validation on all strategies and capture results
            if progress_callback:
                progress_callback(f"Walk-forward validation on {len(dsl_strategies)} DSL strategies...", 92)
            import math
            all_wf_results = []  # (strategy, wf_results, train_sharpe, test_sharpe, has_enough_trades, is_overfitted, train_sharpe_valid, test_sharpe_valid)
            
            for wf_idx, strategy in enumerate(dsl_strategies):
                # Emit walk-forward sub-progress
                if progress_callback:
                    wf_pct = 92 + int((wf_idx / max(len(dsl_strategies), 1)) * 8)  # 92% to 100%
                    progress_callback(f"Walk-forward {strategy.name} ({wf_idx+1}/{len(dsl_strategies)})", wf_pct)
                try:
                    # Check WF results cache — skip expensive re-validation if we already
                    # know the result for this (template, symbol) combo
                    template_name = strategy.metadata.get('template_name', '') if strategy.metadata else ''
                    primary_symbol = strategy.symbols[0] if strategy.symbols else ''
                    wf_cache_key = (template_name, primary_symbol)

                    # Pre-WF fundamental filter: skip dividend_aristocrat strategies on
                    # symbols with no meaningful dividend yield — they will always produce
                    # 0 trades in backtest (entry condition requires yield > 2%).
                    if 'dividend' in template_name.lower() or 'aristocrat' in template_name.lower():
                        try:
                            quarters = self._get_cached_quarterly_data(primary_symbol)
                            if quarters:
                                div_yields = [q.get('dividend_yield') for q in quarters if q.get('dividend_yield') is not None]
                                latest_yield = div_yields[0] if div_yields else 0.0
                            else:
                                latest_yield = 0.0
                            if latest_yield < 0.015:
                                logger.debug(f"Pre-WF skip: {template_name} on {primary_symbol} — dividend yield {latest_yield:.2%} < 1.5%")
                                continue
                        except Exception:
                            pass  # If we can't check, let WF decide
                    
                    import time as _wf_time
                    cached_wf = self._wf_results_cache.get(wf_cache_key)
                    if cached_wf is not None:
                        cached_result, cached_at = cached_wf
                        cache_age = _wf_time.time() - cached_at
                        if cache_age < self._wf_cache_ttl:
                            # Unpack cached result
                            (train_sharpe, test_sharpe, has_enough_trades, is_overfitted,
                             train_sharpe_valid, test_sharpe_valid, wf_results) = cached_result
                            all_wf_results.append((strategy, wf_results, train_sharpe, test_sharpe,
                                                   has_enough_trades, is_overfitted, train_sharpe_valid, test_sharpe_valid))
                            logger.info(
                                f"WF cache hit: {strategy.name} ({primary_symbol}) → "
                                f"S={test_sharpe:.2f} (cached {cache_age/3600:.1f}h ago)"
                            )
                            continue
                    
                    # Clear indicator and data caches before each strategy to prevent
                    # shape mismatch errors when different symbols have different data lengths
                    if hasattr(strategy_engine, 'indicator_library'):
                        strategy_engine.indicator_library.clear_cache()
                    if hasattr(strategy_engine.market_data, '_historical_memory_cache'):
                        strategy_engine.market_data._historical_memory_cache.clear()

                    wf_results = strategy_engine.walk_forward_validate(
                        strategy=strategy,
                        start=start_date,
                        end=end_date,
                        train_days=train_days,
                        test_days=test_days
                    )
                    
                    train_sharpe = wf_results['train_sharpe']
                    test_sharpe = wf_results['test_sharpe']
                    is_overfitted = wf_results['is_overfitted']
                    
                    test_trades = wf_results['test_results'].total_trades if wf_results.get('test_results') else 0
                    train_trades = wf_results['train_results'].total_trades if wf_results.get('train_results') else 0
                    
                    # Load min_trades thresholds from config — asset-class and timeframe aware
                    try:
                        import yaml as _yaml
                        from pathlib import Path as _Path
                        _cfg_path = _Path("config/autonomous_trading.yaml")
                        _at_cfg = {}
                        if _cfg_path.exists():
                            with open(_cfg_path) as _f:
                                _full_cfg = _yaml.safe_load(_f) or {}
                            _at_cfg = _full_cfg.get('activation_thresholds', {})
                    except Exception:
                        _at_cfg = {}
                    _interval = (strategy.metadata or {}).get('interval', '1d')
                    _is_crypto = False
                    _is_commodity = False
                    try:
                        from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_COMMODITIES
                        _sym = strategy.symbols[0].upper() if strategy.symbols else ''
                        _is_crypto = _sym in set(DEMO_ALLOWED_CRYPTO)
                        _is_commodity = _sym in set(DEMO_ALLOWED_COMMODITIES)
                    except Exception:
                        pass
                    if _is_commodity:
                        _min_trades = _at_cfg.get('min_trades_commodity', 8)
                    elif _interval == '1h':
                        _min_trades = _at_cfg.get('min_trades_dsl_1h', 20)
                    elif _interval == '4h':
                        _min_trades = _at_cfg.get('min_trades_dsl_4h', 12)
                    else:
                        _min_trades = _at_cfg.get('min_trades_dsl', 15)
                    
                    has_enough_trades = test_trades >= _min_trades and train_trades >= max(2, _min_trades // 3)

                    # Sharpe-weighted exception: high-conviction strategies (test Sharpe ≥ 2.0)
                    # with at least 3 test trades pass even if below the min_trades threshold.
                    # A Sharpe of 2.0+ with 3+ trades is statistically more meaningful than
                    # a Sharpe of 0.5 with 15 trades. Low-frequency strategies (forex, commodities)
                    # naturally produce fewer trades in a 120-180 day test window.
                    if not has_enough_trades and test_trades >= 3 and test_sharpe >= 2.0:
                        has_enough_trades = True
                        logger.info(
                            f"Sharpe exception: {strategy.name} — test_sharpe={test_sharpe:.2f} ≥ 2.0 "
                            f"with {test_trades} trades (below {_min_trades} threshold but high conviction)"
                        )
                    
                    # Update zero-trade blacklist: track template+symbol combos that produce 0 trades
                    if test_trades == 0 or train_trades == 0:
                        template_name = strategy.metadata.get('template_name', '') if strategy.metadata else ''
                        primary_symbol = strategy.symbols[0] if strategy.symbols else ''
                        bl_key = (template_name, primary_symbol) if primary_symbol else None
                        if bl_key:
                            self._zero_trade_blacklist[bl_key] = self._zero_trade_blacklist.get(bl_key, 0) + 1
                            self._zero_trade_blacklist_timestamps[bl_key] = datetime.now().isoformat()
                            if self._zero_trade_blacklist[bl_key] >= self._zero_trade_blacklist_threshold:
                                logger.info(f"Blacklisted 0-trade combo: {template_name} + {primary_symbol} (count={self._zero_trade_blacklist[bl_key]})")
                            self._save_blacklist_to_disk()
                    else:
                        # Reset blacklist count on success — the combo works sometimes
                        template_name = strategy.metadata.get('template_name', '') if strategy.metadata else ''
                        primary_symbol = strategy.symbols[0] if strategy.symbols else ''
                        bl_key = (template_name, primary_symbol) if primary_symbol else None
                        if bl_key and bl_key in self._zero_trade_blacklist:
                            del self._zero_trade_blacklist[bl_key]
                            if bl_key in self._zero_trade_blacklist_timestamps:
                                del self._zero_trade_blacklist_timestamps[bl_key]
                            self._save_blacklist_to_disk()
                    
                    train_sharpe_valid = not (math.isinf(train_sharpe) or math.isnan(train_sharpe))
                    test_sharpe_valid = not (math.isinf(test_sharpe) or math.isnan(test_sharpe))
                    
                    all_wf_results.append((strategy, wf_results, train_sharpe, test_sharpe,
                                           has_enough_trades, is_overfitted, train_sharpe_valid, test_sharpe_valid))
                    
                    # Cache the WF result so we don't re-run it next cycle
                    self._wf_results_cache[wf_cache_key] = (
                        (train_sharpe, test_sharpe, has_enough_trades, is_overfitted,
                         train_sharpe_valid, test_sharpe_valid, wf_results),
                        _wf_time.time()
                    )
                    
                    # Record validated combo if WF passed (positive test Sharpe, enough trades, not overfitted)
                    if test_sharpe_valid and test_sharpe > 0.15 and has_enough_trades and not is_overfitted:
                        test_trades = wf_results['test_results'].total_trades if wf_results.get('test_results') else 0
                        self._wf_validated[wf_cache_key] = {
                            'sharpe': round(test_sharpe, 3),
                            'trades': test_trades,
                            'timestamp': datetime.now().isoformat(),
                        }
                        self._save_wf_validated_to_disk()
                    else:
                        # WF failed — persist to disk so it survives restarts
                        self._save_wf_failed_to_disk()
                    
                    # Log result (note: actual pass/fail uses direction-aware thresholds below,
                    # this log is just for quick visibility during the WF loop)
                    if train_sharpe_valid and test_sharpe_valid and has_enough_trades and not is_overfitted and test_sharpe > 0.15:
                        logger.info(
                            f"✓ {strategy.name}: train_sharpe={train_sharpe:.2f}, "
                            f"test_sharpe={test_sharpe:.2f}, passed"
                        )
                    else:
                        logger.info(
                            f"✗ {strategy.name}: train_sharpe={train_sharpe:.2f}, "
                            f"test_sharpe={test_sharpe:.2f}, overfitted={is_overfitted}, "
                            f"trades={'ok' if has_enough_trades else 'low'}, rejected"
                        )
                
                except Exception as e:
                    logger.warning(f"Walk-forward validation failed for {strategy.name}: {e}")
                    # Log crash to cycle log
                    try:
                        from src.core.cycle_logger import get_cycle_logger
                        get_cycle_logger().log_error("WALK-FORWARD", f"{strategy.name}: {str(e)[:150]}")
                    except Exception:
                        pass
                    continue
            
            # Monte Carlo Bootstrap — filter out strategies whose OOS edge is likely noise.
            # For each strategy that has test trades, we resample the trade P&L 1000 times
            # and require the 5th-percentile Sharpe > 0.2. This catches strategies that
            # happened to get lucky on the specific OOS period but have no real edge.
            # Strategies with < 5 test trades are skipped (not enough data to bootstrap).
            mc_passed_ids = set()
            MC_ITERATIONS = 1000
            MC_MIN_P5_SHARPE = 0.0  # Break-even bar: reject only if edge is negative at p5
            MC_MIN_TRADES_FOR_BOOTSTRAP = 15  # Raised from 5 — too few trades makes bootstrap meaningless
            for s, wf, ts, tes, het, ov, tv, tev in all_wf_results:
                if not (tv and tev and het and not ov):
                    mc_passed_ids.add(s.id)  # Already filtered out below — don't double-filter
                    continue
                # wf may be None when loaded from 4-tuple disk cache
                if wf is None:
                    mc_passed_ids.add(s.id)
                    continue
                test_results = wf.get('test_results')
                if test_results is None:
                    mc_passed_ids.add(s.id)
                    continue
                trades_list = getattr(test_results, 'trades', None)
                # trades may be a DataFrame or a list — handle both
                if trades_list is None:
                    trades_list = []
                elif hasattr(trades_list, 'to_dict'):
                    # It's a DataFrame — convert to list of dicts
                    trades_list = trades_list.to_dict('records') if not trades_list.empty else []
                n_trades = len(trades_list)
                if n_trades < MC_MIN_TRADES_FOR_BOOTSTRAP:
                    # Too few trades to bootstrap — pass through (min_trades gate handles this)
                    mc_passed_ids.add(s.id)
                    continue
                try:
                    import numpy as _np_mc
                    # Extract per-trade returns
                    trade_returns = []
                    for t in trades_list:
                        # Handle both dict and object formats
                        if isinstance(t, dict):
                            ret = t.get('Return') or t.get('return') or t.get('pnl_pct') or t.get('return_pct')
                        else:
                            ret = getattr(t, 'Return', None) or getattr(t, 'return', None) or getattr(t, 'pnl_pct', None)
                        if ret is not None:
                            trade_returns.append(float(ret))
                    if len(trade_returns) < MC_MIN_TRADES_FOR_BOOTSTRAP:
                        mc_passed_ids.add(s.id)
                        continue
                    arr = _np_mc.array(trade_returns)
                    # Bootstrap: resample with replacement, compute Sharpe each iteration.
                    # Annualization: trade-level returns need sqrt(trades_per_year) scaling.
                    # Estimate trades_per_year from test window (180 days default).
                    # This is more accurate than sqrt(n_trades) which conflates sample size
                    # with annualization and produces artificially wide distributions.
                    test_window_days = 180  # matches walk_forward.test_days config
                    trades_per_year = (n_trades / test_window_days) * 252
                    annualization_factor = _np_mc.sqrt(max(trades_per_year, 1.0))
                    bootstrap_sharpes = []
                    for _ in range(MC_ITERATIONS):
                        sample = _np_mc.random.choice(arr, size=len(arr), replace=True)
                        std = sample.std()
                        if std > 0:
                            sharpe = (sample.mean() / std) * annualization_factor
                            bootstrap_sharpes.append(sharpe)
                    if not bootstrap_sharpes:
                        mc_passed_ids.add(s.id)
                        continue
                    p5_sharpe = float(_np_mc.percentile(bootstrap_sharpes, 5))
                    # Threshold: p5 >= 0.0 (break-even in worst 5% of resampled worlds).
                    # A strategy that already passed WF only needs to show its edge is
                    # non-negative under resampling — not that it's strongly positive.
                    # Reject only if the downside tail is genuinely negative (noise).
                    mc_pass = p5_sharpe >= MC_MIN_P5_SHARPE
                    if mc_pass:
                        mc_passed_ids.add(s.id)
                        logger.info(
                            f"MC bootstrap PASS: {s.name} — p5={p5_sharpe:.2f} "
                            f"(n={n_trades} trades, ann={annualization_factor:.1f}x, {MC_ITERATIONS} iters)"
                        )
                    else:
                        logger.info(
                            f"MC bootstrap FAIL: {s.name} — p5={p5_sharpe:.2f} < {MC_MIN_P5_SHARPE} "
                            f"(n={n_trades} trades) — edge likely noise, rejected"
                        )
                except Exception as _mc_err:
                    logger.debug(f"Monte Carlo bootstrap failed for {s.name}: {_mc_err}")
                    mc_passed_ids.add(s.id)  # Fail open — don't block on MC error

            mc_filtered = len(all_wf_results) - len(mc_passed_ids)
            if mc_filtered > 0:
                logger.info(f"Monte Carlo bootstrap: filtered {mc_filtered} strategies as likely noise")

            # Pass 1: Direction-aware thresholds
            # The TEST period is more recent and more relevant for live trading.
            # Train Sharpe matters for confirming the strategy isn't random, but
            # a weak train period doesn't invalidate strong OOS performance.
            validated_strategies = []
            for s, wf, ts, tes, het, ov, tv, tev in all_wf_results:
                if s.id not in mc_passed_ids:
                    continue  # Filtered by Monte Carlo bootstrap
                if wf is None:
                    continue  # Loaded from 4-tuple disk cache — no wf_results dict
                if not (tv and tev and het and not ov):
                    continue
                direction = self._detect_strategy_direction(s)
                thresholds = self._get_direction_aware_thresholds(direction, market_regime)
                min_sharpe = thresholds['min_sharpe']
                test_return = wf['test_results'].total_return if wf.get('test_results') else 0
                min_return = thresholds['min_return']
                test_win_rate = wf['test_results'].win_rate if wf.get('test_results') else 0
                test_trades = wf['test_results'].total_trades if wf.get('test_results') else 0
                min_win_rate = thresholds['min_win_rate']

                # Strategy-type-aware win rate: trend-following strategies (EMA crossover,
                # ATR, ADX, MACD momentum) have inherently lower win rates with higher R:R.
                # A 30% WR with Sharpe 1.5 is a valid trend profile — don't reject it with
                # the mean-reversion 45% floor.
                _stype = self._detect_strategy_type(s) if hasattr(self, '_detect_strategy_type') else 'unknown'
                if _stype in ('trend_following', 'breakout', 'momentum'):
                    min_win_rate = min(min_win_rate, 0.30)  # floor 30% for trend strategies
                
                # Primary path: both train and test above threshold
                if ts > min_sharpe and tes > min_sharpe and test_return >= min_return and test_win_rate >= min_win_rate:
                    validated_strategies.append((s, wf))
                # Test-dominant path: test Sharpe is strong, train is non-negative.
                # The test period is more recent — if it shows edge, the strategy works NOW.
                elif ts >= -0.1 and tes >= min_sharpe and test_return >= min_return and test_win_rate >= min_win_rate:
                    validated_strategies.append((s, wf))
                    logger.info(
                        f"  Passed on strong test Sharpe: {s.name} "
                        f"(train={ts:.2f}, test={tes:.2f}, threshold={min_sharpe})"
                    )
                # Fallback for excellent OOS performers with negative train Sharpe.
                # Train period may have had an adverse regime for this strategy type.
                elif ts >= -0.3 and tes >= min_sharpe * 2 and test_trades >= 3 and test_return >= min_return and test_win_rate >= min_win_rate:
                    validated_strategies.append((s, wf))
                    logger.info(
                        f"  Passed on excellent OOS performance: {s.name} "
                        f"(train={ts:.2f}, test={tes:.2f}, test_trades={test_trades}, threshold={min_sharpe})"
                    )
            
            logger.info(
                f"Walk-forward validation (direction-aware): {len(validated_strategies)}/{len(all_wf_results)} "
                f"strategies passed ({len(validated_strategies)/max(len(all_wf_results),1)*100:.1f}%)"
            )
            
            # Write detailed WF results to cycle log
            try:
                from src.core.cycle_logger import get_cycle_logger
                cl = get_cycle_logger()
                wf_log_results = []
                for s, wf, ts, tes, het, ov, tv, tev in all_wf_results:
                    if wf is None:
                        continue
                    te_results = wf.get('test_results')
                    tr_results = wf.get('train_results')
                    passed = any(s.id == vs.id for vs, _ in validated_strategies) if validated_strategies else False
                    wf_log_results.append({
                        'name': s.name,
                        'symbol': s.symbols[0] if s.symbols else '?',
                        'passed': passed,
                        'train_sharpe': ts,
                        'test_sharpe': tes,
                        'train_trades': tr_results.total_trades if tr_results else 0,
                        'test_trades': te_results.total_trades if te_results else 0,
                        'test_return': te_results.total_return if te_results else 0,
                        'test_win_rate': te_results.win_rate if te_results else 0,
                        'test_drawdown': te_results.max_drawdown if te_results else 0,
                        'overfitted': ov,
                    })
                cl.log_wf_results(wf_log_results)
            except Exception as e:
                logger.debug(f"Could not write WF results to cycle log: {e}")
            
            # Pass 2: If too few passed, add relaxed candidates (Sharpe > 0.1, no direction filter)
            if len(validated_strategies) < 10:
                strict_ids = {s.id for s, _ in validated_strategies}
                relaxed_additions = [
                    (s, wf) for s, wf, ts, tes, het, ov, tv, tev in all_wf_results
                    if s.id not in strict_ids and tv and tev and ts > 0.1 and tes > 0.1 and het and not ov
                ]
                
                if relaxed_additions:
                    validated_strategies.extend(relaxed_additions)
                    logger.info(
                        f"Walk-forward validation (relaxed): added {len(relaxed_additions)} more strategies "
                        f"(total: {len(validated_strategies)})"
                    )
            
            # Select diverse strategies from validated candidates
            if len(validated_strategies) > count:
                strategies = self.select_diverse_strategies(
                    strategies=validated_strategies,
                    count=count,
                    max_correlation=0.7
                )
                logger.info(f"Selected {len(strategies)} diverse strategies from {len(validated_strategies)} validated")
            else:
                strategies = [s[0] for s in validated_strategies]
                logger.info(f"Using all {len(strategies)} validated strategies (fewer than target)")
            
            # Store walk-forward out-of-sample results as backtest_results on each
            # strategy so the downstream activation step does not need to re-backtest.
            for strategy in strategies:
                # Find the matching wf_results
                for s, wf in validated_strategies:
                    if s.id == strategy.id:
                        strategy.backtest_results = wf['test_results']
                        if not hasattr(strategy, 'metadata') or strategy.metadata is None:
                            strategy.metadata = {}
                        strategy.metadata['walk_forward_validated'] = True
                        strategy.metadata['wf_train_sharpe'] = wf['train_sharpe']
                        strategy.metadata['wf_test_sharpe'] = wf['test_sharpe']
                        strategy.metadata['wf_performance_degradation'] = wf['performance_degradation']
                        break
            
            # Add Alpha Edge strategies back (they bypassed walk-forward)
            strategies.extend(alpha_edge_strategies)
            logger.info(f"Final: {len(strategies)} strategies ({len(alpha_edge_strategies)} Alpha Edge + {len(strategies) - len(alpha_edge_strategies)} DSL)")

            # Track approvals (post-WF) for the templates dashboard
            self.track_approvals(strategies)

            # === WATCHLIST VALIDATION ===
            # Walk-forward each watchlist symbol for every validated DSL strategy.
            # Only symbols that pass WF stay in the watchlist. This ensures every
            # symbol a strategy can trade has been proven to work with that template.
            #
            # Tiered thresholds by asset class relationship to primary symbol:
            #   Same class (stock→stock, forex→forex):  S > 0.2, t >= 3
            #   Adjacent   (stock→ETF/index):            S > 0.3, t >= 4
            #   Cross-asset (stock→forex/commodity/crypto): S > 0.5, t >= 6
            #
            # Max watchlist size: 3 total (primary + 2). No floor guarantee —
            # a single-symbol strategy is better than one with a weak second symbol.
            _WL_MAX = 2  # max extra symbols beyond primary

            def _wl_thresholds(primary_class: str, sym_class: str):
                """Return (min_sharpe, min_trades) for a watchlist symbol."""
                if primary_class == sym_class:
                    return 0.2, 3   # same class — relaxed
                # Adjacent: equity ↔ ETF/index
                _equity = {"stock", "etf", "index"}
                if primary_class in _equity and sym_class in _equity:
                    return 0.3, 4   # adjacent
                # Cross-asset: anything else
                return 0.5, 6

            # Detect current regime once — reused for all watchlist regime checks
            _wl_regime = "unknown"
            try:
                from src.strategy.market_analyzer import MarketStatisticsAnalyzer
                from src.data.market_data_manager import get_market_data_manager
                _wl_mdm = get_market_data_manager()
                if _wl_mdm:
                    _wl_analyzer = MarketStatisticsAnalyzer(_wl_mdm)
                    _wl_sub, _, _, _ = _wl_analyzer.detect_sub_regime()
                    _wl_regime = _wl_sub.value
            except Exception:
                pass

            import time as _wl_time
            wl_validated_total = 0
            wl_pruned_total = 0
            for strategy in strategies:
                if not strategy.symbols or len(strategy.symbols) <= 1:
                    continue
                # Skip Alpha Edge (they don't use DSL walk-forward)
                if strategy.metadata and strategy.metadata.get('strategy_category') == 'alpha_edge':
                    continue
                template_name = strategy.metadata.get('template_name', '') if strategy.metadata else ''
                if not template_name:
                    continue

                primary = strategy.symbols[0]
                primary_class = self._get_asset_class(primary)
                validated_symbols = [primary]  # Primary already passed WF

                # Detect template direction for regime compatibility check
                template_direction = 'long'
                if strategy.metadata:
                    template_direction = strategy.metadata.get('direction', 'long').lower()

                for sym in strategy.symbols[1:]:
                    # Hard cap: primary + 2 max
                    if len(validated_symbols) >= _WL_MAX + 1:
                        wl_pruned_total += 1
                        continue

                    # Skip daily-only LME metals — no intraday OR reliable daily data
                    # via Yahoo/FMP for these symbols. Stale _wf_validated_combos.json
                    # entries can inject them here even after the proposal-stage filter.
                    if sym.upper() in _DAILY_ONLY_SYMBOLS:
                        logger.debug(f"  Watchlist WF skip: {sym} is daily-only LME metal, no data for WF")
                        wl_pruned_total += 1
                        continue

                    sym_class = self._get_asset_class(sym)
                    min_sharpe, min_trades = _wl_thresholds(primary_class, sym_class)

                    # Regime compatibility: skip if symbol's regime is incompatible
                    # with the template direction (reuse already-computed regime)
                    if _wl_regime != "unknown":
                        _is_short = template_direction == 'short'
                        _trending_up = 'trending_up' in _wl_regime
                        _trending_down = 'trending_down' in _wl_regime
                        # Short templates in strong uptrend — skip
                        if _is_short and _trending_up and 'strong' in _wl_regime:
                            wl_pruned_total += 1
                            continue
                        # Long templates in strong downtrend — skip
                        if not _is_short and _trending_down and 'strong' in _wl_regime:
                            wl_pruned_total += 1
                            continue

                    # Check blacklist first (cheap)
                    bl_key = (template_name, sym)
                    if bl_key in self._zero_trade_blacklist and self._zero_trade_blacklist[bl_key] >= self._zero_trade_blacklist_threshold:
                        wl_pruned_total += 1
                        continue

                    # Check WF cache (already validated in a previous cycle?)
                    wf_key = (template_name, sym)
                    cached = self._wf_results_cache.get(wf_key)
                    if cached is not None:
                        cached_result, cached_at = cached
                        if _wl_time.time() - cached_at < self._wf_cache_ttl:
                            test_sharpe = cached_result[1]
                            has_trades = cached_result[2]
                            is_overfitted = cached_result[3]
                            if test_sharpe > min_sharpe and has_trades and not is_overfitted:
                                validated_symbols.append(sym)
                                wl_validated_total += 1
                            else:
                                wl_pruned_total += 1
                            continue

                    # No cache — run WF on this symbol
                    try:
                        import copy
                        temp_strategy = copy.deepcopy(strategy)
                        temp_strategy.symbols = [sym]

                        if hasattr(strategy_engine, 'indicator_library'):
                            strategy_engine.indicator_library.clear_cache()
                        if hasattr(strategy_engine.market_data, '_historical_memory_cache'):
                            strategy_engine.market_data._historical_memory_cache.clear()

                        wf_result = strategy_engine.walk_forward_validate(
                            strategy=temp_strategy,
                            start=start_date,
                            end=end_date,
                            train_days=train_days,
                            test_days=test_days
                        )

                        ts = wf_result['train_sharpe']
                        tes = wf_result['test_sharpe']
                        ov = wf_result['is_overfitted']
                        test_trades = wf_result['test_results'].total_trades if wf_result.get('test_results') else 0
                        train_trades = wf_result['train_results'].total_trades if wf_result.get('train_results') else 0
                        het = test_trades >= min_trades and train_trades >= min_trades
                        tv = not (math.isinf(ts) or math.isnan(ts))
                        tev = not (math.isinf(tes) or math.isnan(tes))

                        # Cache the result
                        self._wf_results_cache[wf_key] = (
                            (ts, tes, het, ov, tv, tev, wf_result),
                            _wl_time.time()
                        )

                        if tev and tes > min_sharpe and het and not ov:
                            validated_symbols.append(sym)
                            wl_validated_total += 1
                            self._wf_validated[wf_key] = {
                                'sharpe': round(tes, 3),
                                'trades': test_trades,
                                'timestamp': datetime.now().isoformat(),
                            }
                            self._save_wf_validated_to_disk()
                            logger.info(
                                f"  Watchlist WF PASS: {template_name} on {sym} "
                                f"(S={tes:.2f}, t={test_trades}, threshold=S>{min_sharpe}/t>={min_trades}, "
                                f"class={primary_class}→{sym_class})"
                            )
                        else:
                            wl_pruned_total += 1
                            self._save_wf_failed_to_disk()
                            if test_trades == 0 or train_trades == 0:
                                self._zero_trade_blacklist[bl_key] = self._zero_trade_blacklist.get(bl_key, 0) + 1
                                self._zero_trade_blacklist_timestamps[bl_key] = datetime.now().isoformat()
                                self._save_blacklist_to_disk()
                            logger.info(
                                f"  Watchlist WF FAIL: {template_name} on {sym} "
                                f"(S={tes:.2f}, t={test_trades}, need S>{min_sharpe}/t>={min_trades})"
                            )
                    except Exception as wl_err:
                        logger.debug(f"  Watchlist WF error for {template_name} on {sym}: {wl_err}")
                        wl_pruned_total += 1

                strategy.symbols = validated_symbols

            if wl_validated_total > 0 or wl_pruned_total > 0:
                logger.info(
                    f"Watchlist validation: {wl_validated_total} symbols passed WF, "
                    f"{wl_pruned_total} pruned (threshold/regime/blacklist/cap)"
                )

            # Enforce max 1 strategy per (symbol, direction, type, interval) to prevent concentration
            # Different intervals on the same symbol ARE allowed — they capture different timeframes
            seen_combos = set()
            deduped_strategies = []
            for strategy in strategies:
                primary_symbol = strategy.symbols[0] if strategy.symbols else 'unknown'
                direction = 'LONG'
                if hasattr(strategy, 'metadata') and strategy.metadata:
                    stored_direction = strategy.metadata.get('direction', '')
                    if stored_direction.lower() == 'short':
                        direction = 'SHORT'
                if direction == 'LONG' and hasattr(strategy, 'rules') and strategy.rules:
                    rules = strategy.rules if isinstance(strategy.rules, dict) else {}
                    entry_conditions = rules.get('entry_conditions', [])
                    for cond in entry_conditions:
                        if isinstance(cond, str) and ('SHORT' in cond.upper() or 'SELL' in cond.upper() or 'OVERBOUGHT' in cond.upper()):
                            direction = 'SHORT'
                            break
                tname = strategy.metadata.get('template_name', strategy.name.split(' Multi')[0] if ' Multi' in strategy.name else strategy.name) if strategy.metadata else strategy.name
                interval = strategy.rules.get('interval', '1d') if hasattr(strategy, 'rules') and strategy.rules else '1d'
                
                combo = (primary_symbol, direction, tname, interval)
                if combo in seen_combos:
                    logger.info(f"Dedup: Removing duplicate {strategy.name} ({primary_symbol}/{direction}/{tname}/{interval})")
                    continue
                seen_combos.add(combo)
                deduped_strategies.append(strategy)

            if len(deduped_strategies) < len(strategies):
                logger.info(f"Dedup: Removed {len(strategies) - len(deduped_strategies)} duplicate strategies, {len(deduped_strategies)} remaining")
            strategies = deduped_strategies

            if progress_callback:
                progress_callback(f"Walk-forward validation complete", 100)
        
        else:
            # Standard quality filtering without walk-forward validation
            if len(strategies) > count:
                logger.info(f"Scoring {len(strategies)} strategies for quality filtering")
                scored_strategies = []
                
                for strategy in strategies:
                    quality_score = self.score_strategy_quality(strategy, market_regime, strategies)
                    # Store quality score in metadata
                    if not hasattr(strategy, 'metadata') or strategy.metadata is None:
                        strategy.metadata = {}
                    strategy.metadata['quality_score'] = quality_score
                    scored_strategies.append((strategy, quality_score))
                    logger.info(f"Strategy '{strategy.name}' quality score: {quality_score:.2f}")
                
                # Sort by quality score (descending) and take top N
                scored_strategies.sort(key=lambda x: x[1], reverse=True)
                strategies = [s[0] for s in scored_strategies[:count]]
                
                logger.info(f"Filtered to top {count} strategies by quality score")
                for i, strategy in enumerate(strategies):
                    score = strategy.metadata.get('quality_score', 0.0)
                    logger.info(f"  {i+1}. {strategy.name} (score: {score:.2f})")
        
        # NEW: Filter proposals similar to active strategies BEFORE returning
        if strategy_engine:
            try:
                active_strategies = strategy_engine.get_active_strategies()
                
                if active_strategies:
                    # Check if similarity detection is enabled in config
                    similarity_enabled = True
                    proposal_threshold = 70
                    try:
                        import yaml
                        from pathlib import Path
                        config_path = Path("config/autonomous_trading.yaml")
                        if config_path.exists():
                            with open(config_path, 'r') as f:
                                config = yaml.safe_load(f)
                                sim_config = config.get('similarity_detection', {})
                                similarity_enabled = sim_config.get('enabled', True)
                                proposal_threshold = sim_config.get('proposal_similarity_threshold', 70)
                    except Exception as e:
                        logger.warning(f"Could not load similarity config: {e}")
                    
                    if not similarity_enabled:
                        logger.info(f"Similarity detection disabled in config — skipping proposal filtering")
                    else:
                        logger.info(f"Filtering proposals against {len(active_strategies)} active strategies")
                        
                        filtered_strategies = []
                        for proposed_strategy in strategies:
                            is_too_similar = False
                            
                            for active_strategy in active_strategies:
                                similarity = strategy_engine._compute_strategy_similarity(
                                    proposed_strategy, 
                                    active_strategy
                                )
                                
                                if similarity > proposal_threshold:
                                    logger.info(
                                        f"Filtered proposal '{proposed_strategy.name}' - "
                                        f"{similarity:.1f}% similar to active '{active_strategy.name}' "
                                        f"(threshold: {proposal_threshold}%)"
                                    )
                                    is_too_similar = True
                                    break
                            
                            if not is_too_similar:
                                filtered_strategies.append(proposed_strategy)
                        
                        logger.info(
                            f"Similarity filtering: {len(filtered_strategies)}/{len(strategies)} proposals "
                            f"passed ({len(strategies) - len(filtered_strategies)} filtered)"
                        )
                        
                        strategies = filtered_strategies
            except Exception as e:
                logger.warning(f"Error during proposal similarity filtering: {e}")
                # Continue with unfiltered strategies if filtering fails
        
        logger.info(f"Successfully proposed {len(strategies)} strategies")
        return strategies
    
    def score_strategy_quality(
        self,
        strategy: Strategy,
        market_regime: MarketRegime,
        all_strategies: List[Strategy]
    ) -> float:
        """
        Score strategy quality based on multiple factors.
        
        Args:
            strategy: Strategy to score
            market_regime: Current market regime
            all_strategies: All strategies in the batch (for diversity scoring)
        
        Returns:
            Quality score between 0.0 and 1.0
        """
        scores = []
        weights = []
        
        # 1. Complexity Score (weight: 0.25)
        # Ideal: 2-3 indicators, too simple: 1, too complex: 4+
        indicators = strategy.rules.get("indicators", [])
        num_indicators = len(indicators)
        
        if num_indicators == 0:
            complexity_score = 0.0
        elif num_indicators == 1:
            complexity_score = 0.5  # Too simple
        elif num_indicators in [2, 3]:
            complexity_score = 1.0  # Ideal
        else:
            complexity_score = max(0.3, 1.0 - (num_indicators - 3) * 0.15)  # Too complex
        
        scores.append(complexity_score)
        weights.append(0.25)
        logger.debug(f"Complexity score for '{strategy.name}': {complexity_score:.2f} ({num_indicators} indicators)")
        
        # 2. Logic Score (weight: 0.30)
        # Check for balanced entry/exit conditions
        entry_conditions = strategy.rules.get("entry_conditions", [])
        exit_conditions = strategy.rules.get("exit_conditions", [])
        
        has_entry = len(entry_conditions) > 0
        has_exit = len(exit_conditions) > 0
        
        if has_entry and has_exit:
            # Both present - check balance
            entry_count = len(entry_conditions)
            exit_count = len(exit_conditions)
            balance_ratio = min(entry_count, exit_count) / max(entry_count, exit_count)
            logic_score = 0.7 + (balance_ratio * 0.3)  # 0.7-1.0 range
        elif has_entry or has_exit:
            logic_score = 0.3  # Only one side
        else:
            logic_score = 0.0  # Neither
        
        scores.append(logic_score)
        weights.append(0.30)
        logger.debug(f"Logic score for '{strategy.name}': {logic_score:.2f} (entry: {len(entry_conditions)}, exit: {len(exit_conditions)})")
        
        # 3. Diversity Score (weight: 0.25)
        # Penalize strategies too similar to others
        diversity_score = 1.0
        
        for other_strategy in all_strategies:
            if other_strategy.id == strategy.id:
                continue
            
            # Compare indicators used
            other_indicators = set(other_strategy.rules.get("indicators", []))
            strategy_indicators = set(indicators)
            
            if len(strategy_indicators) > 0 and len(other_indicators) > 0:
                # Calculate Jaccard similarity
                intersection = len(strategy_indicators & other_indicators)
                union = len(strategy_indicators | other_indicators)
                similarity = intersection / union if union > 0 else 0
                
                # Penalize high similarity
                if similarity > 0.7:
                    diversity_score *= 0.7  # Strong penalty
                elif similarity > 0.5:
                    diversity_score *= 0.85  # Moderate penalty
        
        scores.append(diversity_score)
        weights.append(0.25)
        logger.debug(f"Diversity score for '{strategy.name}': {diversity_score:.2f}")
        
        # 4. Regime Appropriateness Score (weight: 0.20)
        # Score how well strategy matches current market regime
        regime_score = self._score_regime_appropriateness(strategy, market_regime)
        
        scores.append(regime_score)
        weights.append(0.20)
        logger.debug(f"Regime appropriateness score for '{strategy.name}': {regime_score:.2f}")
        
        # Calculate weighted average
        total_score = sum(s * w for s, w in zip(scores, weights))
        
        logger.info(f"Overall quality score for '{strategy.name}': {total_score:.2f}")
        return total_score

    def select_diverse_strategies(
        self,
        strategies: List[Tuple[Strategy, Dict[str, Any]]],
        count: int,
        max_correlation: float = 0.7
    ) -> List[Strategy]:
        """
        Select diverse strategies with low correlation.

        Args:
            strategies: List of (strategy, walk_forward_results) tuples
            count: Number of strategies to select
            max_correlation: Maximum allowed correlation between strategies (default 0.7)

        Returns:
            List of selected diverse strategies
        """
        logger.info(f"Selecting {count} diverse strategies from {len(strategies)} candidates")

        if len(strategies) <= count:
            logger.info("Fewer candidates than requested, returning all")
            return [s[0] for s in strategies]

        # Extract returns series for correlation calculation
        returns_series = {}
        for strategy, wf_results in strategies:
            # Use test period returns for correlation (out-of-sample)
            test_results = wf_results['test_results']
            if hasattr(test_results, 'returns') and test_results.returns is not None:
                returns_series[strategy.id] = test_results.returns
            else:
                # If no returns series, use a placeholder (will have low correlation)
                logger.warning(f"No returns series for {strategy.name}, using placeholder")
                returns_series[strategy.id] = pd.Series([0.0] * 30)

        # Calculate correlation matrix
        if len(returns_series) > 1:
            # Align all returns series to same index
            returns_df = pd.DataFrame(returns_series)
            correlation_matrix = returns_df.corr()
            logger.info(f"Correlation matrix shape: {correlation_matrix.shape}")
        else:
            correlation_matrix = pd.DataFrame()

        # Selection algorithm: greedy selection with diversity preference
        selected = []
        remaining = list(strategies)

        # Sort by combined train+test Sharpe (descending)
        remaining.sort(
            key=lambda x: (x[1]['train_sharpe'] + x[1]['test_sharpe']) / 2,
            reverse=True
        )

        # Select first strategy (highest combined Sharpe)
        if remaining:
            selected.append(remaining.pop(0))
            logger.info(f"Selected strategy 1: {selected[0][0].name} (highest Sharpe)")

        # Select remaining strategies with diversity preference
        while len(selected) < count and remaining:
            best_candidate = None
            best_score = -float('inf')

            for candidate_tuple in remaining:
                candidate, wf_results = candidate_tuple

                # Calculate diversity score
                diversity_score = 0.0

                # Check correlation with already selected strategies
                if len(correlation_matrix) > 0:
                    max_corr = 0.0
                    for selected_tuple in selected:
                        selected_strategy = selected_tuple[0]
                        if candidate.id in correlation_matrix.index and selected_strategy.id in correlation_matrix.columns:
                            corr = abs(correlation_matrix.loc[candidate.id, selected_strategy.id])
                            max_corr = max(max_corr, corr)

                    # Penalize high correlation
                    if max_corr > max_correlation:
                        diversity_score -= 10.0  # Strong penalty
                    else:
                        diversity_score += (1.0 - max_corr) * 5.0  # Reward low correlation

                # Prefer different strategy types
                selected_types = set()
                for selected_tuple in selected:
                    selected_strategy = selected_tuple[0]
                    if hasattr(selected_strategy, 'metadata') and selected_strategy.metadata:
                        strategy_type = selected_strategy.metadata.get('strategy_type', 'unknown')
                        selected_types.add(strategy_type)

                candidate_type = 'unknown'
                if hasattr(candidate, 'metadata') and candidate.metadata:
                    candidate_type = candidate.metadata.get('strategy_type', 'unknown')

                if candidate_type not in selected_types:
                    diversity_score += 3.0  # Reward different type

                # Prefer different indicator combinations
                selected_indicators = set()
                for selected_tuple in selected:
                    selected_strategy = selected_tuple[0]
                    if 'indicators' in selected_strategy.rules:
                        selected_indicators.update(selected_strategy.rules['indicators'])

                candidate_indicators = set(candidate.rules.get('indicators', []))
                indicator_overlap = len(candidate_indicators & selected_indicators)
                indicator_unique = len(candidate_indicators - selected_indicators)

                if indicator_unique > 0:
                    diversity_score += indicator_unique * 0.5  # Reward unique indicators
                if indicator_overlap > 0:
                    diversity_score -= indicator_overlap * 0.3  # Penalize overlap

                # Combine with performance score
                combined_sharpe = (wf_results['train_sharpe'] + wf_results['test_sharpe']) / 2
                performance_score = combined_sharpe * 2.0

                total_score = diversity_score + performance_score

                if total_score > best_score:
                    best_score = total_score
                    best_candidate = candidate_tuple

            if best_candidate:
                selected.append(best_candidate)
                remaining.remove(best_candidate)
                logger.info(
                    f"Selected strategy {len(selected)}: {best_candidate[0].name} "
                    f"(score: {best_score:.2f})"
                )
            else:
                break

        # Log diversity metrics
        if len(selected) > 1 and len(correlation_matrix) > 0:
            selected_ids = [s[0].id for s in selected]
            selected_corr = correlation_matrix.loc[selected_ids, selected_ids]

            # Calculate average correlation (excluding diagonal)
            mask = ~pd.DataFrame(selected_corr).eq(1.0)
            avg_correlation = selected_corr.where(mask).mean().mean()

            logger.info(f"Selected strategies average correlation: {avg_correlation:.3f}")

            # Log strategy types
            selected_types = []
            for strategy_tuple in selected:
                strategy = strategy_tuple[0]
                if hasattr(strategy, 'metadata') and strategy.metadata:
                    strategy_type = strategy.metadata.get('strategy_type', 'unknown')
                    selected_types.append(strategy_type)

            logger.info(f"Selected strategy types: {selected_types}")

        return [s[0] for s in selected]

    
    def _score_regime_appropriateness(
        self,
        strategy: Strategy,
        market_regime: MarketRegime
    ) -> float:
        """
        Score how well a strategy matches the current market regime.
        
        Args:
            strategy: Strategy to score
            market_regime: Current market regime
        
        Returns:
            Score between 0.0 and 1.0
        """
        indicators = set(strategy.rules.get("indicators", []))
        description = strategy.description.lower()
        
        # Define regime-appropriate indicators and keywords
        regime_profiles = {
            MarketRegime.TRENDING_UP: {
                "indicators": {"SMA", "EMA", "MACD", "ATR"},
                "keywords": ["momentum", "trend", "breakout", "uptrend", "bullish"],
                "avoid_keywords": ["mean reversion", "oversold", "support"]
            },
            MarketRegime.TRENDING_DOWN: {
                "indicators": {"RSI", "Stochastic Oscillator", "Support/Resistance"},
                "keywords": ["defensive", "oversold", "bounce", "support", "reversal"],
                "avoid_keywords": ["breakout", "momentum", "bullish"]
            },
            MarketRegime.RANGING: {
                "indicators": {"RSI", "Bollinger Bands", "Stochastic Oscillator", "Support/Resistance"},
                "keywords": ["mean reversion", "range", "oscillator", "support", "resistance"],
                "avoid_keywords": ["trend", "breakout", "momentum"]
            }
        }
        
        profile = regime_profiles.get(market_regime, {})
        appropriate_indicators = profile.get("indicators", set())
        keywords = profile.get("keywords", [])
        avoid_keywords = profile.get("avoid_keywords", [])
        
        score = 0.5  # Base score
        
        # Check indicator alignment (up to +0.3)
        if indicators:
            indicator_overlap = len(indicators & appropriate_indicators)
            indicator_score = min(0.3, indicator_overlap * 0.15)
            score += indicator_score
        
        # Check keyword presence (up to +0.2)
        keyword_matches = sum(1 for kw in keywords if kw in description)
        keyword_score = min(0.2, keyword_matches * 0.1)
        score += keyword_score
        
        # Penalize avoid keywords (up to -0.2)
        avoid_matches = sum(1 for kw in avoid_keywords if kw in description)
        avoid_penalty = min(0.2, avoid_matches * 0.1)
        score -= avoid_penalty
        
        # Clamp to [0, 1]
        return max(0.0, min(1.0, score))
    
    def revise_strategy(
        self,
        failed_strategy: Strategy,
        validation_errors: List[str],
        market_regime: MarketRegime,
        available_indicators: List[str]
    ) -> Optional[Strategy]:
        """
        Revise a failed strategy based on validation errors.
        
        Args:
            failed_strategy: Strategy that failed validation
            validation_errors: List of specific validation errors
            market_regime: Current market regime
            available_indicators: List of available indicators
        
        Returns:
            Revised Strategy object or None if revision fails
        """
        logger.info(f"Attempting to revise strategy '{failed_strategy.name}' due to errors: {validation_errors}")
        
        # Create revision prompt with specific errors
        errors_text = "\n".join(f"- {error}" for error in validation_errors)
        
        prompt = f"""The previous strategy failed validation. Please generate a REVISED strategy that fixes these issues.

ORIGINAL STRATEGY:
Name: {failed_strategy.name}
Description: {failed_strategy.description}
Entry Conditions: {failed_strategy.rules.get('entry_conditions', [])}
Exit Conditions: {failed_strategy.rules.get('exit_conditions', [])}
Indicators: {failed_strategy.rules.get('indicators', [])}

VALIDATION ERRORS:
{errors_text}

REQUIREMENTS FOR REVISED STRATEGY:
1. Fix ALL validation errors listed above
2. Maintain the core strategy concept if possible
3. Use EXACT indicator naming convention (e.g., "RSI_14", "SMA_20", "Upper_Band_20")
4. Ensure entry and exit conditions are balanced and opposite
5. Use 2-3 indicators from: {', '.join(available_indicators)}
6. Appropriate for {market_regime.value} market

Generate a CORRECTED strategy that addresses all errors:"""
        
        try:
            # Generate revised strategy using LLM
            market_context = {
                "risk_config": failed_strategy.risk_params,
                "available_symbols": failed_strategy.symbols,
                "symbols": failed_strategy.symbols
            }
            
            strategy_def = self.llm_service.generate_strategy(prompt, market_context)
            
            # Create revised Strategy object
            revised_strategy = Strategy(
                id=str(uuid.uuid4()),
                name=f"{strategy_def.name} (Revised)",
                description=strategy_def.description,
                status=StrategyStatus.PROPOSED,
                rules=strategy_def.rules,
                symbols=strategy_def.symbols,
                risk_params=strategy_def.risk_params,
                created_at=datetime.now(),
                performance=PerformanceMetrics(),
                reasoning=strategy_def.reasoning
            )
            
            # Track revision metadata
            if not hasattr(revised_strategy, 'metadata') or revised_strategy.metadata is None:
                revised_strategy.metadata = {}
            revised_strategy.metadata['original_strategy_id'] = failed_strategy.id
            revised_strategy.metadata['revision_count'] = failed_strategy.metadata.get('revision_count', 0) + 1
            revised_strategy.metadata['revision_errors'] = validation_errors
            
            logger.info(f"Successfully revised strategy: {revised_strategy.name}")
            return revised_strategy
        
        except Exception as e:
            logger.error(f"Failed to revise strategy: {e}")
            return None
    
    def generate_from_template(
        self,
        template: StrategyTemplate,
        symbols: List[str],
        market_statistics: Dict,
        indicator_distributions: Dict,
        market_context: Dict,
        optimize_parameters: bool = False,
        optimization_start: datetime = None,
        optimization_end: datetime = None
    ) -> Strategy:
        """
        Generate a strategy from a template using market statistics.
        
        Args:
            template: Strategy template to use
            symbols: Symbols to trade
            market_statistics: Market statistics from MarketStatisticsAnalyzer
            indicator_distributions: Indicator distribution data
            market_context: Market context (VIX, rates, etc.)
            optimize_parameters: Whether to optimize parameters using grid search
            optimization_start: Start date for parameter optimization
            optimization_end: End date for parameter optimization
            
        Returns:
            Strategy object generated from template
        """
        logger.info(f"Generating strategy from template: {template.name}")
        
        # Customize template parameters based on market statistics
        customized_params = self.customize_template_parameters(
            template=template,
            market_statistics=market_statistics,
            indicator_distributions=indicator_distributions,
            market_context=market_context
        )
        
        # Optionally optimize parameters using grid search
        if optimize_parameters and optimization_start and optimization_end:
            logger.info(f"Optimizing parameters for template: {template.name}")
            
            # First create a strategy with default parameters for optimization
            temp_strategy = self._create_strategy_from_params(
                template, symbols, customized_params, market_statistics
            )
            
            # Import ParameterOptimizer here to avoid circular imports
            from src.strategy.parameter_optimizer import ParameterOptimizer
            
            # Initialize optimizer with strategy engine
            optimizer = ParameterOptimizer(self.strategy_engine)
            
            # Run optimization
            try:
                optimization_result = optimizer.optimize(
                    template=template,
                    strategy=temp_strategy,
                    start=optimization_start,
                    end=optimization_end,
                    min_out_of_sample_sharpe=0.3
                )
                
                # Log optimization results
                logger.info(
                    f"Optimization complete: "
                    f"best Sharpe={optimization_result['best_sharpe']:.2f}, "
                    f"improvement={optimization_result['sharpe_improvement']:.1f}%, "
                    f"tested={optimization_result['tested_combinations']} combinations"
                )
                
                # Apply optimized parameters if optimization succeeded
                if not optimization_result.get('optimization_failed', False):
                    customized_params.update(optimization_result['best_params'])
                    logger.info(f"Using optimized parameters: {optimization_result['best_params']}")
                else:
                    logger.warning("Optimization failed, using default parameters")
            
            except Exception as e:
                logger.error(f"Parameter optimization failed: {e}")
                logger.warning("Falling back to default parameters")
        
        # Build entry and exit conditions with customized parameters
        entry_conditions = []
        exit_conditions = []
        
        for condition_template in template.entry_conditions:
            customized_condition = self._apply_parameters_to_condition(
                condition_template,
                customized_params
            )
            entry_conditions.append(customized_condition)
        
        for condition_template in template.exit_conditions:
            customized_condition = self._apply_parameters_to_condition(
                condition_template,
                customized_params
            )
            exit_conditions.append(customized_condition)
        
        # Extract indicator names from required_indicators
        # The template already specifies exact indicator keys (e.g., "SMA_20", "SMA_50")
        # We need to map these to the indicator names that StrategyEngine understands
        
        indicators = []
        for template_indicator in template.required_indicators:
            # Map exact indicator keys to indicator names for StrategyEngine
            # StrategyEngine expects indicator names like "SMA", "RSI", "Bollinger Bands"
            # and will calculate all required periods based on the DSL rules
            
            if "Band" in template_indicator or "BBANDS" in template_indicator:
                # Bollinger Bands indicators
                if "Bollinger Bands" not in indicators:
                    indicators.append("Bollinger Bands")
            elif "MACD" in template_indicator:
                # MACD indicators
                if "MACD" not in indicators:
                    indicators.append("MACD")
            elif template_indicator in ["Support", "Resistance"]:
                # Support/Resistance
                if "Support/Resistance" not in indicators:
                    indicators.append("Support/Resistance")
            elif "STOCH" in template_indicator:
                # Stochastic Oscillator
                if "Stochastic Oscillator" not in indicators:
                    indicators.append("Stochastic Oscillator")
            elif "_" in template_indicator:
                # Extract base name and period (e.g., "RSI_14" -> "RSI", "SMA_20" -> "SMA")
                parts = template_indicator.split("_")
                base_name = parts[0]
                period = parts[1] if len(parts) > 1 else None
                
                # Add indicator with period specification
                # Format: "INDICATOR:period" so StrategyEngine knows to calculate this specific period
                if period and period.isdigit():
                    indicator_spec = f"{base_name}:{period}"
                    if indicator_spec not in indicators:
                        indicators.append(indicator_spec)
                else:
                    # No period specified, just add base name
                    if base_name not in indicators:
                        indicators.append(base_name)
            else:
                # Direct indicator name without underscore
                if template_indicator not in indicators:
                    indicators.append(template_indicator)
        
        # Create strategy object
        strategy = Strategy(
            id=str(uuid.uuid4()),
            name=template.name,
            description=template.description,
            status=StrategyStatus.PROPOSED,
            rules={
                "entry_conditions": entry_conditions,
                "exit_conditions": exit_conditions,
                "indicators": indicators
            },
            symbols=symbols,
            risk_params=self._compute_adaptive_risk_config(
                strategy_type=template.strategy_type,
                symbols=symbols,
                market_statistics=market_statistics,
                template_params=customized_params,
            ),
            created_at=datetime.now(),
            performance=PerformanceMetrics(),
            reasoning=f"Generated from template: {template.name}. {template.description}"
        )
        
        # Apply asset-class-specific risk parameter overrides
        primary_symbol = symbols[0] if symbols else None
        asset_class = self._get_asset_class(primary_symbol) if primary_symbol else "stock"
        strategy.risk_params = self._apply_asset_class_overrides(strategy.risk_params, primary_symbol) if primary_symbol else strategy.risk_params

        # Add template metadata
        if not hasattr(strategy, 'metadata') or strategy.metadata is None:
            strategy.metadata = {}
        strategy.metadata['template_name'] = template.name
        strategy.metadata['template_type'] = template.strategy_type.value
        strategy.metadata['customized_parameters'] = customized_params
        strategy.metadata['asset_class'] = asset_class
        
        # Propagate critical template flags
        if template.metadata:
            for key in ['crypto_optimized', 'intraday', 'interval', 'interval_4h', 'skip_param_override', 'strategy_category',
                        'direction', 'alpha_edge_type', 'alpha_edge_bypass', 'market_neutral', 'pair_symbols']:
                if key in template.metadata:
                    strategy.metadata[key] = template.metadata[key]
        
        logger.info(f"Strategy generated from template: {strategy.name}")
        logger.debug(f"Entry conditions: {entry_conditions}")
        logger.debug(f"Exit conditions: {exit_conditions}")
        logger.debug(f"Indicators: {indicators}")
        
        return strategy
    
    def _create_strategy_from_params(
        self,
        template: StrategyTemplate,
        symbols: List[str],
        params: Dict,
        market_statistics: Optional[Dict] = None
    ) -> Strategy:
        """
        Create a strategy from template and parameters (helper for optimization).
        
        Args:
            template: Strategy template
            symbols: Symbols to trade
            params: Parameter dictionary
        
        Returns:
            Strategy object
        """
        # Build entry and exit conditions with parameters
        entry_conditions = []
        exit_conditions = []
        
        for condition_template in template.entry_conditions:
            customized_condition = self._apply_parameters_to_condition(
                condition_template,
                params
            )
            entry_conditions.append(customized_condition)
        
        for condition_template in template.exit_conditions:
            customized_condition = self._apply_parameters_to_condition(
                condition_template,
                params
            )
            exit_conditions.append(customized_condition)
        
        # Extract indicator names from required_indicators
        indicators = []
        for template_indicator in template.required_indicators:
            if "Band" in template_indicator or "BBANDS" in template_indicator:
                if "Bollinger Bands" not in indicators:
                    indicators.append("Bollinger Bands")
            elif "MACD" in template_indicator:
                if "MACD" not in indicators:
                    indicators.append("MACD")
            elif template_indicator in ["Support", "Resistance"]:
                if "Support/Resistance" not in indicators:
                    indicators.append("Support/Resistance")
            elif "STOCH" in template_indicator:
                if "Stochastic Oscillator" not in indicators:
                    indicators.append("Stochastic Oscillator")
            elif "_" in template_indicator:
                parts = template_indicator.split("_")
                base_name = parts[0]
                period = parts[1] if len(parts) > 1 else None
                
                if period and period.isdigit():
                    indicator_spec = f"{base_name}:{period}"
                    if indicator_spec not in indicators:
                        indicators.append(indicator_spec)
                else:
                    if base_name not in indicators:
                        indicators.append(base_name)
            else:
                if template_indicator not in indicators:
                    indicators.append(template_indicator)
        
        # Create strategy object
        strategy = Strategy(
            id=str(uuid.uuid4()),
            name=template.name,
            description=template.description,
            status=StrategyStatus.PROPOSED,
            rules={
                "entry_conditions": entry_conditions,
                "exit_conditions": exit_conditions,
                "indicators": indicators
            },
            symbols=symbols,
            risk_params=self._compute_adaptive_risk_config(
                strategy_type=template.strategy_type,
                symbols=symbols,
                market_statistics=market_statistics,
                template_params=params,
            ),
            created_at=datetime.now(),
            performance=PerformanceMetrics(),
            reasoning=f"Generated from template: {template.name}. {template.description}"
        )
        
        # Apply asset-class-specific risk parameter overrides
        primary_symbol = symbols[0] if symbols else None
        asset_class = self._get_asset_class(primary_symbol) if primary_symbol else "stock"
        strategy.risk_params = self._apply_asset_class_overrides(strategy.risk_params, primary_symbol) if primary_symbol else strategy.risk_params

        # Add template to metadata for walk-forward analysis
        if not hasattr(strategy, 'metadata') or strategy.metadata is None:
            strategy.metadata = {}
        # Don't store template object (not JSON serializable) - store name and type instead
        strategy.metadata['template_name'] = template.name
        strategy.metadata['template_type'] = template.strategy_type.value
        strategy.metadata['asset_class'] = asset_class
        
        # Propagate critical template flags
        if template.metadata:
            for key in ['crypto_optimized', 'intraday', 'interval', 'interval_4h', 'skip_param_override', 'strategy_category',
                        'direction', 'alpha_edge_type', 'alpha_edge_bypass', 'market_neutral', 'pair_symbols']:
                if key in template.metadata:
                    strategy.metadata[key] = template.metadata[key]
        
        return strategy
    
    def customize_template_parameters(
        self,
        template: StrategyTemplate,
        market_statistics: Dict,
        indicator_distributions: Dict,
        market_context: Dict
    ) -> Dict:
        """
        Customize template parameters based on market statistics.
        
        Args:
            template: Strategy template
            market_statistics: Market statistics from MarketStatisticsAnalyzer
            indicator_distributions: Indicator distribution data
            market_context: Market context (VIX, rates, etc.)
            
        Returns:
            Dictionary of customized parameters
        """
        logger.info(f"Customizing parameters for template: {template.name}")
        
        # Start with default parameters
        params = template.default_parameters.copy()
        
        # HIGH-SENSITIVITY TEMPLATES: Skip parameter overrides to preserve
        # intentionally relaxed thresholds that fire in normal market conditions
        if template.metadata and template.metadata.get('skip_param_override', False):
            logger.info(f"Skipping parameter overrides for high-sensitivity template: {template.name}")
            return params
        
        # Get average market statistics across all symbols
        avg_volatility = 0.0
        avg_trend_strength = 0.0
        avg_mean_reversion_score = 0.0
        
        if market_statistics:
            volatilities = []
            trend_strengths = []
            mean_reversion_scores = []
            
            for symbol, stats in market_statistics.items():
                vol = stats.get('volatility_metrics', {}).get('volatility', 0.0)
                trend = stats.get('trend_metrics', {}).get('trend_strength', 0.0)
                mr_score = stats.get('mean_reversion_metrics', {}).get('mean_reversion_score', 0.0)
                
                volatilities.append(vol)
                trend_strengths.append(trend)
                mean_reversion_scores.append(mr_score)
            
            if volatilities:
                avg_volatility = sum(volatilities) / len(volatilities)
            if trend_strengths:
                avg_trend_strength = sum(trend_strengths) / len(trend_strengths)
            if mean_reversion_scores:
                avg_mean_reversion_score = sum(mean_reversion_scores) / len(mean_reversion_scores)
        
        logger.debug(f"Average market metrics: volatility={avg_volatility:.3f}, "
                    f"trend_strength={avg_trend_strength:.2f}, "
                    f"mean_reversion_score={avg_mean_reversion_score:.2f}")
        
        # Adjust RSI thresholds based on indicator distributions
        if indicator_distributions:
            # Get RSI distribution from first symbol
            first_symbol = list(indicator_distributions.keys())[0]
            rsi_dist = indicator_distributions[first_symbol].get('RSI', {})
            
            if rsi_dist:
                pct_oversold = rsi_dist.get('pct_oversold', 5.0)
                pct_overbought = rsi_dist.get('pct_overbought', 5.0)
                
                logger.debug(f"RSI distribution: oversold={pct_oversold:.1f}%, overbought={pct_overbought:.1f}%")
                
                # Adjust thresholds based on distribution — but never relax beyond
                # the template's own threshold. The template threshold is the maximum
                # acceptable looseness. We can tighten (make more selective) but not loosen.
                if 'oversold_threshold' in params:
                    template_threshold = template.default_parameters.get('oversold_threshold', 30)
                    if pct_oversold > 20:
                        # Too common, tighten threshold
                        params['oversold_threshold'] = max(template_threshold - 5, 20)
                        logger.info(f"Tightened RSI oversold threshold to {params['oversold_threshold']} (was {template_threshold}, fires {pct_oversold:.0f}% of time)")
                    # Don't relax — the template threshold is already the maximum
                
                if 'overbought_threshold' in params:
                    template_threshold = template.default_parameters.get('overbought_threshold', 70)
                    if pct_overbought > 20:
                        # Too common, tighten threshold
                        params['overbought_threshold'] = min(template_threshold + 5, 85)
                        logger.info(f"Tightened RSI overbought threshold to {params['overbought_threshold']} (was {template_threshold}, fires {pct_overbought:.0f}% of time)")
                    # Don't relax — the template threshold is already the maximum
        
        # Adjust Bollinger Band parameters based on volatility
        if 'bb_std' in params:
            if avg_volatility > 0.03:  # High volatility (>3% daily)
                params['bb_std'] = 2.5
                logger.info(f"Adjusted Bollinger Band std to 2.5 (high volatility: {avg_volatility:.3f})")
            elif avg_volatility < 0.01:  # Low volatility (<1% daily)
                params['bb_std'] = 1.5
                logger.info(f"Adjusted Bollinger Band std to 1.5 (low volatility: {avg_volatility:.3f})")
            else:  # Moderate volatility - use tighter bands for more signals
                params['bb_std'] = 1.8
                logger.info(f"Adjusted Bollinger Band std to 1.8 (moderate volatility: {avg_volatility:.3f})")
        
        if 'bb_period' in params:
            if avg_volatility > 0.03:
                params['bb_period'] = 30  # Longer period for high volatility
                logger.info(f"Adjusted Bollinger Band period to 30 (high volatility)")
            elif avg_volatility < 0.01:
                params['bb_period'] = 15  # Shorter period for low volatility
                logger.info(f"Adjusted Bollinger Band period to 15 (low volatility)")
        
        # Adjust ATR multiplier for ranging markets - MORE AGGRESSIVE FOR LOW VOL
        if 'atr_multiplier' in params:
            if avg_volatility > 0.03:  # High volatility
                params['atr_multiplier'] = 1.2
                logger.info(f"Adjusted ATR multiplier to 1.2 (high volatility: {avg_volatility:.3f})")
            elif avg_volatility < 0.015:  # Low/moderate volatility - use MUCH smaller multiplier
                params['atr_multiplier'] = 0.5  # Changed from 0.8 to 0.5 for more signals
                logger.info(f"Adjusted ATR multiplier to 0.5 (low volatility: {avg_volatility:.3f})")
            else:  # Moderate volatility
                params['atr_multiplier'] = 0.8  # Changed from 1.0 to 0.8
                logger.info(f"Adjusted ATR multiplier to 0.8 (moderate volatility: {avg_volatility:.3f})")
        
        # Adjust moving average periods based on trend strength
        if 'fast_period' in params and 'slow_period' in params:
            if avg_trend_strength > 0.7:
                # Strong trend, use shorter periods for faster response
                params['fast_period'] = 10
                params['slow_period'] = 30
                logger.info(f"Adjusted MA periods to 10/30 (strong trend: {avg_trend_strength:.2f})")
            elif avg_trend_strength < 0.3:
                # Weak trend, use longer periods for stability
                params['fast_period'] = 30
                params['slow_period'] = 90
                logger.info(f"Adjusted MA periods to 30/90 (weak trend: {avg_trend_strength:.2f})")
        
        # Adjust thresholds based on VIX (market fear)
        vix = market_context.get('vix', 20.0)
        treasury_10y = market_context.get('treasury_10y', 4.0)
        unemployment_rate = market_context.get('unemployment_rate', 4.0)
        unemployment_trend = market_context.get('unemployment_trend', 'stable')
        fed_funds_rate = market_context.get('fed_funds_rate', 5.0)
        
        logger.info(
            f"Macro context: VIX={vix:.1f}, Treasury={treasury_10y:.2f}%, "
            f"Unemployment={unemployment_rate:.1f}% ({unemployment_trend}), "
            f"Fed Funds={fed_funds_rate:.2f}%"
        )
        
        # VIX-based adjustments
        if vix > 25:  # High fear
            # Use more conservative thresholds
            if 'oversold_threshold' in params:
                params['oversold_threshold'] = min(params['oversold_threshold'] + 5, 40)
                logger.info(f"Adjusted oversold threshold for high VIX ({vix:.1f})")
            if 'overbought_threshold' in params:
                params['overbought_threshold'] = max(params['overbought_threshold'] - 5, 60)
                logger.info(f"Adjusted overbought threshold for high VIX ({vix:.1f})")
        
        # Treasury Yields Rising (10Y > 4.5%): Tighten stop-losses, favor shorter-term
        if treasury_10y > 4.5:
            logger.info(f"High treasury yields ({treasury_10y:.2f}%) - tightening parameters")
            
            # Tighten stop-losses (reduce holding periods)
            if 'stop_loss_pct' in params:
                params['stop_loss_pct'] = max(params.get('stop_loss_pct', 0.02) * 0.8, 0.015)
                logger.info(f"Tightened stop-loss to {params['stop_loss_pct']:.3f} (high yields)")
            
            # Favor shorter-term strategies (reduce MA periods)
            if 'fast_period' in params:
                params['fast_period'] = max(int(params['fast_period'] * 0.8), 5)
                logger.info(f"Reduced fast MA period to {params['fast_period']} (high yields)")
            if 'slow_period' in params:
                params['slow_period'] = max(int(params['slow_period'] * 0.8), 20)
                logger.info(f"Reduced slow MA period to {params['slow_period']} (high yields)")
        
        # Unemployment Rising: More conservative entry, wider stops
        if unemployment_trend == 'rising':
            logger.info(f"Rising unemployment ({unemployment_rate:.1f}%) - conservative parameters")
            
            # More conservative entry thresholds
            if 'oversold_threshold' in params:
                params['oversold_threshold'] = max(params['oversold_threshold'] - 5, 20)
                logger.info(f"More conservative oversold threshold: {params['oversold_threshold']}")
            
            # Wider stop-losses (avoid whipsaws)
            if 'stop_loss_pct' in params:
                params['stop_loss_pct'] = params.get('stop_loss_pct', 0.02) * 1.2
                logger.info(f"Widened stop-loss to {params['stop_loss_pct']:.3f} (rising unemployment)")
        
        # Fed Tightening (Fed Funds > 5%): Reduce leverage, favor defensive
        if fed_funds_rate > 5.0:
            logger.info(f"Fed tightening (Fed Funds={fed_funds_rate:.2f}%) - defensive parameters")
            
            # Reduce position sizes (handled by VIX adjustment in PortfolioManager)
            # Favor defensive sectors (would need sector data)
            
            # More conservative thresholds
            if 'oversold_threshold' in params:
                params['oversold_threshold'] = max(params['oversold_threshold'] - 3, 25)
                logger.info(f"More conservative for Fed tightening: oversold={params['oversold_threshold']}")
            
            # Tighter Bollinger Bands
            if 'bb_std' in params:
                params['bb_std'] = max(params['bb_std'] - 0.2, 1.5)
                logger.info(f"Tighter Bollinger Bands: std={params['bb_std']:.1f} (Fed tightening)")
        
        logger.info(f"Customized parameters: {params}")
        return params
    
    def _apply_parameters_to_condition(self, condition_template: str, params: Dict) -> str:
        """
        Apply customized parameters to a condition template.
        
        Handles both DSL formats:
        - RSI(14) < 25  (parenthesized period)
        - RSI_14 < 25   (underscore period)
        - RSI < 25       (no period)
        """
        import re
        condition = condition_template
        
        # Detect RSI range filters (RSI > X AND RSI < Y) — preserve intentional ranges
        has_rsi_gt = bool(re.search(r'RSI(?:[(_]\d+[)]?)?\s*>', condition))
        has_rsi_lt = bool(re.search(r'RSI(?:[(_]\d+[)]?)?\s*<', condition))
        is_rsi_range_filter = has_rsi_gt and has_rsi_lt
        
        # RSI thresholds — match RSI(14) < 25, RSI_14 < 25, RSI < 25
        if not is_rsi_range_filter:
            if 'oversold_threshold' in params:
                condition = re.sub(
                    r'(RSI(?:\(\d+\)|_\d+)?)\s*<\s*\d+',
                    rf'\1 < {params["oversold_threshold"]}',
                    condition
                )
            
            if 'overbought_threshold' in params:
                condition = re.sub(
                    r'(RSI(?:\(\d+\)|_\d+)?)\s*>\s*\d+',
                    rf'\1 > {params["overbought_threshold"]}',
                    condition
                )
        else:
            # RSI range filter: RSI > X AND RSI < Y
            # Use rsi_entry_min for the lower bound and rsi_entry_max for the upper
            if 'rsi_entry_min' in params:
                condition = re.sub(
                    r'(RSI(?:\(\d+\)|_\d+)?)\s*>\s*\d+',
                    rf'\1 > {params["rsi_entry_min"]}',
                    condition
                )
            if 'rsi_entry_max' in params:
                condition = re.sub(
                    r'(RSI(?:\(\d+\)|_\d+)?)\s*<\s*\d+',
                    rf'\1 < {params["rsi_entry_max"]}',
                    condition
                )
        
        # Stochastic thresholds — match STOCH(14) < 20, STOCH_14 < 20, STOCH < 20
        if 'oversold_threshold' in params and 'STOCH' in condition:
            condition = re.sub(
                r'(STOCH(?:\(\d+\)|_\d+)?)\s*<\s*\d+',
                rf'\1 < {params["oversold_threshold"]}',
                condition
            )
        
        if 'overbought_threshold' in params and 'STOCH' in condition:
            condition = re.sub(
                r'(STOCH(?:\(\d+\)|_\d+)?)\s*>\s*\d+',
                rf'\1 > {params["overbought_threshold"]}',
                condition
            )
        
        # Bollinger Band parameters — match BB_LOWER(20, 2), BB_MIDDLE(20, 2), etc.
        if 'bb_period' in params:
            # Handle BB_LOWER(20, 2) format
            condition = re.sub(
                r'(BB_(?:LOWER|UPPER|MIDDLE))\((\d+)',
                rf'\1({params["bb_period"]}',
                condition
            )
            # Handle Upper_Band_20, Lower_Band_20 format
            condition = re.sub(
                r'(Upper_Band|Lower_Band|Middle_Band)_\d+',
                rf'\1_{params["bb_period"]}',
                condition
            )
        
        if 'bb_std' in params:
            # Handle BB_LOWER(20, 2) → BB_LOWER(20, 2.5) format
            condition = re.sub(
                r'(BB_(?:LOWER|UPPER|MIDDLE)\(\d+,\s*)\d+\.?\d*',
                rf'\g<1>{params["bb_std"]}',
                condition
            )
        
        # Moving average periods
        if 'fast_period' in params:
            # Handle SMA(20), EMA(20) format
            condition = re.sub(r'(SMA|EMA)\(20\)', rf'\1({params["fast_period"]})', condition)
            # Handle SMA_20, EMA_20 format
            condition = re.sub(r'(SMA|EMA)_20\b', rf'\1_{params["fast_period"]}', condition)
        
        if 'slow_period' in params:
            condition = re.sub(r'(SMA|EMA)\(50\)', rf'\1({params["slow_period"]})', condition)
            condition = re.sub(r'(SMA|EMA)_50\b', rf'\1_{params["slow_period"]}', condition)
        
        # RSI period
        if 'rsi_period' in params:
            condition = re.sub(r'RSI\(\d+\)', f'RSI({params["rsi_period"]})', condition)
            condition = re.sub(r'RSI_\d+', f'RSI_{params["rsi_period"]}', condition)
        
        # Stochastic period
        if 'stoch_period' in params:
            condition = re.sub(r'STOCH\(\d+\)', f'STOCH({params["stoch_period"]})', condition)
            condition = re.sub(r'STOCH_\d+', f'STOCH_{params["stoch_period"]}', condition)
        
        # ATR multiplier
        if 'atr_multiplier' in params and 'ATR' in condition:
            condition = re.sub(
                r'(\d+\.?\d*)\s*\*\s*ATR',
                f'{params["atr_multiplier"]} * ATR',
                condition
            )
        
        # Volume multiplier — match VOLUME_MA(20) * 3.0 patterns
        if 'volume_multiplier' in params and 'VOLUME' in condition:
            condition = re.sub(
                r'(VOLUME_MA\(\d+\)\s*\*\s*)\d+\.?\d*',
                rf'\g<1>{params["volume_multiplier"]}',
                condition
            )
        
        return condition
    
    def generate_strategies_from_templates(
        self,
        count: int,
        symbols: List[str],
        market_regime: MarketRegime,
        optimize_parameters: bool = False,
        strategy_engine = None,
        market_statistics: Optional[Dict] = None,
        indicator_distributions: Optional[Dict] = None
    ) -> List[Strategy]:
        """
        Generate multiple strategies from templates with parameter variations.
        
        Args:
            count: Number of strategies to generate
            symbols: Symbols to trade
            market_regime: Current market regime
            optimize_parameters: Whether to optimize parameters using grid search
            strategy_engine: StrategyEngine instance for optimization
            market_statistics: Pre-computed market statistics per symbol (avoids redundant analysis)
            indicator_distributions: Pre-computed indicator distributions per symbol (avoids redundant analysis)
            
        Returns:
            List of Strategy objects
        """
        # Load config once for the entire method (avoids ~15 redundant YAML reads)
        import yaml
        from pathlib import Path
        _config = {}
        config_path = Path("config/autonomous_trading.yaml")
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    _config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Could not load config: {e}")
        logger.info(f"Generating {count} strategies from templates for {market_regime.value} market (optimize: {optimize_parameters})")
        
        # Use pre-computed data if provided, otherwise compute fresh
        if market_statistics is not None and indicator_distributions is not None:
            logger.info(f"Using pre-computed market statistics for {len(market_statistics)} symbols (skipping redundant analysis)")
        else:
            logger.info(f"Analyzing market statistics for symbols: {symbols}")
            market_statistics = market_statistics or {}
            indicator_distributions = indicator_distributions or {}
            
            # Load backtest period from config for market analysis
            import yaml
            from pathlib import Path
            config_path = Path("config/autonomous_trading.yaml")
            analysis_period_days = 730  # Default to 2 years
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    analysis_period_days = config.get('backtest', {}).get('days', 730)
            
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            def _analyze_sym(sym):
                try:
                    stats = self.market_analyzer.analyze_symbol(sym, period_days=analysis_period_days)
                    dists = self.market_analyzer.analyze_indicator_distributions(sym, period_days=analysis_period_days)
                    return sym, stats, dists, None
                except Exception as e:
                    return sym, None, None, str(e)
            
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(_analyze_sym, s): s for s in symbols}
                for future in as_completed(futures):
                    sym, stats, dists, err = future.result()
                    if err:
                        logger.warning(f"Failed to analyze {sym}: {err}")
                    else:
                        market_statistics[sym] = stats
                        indicator_distributions[sym] = dists
        
        # Get market context
        try:
            market_context = self.market_analyzer.get_market_context()
        except Exception as e:
            logger.warning(f"Failed to get market context: {e}")
            market_context = {}
        
        # Load sector classifications for sector-aware symbol selection
        sector_map = {}
        try:
            from src.risk.risk_manager import SYMBOL_SECTOR_MAP
            sector_map = SYMBOL_SECTOR_MAP
            if sector_map:
                logger.info(f"Loaded sector classifications for {len(sector_map)} symbols (from SYMBOL_SECTOR_MAP)")
        except Exception as e:
            logger.debug(f"Could not load sector classifications: {e}")

        # Phase 2: Run cross-sectional fundamental ranking for AE scoring
        try:
            rankings = self.get_fundamental_rankings(symbols, market_statistics)
            if rankings:
                logger.info(f"Cross-sectional ranking complete: {len(rankings)} stocks ranked")
                # Store on strategy engine so the fundamental filter in signal generation
                # can use cross-sectional tercile ranking instead of absolute thresholds
                if strategy_engine is not None:
                    strategy_engine._ranker_results = rankings
        except Exception as e:
            logger.warning(f"Fundamental ranking failed (non-critical): {e}")
        
        # Apply macro-aware template filtering
        templates = self._filter_templates_by_macro_regime(market_regime, market_context)
        
        # Apply user-specified proposal filters (asset classes, intervals, strategy types)
        proposal_filters = getattr(self, '_proposal_filters', {})
        if proposal_filters:
            # Filter symbols by asset class
            filter_asset_classes = proposal_filters.get('asset_classes')
            if filter_asset_classes:
                filtered_symbols = [s for s in symbols if self._get_asset_class(s) in filter_asset_classes]
                logger.info(f"Asset class filter {filter_asset_classes}: {len(symbols)} → {len(filtered_symbols)} symbols")
                symbols = filtered_symbols
            
            # Filter templates by interval (intraday vs daily)
            filter_intervals = proposal_filters.get('intervals')
            if filter_intervals:
                def _template_matches_interval(t):
                    md = t.metadata or {}
                    is_1h = md.get('intraday', False) and not md.get('interval_4h', False)
                    is_4h = md.get('interval_4h', False)
                    is_daily = not is_1h and not is_4h
                    
                    if '1h' in filter_intervals and is_1h:
                        return True
                    if '4h' in filter_intervals and is_4h:
                        return True
                    if '1d' in filter_intervals and is_daily:
                        return True
                    return False
                before = len(templates)
                templates = [t for t in templates if _template_matches_interval(t)]
                logger.info(f"Interval filter {filter_intervals}: {before} → {len(templates)} templates")
            
            # Filter templates by strategy type (dsl vs alpha_edge)
            filter_types = proposal_filters.get('strategy_types')
            if filter_types:
                before = len(templates)
                filtered = []
                for t in templates:
                    is_ae = t.metadata and t.metadata.get('strategy_category') == 'alpha_edge'
                    if 'alpha_edge' in filter_types and is_ae:
                        filtered.append(t)
                    elif 'dsl' in filter_types and not is_ae:
                        filtered.append(t)
                templates = filtered
                logger.info(f"Strategy type filter {filter_types}: {before} → {len(templates)} templates")
        
        # Separate Alpha Edge templates from DSL templates for matching.
        # Alpha Edge uses fundamental signals — they do not belong in the DSL scoring pool.
        # They'll be added via the force-add path (capped at 3-5) after DSL generation.
        dsl_templates = [t for t in templates if not (t.metadata and t.metadata.get('strategy_category') == 'alpha_edge')]
        ae_templates = [t for t in templates if t.metadata and t.metadata.get('strategy_category') == 'alpha_edge']

        # Filter out disabled templates
        dsl_templates = [t for t in dsl_templates if not self._is_template_disabled(t)[0]]
        ae_templates = [t for t in ae_templates if not self._is_template_disabled(t)[0]]

        logger.info(f"Templates: {len(dsl_templates)} DSL + {len(ae_templates)} Alpha Edge (AE handled separately)")
        
        adjusted_count = count  # Exact target — we'll produce exactly this many unique strategies
        
        # Reserve slots for Alpha Edge (force-added separately)
        # When no DSL templates exist (e.g., user filtered to alpha_edge only),
        # give all slots to Alpha Edge.
        #
        # Q2 (2026-05-01): raised AE cap from 5 → 8 when DSL templates exist.
        # With 25 AE templates in the library and only 5 slots per cycle, most
        # templates never got a chance to propose (confirmed: 5 live AE strategies
        # for 25 templates). Raising to 8 gives AE templates ~1.6x more cycles
        # per rotation without overwhelming the DSL pool. WF + conviction still
        # decide what activates.
        if dsl_templates:
            ae_slots = min(8, len(ae_templates))
        else:
            ae_slots = len(ae_templates)  # All slots go to AE when no DSL
        dsl_target = adjusted_count - ae_slots
        logger.info(f"Target: {dsl_target} DSL + {ae_slots} Alpha Edge = {adjusted_count} total unique strategies")
        
        if not dsl_templates and not ae_templates:
            logger.warning(f"No templates found for regime {market_regime.value} after macro filtering")
            return []
        
        if not dsl_templates:
            logger.info(f"No DSL templates for regime {market_regime.value} — skipping DSL phase, proceeding to Alpha Edge")
        
        # === PHASE 1: Score all (template, symbol) pairs ===
        # Request a large pool — we'll draw from it until we have enough unique strategies.
        # The pool is cheap (just scoring), the expensive part is WF which comes later.
        max_pool = len(dsl_templates) * len(symbols)  # Theoretical max
        template_symbol_assignments = self._match_templates_to_symbols(
            templates_for_cycle=dsl_templates,
            symbols=symbols,
            adjusted_count=min(max_pool, dsl_target * 3),  # Large pool to draw from
            market_statistics=market_statistics,
            indicator_distributions=indicator_distributions,
        )
        
        # Build multi-symbol watchlists for each template
        # Top trader approach: each strategy scans its best-fit symbols, not just 1
        watchlist_size = 10  # default
        try:
            import yaml
            from pathlib import Path
            config_path = Path("config/autonomous_trading.yaml")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    wl_config = yaml.safe_load(f)
                    watchlist_size = wl_config.get('autonomous', {}).get('watchlist_size', 10)
        except Exception:
            pass

        # Load existing active AND approved-backtested strategies to avoid proposing
        # same template+symbol combos that are already in the pipeline.
        # Must be built BEFORE _build_watchlists which uses active_symbol_template_pairs.
        active_template_symbols = set()  # template names with active/approved strategies
        active_symbol_template_pairs = set()  # (template_name, symbol) pairs already in pipeline
        try:
            if strategy_engine:
                from src.models.database import get_database
                from src.models.orm import StrategyORM
                from src.models.enums import StrategyStatus
                import json as _json
                
                db = get_database()
                session = db.get_session()
                try:
                    # Include DEMO, LIVE, and BACKTESTED with activation_approved
                    existing = session.query(StrategyORM).filter(
                        StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE, StrategyStatus.BACKTESTED])
                    ).all()
                    for s in existing:
                        md = s.strategy_metadata if isinstance(s.strategy_metadata, dict) else {}
                        # Only include BACKTESTED if activation_approved
                        if s.status == StrategyStatus.BACKTESTED and not md.get('activation_approved'):
                            continue
                        tname = md.get('template_name', s.name)
                        active_template_symbols.add(tname)
                        # Track (template, symbol) pairs including watchlist symbols
                        syms = s.symbols if isinstance(s.symbols, list) else (_json.loads(s.symbols) if isinstance(s.symbols, str) else [])
                        for sym in syms:
                            active_symbol_template_pairs.add((tname, sym))
                finally:
                    session.close()
                
                if active_template_symbols:
                    logger.info(f"Loaded {len(active_template_symbols)} active/approved templates for dedup ({len(active_symbol_template_pairs)} template+symbol pairs)")
        except Exception as e:
            logger.warning(f"Could not load active strategies for proposal dedup: {e}")

        # _match_templates_to_symbols already scored all (template, symbol) pairs internally.
        # We need the all_pairs data to build watchlists. Store it during matching.
        watchlists = self._build_watchlists(
            all_pairs=getattr(self, '_last_scored_pairs', []),
            assignments=template_symbol_assignments,
            watchlist_size=watchlist_size,
            active_symbol_template_pairs=active_symbol_template_pairs,
        )
        logger.info(f"Built watchlists for {len(watchlists)} templates (size: {watchlist_size})")

        # === PHASE 2: Generate unique strategies with parameter variations ===
        # Each template produces one strategy per variation (different params, same watchlist).
        # The watchlist is built from the scored (template, symbol) assignments.
        strategies = []
        seen_templates = set()
        skipped_dupes = 0

        # Group assignments by template to build watchlists
        from collections import OrderedDict
        template_assignments = OrderedDict()
        for template, assigned_symbol in template_symbol_assignments:
            if template.name not in template_assignments:
                template_assignments[template.name] = (template, [])
            template_assignments[template.name][1].append(assigned_symbol)
        
        # Iterate over each unique (template, symbol) pair directly.
        # Previously we grouped by template and generated parameter variations (BB 1.8, 2.0, 2.5)
        # on the same symbol — but the WF cache key is (template_name, primary_symbol), so
        # variations produced identical results and clogged activation with "Duplicate" rejections.
        # Now each slot goes to a different template×symbol combo for maximum diversity.
        seen_template_symbols = set()
        logger.info(f"Generating 1 strategy per unique (template, symbol) pair from {len(template_symbol_assignments)} assignments")
        
        for template, assigned_symbol in template_symbol_assignments:
            if len(strategies) >= dsl_target:
                break
            
            template_name = template.name
            
            # Skip if this (template, symbol) pair already exists in the pipeline
            # Only block the specific template+symbol combo, not the entire template.
            # A template can have strategies on multiple symbols (BCH, BTC, ETH, etc.)
            if (template_name, assigned_symbol) in active_symbol_template_pairs:
                skipped_dupes += 1
                continue
            
            # For fixed_symbols templates (single-symbol like Gold Momentum Long GOLD),
            # also check the actual fixed symbol — not just the assigned_symbol from scoring.
            # This catches the race condition where multiple rapid cycles each see an empty
            # pipeline and all propose the same fixed-symbol strategy before any is committed.
            if template.metadata and 'fixed_symbols' in template.metadata:
                fixed_syms = template.metadata['fixed_symbols']
                if isinstance(fixed_syms, list):
                    if any((template_name, fs) in active_symbol_template_pairs for fs in fixed_syms):
                        skipped_dupes += 1
                        continue
            
            # Skip duplicate (template, symbol) pairs within this cycle
            pair_key = (template_name, assigned_symbol)
            if pair_key in seen_template_symbols:
                skipped_dupes += 1
                continue
            seen_template_symbols.add(pair_key)

            # Skip LME metals (ZINC, ALUMINUM, PLATINUM, NICKEL) on intraday templates.
            # These symbols only have daily data — intraday WF will always crash with
            # "No historical data available", flooding errors.log and wasting proposal slots.
            _is_intraday = bool(template.metadata and template.metadata.get('intraday', False))
            _is_4h = bool(template.metadata and template.metadata.get('interval_4h', False))
            _primary_sym = (template.metadata.get('fixed_symbols', [assigned_symbol]) if template.metadata else [assigned_symbol])
            _primary_sym = _primary_sym[0] if isinstance(_primary_sym, list) else _primary_sym
            if _primary_sym.upper() in _DAILY_ONLY_SYMBOLS and (_is_intraday or _is_4h):
                logger.debug(f"Skipping {template_name} on {_primary_sym} — LME metal has no intraday data")
                skipped_dupes += 1
                continue

            # Build watchlist: primary symbol is the assigned one, rest from template's watchlist
            if template.metadata and 'fixed_symbols' in template.metadata:
                strategy_symbol = template.metadata['fixed_symbols']
            else:
                watchlist = watchlists.get(template_name, [assigned_symbol])
                if assigned_symbol in watchlist:
                    strategy_symbol = [assigned_symbol] + [s for s in watchlist if s != assigned_symbol]
                else:
                    strategy_symbol = [assigned_symbol] + watchlist[:watchlist_size - 1]

            # Strip daily-only LME metals from watchlist of intraday/4h strategies.
            # The watchlist builder filters them for new entries, but stale validated
            # combos cache may still contain ALUMINUM/ZINC/NICKEL for intraday templates.
            if (_is_intraday or _is_4h) and isinstance(strategy_symbol, list):
                strategy_symbol = [s for s in strategy_symbol if s.upper() not in _DAILY_ONLY_SYMBOLS]
                if not strategy_symbol:
                    logger.debug(f"Skipping {template_name} — all symbols are daily-only after LME filter")
                    skipped_dupes += 1
                    continue
            
            # Use market-customized params (no parameter variations —
            # diversity comes from different symbols, not different BB std_dev)
            customized_params = self.customize_template_parameters(
                template=template,
                market_statistics=market_statistics,
                indicator_distributions=indicator_distributions,
                market_context=market_context
            )
            
            # Set signal_interval based on template type:
            # - intraday templates → 1h
            # - 4H templates → 4h
            # - daily templates → 1d (NOT the config default — daily templates
            #   are calibrated for daily bars and should not use 1h with scaling)
            is_intraday = template.metadata and template.metadata.get('intraday', False)
            is_4h = template.metadata and template.metadata.get('interval_4h', False)
            if is_intraday:
                customized_params['signal_interval'] = '1h'
            elif is_4h:
                customized_params['signal_interval'] = '4h'
            else:
                # Daily template: always use daily bars for signal generation.
                # The config default_interval is for the signal LOOP frequency,
                # not the data interval. Daily-calibrated indicators (RSI(14) = 14 days)
                # must run on daily data to produce correct signals.
                customized_params['signal_interval'] = '1d'
            
            # Validate parameter bounds
            validated_params = self._validate_parameter_bounds(
                params=customized_params,
                indicator_distributions=indicator_distributions
            )
            
            # Generate strategy
            strategy = self._generate_strategy_with_params(
                template=template,
                symbols=strategy_symbol,
                params=validated_params,
                variation_number=len(strategies),
                market_statistics=market_statistics,
            )
            
            # Store metadata
            if not hasattr(strategy, 'metadata') or strategy.metadata is None:
                strategy.metadata = {}
            strategy.metadata['macro_regime'] = market_context.get('macro_regime', 'transitional')
            strategy.metadata['vix_at_creation'] = market_context.get('vix', 20.0)
            strategy.metadata['risk_regime'] = market_context.get('risk_regime', 'neutral')
            
            # Estimate signal frequency
            estimated_frequency = self._estimate_signal_frequency(
                params=validated_params,
                template=template,
                indicator_distributions=indicator_distributions
            )
            strategy.metadata['estimated_signal_frequency'] = estimated_frequency
            
            strategies.append(strategy)
        
        if skipped_dupes > 0:
            logger.info(f"DSL generation: {len(strategies)} unique strategies produced, {skipped_dupes} duplicates skipped")
        else:
            logger.info(f"DSL generation: {len(strategies)} unique strategies produced")
        
        if len(strategies) < dsl_target and dsl_templates:
            logger.warning(
                f"Could only produce {len(strategies)}/{dsl_target} unique DSL strategies "
                f"({len(seen_template_symbols)} unique pairs from {len(template_symbol_assignments)} assignments, {skipped_dupes} skipped)"
            )
        
        # === PHASE 3: Add Alpha Edge strategies with multi-symbol watchlists ===
        # Same approach as DSL: each AE template gets ONE strategy with a watchlist
        # of the top 5 best-fit symbols (ranked by the cross-sectional ranker).
        # Signal generation evaluates all watchlist symbols on each cycle.
        alpha_edge_count = 0
        ae_max_per_template = 5  # Top 5 symbols per template watchlist

        alpha_edge_templates_filtered = list(ae_templates)

        # Skip templates that consistently produce bad results
        UNDERPERFORMING_AE_TEMPLATES = {'end-of-month momentum long'}
        alpha_edge_templates_filtered = [
            t for t in alpha_edge_templates_filtered
            if t.name.lower() not in UNDERPERFORMING_AE_TEMPLATES
        ]

        # Q1 (2026-05-01): rotate AE template order across cycles so ALL templates
        # in the library get a shot, not just the first N in definition order.
        #
        # Prior behaviour: templates are evaluated in the order defined in
        # strategy_templates.py. With ae_slots=5-8, templates defined later
        # in the file never reached the loop. Confirmed: 0 Post-Earnings Drift
        # Long, 0 Sector Rotation, 0 52-Week High Momentum, 0 Analyst Revision,
        # 0 Share Buyback Momentum — all valid templates that never proposed.
        #
        # Anchor on hour-of-year: advances once per hour, giving the autonomous
        # scheduler (runs daily 15:15 UTC + weekday 19:00 UTC, plus intraday
        # signal cycles that also reach this code) a stable rotation that
        # spreads fairly across the template list without depending on a
        # persisted counter. Two cycles on the same hour see the same order —
        # that's fine; adjacent cycles rotate.
        try:
            import time as _time_q1
            _rotation_offset = int(_time_q1.time() // 3600) % max(1, len(alpha_edge_templates_filtered))
            if _rotation_offset and alpha_edge_templates_filtered:
                alpha_edge_templates_filtered = (
                    alpha_edge_templates_filtered[_rotation_offset:] +
                    alpha_edge_templates_filtered[:_rotation_offset]
                )
                logger.info(
                    f"AE template rotation: offset={_rotation_offset}, "
                    f"starting with '{alpha_edge_templates_filtered[0].name}' "
                    f"(of {len(alpha_edge_templates_filtered)} templates)"
                )
        except Exception as _rot_err:
            logger.debug(f"AE rotation skipped: {_rot_err}")

        # Check which Alpha Edge templates already have active strategies in DB
        active_ae_template_symbols = set()  # (template_name, symbol) pairs already active
        try:
            from src.models.database import get_database
            from src.models.orm import StrategyORM
            import json as _json_ae
            db = get_database()
            session = db.get_session()
            try:
                active_strategies_db = session.query(StrategyORM).filter(
                    StrategyORM.status.in_(["DEMO", "LIVE", "BACKTESTED"])
                ).all()
                for s in active_strategies_db:
                    meta = s.strategy_metadata if isinstance(s.strategy_metadata, dict) else {}
                    if meta.get('strategy_category') == 'alpha_edge':
                        tname = meta.get('template_name', '')
                        syms = s.symbols if isinstance(s.symbols, list) else []
                        if isinstance(syms, str):
                            try:
                                syms = _json_ae.loads(syms)
                            except Exception:
                                syms = []
                        for sym in syms:
                            active_ae_template_symbols.add((tname.lower(), sym))
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Could not check active Alpha Edge strategies: {e}")

        for ae_template in alpha_edge_templates_filtered:
            if alpha_edge_count >= ae_slots:
                break

            ae_type = ae_template.name.lower()
            ae_type_meta = (ae_template.metadata or {}).get('alpha_edge_type', '')

            # Fixed-symbol templates (sector rotation) — use as-is
            if ae_template.metadata and 'fixed_symbols' in ae_template.metadata:
                strategy_symbols = ae_template.metadata['fixed_symbols']
            else:
                # Build watchlist: score all eligible symbols, take top 5
                candidate_symbols = []
                best_syms = (ae_template.metadata or {}).get('best_symbols', [])

                for sym in symbols:
                    # Skip if this (template, symbol) pair is already active
                    if (ae_type, sym) in active_ae_template_symbols:
                        continue

                    sym_stats = market_statistics.get(sym, {})
                    if not sym_stats:
                        continue

                    asset_class = self._get_asset_class(sym)

                    # Template-specific eligibility filter
                    ae_score = 50.0
                    vol = sym_stats.get('volatility_metrics', {}).get('volatility', 0)

                    if 'earnings' in ae_type or 'revenue' in ae_type or 'analyst' in ae_type:
                        if asset_class != 'stock':
                            continue
                        ae_score += vol * 100
                    elif 'dividend' in ae_type or 'aristocrat' in ae_type:
                        if asset_class != 'stock':
                            continue
                        if sym in best_syms:
                            ae_score += 80
                        else:
                            ae_score += (1 - vol) * 30
                    elif 'insider' in ae_type or 'buyback' in ae_type:
                        if asset_class != 'stock':
                            continue
                        ae_score += vol * 50
                    elif 'sector' in ae_type:
                        if asset_class == 'etf':
                            ae_score += 30
                        elif asset_class in ('crypto', 'forex', 'commodity'):
                            continue
                    elif 'quality' in ae_type or 'value' in ae_type or 'relative' in ae_type:
                        if asset_class != 'stock':
                            continue
                        mr = sym_stats.get('mean_reversion_metrics', {}).get('mean_reversion_score', 0)
                        ae_score += mr * 30
                    elif 'composite' in ae_type or 'multi' in ae_type:
                        if asset_class != 'stock':
                            continue
                        # Use ranker composite score directly if available
                        if self._ranker_results and sym in self._ranker_results:
                            ae_score = self._ranker_results[sym].get('composite_score', 50.0)
                        else:
                            ae_score += vol * 50
                    else:
                        if asset_class in ('crypto', 'forex', 'commodity', 'index'):
                            continue

                    # Boost from ranker if available
                    if self._ranker_results and sym in self._ranker_results:
                        ranker_score = self._ranker_results[sym].get('composite_score', 50.0)
                        ae_score = ae_score * 0.4 + ranker_score * 0.6  # 60% ranker, 40% template-specific

                    candidate_symbols.append((ae_score, sym))

                if not candidate_symbols:
                    logger.warning(f"No eligible symbols for AE template '{ae_template.name}' — skipping")
                    continue

                # SHORT templates need the WORST-ranked symbols (low quality, high accruals)
                # LONG templates need the BEST-ranked symbols (high quality, low accruals)
                is_short_template = (ae_template.metadata or {}).get('direction', 'long') == 'short'
                if is_short_template:
                    # SHORT symbol selection: use template-specific fundamental screens
                    # directly on quarterly data, NOT inverted ranker scores.
                    # The ranker was built for long-side factor investing — inverting it
                    # picks stocks with low momentum but high quality (like TXN, NVDA),
                    # which are terrible short candidates.
                    #
                    # Instead, screen for actual deterioration signals:
                    # - Quality Deterioration: declining ROE, rising D/E
                    # - Accruals Quality: high accruals ratio (earnings manipulation)
                    # - Earnings Miss: negative earnings surprise, declining revenue
                    self._ensure_fundamental_data_provider()
                    provider = self._fundamental_data_provider
                    
                    short_scored = []
                    ae_type_meta = (ae_template.metadata or {}).get('alpha_edge_type', ae_type)
                    
                    for score, sym in candidate_symbols:
                        try:
                            quarters = provider.get_historical_fundamentals(sym, quarters=4)
                            if not quarters or len(quarters) < 2:
                                continue
                            latest = quarters[-1]
                            prev = quarters[-2] if len(quarters) >= 2 else {}
                            
                            short_score = 0.0
                            
                            if 'deterioration' in ae_type_meta or 'quality' in ae_type_meta:
                                # Want: low ROE, high D/E, declining margins
                                roe = latest.get('roe')
                                de = latest.get('debt_to_equity')
                                gm = latest.get('gross_margin')
                                prev_gm = prev.get('gross_margin')
                                if roe is not None and roe < 0.10:
                                    short_score += 30  # Low ROE
                                if roe is not None and roe < 0.05:
                                    short_score += 20  # Very low ROE
                                if de is not None and de > 1.0:
                                    short_score += 20  # High leverage
                                if de is not None and de > 2.0:
                                    short_score += 15  # Very high leverage
                                if gm is not None and prev_gm is not None and gm < prev_gm:
                                    short_score += 15  # Declining margins
                                    
                            elif 'accruals' in ae_type_meta:
                                # Want: high accruals ratio (earnings manipulation signal)
                                accruals = latest.get('accruals_ratio')
                                ocf = latest.get('operating_cash_flow')
                                ni = latest.get('net_income')
                                if accruals is not None and accruals > 0.03:
                                    short_score += 30
                                if accruals is not None and accruals > 0.06:
                                    short_score += 20
                                if ocf is not None and ni is not None and ocf < ni * 0.5:
                                    short_score += 25  # Cash flow much lower than earnings
                                    
                            elif 'earnings_miss' in ae_type_meta or 'miss' in ae_type_meta:
                                # Want: negative surprise, declining revenue
                                surprise = latest.get('earnings_surprise')
                                rev_growth = latest.get('revenue_growth')
                                if surprise is not None and surprise < 0:
                                    short_score += 30
                                if surprise is not None and surprise < -0.05:
                                    short_score += 20
                                if rev_growth is not None and rev_growth < 0:
                                    short_score += 25  # Revenue declining
                                if rev_growth is not None and rev_growth < -0.05:
                                    short_score += 15  # Revenue declining fast
                            else:
                                # Generic short: use inverted composite as fallback
                                if self._ranker_results and sym in self._ranker_results:
                                    short_score = 100.0 - self._ranker_results[sym].get('composite_score', 50.0)
                                    
                            if short_score > 0:
                                short_scored.append((short_score, sym))
                        except Exception:
                            continue
                    
                    if short_scored:
                        short_scored.sort(reverse=True)
                        strategy_symbols = [sym for _, sym in short_scored[:ae_max_per_template]]
                    else:
                        # Fallback: if no symbols pass the screen, use inverted ranker
                        candidate_symbols.sort(reverse=True)
                        strategy_symbols = [sym for _, sym in candidate_symbols[:ae_max_per_template]]
                    
                    logger.info(
                        f"AE watchlist for '{ae_template.name}' (SHORT — screened): {strategy_symbols} "
                        f"(from {len(short_scored)} screened / {len(candidate_symbols)} candidates)"
                    )
                else:
                    candidate_symbols.sort(reverse=True)
                    strategy_symbols = [sym for _, sym in candidate_symbols[:ae_max_per_template]]
                    logger.info(
                        f"AE watchlist for '{ae_template.name}': {strategy_symbols} "
                        f"(top {len(strategy_symbols)} of {len(candidate_symbols)} candidates)"
                    )

            # Create ONE strategy with the multi-symbol watchlist
            try:
                variation_params = self._create_parameter_variation(ae_template, len(strategies))
                customized_params = self.customize_template_parameters(
                    template=ae_template,
                    market_statistics=market_statistics,
                    indicator_distributions=indicator_distributions,
                    market_context=market_context
                )
                customized_params.update(variation_params)
                validated_params = self._validate_parameter_bounds(
                    params=customized_params,
                    indicator_distributions=indicator_distributions
                )

                strategy = self._generate_strategy_with_params(
                    template=ae_template,
                    symbols=strategy_symbols,
                    params=validated_params,
                    variation_number=len(strategies),
                    market_statistics=market_statistics,
                )

                if not hasattr(strategy, 'metadata') or strategy.metadata is None:
                    strategy.metadata = {}
                strategy.metadata['macro_regime'] = market_context.get('macro_regime', 'transitional')
                strategy.metadata['vix_at_creation'] = market_context.get('vix', 20.0)
                strategy.metadata['risk_regime'] = market_context.get('risk_regime', 'neutral')
                strategy.metadata['strategy_category'] = 'alpha_edge'
                strategy.metadata['force_added'] = True
                if 'short' in ae_template.name.lower() or (ae_template.metadata and ae_template.metadata.get('direction') == 'short'):
                    strategy.metadata['direction'] = 'short'
                else:
                    strategy.metadata['direction'] = 'long'

                strategies.append(strategy)
                alpha_edge_count += 1
                logger.info(f"Added Alpha Edge strategy: {strategy.name} with {len(strategy_symbols)} symbols ({alpha_edge_count}/{ae_slots})")
            except Exception as e:
                logger.warning(f"Failed to add Alpha Edge template '{ae_template.name}': {e}")
        
        logger.info(
            f"Final: {len(strategies)} unique strategies "
            f"({len(strategies) - alpha_edge_count} DSL + {alpha_edge_count} Alpha Edge, "
            f"target was {adjusted_count})"
        )
        
        return strategies
    
    def _create_parameter_variation(self, template: StrategyTemplate, variation_number: int) -> Dict:
        """
        Create parameter variations for diversity.
        
        Varies BOTH thresholds AND indicator periods to produce genuinely different
        conditions. RSI(14) < 35 and RSI(10) < 35 are different strategies that
        look at different timeframes.
        
        Args:
            template: Strategy template
            variation_number: Variation index
            
        Returns:
            Dictionary of varied parameters
        """
        variations = {}
        conditions_text = " ".join(template.entry_conditions + template.exit_conditions).upper()
        
        # === INDICATOR PERIOD VARIATIONS (most impactful for uniqueness) ===
        # Always vary periods if the indicator appears in conditions, regardless
        # of whether the period is in default_parameters.
        
        if 'RSI' in conditions_text:
            rsi_period_variations = [7, 10, 14, 21]  # Standard trader lookbacks
            variations['rsi_period'] = rsi_period_variations[variation_number % len(rsi_period_variations)]
        
        if 'STOCH' in conditions_text:
            stoch_period_variations = [9, 14, 21]  # Standard stochastic periods
            variations['stoch_period'] = stoch_period_variations[variation_number % len(stoch_period_variations)]
        
        if 'BB_' in conditions_text or 'BOLLINGER' in conditions_text:
            bb_variations = [(15, 1.5), (20, 2.0), (20, 2.5), (25, 2.0), (30, 2.0)]
            period, std = bb_variations[variation_number % len(bb_variations)]
            variations['bb_period'] = period
            variations['bb_std'] = std
        
        if ('SMA' in conditions_text or 'EMA' in conditions_text) and 'CROSSES' not in conditions_text:
            # For non-crossover MA conditions (e.g., CLOSE > SMA(20))
            # Don't vary crossover MAs here — they have fast/slow periods below
            pass
        
        # === THRESHOLD VARIATIONS ===
        if 'oversold_threshold' in template.default_parameters:
            rsi_variations = [25, 30, 35, 40]  # Realistic oversold levels
            variations['oversold_threshold'] = rsi_variations[variation_number % len(rsi_variations)]
        
        if 'overbought_threshold' in template.default_parameters:
            rsi_variations = [60, 65, 70, 75]  # Realistic overbought levels
            variations['overbought_threshold'] = rsi_variations[variation_number % len(rsi_variations)]
        
        # === MA PERIOD VARIATIONS ===
        if 'fast_period' in template.default_parameters and 'slow_period' in template.default_parameters:
            ma_variations = [(5, 20), (8, 25), (10, 30), (15, 40), (20, 50), (25, 60), (30, 90)]
            fast, slow = ma_variations[variation_number % len(ma_variations)]
            variations['fast_period'] = fast
            variations['slow_period'] = slow
        
        # === MIDRANGE/MOMENTUM VARIATIONS ===
        if 'rsi_entry_min' in template.default_parameters:
            rsi_min_variations = [38, 42, 45, 48, 50, 52]
            variations['rsi_entry_min'] = rsi_min_variations[variation_number % len(rsi_min_variations)]
        
        if 'rsi_entry_max' in template.default_parameters:
            rsi_max_variations = [58, 60, 62, 65, 68, 72]
            variations['rsi_entry_max'] = rsi_max_variations[variation_number % len(rsi_max_variations)]
        
        if 'stoch_entry_min' in template.default_parameters:
            stoch_min_variations = [20, 25, 30, 35, 40]
            variations['stoch_entry_min'] = stoch_min_variations[variation_number % len(stoch_min_variations)]
        
        if 'stoch_entry_max' in template.default_parameters:
            stoch_max_variations = [60, 65, 70, 75, 80]
            variations['stoch_entry_max'] = stoch_max_variations[variation_number % len(stoch_max_variations)]
        
        if 'mid_period' in template.default_parameters:
            mid_variations = [13, 15, 18, 20, 25]
            variations['mid_period'] = mid_variations[variation_number % len(mid_variations)]
        
        # === ATR MULTIPLIER VARIATIONS ===
        if 'atr_multiplier' in template.default_parameters:
            atr_variations = [0.8, 1.0, 1.2, 1.5, 2.0]
            variations['atr_multiplier'] = atr_variations[variation_number % len(atr_variations)]
        
        # === INTERVAL DIVERSITY ===
        # Same template on same symbol but different signal intervals (1d, 4h, 1h)
        # are genuinely different strategies. Daily RSI(14) < 30 catches multi-day
        # pullbacks; hourly RSI(14) < 30 catches intraday dips.
        # WF always uses daily bars (Yahoo 1h only goes back 30 days), but live
        # signal generation uses the strategy's interval with indicator scaling.
        # Intraday-native templates (marked with metadata.intraday) always use 1h.
        is_intraday_template = template.metadata and template.metadata.get('intraday', False)
        is_4h_template = template.metadata and template.metadata.get('interval_4h', False)
        if is_intraday_template:
            variations['signal_interval'] = '1h'
        elif is_4h_template:
            variations['signal_interval'] = '4h'
        else:
            # Daily templates must use daily bars — no random interval variation.
            # Running a daily-calibrated RSI(14) on 1h data produces a completely
            # different signal (14-hour RSI vs 14-day RSI).
            variations['signal_interval'] = '1d'
        
        # === RISK VARIATIONS (don't affect WF conditions but affect live position management) ===
        # Vary SL/TP as coherent pairs that maintain a minimum 1.5:1 R:R ratio.
        # Random independent SL/TP variation can produce nonsensical combinations
        # like SL=1% TP=2% (gets stopped on noise) or SL=3% TP=2% (negative R:R).
        if 'stop_loss_pct' in template.default_parameters and 'take_profit_pct' in template.default_parameters:
            # Coherent risk profiles: (SL, TP) pairs with sensible R:R ratios
            risk_profiles = [
                (0.015, 0.03),   # Tight, 2:1 R:R — for low-vol instruments
                (0.02, 0.04),    # Standard, 2:1 R:R
                (0.025, 0.05),   # Medium, 2:1 R:R
                (0.03, 0.06),    # Wide, 2:1 R:R — for high-vol instruments
                (0.04, 0.08),    # Very wide, 2:1 R:R — for crypto/commodities
            ]
            sl, tp = risk_profiles[variation_number % len(risk_profiles)]
            variations['stop_loss_pct'] = sl
            variations['take_profit_pct'] = tp
        elif 'stop_loss_pct' in template.default_parameters:
            sl_variations = [0.015, 0.02, 0.025, 0.03, 0.04]
            variations['stop_loss_pct'] = sl_variations[variation_number % len(sl_variations)]
        elif 'take_profit_pct' in template.default_parameters:
            tp_variations = [0.03, 0.04, 0.05, 0.06, 0.08]
            variations['take_profit_pct'] = tp_variations[variation_number % len(tp_variations)]
        
        return variations
    
    def _validate_parameter_bounds(self, params: Dict, indicator_distributions: Dict) -> Dict:
        """
        Validate and adjust parameter bounds to ensure reasonable signal frequency.
        
        Args:
            params: Parameter dictionary to validate
            indicator_distributions: Indicator distribution data for validation
            
        Returns:
            Adjusted parameters that should generate reasonable signals
        """
        adjusted_params = params.copy()
        
        # Validate RSI thresholds - RELAXED for ranging markets
        if 'oversold_threshold' in params and 'overbought_threshold' in params:
            oversold = params['oversold_threshold']
            overbought = params['overbought_threshold']
            
            # Allow wider range for ranging markets (20-50 instead of 30-40)
            # RSI < 35 occurs ~10-15% of time (more signals)
            # RSI < 25 occurs ~5% of time (moderate signals)
            if oversold < 20:
                logger.warning(f"RSI oversold threshold {oversold} is too tight (< 20), adjusting to 20")
                adjusted_params['oversold_threshold'] = 20
            elif oversold > 50:  # Changed from 40 to 50 to allow more variation
                logger.warning(f"RSI oversold threshold {oversold} is too loose (> 50), adjusting to 50")
                adjusted_params['oversold_threshold'] = 50
            
            if overbought > 80:
                logger.warning(f"RSI overbought threshold {overbought} is too tight (> 80), adjusting to 80")
                adjusted_params['overbought_threshold'] = 80
            elif overbought < 50:  # Changed from 60 to 50 to allow more variation
                logger.warning(f"RSI overbought threshold {overbought} is too loose (< 50), adjusting to 50")
                adjusted_params['overbought_threshold'] = 50
            
            # Ensure reasonable spread between entry and exit
            spread = overbought - oversold
            if spread < 20:  # Changed from 25 to 20 to allow tighter spreads
                logger.warning(f"RSI threshold spread {spread} is too narrow, adjusting")
                # Widen the spread to at least 20 points
                mid = (oversold + overbought) / 2
                adjusted_params['oversold_threshold'] = max(20, int(mid - 10))
                adjusted_params['overbought_threshold'] = min(80, int(mid + 10))
        
        # Validate Stochastic thresholds (similar to RSI but allow wider range)
        if 'oversold_threshold' in params and 'STOCH' in str(params):
            oversold = params['oversold_threshold']
            if oversold < 10:
                logger.warning(f"Stochastic oversold threshold {oversold} is too tight (< 10), adjusting to 10")
                adjusted_params['oversold_threshold'] = 10
            elif oversold > 30:
                logger.warning(f"Stochastic oversold threshold {oversold} is too loose (> 30), adjusting to 30")
                adjusted_params['oversold_threshold'] = 30
        
        if 'overbought_threshold' in params and 'STOCH' in str(params):
            overbought = params['overbought_threshold']
            if overbought > 90:
                logger.warning(f"Stochastic overbought threshold {overbought} is too tight (> 90), adjusting to 90")
                adjusted_params['overbought_threshold'] = 90
            elif overbought < 70:
                logger.warning(f"Stochastic overbought threshold {overbought} is too loose (< 70), adjusting to 70")
                adjusted_params['overbought_threshold'] = 70
        
        # Validate Bollinger Band parameters - RELAXED for more signals
        if 'bb_std' in params:
            bb_std = params['bb_std']
            # BB std between 1.0 and 3.0 for reasonable signals (was 1.5-3.0)
            if bb_std < 1.0:
                logger.warning(f"Bollinger Band std {bb_std} is too tight (< 1.0), adjusting to 1.0")
                adjusted_params['bb_std'] = 1.0
            elif bb_std > 3.0:
                logger.warning(f"Bollinger Band std {bb_std} is too wide (> 3.0), adjusting to 3.0")
                adjusted_params['bb_std'] = 3.0
        
        # Validate ATR multiplier - RELAXED for ranging markets
        if 'atr_multiplier' in params:
            atr_mult = params['atr_multiplier']
            # Allow 0.5 to 2.5 (was implicitly 2.0 fixed)
            if atr_mult < 0.5:
                logger.warning(f"ATR multiplier {atr_mult} is too small (< 0.5), adjusting to 0.5")
                adjusted_params['atr_multiplier'] = 0.5
            elif atr_mult > 2.5:
                logger.warning(f"ATR multiplier {atr_mult} is too large (> 2.5), adjusting to 2.5")
                adjusted_params['atr_multiplier'] = 2.5
        
        # Validate moving average periods
        if 'fast_period' in params and 'slow_period' in params:
            fast = params['fast_period']
            slow = params['slow_period']
            
            # Ensure reasonable spread
            if slow - fast < 10:
                logger.warning(f"MA period spread {slow - fast} is too narrow, adjusting")
                adjusted_params['slow_period'] = fast + 20
            
            # Ensure not too slow (would generate very few signals)
            if slow > 100:
                logger.warning(f"Slow MA period {slow} is too long (> 100), adjusting to 100")
                adjusted_params['slow_period'] = 100
        
        return adjusted_params
    
    def _score_symbol_for_template(
        self,
        template: StrategyTemplate,
        symbol: str,
        market_statistics: Dict,
        indicator_distributions: Dict,
    ) -> float:
        """
        Score how close a symbol's current indicators are to firing a template's
        entry conditions.  Higher score = more likely to generate a signal today.

        The scoring is heuristic — it inspects the template's ``entry_conditions``
        strings for known indicator patterns (RSI, STOCH, BB, SMA/EMA, MACD,
        Support/Resistance) and compares the symbol's *current* values against
        the thresholds embedded in those conditions.

        Returns a float in [0, 100].  0 means "no data / impossible to score".
        """
        # Blacklist check: if this template+symbol combo consistently produces
        # 0 trades in walk-forward, skip it temporarily. Blacklist entries expire
        # after 7 days so combos get retried when market conditions change.
        bl_key = (template.name, symbol)
        if bl_key in self._zero_trade_blacklist and self._zero_trade_blacklist[bl_key] >= self._zero_trade_blacklist_threshold:
            # Check if the blacklist entry has expired
            bl_timestamp = self._zero_trade_blacklist_timestamps.get(bl_key, '')
            if bl_timestamp:
                try:
                    from datetime import datetime as _dt_bl
                    bl_date = _dt_bl.fromisoformat(bl_timestamp)
                    days_since = (_dt_bl.now() - bl_date).days
                    if days_since >= 7:
                        # Expired — remove from blacklist and allow retry
                        del self._zero_trade_blacklist[bl_key]
                        if bl_key in self._zero_trade_blacklist_timestamps:
                            del self._zero_trade_blacklist_timestamps[bl_key]
                        self._save_blacklist_to_disk()
                        # Don't return 0 — let it be scored normally
                    else:
                        return 0.0
                except (ValueError, TypeError):
                    return 0.0
            else:
                return 0.0

        # Rejection blacklist check: if this template+symbol combo has been
        # rejected too many times at activation, skip it.
        if self.is_rejection_blacklisted(template.name, symbol):
            return 0.0

        # HARD BLOCK: Crypto-optimized templates MUST only run on crypto symbols.
        # These templates have crypto-specific thresholds (RSI < 40 instead of < 25,
        # wider stops, weekend assumptions, etc.) — running them on stocks is nonsensical.
        # This check MUST run before the WF cache check, because a stale cache entry
        # from before this flag was added would otherwise bypass the block.
        if template.metadata and template.metadata.get('crypto_optimized'):
            asset_class = self._get_asset_class(symbol)
            if asset_class != 'crypto':
                return 0.0

        # HARD BLOCK: SHORT templates on crypto — eToro doesn't allow shorting.
        # Commodities ARE shortable on eToro (they're CFDs), so only block crypto.
        # These combos always produce 0 trades and waste WF compute. Block at scoring
        # time so they never consume proposal slots.
        NO_SHORT_ASSET_CLASSES = {"crypto"}
        template_direction = (template.metadata or {}).get('direction', 'long').lower()
        if template_direction == 'short' and self._get_asset_class(symbol) in NO_SHORT_ASSET_CLASSES:
            return 0.0

        # HARD BLOCK: Templates requiring volume data cannot run on symbols without it.
        # Forex has no volume from FMP, some indices/commodities have unreliable volume.
        # Must also run before WF cache to prevent stale cache bypass.
        conditions_text_upper = " ".join(template.entry_conditions).upper()
        template_needs_volume = 'VOLUME' in conditions_text_upper
        if template_needs_volume:
            sym_stats_pre = market_statistics.get(symbol, {})
            vol_profile_pre = sym_stats_pre.get('volume_profile', {})
            if not vol_profile_pre.get('has_volume_data', False):
                return 0.0

        # WF cache check: if we already walk-forwarded this combo recently and it FAILED,
        # don't propose it again — the result won't change until the data does.
        # Combos that PASSED WF are allowed to be re-proposed (using cached results)
        # so they get another shot at activation.
        import time as _score_time
        wf_cached = self._wf_results_cache.get(bl_key)
        if wf_cached is not None:
            cached_result, cached_at = wf_cached
            if _score_time.time() - cached_at < self._wf_cache_ttl:
                # Unpack cached result: (train_sharpe, test_sharpe, has_enough_trades, is_overfitted, ...)
                test_sharpe = cached_result[1]
                has_enough_trades = cached_result[2]
                is_overfitted = cached_result[3]
                # Only block if WF FAILED (negative test Sharpe, overfitted, or 0 trades)
                if test_sharpe < 0.15 or is_overfitted or not has_enough_trades:
                    return 0.0
                # WF passed — allow re-proposal (cached result will be used, no re-backtest)

        score = 0.0
        checks = 0

        sym_stats = market_statistics.get(symbol, {})
        sym_dist = indicator_distributions.get(symbol, {})
        price_action = sym_stats.get('price_action', {})
        current_price = price_action.get('current_price', 0.0)
        trend = sym_stats.get('trend_metrics', {})
        vol = sym_stats.get('volatility_metrics', {})

        conditions_text = " ".join(template.entry_conditions).upper()

        # Alpha Edge templates use fundamental conditions (not DSL indicators)
        # Give them a high base score so they compete with DSL templates
        if template.metadata and template.metadata.get('strategy_category') == 'alpha_edge':
            # Phase 2: Use cross-sectional ranking if available
            if self._ranker_results and symbol in self._ranker_results:
                ranking = self._ranker_results[symbol]
                composite = ranking.get("composite_score", 50.0)
                # Map composite score (0-100) to our scoring range (40-100)
                # Top-ranked stocks get highest scores, bottom-ranked get lowest
                alpha_score = 40.0 + (composite / 100.0) * 60.0

                # Template-specific adjustments on top of composite score
                raw = ranking.get("raw_metrics", {})
                template_type_name = template.name.lower()

                # Multi-Factor Composite: pure composite score, no adjustments
                if template.metadata.get("is_composite"):
                    return min(100.0, max(0.0, alpha_score))

                # Quality templates: boost quality rank weight
                if 'quality' in template_type_name:
                    alpha_score += (ranking.get("quality_rank", 50) - 50) * 0.3

                # Value templates: boost value rank weight
                if 'value' in template_type_name or 'relative' in template_type_name:
                    alpha_score += (ranking.get("value_rank", 50) - 50) * 0.3

                # Earnings/growth templates: boost growth rank weight
                if 'earnings' in template_type_name or 'revenue' in template_type_name:
                    alpha_score += (ranking.get("growth_rank", 50) - 50) * 0.3

                # F-Score gate: penalize low-quality stocks for long templates
                f_score = raw.get("piotroski_f_score")
                if f_score is not None and template_direction != 'short':
                    if f_score <= 3:
                        alpha_score -= 20  # Weak fundamentals
                    elif f_score >= 7:
                        alpha_score += 10  # Strong fundamentals

                # Accruals gate: penalize high-accruals stocks
                accruals = raw.get("accruals_ratio")
                if accruals is not None:
                    if accruals > 0.10:
                        alpha_score -= 15  # Earnings not backed by cash
                    elif accruals < -0.05:
                        alpha_score += 10  # Cash-rich earnings

                return min(100.0, max(0.0, alpha_score))

            # Fallback: original scoring when ranker hasn't run yet
            # Score based on template type and symbol suitability
            alpha_score = 70.0  # High base score
            
            template_type = template.metadata.get('strategy_type', template.strategy_type.value if hasattr(template.strategy_type, 'value') else '')
            
            # Earnings Momentum: prefer stocks with high volatility (more earnings impact)
            if 'earnings' in template.name.lower() or template.metadata.get('requires_earnings_data'):
                asset_class = self._get_asset_class(symbol)
                if asset_class == 'stock':
                    alpha_score += 15  # Stocks are ideal for earnings momentum
                    # Bonus for higher volatility stocks (more post-earnings drift)
                    volatility = vol.get('volatility', 0)
                    if volatility > 0.02:
                        alpha_score += 5
                    # Fundamental scoring: check earnings recency
                    try:
                        quarters = self._get_cached_quarterly_data(symbol)
                        if quarters:
                            # Check if earnings reported within last 45 days
                            from datetime import datetime as _dt
                            latest_date_str = quarters[0].get('date', '') if quarters else ''
                            if latest_date_str:
                                try:
                                    latest_date = _dt.strptime(latest_date_str[:10], '%Y-%m-%d')
                                    days_since = (_dt.now() - latest_date).days
                                    if days_since <= 45:
                                        alpha_score += 10  # Recent earnings
                                except (ValueError, TypeError):
                                    pass
                        else:
                            alpha_score -= 15  # No earnings data from FMP
                    except Exception:
                        pass
                elif asset_class in ('etf', 'index'):
                    alpha_score -= 20  # ETFs/indices do not have individual earnings
                else:
                    alpha_score -= 30  # Forex/crypto/commodities do not have earnings
            
            # Sector Rotation: only score sector ETFs
            elif 'sector' in template.name.lower() or template.metadata.get('uses_sector_etfs'):
                fixed_symbols = template.metadata.get('fixed_symbols', [])
                if symbol in fixed_symbols:
                    alpha_score += 15  # This is a target sector ETF
                else:
                    alpha_score -= 40  # Not a sector ETF, poor match
            
            # Quality Mean Reversion: prefer large-cap stocks with mean reversion characteristics
            elif 'quality' in template.name.lower() or template.metadata.get('requires_quality_screening'):
                asset_class = self._get_asset_class(symbol)
                if asset_class == 'stock':
                    alpha_score += 10
                    # Bonus for stocks showing mean reversion characteristics
                    mr_score = sym_stats.get('mean_reversion_metrics', {}).get('mean_reversion_score', 0)
                    if mr_score > 0.1:
                        alpha_score += 10
                    # Bonus for oversold RSI (technical component of quality mean reversion)
                    rsi_data = sym_dist.get('RSI', {})
                    if rsi_data.get('current_value') and rsi_data['current_value'] < 40:
                        alpha_score += 5
                    # Fundamental scoring: verify ROE data availability
                    try:
                        quarters = self._get_cached_quarterly_data(symbol)
                        if quarters:
                            roe_values = [q.get('roe') for q in quarters if q.get('roe') is not None]
                            if roe_values:
                                alpha_score += 5  # ROE data available
                            else:
                                alpha_score -= 15  # No quality metrics
                        else:
                            alpha_score -= 15  # No fundamental data
                    except Exception:
                        pass
                elif asset_class in ('etf', 'index'):
                    alpha_score -= 10  # ETFs can work but less ideal
                else:
                    alpha_score -= 30  # Not suitable
            
            # Dividend Aristocrat: prefer high-yield stable stocks
            elif 'dividend' in template.name.lower() or 'aristocrat' in template.name.lower():
                asset_class = self._get_asset_class(symbol)
                best_symbols = template.metadata.get('best_symbols', [])
                if symbol in best_symbols:
                    alpha_score += 20  # Ideal dividend aristocrat candidate
                elif asset_class == 'stock':
                    alpha_score += 10  # Stocks can be dividend payers
                elif asset_class in ('etf',):
                    alpha_score -= 5  # Some ETFs pay dividends
                else:
                    alpha_score -= 30  # Forex/crypto/commodities do not pay dividends
                # Fundamental scoring: verify dividend yield and stability
                if asset_class in ('stock', 'etf'):
                    try:
                        quarters = self._get_cached_quarterly_data(symbol)
                        if quarters:
                            div_yields = [q.get('dividend_yield') for q in quarters if q.get('dividend_yield') is not None]
                            if div_yields:
                                latest_yield = div_yields[0] if div_yields else 0
                                if latest_yield < 0.015:
                                    alpha_score -= 25  # Yield below 1.5%
                                # Check dividend stability over last 4 periods
                                if len(div_yields) >= 4:
                                    recent_4 = div_yields[:4]
                                    # Stable = no period with zero or drastically lower yield
                                    non_zero = [y for y in recent_4 if y > 0]
                                    if len(non_zero) >= 3:
                                        alpha_score += 10  # Stable dividend history
                                    else:
                                        alpha_score -= 10  # Unstable dividends
                            else:
                                alpha_score -= 15  # No dividend data available
                        else:
                            alpha_score -= 10  # No fundamental data
                    except Exception:
                        pass
            
            # Insider Buying: works for all stocks
            elif 'insider' in template.name.lower():
                asset_class = self._get_asset_class(symbol)
                if asset_class == 'stock':
                    alpha_score += 15  # Insider data available for stocks
                    # Fundamental scoring: check recent insider activity
                    try:
                        insider_net = self._get_cached_insider_net(symbol)
                        if insider_net and insider_net.get('buy_count', 0) > 0:
                            alpha_score += 15  # Recent insider buying activity
                        elif insider_net is not None and insider_net.get('buy_count', 0) == 0:
                            alpha_score -= 10  # No insider activity
                    except Exception:
                        pass
                elif asset_class in ('etf', 'index'):
                    alpha_score -= 20  # ETFs do not have insider filings
                else:
                    alpha_score -= 30  # Not applicable
            
            # Revenue Acceleration: prefer growth stocks
            elif 'revenue' in template.name.lower() and 'acceleration' in template.name.lower():
                asset_class = self._get_asset_class(symbol)
                if asset_class == 'stock':
                    alpha_score += 15
                    # Bonus for higher volatility (growth stocks tend to be more volatile)
                    volatility = vol.get('volatility', 0)
                    if volatility > 0.02:
                        alpha_score += 5
                    # Fundamental scoring: check quarterly revenue consistency
                    try:
                        quarters = self._get_cached_quarterly_data(symbol)
                        if quarters and len(quarters) >= 4:
                            revenues = [q.get('revenue') for q in quarters if q.get('revenue') is not None and q.get('revenue') > 0]
                            if revenues and len(revenues) >= 4:
                                import statistics
                                mean_rev = statistics.mean(revenues)
                                if mean_rev > 0:
                                    cv = statistics.stdev(revenues) / mean_rev
                                    if cv > 0.5:
                                        alpha_score -= 20  # Inconsistent revenue
                                # Check for 3+ consecutive quarters of positive growth
                                consecutive_growth = 0
                                max_consecutive = 0
                                for i in range(1, len(revenues)):
                                    if revenues[i] > revenues[i - 1]:
                                        consecutive_growth += 1
                                        max_consecutive = max(max_consecutive, consecutive_growth)
                                    else:
                                        consecutive_growth = 0
                                if max_consecutive >= 3:
                                    alpha_score += 15  # Strong growth streak
                    except Exception:
                        pass  # Scoring is best-effort
                elif asset_class in ('etf', 'index'):
                    alpha_score -= 20  # ETFs do not report quarterly revenue
                else:
                    alpha_score -= 30
            
            # Relative Value: works for stocks and sector ETFs
            elif 'relative' in template.name.lower() and 'value' in template.name.lower():
                asset_class = self._get_asset_class(symbol)
                if asset_class == 'stock':
                    alpha_score += 15  # Stocks have P/E, P/S, EV/EBITDA
                elif asset_class == 'etf':
                    alpha_score += 5  # Sector ETFs can be compared
                else:
                    alpha_score -= 30  # Not applicable
            
            # End-of-Month Momentum: best for broad market ETFs and large-cap stocks
            elif 'end' in template.name.lower() and 'month' in template.name.lower():
                asset_class = self._get_asset_class(symbol)
                best_symbols = template.metadata.get('best_symbols', [])
                if symbol in best_symbols:
                    alpha_score += 20  # Ideal: broad market ETFs (SPY, QQQ, IWM, DIA)
                elif asset_class == 'etf':
                    alpha_score += 10  # Other ETFs benefit from rebalancing flows
                elif asset_class == 'stock':
                    alpha_score += 5  # Large-cap stocks also see month-end flows
                elif asset_class == 'index':
                    alpha_score += 5  # Indices track the same flows
                else:
                    alpha_score -= 20  # Forex/crypto/commodities less affected
            
            # Pairs Trading: only score symbols that are in the defined pairs
            elif 'pairs' in template.name.lower() and 'trading' in template.name.lower():
                pair_symbols_list = template.metadata.get('pair_symbols', [])
                pair_universe = {s for pair in pair_symbols_list for s in pair}
                if symbol in pair_universe:
                    alpha_score += 20  # Symbol is in a defined pair
                else:
                    alpha_score -= 50  # Not in any pair — poor match

            # Analyst Revision Momentum: prefer stocks with analyst coverage
            elif template.metadata.get('alpha_edge_type') == 'analyst_revision_momentum':
                asset_class = self._get_asset_class(symbol)
                if asset_class == 'stock':
                    quarters = self._get_cached_quarterly_data(symbol)
                    if quarters:
                        estimates = [q.get('estimated_eps') for q in quarters if q.get('estimated_eps') is not None]
                        if len(estimates) >= 3:
                            up_revisions = sum(1 for i in range(1, len(estimates)) if estimates[i] > estimates[i-1])
                            if up_revisions >= 2:
                                alpha_score += 15
                            alpha_score += 5  # Has estimate data
                        elif len(estimates) == 0:
                            alpha_score -= 15  # No analyst coverage
                elif asset_class in ('etf', 'index'):
                    alpha_score -= 20
                else:
                    alpha_score -= 30

            # Share Buyback: prefer stocks with active buybacks
            elif template.metadata.get('alpha_edge_type') == 'share_buyback':
                asset_class = self._get_asset_class(symbol)
                if asset_class == 'stock':
                    try:
                        self._ensure_fundamental_data_provider()
                        fd = self._fundamental_data_provider.get_fundamental_data(symbol)
                        if fd and fd.shares_change_percent is not None:
                            if fd.shares_change_percent < -0.01:
                                alpha_score += 15  # Active buyback
                            elif fd.shares_change_percent > 0.02:
                                alpha_score -= 20  # Diluting
                        if fd and fd.eps is not None and fd.eps > 0:
                            alpha_score += 5  # Profitable
                    except Exception:
                        pass
                elif asset_class in ('etf', 'index'):
                    alpha_score -= 20
                else:
                    alpha_score -= 30
            
            return min(100.0, max(0.0, alpha_score))

        # --- RSI proximity ---------------------------------------------------
        rsi_info = sym_dist.get('RSI', {})
        rsi_current = rsi_info.get('current_value')
        if rsi_current is not None:
            import re
            # Match patterns like RSI(14) < 45, RSI(14) > 30
            for m in re.finditer(r'RSI\(\d+\)\s*<\s*(\d+)', conditions_text):
                threshold = float(m.group(1))
                # How close is current RSI to being below threshold?
                if rsi_current < threshold:
                    score += 25  # already satisfies
                else:
                    distance = rsi_current - threshold
                    score += max(0, 25 - distance)  # linear decay
                checks += 1

            for m in re.finditer(r'RSI\(\d+\)\s*>\s*(\d+)', conditions_text):
                threshold = float(m.group(1))
                if rsi_current > threshold:
                    score += 25
                else:
                    distance = threshold - rsi_current
                    score += max(0, 25 - distance)
                checks += 1

        # --- Stochastic proximity ---------------------------------------------
        stoch_info = sym_dist.get('STOCH', {})
        stoch_current = stoch_info.get('current_value')
        if stoch_current is not None and 'STOCH' in conditions_text:
            import re
            for m in re.finditer(r'STOCH\(\d+\)\s*<\s*(\d+)', conditions_text):
                threshold = float(m.group(1))
                if stoch_current < threshold:
                    score += 25
                else:
                    distance = stoch_current - threshold
                    score += max(0, 25 - distance)
                checks += 1

            for m in re.finditer(r'STOCH\(\d+\)\s*>\s*(\d+)', conditions_text):
                threshold = float(m.group(1))
                if stoch_current > threshold:
                    score += 25
                else:
                    distance = threshold - stoch_current
                    score += max(0, 25 - distance)
                checks += 1

        # --- Price vs SMA / EMA proximity ------------------------------------
        if current_price > 0:
            # Approximate SMA(20) from price_action (current_price is close to it
            # in ranging markets).  We use the 20-day midpoint as a rough SMA proxy.
            sma_proxy = (price_action.get('high_20d', current_price) +
                         price_action.get('low_20d', current_price)) / 2.0

            if 'CLOSE > SMA' in conditions_text or 'CLOSE > EMA' in conditions_text:
                if current_price > sma_proxy:
                    score += 20
                else:
                    pct_below = (sma_proxy - current_price) / sma_proxy * 100
                    score += max(0, 20 - pct_below * 5)
                checks += 1

            if 'CLOSE < SMA' in conditions_text or 'CLOSE < EMA' in conditions_text:
                if current_price < sma_proxy:
                    score += 20
                else:
                    pct_above = (current_price - sma_proxy) / sma_proxy * 100
                    score += max(0, 20 - pct_above * 5)
                checks += 1

            # MA crossover patterns (SMA/EMA CROSSES_BELOW or EMA < EMA)
            if ('CROSSES_BELOW' in conditions_text and ('SMA' in conditions_text or 'EMA' in conditions_text)):
                # Bearish crossover: score based on negative trend
                # price_change_20d is in pct points (e.g., -3.0 = -3%)
                price_change_20d = trend.get('price_change_20d', 0)
                if price_change_20d < -2:
                    score += 20  # Strong negative momentum → crossover likely
                elif price_change_20d < 0:
                    score += 12  # Mild negative
                else:
                    score += max(0, 5 - price_change_20d * 2)  # Positive = unlikely
                checks += 1

            # EMA alignment patterns (EMA(10) < EMA(20) < EMA(50))
            if 'EMA(10)' in conditions_text and 'EMA(20)' in conditions_text and '<' in conditions_text:
                # Check if this is a bearish alignment (short template)
                if template_direction == 'short':
                    price_change_20d = trend.get('price_change_20d', 0)
                    trend_strength = trend.get('trend_strength', 0)
                    if price_change_20d < -3 and trend_strength > 0.3:
                        score += 20  # Strong downtrend → EMAs likely aligned bearish
                    elif price_change_20d < -1:
                        score += 10
                    checks += 1

            # --- Bollinger Band proximity ------------------------------------
            if 'BB_LOWER' in conditions_text or 'BB_UPPER' in conditions_text or 'BB_MIDDLE' in conditions_text:
                atr = vol.get('current_atr', 0)
                bb_middle = sma_proxy
                bb_upper = bb_middle + 2 * atr if atr else bb_middle * 1.02
                bb_lower = bb_middle - 2 * atr if atr else bb_middle * 0.98

                if 'BB_LOWER' in conditions_text and 'CLOSE < BB_LOWER' in conditions_text:
                    if current_price < bb_lower:
                        score += 20
                    else:
                        dist_pct = (current_price - bb_lower) / current_price * 100
                        score += max(0, 20 - dist_pct * 4)
                    checks += 1

                if 'BB_UPPER' in conditions_text and 'CLOSE > BB_UPPER' in conditions_text:
                    if current_price > bb_upper:
                        score += 20
                    else:
                        dist_pct = (bb_upper - current_price) / current_price * 100
                        score += max(0, 20 - dist_pct * 4)
                    checks += 1

                if 'BB_MIDDLE' in conditions_text and 'CLOSE > BB_MIDDLE' in conditions_text:
                    if current_price > bb_middle:
                        score += 20
                    else:
                        dist_pct = (bb_middle - current_price) / current_price * 100
                        score += max(0, 20 - dist_pct * 4)
                    checks += 1

            # --- Support / Resistance proximity --------------------------------
            if 'RESISTANCE' in conditions_text:
                resistance = price_action.get('resistance', current_price)
                if resistance and resistance > 0:
                    if current_price >= resistance * 0.998:
                        score += 20
                    else:
                        dist_pct = (resistance - current_price) / current_price * 100
                        score += max(0, 20 - dist_pct * 4)
                    checks += 1

            if 'SUPPORT' in conditions_text and 'CLOSE < SUPPORT' in conditions_text:
                support = price_action.get('support', current_price)
                if support and support > 0:
                    if current_price <= support * 1.002:
                        score += 20
                    else:
                        dist_pct = (current_price - support) / current_price * 100
                        score += max(0, 20 - dist_pct * 4)
                    checks += 1

        # --- ADX proximity ----------------------------------------------------
        if 'ADX' in conditions_text:
            adx_val = trend.get('adx', 0)
            import re
            for m in re.finditer(r'ADX\(\d+\)\s*>\s*(\d+)', conditions_text):
                threshold = float(m.group(1))
                if adx_val > threshold:
                    score += 15
                else:
                    distance = threshold - adx_val
                    score += max(0, 15 - distance)
                checks += 1

        # --- MACD (give a baseline score — we do not have real-time MACD) ------
        if 'MACD' in conditions_text:
            # price_change_20d is in percentage points (e.g., -3.0 = -3%)
            price_change = trend.get('price_change_20d', 0)
            if 'CROSSES_ABOVE' in conditions_text:
                # Bullish MACD crossover: positive momentum helps
                if price_change > 0:
                    score += 15
                else:
                    score += max(0, 15 + price_change)  # decays as price drops (e.g., -3 → 12)
                checks += 1
            elif 'CROSSES_BELOW' in conditions_text:
                # Bearish MACD crossover: negative momentum helps
                if price_change < 0:
                    score += 15
                else:
                    score += max(0, 15 - price_change)  # decays as price rises
                checks += 1

        # --- SHORT trend-following scoring ------------------------------------
        # SHORT templates need symbols in actual downtrends. Score based on:
        # - Negative 20d/50d price change (momentum)
        # - Price below key MAs (trend structure)
        # - Sufficient volatility (need movement to profit from shorts)
        # NOTE: price_change values are in percentage points (e.g., -3.0 = -3%)
        template_direction = (template.metadata or {}).get('direction', 'long').lower()
        if template_direction == 'short' and current_price > 0:
            price_change_20d = trend.get('price_change_20d', 0)  # In pct points: -3.0 = -3%
            price_change_50d = trend.get('price_change_50d', 0)
            trend_strength = trend.get('trend_strength', 0)
            volatility = vol.get('volatility', 0)

            # Negative momentum = good for shorts (values in pct points)
            if price_change_20d < -2:
                score += 20  # Stock is actually falling (> 2% in 20d)
            elif price_change_20d < 0:
                score += 10  # Slightly negative
            else:
                score += 0   # Positive momentum = bad for shorts
            checks += 1

            # Negative 50d trend confirms sustained downtrend
            if price_change_50d < -3:
                score += 15
            elif price_change_50d < 0:
                score += 8
            checks += 1

            # Volatility: shorts need movement. Low-vol stocks don't move enough.
            if volatility > 0.025:
                score += 10  # Good volatility for shorting
            elif volatility > 0.015:
                score += 5
            checks += 1

            # Penalize indices/forex for trend-following shorts — they mean-revert
            # more than individual stocks. Stocks have idiosyncratic risk that
            # sustains trends (earnings misses, sector rotation, etc.)
            asset_class = self._get_asset_class(symbol)
            if asset_class == 'stock':
                score += 10  # Stocks trend better than indices
            elif asset_class in ('index', 'forex'):
                score -= 5   # Indices/forex mean-revert, bad for trend shorts

        # --- Volume proximity (for volume-dependent templates) ----------------
        vol_profile = sym_stats.get('volume_profile', {})
        has_volume = vol_profile.get('has_volume_data', False)
        
        # Volume hard-block already checked at top of method. Here we just score.
        if has_volume and template_needs_volume:
            spike_freq = vol_profile.get('spike_frequency', 0)
            vol_trend = vol_profile.get('volume_trend', 1.0)
            current_vs_avg = vol_profile.get('current_vs_avg', 1.0)
            
            # Volume spike templates: prefer symbols with frequent spikes
            if 'VOLUME_MA' in conditions_text and ('*' in conditions_text or 'VOLUME >' in conditions_text):
                # Score based on spike frequency (higher = more likely to trigger)
                score += min(20, spike_freq * 200)  # 10% spike freq → 20 points
                # Bonus if current volume is already elevated
                if current_vs_avg > 1.5:
                    score += 10
                checks += 1
            
            # Rising volume trend bonus for momentum/breakout templates
            if vol_trend > 1.1:
                score += 5  # Volume increasing — good for breakout/momentum

        # Normalise to 0-100
        if checks == 0:
            return 50.0  # no data → neutral score
        
        # Per-condition scoring: if ANY condition scored 0 out of its max,
        # the template is unlikely to fire on this symbol. Apply a heavy penalty.
        per_check_max = 25.0  # Each check contributes up to 25 points
        if checks > 0:
            avg_per_check = score / checks
            if avg_per_check < 5.0:
                # Average score per condition is very low — almost no condition is close to firing
                return 0.0
        
        # Normalize: use a blend of average-per-check and total-conditions-met.
        # This prevents simple 1-condition templates (RSI Dip Buy) from always
        # outscoring complex multi-condition templates (BB Bounce + RSI + SMA).
        #
        # Old formula: score/checks * 4.0  → penalizes templates with more checks
        # New formula: weighted blend of:
        #   - avg_score (how close each condition is to firing): 60% weight
        #   - breadth_bonus (reward for having multiple conditions all scoring well): 40% weight
        #
        # A 3-condition template scoring 15/25 on each (avg=15) gets:
        #   avg_component = 15/25 * 100 * 0.6 = 36
        #   breadth_bonus = min(20, (3-1) * 8) * (15/25) = 16 * 0.6 = 9.6 → * 0.4 = 3.84
        #   total = 39.84 → ~40
        #
        # A 1-condition template scoring 22/25 (avg=22) gets:
        #   avg_component = 22/25 * 100 * 0.6 = 52.8
        #   breadth_bonus = min(20, 0) * (22/25) = 0 → * 0.4 = 0
        #   total = 52.8 → ~53
        #
        # Gap narrowed from 88 vs 60 to 53 vs 40. Multi-condition templates
        # are still lower (they SHOULD be — harder to fire) but not crushed.
        avg_per_check = score / checks
        avg_component = (avg_per_check / per_check_max) * 100.0 * 0.6
        
        # Breadth bonus: reward templates that have multiple conditions all scoring decently.
        # Each additional check beyond 1 adds up to 8 points, scaled by how well conditions scored.
        breadth_raw = min(20.0, (checks - 1) * 8.0) * (avg_per_check / per_check_max)
        breadth_component = breadth_raw * 0.4
        
        base_score = min(100.0, avg_component + breadth_component)
        
        # Crypto-optimized bonus: already hard-blocked non-crypto at the top of this method.
        # Give crypto symbols a small scoring boost for their native templates.
        if template.metadata and template.metadata.get('crypto_optimized'):
            base_score = min(100.0, base_score + 10)
        
        # Non-crypto ranging/mean-reversion templates get a small boost for crypto symbols
        # in ranging regimes. Templates like Keltner Channel Bounce and BB Middle Band Bounce
        # work well on crypto in quiet markets, but get outscored by stock symbols.
        if not (template.metadata and template.metadata.get('crypto_optimized')):
            asset_class = self._get_asset_class(symbol)
            if asset_class == 'crypto':
                is_ranging_template = (
                    template.strategy_type == StrategyType.MEAN_REVERSION or
                    any(r in [MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL] 
                        for r in (template.market_regimes or []))
                )
                if is_ranging_template:
                    base_score = min(100.0, base_score + 10)
        
        # --- Forex carry bias at proposal time --------------------------------
        # Boost forex template-symbol combos where the template direction aligns
        # with the carry direction. Mean-reversion templates on pairs with strong
        # carry get an extra boost since carry trades tend to mean-revert to fair value.
        asset_class = self._get_asset_class(symbol)
        if asset_class == 'forex' and self.market_analyzer:
            try:
                carry_data = self.market_analyzer.get_carry_rates()
                carry_diff = carry_data.get('carry', {}).get(symbol.upper())
                if carry_diff is not None and abs(carry_diff) >= 0.5:
                    is_long_template = template_direction != 'short'
                    carry_favors_long = carry_diff > 0

                    # Direction alignment: +10 if template direction matches carry
                    if (is_long_template and carry_favors_long) or (not is_long_template and not carry_favors_long):
                        base_score = min(100.0, base_score + 10)
                        # Extra boost for mean-reversion on high-carry pairs
                        if template.strategy_type == StrategyType.MEAN_REVERSION and abs(carry_diff) >= 2.0:
                            base_score = min(100.0, base_score + 5)
                    else:
                        # Fighting carry: penalize
                        base_score = max(0.0, base_score - 8)
            except Exception:
                pass  # Carry data unavailable — no adjustment

        # --- Crypto halving cycle bias at proposal time -----------------------
        # Boost/penalize crypto proposals based on where we are in the halving cycle.
        # In accumulation/early_bull phases, boost low-frequency trend templates.
        # In distribution/bear phases, penalize all crypto proposals.
        if asset_class == 'crypto' and self.market_analyzer:
            try:
                cycle = self.market_analyzer.get_crypto_cycle_phase()
                recommendation = cycle.get('recommendation', 'hold')
                is_low_freq = template.metadata and template.metadata.get('low_frequency')

                if recommendation == 'accumulate':
                    base_score = min(100.0, base_score + 15)
                    if is_low_freq:
                        base_score = min(100.0, base_score + 5)  # Extra boost for patient strategies
                elif recommendation == 'hold':
                    base_score = min(100.0, base_score + 5)
                elif recommendation == 'reduce':
                    base_score = max(0.0, base_score - 15)
                elif recommendation == 'avoid':
                    base_score = max(0.0, base_score - 25)
            except Exception:
                pass
        
        return base_score

    def _match_templates_to_symbols(
        self,
        templates_for_cycle: List[StrategyTemplate],
        symbols: List[str],
        adjusted_count: int,
        market_statistics: Dict,
        indicator_distributions: Dict,
    ) -> List[Tuple[StrategyTemplate, str]]:
        """
        Round-robin template-first selection: every template gets its best
        symbol(s) before any template gets a second slot. This guarantees
        maximum template diversity in every cycle.

        Think of it like a trader allocating a research budget: you want to
        test every strategy idea, not just the ones that worked last month.
        The score only decides which *symbol* is best for a given template —
        templates don't compete against each other for slots.

        Algorithm:
        1. Score all (template, symbol) pairs purely on signal likelihood
        2. For each template, rank its symbols by score
        3. Round-robin: pick the best symbol for each template (round 1),
           then the 2nd-best for each template (round 2), etc.
        4. Apply directional quotas (LONG/SHORT balance) and asset class
           minimums as post-filters, not as scoring penalties
        """
        import math
        import yaml
        import random
        from pathlib import Path
        from collections import defaultdict

        max_per_symbol = max(2, math.ceil(adjusted_count / max(len(symbols), 1)))

        # --- Load active (template, symbol) pairs to exclude from selection ---
        # These are combos already in the pipeline (DEMO/LIVE/approved-BACKTESTED).
        # Excluding them here (not downstream in generate_strategies_from_templates)
        # means their slots go to new combos instead of being wasted.
        active_pairs: set = set()
        try:
            from src.models.database import get_database
            from src.models.orm import StrategyORM
            from src.models.enums import StrategyStatus
            import json as _json_ap
            db = get_database()
            session = db.get_session()
            try:
                existing = session.query(StrategyORM).filter(
                    StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE, StrategyStatus.BACKTESTED])
                ).all()
                for s in existing:
                    md = s.strategy_metadata if isinstance(s.strategy_metadata, dict) else {}
                    if s.status == StrategyStatus.BACKTESTED and not md.get('activation_approved'):
                        continue
                    tname = md.get('template_name', s.name)
                    syms = s.symbols if isinstance(s.symbols, list) else (_json_ap.loads(s.symbols) if isinstance(s.symbols, str) else [])
                    for sym in syms:
                        active_pairs.add((tname, sym))
            finally:
                session.close()
            if active_pairs:
                logger.info(f"Excluding {len(active_pairs)} active (template, symbol) pairs from selection")
        except Exception as e:
            logger.debug(f"Could not load active pairs for exclusion: {e}")

        # --- PHASE 1: Score all (template, symbol) pairs ---
        # Score is purely "how likely is this symbol to fire this template's
        # entry conditions right now?" No penalties for active count, no
        # exploration boosts. Pure signal likelihood.
        template_weights = getattr(self, '_template_weights', {})
        symbol_scores_fb = getattr(self, '_symbol_scores', {})

        all_pairs: List[Tuple[float, StrategyTemplate, str]] = []
        template_ranked: Dict[str, List[Tuple[float, str]]] = defaultdict(list)
        template_map: Dict[str, StrategyTemplate] = {}

        active_templates = []
        for template in templates_for_cycle:
            disabled, _reason = self._is_template_disabled(template)
            if disabled:
                continue
            active_templates.append(template)
            template_map[template.name] = template

            for symbol in symbols:
                # Skip combos already active in the pipeline.
                # Exception: crypto_optimized templates only have BTC/ETH as valid symbols.
                # With only 2 symbols, blocking both because another version is already
                # running would permanently starve all crypto templates. Allow them through
                # — the per-timeframe cap (MAX_PER_SYMBOL_PER_TIMEFRAME) handles concentration.
                is_crypto_template = bool(template.metadata and template.metadata.get('crypto_optimized'))
                if not is_crypto_template and (template.name, symbol) in active_pairs:
                    continue

                # Skip daily-only LME metals for intraday/4h templates — no data available
                _tmpl_is_intraday = bool(template.metadata and (
                    template.metadata.get('intraday') or template.metadata.get('interval_4h')
                ))
                if _tmpl_is_intraday and symbol.upper() in _DAILY_ONLY_SYMBOLS:
                    continue

                base_score = self._score_symbol_for_template(
                    template, symbol, market_statistics, indicator_distributions
                )
                if base_score <= 0:
                    continue

                # Light performance feedback — just a tiebreaker, not a dominator
                ttype = (template.metadata or {}).get('strategy_type') or template.name
                tw = template_weights.get(ttype, 1.0)
                base_score *= tw

                # Fast 5-day feedback suppression — applied on top of 60-day weights.
                # If a template family has < 30% win rate in the last 5 days, suppress
                # it to 10-40% of normal weight. This adapts to current market within days.
                # Example: ATR Dynamic Trend Follow at 20% win rate → 0.1x multiplier.
                fast_suppression = getattr(self, '_fast_template_suppression', {})
                fast_mult = fast_suppression.get(template.name, 1.0)

                # Market Quality Score: in low-quality (choppy) markets, additionally
                # suppress trend-following templates by up to 50%.
                mqs_trend_mult = getattr(self, '_mqs_trend_weight_multiplier', 1.0)
                if mqs_trend_mult < 1.0:
                    tmpl_type = (template.metadata or {}).get('strategy_type', '')
                    tmpl_name_lower = template.name.lower()
                    is_trend = (
                        str(tmpl_type).lower() in ('trend_following', 'momentum', 'breakout') or
                        any(kw in tmpl_name_lower for kw in ['trend', 'momentum', 'breakout', 'atr dynamic', 'ema ribbon', 'adx', 'vwap trend'])
                    )
                    if is_trend:
                        fast_mult *= mqs_trend_mult

                if fast_mult != 1.0:
                    base_score *= fast_mult

                sym_bonus = symbol_scores_fb.get(symbol, 0.0)
                base_score += max(-15.0, min(15.0, sym_bonus))

                # Small noise to break ties between similar symbols
                noise = random.uniform(-3, 3)
                final_score = base_score + noise

                if final_score > 0:
                    all_pairs.append((final_score, template, symbol))
                    template_ranked[template.name].append((final_score, symbol))

        # Sort each template's symbol list by score descending
        for tname in template_ranked:
            template_ranked[tname].sort(key=lambda x: -x[0])

        all_pairs.sort(key=lambda x: -x[0])

        logger.info(
            f"Scored {len(all_pairs)} viable (template, symbol) pairs "
            f"across {len(active_templates)} templates and {len(symbols)} symbols"
        )
        logger.info(f"Top 10 (template, symbol) pairs by signal-likelihood score:")
        for score, tmpl, sym in all_pairs[:10]:
            logger.info(f"  {tmpl.name} × {sym} = {score:.1f}")

        # Log templates with zero viable pairs (all combos blocked by blacklists/active_pairs)
        templates_with_pairs = set(tmpl.name for _, tmpl, _ in all_pairs)
        templates_no_pairs = [t for t in active_templates if t.name not in templates_with_pairs]
        if templates_no_pairs:
            # Group by reason for better diagnostics
            blocked_by_active = []
            blocked_by_blacklist = []
            blocked_by_regime = []
            for t in templates_no_pairs:
                all_combos_active = all(
                    (t.name, sym) in active_pairs for sym in symbols
                )
                all_combos_blacklisted = all(
                    (t.name, sym) in self._zero_trade_blacklist or
                    self.is_rejection_blacklisted(t.name, sym)
                    for sym in symbols[:10]  # Sample first 10 to avoid O(n²)
                )
                if all_combos_active:
                    blocked_by_active.append(t.name)
                elif all_combos_blacklisted:
                    blocked_by_blacklist.append(t.name)
                else:
                    blocked_by_regime.append(t.name)
            if blocked_by_active:
                logger.info(f"Templates with all combos already active ({len(blocked_by_active)}): "
                           f"{', '.join(blocked_by_active[:10])}")
            if blocked_by_blacklist:
                logger.info(f"Templates with all combos blacklisted ({len(blocked_by_blacklist)}): "
                           f"{', '.join(blocked_by_blacklist[:10])}")
            if blocked_by_regime:
                logger.info(f"Templates with no viable pairs (low score/regime mismatch) ({len(blocked_by_regime)}): "
                           f"{', '.join(blocked_by_regime[:10])}")

        # --- PHASE 2: Round-robin template-first selection ---
        # Every template gets a seat at the table. Score only decides which
        # symbol is best for each template — templates don't compete.

        # Load directional quotas from config
        quotas_config = {}
        try:
            config_path = Path("config/autonomous_trading.yaml")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    quotas_config = config.get('position_management', {}).get('directional_quotas', {})
        except Exception as e:
            logger.warning(f"Could not load directional quotas config: {e}")

        quotas_enabled = quotas_config.get('enabled', True)
        current_regime = 'ranging'
        try:
            sub_regime, _, _, _ = self.market_analyzer.detect_sub_regime()
            current_regime = sub_regime.value.lower()
        except Exception:
            pass

        regime_quotas = quotas_config.get(current_regime)
        if not regime_quotas:
            parent_regime_map = {
                'ranging_low_vol': 'ranging', 'ranging_high_vol': 'ranging',
                'trending_up_strong': 'trending_up', 'trending_up_weak': 'trending_up',
                'trending_down_strong': 'trending_down', 'trending_down_weak': 'trending_down',
            }
            parent = parent_regime_map.get(current_regime)
            regime_quotas = quotas_config.get(parent, quotas_config.get('ranging', {}))
        min_long_pct = regime_quotas.get('min_long_pct', 0.35)
        min_short_pct = regime_quotas.get('min_short_pct', 0.35)

        def _get_direction(template: StrategyTemplate) -> str:
            md = template.metadata or {}
            return md.get('direction', 'long').lower()

        def _is_alpha_edge(template: StrategyTemplate) -> bool:
            md = template.metadata or {}
            return md.get('strategy_category') == 'alpha_edge'

        # Separate DSL and Alpha Edge templates
        dsl_templates = [t for t in active_templates if not _is_alpha_edge(t)]
        ae_templates_list = [t for t in active_templates if _is_alpha_edge(t)]

        # Shuffle template order each cycle so the round-robin starting
        # position varies — prevents the same templates always getting "first pick"
        random.shuffle(dsl_templates)

        long_templates = [t for t in dsl_templates if _get_direction(t) == 'long']
        short_templates = [t for t in dsl_templates if _get_direction(t) == 'short']

        dsl_count = adjusted_count
        min_long_count = max(1, int(math.ceil(dsl_count * min_long_pct))) if quotas_enabled else 0
        min_short_count = max(1, int(math.ceil(dsl_count * min_short_pct))) if quotas_enabled else 0

        logger.info(
            f"Round-robin: {len(dsl_templates)} DSL templates "
            f"({len(long_templates)}L, {len(short_templates)}S), "
            f"target {dsl_count}, min {min_long_count}L/{min_short_count}S"
        )

        picked_combos = set()
        symbol_usage = defaultdict(int)
        assignments: List[Tuple[StrategyTemplate, str]] = []
        # Track which asset classes each template has been assigned to
        template_asset_classes: Dict[str, set] = defaultdict(set)

        def _pick_best_symbol(tmpl, force_new_asset_class=False):
            """Pick the highest-scored unused symbol for this template.
            
            If force_new_asset_class=True, skip symbols whose asset class
            is already covered by a previous assignment for this template.
            This ensures each template's slots span different asset classes
            (stock, crypto, ETF, commodity, forex) before doubling up.
            Falls back to any viable symbol if no new asset class is available.
            """
            covered = template_asset_classes.get(tmpl.name, set())
            # First pass: prefer a symbol from an uncovered asset class
            if force_new_asset_class and covered:
                for _sc, sym in template_ranked.get(tmpl.name, []):
                    if (tmpl.name, sym) in picked_combos:
                        continue
                    if symbol_usage[sym] >= max_per_symbol:
                        continue
                    if self._get_asset_class(sym) in covered:
                        continue
                    return sym
            # Second pass (or first if not forcing): best available
            for _sc, sym in template_ranked.get(tmpl.name, []):
                if (tmpl.name, sym) in picked_combos:
                    continue
                if symbol_usage[sym] >= max_per_symbol:
                    continue
                return sym
            return None

        def _assign(tmpl, sym):
            picked_combos.add((tmpl.name, sym))
            symbol_usage[sym] += 1
            template_asset_classes[tmpl.name].add(self._get_asset_class(sym))
            assignments.append((tmpl, sym))

        # Round 1: every template gets its best symbol (pure score)
        for t in long_templates:
            sym = _pick_best_symbol(t)
            if sym:
                _assign(t, sym)
        for t in short_templates:
            sym = _pick_best_symbol(t)
            if sym:
                _assign(t, sym)

        r1_long = sum(1 for t, _ in assignments if _get_direction(t) == 'long')
        r1_short = sum(1 for t, _ in assignments if _get_direction(t) == 'short')
        logger.info(f"Round 1 (1 per template): {len(assignments)} ({r1_long}L, {r1_short}S)")

        # Fill directional quota shortfalls
        if quotas_enabled:
            for deficit, pool in [(max(0, min_long_count - r1_long), long_templates),
                                  (max(0, min_short_count - r1_short), short_templates)]:
                for t in pool:
                    if deficit <= 0:
                        break
                    sym = _pick_best_symbol(t, force_new_asset_class=True)
                    if sym:
                        _assign(t, sym)
                        deficit -= 1

        # Round-robin remaining slots — force different asset classes so each
        # template gets tested across stocks, crypto, ETFs, commodities, forex
        # before doubling up on any single asset class.
        remaining = dsl_count - len(assignments)
        rnd = 2
        while remaining > 0:
            filled = 0
            order = (long_templates + short_templates) if rnd % 2 == 0 else (short_templates + long_templates)
            for t in order:
                if remaining <= 0:
                    break
                sym = _pick_best_symbol(t, force_new_asset_class=True)
                if sym:
                    _assign(t, sym)
                    remaining -= 1
                    filled += 1
            if filled == 0:
                break
            rnd += 1

        logger.info(f"Round-robin filled to {len(assignments)}/{dsl_count} in {rnd - 1} rounds")

        # Alpha Edge on top
        for _sc, t, sym in all_pairs:
            if not _is_alpha_edge(t):
                continue
            if (t.name, sym) in picked_combos:
                continue
            _assign(t, sym)

        # Asset class minimums
        from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX
        crypto_set = set(DEMO_ALLOWED_CRYPTO)
        forex_set = set(DEMO_ALLOWED_FOREX)
        crypto_count = sum(1 for _, s in assignments if s in crypto_set)
        forex_count = sum(1 for _, s in assignments if s in forex_set)
        min_crypto = max(2, int(dsl_count * 0.10))
        min_forex = max(1, int(dsl_count * 0.05))

        for asset_set, cur, mn, label, dir_filter in [
            (crypto_set, crypto_count, min_crypto, "crypto", lambda t: _get_direction(t) == 'long'),
            (forex_set, forex_count, min_forex, "forex", lambda t: True),
        ]:
            if cur < mn:
                needed = mn - cur
                for _sc, t, sym in all_pairs:
                    if needed <= 0:
                        break
                    if sym not in asset_set or (t.name, sym) in picked_combos or not dir_filter(t):
                        continue
                    _assign(t, sym)
                    needed -= 1
                added = (mn - cur) - needed
                if added > 0:
                    logger.info(f"Asset class: +{added} {label} (was {cur}, min {mn})")

        # Filter impossible SHORT combos
        NO_SHORT_ASSET_CLASSES = {"crypto"}
        assignments = [(t, s) for t, s in assignments
                       if not (_get_direction(t) == 'short' and self._get_asset_class(s) in NO_SHORT_ASSET_CLASSES)]

        # Final logging
        fl = sum(1 for t, _ in assignments if _get_direction(t) == 'long' and not _is_alpha_edge(t))
        fs = sum(1 for t, _ in assignments if _get_direction(t) == 'short' and not _is_alpha_edge(t))
        fa = sum(1 for t, _ in assignments if _is_alpha_edge(t))
        ut = len({t.name for t, _ in assignments})
        us = len({s for _, s in assignments})
        logger.info(
            f"Final: {len(assignments)} proposals — {fl}L, {fs}S, {fa}AE | "
            f"{ut} unique templates, {us} unique symbols (regime: {current_regime})"
        )
        for idx, (t, s) in enumerate(assignments[:20]):
            d = _get_direction(t)
            lbl = "AE" if _is_alpha_edge(t) else d.upper()
            logger.info(f"  {idx+1}: '{t.name}' → {s} [{lbl}]")
        if len(assignments) > 20:
            logger.info(f"  ... and {len(assignments) - 20} more")

        self._last_scored_pairs = all_pairs
        return assignments

    def _build_watchlists(
        self,
        all_pairs: List[Tuple[float, 'StrategyTemplate', str]],
        assignments: List[Tuple['StrategyTemplate', str]],
        watchlist_size: int = 10,
        active_symbol_template_pairs: set = None,
    ) -> Dict[str, List[str]]:
        """
        For each template in assignments, build a watchlist of symbols.

        Priority order:
        1. Primary symbol (from the assignment) — always first, always WF-validated
        2. WF-validated symbols for this template (from persisted _wf_validated)
        3. Top-scored symbols from _score_symbol_for_template (unvalidated but promising)

        All symbols restricted to the same asset class as the primary.
        Blacklisted (template, symbol) combos are excluded.
        Symbols already covered by another active strategy of the same template are excluded
        (prevents the same symbol appearing in multiple strategies' watchlists for the same template).

        Args:
            all_pairs: All (score, template, symbol) triples, sorted descending by score
            assignments: The selected (template, symbol) pairs from _match_templates_to_symbols
            watchlist_size: Max symbols per strategy watchlist
            active_symbol_template_pairs: Set of (template_name, symbol) already in active pipeline

        Returns:
            Dict mapping template.name to ordered list of symbols (primary first)
        """
        watchlists: Dict[str, List[str]] = {}
        _active_pairs = active_symbol_template_pairs or set()
        
        ASSET_CLASS_GROUPS = {
            'stock': {'stock', 'etf'},
            'etf': {'stock', 'etf'},
            'crypto': {'crypto'},
            'forex': {'forex'},
            'index': {'index'},
            'commodity': {'commodity'},
        }
        
        # Group all_pairs by template name for fast lookup
        template_scores: Dict[str, List[Tuple[float, str]]] = {}
        for score, template, symbol in all_pairs:
            tname = template.name
            if tname not in template_scores:
                template_scores[tname] = []
            template_scores[tname].append((score, symbol))
        
        for template, primary_symbol in assignments:
            tname = template.name
            if tname in watchlists:
                continue
            
            primary_class = self._get_asset_class(primary_symbol)
            allowed_classes = ASSET_CLASS_GROUPS.get(primary_class, {primary_class})
            
            watchlist = [primary_symbol]
            seen = {primary_symbol}
            
            # Phase 1: Add WF-validated symbols for this template (proven to work)
            _template_is_intraday = bool(template.metadata and (
                template.metadata.get('intraday', False) or
                template.metadata.get('interval_4h', False)
            ))
            validated_for_template = [
                (v['sharpe'], sym)
                for (t, sym), v in self._wf_validated.items()
                if t == tname and sym not in seen
                and self._get_asset_class(sym) in allowed_classes
                and (tname, sym) not in _active_pairs  # skip symbols already in active pipeline
                # Don't add daily-only LME metals to intraday/4h template watchlists
                and not (_template_is_intraday and sym.upper() in _DAILY_ONLY_SYMBOLS)
            ]
            # Sort by Sharpe descending — best performers first
            validated_for_template.sort(reverse=True)
            
            for sharpe, sym in validated_for_template:
                if len(watchlist) >= watchlist_size:
                    break
                # Skip blacklisted combos
                bl_key = (tname, sym)
                if bl_key in self._zero_trade_blacklist and self._zero_trade_blacklist[bl_key] >= self._zero_trade_blacklist_threshold:
                    continue
                seen.add(sym)
                watchlist.append(sym)
            
            validated_count = len(watchlist) - 1  # Exclude primary
            
            # Phase 2: Fill remaining slots with top-scored symbols (unvalidated but promising)
            candidates = template_scores.get(tname, [])
            for score, symbol in candidates:
                if len(watchlist) >= watchlist_size:
                    break
                if symbol in seen:
                    continue
                if (tname, symbol) in _active_pairs:  # skip symbols already in active pipeline
                    continue
                sym_class = self._get_asset_class(symbol)
                if sym_class not in allowed_classes:
                    continue
                # Don't add daily-only LME metals to intraday/4h template watchlists
                if _template_is_intraday and symbol.upper() in _DAILY_ONLY_SYMBOLS:
                    continue
                # Skip blacklisted combos
                bl_key = (tname, symbol)
                if bl_key in self._zero_trade_blacklist and self._zero_trade_blacklist[bl_key] >= self._zero_trade_blacklist_threshold:
                    continue
                seen.add(symbol)
                watchlist.append(symbol)
            
            watchlists[tname] = watchlist
            scored_count = len(watchlist) - 1 - validated_count
            logger.info(
                f"Watchlist for '{tname}': {len(watchlist)} symbols ({primary_class}) "
                f"[primary: {primary_symbol}, validated: {validated_count}, scored: {scored_count}]"
            )
        
        return watchlists

    def _estimate_signal_frequency(self, params: Dict, template: StrategyTemplate, 
                                   indicator_distributions: Dict) -> float:
        """
        Estimate expected signal frequency (entries per month) based on parameters.
        
        Args:
            params: Strategy parameters
            template: Strategy template
            indicator_distributions: Indicator distribution data
            
        Returns:
            Estimated entries per month (0.0 if cannot estimate)
        """
        # Get indicator distributions from first symbol
        if not indicator_distributions:
            return 0.0
        
        first_symbol = list(indicator_distributions.keys())[0]
        distributions = indicator_distributions[first_symbol]
        
        # Estimate based on strategy type
        if template.strategy_type.value == "mean_reversion":
            # For mean reversion, estimate based on oversold/overbought frequency
            if 'RSI' in distributions and 'oversold_threshold' in params:
                rsi_dist = distributions['RSI']
                oversold_threshold = params['oversold_threshold']
                
                # Estimate percentage of time below threshold
                # Use actual distribution data if available
                pct_oversold = rsi_dist.get('pct_oversold', 5.0)
                
                # Adjust based on our threshold vs standard (30)
                if oversold_threshold < 30:
                    # Tighter threshold = fewer signals
                    adjustment = oversold_threshold / 30.0
                    pct_oversold = pct_oversold * adjustment
                elif oversold_threshold > 30:
                    # Looser threshold = more signals
                    adjustment = oversold_threshold / 30.0
                    pct_oversold = pct_oversold * adjustment
                
                # Convert to entries per month (assuming 21 trading days/month)
                entries_per_month = (pct_oversold / 100.0) * 21
                
                logger.debug(f"Estimated signal frequency: {entries_per_month:.2f} entries/month "
                           f"(RSI < {oversold_threshold}, {pct_oversold:.1f}% of time)")
                
                return entries_per_month
        
        # Default: assume template's expected frequency
        freq_str = template.expected_trade_frequency
        # Parse "2-4 trades/month" -> average 3
        if "trades/month" in freq_str:
            parts = freq_str.split()[0].split("-")
            if len(parts) == 2:
                return (float(parts[0]) + float(parts[1])) / 2.0
        
        return 1.0  # Default to 1 trade/month if cannot estimate
    
    def _generate_strategy_with_params(
        self,
        template: StrategyTemplate,
        symbols: List[str],
        params: Dict,
        variation_number: int,
        market_statistics: Optional[Dict] = None
    ) -> Strategy:
        """
        Generate a strategy from template with specific parameters.
        
        Args:
            template: Strategy template
            symbols: Symbols to trade
            params: Customized parameters
            variation_number: Variation index for naming
            market_statistics: Per-symbol analysis dicts for adaptive risk
            
        Returns:
            Strategy object
        """
        # Check if this is a short strategy
        is_short_strategy = template.metadata and template.metadata.get("direction") == "short"
        
        # Build entry and exit conditions with parameters
        entry_conditions = []
        exit_conditions = []
        
        for condition_template in template.entry_conditions:
            customized_condition = self._apply_parameters_to_condition(
                condition_template,
                params
            )
            entry_conditions.append(customized_condition)
        
        for condition_template in template.exit_conditions:
            customized_condition = self._apply_parameters_to_condition(
                condition_template,
                params
            )
            exit_conditions.append(customized_condition)
        
        # Extract indicator names with periods from conditions
        import re
        
        indicators = []
        all_conditions = entry_conditions + exit_conditions
        
        # Pattern to match indicators with periods: EMA(20), SMA(50), RSI(14), etc.
        indicator_pattern = r'(EMA|SMA|RSI|ATR|STOCH|BB|MACD)\((\d+)\)'
        
        for condition in all_conditions:
            matches = re.findall(indicator_pattern, condition)
            for indicator_name, period in matches:
                # Add indicator with period specification
                indicator_spec = f"{indicator_name}:{period}"
                if indicator_spec not in indicators:
                    indicators.append(indicator_spec)
        
        # Also add indicators from template if not already present
        indicator_mapping = {
            "RSI": "RSI",
            "SMA": "SMA",
            "EMA": "EMA",
            "MACD": "MACD",
            "Bollinger Bands": "Bollinger Bands",
            "ATR": "ATR",
            "Volume MA": "Volume MA",
            "Price Change %": "Price Change %",
            "Support/Resistance": "Support/Resistance",
            "Stochastic Oscillator": "Stochastic Oscillator"
        }
        
        for template_indicator in template.required_indicators:
            # Extract base indicator name
            if "Band" in template_indicator:
                if "Bollinger Bands" not in indicators:
                    indicators.append("Bollinger Bands")
            elif "MACD" in template_indicator:
                if "MACD" not in indicators:
                    indicators.append("MACD")
            elif "Support" in template_indicator or "Resistance" in template_indicator:
                if "Support/Resistance" not in indicators:
                    indicators.append("Support/Resistance")
            elif "STOCH" in template_indicator:
                if "Stochastic Oscillator" not in indicators:
                    indicators.append("Stochastic Oscillator")
            elif "_" in template_indicator:
                base_name = template_indicator.split("_")[0]
                for template_name in indicator_mapping.keys():
                    if base_name.upper() in template_name.upper():
                        if template_name not in indicators:
                            indicators.append(template_name)
                        break
            else:
                if template_indicator not in indicators:
                    indicators.append(template_indicator)
        
        # Create unique name: template + primary symbol + direction + key params
        # No version number — the name should be meaningful to a trader.
        # If a strategy with this name already exists, it will be caught by dedup.
        symbol_str = symbols[0] if symbols else "Multi"
        direction_str = "SHORT" if is_short_strategy else "LONG"

        # Add key parameter info to name for differentiation
        param_info = ""
        if 'oversold_threshold' in params and 'overbought_threshold' in params:
            param_info = f" RSI({params['oversold_threshold']}/{params['overbought_threshold']})"
        elif 'fast_period' in params and 'slow_period' in params:
            param_info = f" MA({params['fast_period']}/{params['slow_period']})"
        elif 'bb_period' in params and 'bb_std' in params:
            param_info = f" BB({params['bb_period']},{params['bb_std']})"

        strategy_name = f"{template.name} {symbol_str} {direction_str}{param_info}"
        
        # Determine signal interval from params (set by _create_parameter_variation)
        signal_interval = params.get('signal_interval', '1d')
        
        # Create strategy object
        strategy = Strategy(
            id=str(uuid.uuid4()),
            name=strategy_name,
            description=template.description,
            status=StrategyStatus.PROPOSED,
            rules={
                "entry_conditions": entry_conditions,
                "exit_conditions": exit_conditions,
                "indicators": indicators,
                "interval": signal_interval
            },
            symbols=symbols,
            risk_params=self._compute_adaptive_risk_config(
                strategy_type=template.strategy_type,
                symbols=symbols,
                market_statistics=market_statistics,
                template_params=params,
            ),
            created_at=datetime.now(),
            performance=PerformanceMetrics(),
            reasoning=f"Generated from template: {template.name}. {template.description}"
        )
        
        # Apply asset-class-specific risk parameter overrides
        primary_symbol = symbols[0] if symbols else None
        asset_class = self._get_asset_class(primary_symbol) if primary_symbol else "stock"
        strategy.risk_params = self._apply_asset_class_overrides(strategy.risk_params, primary_symbol) if primary_symbol else strategy.risk_params

        # Add metadata
        if not hasattr(strategy, 'metadata') or strategy.metadata is None:
            strategy.metadata = {}
        strategy.metadata['template_name'] = template.name
        strategy.metadata['template_type'] = template.strategy_type.value
        # Don't store template object (not JSON serializable)
        strategy.metadata['customized_parameters'] = params
        strategy.metadata['variation_number'] = variation_number
        strategy.metadata['direction'] = 'short' if is_short_strategy else 'long'  # Store strategy direction
        strategy.metadata['asset_class'] = asset_class

        # Propagate strategy_category from template metadata (e.g., 'alpha_edge')
        if template.metadata and 'strategy_category' in template.metadata:
            strategy.metadata['strategy_category'] = template.metadata['strategy_category']

        # Propagate Alpha Edge specific metadata
        if template.metadata:
            for key in ['requires_fundamental_data', 'requires_earnings_data', 'requires_quality_screening', 
                        'requires_macro_data', 'uses_sector_etfs', 'fixed_symbols', 'min_market_cap',
                        'crypto_optimized', 'intraday', 'interval', 'interval_4h', 'skip_param_override', 'market_neutral',
                        'alpha_edge_type', 'alpha_edge_bypass', 'pair_symbols']:
                if key in template.metadata:
                    strategy.metadata[key] = template.metadata[key]
        
        return strategy
    
    def _get_available_indicators(self) -> List[str]:
        """
        Get list of available technical indicators.
        
        Returns:
            List of indicator names
        """
        # Return the 10 essential indicators from the implementation plan
        return [
            "SMA",
            "EMA",
            "RSI",
            "MACD",
            "Bollinger Bands",
            "ATR",
            "Volume MA",
            "Price Change %",
            "Support/Resistance",
            "Stochastic Oscillator"
        ]
    
    def _create_proposal_prompt(
        self,
        regime: MarketRegime,
        available_indicators: List[str],
        symbols: Optional[List[str]],
        strategy_number: int,
        total_strategies: int = 6,
        market_statistics: Optional[Dict] = None,
        indicator_distributions: Optional[Dict] = None,
        market_context: Optional[Dict] = None
    ) -> str:
        """
        Create prompt for LLM to generate strategy appropriate for market regime.
        
        Args:
            regime: Current market regime
            available_indicators: List of available indicators
            symbols: Symbols to trade (if specified)
            strategy_number: Strategy number in batch (1-indexed)
            total_strategies: Total number of strategies to generate
            market_statistics: Market statistics from MarketStatisticsAnalyzer
            indicator_distributions: Indicator distribution data
            market_context: Market context (VIX, rates, etc.)
        
        Returns:
            Formatted prompt string
        """
        indicators_str = ", ".join(available_indicators)
        
        # Build market data section if statistics are available
        market_data_section = ""
        if market_statistics and len(market_statistics) > 0:
            market_data_section = "\n\nCRITICAL MARKET DATA:\n"
            
            for symbol, stats in market_statistics.items():
                volatility = stats.get('volatility_metrics', {}).get('volatility', 0.0)
                trend_strength = stats.get('trend_metrics', {}).get('trend_strength', 0.0)
                mean_reversion_score = stats.get('mean_reversion_metrics', {}).get('mean_reversion_score', 0.0)
                price_action = stats.get('price_action', {})
                current_price = price_action.get('current_price', 0.0)
                support = price_action.get('support', 0.0)
                resistance = price_action.get('resistance', 0.0)
                
                market_data_section += f"\n{symbol} Market Statistics:\n"
                market_data_section += f"- Volatility: {volatility*100:.1f}%\n"
                market_data_section += f"- Trend strength: {trend_strength:.2f} (0=ranging, 1=strong trend)\n"
                market_data_section += f"- Mean reversion score: {mean_reversion_score:.2f} (0=trending, 1=mean reverting)\n"
                market_data_section += f"- Current price: ${current_price:.2f}\n"
                market_data_section += f"- Support level (20d): ${support:.2f}\n"
                market_data_section += f"- Resistance level (20d): ${resistance:.2f}\n"
                
                # Add indicator distribution data if available
                if indicator_distributions and symbol in indicator_distributions:
                    distributions = indicator_distributions[symbol]
                    
                    if 'RSI' in distributions:
                        rsi = distributions['RSI']
                        market_data_section += f"- RSI below 30 occurs {rsi['pct_oversold']:.1f}% of time (avg duration: {rsi['avg_duration_oversold']:.1f} days)\n"
                        market_data_section += f"- RSI above 70 occurs {rsi['pct_overbought']:.1f}% of time (avg duration: {rsi['avg_duration_overbought']:.1f} days)\n"
                        market_data_section += f"- Current RSI: {rsi['current_value']:.1f}\n"
                    
                    if 'STOCH' in distributions:
                        stoch = distributions['STOCH']
                        market_data_section += f"- Stochastic below 20 occurs {stoch['pct_oversold']:.1f}% of time\n"
                        market_data_section += f"- Stochastic above 80 occurs {stoch['pct_overbought']:.1f}% of time\n"
                    
                    if 'Bollinger_Bands' in distributions:
                        bb = distributions['Bollinger_Bands']
                        market_data_section += f"- Price below lower band occurs {bb.get('pct_below_lower', 0):.1f}% of time\n"
                        market_data_section += f"- Price above upper band occurs {bb.get('pct_above_upper', 0):.1f}% of time\n"
            
            # Add market context if available
            if market_context:
                vix = market_context.get('vix')
                risk_regime = market_context.get('risk_regime', 'unknown')
                
                market_data_section += f"\nMarket Context:\n"
                if vix:
                    market_data_section += f"- VIX (market fear): {vix:.1f}\n"
                market_data_section += f"- Risk regime: {risk_regime}\n"
            
            market_data_section += """
Design a strategy that:
1. Uses thresholds that actually trigger in this market (based on indicator distributions above)
2. Accounts for the current volatility level
3. Respects actual support/resistance levels
4. Considers the mean reversion vs trending characteristics
5. Adapts to the current market context (VIX, risk regime)

IMPORTANT: If RSI < 30 only occurs 5% of the time, do not make it your only entry condition!
Use the distribution data to choose realistic thresholds that will actually trigger trades.
"""
        
        # Regime-specific guidance
        regime_guidance = {
            MarketRegime.TRENDING_UP: (
                "The market is in an uptrend. Focus on momentum and breakout strategies. "
                "Look for opportunities to ride the trend with proper risk management. "
                "Consider strategies that buy on pullbacks or breakouts to new highs."
            ),
            MarketRegime.TRENDING_DOWN: (
                "The market is in a downtrend. Focus on defensive strategies or short-term mean reversion. "
                "Consider strategies that wait for oversold conditions or avoid long positions. "
                "Risk management is critical in downtrends."
            ),
            MarketRegime.RANGING: (
                "The market is range-bound. Focus on mean reversion strategies. "
                "Look for opportunities to buy at support and sell at resistance. "
                "Consider strategies that profit from oscillations within the range."
            )
        }
        
        guidance = regime_guidance.get(regime, "Generate a balanced trading strategy.")
        
        # Strategy-specific focus based on number to ensure diversity
        strategy_focus = ""
        if strategy_number <= 2:
            strategy_focus = (
                "\n\nSTRATEGY FOCUS: Mean Reversion\n"
                "Focus on mean reversion strategies that profit from price returning to average. "
                "Use indicators like RSI, Bollinger Bands, or Stochastic to identify overbought/oversold conditions. "
                "Buy when oversold, sell when overbought."
            )
        elif strategy_number <= 4:
            strategy_focus = (
                "\n\nSTRATEGY FOCUS: Momentum/Breakout\n"
                "Focus on momentum and breakout strategies that ride strong trends. "
                "Use indicators like MACD, EMA crossovers, or price breakouts above resistance. "
                "Enter when momentum is strong, exit when momentum weakens."
            )
        else:
            strategy_focus = (
                "\n\nSTRATEGY FOCUS: Volatility/Oscillators\n"
                "Focus on volatility-based strategies using oscillators. "
                "Use indicators like ATR, Stochastic, or Bollinger Band width. "
                "Trade based on volatility expansion/contraction or oscillator extremes."
            )
        
        symbols_constraint = ""
        if symbols:
            symbols_constraint = f" Trade ONLY these symbols: {', '.join(symbols)}."
        
        # Diversity instruction
        diversity_instruction = (
            f"\n\nDIVERSITY REQUIREMENT: This is strategy #{strategy_number} of {total_strategies}. "
            f"Generate a UNIQUE strategy that is DIFFERENT from typical strategies. "
            f"Use a creative combination of indicators and conditions. "
            f"Make this strategy DISTINCT and innovative - avoid generic patterns."
        )
        
        # Add recent performance history section
        performance_section = ""
        try:
            recent_performance = self.performance_tracker.get_recent_performance(days=30, market_regime=regime.value)
            
            if recent_performance:  # Empty dict is falsy
                performance_section = "\n\nRECENT STRATEGY PERFORMANCE (Last 30 Days):\n"
                
                # Sort by success rate for better presentation
                sorted_types = sorted(
                    recent_performance.items(),
                    key=lambda x: x[1]['success_rate'],
                    reverse=True
                )
                
                for strategy_type, metrics in sorted_types:
                    avg_sharpe = metrics['avg_sharpe']
                    success_rate = metrics['success_rate']
                    count = metrics['count']
                    
                    performance_section += (
                        f"- {strategy_type.replace('_', ' ').title()} strategies: "
                        f"avg Sharpe {avg_sharpe:.2f}, "
                        f"success rate {success_rate:.0%} "
                        f"({count} backtests)\n"
                    )
                
                performance_section += (
                    "\nPrefer strategy types that have worked recently in this market regime. "
                    "If a strategy type has high success rate, consider using similar patterns. "
                    "If a strategy type has low success rate, try a different approach.\n"
                )
            else:
                # No historical data yet
                performance_section = (
                    "\n\nRECENT STRATEGY PERFORMANCE: No historical data available yet. "
                    "This is one of the first strategies being generated.\n"
                )
        except Exception as e:
            logger.warning(f"Could not retrieve performance history: {e}")
            performance_section = ""
        
        prompt_header = (
            "Generate trading strategy #" + str(strategy_number) + " for " + regime.value + " market. " +
            guidance + symbols_constraint + strategy_focus + diversity_instruction + 
            performance_section + market_data_section + "\n\n" +
            "Include entry/exit rules using these indicators: " + indicators_str
        )
        
        prompt = prompt_header + "\n\n" + '''
CRITICAL - USE DSL SYNTAX:
All entry and exit conditions MUST use DSL (Domain-Specific Language) syntax, NOT natural language.

DSL SYNTAX EXAMPLES:
CORRECT DSL: "RSI(14) < 30"
WRONG: "RSI_14 is below 30"

CORRECT DSL: "CLOSE < BB_LOWER(20, 2)"
WRONG: "Price crosses below Lower_Band_20"

CORRECT DSL: "SMA(20) CROSSES_ABOVE SMA(50)"
[X] WRONG: "SMA_20 crosses above SMA_50"

[OK] CORRECT DSL: "MACD() CROSSES_ABOVE MACD_SIGNAL()"
[X] WRONG: "MACD_12_26_9 crosses above MACD_12_26_9_SIGNAL"

DSL SYNTAX RULES:
1. Use indicator functions with parameters: RSI(14), SMA(20), EMA(50)
2. Use comparison operators: <, >, <=, >=, ==, !=
3. Use logical operators: AND, OR
4. Use crossover operators: CROSSES_ABOVE, CROSSES_BELOW
5. Use price fields: CLOSE, OPEN, HIGH, LOW, VOLUME
6. Use indicator shortcuts: BB_LOWER(20, 2), BB_UPPER(20, 2), BB_MIDDLE(20, 2)

COMPLETE DSL SYNTAX REFERENCE:

BASIC COMPARISONS:
- RSI(14) < 30
- RSI(14) > 70
- STOCH(14) < 20
- STOCH(14) > 80
- ATR(14) > 1.5
- CLOSE > SMA(20)
- CLOSE < EMA(50)

BOLLINGER BANDS:
- CLOSE < BB_LOWER(20, 2)
- CLOSE > BB_UPPER(20, 2)
- CLOSE > BB_MIDDLE(20, 2)

CROSSOVERS:
- SMA(20) CROSSES_ABOVE SMA(50)
- SMA(20) CROSSES_BELOW SMA(50)
- MACD() CROSSES_ABOVE MACD_SIGNAL()
- MACD() CROSSES_BELOW MACD_SIGNAL()
- CLOSE CROSSES_ABOVE SMA(20)
- CLOSE CROSSES_BELOW SMA(20)

SUPPORT/RESISTANCE:
- CLOSE > RESISTANCE
- CLOSE < SUPPORT

COMPOUND CONDITIONS (use AND/OR):
- RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2)
- RSI(14) > 70 OR CLOSE > BB_UPPER(20, 2)
- CLOSE > EMA(20) AND EMA(20) > EMA(50)

CRITICAL - EXACT INDICATOR NAMING CONVENTION:
When writing entry/exit conditions, you MUST use EXACT indicator names with this format:

STANDARD FORMAT: {{INDICATOR}}_{{PERIOD}}

SINGLE-WORD INDICATORS:
- "RSI_14" for 14-period RSI (NOT "RSI" or "RSI below 30")
- "SMA_20" for 20-period SMA (NOT "SMA" or "20-day SMA")
- "EMA_50" for 50-period EMA (NOT "EMA" or "50-day EMA")
- "ATR_14" for 14-period ATR
- "STOCH_14" for 14-period Stochastic

MULTI-WORD INDICATORS:
- "VOLUME_MA_20" for 20-period Volume MA
- "PRICE_CHANGE_PCT_1" for 1-day price change %

BOLLINGER BANDS:
- "Upper_Band_20" for upper band (period 20)
- "Middle_Band_20" for middle band
- "Lower_Band_20" for lower band

MACD:
- "MACD_12_26_9" for MACD line
- "MACD_12_26_9_SIGNAL" for signal line
- "MACD_12_26_9_HIST" for histogram

SUPPORT/RESISTANCE:
- "Support" (simple name)
- "Resistance" (simple name)

CRITICAL - PROPER THRESHOLD EXAMPLES:
Use these EXACT threshold patterns for common indicators:

RSI THRESHOLDS (CORRECT):
[OK] Entry (oversold): "RSI(14) < 30" (DSL syntax)
[OK] Exit (overbought): "RSI(14) > 70" (DSL syntax)
[OK] Alternative exit (moderate): "RSI(14) > 60" (more frequent exits)
[OK] Alternative exit (crossover): "RSI(14) CROSSES_ABOVE 50" (mean reversion exit)

BOLLINGER BANDS (CORRECT):
[OK] Entry (lower band): "CLOSE < BB_LOWER(20, 2)" (DSL syntax)
[OK] Exit (upper band): "CLOSE > BB_UPPER(20, 2)" (DSL syntax)
[OK] Alternative exit (middle band): "CLOSE > BB_MIDDLE(20, 2)" (more frequent exits)

STOCHASTIC (CORRECT):
[OK] Entry (oversold): "STOCH(14) < 20" (DSL syntax)
[OK] Exit (overbought): "STOCH(14) > 80" (DSL syntax)
[OK] Alternative exit (moderate): "STOCH(14) > 60" (more frequent exits)

MOVING AVERAGE CROSSOVERS (CORRECT):
[OK] Entry: "CLOSE CROSSES_ABOVE SMA(20)" (DSL syntax)
[OK] Exit: "CLOSE CROSSES_BELOW SMA(20)" (DSL syntax)

CRITICAL - ENTRY/EXIT PAIRING RULES FOR TRADE FREQUENCY:
You MUST follow these pairing rules to ensure strategies generate real trades:

1. MEAN REVERSION STRATEGIES (for ranging markets):
   - Entry: RSI(14) < 30 OR CLOSE < BB_LOWER(20, 2) OR STOCH(14) < 20
   - Exit: RSI(14) > 60 (NOT 70!) OR CLOSE > BB_MIDDLE(20, 2) (NOT BB_UPPER!) OR STOCH(14) > 60 (NOT 80!)
   - Rationale: In ranging markets, price rarely reaches extreme overbought (RSI 70+), so use moderate exits

2. MOMENTUM STRATEGIES (for trending markets):
   - Entry: CLOSE CROSSES_ABOVE SMA(20) OR MACD() CROSSES_ABOVE MACD_SIGNAL()
   - Exit: CLOSE CROSSES_BELOW SMA(20) OR MACD() CROSSES_BELOW MACD_SIGNAL()
   - Rationale: Use crossovers for clear entry/exit signals

3. VOLATILITY STRATEGIES:
   - Entry: CLOSE < BB_LOWER(20, 2)
   - Exit: CLOSE > BB_MIDDLE(20, 2) (NOT BB_UPPER!)
   - Rationale: Middle band exits are more frequent than upper band exits

4. AVOID EXTREME THRESHOLDS:
   - [X] DO NOT use RSI(14) > 70 for exits in ranging markets (too rare)
   - [X] DO NOT use STOCH(14) > 80 for exits in ranging markets (too rare)
   - [X] DO NOT use BB_UPPER for exits (too rare)
   - [OK] DO use RSI(14) > 60, STOCH(14) > 60, BB_MIDDLE for more frequent exits

5. Entry and exit conditions MUST be OPPOSITE - they should NOT overlap
6. Entry should trigger when price is LOW, exit should trigger when price is HIGH

ANTI-PATTERNS - NEVER USE THESE:
[X] NEVER use "RSI(14) < 70" for entry (too common, triggers constantly)
[X] NEVER use "RSI(14) > 30" for exit (too common, triggers constantly)
[X] NEVER use same threshold for entry and exit (e.g., both at RSI 50)
[X] NEVER use overlapping conditions (e.g., entry RSI < 70, exit RSI > 30)
[X] NEVER use natural language like "Price is above SMA_20" - Use DSL: "CLOSE > SMA(20)"
[X] NEVER use natural language like "RSI is below 30" - Use DSL: "RSI(14) < 30"
[X] NEVER use natural language like "Price crosses below Lower_Band_20" - Use DSL: "CLOSE < BB_LOWER(20, 2)"

EXAMPLE OF GOOD STRATEGY (RANGING MARKET) - DSL SYNTAX:
{{
  "name": "RSI Bollinger Mean Reversion",
  "description": "Buy when oversold at lower band, sell when price returns to middle band",
  "entry_conditions": [
    "RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2)"
  ],
  "exit_conditions": [
    "RSI(14) > 60 OR CLOSE > BB_MIDDLE(20, 2)"
  ],
  "symbols": ["SPY", "QQQ"],
  "indicators": ["RSI", "Bollinger Bands"]
}}

EXAMPLE OF GOOD STRATEGY (TRENDING MARKET) - DSL SYNTAX:
{{
  "name": "Moving Average Crossover",
  "description": "Buy when price crosses above SMA, sell when it crosses below",
  "entry_conditions": [
    "SMA(20) CROSSES_ABOVE SMA(50)"
  ],
  "exit_conditions": [
    "SMA(20) CROSSES_BELOW SMA(50)"
  ],
  "symbols": ["SPY", "QQQ"],
  "indicators": ["SMA"]
}}

CRITICAL - AVOID CONTRADICTORY CONDITIONS:
[X] BAD: Entry uses "RSI(14) < 30 AND RSI(14) > 70" (impossible!)
[X] BAD: Entry uses "CLOSE < BB_LOWER(20, 2) AND CLOSE > BB_UPPER(20, 2)" (impossible!)
[OK] GOOD: Entry uses "RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2)" (both indicate oversold)
[OK] GOOD: Entry uses "RSI(14) < 30 OR CLOSE < BB_LOWER(20, 2)" (either condition triggers)

CRITICAL - CROSSOVER DETECTION:
For detecting when one indicator crosses above/below another:
[OK] CORRECT: "MACD() CROSSES_ABOVE MACD_SIGNAL()" (bullish crossover)
[OK] CORRECT: "CLOSE CROSSES_ABOVE SMA(20)" (price breaks above moving average)
[OK] CORRECT: "CLOSE < BB_LOWER(20, 2)" (price below lower band)
[X] WRONG: "MACD() > MACD_SIGNAL()" (this is a state, not a crossover - use for non-crossover conditions)

CRITICAL - REALISTIC EXPECTATIONS:
Good strategies typically have:
- Win rate: 40-60% (not 80% or more, that is unrealistic)
- Trade frequency: 1-5 trades per month per symbol (not 50+ trades)
- Sharpe ratio: 1.0-2.0 is excellent (not 5.0 or more, that is unrealistic)
- Max drawdown: 10-20% is acceptable (not 50% or more, that is too risky)

Design your strategy to generate REALISTIC trading opportunities, not constant signals.

CRITICAL - TRADE FREQUENCY OPTIMIZATION:
To ensure strategies generate sufficient trades in 90 days:

1. USE MODERATE EXIT THRESHOLDS:
   - [OK] RSI(14) > 60 instead of RSI(14) > 70 (triggers 2 to 3 times more often)
   - [OK] STOCH(14) > 60 instead of STOCH(14) > 80 (triggers 2 to 3 times more often)
   - [OK] BB_MIDDLE instead of BB_UPPER (triggers 2 times more often)

2. USE CROSSOVER EXITS:
   - [OK] "CLOSE CROSSES_ABOVE SMA(20)" (clear exit signal)
   - [OK] "MACD() CROSSES_BELOW MACD_SIGNAL()" (clear exit signal)
   - [OK] "RSI(14) CROSSES_ABOVE 50" (mean reversion exit)

3. COMBINE CONDITIONS WITH OR (not AND):
   - [OK] "RSI(14) > 60 OR CLOSE > BB_MIDDLE(20, 2)" (either triggers exit)
   - [X] "RSI(14) > 60 AND CLOSE > BB_MIDDLE(20, 2)" (both must trigger, too rare)

4. AVOID EXTREME CONDITIONS:
   - [X] "CLOSE > RESISTANCE" (may never happen in 90 days)
   - [X] "RSI(14) > 80" (extremely rare)
   - [X] "STOCH(14) > 90" (almost never happens)

5. TEST YOUR LOGIC:
   - If entry is "RSI(14) < 30" (oversold), exit should be "RSI(14) > 60" (moderate recovery)
   - If entry is "CLOSE < BB_LOWER(20, 2)", exit should be "CLOSE > BB_MIDDLE(20, 2)" (return to mean)
   - If entry is "STOCH(14) < 20", exit should be "STOCH(14) > 60" (moderate recovery)

Create a unique strategy that:
1. Is appropriate for the current market regime
2. Uses 2-3 of the available indicators
3. Has clear entry and exit conditions using DSL SYNTAX (not natural language)
4. Follows the entry/exit pairing rules (entry at LOW conditions, exit at HIGH conditions)
5. Avoids all anti-patterns listed above
6. Avoids contradictory conditions (do not combine oversold + overbought in same condition)
7. Uses crossover detection correctly when needed
8. Includes proper risk management
9. Is different from typical momentum or mean reversion strategies (be creative)

Make this strategy distinct and innovative while following all threshold and pairing rules.'''
        
        return prompt
    
    def get_strategy_templates(self, regime: MarketRegime) -> List[Dict]:
        """
        Get strategy templates appropriate for market regime.
        
        Args:
            regime: Market regime
        
        Returns:
            List of strategy template dictionaries
        """
        templates = {
            MarketRegime.TRENDING_UP: [
                {
                    "type": "momentum",
                    "description": "Momentum strategy for uptrending markets",
                    "indicators": ["SMA", "RSI", "Volume MA"]
                },
                {
                    "type": "breakout",
                    "description": "Breakout strategy for strong trends",
                    "indicators": ["Bollinger Bands", "ATR", "Volume MA"]
                }
            ],
            MarketRegime.TRENDING_DOWN: [
                {
                    "type": "mean_reversion",
                    "description": "Mean reversion for oversold bounces",
                    "indicators": ["RSI", "Bollinger Bands", "Stochastic Oscillator"]
                },
                {
                    "type": "defensive",
                    "description": "Defensive strategy for downtrends",
                    "indicators": ["SMA", "ATR", "Support/Resistance"]
                }
            ],
            MarketRegime.RANGING: [
                {
                    "type": "mean_reversion",
                    "description": "Mean reversion for range-bound markets",
                    "indicators": ["RSI", "Bollinger Bands", "Support/Resistance"]
                },
                {
                    "type": "oscillator",
                    "description": "Oscillator-based strategy for ranges",
                    "indicators": ["Stochastic Oscillator", "RSI", "MACD"]
                }
            ]
        }
        
        return templates.get(regime, [])

    def _detect_crypto_regime(self) -> 'MarketRegime':
        """Detect market regime using BTC/ETH as benchmarks (independent of equity regime)."""
        try:
            from src.strategy.strategy_templates import MarketRegime as MR
            sub_regime, confidence, _, metrics = self.market_analyzer.detect_sub_regime(symbols=['BTC', 'ETH'])
            logger.info(
                f"Crypto regime: {sub_regime.value} (confidence: {confidence:.2f}, "
                f"20d={metrics.get('avg_change_20d', 0):.2%}, "
                f"50d={metrics.get('avg_change_50d', 0):.2%})"
            )
            return sub_regime
        except Exception as e:
            logger.warning(f"Crypto regime detection failed, using equity regime: {e}")
            return None

    def _detect_forex_regime(self) -> 'MarketRegime':
        """Detect market regime using major forex pairs (independent of equity regime)."""
        try:
            sub_regime, confidence, _, metrics = self.market_analyzer.detect_sub_regime(
                symbols=['EURUSD', 'GBPUSD', 'USDJPY']
            )
            logger.info(
                f"Forex regime: {sub_regime.value} (confidence: {confidence:.2f}, "
                f"20d={metrics.get('avg_change_20d', 0):.2%}, "
                f"50d={metrics.get('avg_change_50d', 0):.2%})"
            )
            return sub_regime
        except Exception as e:
            logger.warning(f"Forex regime detection failed, using equity regime: {e}")
            return None

    def _detect_commodity_regime(self) -> 'MarketRegime':
        """Detect market regime using major commodities (independent of equity regime)."""
        try:
            sub_regime, confidence, _, metrics = self.market_analyzer.detect_sub_regime(
                symbols=['GOLD', 'OIL', 'SILVER']
            )
            logger.info(
                f"Commodity regime: {sub_regime.value} (confidence: {confidence:.2f}, "
                f"20d={metrics.get('avg_change_20d', 0):.2%}, "
                f"50d={metrics.get('avg_change_50d', 0):.2%})"
            )
            return sub_regime
        except Exception as e:
            logger.warning(f"Commodity regime detection failed, using equity regime: {e}")
            return None

    def _filter_templates_by_macro_regime(
        self, market_regime: MarketRegime, market_context: Dict
    ) -> List:
        """
        Filter strategy templates based on current market regime and macro conditions.
        
        Uses per-asset-class regime detection: crypto templates are filtered by
        the crypto regime (BTC/ETH), not the equity regime (SPY/QQQ). This prevents
        applying equity downtrend logic to crypto that may be in a different regime.
        
        Alpha Edge templates are ALWAYS included (they have their own regime logic).
        
        Args:
            market_regime: Current market regime (trending/ranging) — equity-based
            market_context: Market context with VIX, inflation, etc.
            
        Returns:
            Filtered list of templates appropriate for current conditions
        """
        from src.strategy.strategy_templates import MarketRegime as MR

        # --- Per-asset-class regime detection ---
        # Crypto has its own market dynamics — detect independently
        crypto_regime = self._detect_crypto_regime()
        if crypto_regime is None:
            crypto_regime = market_regime  # Fallback to equity regime

        # Forex and commodities also have independent dynamics
        forex_regime = self._detect_forex_regime()
        if forex_regime is None:
            forex_regime = market_regime

        commodity_regime = self._detect_commodity_regime()
        if commodity_regime is None:
            commodity_regime = market_regime

        # Store for use by _match_templates_to_symbols (directional quotas per asset class)
        self._crypto_regime = crypto_regime
        self._forex_regime = forex_regime
        self._commodity_regime = commodity_regime
        self._equity_regime = market_regime

        def _get_templates_for_regime_with_parent(regime):
            """Get templates matching a regime, including parent regime fallback."""
            templates = self.template_library.get_templates_for_regime(regime)
            if len(templates) < 5:
                parent_regime_map = {
                    'ranging_low_vol': 'ranging',
                    'ranging_high_vol': 'ranging',
                    'trending_up_strong': 'trending_up',
                    'trending_up_weak': 'trending_up',
                    'trending_down_strong': 'trending_down',
                    'trending_down_weak': 'trending_down',
                }
                parent_regime_name = parent_regime_map.get(regime.value)
                if parent_regime_name:
                    parent_regime = MR(parent_regime_name)
                    parent_templates = self.template_library.get_templates_for_regime(parent_regime)
                    existing_names = {t.name for t in templates}
                    for pt in parent_templates:
                        if pt.name not in existing_names:
                            templates.append(pt)
            return templates

        # Get equity-regime templates (for stocks, ETFs, forex, indices, commodities).
        # Strip crypto_optimized templates from the equity pool — they score 0 on all
        # non-crypto symbols anyway (hard-blocked in _score_symbol_for_template), so
        # keeping them in the equity pool just wastes slots and causes the dedup below
        # to block them from being re-added from the crypto-regime pool.
        equity_templates_raw = _get_templates_for_regime_with_parent(market_regime)
        equity_templates = [t for t in equity_templates_raw
                           if not (t.metadata and t.metadata.get('crypto_optimized'))]

        # Get crypto-regime templates (for crypto symbols).
        # Always add crypto templates regardless of whether crypto regime matches equity —
        # crypto_optimized templates are hard-blocked from non-crypto symbols in scoring,
        # so they can only ever run on BTC/ETH. Without stripping them from the equity
        # pool above, the dedup below would block all of them when regimes match.
        crypto_templates = _get_templates_for_regime_with_parent(crypto_regime)
        crypto_only = [t for t in crypto_templates
                      if t.metadata and t.metadata.get('crypto_optimized')]
        equity_names = {t.name for t in equity_templates}
        added_crypto = 0
        for ct in crypto_only:
            if ct.name not in equity_names:
                equity_templates.append(ct)
                equity_names.add(ct.name)
                added_crypto += 1
        if crypto_regime.value != market_regime.value:
            logger.info(
                f"Multi-regime gate: equity={market_regime.value} ({len(equity_templates) - added_crypto} templates), "
                f"crypto={crypto_regime.value} ({added_crypto} crypto templates added)"
            )
        else:
            logger.info(
                f"Regime gate: {market_regime.value} (crypto matches equity, {added_crypto} crypto templates added)"
            )

        templates = equity_templates
        vix = market_context.get('vix', 20.0)
        
        logger.info(f"Regime gate: {market_regime.value} → {len(templates)} matching templates (VIX={vix:.1f})")
        
        # Separate Alpha Edge from DSL
        alpha_edge_templates = []
        dsl_templates = []
        for t in templates:
            if t.metadata and t.metadata.get('strategy_category') == 'alpha_edge':
                alpha_edge_templates.append(t)
            else:
                dsl_templates.append(t)
        
        # Force-add ALL Alpha Edge templates from the library (they self-filter by regime)
        if len(alpha_edge_templates) < 3:
            all_library = self.template_library.get_all_templates() if hasattr(self.template_library, 'get_all_templates') else []
            ae_names = {t.name for t in alpha_edge_templates}
            for t in all_library:
                if t.metadata and t.metadata.get('strategy_category') == 'alpha_edge' and t.name not in ae_names:
                    alpha_edge_templates.append(t)
                    ae_names.add(t.name)
        
        # VIX risk-off: additionally exclude momentum/breakout from DSL set
        if vix > 30:
            before = len(dsl_templates)
            dsl_templates = [
                t for t in dsl_templates
                if t.strategy_type not in ['momentum', 'breakout', 'trend_following']
            ]
            excluded = before - len(dsl_templates)
            if excluded:
                logger.info(f"VIX risk-off ({vix:.1f}): excluded {excluded} momentum/breakout templates")

        # Regime-directional filter: in trending_up regimes, suppress generic SHORT-direction
        # templates that are NOT designed for uptrends (they generate 0 trades, waste proposal
        # slots, and accumulate in the zero-trade blacklist).
        #
        # CRITICAL EXEMPTION: templates whose market_regimes explicitly include a trending_up
        # variant are uptrend-specific shorts (exhaustion, parabolic, BB squeeze, EMA rejection,
        # MACD divergence, volume climax). These are the HEDGE — they wait for the correction
        # inside an uptrend. Suppressing them defeats their entire purpose and leaves the book
        # with zero short equity exposure going into corrections.
        trending_up_regimes = {
            'trending_up', 'trending_up_weak', 'trending_up_strong'
        }
        regime_str = market_regime.value if hasattr(market_regime, 'value') else str(market_regime)
        if regime_str in trending_up_regimes:
            before = len(dsl_templates)
            suppressed = []
            kept_uptrend_shorts = []
            for t in dsl_templates:
                meta = t.metadata or {}
                is_short = meta.get('direction', '').lower() == 'short'
                is_neutral = meta.get('market_neutral', False)
                is_ae = meta.get('strategy_category', '') == 'alpha_edge'
                # Check if this template explicitly targets trending_up regimes
                template_regimes = getattr(t, 'market_regimes', None) or []
                targets_uptrend = any(
                    (r.value if hasattr(r, 'value') else str(r)) in trending_up_regimes
                    for r in template_regimes
                )
                if is_short and not is_neutral and not is_ae and not targets_uptrend:
                    suppressed.append(t)
                else:
                    if is_short and targets_uptrend:
                        kept_uptrend_shorts.append(t.name)
                    dsl_templates  # keep — handled below via list comprehension

            dsl_templates = [
                t for t in dsl_templates
                if not (
                    (t.metadata or {}).get('direction', '').lower() == 'short'
                    and not (t.metadata or {}).get('market_neutral', False)
                    and (t.metadata or {}).get('strategy_category', '') != 'alpha_edge'
                    and not any(
                        (r.value if hasattr(r, 'value') else str(r)) in trending_up_regimes
                        for r in (getattr(t, 'market_regimes', None) or [])
                    )
                )
            ]
            excluded = before - len(dsl_templates)
            if excluded:
                logger.info(
                    f"Regime filter ({regime_str}): suppressed {excluded} generic SHORT templates "
                    f"(not designed for uptrends)"
                )
            if kept_uptrend_shorts:
                logger.info(
                    f"Regime filter ({regime_str}): kept {len(kept_uptrend_shorts)} uptrend-specific "
                    f"SHORT templates (exhaustion/reversal hedges): {kept_uptrend_shorts}"
                )
        
        filtered = dsl_templates + alpha_edge_templates
        
        if not filtered:
            logger.warning("No templates after regime gate, falling back to all regime-matched + AE")
            filtered = templates + alpha_edge_templates
        
        # Log summary by type
        from collections import Counter
        type_counts = Counter(
            (t.metadata or {}).get('strategy_category', t.strategy_type.value if hasattr(t.strategy_type, 'value') else str(t.strategy_type))
            for t in filtered
        )
        logger.info(f"Template selection: {len(filtered)} total — {dict(type_counts)}")
        
        return filtered
    
    def _adjust_strategy_count_by_macro(self, count: int, market_context: Dict) -> int:
        """
        Adjust number of strategies to generate based on macro regime.
        
        Args:
            count: Requested strategy count
            market_context: Market context with VIX, etc.
            
        Returns:
            Adjusted strategy count
        """
        vix = market_context.get('vix', 20.0)
        
        # Risk-Off (VIX > 30): Reduce strategy count
        if vix > 30:
            adjusted = max(2, count - 1)  # Reduce by 1, minimum 2
            logger.info(f"Reducing strategy count {count} → {adjusted} (VIX={vix:.1f}, risk-off)")
            return adjusted
        
        # Risk-On (VIX < 15): Increase strategy count
        elif vix < 15:
            adjusted = count + 1  # Increase by 1
            logger.info(f"Increasing strategy count {count} → {adjusted} (VIX={vix:.1f}, risk-on)")
            return adjusted
        
        # Normal conditions
        else:
            return count

    def apply_performance_feedback(
        self,
        feedback: Dict[str, Any],
        max_weight: float = 1.5,
        min_weight: float = 0.4,
    ) -> None:
        """Apply performance feedback from the trade journal to adjust future proposals.

        Dynamic template weighting that:
        - Aggressively penalizes consistently losing templates (down to 0.4x)
        - Moderately boosts winning templates (up to 1.5x)
        - Uses P&L-weighted scoring, not just win rate
        - Applies time-decay so stale feedback fades (templates can recover)
        - Regime-specific: a template losing in ranging_low_vol might win in trending_up

        Args:
            feedback: Output of ``TradeJournal.get_performance_feedback()``.
            max_weight: Maximum multiplier for winning templates (default 1.5).
            min_weight: Minimum multiplier for losing templates (default 0.4).
        """
        # Load config overrides
        try:
            import yaml
            from pathlib import Path
            config_path = Path("config/autonomous_trading.yaml")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    pf_config = config.get('performance_feedback', {})
                    max_weight = pf_config.get('max_weight_adjustment', max_weight)
                    min_weight = pf_config.get('min_weight_adjustment', min_weight)
        except Exception:
            pass

        if not feedback or not feedback.get("has_sufficient_data"):
            logger.info("Performance feedback: insufficient data, using default weights")
            self._template_weights = {}
            self._symbol_scores = {}
            self._regime_template_preferences = {}
            return

        # --- Template weights ---
        # Dynamic weighting based on BOTH win rate AND average P&L.
        # A template with 60% win rate but tiny winners and big losers
        # should still be penalized. Conversely, a 35% win rate template
        # with huge winners (trend following) should be boosted.
        template_perf = feedback.get("template_performance", {})
        template_weights: Dict[str, float] = {}
        if template_perf:
            # Calculate expectancy-based weight for each template
            for ttype, metrics in template_perf.items():
                wr = metrics.get("win_rate", 50.0)
                total_pnl = metrics.get("total_pnl", 0.0)
                total_trades = metrics.get("total_trades", 1)
                avg_pnl_per_trade = total_pnl / max(total_trades, 1)

                # Composite score: blend win rate deviation with P&L signal
                # Win rate component: 50% → 1.0, 70% → 1.4, 30% → 0.6
                wr_component = 1.0 + (wr - 50.0) / 50.0

                # P&L component: positive avg P&L → boost, negative → penalize
                # Scale: $50 avg profit → 1.1x, -$50 avg loss → 0.9x
                pnl_component = 1.0 + max(-0.5, min(0.5, avg_pnl_per_trade / 100.0))

                # Blend: 60% win rate signal, 40% P&L signal
                raw_weight = wr_component * 0.6 + pnl_component * 0.4

                # Confidence scaling: more trades → more trust in the signal
                # 5 trades → 50% confidence, 10 → 75%, 20+ → 100%
                confidence = min(1.0, total_trades / 20.0)
                # Blend toward 1.0 (neutral) when confidence is low
                weight = 1.0 + (raw_weight - 1.0) * confidence

                weight = max(min_weight, min(max_weight, weight))
                template_weights[ttype] = weight

            logger.info(
                f"Performance feedback template weights (dynamic): "
                + ", ".join(f"{k}={v:.2f}" for k, v in sorted(template_weights.items(), key=lambda x: -x[1]))
            )

        self._template_weights = template_weights

        # --- Symbol preference scores ---
        # More aggressive: use P&L-weighted scoring with confidence scaling
        symbol_perf = feedback.get("symbol_performance", {})
        symbol_scores: Dict[str, float] = {}
        if symbol_perf:
            for sym, metrics in symbol_perf.items():
                avg_ret = metrics.get("avg_return_pct", 0.0)
                wr = metrics.get("win_rate", 50.0)
                total_trades = metrics.get("total_trades", 1)
                total_pnl = metrics.get("total_pnl", 0.0)

                # Combined score: win rate deviation + P&L signal
                score = (wr - 50.0) * 0.5 + avg_ret * 10.0

                # P&L bonus/penalty: big winners get extra boost
                if total_pnl > 0:
                    score += min(10.0, total_pnl / 50.0)
                else:
                    score += max(-10.0, total_pnl / 50.0)

                # Confidence scaling
                confidence = min(1.0, total_trades / 15.0)
                score *= confidence

                # Cap at ±15 (was ±8, more aggressive now)
                symbol_scores[sym] = max(-15.0, min(15.0, score))

            # Log top/bottom 5
            sorted_syms = sorted(symbol_scores.items(), key=lambda x: -x[1])
            if sorted_syms:
                top = sorted_syms[:5]
                bottom = sorted_syms[-5:]
                logger.info(
                    f"Performance feedback top symbols: "
                    + ", ".join(f"{s}={sc:.1f}" for s, sc in top)
                )
                logger.info(
                    f"Performance feedback bottom symbols: "
                    + ", ".join(f"{s}={sc:.1f}" for s, sc in bottom)
                )

        self._symbol_scores = symbol_scores

        # --- Regime-specific template preferences ---
        regime_perf = feedback.get("regime_performance", {})
        regime_prefs: Dict[str, Dict[str, float]] = {}
        if regime_perf:
            for regime, metrics in regime_perf.items():
                best = metrics.get("best_template_win_rates", {})
                if best:
                    regime_prefs[regime] = best
                    logger.info(
                        f"Performance feedback regime '{regime}' best templates: "
                        + ", ".join(f"{k}={v:.0f}%" for k, v in sorted(best.items(), key=lambda x: -x[1]))
                    )

        self._regime_template_preferences = regime_prefs

        logger.info(
            f"Performance feedback applied: {len(template_weights)} template weights, "
            f"{len(symbol_scores)} symbol scores, {len(regime_prefs)} regime preferences"
        )

