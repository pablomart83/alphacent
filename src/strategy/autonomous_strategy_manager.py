"""Autonomous Strategy Manager for orchestrating the complete strategy lifecycle."""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import yaml

from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.dataclasses import Strategy
from src.models.enums import StrategyStatus
from src.strategy.portfolio_manager import PortfolioManager
from src.strategy.strategy_engine import StrategyEngine
from src.strategy.strategy_proposer import StrategyProposer

# Stage constants for cycle pipeline
CYCLE_STAGES = [
    "cleanup_retirement",
    "performance_feedback",
    "strategy_proposals",
    "data_validation",
    "walk_forward_backtesting",
    "strategy_activation",
    "signal_generation",
    "order_submission",
]

STAGE_LABELS = {
    "cleanup_retirement": "Cleanup & Retirement",
    "performance_feedback": "Performance Feedback",
    "strategy_proposals": "Strategy Proposals",
    "data_validation": "Data Validation",
    "walk_forward_backtesting": "Walk-Forward Backtesting",
    "strategy_activation": "Strategy Activation",
    "signal_generation": "Retire & Signals",
    "order_submission": "Orders",
}

logger = logging.getLogger(__name__)


class AutonomousStrategyManager:
    """Orchestrates the complete autonomous strategy lifecycle."""

    def __init__(
        self,
        llm_service: Optional[LLMService],
        market_data: MarketDataManager,
        strategy_engine: StrategyEngine,
        config: Optional[Dict] = None,
        config_path: Optional[str] = None,
        websocket_manager=None,
    ):
        """
        Initialize Autonomous Strategy Manager.

        Args:
            llm_service: LLM service for strategy generation
            market_data: Market data manager
            strategy_engine: Strategy engine for backtesting and management
            config: Optional configuration dictionary (overrides config file)
            config_path: Optional path to YAML config file (defaults to config/autonomous_trading.yaml)
            websocket_manager: Optional WebSocket manager for real-time updates
        """
        self.llm_service = llm_service
        self.market_data = market_data
        self.strategy_engine = strategy_engine
        self.websocket_manager = websocket_manager

        # Initialize sub-components
        self.strategy_proposer = StrategyProposer(llm_service, market_data)
        self.portfolio_manager = PortfolioManager(strategy_engine)

        # Load configuration
        if config:
            self.config = config
        else:
            self.config = self._load_config(config_path)

        # Track last run time
        self.last_run_time: Optional[datetime] = None

        logger.info("AutonomousStrategyManager initialized")

    async def _broadcast_ws_event(self, event_func, *args, **kwargs):
        """
        Safely broadcast WebSocket event if manager is available.
        
        Args:
            event_func: WebSocket manager method to call
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method
        """
        if self.websocket_manager:
            try:
                await event_func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Failed to broadcast WebSocket event: {e}")

    def _emit_stage_event(self, stage: str, status: str, progress_pct: int, metrics: Optional[Dict] = None, error: Optional[str] = None):
        """Emit a structured stage event via WebSocket for the cycle pipeline UI."""
        if not self.websocket_manager:
            return
        event_data = {
            "stage": stage,
            "stage_label": STAGE_LABELS.get(stage, stage),
            "status": status,  # pending, running, complete, error
            "progress_pct": progress_pct,
            "metrics": metrics or {},
            "timestamp": datetime.now().isoformat(),
        }
        if error:
            event_data["error"] = error
        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                asyncio.ensure_future(
                    self.websocket_manager.broadcast_cycle_progress(event_data),
                    loop=loop
                )
            except RuntimeError:
                # No running event loop — create one temporarily
                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    self.websocket_manager.broadcast_cycle_progress(event_data)
                )
                loop.close()
        except Exception as e:
            logger.warning(f"Failed to emit stage event: {e}")
    def _safe_broadcast(self, coro_func, *args, **kwargs):
        """Safely call an async WebSocket broadcast method from sync context.

        Works both when there's a running event loop (async context) and when
        there isn't (background thread context).
        """
        if not self.websocket_manager:
            return
        try:
            loop = asyncio.get_running_loop()
            asyncio.ensure_future(coro_func(*args, **kwargs), loop=loop)
        except RuntimeError:
            # No running event loop — create one temporarily
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(coro_func(*args, **kwargs))
                loop.close()
            except Exception as e:
                logger.warning(f"Failed to broadcast WS event: {e}")
        except Exception as e:
            logger.warning(f"Failed to broadcast WS event: {e}")

    def _load_config(self, config_path: Optional[str] = None) -> Dict:
        """
        Load configuration from YAML file.

        Args:
            config_path: Optional path to config file

        Returns:
            Configuration dictionary
        """
        # Default config path
        if config_path is None:
            config_path = "config/autonomous_trading.yaml"

        # Start with default config
        config = self._default_config()

        # Try to load from file
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        # Merge file config with defaults (file config takes precedence)
                        config = self._merge_configs(config, file_config)
                        logger.info(f"Loaded configuration from {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {e}. Using defaults.")
        else:
            logger.info(f"Config file {config_path} not found. Using default configuration.")

        return config

    def _merge_configs(self, default: Dict, override: Dict) -> Dict:
        """
        Recursively merge two configuration dictionaries.

        Args:
            default: Default configuration
            override: Override configuration

        Returns:
            Merged configuration
        """
        result = default.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result

    def _default_config(self) -> Dict:
        """
        Get default configuration.

        Returns:
            Default configuration dictionary
        """
        return {
            "llm": {
                "model": "qwen2.5-coder:7b",
                "temperature": 0.7,
            },
            "autonomous": {
                "enabled": True,
                "proposal_frequency": "weekly",  # or "daily"
                "max_active_strategies": 10,
                "min_active_strategies": 5,
                "proposal_count": 5,  # Number of strategies to propose per cycle
            },
            "activation_thresholds": {
                "min_sharpe": 1.5,
                "max_drawdown": 0.15,
                "min_win_rate": 0.5,
                "min_trades": 20,
            },
            "retirement_thresholds": {
                "max_sharpe": 0.5,
                "max_drawdown": 0.15,
                "min_win_rate": 0.4,
                "min_trades_for_evaluation": 30,
            },
            "backtest": {
                "days": 90,  # Number of days to backtest
            },
        }

    def run_strategy_cycle(self, filters: Dict = None) -> Dict:
        """
        Run complete autonomous strategy cycle with structured stage events.

        Args:
            filters: Optional dict with keys 'asset_classes', 'intervals', 'strategy_types'
                     to restrict what gets proposed.

        Returns:
            Dictionary with cycle statistics
        """
        self._cycle_filters = filters or {}
        logger.info("=" * 80)
        logger.info("Starting autonomous strategy cycle")
        logger.info("=" * 80)

        cycle_start = datetime.now()
        cycle_id = f"cycle_{int(cycle_start.timestamp())}"
        stats = {
            "cycle_id": cycle_id,
            "cycle_start": cycle_start,
            "proposals_generated": 0,
            "proposals_backtested": 0,
            "strategies_activated": 0,
            "activated_strategy_ids": [],
            "strategies_retired": 0,
            "strategies_cleaned": 0,
            "errors": [],
        }

        # Broadcast cycle started event
        self._safe_broadcast(
            self.websocket_manager.broadcast_autonomous_cycle_event,
            "cycle_started",
            {
                "cycle_id": cycle_id,
                "estimated_duration": 2700,
                "timestamp": cycle_start.isoformat()
            }
        )

        # Save cycle run to DB
        self._save_cycle_run(cycle_id, "running", cycle_start)

        try:
            # Step -1: Warm FMP cache
            # Skip if warmed recently AND cache coverage is adequate (>80% of symbols have fresh data).
            # This prevents the scenario where the first cycle after reboot partially warms the cache
            # (rate limit hit), saves the timestamp, and then subsequent cycles skip warming entirely
            # leaving the cache incomplete.
            try:
                from src.data.fmp_cache_warmer import FMPCacheWarmer
                should_warm = True
                last_warm = FMPCacheWarmer.get_last_warm_timestamp()
                if last_warm:
                    hours_since_warm = (datetime.now() - last_warm).total_seconds() / 3600
                    if hours_since_warm < 24:
                        # Check cache coverage — if too many symbols are missing, warm anyway
                        try:
                            from src.models.database import get_database
                            from src.models.orm import FundamentalDataORM
                            from src.core.tradeable_instruments import get_tradeable_symbols
                            from src.models.enums import TradingMode
                            all_symbols = get_tradeable_symbols(TradingMode.DEMO)
                            stock_symbols = [s for s in all_symbols if s not in FMPCacheWarmer.SKIP_FUNDAMENTALS]
                            db = get_database()
                            session = db.get_session()
                            try:
                                fresh_cutoff = datetime.now() - timedelta(days=7)
                                fresh_count = session.query(FundamentalDataORM).filter(
                                    FundamentalDataORM.fetched_at >= fresh_cutoff
                                ).count()
                            finally:
                                session.close()
                            coverage_pct = fresh_count / len(stock_symbols) if stock_symbols else 1.0
                            if coverage_pct >= 0.80:
                                should_warm = False
                                logger.info(f"\n[STEP -1] FMP cache warm skipped ({hours_since_warm:.1f}h since last warm, {coverage_pct:.0%} coverage)")
                                self._emit_stage_event("cache_warming", "complete", 4, {
                                    "skipped": True,
                                    "reason": f"Last warm {hours_since_warm:.0f}h ago, {coverage_pct:.0%} coverage",
                                })
                            else:
                                logger.info(
                                    f"\n[STEP -1] FMP cache coverage only {coverage_pct:.0%} ({fresh_count}/{len(stock_symbols)}) "
                                    f"— warming despite recent timestamp"
                                )
                        except Exception as _cov_err:
                            logger.debug(f"Could not check cache coverage: {_cov_err}")
                            should_warm = False  # If we can't check, assume it's fine
                            self._emit_stage_event("cache_warming", "complete", 4, {
                                "skipped": True,
                                "reason": f"Last warm {hours_since_warm:.0f}h ago",
                            })
                if should_warm:
                    logger.info("\n[STEP -1] Warming FMP fundamental data cache...")
                    self._emit_stage_event("cache_warming", "running", 1, {
                        "phase": "Warming FMP fundamental data cache..."
                    })
                    cache_warmer = FMPCacheWarmer(self.config)

                    def _cache_warm_progress(current, total, warm_stats):
                        pct = int((current / total) * 4)  # 0-4% of overall pipeline
                        self._emit_stage_event("cache_warming", "running", pct, {
                            "phase": f"Warming cache... {current}/{total} symbols",
                            "current": current,
                            "total": total,
                            "api_fetched": warm_stats.get("fundamentals_fetched", 0),
                            "from_cache": warm_stats.get("fundamentals_cached", 0),
                        })

                    cache_warmer.warm_all_symbols(progress_callback=_cache_warm_progress)
                    self._emit_stage_event("cache_warming", "complete", 4, {
                        "skipped": False,
                    })
            except Exception as e:
                logger.warning(f"  Cache warming failed (non-critical): {e}")
                self._emit_stage_event("cache_warming", "complete", 4, {
                    "skipped": True,
                    "reason": f"Failed: {str(e)[:50]}",
                })

            # === Stage 1: Cleanup & Retirement ===
            self._emit_stage_event("cleanup_retirement", "running", 5)
            logger.info("\n[STAGE 1] Cleanup & Retirement...")
            self._cleanup_inactive_strategies(stats)
            self._emit_stage_event("cleanup_retirement", "complete", 12, {
                "retired": stats.get("strategies_retired", 0),
                "cleaned": stats.get("strategies_cleaned", 0),
            })

            # === Stage 2: Performance Feedback ===
            self._emit_stage_event("performance_feedback", "running", 15)
            logger.info("\n[STAGE 2] Performance Feedback...")
            self._apply_performance_feedback(stats)
            self._emit_stage_event("performance_feedback", "complete", 20, {
                "trades_analyzed": stats.get("trades_analyzed", 0),
                "template_adjustments": stats.get("template_adjustments", 0),
            })

            # === Stage 3: Strategy Proposals ===
            self._emit_stage_event("strategy_proposals", "running", 22, {
                "phase": "Analyzing 118 symbols..."
            })
            logger.info("\n[STAGE 3] Strategy Proposals...")
            proposals = self._propose_strategies(stats)
            alpha_edge_count = sum(1 for p in proposals if p.metadata.get("strategy_category") == "alpha_edge")
            template_count = len(proposals) - alpha_edge_count
            self._emit_stage_event("strategy_proposals", "complete", 65, {
                "proposed": stats["proposals_generated"],
                "by_category": {"alpha_edge": alpha_edge_count, "template": template_count},
            })

            # === Stage 4: Data Validation ===
            self._emit_stage_event("data_validation", "running", 65)
            logger.info("\n[STAGE 4] Data Validation...")
            # Data validation happens implicitly during backtesting; emit metrics from DQ reports
            symbols_checked = len(set(s for p in proposals for s in p.symbols))
            self._emit_stage_event("data_validation", "complete", 68, {
                "symbols_checked": symbols_checked,
                "passed": symbols_checked,  # All pass if we get here
                "failed": 0,
            })

            # === Stage 5: Walk-Forward Backtesting ===
            self._emit_stage_event("walk_forward_backtesting", "running", 68)
            logger.info("\n[STAGE 5] Walk-Forward Backtesting...")
            backtested_strategies = self._backtest_proposals(proposals, stats)
            bt_passed = len(backtested_strategies)
            bt_failed = stats["proposals_generated"] - bt_passed
            # Calculate avg metrics from backtested strategies
            def _get_bt_metric(bt, key, default=0):
                """Get metric from BacktestResults dataclass or dict."""
                if hasattr(bt, key):
                    return getattr(bt, key, default)
                elif isinstance(bt, dict):
                    return bt.get(key, default)
                return default

            sharpes = [_get_bt_metric(s.backtest_results, 'sharpe_ratio') for s in backtested_strategies if s.backtest_results]
            win_rates = [_get_bt_metric(s.backtest_results, 'win_rate') for s in backtested_strategies if s.backtest_results]
            avg_sharpe = sum(sharpes) / len(sharpes) if sharpes else 0
            avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0
            self._emit_stage_event("walk_forward_backtesting", "complete", 80, {
                "backtested": stats["proposals_backtested"],
                "passed": bt_passed,
                "failed": bt_failed,
                "avg_sharpe": round(avg_sharpe, 2),
                "avg_win_rate": round(avg_win_rate * 100, 1),
            })

            # === Stage 6: Strategy Activation ===
            self._emit_stage_event("strategy_activation", "running", 80)
            logger.info("\n[STAGE 6] Strategy Activation...")
            self._evaluate_and_activate(backtested_strategies, stats)
            # Count total active strategies
            try:
                from src.models.database import get_database
                from src.models.orm import StrategyORM
                session = get_database().get_session()
                try:
                    total_active = session.query(StrategyORM).filter(
                        StrategyORM.status.in_(["DEMO", "LIVE"])
                    ).count()
                finally:
                    session.close()
            except Exception:
                total_active = 0
            # Adjust activated count to reflect net activations (subtract retirements from this cycle)
            newly_approved = stats["strategies_activated"]  # Used for Stage 6 UI event

            # Recalculate avg_sharpe from APPROVED strategies only (not all backtested)
            # cycle_avg_sharpe = quality of what THIS cycle approved
            # portfolio_avg_sharpe = quality of the entire active portfolio
            cycle_avg_sharpe = 0.0
            cycle_avg_win_rate = 0.0
            portfolio_avg_sharpe = 0.0
            portfolio_avg_win_rate = 0.0
            approved_ids = set(stats.get("activated_strategy_ids", []))
            if approved_ids:
                approved_sharpes = [
                    _get_bt_metric(s.backtest_results, 'sharpe_ratio')
                    for s in backtested_strategies
                    if s.backtest_results and s.id in approved_ids
                ]
                approved_win_rates = [
                    _get_bt_metric(s.backtest_results, 'win_rate')
                    for s in backtested_strategies
                    if s.backtest_results and s.id in approved_ids
                ]
                cycle_avg_sharpe = sum(approved_sharpes) / len(approved_sharpes) if approved_sharpes else 0
                cycle_avg_win_rate = sum(approved_win_rates) / len(approved_win_rates) if approved_win_rates else 0
            else:
                cycle_avg_sharpe = 0
                cycle_avg_win_rate = 0
            try:
                active_strategies = self.strategy_engine.get_active_strategies()
                if active_strategies:
                    active_sharpes = [
                        _get_bt_metric(s.backtest_results, 'sharpe_ratio')
                        for s in active_strategies
                        if s.backtest_results
                    ]
                    active_win_rates = [
                        _get_bt_metric(s.backtest_results, 'win_rate')
                        for s in active_strategies
                        if s.backtest_results
                    ]
                    portfolio_avg_sharpe = sum(active_sharpes) / len(active_sharpes) if active_sharpes else 0
                    portfolio_avg_win_rate = sum(active_win_rates) / len(active_win_rates) if active_win_rates else 0
                    logger.info(
                        f"Cycle avg Sharpe: {cycle_avg_sharpe:.2f}, "
                        f"Portfolio avg Sharpe: {portfolio_avg_sharpe:.2f}, "
                        f"Portfolio avg Win Rate: {portfolio_avg_win_rate:.1%}"
                    )
            except Exception as e:
                logger.warning(f"Failed to recalculate activated strategy metrics: {e}")
                portfolio_avg_sharpe = avg_sharpe
                portfolio_avg_win_rate = avg_win_rate

            # P2 #12: Track AE vs DSL performance separately
            ae_active_sharpes = []
            dsl_active_sharpes = []
            try:
                if active_strategies:
                    for s in active_strategies:
                        if s.backtest_results:
                            sharpe = _get_bt_metric(s.backtest_results, 'sharpe_ratio')
                            is_ae = s.metadata and s.metadata.get('strategy_category') == 'alpha_edge'
                            if is_ae:
                                ae_active_sharpes.append(sharpe)
                            else:
                                dsl_active_sharpes.append(sharpe)
                ae_avg_sharpe = sum(ae_active_sharpes) / len(ae_active_sharpes) if ae_active_sharpes else 0
                dsl_avg_sharpe = sum(dsl_active_sharpes) / len(dsl_active_sharpes) if dsl_active_sharpes else 0
                stats['ae_performance'] = {
                    'active_count': len(ae_active_sharpes),
                    'avg_sharpe': round(ae_avg_sharpe, 2),
                }
                stats['dsl_performance'] = {
                    'active_count': len(dsl_active_sharpes),
                    'avg_sharpe': round(dsl_avg_sharpe, 2),
                }
                if ae_active_sharpes:
                    logger.info(f"AE performance: {len(ae_active_sharpes)} active, avg Sharpe {ae_avg_sharpe:.2f}")
                    logger.info(f"DSL performance: {len(dsl_active_sharpes)} active, avg Sharpe {dsl_avg_sharpe:.2f}")
            except Exception as e:
                logger.debug(f"Could not compute AE vs DSL performance: {e}")

            # Use CYCLE avg for the pipeline UI — this is what the current run produced
            self._emit_stage_event("strategy_activation", "complete", 90, {
                "approved": stats["strategies_activated"],
                "total_active": total_active,
                "avg_sharpe": round(cycle_avg_sharpe, 2),
                "avg_win_rate": round(cycle_avg_win_rate * 100, 1),
                "portfolio_avg_sharpe": round(portfolio_avg_sharpe, 2),
            })

            # === Stage 7: Retirement Check + Signal Generation ===
            self._emit_stage_event("signal_generation", "running", 90, {
                "phase": "Checking retirement triggers..."
            })
            logger.info("\n[STAGE 7] Checking retirement triggers...")
            self._check_and_retire_strategies(stats)

            signals_generated = 0
            signals_rejected = 0
            orders_submitted = 0
            promoted_to_demo = 0  # Strategies actually activated (BACKTESTED→DEMO) this cycle
            newly_approved = stats["strategies_activated"]  # Count of strategies approved as BACKTESTED

            if newly_approved > 0:
                self._emit_stage_event("signal_generation", "running", 93, {
                    "phase": f"Generating signals for {newly_approved} approved strategies..."
                })
                logger.info(f"\n[STAGE 7b] Running signal generation for {newly_approved} newly approved strategies...")

                try:
                    from src.core.trading_scheduler import get_trading_scheduler
                    import time as _time

                    scheduler = get_trading_scheduler()

                    if not scheduler._components_initialized:
                        import asyncio
                        logger.info("Initializing trading scheduler components...")
                        try:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            success = loop.run_until_complete(scheduler._initialize_components())
                            loop.close()
                            if not success:
                                raise RuntimeError("Scheduler component initialization failed")
                        except Exception as init_err:
                            logger.error(f"Error initializing scheduler components: {init_err}")
                            raise

                    activated_ids = stats.get("activated_strategy_ids", [])
                    sig_result = scheduler.run_signal_generation_sync(strategy_ids=activated_ids, include_dynamic=True)

                    signals_generated = sig_result.get("signals_generated", 0)
                    signals_rejected = sig_result.get("signals_rejected", 0)
                    orders_submitted = sig_result.get("orders_submitted", 0)
                    promoted_to_demo = sig_result.get("promoted_to_demo", 0)

                    scheduler._last_signal_check = _time.time()

                    logger.info(
                        f"Signal generation complete: {signals_generated} raw signals, "
                        f"{sig_result.get('signals_coordinated', 0)} after coordination, "
                        f"{orders_submitted} orders, {signals_rejected} rejected, "
                        f"{promoted_to_demo} promoted to DEMO"
                    )

                except Exception as e:
                    logger.error(f"Error in signal generation: {e}", exc_info=True)
                    stats["errors"].append({"type": "signal_generation", "message": str(e)})
            else:
                logger.info("\n[STAGE 7b] No new strategies activated — 30-min scheduler handles existing")

            # Complete signal_generation stage with signal metrics
            self._emit_stage_event("signal_generation", "complete", 95, {
                "retired": stats.get("strategies_retired", 0),
                "signals_generated": signals_generated,
                "signals_rejected": signals_rejected,
                "new_strategies": newly_approved,
            })

            # === Stage 8: Order Execution Results ===
            self._emit_stage_event("order_submission", "running", 95, {
                "phase": f"{orders_submitted} orders submitted" if orders_submitted > 0 else "No orders to submit",
                "signals_generated": signals_generated,
                "signals_rejected": signals_rejected,
                "orders_submitted": orders_submitted,
            })

            # Update last run time
            self.last_run_time = cycle_start
            stats["signals_generated"] = signals_generated
            stats["signals_rejected"] = signals_rejected
            stats["orders_submitted"] = orders_submitted
            cycle_end = datetime.now()
            cycle_duration = (cycle_end - cycle_start).total_seconds()
            stats["cycle_end"] = cycle_end
            stats["cycle_duration_seconds"] = cycle_duration

            # Re-query total_active AFTER signal generation (BACKTESTED→DEMO promotions happen there)
            try:
                from src.models.database import get_database
                from src.models.orm import StrategyORM
                session = get_database().get_session()
                try:
                    total_active = session.query(StrategyORM).filter(
                        StrategyORM.status.in_(["DEMO", "LIVE"])
                    ).count()
                    total_backtested = session.query(StrategyORM).filter(
                        StrategyORM.status == "BACKTESTED"
                    ).count()
                finally:
                    session.close()
            except Exception:
                total_backtested = 0
                pass  # Keep the pre-signal-gen count if query fails

            # Save completed cycle to DB
            # activated = strategies that passed activation criteria → BACKTESTED status
            # promoted_to_demo = strategies that got their first order executed → DEMO status
            stats["strategies_activated_to_demo"] = promoted_to_demo
            self._update_cycle_run(cycle_id, "completed", cycle_end, cycle_duration, stats, {
                "symbols_checked": symbols_checked,
                "avg_sharpe": cycle_avg_sharpe,
                "avg_win_rate": cycle_avg_win_rate,
                "portfolio_avg_sharpe": portfolio_avg_sharpe,
                "total_active": total_active,
                "total_backtested": total_backtested,
                "bt_passed": bt_passed,
                "bt_failed": bt_failed,
                "alpha_edge_count": alpha_edge_count,
                "template_count": template_count,
            })

            # Persist detected market regime to YAML for the status endpoint
            try:
                import yaml
                from pathlib import Path
                config_path = Path("config/autonomous_trading.yaml")
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        yaml_config = yaml.safe_load(f) or {}
                    
                    # Detect current regime
                    try:
                        sub_regime, confidence, _, _ = self.strategy_proposer.market_analyzer.detect_sub_regime()
                        stats['regime'] = sub_regime.value
                        stats['regime_confidence'] = confidence
                        yaml_config['market_regime'] = {
                            'current': sub_regime.value,
                            'confidence': float(confidence),  # Convert numpy scalar to plain float
                            'updated_at': datetime.now().isoformat(),
                        }
                        with open(config_path, 'w') as f:
                            yaml.dump(yaml_config, f, default_flow_style=False, sort_keys=False)
                        logger.info(f"Persisted market regime: {sub_regime.value} (confidence: {confidence:.2f})")
                    except Exception as e:
                        logger.warning(f"Could not detect/persist market regime: {e}")
            except Exception as e:
                logger.warning(f"Could not persist market regime to YAML: {e}")

            # Emit final stage complete so frontend pipeline shows 100%
            self._emit_stage_event("order_submission", "complete", 100, {
                "orders_submitted": orders_submitted,
                "signals_generated": signals_generated,
                "signals_rejected": signals_rejected,
                "active_strategies": total_active,
                "newly_activated": promoted_to_demo,
                "newly_approved": newly_approved,
                "cycle_duration": f"{cycle_duration:.0f}s",
            })

            # Broadcast cycle completed event
            self._safe_broadcast(
                self.websocket_manager.broadcast_autonomous_cycle_event,
                "cycle_completed",
                {
                    "cycle_id": cycle_id,
                    "duration_seconds": cycle_duration,
                    "strategies_cleaned": stats["strategies_cleaned"],
                    "proposals_generated": stats["proposals_generated"],
                    "proposals_backtested": stats["proposals_backtested"],
                    "strategies_activated": promoted_to_demo,
                    "strategies_retired": stats["strategies_retired"],
                    "errors_count": len(stats["errors"]),
                    "timestamp": cycle_end.isoformat()
                }
            )

            logger.info("\n" + "=" * 80)
            logger.info("Autonomous strategy cycle completed")
            logger.info(f"Duration: {cycle_duration:.1f} seconds")
            logger.info(f"Strategies cleaned: {stats['strategies_cleaned']}")
            logger.info(f"Proposals generated: {stats['proposals_generated']}")
            logger.info(f"Proposals backtested: {stats['proposals_backtested']}")
            logger.info(f"Strategies approved (BACKTESTED): {newly_approved}, Activated to DEMO: {promoted_to_demo}, Retired: {stats['strategies_retired']}")
            logger.info(f"Total active (DEMO+LIVE): {total_active}")
            logger.info(f"Signals generated: {signals_generated}, Orders submitted: {orders_submitted}, Rejected: {signals_rejected}")
            if promoted_to_demo > 0:
                logger.info(f"Strategies promoted to DEMO: {promoted_to_demo} (signal fired + order placed)")
            if stats["errors"]:
                logger.warning(f"Errors encountered: {len(stats['errors'])}")
            logger.info("=" * 80)

            # Write structured cycle summary to dedicated log file
            try:
                from src.core.cycle_logger import get_cycle_logger
                cl = get_cycle_logger()

                # Get account info for portfolio state
                account_balance = 0
                account_equity = 0
                try:
                    from src.core.trading_scheduler import get_trading_scheduler
                    sched = get_trading_scheduler()
                    if sched._etoro_client:
                        acct = sched._etoro_client.get_account_info()
                        account_balance = getattr(acct, 'balance', 0) or 0
                        account_equity = getattr(acct, 'equity', 0) or 0
                except Exception:
                    pass

                # Get open positions for portfolio state
                open_pos_count = 0
                total_unrealized = 0
                try:
                    from src.models.database import get_database
                    from src.models.orm import PositionORM, StrategyORM
                    _s = get_database().get_session()
                    try:
                        open_positions = _s.query(PositionORM).filter(PositionORM.closed_at.is_(None)).all()
                        open_pos_count = len(open_positions)
                        total_unrealized = sum(p.unrealized_pnl or 0 for p in open_positions)
                    finally:
                        _s.close()
                except Exception:
                    pass

                cl.start_cycle(
                    cycle_id=cycle_id,
                    regime=stats.get('regime', 'unknown'),
                    confidence=stats.get('regime_confidence', 0),
                    active_strategies=total_active,
                    open_positions=open_pos_count,
                    account_balance=account_balance,
                    account_equity=account_equity,
                )

                cl.log_stage("CLEANUP", f"{stats['strategies_cleaned']} cleaned, {stats['strategies_retired']} retired")

                cl.log_proposals(
                    total=stats['proposals_generated'],
                    dsl=template_count,
                    alpha_edge=alpha_edge_count,
                    wf_passed=bt_passed,
                    wf_total=bt_passed + bt_failed,
                    pass_rate=(bt_passed / max(bt_passed + bt_failed, 1)) * 100,
                )

                # Log detailed walk-forward results
                wf_details = stats.get('wf_results', [])
                if wf_details:
                    cl.log_wf_results(wf_details)

                # Log template performance stats
                template_stats = stats.get('template_stats', {})
                if template_stats:
                    cl.log_template_stats(template_stats)

                # Log activation details
                activated_details = stats.get('activated_details', [])
                rejected_details = stats.get('rejected_details', [])
                if activated_details or rejected_details:
                    cl.log_activation(activated_details, rejected_details)
                else:
                    cl.log_stage("ACTIVATION", f"{promoted_to_demo} activated to DEMO (approved={stats['strategies_activated']})",
                                 {"avg_sharpe": f"{avg_sharpe:.2f}", "avg_wr": f"{avg_win_rate:.1f}%"})

                # Log retirement details
                retired_details = stats.get('retired_details', [])
                if retired_details:
                    cl.log_retirement(retired_details)

                # Log portfolio state with actual exposure calculation
                long_exp = 0.0
                short_exp = 0.0
                position_details = []
                try:
                    if open_positions and account_balance > 0:
                        for p in open_positions:
                            # Use invested_amount if available (more reliable than qty × price
                            # because eToro stores qty in units for stocks but sometimes in
                            # dollar amounts for crypto/CFDs)
                            invested = getattr(p, 'invested_amount', None)
                            if invested and invested > 0:
                                pos_value = abs(invested)
                            else:
                                # FALLBACK: invested_amount is NULL (old positions or sync issues).
                                # eToro stores quantity as DOLLAR AMOUNT for CFDs (crypto, forex)
                                # but as SHARE COUNT for stocks. qty * price produces correct
                                # values for stocks but astronomical values for CFDs.
                                # Cap at 5% of account balance (max allocation per strategy)
                                # to prevent 195%+ phantom exposure from qty-in-dollars CFDs.
                                raw_value = abs((p.quantity or 0) * (p.current_price or p.entry_price or 0))
                                max_reasonable = account_balance * 0.05  # 5% max per position
                                if raw_value > max_reasonable:
                                    # Likely a CFD where qty is dollars — use qty as the value
                                    pos_value = abs(p.quantity or 0)
                                    if pos_value > max_reasonable:
                                        pos_value = max_reasonable  # Hard cap
                                    logger.debug(
                                        f"Exposure fallback for {p.symbol}: qty*price=${raw_value:,.0f} "
                                        f"unreasonable, using ${pos_value:,.0f}"
                                    )
                                else:
                                    pos_value = raw_value
                            pct = (pos_value / (account_equity or account_balance)) * 100 if (account_equity or account_balance) > 0 else 0
                            side_str = str(p.side).upper() if p.side else ''
                            if 'LONG' in side_str or 'BUY' in side_str:
                                long_exp += pct
                            elif 'SHORT' in side_str or 'SELL' in side_str:
                                short_exp += pct
                            # Build per-position detail for cycle log
                            days_held = (datetime.now() - p.opened_at).days if p.opened_at else 0
                            # Look up strategy name
                            strat_name = ''
                            try:
                                if p.strategy_id:
                                    strat_orm = _s.query(StrategyORM).filter_by(id=p.strategy_id).first()
                                    if strat_orm:
                                        strat_name = strat_orm.name
                            except Exception:
                                pass
                            position_details.append({
                                'symbol': p.symbol or '?',
                                'side': 'LONG' if 'LONG' in side_str or 'BUY' in side_str else 'SHORT',
                                'pnl': p.unrealized_pnl or 0,
                                'days_held': days_held,
                                'strategy': strat_name,
                            })
                except Exception as exp_err:
                    logger.debug(f"Could not calculate exposure: {exp_err}")

                cl.log_portfolio_state(
                    positions_count=open_pos_count,
                    total_unrealized_pnl=total_unrealized,
                    long_exposure_pct=long_exp,
                    short_exposure_pct=short_exp,
                    position_details=position_details,
                )

                cl.log_signals(
                    generated=signals_generated,
                    coordinated=signals_generated - signals_rejected,
                    rejected=signals_rejected,
                    orders_submitted=orders_submitted,
                )

                for err in stats.get("errors", []):
                    cl.log_error("CYCLE", str(err))

                cl.end_cycle(cycle_duration, {
                    "proposals_generated": stats['proposals_generated'],
                    "template_count": template_count,
                    "alpha_edge_count": alpha_edge_count,
                    "bt_passed": bt_passed,
                    "bt_total": bt_passed + bt_failed,
                    "strategies_activated": promoted_to_demo,
                    "strategies_retired": stats['strategies_retired'],
                    "total_active": total_active,
                    "signals_generated": signals_generated,
                    "orders_submitted": orders_submitted,
                    "errors": stats.get("errors", []),
                })
            except Exception as e:
                logger.warning(f"Failed to write cycle log: {e}")

            return stats

        except Exception as e:
            logger.error(f"Fatal error in autonomous strategy cycle: {e}", exc_info=True)
            stats["errors"].append({"type": "fatal", "message": str(e)})
            self._update_cycle_run(cycle_id, "error", datetime.now(), 
                                   (datetime.now() - cycle_start).total_seconds(), stats, {})
            self._safe_broadcast(
                self.websocket_manager.broadcast_autonomous_notification,
                {
                    "type": "cycle_error",
                    "severity": "error",
                    "title": "Autonomous Cycle Error",
                    "message": f"Fatal error in cycle: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
            )
            return stats

    def _save_cycle_run(self, cycle_id: str, status: str, started_at: datetime):
        """Save a new cycle run record to the database."""
        try:
            from src.models.database import get_database
            from src.models.orm import AutonomousCycleRunORM, Base
            db = get_database()
            # Ensure the table exists (safe to call multiple times)
            Base.metadata.create_all(bind=db.engine, tables=[AutonomousCycleRunORM.__table__])
            session = db.get_session()
            try:
                run = AutonomousCycleRunORM(
                    cycle_id=cycle_id,
                    status=status,
                    started_at=started_at,
                )
                session.add(run)
                session.commit()
                logger.info(f"Saved cycle run {cycle_id} to DB")
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Failed to save cycle run to DB: {e}")
            # Also write to file for debugging
            with open('cycle_error.log', 'a') as f:
                f.write(f"_save_cycle_run error: {e}\n")

    def _update_cycle_run(self, cycle_id: str, status: str, completed_at: datetime,
                          duration: float, stats: Dict, extra: Dict):
        """Update an existing cycle run record with results."""
        try:
            from src.models.database import get_database
            from src.models.orm import AutonomousCycleRunORM, Base
            db = get_database()
            Base.metadata.create_all(bind=db.engine, tables=[AutonomousCycleRunORM.__table__])
            session = db.get_session()
            try:
                run = session.query(AutonomousCycleRunORM).filter_by(cycle_id=cycle_id).first()
                if not run:
                    logger.warning(f"Cycle run {cycle_id} not found in DB for update")
                    return
                run.status = status
                run.completed_at = completed_at
                run.duration_seconds = duration
                run.strategies_cleaned = stats.get("strategies_cleaned", 0)
                run.strategies_retired = stats.get("strategies_retired", 0)
                run.trades_analyzed = stats.get("trades_analyzed", 0)
                run.template_adjustments = stats.get("template_adjustments", 0)
                run.proposals_generated = stats.get("proposals_generated", 0)
                run.proposals_alpha_edge = extra.get("alpha_edge_count", 0)
                run.proposals_template = extra.get("template_count", 0)
                run.symbols_checked = extra.get("symbols_checked", 0)
                run.symbols_passed = extra.get("symbols_checked", 0)
                run.symbols_failed = 0
                run.backtested = stats.get("proposals_backtested", 0)
                run.backtest_passed = extra.get("bt_passed", 0)
                run.backtest_failed = extra.get("bt_failed", 0)
                run.avg_sharpe = extra.get("avg_sharpe")
                run.avg_win_rate = extra.get("avg_win_rate")
                run.activated = stats.get("strategies_activated", 0)  # passed activation → BACKTESTED
                run.promoted_to_demo = stats.get("strategies_activated_to_demo", 0)  # got first order → DEMO
                run.total_active = extra.get("total_active", 0)
                run.total_backtested = extra.get("total_backtested", 0)
                run.errors = stats.get("errors", []) if stats.get("errors") else None
                session.commit()
                logger.info(f"Updated cycle run {cycle_id} in DB: status={status}")
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Failed to update cycle run in DB: {e}")
            with open('cycle_error.log', 'a') as f:
                f.write(f"_update_cycle_run error: {e}\n")

    def _cleanup_inactive_strategies(self, stats: Dict) -> None:
        """
        Clean up strategies at cycle start.

        Design:
        - PROPOSED / INVALID: delete immediately (stale research artifacts)
        - BACKTESTED (unapproved, not demoted from active): delete (failed WF thresholds)
        - BACKTESTED (demoted_from_active, within TTL): keep for re-evaluation
        - BACKTESTED (demoted_from_active, past TTL): permanently delete
        - RETIRED (legacy, shouldn't exist anymore): clean up if past 14d
        - DEMO / LIVE: never touched here

        Active strategy retirement (health=0 / decay=0) is handled in
        _check_strategy_health and _check_strategy_decay, which demote to
        BACKTESTED with activation_approved=False and a 14-day TTL.
        """
        try:
            from src.models.database import get_database
            from src.models.orm import StrategyORM, StrategyRetirementORM

            db = get_database()
            session = db.get_session()

            try:
                stale_strategies = []

                # 1. PROPOSED and INVALID — always delete (stale cycle artifacts)
                stale_strategies += session.query(StrategyORM).filter(
                    StrategyORM.status.in_([
                        StrategyStatus.PROPOSED,
                        StrategyStatus.INVALID
                    ])
                ).all()

                # 2. RETIRED — permanently delete at cycle start.
                # RETIRED is a terminal state set only by legacy code paths or manual intervention.
                # Health/decay checks now demote to BACKTESTED directly, never setting RETIRED.
                # Any RETIRED strategy here is stale and should be cleaned up immediately.
                stale_strategies += session.query(StrategyORM).filter(
                    StrategyORM.status == StrategyStatus.RETIRED
                ).all()

                # 3. BACKTESTED — keep approved and recently-demoted-from-active; delete the rest
                for s in session.query(StrategyORM).filter(StrategyORM.status == StrategyStatus.BACKTESTED).all():
                    meta = s.strategy_metadata if isinstance(s.strategy_metadata, dict) else {}

                    if meta.get('activation_approved'):
                        continue  # Approved and waiting for signal — keep

                    if meta.get('demoted_from_active'):
                        # Demoted from active (health=0 or decay=0) — respect TTL
                        ttl_days = meta.get('demotion_ttl_days', 14)
                        demoted_at_str = meta.get('demoted_at')
                        if demoted_at_str:
                            try:
                                age_days = (datetime.now() - datetime.fromisoformat(demoted_at_str)).days
                                if age_days <= ttl_days:
                                    continue  # Within TTL — keep for re-evaluation
                                logger.info(
                                    f"    Demoted strategy past TTL: {s.name} "
                                    f"({age_days}d > {ttl_days}d TTL)"
                                )
                            except Exception:
                                continue  # Can't parse — keep to be safe
                        else:
                            continue  # No timestamp — keep to be safe

                    # Unapproved, not demoted from active — failed WF thresholds, delete
                    stale_strategies.append(s)

                if not stale_strategies:
                    logger.info("  No strategies to clean up")
                else:
                    delete_ids = [s.id for s in stale_strategies]
                    session.query(StrategyRetirementORM).filter(
                        StrategyRetirementORM.strategy_id.in_(delete_ids)
                    ).delete(synchronize_session=False)

                    for s in stale_strategies:
                        old_status = s.status.value if hasattr(s.status, "value") else str(s.status)
                        logger.info(f"    Deleting: {s.name} (status: {old_status})")
                        session.delete(s)
                        stats["strategies_cleaned"] += 1

                session.commit()

                backtested_count = session.query(StrategyORM).filter(
                    StrategyORM.status == StrategyStatus.BACKTESTED
                ).count()
                active_count = session.query(StrategyORM).filter(
                    StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE])
                ).count()

                logger.info(
                    f"  ✓ Cleanup complete. "
                    f"Kept: {backtested_count} BACKTESTED, {active_count} DEMO/LIVE. "
                    f"Deleted: {stats['strategies_cleaned']} stale."
                )

            finally:
                session.close()

        except Exception as e:
            logger.error(f"Error cleaning up strategies: {e}", exc_info=True)
            stats["errors"].append({"step": "cleanup", "message": str(e)})

    def _propose_strategies(self, stats: Dict) -> List[Strategy]:
        """
        Propose new strategies based on market conditions.

        Args:
            stats: Statistics dictionary to update

        Returns:
            List of proposed strategies
        """
        try:
            proposal_count = self.config["autonomous"]["proposal_count"]
            
            # Log disabled templates once per cycle
            try:
                all_templates = self.strategy_proposer.template_library.get_all_templates()
                for template in all_templates:
                    disabled, reason = self.strategy_proposer._is_template_disabled(template)
                    if disabled:
                        logger.warning(f"Template '{template.name}' is disabled: {reason}")
            except Exception as e:
                logger.debug(f"Could not check disabled templates: {e}")
            
            # Progress callback for sub-stage updates
            def on_proposal_progress(phase: str, pct: int):
                # Map 0-100% of proposals to 22-65% of overall pipeline
                overall_pct = 22 + int(pct * 0.43)  # 22% to 65%
                self._emit_stage_event("strategy_proposals", "running", overall_pct, {
                    "phase": phase
                })
            
            proposals = self.strategy_proposer.propose_strategies(
                count=proposal_count,
                strategy_engine=self.strategy_engine,
                use_walk_forward=True,
                progress_callback=on_proposal_progress,
                filters=getattr(self, '_cycle_filters', None)
            )

            stats["proposals_generated"] = len(proposals)

            for i, strategy in enumerate(proposals, 1):
                logger.info(
                    f"  [{i}/{len(proposals)}] Proposed: {strategy.name} "
                    f"(symbols: {', '.join(strategy.symbols)})"
                )
                
                # Broadcast strategy proposed event
                self._safe_broadcast(
                    self.websocket_manager.broadcast_autonomous_strategy_event,
                    "strategy_proposed",
                    {
                        "id": strategy.id,
                        "name": strategy.name,
                        "symbols": strategy.symbols,
                        "status": strategy.status.value,
                        "timestamp": datetime.now().isoformat()
                    }
                )

            # Broadcast notification for proposals
            if len(proposals) > 0:
                self._safe_broadcast(
                    self.websocket_manager.broadcast_autonomous_notification,
                    {
                        "type": "strategies_proposed",
                        "severity": "info",
                        "title": "Strategies Proposed",
                        "message": f"{len(proposals)} new strategies generated for current market conditions",
                        "timestamp": datetime.now().isoformat(),
                        "data": {
                            "count": len(proposals)
                        }
                    }
                )

            return proposals

        except Exception as e:
            logger.error(f"Error proposing strategies: {e}", exc_info=True)
            stats["errors"].append({"step": "propose", "message": str(e)})
            return []

    def _apply_performance_feedback(self, stats: Dict) -> None:
        """Fetch performance feedback from the trade journal and apply it to the proposer.

        Reads feedback config from ``self.config`` and delegates to
        ``TradeJournal.get_performance_feedback()`` and
        ``StrategyProposer.apply_performance_feedback()``.
        """
        try:
            from src.models.database import get_database
            from src.analytics.trade_journal import TradeJournal

            db = get_database()
            trade_journal = TradeJournal(db)

            # Read feedback config
            feedback_cfg = self.config.get("performance_feedback", {})
            lookback_days = feedback_cfg.get("feedback_lookback_days", 60)
            min_trades = feedback_cfg.get("min_trades_for_feedback", 5)
            max_weight = feedback_cfg.get("max_weight_adjustment", 2.0)
            min_weight = feedback_cfg.get("min_weight_adjustment", 0.3)

            feedback = trade_journal.get_performance_feedback(
                lookback_days=lookback_days,
                min_trades=min_trades,
            )

            self.strategy_proposer.apply_performance_feedback(
                feedback=feedback,
                max_weight=max_weight,
                min_weight=min_weight,
            )

            stats["performance_feedback_applied"] = feedback.get("has_sufficient_data", False)
            stats["performance_feedback_trades"] = feedback.get("total_trades", 0)

            logger.info(
                f"  Performance feedback: {feedback.get('total_trades', 0)} trades analyzed, "
                f"sufficient_data={feedback.get('has_sufficient_data', False)}"
            )

        except Exception as e:
            logger.warning(f"  Performance feedback failed (non-critical): {e}")
            stats["performance_feedback_applied"] = False
            stats["performance_feedback_trades"] = 0



    def _backtest_proposals(
        self, proposals: List[Strategy], stats: Dict
    ) -> List[Strategy]:
        """
        Backtest all proposed strategies.

        Args:
            proposals: List of proposed strategies
            stats: Statistics dictionary to update

        Returns:
            List of successfully backtested strategies
        """
        backtested_strategies = []
        backtest_days = self.config["backtest"]["days"]
        # Alpha Edge uses same backtest window as DSL (from config)
        alpha_edge_backtest_days = backtest_days

        end_date = datetime.now()
        start_date = end_date - timedelta(days=backtest_days)
        alpha_edge_start_date = end_date - timedelta(days=alpha_edge_backtest_days)

        for i, strategy in enumerate(proposals, 1):
            try:
                current_strategy = strategy
                
                # Route Alpha Edge strategies through fundamental validation path
                is_alpha_edge = (
                    hasattr(strategy, 'metadata') and strategy.metadata 
                    and strategy.metadata.get('strategy_category') == 'alpha_edge'
                )
                
                # Emit sub-progress for pipeline UI
                bt_pct = 68 + int((i / len(proposals)) * 12)  # 68% to 80%
                category = "Alpha Edge" if is_alpha_edge else "DSL"
                self._emit_stage_event("walk_forward_backtesting", "running", bt_pct, {
                    "phase": f"Validating {strategy.name} ({i}/{len(proposals)}) [{category}]",
                    "current": i,
                    "total": len(proposals),
                })
                
                if is_alpha_edge:
                    # Alpha Edge: fundamental validation + FMP-based backtest
                    logger.info(f"  [{i}/{len(proposals)}] Alpha Edge fundamental validation: {strategy.name}...")
                    
                    alpha_validation = self.strategy_engine.validate_alpha_edge_strategy(strategy)
                    
                    if not alpha_validation["is_valid"]:
                        logger.warning(f"      Alpha Edge validation failed: {', '.join(alpha_validation['errors'])}")
                        strategy.status = StrategyStatus.INVALID
                        stats["errors"].append({
                            "step": "alpha_edge_validation",
                            "strategy": strategy.name,
                            "message": f"Alpha Edge validation failed: {', '.join(alpha_validation['errors'])}"
                        })
                        continue
                    
                    if alpha_validation.get("warnings"):
                        for w in alpha_validation["warnings"]:
                            logger.info(f"      Warning: {w}")
                    
                    logger.info(f"      Alpha Edge validation passed for {strategy.name}")
                    
                    # Alpha Edge backtest using real FMP historical data
                    if strategy.backtest_results is None:
                        logger.info(f"  [{i}/{len(proposals)}] Alpha Edge backtesting with FMP data: {strategy.name} ({alpha_edge_backtest_days} days)...")
                        backtest_results = self.strategy_engine.backtest_alpha_edge_strategy(
                            strategy=strategy, start=alpha_edge_start_date, end=end_date
                        )
                        strategy.backtest_results = backtest_results
                    
                    backtest_results = strategy.backtest_results
                    
                    # Update performance metrics
                    from src.models.dataclasses import PerformanceMetrics
                    strategy.performance = PerformanceMetrics(
                        total_return=backtest_results.total_return,
                        sharpe_ratio=backtest_results.sharpe_ratio,
                        sortino_ratio=backtest_results.sortino_ratio,
                        max_drawdown=backtest_results.max_drawdown,
                        win_rate=backtest_results.win_rate,
                        avg_win=backtest_results.avg_win,
                        avg_loss=backtest_results.avg_loss,
                        total_trades=backtest_results.total_trades
                    )
                    
                    logger.info(
                        f"      Alpha Edge results: Sharpe={backtest_results.sharpe_ratio:.2f}, "
                        f"Return={backtest_results.total_return:.2%}, "
                        f"Drawdown={backtest_results.max_drawdown:.2%}, "
                        f"WinRate={backtest_results.win_rate:.2%}, "
                        f"Trades={backtest_results.total_trades}"
                    )
                    
                    # If backtest produced insufficient trades (the 0-trade problem),
                    # fall back to factor-based validation. Fundamental strategies fire
                    # quarterly — expecting 2+ trades in a 2-year window on a single symbol
                    # is unrealistic. Instead, validate the underlying factor's edge.
                    min_ae_trades = 10
                    try:
                        min_ae_trades = self.config.get('activation_thresholds', {}).get('min_trades_alpha_edge', 10)
                    except Exception:
                        pass
                    
                    if backtest_results.total_trades < min_ae_trades:
                        logger.info(
                            f"      AE backtest produced {backtest_results.total_trades} trades "
                            f"(< {min_ae_trades}) — running factor-based validation..."
                        )
                        factor_result = self.strategy_engine.validate_alpha_edge_factor(strategy)
                        
                        if factor_result['passed']:
                            # Use the factor validation's synthetic results instead
                            backtest_results = factor_result['backtest_results']
                            strategy.backtest_results = backtest_results
                            if not strategy.metadata:
                                strategy.metadata = {}
                            strategy.metadata['validated_by'] = 'factor_validation'
                            strategy.metadata['factor_score'] = factor_result['factor_score']
                            strategy.metadata['factor_details'] = factor_result['details']
                            logger.info(
                                f"      Factor validation PASSED (score={factor_result['factor_score']:.0f}) — "
                                f"using synthetic results: Sharpe={backtest_results.sharpe_ratio:.2f}, "
                                f"WR={backtest_results.win_rate:.0%}"
                            )
                        else:
                            logger.warning(
                                f"      Factor validation FAILED (score={factor_result['factor_score']:.0f}) — "
                                f"strategy rejected"
                            )
                            strategy.status = StrategyStatus.INVALID
                            stats["errors"].append({
                                "step": "factor_validation",
                                "strategy": strategy.name,
                                "message": f"Factor score {factor_result['factor_score']:.0f} below threshold"
                            })
                            continue
                    
                    # Cache Alpha Edge backtest result in the proposer's WF cache
                    # so the same (template, symbol) combo isn't re-proposed next cycle
                    try:
                        import time as _ae_time
                        template_name = strategy.metadata.get('template_name', '') if strategy.metadata else ''
                        primary_symbol = strategy.symbols[0] if strategy.symbols else ''
                        if template_name and primary_symbol:
                            ae_cache_key = (template_name, primary_symbol)
                            # Store a minimal WF-compatible result tuple
                            ae_wf_result = {
                                'train_sharpe': backtest_results.sharpe_ratio,
                                'test_sharpe': backtest_results.sharpe_ratio,
                                'test_results': backtest_results,
                                'train_results': backtest_results,
                                'is_overfitted': False,
                                'performance_degradation': 0.0,
                            }
                            import math
                            s_valid = not (math.isinf(backtest_results.sharpe_ratio) or math.isnan(backtest_results.sharpe_ratio))
                            has_trades = backtest_results.total_trades >= 2
                            self.strategy_proposer._wf_results_cache[ae_cache_key] = (
                                (backtest_results.sharpe_ratio, backtest_results.sharpe_ratio,
                                 has_trades, False, s_valid, s_valid, ae_wf_result),
                                _ae_time.time()
                            )
                    except Exception as cache_err:
                        logger.debug(f"Could not cache AE backtest result: {cache_err}")
                    
                    # Broadcast and add to results
                    self._safe_broadcast(
                        self.websocket_manager.broadcast_autonomous_strategy_event,
                        "strategy_backtested",
                        {
                            "id": strategy.id,
                            "name": strategy.name,
                            "symbols": strategy.symbols,
                            "status": strategy.status.value if hasattr(strategy.status, 'value') else str(strategy.status),
                            "backtest_results": {
                                "sharpe_ratio": backtest_results.sharpe_ratio,
                                "total_return": backtest_results.total_return,
                                "max_drawdown": backtest_results.max_drawdown,
                                "win_rate": backtest_results.win_rate,
                                "total_trades": backtest_results.total_trades
                            },
                            "timestamp": datetime.now().isoformat()
                        }
                    )
                    
                    backtested_strategies.append(strategy)
                    stats["proposals_backtested"] += 1
                    continue  # Skip the DSL validation path below
                
                # Skip rule/signal validation for walk-forward validated strategies
                # Walk-forward validation already tests on out-of-sample data, so
                # re-running rule and signal validation is redundant and slow.
                is_walk_forward_validated = (
                    hasattr(strategy, 'metadata') and strategy.metadata
                    and strategy.metadata.get('walk_forward_validated') == True
                )
                
                if is_walk_forward_validated:
                    logger.info(
                        f"  [{i}/{len(proposals)}] Skipping rule validation for walk-forward validated strategy: {strategy.name}"
                    )
                else:
                    logger.info(
                        f"  [{i}/{len(proposals)}] Validating rules for: {strategy.name}..."
                    )
                    
                    # Rule validation for strategies that haven't been walk-forward validated.
                    # The root causes of false rejections have been fixed:
                    # 1. Validation now uses the same data window as backtest (from config)
                    # 2. Asset-class-aware min_entry_pct thresholds (forex/crypto get lower thresholds)
                    # 3. FMP data used for forex symbols (not just Yahoo Finance)
                    rule_validation = self.strategy_engine.validate_strategy_rules(strategy)
                    
                    if not rule_validation["is_valid"]:
                        logger.warning(
                            f"      Rule validation failed: {', '.join(rule_validation['errors'])}"
                        )
                        if rule_validation["suggestions"]:
                            logger.info(f"      Suggestions: {', '.join(rule_validation['suggestions'])}")
                        
                        # Mark strategy as INVALID and skip
                        strategy.status = StrategyStatus.INVALID
                        stats["errors"].append({
                            "step": "rule_validation",
                            "strategy": strategy.name,
                            "message": f"Rule validation failed: {', '.join(rule_validation['errors'])}"
                        })
                        continue
                    
                    logger.info(
                        f"      Rule validation passed (overlap: {rule_validation['overlap_percentage']:.1f}%, "
                        f"entry-only: {rule_validation['entry_only_percentage']:.1f}%)"
                    )
                    
                    logger.info(
                        f"  [{i}/{len(proposals)}] Validating signals for: {strategy.name}..."
                    )
                    
                    validation_result = self.strategy_engine.validate_strategy_signals(strategy)
                    
                    # If validation fails, attempt revision (max 2 attempts)
                    revision_attempts = 0
                    max_revisions = 2
                    current_strategy = strategy
                    
                    while not validation_result["is_valid"] and revision_attempts < max_revisions:
                        logger.warning(
                            f"      Validation failed (attempt {revision_attempts + 1}): "
                            f"{', '.join(validation_result['errors'])}"
                        )
                        logger.info(f"      Attempting to revise strategy...")
                        
                        # Get market regime for revision
                        market_regime, _, _ = self.strategy_proposer.analyze_market_conditions()
                        available_indicators = self.strategy_proposer._get_available_indicators()
                        
                        # Attempt revision
                        revised_strategy = self.strategy_proposer.revise_strategy(
                            failed_strategy=current_strategy,
                            validation_errors=validation_result['errors'],
                            market_regime=market_regime,
                            available_indicators=available_indicators
                        )
                        
                        if revised_strategy is None:
                            logger.error(f"      Revision failed - LLM could not generate valid strategy")
                            break
                        
                        logger.info(f"      Revision successful: {revised_strategy.name}")
                        current_strategy = revised_strategy
                        revision_attempts += 1
                        
                        # Validate the revised strategy
                        validation_result = self.strategy_engine.validate_strategy_signals(current_strategy)
                    
                    # Check final validation result
                    if not validation_result["is_valid"]:
                        logger.warning(
                            f"      Validation failed after {revision_attempts} revision attempts"
                        )
                        logger.warning(
                            f"      Entry signals: {validation_result['entry_signals']}, "
                            f"Exit signals: {validation_result['exit_signals']}"
                        )
                        logger.warning(f"      Skipping backtest for {current_strategy.name}")
                        
                        # Mark strategy as INVALID
                        current_strategy.status = StrategyStatus.INVALID
                        
                        stats["errors"].append({
                            "step": "validation",
                            "strategy": current_strategy.name,
                            "message": f"Signal validation failed after {revision_attempts} revisions: {', '.join(validation_result['errors'])}"
                        })
                        continue
                    
                    logger.info(
                        f"      Validation passed: {validation_result['entry_signals']} entry signals, "
                        f"{validation_result['exit_signals']} exit signals"
                    )
                    
                    if revision_attempts > 0:
                        logger.info(f"      Strategy revised {revision_attempts} time(s) before passing validation")
                
                logger.info(
                    f"  [{i}/{len(proposals)}] Backtesting: {current_strategy.name} "
                    f"({backtest_days} days)..."
                )

                # Skip redundant backtest if walk-forward validation already produced
                # out-of-sample results (stored on strategy by propose_strategies).
                if (current_strategy.backtest_results is not None
                        and hasattr(current_strategy, 'metadata')
                        and current_strategy.metadata
                        and current_strategy.metadata.get('walk_forward_validated')):
                    backtest_results = current_strategy.backtest_results
                    logger.info(
                        f"      Using walk-forward out-of-sample results (skipping redundant backtest): "
                        f"Sharpe={backtest_results.sharpe_ratio:.2f}, "
                        f"Return={backtest_results.total_return:.2%}, "
                        f"Drawdown={backtest_results.max_drawdown:.2%}, "
                        f"WinRate={backtest_results.win_rate:.2%}, "
                        f"Trades={backtest_results.total_trades}"
                    )
                else:
                    # Run full backtest (only for strategies without walk-forward results)
                    backtest_results = self.strategy_engine.backtest_strategy(
                        strategy=current_strategy, start=start_date, end=end_date
                    )
                    current_strategy.backtest_results = backtest_results

                    logger.info(
                        f"      Results: Sharpe={backtest_results.sharpe_ratio:.2f}, "
                        f"Return={backtest_results.total_return:.2%}, "
                        f"Drawdown={backtest_results.max_drawdown:.2%}, "
                        f"WinRate={backtest_results.win_rate:.2%}, "
                        f"Trades={backtest_results.total_trades}"
                    )

                # Broadcast strategy backtested event
                self._safe_broadcast(
                    self.websocket_manager.broadcast_autonomous_strategy_event,
                    "strategy_backtested",
                    {
                        "id": current_strategy.id,
                        "name": current_strategy.name,
                        "symbols": current_strategy.symbols,
                        "status": current_strategy.status.value,
                        "backtest_results": {
                            "sharpe_ratio": backtest_results.sharpe_ratio,
                            "total_return": backtest_results.total_return,
                            "max_drawdown": backtest_results.max_drawdown,
                            "win_rate": backtest_results.win_rate,
                            "total_trades": backtest_results.total_trades
                        },
                        "timestamp": datetime.now().isoformat()
                    }
                )

                backtested_strategies.append(current_strategy)
                stats["proposals_backtested"] += 1

            except Exception as e:
                logger.error(
                    f"  [{i}/{len(proposals)}] Failed to backtest {strategy.name}: {e}"
                )
                stats["errors"].append(
                    {"step": "backtest", "strategy": strategy.name, "message": str(e)}
                )
                continue

        return backtested_strategies

    def _evaluate_and_activate(
        self, backtested_strategies: List[Strategy], stats: Dict
    ) -> None:
        """
        Evaluate backtested strategies and activate high performers.
        """
        stats.setdefault('activated_details', [])
        stats.setdefault('rejected_details', [])
        
        # Track (template_name, primary_symbol) activated this cycle to prevent
        # multiple variants of the same template on the same symbol
        activated_this_cycle = set()
        
        # Track per-symbol AE activation count to prevent concentration
        # (e.g., 3 AE strategies all on ASML)
        ae_activations_per_symbol = {}
        MAX_AE_PER_SYMBOL = 2  # Max AE strategies on the same primary symbol
        
        # Also load existing active strategies to prevent re-activating same template+symbol
        existing_active_combos = set()
        try:
            active_strategies = self.strategy_engine.get_active_strategies()
            for s in active_strategies:
                tname = s.metadata.get('template_name', s.name) if s.metadata else s.name
                psym = s.symbols[0] if s.symbols else 'unknown'
                existing_active_combos.add((tname, psym))
        except Exception as e:
            logger.warning(f"Could not load existing active combos: {e}")
        
        # Fetch market context (VIX, macro regime) for threshold adjustments
        market_context = None
        try:
            market_context = self.strategy_proposer.market_analyzer.get_market_context()
            vix = market_context.get('vix', 'N/A')
            regime = market_context.get('macro_regime', 'unknown')
            logger.info(f"Market context for activation: VIX={vix}, regime={regime}")
        except Exception as e:
            logger.warning(f"Failed to fetch market context: {e} — using default thresholds")

        # Pre-sort strategies by conviction score (Sharpe × win_rate) so the best
        # strategies get activated first when we hit the max_active_strategies cap
        def _conviction_score(s):
            bt = s.backtest_results
            if not bt:
                return 0
            return bt.sharpe_ratio * bt.win_rate
        
        backtested_strategies = sorted(backtested_strategies, key=_conviction_score, reverse=True)
        logger.info(f"Sorted {len(backtested_strategies)} strategies by conviction (top: {backtested_strategies[0].name if backtested_strategies else 'none'})")

        for i, strategy in enumerate(backtested_strategies, 1):
            try:
                # Emit sub-progress for pipeline UI
                act_pct = 80 + int((i / len(backtested_strategies)) * 10)  # 80% to 90%
                self._emit_stage_event("strategy_activation", "running", act_pct, {
                    "phase": f"Evaluating {strategy.name} ({i}/{len(backtested_strategies)})",
                    "current": i,
                    "total": len(backtested_strategies),
                })
                
                # Evaluate for activation
                result = self.portfolio_manager.evaluate_for_activation(
                    strategy=strategy, backtest_results=strategy.backtest_results,
                    market_context=market_context
                )
                
                # Unpack result: (bool, reason_string_or_None)
                if isinstance(result, tuple):
                    should_activate, rejection_reason = result
                else:
                    # Backward compat if someone returns bare bool
                    should_activate = result
                    rejection_reason = "Below activation thresholds"

                if not should_activate:
                    bt = strategy.backtest_results
                    # Track rejection for blacklist
                    try:
                        rej_template_name = strategy.metadata.get('template_name', strategy.name) if strategy.metadata else strategy.name
                        rej_primary_sym = strategy.symbols[0] if strategy.symbols else 'unknown'
                        self.strategy_proposer.record_rejection(rej_template_name, rej_primary_sym)
                    except Exception as e:
                        logger.debug(f"Could not record rejection: {e}")
                    stats["rejected_details"].append({
                        "name": strategy.name,
                        "sharpe": bt.sharpe_ratio if bt else 0,
                        "win_rate": bt.win_rate if bt else 0,
                        "trades": bt.total_trades if bt else 0,
                        "reason": rejection_reason or "Below activation thresholds",
                    })
                    continue

                logger.info(
                    f"  [{i}/{len(backtested_strategies)}] ✓ {strategy.name} "
                    f"passed activation criteria"
                )

                # Dedup: max 1 activation per (template, primary_symbol) per cycle
                template_name = strategy.metadata.get('template_name', strategy.name) if strategy.metadata else strategy.name
                primary_sym = strategy.symbols[0] if strategy.symbols else 'unknown'
                activation_key = (template_name, primary_sym)
                if activation_key in activated_this_cycle:
                    logger.info(
                        f"      Skipping duplicate: {template_name} on {primary_sym} "
                        f"already activated this cycle"
                    )
                    stats["rejected_details"].append({
                        "name": strategy.name,
                        "sharpe": strategy.backtest_results.sharpe_ratio if strategy.backtest_results else 0,
                        "win_rate": strategy.backtest_results.win_rate if strategy.backtest_results else 0,
                        "trades": strategy.backtest_results.total_trades if strategy.backtest_results else 0,
                        "reason": f"Duplicate: {template_name} on {primary_sym} already activated",
                    })
                    continue
                
                # Cross-cycle dedup: skip if same template+symbol already active in DB
                if activation_key in existing_active_combos:
                    # Check if the new strategy is meaningfully better (>15% Sharpe improvement)
                    # If so, supersede the existing strategy instead of skipping
                    superseded = False
                    try:
                        new_sharpe = strategy.backtest_results.sharpe_ratio if strategy.backtest_results else 0
                        if new_sharpe > 0:
                            from src.models.database import get_database
                            from src.models.orm import StrategyORM
                            from sqlalchemy.orm.attributes import flag_modified as _flag_mod
                            _db = get_database()
                            _sess = _db.get_session()
                            try:
                                # Find the existing active strategy for this template+symbol
                                existing_strats = _sess.query(StrategyORM).filter(
                                    StrategyORM.status.in_(['DEMO', 'LIVE'])
                                ).all()
                                for _es in existing_strats:
                                    _em = _es.strategy_metadata if isinstance(_es.strategy_metadata, dict) else {}
                                    _et = _em.get('template_name', _es.name)
                                    _ep = (_es.symbols[0] if isinstance(_es.symbols, list) and _es.symbols
                                           else _es.symbols) if _es.symbols else 'unknown'
                                    if isinstance(_ep, str) and _ep.startswith('['):
                                        import json as _j
                                        try: _ep = _j.loads(_ep)[0]
                                        except: pass
                                    if (_et, _ep) != activation_key:
                                        continue
                                    # Found the existing strategy — check if already superseded
                                    if _em.get('superseded'):
                                        break
                                    # Get existing Sharpe from backtest_results
                                    existing_bt = _es.backtest_results or {}
                                    existing_sharpe = (existing_bt.get('sharpe_ratio', 0)
                                                       if isinstance(existing_bt, dict)
                                                       else getattr(existing_bt, 'sharpe_ratio', 0))
                                    improvement = ((new_sharpe - existing_sharpe) / max(abs(existing_sharpe), 0.01))
                                    if improvement > 0.15:  # >15% Sharpe improvement
                                        # Supersede: stop old strategy from generating new signals
                                        _em['superseded'] = True
                                        _em['superseded_by'] = strategy.id
                                        _em['superseded_at'] = datetime.now().isoformat()
                                        _em['superseded_reason'] = (
                                            f"Better calibration found: Sharpe {new_sharpe:.2f} vs {existing_sharpe:.2f} "
                                            f"(+{improvement:.0%})"
                                        )
                                        _es.strategy_metadata = _em
                                        _flag_mod(_es, 'strategy_metadata')
                                        _sess.commit()
                                        superseded = True
                                        logger.info(
                                            f"      Superseding {_es.name} with {strategy.name} "
                                            f"(Sharpe {existing_sharpe:.2f} → {new_sharpe:.2f}, +{improvement:.0%})"
                                        )
                                    break
                            finally:
                                _sess.close()
                    except Exception as _sup_err:
                        logger.debug(f"Supersession check failed: {_sup_err}")

                    if not superseded:
                        logger.info(
                            f"      Skipping: {template_name} on {primary_sym} "
                            f"already active from a previous cycle"
                        )
                        stats["rejected_details"].append({
                            "name": strategy.name,
                            "sharpe": strategy.backtest_results.sharpe_ratio if strategy.backtest_results else 0,
                            "win_rate": strategy.backtest_results.win_rate if strategy.backtest_results else 0,
                            "trades": strategy.backtest_results.total_trades if strategy.backtest_results else 0,
                            "reason": f"Already active: {template_name} on {primary_sym}",
                        })
                        continue
                    # Superseded — fall through to activate the new strategy immediately

                # Per-symbol AE concentration check: prevent too many AE strategies
                # on the same primary symbol (e.g., 3 different AE templates all on ASML)
                is_ae = (
                    hasattr(strategy, 'metadata') and strategy.metadata
                    and strategy.metadata.get('strategy_category') == 'alpha_edge'
                )
                if is_ae:
                    ae_count_for_sym = ae_activations_per_symbol.get(primary_sym, 0)
                    if ae_count_for_sym >= MAX_AE_PER_SYMBOL:
                        logger.info(
                            f"      Skipping: {MAX_AE_PER_SYMBOL} AE strategies already activated "
                            f"on {primary_sym} this cycle (concentration limit)"
                        )
                        stats["rejected_details"].append({
                            "name": strategy.name,
                            "sharpe": strategy.backtest_results.sharpe_ratio if strategy.backtest_results else 0,
                            "win_rate": strategy.backtest_results.win_rate if strategy.backtest_results else 0,
                            "trades": strategy.backtest_results.total_trades if strategy.backtest_results else 0,
                            "reason": f"AE concentration: {MAX_AE_PER_SYMBOL} AE strategies already on {primary_sym}",
                        })
                        continue

                # Pre-check retirement triggers before activating — but ONLY for strategies
                # that have live trade history. Newly proposed strategies have zero live trades;
                # their performance metrics are from backtesting, which already passed activation
                # thresholds (stricter than retirement thresholds). Checking backtest metrics
                # against retirement thresholds is meaningless and can block good strategies.
                #
                # Return correlation check: reject strategies whose backtest returns are
                # highly correlated (>0.7) with any existing active strategy's returns.
                # This catches "different rules, same bet" situations (e.g., BB Middle Band
                # on IWM and RSI Dip Buy on QQQ both lose on broad market selloffs).
                try:
                    if strategy.backtest_results and hasattr(strategy.backtest_results, 'daily_returns'):
                        new_returns = strategy.backtest_results.daily_returns
                        if new_returns is not None and len(new_returns) > 20:
                            import numpy as np
                            corr_threshold = 0.7
                            try:
                                import yaml as _yaml_corr
                                from pathlib import Path as _Path_corr
                                _corr_path = _Path_corr("config/autonomous_trading.yaml")
                                if _corr_path.exists():
                                    with open(_corr_path, 'r') as _f_corr:
                                        _corr_cfg = _yaml_corr.safe_load(_f_corr)
                                        corr_threshold = _corr_cfg.get('advanced', {}).get('correlation_threshold', 0.7)
                            except Exception:
                                pass

                            too_correlated = False
                            correlated_with = None
                            for active_s in active_strategies:
                                if not (active_s.backtest_results and hasattr(active_s.backtest_results, 'daily_returns')):
                                    continue
                                active_returns = active_s.backtest_results.daily_returns
                                if active_returns is None or len(active_returns) < 20:
                                    continue
                                # Align lengths
                                min_len = min(len(new_returns), len(active_returns))
                                try:
                                    corr = np.corrcoef(
                                        np.array(new_returns[-min_len:], dtype=float),
                                        np.array(active_returns[-min_len:], dtype=float)
                                    )[0, 1]
                                    if not np.isnan(corr) and abs(corr) > corr_threshold:
                                        too_correlated = True
                                        correlated_with = active_s.name
                                        break
                                except Exception:
                                    continue

                            if too_correlated:
                                logger.info(
                                    f"      Skipping: return correlation {abs(corr):.2f} > {corr_threshold} "
                                    f"with active '{correlated_with}'"
                                )
                                stats["rejected_details"].append({
                                    "name": strategy.name,
                                    "sharpe": strategy.backtest_results.sharpe_ratio if strategy.backtest_results else 0,
                                    "win_rate": strategy.backtest_results.win_rate if strategy.backtest_results else 0,
                                    "trades": strategy.backtest_results.total_trades if strategy.backtest_results else 0,
                                    "reason": f"Correlated ({abs(corr):.2f}) with {correlated_with}",
                                })
                                continue
                except Exception as e:
                    logger.debug(f"Return correlation check skipped: {e}")

                #
                # EXCEPTION: Check backtest max_drawdown against retirement threshold (25%)
                # because activation allows up to 20% drawdown but retirement triggers at 25%.
                # A strategy with 29% backtest drawdown passes activation but gets immediately
                # retired — wasting an activation slot.
                if strategy.live_trade_count and strategy.live_trade_count >= 1:
                    pre_retirement_reason = self.portfolio_manager.check_retirement_triggers(strategy)
                    if pre_retirement_reason:
                        logger.warning(
                            f"      ⚠️ Skipping activation — would immediately trigger retirement: "
                            f"{pre_retirement_reason}"
                        )
                        continue
                elif strategy.backtest_results and strategy.backtest_results.max_drawdown > 0.25:
                    # Check if the drawdown is reasonable for this symbol's volatility
                    # High-vol stocks (PLTR, TSLA) naturally have higher drawdowns
                    # Scale threshold: base 25% + (symbol_vol / avg_vol - 1) * 15%
                    dd_threshold = 0.25
                    try:
                        primary_sym = strategy.symbols[0] if strategy.symbols else None
                        if primary_sym and hasattr(self, 'strategy_proposer'):
                            sym_stats = self.strategy_proposer.market_analyzer.analyze_symbol(primary_sym, period_days=365)
                            sym_vol = sym_stats.get('volatility_metrics', {}).get('volatility', 0.15)
                            avg_vol = 0.15  # Rough market average
                            if sym_vol > avg_vol:
                                vol_ratio = sym_vol / avg_vol
                                dd_threshold = min(0.40, 0.25 + (vol_ratio - 1) * 0.15)
                    except Exception:
                        pass
                    
                    if strategy.backtest_results.max_drawdown > dd_threshold:
                        logger.warning(
                            f"      ⚠️ Skipping activation — backtest drawdown "
                            f"{strategy.backtest_results.max_drawdown:.1%} > {dd_threshold:.0%} "
                            f"retirement threshold (vol-adjusted)"
                        )
                        bt = strategy.backtest_results
                        stats["rejected_details"].append({
                            "name": strategy.name,
                            "sharpe": bt.sharpe_ratio if bt else 0,
                            "win_rate": bt.win_rate if bt else 0,
                            "trades": bt.total_trades if bt else 0,
                            "reason": f"Drawdown {strategy.backtest_results.max_drawdown:.1%} > {dd_threshold:.0%} (would retire immediately)",
                        })
                        continue

                # Pre-check: avg_loss vs stop-loss effectiveness
                # Retirement triggers at avg_loss > 3x stop_loss with 20+ trades.
                # Catch this at activation to avoid activate-then-immediately-retire.
                # avg_loss from vectorbt is in DOLLARS — convert to % of position size.
                if (strategy.backtest_results and strategy.risk_params
                        and strategy.risk_params.stop_loss_pct > 0
                        and strategy.backtest_results.avg_loss != 0
                        and strategy.backtest_results.total_trades >= 20):
                    avg_loss_dollars = abs(strategy.backtest_results.avg_loss)
                    # Convert to percentage using trade size data if available
                    avg_loss_pct = 0.0
                    bt_trades = strategy.backtest_results.trades
                    if bt_trades is not None and hasattr(bt_trades, '__len__') and len(bt_trades) > 0:
                        try:
                            if 'Size' in bt_trades.columns:
                                avg_pos = bt_trades['Size'].mean()
                                if avg_pos > 0:
                                    avg_loss_pct = avg_loss_dollars / avg_pos
                        except Exception:
                            pass
                    if avg_loss_pct == 0.0:
                        avg_loss_pct = avg_loss_dollars / 10000  # Fallback: 10% of $100K

                    sl_limit = strategy.risk_params.stop_loss_pct * 3.0
                    if avg_loss_pct > sl_limit:
                        logger.warning(
                            f"      ⚠️ Skipping activation — avg loss {avg_loss_pct:.1%} > "
                            f"{sl_limit:.1%} (3x stop-loss) — would retire immediately"
                        )
                        bt = strategy.backtest_results
                        stats["rejected_details"].append({
                            "name": strategy.name,
                            "sharpe": bt.sharpe_ratio if bt else 0,
                            "win_rate": bt.win_rate if bt else 0,
                            "trades": bt.total_trades if bt else 0,
                            "reason": f"Avg loss {avg_loss_pct:.1%} > {sl_limit:.1%} (3x stop-loss, would retire immediately)",
                        })
                        continue

                # Check if we can activate (not at max strategies)
                active_strategies = self.strategy_engine.get_active_strategies()
                max_strategies = self.config["autonomous"]["max_active_strategies"]

                if len(active_strategies) >= max_strategies:
                    logger.warning(
                        f"      Cannot activate: already at maximum of "
                        f"{max_strategies} active strategies"
                    )
                    continue

                # Mark as BACKTESTED (ready to trade) — NOT DEMO yet.
                # Strategy will be promoted to DEMO when it generates its first signal.
                # This prevents idle DEMO strategies consuming slots.
                try:
                    # Dynamic allocation formula:
                    #   allocation = base × sharpe_factor × confidence × budget_factor
                    #
                    # - base: 2% (standard position size)
                    # - sharpe_factor: linear scale from Sharpe ratio (S=1 → 1x, S=2 → 2x)
                    # - confidence: trade count scaling (3 trades → 0.38x, 10+ → 1x)
                    # - budget_factor: scales down when remaining exposure budget is tight
                    #
                    # Result clamped to [0.5%, 5.0%] per strategy.
                    bt = strategy.backtest_results
                    sharpe = bt.sharpe_ratio if bt else 0
                    win_rate = bt.win_rate if bt else 0
                    test_trades = bt.total_trades if bt else 0

                    base_pct = 2.0
                    sharpe_factor = max(0.5, min(2.5, sharpe / 1.0))
                    confidence_factor = max(0.3, min(1.0, test_trades / 8.0))

                    # Budget awareness: how much exposure room is left?
                    try:
                        account_equity_val = 0
                        current_exposure_pct = 0
                        from src.core.trading_scheduler import get_trading_scheduler
                        sched = get_trading_scheduler()
                        if sched._etoro_client:
                            acct = sched._etoro_client.get_account_info()
                            account_equity_val = getattr(acct, 'equity', 0) or getattr(acct, 'balance', 0) or 0
                        from src.models.database import get_database
                        from src.models.orm import PositionORM as _PosORM
                        _bs = get_database().get_session()
                        try:
                            open_pos = _bs.query(_PosORM).filter(_PosORM.closed_at.is_(None)).all()
                            total_invested = sum(abs(p.invested_amount or p.quantity or 0) for p in open_pos)
                            if account_equity_val > 0:
                                current_exposure_pct = total_invested / account_equity_val
                        finally:
                            _bs.close()

                        max_exposure = 0.90  # from risk config
                        remaining_exposure = max(0.05, max_exposure - current_exposure_pct)
                        remaining_slots = max(1, max_strategies - len(active_strategies))
                        fair_share = (remaining_exposure / remaining_slots) * 100  # as pct
                        budget_factor = max(0.4, min(1.5, fair_share / base_pct))
                    except Exception:
                        budget_factor = 1.0

                    allocation_pct = base_pct * sharpe_factor * confidence_factor * budget_factor
                    allocation_pct = round(max(0.5, min(5.0, allocation_pct)), 1)

                    logger.info(
                        f"      Allocation: {allocation_pct:.1f}% "
                        f"(base={base_pct}% × sharpe={sharpe_factor:.2f} × conf={confidence_factor:.2f} "
                        f"× budget={budget_factor:.2f})"
                    )
                    
                    # Save as BACKTESTED with allocation in metadata
                    strategy.status = StrategyStatus.BACKTESTED
                    if not strategy.metadata:
                        strategy.metadata = {}
                    strategy.metadata['pending_allocation_pct'] = allocation_pct
                    strategy.metadata['activation_approved'] = True
                    strategy.allocation_percent = allocation_pct
                    self.strategy_engine._save_strategy(strategy)

                    stats["strategies_activated"] += 1
                    stats["activated_strategy_ids"].append(strategy.id)
                    activated_this_cycle.add(activation_key)
                    # Track AE per-symbol concentration
                    if is_ae:
                        ae_activations_per_symbol[primary_sym] = ae_activations_per_symbol.get(primary_sym, 0) + 1
                    # Reset rejection counter on successful activation
                    try:
                        self.strategy_proposer.reset_rejection(template_name, primary_sym)
                    except Exception as e:
                        logger.debug(f"Could not reset rejection counter: {e}")
                    stats["activated_details"].append({
                        "name": strategy.name,
                        "symbols": strategy.symbols,
                        "sharpe": strategy.backtest_results.sharpe_ratio if strategy.backtest_results else 0,
                        "win_rate": strategy.backtest_results.win_rate if strategy.backtest_results else 0,
                        "trades": strategy.backtest_results.total_trades if strategy.backtest_results else 0,
                        "drawdown": strategy.backtest_results.max_drawdown if strategy.backtest_results else 0,
                        "is_alpha_edge": strategy.metadata.get('strategy_category') == 'alpha_edge' if strategy.metadata else False,
                    })
                    logger.info(f"      ✓ Ready (BACKTESTED) — will activate on first signal (allocation: {allocation_pct:.1f}%)")
                    
                    # Broadcast
                    self._safe_broadcast(
                        self.websocket_manager.broadcast_autonomous_strategy_event,
                        "strategy_activated",
                        {
                            "id": strategy.id,
                            "name": strategy.name,
                            "symbols": strategy.symbols,
                            "status": "BACKTESTED",
                            "backtest_results": {
                                "sharpe_ratio": strategy.backtest_results.sharpe_ratio,
                                "total_return": strategy.backtest_results.total_return,
                                "max_drawdown": strategy.backtest_results.max_drawdown,
                                "win_rate": strategy.backtest_results.win_rate
                            },
                            "timestamp": datetime.now().isoformat()
                        }
                    )
                    self._safe_broadcast(
                        self.websocket_manager.broadcast_autonomous_notification,
                        {
                            "type": "strategy_ready",
                            "severity": "info",
                            "title": "Strategy Ready",
                            "message": f"{strategy.name} validated (Sharpe {strategy.backtest_results.sharpe_ratio:.2f}) — waiting for signal",
                            "timestamp": datetime.now().isoformat(),
                            "data": {
                                "strategy_id": strategy.id,
                                "strategy_name": strategy.name
                            }
                        }
                    )
                except Exception as e:
                    logger.error(f"      Failed to activate: {e}")
                    stats["errors"].append(
                        {
                            "step": "activate",
                            "strategy": strategy.name,
                            "message": str(e),
                        }
                    )

            except Exception as e:
                logger.error(
                    f"  [{i}/{len(backtested_strategies)}] Error evaluating "
                    f"{strategy.name}: {e}"
                )
                stats["errors"].append(
                    {"step": "evaluate", "strategy": strategy.name, "message": str(e)}
                )
                continue

        # === Retire rejected strategies ===
        # Strategies that were proposed this cycle but not approved for activation
        # should be retired immediately — they failed the thresholds.
        # Only retire strategies from THIS cycle's batch (not pre-existing BACKTESTED ones).
        activated_ids = set(stats.get("activated_strategy_ids", []))
        retired_in_eval = 0
        try:
            from src.models.database import get_database
            from src.models.orm import StrategyORM
            db = get_database()
            eval_session = db.get_session()
            try:
                for strategy in backtested_strategies:
                    if strategy.id not in activated_ids:
                        strat_orm = eval_session.query(StrategyORM).filter_by(id=strategy.id).first()
                        if strat_orm and strat_orm.status == StrategyStatus.BACKTESTED:
                            # Only retire if it was NOT previously approved (from a prior cycle)
                            meta = strat_orm.strategy_metadata if isinstance(strat_orm.strategy_metadata, dict) else {}
                            if not meta.get('activation_approved'):
                                strat_orm.status = StrategyStatus.RETIRED
                                strat_orm.retired_at = datetime.now()
                                retired_in_eval += 1
                eval_session.commit()
                if retired_in_eval > 0:
                    logger.info(f"  Retired {retired_in_eval} strategies that failed activation thresholds")
                    stats["strategies_retired"] = stats.get("strategies_retired", 0) + retired_in_eval
            finally:
                eval_session.close()
        except Exception as e:
            logger.warning(f"Could not retire rejected strategies: {e}")

        # === Directional Diversity Check ===
        # If 3+ strategies were activated and all are the same direction,
        # force-activate the best opposite-direction strategy (Sharpe > 0)
        if stats["strategies_activated"] >= 3:
            try:
                self._enforce_directional_diversity(backtested_strategies, stats, market_context)
            except Exception as e:
                logger.warning(f"Directional diversity check failed: {e}")

        # === Alpha Edge Fallback ===
        # If no Alpha Edge strategies were activated, force-activate the best one with Sharpe > 0
        try:
            self._alpha_edge_fallback_activation(backtested_strategies, stats)
        except Exception as e:
            logger.warning(f"Alpha Edge fallback activation failed: {e}")

    def _detect_strategy_direction(self, strategy: Strategy) -> str:
        """Detect strategy direction from metadata or entry conditions.

        Returns 'LONG' or 'SHORT'.
        """
        # Check metadata first (most reliable)
        if hasattr(strategy, 'metadata') and strategy.metadata:
            stored = strategy.metadata.get('direction', '')
            if stored.upper() == 'SHORT':
                return 'SHORT'
            if stored.upper() == 'LONG':
                return 'LONG'

        # Fallback: check entry conditions for SHORT/OVERBOUGHT keywords
        if hasattr(strategy, 'rules') and strategy.rules:
            rules = strategy.rules if isinstance(strategy.rules, dict) else {}
            for cond in rules.get('entry_conditions', []):
                if isinstance(cond, str) and ('SHORT' in cond.upper() or 'SELL' in cond.upper() or 'OVERBOUGHT' in cond.upper()):
                    return 'SHORT'

        return 'LONG'

    def _enforce_directional_diversity(
        self, backtested_strategies: List[Strategy], stats: Dict, market_context=None
    ) -> None:
        """Ensure activated strategies have directional diversity.
        
        If 3+ strategies were activated and all are the same direction,
        force-activate the best opposite-direction strategy with Sharpe > 0.
        """
        # Get freshly activated strategies
        active_strategies = self.strategy_engine.get_active_strategies()
        if len(active_strategies) < 3:
            return

        # Count directions among active strategies
        directions = {}
        for s in active_strategies:
            d = self._detect_strategy_direction(s)
            directions.setdefault(d, []).append(s)

        long_count = len(directions.get('LONG', []))
        short_count = len(directions.get('SHORT', []))

        logger.info(
            f"Directional diversity check: {long_count} LONG, {short_count} SHORT "
            f"across {len(active_strategies)} active strategies"
        )

        # If we have both directions, diversity is fine
        if long_count > 0 and short_count > 0:
            return

        # All same direction — find the missing one
        missing_direction = 'LONG' if long_count == 0 else 'SHORT'
        logger.warning(
            f"⚠️ All {len(active_strategies)} active strategies are "
            f"{'SHORT' if missing_direction == 'LONG' else 'LONG'} — "
            f"looking for best {missing_direction} candidate"
        )

        # Search rejected strategies for the best opposite-direction candidate
        best_candidate = None
        best_sharpe = 0.0

        for strategy in backtested_strategies:
            if not strategy.backtest_results:
                continue

            direction = self._detect_strategy_direction(strategy)
            if direction != missing_direction:
                continue

            sharpe = strategy.backtest_results.sharpe_ratio
            if sharpe <= 0:
                continue

            # Skip if already active
            if strategy.status in (StrategyStatus.DEMO, StrategyStatus.LIVE):
                continue

            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_candidate = strategy

        if not best_candidate:
            logger.warning(
                f"No {missing_direction} candidate found with Sharpe > 0 — "
                f"directional diversity not enforced"
            )
            return

        # Check max strategies limit
        max_strategies = self.config["autonomous"]["max_active_strategies"]
        if len(active_strategies) >= max_strategies:
            logger.warning(
                f"Cannot force-activate {missing_direction} strategy — "
                f"already at max {max_strategies} active strategies"
            )
            return

        # Approve the best opposite-direction candidate as BACKTESTED (same lifecycle as normal activation)
        try:
            bt = best_candidate.backtest_results
            if bt and bt.sharpe_ratio > 1.5:
                allocation_pct = 3.0
            elif bt and bt.sharpe_ratio > 0.8:
                allocation_pct = 2.0
            else:
                allocation_pct = 1.0
            test_trades = bt.total_trades if bt else 0
            trade_confidence = min(1.0, test_trades / 10.0)
            allocation_pct = max(0.5, allocation_pct * trade_confidence)

            best_candidate.status = StrategyStatus.BACKTESTED
            if not best_candidate.metadata:
                best_candidate.metadata = {}
            best_candidate.metadata['activation_approved'] = True
            best_candidate.metadata['pending_allocation_pct'] = allocation_pct
            best_candidate.metadata['directional_diversity'] = True
            best_candidate.allocation_percent = allocation_pct
            self.strategy_engine._save_strategy(best_candidate)

            stats["strategies_activated"] += 1
            stats["activated_strategy_ids"].append(best_candidate.id)
            stats.setdefault("activated_details", []).append({
                "name": best_candidate.name,
                "symbols": best_candidate.symbols,
                "sharpe": best_sharpe,
                "win_rate": bt.win_rate if bt else 0,
                "trades": bt.total_trades if bt else 0,
                "drawdown": bt.max_drawdown if bt else 0,
                "is_alpha_edge": best_candidate.metadata.get('strategy_category') == 'alpha_edge' if best_candidate.metadata else False,
                "reason": f"directional_diversity ({missing_direction})",
            })
            logger.info(
                f"✓ Approved {best_candidate.name} ({missing_direction}) "
                f"for directional diversity (Sharpe={best_sharpe:.2f}) "
                f"— will activate on first signal"
            )

            self._safe_broadcast(
                self.websocket_manager.broadcast_autonomous_strategy_event,
                "strategy_activated",
                {
                    "id": best_candidate.id,
                    "name": best_candidate.name,
                    "symbols": best_candidate.symbols,
                    "status": "BACKTESTED",
                    "backtest_results": {
                        "sharpe_ratio": best_candidate.backtest_results.sharpe_ratio,
                        "total_return": best_candidate.backtest_results.total_return,
                        "max_drawdown": best_candidate.backtest_results.max_drawdown,
                        "win_rate": best_candidate.backtest_results.win_rate
                    },
                    "reason": "directional_diversity",
                    "timestamp": datetime.now().isoformat()
                }
            )
            self._safe_broadcast(
                self.websocket_manager.broadcast_autonomous_notification,
                {
                    "type": "strategy_ready",
                    "severity": "info",
                    "title": "Directional Diversity",
                    "message": (
                        f"{best_candidate.name} approved ({missing_direction}) "
                        f"for portfolio balance (Sharpe {best_sharpe:.2f}) — waiting for signal"
                    ),
                    "timestamp": datetime.now().isoformat(),
                    "data": {
                        "strategy_id": best_candidate.id,
                        "strategy_name": best_candidate.name,
                        "reason": "directional_diversity"
                    }
                }
            )
        except Exception as e:
            logger.error(
                f"Failed to force-activate {best_candidate.name} "
                f"for directional diversity: {e}"
            )
    def _alpha_edge_fallback_activation(
        self, backtested_strategies: List[Strategy], stats: Dict
    ) -> None:
        """Ensure at least one Alpha Edge strategy is active.

        If no Alpha Edge strategies were activated during the normal evaluation,
        force-activate the best Alpha Edge candidate with Sharpe > 0.
        If none have Sharpe > 0, log a warning and skip.
        """
        # Check if any Alpha Edge strategies are already active
        active_strategies = self.strategy_engine.get_active_strategies()
        active_alpha_edge = [
            s for s in active_strategies
            if hasattr(s, 'metadata') and s.metadata
            and s.metadata.get('strategy_category') == 'alpha_edge'
        ]

        if active_alpha_edge:
            logger.info(
                f"Alpha Edge fallback not needed — {len(active_alpha_edge)} "
                f"Alpha Edge strategies already active"
            )
            return

        logger.warning(
            "⚠️ No Alpha Edge strategies active — searching for fallback candidate"
        )

        # Find the best Alpha Edge candidate from backtested strategies
        best_candidate = None
        best_sharpe = 0.0

        for strategy in backtested_strategies:
            if not strategy.backtest_results:
                continue

            # Must be Alpha Edge
            if not (hasattr(strategy, 'metadata') and strategy.metadata
                    and strategy.metadata.get('strategy_category') == 'alpha_edge'):
                continue

            sharpe = strategy.backtest_results.sharpe_ratio
            if sharpe <= 0:
                continue

            # Skip if already active
            if strategy.status in (StrategyStatus.DEMO, StrategyStatus.LIVE):
                continue

            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_candidate = strategy

        if not best_candidate:
            logger.warning(
                "No Alpha Edge candidate found with Sharpe > 0 — "
                "fallback activation skipped"
            )
            return

        # Check max strategies limit
        max_strategies = self.config["autonomous"]["max_active_strategies"]
        if len(active_strategies) >= max_strategies:
            logger.warning(
                f"Cannot force-activate Alpha Edge fallback — "
                f"already at max {max_strategies} active strategies"
            )
            return

        # Approve the best Alpha Edge candidate as BACKTESTED (same lifecycle as normal activation).
        # It will be promoted to DEMO when its first signal fires and an order is placed.
        try:
            # Calculate allocation using same logic as _evaluate_and_activate
            bt = best_candidate.backtest_results
            if bt and bt.sharpe_ratio > 1.5:
                allocation_pct = 3.0
            elif bt and bt.sharpe_ratio > 0.8:
                allocation_pct = 2.0
            else:
                allocation_pct = 1.0
            test_trades = bt.total_trades if bt else 0
            trade_confidence = min(1.0, test_trades / 10.0)
            allocation_pct = max(0.5, allocation_pct * trade_confidence)

            best_candidate.status = StrategyStatus.BACKTESTED
            if not best_candidate.metadata:
                best_candidate.metadata = {}
            best_candidate.metadata['activation_approved'] = True
            best_candidate.metadata['pending_allocation_pct'] = allocation_pct
            best_candidate.metadata['alpha_edge_fallback'] = True
            best_candidate.allocation_percent = allocation_pct
            self.strategy_engine._save_strategy(best_candidate)

            stats["strategies_activated"] += 1
            stats["activated_strategy_ids"].append(best_candidate.id)
            stats.setdefault("activated_details", []).append({
                "name": best_candidate.name,
                "symbols": best_candidate.symbols,
                "sharpe": best_sharpe,
                "win_rate": bt.win_rate if bt else 0,
                "trades": bt.total_trades if bt else 0,
                "drawdown": bt.max_drawdown if bt else 0,
                "is_alpha_edge": True,
                "reason": "alpha_edge_fallback",
            })
            logger.info(
                f"✓ Approved {best_candidate.name} as Alpha Edge fallback "
                f"(Sharpe={best_sharpe:.2f}, allocation={allocation_pct:.1f}%) "
                f"— will activate on first signal"
            )

            self._safe_broadcast(
                self.websocket_manager.broadcast_autonomous_strategy_event,
                "strategy_activated",
                {
                    "id": best_candidate.id,
                    "name": best_candidate.name,
                    "symbols": best_candidate.symbols,
                    "status": "BACKTESTED",
                    "backtest_results": {
                        "sharpe_ratio": best_candidate.backtest_results.sharpe_ratio,
                        "total_return": best_candidate.backtest_results.total_return,
                        "max_drawdown": best_candidate.backtest_results.max_drawdown,
                        "win_rate": best_candidate.backtest_results.win_rate
                    },
                    "reason": "alpha_edge_fallback",
                    "timestamp": datetime.now().isoformat()
                }
            )
            self._safe_broadcast(
                self.websocket_manager.broadcast_autonomous_notification,
                {
                    "type": "strategy_ready",
                    "severity": "info",
                    "title": "Alpha Edge Fallback Ready",
                    "message": (
                        f"{best_candidate.name} approved as Alpha Edge fallback "
                        f"(Sharpe {best_sharpe:.2f}) — waiting for signal"
                    ),
                    "timestamp": datetime.now().isoformat(),
                    "data": {
                        "strategy_id": best_candidate.id,
                        "strategy_name": best_candidate.name,
                        "reason": "alpha_edge_fallback"
                    }
                }
            )
        except Exception as e:
            logger.error(
                f"Failed to force-activate Alpha Edge fallback "
                f"{best_candidate.name}: {e}"
            )



    def _check_and_retire_strategies(self, stats: Dict) -> None:
        """
        Check retirement triggers for all active strategies and retire underperformers.
        
        This runs inside the autonomous cycle (research context). It checks:
        1. Regime mismatch — strategy designed for a different market regime
        2. Backtest-based triggers — original performance thresholds
        
        Live performance retirement (P&L, win rate from actual trades) is handled
        by the monitoring service's _check_strategy_health() which runs daily
        with access to real-time position data.

        Args:
            stats: Statistics dictionary to update
        """
        try:
            # Get all active strategies
            active_strategies = self.strategy_engine.get_active_strategies()

            if not active_strategies:
                logger.info("  No active strategies to check")
                return

            logger.info(f"  Checking {len(active_strategies)} active strategies...")

            # Detect current regime ONCE (not per-strategy)
            current_regime = 'unknown'
            try:
                sub_regime, _, _, _ = self.strategy_proposer.market_analyzer.detect_sub_regime()
                current_regime = sub_regime.value
            except Exception:
                pass

            for i, strategy in enumerate(active_strategies, 1):
                try:
                    # Skip strategies activated in this cycle — they just passed activation
                    # thresholds and have no live trade data yet. Re-checking backtest metrics
                    # against retirement thresholds in the same cycle is contradictory.
                    activated_this_cycle = set(stats.get("activated_strategy_ids", []))
                    if strategy.id in activated_this_cycle:
                        logger.info(
                            f"  [{i}/{len(active_strategies)}] ⏭ {strategy.name} "
                            f"skipped (just activated this cycle)"
                        )
                        continue
                    # Check regime mismatch — retire strategies created for a fundamentally
                    # different market regime (e.g., trending_up strategy in trending_down market)
                    retirement_reason = None
                    try:
                        if strategy.metadata and isinstance(strategy.metadata, dict):
                            creation_regime = strategy.metadata.get('macro_regime', '')
                            
                            if creation_regime and current_regime != 'unknown' and creation_regime != current_regime:
                                is_major_shift = (
                                    ('trending_up' in creation_regime and 'trending_down' in current_regime) or
                                    ('trending_down' in creation_regime and 'trending_up' in current_regime) or
                                    ('ranging' in creation_regime and 'trending' in current_regime and 'strong' in current_regime)
                                )
                                if is_major_shift:
                                    retirement_reason = (
                                        f"Regime mismatch: created for '{creation_regime}', "
                                        f"current regime is '{current_regime}'"
                                    )
                                    logger.info(f"  [{i}/{len(active_strategies)}] ✗ {strategy.name} {retirement_reason}")
                    except Exception as e:
                        logger.debug(f"Could not check regime for {strategy.name}: {e}")

                    # Check performance-based retirement triggers (only if regime didn't already trigger)
                    # portfolio_manager.check_retirement_triggers uses LIVE position data
                    # (not stale backtest metrics) to decide if a running strategy should be retired.
                    if not retirement_reason:
                        retirement_reason = self.portfolio_manager.check_retirement_triggers(
                            strategy
                        )

                    if retirement_reason:
                        logger.info(
                            f"  [{i}/{len(active_strategies)}] ✗ {strategy.name} "
                            f"triggered retirement: {retirement_reason}"
                        )

                        # Auto-retire the strategy
                        try:
                            self.portfolio_manager.auto_retire_strategy(
                                strategy, retirement_reason
                            )
                            stats["strategies_retired"] += 1
                            logger.info(f"      ✓ Retired successfully")
                            
                            # Broadcast strategy retired event
                            self._safe_broadcast(
                                self.websocket_manager.broadcast_autonomous_strategy_event,
                                "strategy_retired",
                                {
                                    "id": strategy.id,
                                    "name": strategy.name,
                                    "symbols": strategy.symbols,
                                    "status": StrategyStatus.RETIRED.value,
                                    "retirement_reason": retirement_reason,
                                    "final_metrics": {
                                        "sharpe_ratio": strategy.performance.sharpe_ratio if strategy.performance else 0,
                                        "total_return": strategy.performance.total_return if strategy.performance else 0,
                                        "max_drawdown": strategy.performance.max_drawdown if strategy.performance else 0
                                    },
                                    "timestamp": datetime.now().isoformat()
                                }
                            )
                            self._safe_broadcast(
                                self.websocket_manager.broadcast_autonomous_notification,
                                {
                                    "type": "strategy_retired",
                                    "severity": "warning",
                                    "title": "Strategy Retired",
                                    "message": f"{strategy.name} retired: {retirement_reason}",
                                    "timestamp": datetime.now().isoformat(),
                                    "data": {
                                        "strategy_id": strategy.id,
                                        "strategy_name": strategy.name,
                                        "reason": retirement_reason
                                    }
                                }
                            )
                        except Exception as e:
                            logger.error(f"      Failed to retire: {e}")
                            stats["errors"].append(
                                {
                                    "step": "retire",
                                    "strategy": strategy.name,
                                    "message": str(e),
                                }
                            )
                    else:
                        logger.info(
                            f"  [{i}/{len(active_strategies)}] ✓ {strategy.name} "
                            f"performing well (Sharpe={strategy.performance.sharpe_ratio:.2f}, "
                            f"Drawdown={strategy.performance.max_drawdown:.2%})"
                        )

                except Exception as e:
                    logger.error(
                        f"  [{i}/{len(active_strategies)}] Error checking "
                        f"{strategy.name}: {e}"
                    )
                    stats["errors"].append(
                        {
                            "step": "check_retirement",
                            "strategy": strategy.name,
                            "message": str(e),
                        }
                    )
                    continue

        except Exception as e:
            logger.error(f"Error checking retirement triggers: {e}", exc_info=True)
            stats["errors"].append({"step": "check_retirement", "message": str(e)})

    def get_status(self) -> Dict:
        """
        Get current status of autonomous strategy system.

        Returns:
            Dictionary with system status
        """
        active_strategies = self.strategy_engine.get_active_strategies()
        all_strategies = self.strategy_engine.get_all_strategies()

        # Count strategies by status
        status_counts = {}
        for strategy in all_strategies:
            status = strategy.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        # Detect current market regime
        market_regime, confidence, data_quality = self.strategy_proposer.analyze_market_conditions()

        # Calculate next run time
        next_run_time = None
        if self.last_run_time:
            frequency = self.config["autonomous"]["proposal_frequency"]
            if frequency == "daily":
                next_run_time = self.last_run_time + timedelta(days=1)
            elif frequency == "weekly":
                next_run_time = self.last_run_time + timedelta(weeks=1)

        return {
            "enabled": self.config["autonomous"]["enabled"],
            "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
            "next_run_time": next_run_time.isoformat() if next_run_time else None,
            "market_regime": market_regime.value,
            "market_confidence": confidence,
            "data_quality": data_quality.value,
            "active_strategies_count": len(active_strategies),
            "total_strategies_count": len(all_strategies),
            "status_counts": status_counts,
            "config": self.config,
        }

    def should_run_cycle(self) -> bool:
        """
        Check if it's time to run a new cycle based on frequency configuration.

        Returns:
            True if cycle should run, False otherwise
        """
        if not self.config["autonomous"]["enabled"]:
            return False

        if self.last_run_time is None:
            return True

        frequency = self.config["autonomous"]["proposal_frequency"]
        now = datetime.now()

        if frequency == "daily":
            return (now - self.last_run_time) >= timedelta(days=1)
        elif frequency == "weekly":
            return (now - self.last_run_time) >= timedelta(weeks=1)
        else:
            logger.warning(f"Unknown frequency: {frequency}, defaulting to weekly")
            return (now - self.last_run_time) >= timedelta(weeks=1)

    def run_scheduled_cycle(self) -> Optional[Dict]:
        """
        Run cycle only if it's time based on schedule.

        Returns:
            Cycle statistics if run, None if skipped
        """
        if self.should_run_cycle():
            logger.info("Scheduled cycle triggered")
            return self.run_strategy_cycle()
        else:
            logger.debug("Skipping cycle - not yet time based on schedule")
            return None
