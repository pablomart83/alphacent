# AlphaCent Frontend — Rebuild Requirements Specification

> Greenfield frontend for the AlphaCent autonomous trading platform. No code, components, or patterns from the current frontend carry forward. Every decision in this document is final. Nothing is TBD. This document answers every question a developer needs to write the first line of code.

**Backend state at spec time (2026-05-10):** FastAPI/Python, ~80 REST endpoints, WebSocket manager broadcasting 16 event types. DEMO account ~$491K equity, 65 open positions, regime `trending_up_strong`. LIVE Agent Portfolio $10K virtual / $1K real / 10% mirror ratio, 0 live positions, `live_trading.enabled=true`. Strategies: 50 PAPER + 66 BACKTESTED. Service healthy, errors.log clean. Last commit: `d76d34c`.

---

## Table of Contents

1. [Phase 1 — Feature Inventory (extracted from current system)](#phase-1--feature-inventory)
   - 1A. Backend API surface
   - 1B. WebSocket events
   - 1C. Pages — capabilities and gaps
   - 1D. Data model
   - 1E. Current dependencies
2. [Phase 2 — Technology Decisions and Design Language](#phase-2--technology-decisions-and-design-language)
3. [Phase 3 — Platform Design](#phase-3--platform-design)
   - 3A. Design system
   - 3B. Information architecture (5 surfaces: Command · Book · Strategies · Guard · Research)
   - 3C. Component library
   - 3D. Technical stack (final)
   - 3E. Implementation plan
4. [Appendix — Reference tables](#appendix)


---

# Phase 1 — Feature Inventory

## 1A. Backend API surface

Every endpoint exposed by the FastAPI backend. Grouped by router. Frequency column: `RT` (real-time, push by WS), `P` (poll), `O` (on-demand, user action), `L` (lazy, first visit only).

### Account (`/account`)

| Method | Path | Key query params | Response shape (key fields) | Business concept | Freq |
|---|---|---|---|---|---|
| GET | `/account` | `mode` (DEMO\|LIVE) | `AccountInfoResponse` — balance, equity, buying_power, margin_used, margin_available, daily_pnl, total_pnl, positions_count, updated_at | Current account status | P 30s + WS |
| GET | `/account/positions` | `mode` | `PositionsResponse` — positions[], total_count, pending_count, market_open | Open positions list | P 30s + WS `position_update` |
| GET | `/account/positions/closed` | `mode`, `limit` | `PositionsResponse` | Closed positions history | L + O |
| GET | `/account/positions/pending-open` | `mode` | `PositionsResponse` | Orders waiting for market open | P 60s |
| GET | `/account/positions/pending-closures` | `mode` | `PositionsResponse` | Positions flagged for closure awaiting approval | P 60s + WS |
| GET | `/account/positions/fundamental-alerts` | `mode` | `{ success, alerts[], count }` — alerts with flag_reason, flag_timestamp, fundamental_detail | Fundamental-based exit flags | P 60s |
| GET | `/account/positions/{position_id}` | `mode` | `PositionResponse` | Single position detail | O |
| POST | `/account/positions/{position_id}/approve-closure` | `mode` | `{ success, message, position_id }` | Approve a flagged closure | O |
| POST | `/account/positions/approve-closures-bulk` | `mode`, body `{position_ids}` | `{ success_count, fail_count, errors }` | Bulk approve closures | O |
| POST | `/account/positions/{position_id}/dismiss-closure` | `mode` | `{ success, message }` | Keep position open despite flag | O |
| POST | `/account/positions/{position_id}/dismiss-alert` | `mode` | `{ success, message }` | Dismiss fundamental alert | O |
| POST | `/account/positions/sync` | `mode` | `{ synced, added, updated }` | Force eToro position re-sync | O |
| POST | `/account/positions/close` | `mode`, body `{position_ids}` | `{ message, closed_count, failed }` | Close selected positions | O |
| POST | `/account/positions/close-all` | `mode` | `{ message, closed_count }` | Close every open position | O |
| POST | `/account/positions/delete-closed` | body | `{ deleted }` | Hard-delete closed position records | O |
| GET | `/account/positions/{symbol}/detail` | `mode` | `PositionDetailResponse` | Aggregated detail for symbol (all positions, history, chart data) | L |
| GET | `/account/dashboard/summary` | `mode`, `interval` (1d\|4h\|1h) | pnl_periods, equity_curve, drawdown_data, sector_exposure, market_regime, health_score, quick_stats, account_balance, account_equity, available_cash, total_unrealized_pnl, total_invested | Overview page hero payload | P 30s + WS |
| GET | `/account/metrics-bar` | `mode` | Compact metrics for sticky top bar | Top nav metrics strip | P 10s + WS |

### Orders (`/orders`)

| Method | Path | Key query params | Response shape | Business concept | Freq |
|---|---|---|---|---|---|
| GET | `/orders` | `mode`, `status_filter`, `limit` | `OrdersResponse` — orders[], total_count; each has side, order_type, quantity, price, status, slippage, fill_time_seconds, order_action (entry\|close\|retirement) | Order history | P 15s + WS `order_update` |
| GET | `/orders/execution-quality` | `mode`, `period` (1D\|1W\|1M\|3M) | avg_slippage, fill_rate, avg_fill_time, rejection_rate, total_orders, filled_orders, rejected_orders, pending_orders, slippage_by_strategy, rejection_reasons | Execution quality analytics | L + O |
| GET | `/orders/{order_id}` | `mode` | `OrderResponse` | Single order | O |
| POST | `/orders` | `mode`, body `PlaceOrderRequest` | `{ success, message, order_id }` | Manual order entry | O |
| DELETE | `/orders/{order_id}` | `mode` | `{ success, message, order_id }` | Cancel pending/submitted order (with eToro reconciliation) | O |
| DELETE | `/orders/{order_id}/permanent` | `mode` | `{ success, message, order_id }` | Hard-delete terminal order | O |
| POST | `/orders/bulk-delete` | `mode`, body `{order_ids}` | `{ success_count, fail_count, deleted_order_ids, failed_order_ids }` | Bulk delete | O |
| POST | `/orders/{order_id}/close-position` | `mode` | `{ success, message, order_id, position_closed }` | Close position created by a filled order | O |
| POST | `/orders/sync` | `mode` | `{ synced, added, updated }` | Force eToro order re-sync | O |

### Strategies (`/strategies`)

| Method | Path | Key query params | Response shape | Business concept | Freq |
|---|---|---|---|---|---|
| GET | `/strategies` | `mode`, `status_filter`, `include_retired`, `slim` | `StrategiesResponse` — strategies[], total_count; each has status (PROPOSED\|BACKTESTED\|PAPER\|LIVE\|RETIRED), symbols, allocation_percent, risk_params, performance_metrics (sharpe, total_return, max_dd, win_rate, trades, live_orders, open_positions, unrealized_pnl, health_score 0-5, decay_score 0-10), walk_forward_results, metadata (conviction_score, template_name, market_regime, strategy_category), alpha_vs_spy, deployed_capital, allocated_capital, traded_symbols | Strategy library | P 60s + WS `strategy_update` |
| POST | `/strategies` | body | `StrategyActionResponse` | Create manual strategy | O |
| GET | `/strategies/templates` | `market_regime?` | `TemplatesListResponse` — templates[] with name, description, market_regimes, indicators, entry_rules, exit_rules, success_rate, usage_count, strategy_type, direction, asset_classes, expected_trade_frequency, expected_holding_period, risk_reward_ratio, enabled, active_strategies, avg_sharpe, avg_win_rate, avg_return, total_pnl, best_symbol, worst_symbol, last_proposed, last_activated, is_intraday, is_4h, interval, activated_count, traded_count, proposed_count, strategy_category | Template library | L |
| PUT | `/strategies/templates/{template_name}/toggle` | body `{enabled}` | `StrategyActionResponse` | Enable/disable template | O |
| PUT | `/strategies/templates/bulk-toggle` | body | `StrategyActionResponse` | Bulk template toggle | O |
| GET | `/strategies/symbols` | — | `SymbolsListResponse` — per-symbol Current view (active_strategies, usage_count) + Lifetime view (traded_count, win_rate, total_pnl, best_template) | Symbol analytics | L |
| GET | `/strategies/template-rankings` | `mode` | templates ranked by live performance | Template performance board | L |
| GET | `/strategies/blacklisted-combos` | — | rejection blacklist entries with regime & expiry | Rejection audit | L |
| GET | `/strategies/idle-demotions` | — | strategies demoted for inactivity | Demotion audit | L |
| GET | `/strategies/{strategy_id}` | `mode` | `StrategyResponse` (full) | Strategy detail | O |
| PUT | `/strategies/{strategy_id}` | body | `StrategyActionResponse` | Update strategy | O |
| DELETE | `/strategies/{strategy_id}` | — | `StrategyActionResponse` | Retire strategy | O |
| DELETE | `/strategies/{strategy_id}/permanent` | — | `StrategyActionResponse` | Hard-delete | O |
| POST | `/strategies/{strategy_id}/activate` | — | `StrategyActionResponse` | Promote to PAPER | O |
| POST | `/strategies/{strategy_id}/deactivate` | — | `StrategyActionResponse` | Pause | O |
| GET | `/strategies/{strategy_id}/performance` | — | `PerformanceMetricsResponse` | Single strategy perf | O |
| POST | `/strategies/{strategy_id}/backtest` | body `{start_date?, end_date?}` | `BacktestResultsResponse` — total_return, sharpe, sortino, max_dd, win_rate, avg_win, avg_loss, total_trades, backtest_period, gross_return, net_return, total_transaction_costs, slippage_cost, spread_cost | Re-run backtest | O |
| PUT | `/strategies/{strategy_id}/allocation` | body `{allocation_percent}` | `StrategyActionResponse` | Adjust allocation | O |
| POST | `/strategies/vibe-code/translate` | body `{natural_language}` | `TradingCommandResponse` | Natural-language → structured trading command | O |
| POST | `/strategies/bootstrap` | body `BootstrapRequest` | `BootstrapResponse` | Batch-generate strategies | O |
| POST | `/strategies/generate` | body `GenerateStrategyRequest` | `StrategyResponse` | Generate strategy from prompt + constraints | O |
| GET | `/strategies/autonomous/status` | — | `AutonomousStatusResponse` — enabled, market_regime, market_confidence, data_quality, last_cycle_time, next_scheduled_run, cycle_duration, cycle_stats (proposals/backtested/activated/retired counts), portfolio_health, template_stats[] | Autonomous system state | P 10s + WS `autonomous_status` |
| POST | `/strategies/autonomous/trigger` | body `TriggerCycleRequest` (filters) | `TriggerCycleResponse` — cycle_id | Fire cycle manually | O |
| GET | `/strategies/autonomous/config` | — | `AutonomousConfigResponse` | Read autonomous config | L |
| PUT | `/strategies/autonomous/config` | body `UpdateConfigRequest` | `UpdateConfigResponse` | Write autonomous config (persists to `autonomous_trading.yaml` on EC2) | O |
| GET | `/strategies/autonomous/walk-forward-analytics` | `mode` | WF analytics per family & timeframe | L |
| GET | `/strategies/proposals` | `page`, `limit`, filters | `ProposalsListResponse` | Proposal history | L |
| GET | `/strategies/retirements` | `page`, `limit` | `RetirementsListResponse` | Retirement history | L |
| GET | `/strategies/categories` | — | `CategoriesResponse` | Strategy category taxonomy | L |
| GET | `/strategies/types` | — | `TypesResponse` | Strategy type taxonomy | L |
| POST | `/strategies/reset` | — | `ResetStrategiesResponse` | Wipe and reset (admin) | O |
| GET | `/strategies/risk-attribution` | — | risk contribution per strategy | L |
| GET | `/strategies/graduation-queue` | — | candidates for promotion to LIVE with Sharpe, win_rate, trades, qualification_ratio | P 60s |
| POST | `/strategies/{strategy_id}/graduate` | body `{symbol, position_size, sl_pct, tp_pct, conviction_min, notes}` | `{success, live_strategy_id}` | Graduate (template, symbol) to live | O |
| POST | `/strategies/{strategy_id}/reject-graduation` | body `{symbol, reason}` | `{success}` | Reject graduation (14-day cooldown) | O |
| GET | `/strategies/live` | — | live authorizations list | P 60s |

### Control (`/control`)

| Method | Path | Response shape | Business concept | Freq |
|---|---|---|---|---|
| GET | `/control/system/status` | `SystemStatusResponse` — state (ACTIVE\|PAUSED\|STOPPED\|EMERGENCY_HALT), timestamp, active_strategies, open_positions, reason, uptime_seconds, last_signal_generated, last_order_executed | System state | P 15s + WS `system_state` |
| GET | `/control/system/sessions` | `SessionHistoryResponse` | Past trading sessions (empty today) | L |
| POST | `/control/system/start` | `StateChangeResponse` | Start autonomous trading | O |
| POST | `/control/system/pause` | — | Pause (no new signals; keep positions) | O |
| POST | `/control/system/stop` | — | Stop | O |
| POST | `/control/system/resume` | — | Resume from paused | O |
| POST | `/control/system/reset` | — | Reset from EMERGENCY_HALT | O |
| POST | `/control/kill-switch` | `KillSwitchResponse` — positions_closed, orders_cancelled | Emergency halt, close all | O (confirm) |
| POST | `/control/circuit-breaker/reset` | — | Clear circuit breaker | O |
| POST | `/control/rebalance` | — | Manual rebalance | O |
| GET | `/control/services` | — | Always empty (no external deps currently) | — |
| GET | `/control/services/{service_name}/health` | — | Service health | — |
| POST | `/control/services/{service_name}/start` / `/stop` | — | Service lifecycle | O |
| GET | `/control/autonomous/schedules` | `ScheduleSlotsResponse` — slots[] with id, enabled, days, hour, minute, next_run | Multi-slot scheduler | L |
| POST | `/control/autonomous/schedules` | body | Update schedule slots | O |
| GET/POST | `/control/autonomous/schedule` | — | Legacy single-slot endpoints (deprecated, keep for BC) | — |
| GET | `/control/autonomous/cycles` | `limit` | Cycle history | P 60s |
| POST | `/control/autonomous/cycles/delete` | body | Delete cycle records | O |
| POST | `/control/autonomous/clear-blacklists` | — | Clear rejection blacklist (admin) | O |
| GET | `/control/sync/status` | `SyncStatusResponse` | Monitoring sync summary | P 30s |
| GET | `/control/system-health` | `SystemHealthData` — monitoring_service (running, sub_tasks[] with last_run, duration_s, status), etoro_api (error_rate_5m, avg_response_ms, circuit_breaker_state), circuit_breakers[], trading_gates[] (kill_switch, market_hours, vix_gate, rejection_blacklist, freshness_sla — each with blocking flag), background_threads, data_freshness | System Health page hero | P 15s + WS `system_health` |

### Performance (`/performance`)

| Method | Path | Query | Response | Freq |
|---|---|---|---|---|
| GET | `/performance/metrics` | `period`, `strategy_id?` | sharpe (value+change), total_return, max_drawdown, win_rate, portfolio_history[], strategy_contributions[] | P on period change |
| GET | `/performance/portfolio` | — | strategies[] with allocation & performance, correlation_matrix, risk_metrics (VaR, max_position_size, diversification_score, beta, avg_correlation), total_value | L |
| GET | `/performance/history` | `period` | events[], template_performance[], regime_analysis[] | L |

### Analytics (`/analytics`)

| Method | Path | Query | Response | Freq |
|---|---|---|---|---|
| GET | `/analytics/strategy-attribution` | `mode`, `period` | per-strategy contribution to portfolio return | L |
| GET | `/analytics/trade-analytics` | `mode`, `period` | win/loss distribution, avg_win, avg_loss, profit_factor, avg_holding_time_hours, largest_win, largest_loss, pnl_by_day, pnl_by_hour | L |
| GET | `/analytics/regime-analysis` | `mode` | per-regime strategy performance | L |
| GET | `/analytics/regime-comprehensive` | — | current_regimes (per asset class), performance_by_regime, regime_transitions, strategy_regime_performance (heatmap data), market_context (VIX, yield curve, rates), crypto_cycle, carry_rates, market_quality (score+grade) | L |
| GET | `/analytics/performance` | `mode`, `period`, `interval` (1d\|4h\|1h) | `PerformanceAnalyticsResponse` — total_return, sharpe, sortino, max_drawdown, win_rate, profit_factor, equity_curve[] (with realized cumulative), monthly_returns, returns_distribution, daily_returns_count | L (primary analytics feed) |
| GET | `/analytics/correlation-matrix` | `mode`, `period` | `CorrelationMatrixResponse` — matrix cells (x, y, value), strategies[], avg_correlation, diversification_score | L |
| GET | `/analytics/trade-journal` | `strategy_id?`, pagination | trade_journal rows with entry/exit price/time, reason, pnl, MAE/MFE, conviction_score, ml_confidence, regime, sector | L |
| GET | `/analytics/trade-journal/analytics` | `strategy_id?` | aggregated KPIs | L |
| GET | `/analytics/trade-journal/patterns` | `start_date?` | best/worst patterns, recommendations | L |
| GET | `/analytics/trade-journal/export` | filters | CSV download | O |
| GET | `/analytics/alpha-edge/fundamental-stats` | `mode` | fundamental filter hit/miss stats | L |
| GET | `/analytics/alpha-edge/ml-stats` | `mode` | ML filter confidence distribution | L |
| GET | `/analytics/alpha-edge/conviction-distribution` | `mode` | conviction bucket histogram with P&L overlay | L |
| GET | `/analytics/alpha-edge/template-performance` | `mode` | per-template live perf with sample size | L |
| GET | `/analytics/alpha-edge/transaction-cost-savings` | `mode` | slippage / commission avoided by filters | L |
| GET | `/analytics/cio-dashboard` | `mode` | CIO-style summary (live P&L, top winners/losers, graduation signals, divergence) | L |
| GET | `/analytics/performance-stats` | `mode` | extended perf table | L |
| GET | `/analytics/spy-benchmark` | `period` | SPY daily series for overlay | L |
| GET | `/analytics/rolling-statistics` | `mode` | rolling sharpe, beta, alpha, volatility, probabilistic_sharpe, information_ratio, treynor_ratio, tracking_error | L |
| GET | `/analytics/performance-attribution` | — | per-sector allocation/selection/interaction effects | L |

### Risk (`/risk`)

| Method | Path | Query | Response | Freq |
|---|---|---|---|---|
| GET | `/risk/metrics` | `mode` | portfolio_var, current_drawdown, max_drawdown, leverage, margin_utilization, portfolio_beta, max_position_size, total_exposure, risk_score (safe\|warning\|danger), risk_reasons[], risk_breakdown (per strategy) | P 30s |
| GET | `/risk/history` | `mode`, `period` | history[] with var, drawdown, leverage, beta | L |
| GET | `/risk/limits` | `mode` | `RiskLimitsResponse` | L |
| PUT | `/risk/limits` | body | update limits | O |
| GET | `/risk/alerts` | `mode` | active + recent alerts (var/drawdown/exposure breaches, monitoring alerts) | P 60s |
| GET | `/risk/positions` | `mode` | per-position risk with risk_level (low\|medium\|high), risk_amount, risk_percent | P 60s |
| GET | `/risk/advanced` | `mode` | correlated_pairs, VaR (95/99, historical sim), stress_tests[], margin_utilization with zone (green\|amber\|red), sector_exposure, asset_class_exposure, directional_exposure (long/short net, limit_pct) | L |
| GET | `/risk/cio-risk` | `mode` | CIO risk board summary | L |

### Signals (`/signals`)

| Method | Path | Query | Response | Freq |
|---|---|---|---|---|
| GET | `/signals/recent` | `mode`, `limit` | signals[] with signal_id, strategy_id, symbol, side, signal_type (ENTRY\|EXIT), decision (ACCEPTED\|REJECTED), rejection_reason, created_at, metadata (conviction_score, stage, cycle_id, template_name); summary: total, accepted, rejected, acceptance_rate, rejection_reasons[] by category | P 30s + WS `signal_generated` |

### Config (`/config`)

| Method | Path | Query / body | Response | Freq |
|---|---|---|---|---|
| POST | `/config/credentials` | body `{mode, public_key, user_key}` | `CredentialsResponse` | O |
| GET | `/config/connection-status` | `mode` | `{ connected, mode, message }` (live-tests eToro) | O |
| GET | `/config/risk` | `mode` | `RiskConfigResponse` — includes position-management fields (trailing_stop_enabled, trailing_stop_activation_pct, trailing_stop_distance_pct, partial_exit_levels, correlation_adjustment_enabled/threshold/reduction_factor, regime_based_sizing_enabled/multipliers, cancel_stale_orders, stale_order_hours) | L |
| PUT | `/config/risk` | body | saves to DB + JSON fallback | O |
| GET | `/config` | — | App config (trading_mode, general) | L |
| PUT | `/config` | body | Update app config | O |
| GET | `/config/alpha-edge` | — | fundamental filters, ML filter, trading frequency, template enablement | L |
| PUT | `/config/alpha-edge` | body | update | O |
| GET | `/config/alpha-edge/api-usage` | — | FMP & Alpha Vantage quota status, cache stats | L |
| GET | `/config/autonomous` | — | full autonomous config including min_sharpe/WR/return thresholds per asset & timeframe, WF params, direction-aware thresholds per regime × direction × metric, adaptive risk params, conviction thresholds (demo + live), retirement triggers | L (write-through by Settings page) |
| PUT | `/config/autonomous` | body | persists to YAML + DB | O |
| GET | `/config/live-trading` | — | live config (enabled, base_risk_pct, min_order_size, max_order_size, symbol_cap, mirror_ratio, conviction_threshold, conviction_threshold_crypto) | L |
| PUT | `/config/live-trading` | body | update | O |

### Live (`/live`)

| Method | Path | Response | Freq |
|---|---|---|---|
| GET | `/live/summary` | virtual_balance, virtual_equity, real_equity, mirror_ratio, unrealized_pnl_virtual/real, today_pnl_virtual/real, open_positions, deployed_capital_virtual/real, deployed_pct, active_live_authorizations, live_enabled | P 15s + WS |
| GET | `/live/divergence` | divergence[] — per live authorization: paper_sharpe vs live_sharpe, divergence_pct, divergence_flag (live <50% of paper) | P 60s |
| POST | `/live/strategies/{live_id}/retire` | `{success, retired_at}` | O |
| POST | `/live/positions/{position_id}/close` | `{success, message}` | O |

### Alerts (`/alerts`)

| Method | Path | Response | Freq |
|---|---|---|---|
| GET | `/alerts/config` | AlertConfig (pnl_loss, pnl_gain, drawdown, position_loss, margin thresholds + browser_push_enabled) | L |
| PUT | `/alerts/config` | updated config | O |
| GET | `/alerts/history` | `limit`, `unread_only`, `severity` filters; returns alerts[], unread_count, total | P 60s |
| POST | `/alerts/history/{alert_id}/read` | `{success}` | O |
| POST | `/alerts/history/read-all` | `{success}` | O |
| POST | `/alerts/history/{alert_id}/acknowledge` | `{success}` (for critical) | O |
| DELETE | `/alerts/history` | `{success}` (clear all) | O |

### Market data (`/market-data`)

| Method | Path | Response | Freq |
|---|---|---|---|
| GET | `/market-data/symbol-aliases` | display→eToro symbol map | L (static) |
| GET | `/market-data/smart-portfolios` | eToro Smart Portfolios | L |
| GET | `/market-data/tradeable-symbols` | `mode` | symbols[] + default_watchlist | L |
| GET | `/market-data/data-quality` | all symbols quality reports (score, issues, metrics) | L |
| GET | `/market-data/data-quality/{symbol}` | single symbol report | O |
| GET | `/market-data/{symbol}` | `mode` | `QuoteResponse` (price, bid, ask, volume, change, change_percent, source) | O (chart) |
| GET | `/market-data/{symbol}/historical` | `interval`, `start`, `end`, `mode` | OHLCV bars | O (chart) |
| GET | `/market-data/social-insights/{symbol}` | sentiment, trending_rank, popularity, pro_investor_positions | O |

### Dashboard widgets (`/dashboard`)

| Method | Path | Response | Freq |
|---|---|---|---|
| GET | `/dashboard/top-movers` | `mode` | gainers[5] + losers[5] from open positions by unrealised pnl% | P 30s |
| GET | `/dashboard/recent-signals` | `mode`, `limit` | signals[] with conviction, direction, timestamp | P 30s |
| GET | `/dashboard/strategy-alerts` | `mode`, `limit` | lifecycle events (activation, retirement, pending_closure, demotion) merged | P 60s |

### Data management (`/data`)

| Method | Path | Response | Freq |
|---|---|---|---|
| GET | `/data/sync/status` | last_sync_at/success/duration, sync_running, sync_interval_s, db_stats (total_bars, by_interval, unique_symbols, latest_bar, oldest_bar, recent_1h_symbols), sync_logs (last 50 lines), sync_elapsed_s, quick_update summary | P 5s while running, 30s idle |
| POST | `/data/sync/trigger` | `{success, message}` | O |
| POST | `/data/quick-update/trigger` | `{success, message}` | O |
| GET | `/data/fmp-cache/status` | total_symbols, fresh_count, any_count, coverage_pct, last_warm_at, running | P 5s while running |
| POST | `/data/fmp-cache/trigger` | `{success, message}` | O |
| GET | `/data/monitoring/status` | per-thread status map (position_sync, trailing_stops, partial_exits, quick_update, full_sync, fundamental_exits) | P 15s |
| GET | `/data/quality` | overall data quality per symbol | L |
| GET | `/data/news-sentiment/status` | Marketaux sentiment coverage | L |
| POST | `/data/news-sentiment/trigger` | — | O |

### Audit (`/audit`)

| Method | Path | Query | Response | Freq |
|---|---|---|---|---|
| GET | `/audit/log` | `event_types`, `symbol`, `severity`, `start_date`, `end_date`, `search`, `offset`, `limit` | entries[] (id, timestamp, event_type (signal\|order\|position\|strategy\|rejection), symbol, strategy_name, severity, description, metadata), total, offset, limit | L + filter changes |
| GET | `/audit/trade-lifecycle/{trade_id}` | — | trade_id, symbol, strategy_name, steps[] (signal → order → fill → position → trailing_stop → close, each with timestamp & details) | O (expand row) |
| GET | `/audit/export` | same filters | CSV download | O |

### Auth (`/auth`)

| Method | Path | Rate limit | Notes |
|---|---|---|---|
| POST | `/auth/login` | 5/min/IP | sets session_id cookie (8h) |
| POST | `/auth/logout` | — | — |
| GET | `/auth/status` | — | `{authenticated, username, role, permissions{pages[],actions[]}}` |
| POST | `/auth/change-password` | — | own password |
| GET | `/auth/me` | — | user profile |
| GET | `/auth/users` | admin | list users |
| POST | `/auth/users` | admin | create |
| PUT | `/auth/users/{username}` | admin | update role/permissions/active |
| DELETE | `/auth/users/{username}` | admin | delete |
| POST | `/auth/users/{username}/reset-password` | admin | reset |
| GET | `/auth/roles` | — | role → default permissions map |

### WebSocket (`/ws`)

- `GET /ws?session_id=<sid>` — accepts WebSocket upgrade, validates session, joins broadcast channel. See 1B for event types.

---

## 1B. WebSocket event system

Every event broadcast by `WebSocketManager.broadcast_*`. The client `websocket.ts` subscribes via `wsManager.on(type, handler)`.

| Event type | Message shape | Backend broadcaster | UI target | Throttle |
|---|---|---|---|---|
| `connection` | `{type, status, timestamp}` | on connect | status indicator | none |
| `market_data` | `{type, symbol, data, timestamp}` | `broadcast_market_data_update` | price cells, charts | 1000ms |
| `position_update` | `{type, position, timestamp}` | `broadcast_position_update` | PositionsContext, Portfolio, Overview | 500ms |
| `order_update` | `{type, order, timestamp}` | `broadcast_order_update` | Orders page, Portfolio (pending count) | none |
| `strategy_update` | `{type, strategy, timestamp}` | `broadcast_strategy_update` | Strategies page, Overview pipeline | none |
| `strategy_performance` | `{type, strategy_id, performance, timestamp}` | `broadcast_strategy_performance_update` | strategy detail panel | none |
| `system_state` | `{type, state, timestamp}` | `broadcast_system_state_change` | top nav state pill, System Health | none |
| `error` | `{type, error, timestamp}` | `broadcast_error_notification` | toast | none |
| `signal_generated` | `{type, signal (strategy_id, symbol, action, confidence, reasoning), timestamp}` | `broadcast_signal_generated` | Autonomous live ticker, recent signals widget | none |
| `backtest_progress` | `{type, strategy_id, progress (percent_complete, current_date, signals_generated, preliminary_metrics), timestamp}` | `broadcast_backtest_progress` | strategy detail progress bar | none |
| `autonomous_status` (channel format `autonomous:status`) | `{channel, event: "status_update", data, timestamp}` | `broadcast_autonomous_status_update` | Autonomous page header | 2000ms |
| `autonomous_cycle` (channel `autonomous:cycle`) | `{channel, event: "cycle_started"\|"cycle_completed"\|"cycle_progress", data, timestamp}` | `broadcast_autonomous_cycle_event` | Autonomous page cycle pipeline | none |
| `autonomous_strategies` (channel `autonomous:strategies`) | `{channel, event: "strategy_proposed"\|"strategy_backtested"\|"strategy_activated"\|"strategy_retired", data, timestamp}` | `broadcast_autonomous_strategy_event` | Autonomous page stream | none |
| `autonomous_notifications` (channel `autonomous:notifications`) | `{channel, event: "notification", data, timestamp}` — data has type, severity, title, message, actionButton | `broadcast_autonomous_notification` | toast + notification center | none |
| `cycle_progress` | `{type, data (stage, percent_complete, message), timestamp}` | `broadcast_cycle_progress` | TradingCyclePipeline component | none |
| `fundamental_alert` | `{type, data (position_id, symbol, reason, details), timestamp}` | `broadcast_fundamental_alert` | Portfolio fundamental alerts panel | none |

Channel-format messages (4 above with `channel + event`) are normalised client-side to flat `type` format in `websocket.ts::convertChannelToType`.

**Connection lifecycle:** client opens `wss://alphacent.co.uk/ws?session_id=<cookie>`, server sends `connection` welcome, server validates session every inbound message, server closes with `1008` on expiry. Client reconnects with exponential backoff (1s → 30s max, 10 attempts) unless disconnect was intentional.

---

## 1C. Existing pages — capabilities and gaps

The current frontend has 15 page files (some aggregate, some sub-pages). Below is what each one *does* today — the knowledge we need to preserve even though none of the code carries forward.

### Overview (`OverviewNew.tsx`)

**Displays:**
- Compact metrics row: Equity, Daily P&L (abs + %), Unrealized, Win Rate, Sharpe, Max DD, Cash
- Multi-timeframe returns table (1D/1W/1M/3M/6M/YTD/1Y/ALL) — each row has absolute return, clicks switch the chart period. Alpha vs SPY shown when SPY data available.
- Strategy pipeline funnel (cumulative): Proposed → Backtested → Active (PAPER+LIVE+PAUSED) → Retired, each count clickable to filter Strategies page
- Equity curve chart (TradingView Lightweight Charts) with SPY benchmark overlay, period selector (1W/1M/3M/6M/1Y/ALL), interval selector (1d/4h/1h), drawdown overlay, realized-P&L line
- Activity panel (right side): recent strategy activations, cycle events, closures
- Market regime pill (trending_up/down/ranging/high_vol colored)
- Health score (composite of drawdown, concentration, margin, diversity)

**Actions:** change period, change interval, toggle benchmark, fullscreen chart, refresh, jump to TearSheet PDF generator.

**Gaps:**
- Health score is a single opaque number — user can't drill into which component is poor.
- Three separate chart components on the page with misaligned axes (known issue in steering).
- No cycle-status inline — you have to navigate to Autonomous page to see the countdown.
- Recent signals are in ActivityPanel, not surfaced prominently. When 50 strategies generate signals, the signal feed is the most interesting event; it shouldn't be hidden.

### Portfolio (`PortfolioNew.tsx`)

**Tabs:** Open Positions | Closed Positions | Pending Closures | Fundamental Alerts.

**Open positions table:** symbol (clickable to PositionDetailView), strategy, side (BUY/SELL pill), status (Open / Pending Close), invested, entry, current, P&L (abs + %), holding (colored by days), opened_at, row menu (close, modify SL, modify TP).
**Filters:** search (symbol), strategy dropdown, side dropdown. **Bulk actions:** select-all, close selected, close all (with confirmation). Export CSV.

**Closed positions:** same columns + exit_reason; filters include date range (1d/7d/30d/all). Export CSV.

**Pending closures:** positions flagged by fundamentals or retirement, with reason, approve/dismiss buttons, bulk approve-all.

**Fundamental alerts:** per-position fundamental reason card (earnings miss, revenue decline, sector rotation, etc.) with close-position or dismiss buttons, trigger-check button.

**Pie charts (side panel):** allocation by symbol (top 10), sector exposure. Asset-class summary table.

**Gaps:**
- SL/TP modification UI exists but eToro LIVE API doesn't support SL updates for LIVE positions. For DEMO, the SL goes to DB only (TSL is DB-side enforced). The UI doesn't signal this honestly.
- No single position-level alpha-vs-regime or time-to-target indicator.
- No directional exposure visualisation at portfolio level (long/short net).
- Closed positions default to returning every row — `limit=0` means no cap, so with thousands of closed trades the response can be heavy.

### Orders (`OrdersNew.tsx`)

**Tabs:** All Orders | Pending (live + pending-closure queue) | Execution Quality.

**All orders table:** symbol, strategy, side, order_type, quantity, price, status (pill), slippage, fill_time, order_action (entry/close/retirement), created_at, row menu (cancel, delete, close position).
**Filters:** search, status, side, source (auto/manual), strategy, date range.
**Bulk actions:** select, cancel selected, delete selected.
**Manual order form (2-step):** fill fields → review → submit.
**Sync with eToro** button.

**Execution Quality tab:** avg slippage (bps), fill rate %, avg fill time, rejection rate. Charts: slippage by strategy (bar), rejections by reason (bar), order flow timeline, order-type breakdown pie, period selector 1D/1W/1M.

**Gaps:**
- Entry orders have a documented 82% FAILED rate because market-closed deferrals are logged as FAILED then retried — cosmetic but noisy.
- Market status is hardcoded for US NYSE/NASDAQ only in the page itself; doesn't reflect crypto 24/7 or forex 24/5.
- Execution quality is a snapshot per period — no trend line of slippage over time per strategy.
- No view of what the scheduler *intends* to trade next (the post-signal, pre-execution queue).

### Strategies (`StrategiesNew.tsx`)

**Tabs:** Overview | Strategies | Templates | Symbols | Template Rankings | Blacklists | Idle Demotions | ● Live (N).

**Strategies tab:** table with id, name, template, category, status (PROPOSED/BACKTESTED/PAPER/LIVE/RETIRED — colored), symbols (count + preview), allocation %, Sharpe, Total Return, Max DD, Win Rate, Trades, Open Positions, Health (0-5 score), Decay (10→0), Conviction, last activated, actions (activate / deactivate / retire / permanently delete / backtest / view detail).

**Filters:** search, status, template, regime, source (TEMPLATE/USER), category (alpha_edge/template_based/manual), type (momentum/mean_reversion/breakout/etc.).

**Strategy detail dialog:** full metadata, walk_forward_results (train vs test sharpe, consistency_score), reasoning (hypothesis, alpha_sources, market_assumptions, signal_logic), fundamental_data, conviction decomposition, backtest results with equity curve chart.

**Templates tab:** `TemplateManager` component — per-template cards with toggle on/off, rule preview, active count, live P&L, avg Sharpe, best/worst symbol, asset classes, timeframe, last proposed/activated.

**Symbols tab:** `SymbolManager` — per-symbol stats (proposed count, active count, traded count, total P&L, win rate, best template) with search.

**Template Rankings:** leaderboard with family filter, timeframe filter, sortable columns.

**Blacklists / Idle Demotions:** read-only audit tables.

**● Live tab:** active live authorizations with paper/live Sharpe side-by-side, retire button per row.

**Actions:** compare two strategies (side-by-side dialog), bulk toggle templates, reset all strategies.

**Gaps:**
- Strategy detail dialog is deeply nested modal-on-modal — breaks flow.
- No at-a-glance way to see which strategies are currently generating signals vs idle.
- Walk-forward evidence buried in metadata — it's the strongest argument for or against a strategy but you need to expand detail to find it.
- Conviction decomposition (WF edge + signal quality + regime fit + asset tradability + fundamental + carry + crypto cycle + sentiment + factor) is a ~132-point max normalised to 100, but shown as a single number.

### Autonomous (`AutonomousNew.tsx`)

**Main panel tabs:** Cycle Pipeline | Strategies Stream | Orders | Scheduler | Cycle History | Graduation Gate (being removed — see Track B).

**Cycle pipeline visualization:** each cycle stage as a node (Cleanup → Market Analysis → Proposal → Walk-Forward → Monte Carlo → Direction-Aware Thresholds → Conviction Scoring → Activation → Signal Generation), current stage highlighted, progress %, WS-updated.

**Controls:** Start / Pause / Stop / Resume / Reset buttons (with confirmation), Trigger Cycle Now, Filters (asset classes, intervals) applied to manual trigger.

**Strategies stream:** live feed of proposals → wf_validated → activated → signal_emitted → order_submitted → order_filled events.

**Scheduler panel:** multi-slot — add/remove slots, each has enabled toggle, days multi-select, hour/minute, next-run preview. Save only when dirty.

**Cycle history:** list of past cycles with duration, counts (proposed / backtested / activated / retired).

**Market regime status:** current regime, confidence, data quality.

**CycleIntelligencePanel:** research view — conviction/WF stats per cycle, per-asset-class breakdown.

**Gaps:**
- Signal funnel (proposed → wf_passed → activated → signal_emitted → order_submitted → order_filled) exists in data (signal_decisions table) but the UI shows fragments, not a single funnel with drop-off per stage.
- Graduation Gate tab here is being removed because it has a dedicated home in /live — confirmed in Track B.
- Paper equity curve in the CIO decision card is pending (Track B P2).
- Re-graduation flow after retirement is pending.

### Live Trading (`LiveNew.tsx`)

**Tabs:** Overview | Positions | Orders | 🎓 Graduation (N) | Divergence.

**Overview:** master switch (on/off toggle with colored border when on), account tiles (Virtual Equity, Today's P&L virtual + real, Open Positions + deployed %, Live Authorizations), mirror ratio info line.

**Positions tab:** table with symbol, side, virtual invested, real invested, entry, current, P&L virtual, P&L real, SL, close button per row.

**Orders tab:** live orders table (same shape as Orders page, filtered to account_type='live').

**Graduation tab:** queue of PAPER (template, symbol) candidates with ≥20 trades, qualification_ratio, Sharpe, win_rate, total_pnl. Each row → CIO decision card: shows paper stats + proposed live params (position_size, sl_pct, tp_pct, conviction_min, notes) → Approve or Reject (14-day cooldown).

**Divergence tab:** per live authorization — paper Sharpe vs live Sharpe comparison, divergence %, flag when live < 50% of paper, retire button.

**Gaps:**
- Master switch toggle doesn't surface what's at risk if flipped off during open live positions.
- Graduation card doesn't show the paper equity curve for the (template, symbol) pair. It's the single most important visual for a CIO decision.
- No divergence heat gradient — just a number.
- No "what would have happened if we'd graduated earlier" counterfactual.

### Analytics (`AnalyticsNew.tsx`)

**Tabs:** Performance | Attribution | Trades | Regime | Alpha Edge | Trade Journal | Rolling Statistics | Perf Attribution | Tear Sheet | TCA | Stress Tests | Alpha Generation.

**Performance tab:** equity curve (TradingView LWC, period+interval selectors), drawdown overlay, Sharpe/Sortino/MDD/WR/profit_factor tiles, monthly returns heatmap, returns distribution histogram.

**Attribution tab:** per-strategy table with contribution %, return, Sharpe, trades, win_rate, regime. Bar chart of top contributors.

**Trades tab:** total/winning/losing trades, avg holding, best/worst trade, win/loss distribution pie, holding periods bar, P&L by hour of day bar, P&L by day of week bar.

**Regime tab:** current regimes per asset class (equity/crypto/forex/commodity) with confidence + data quality, performance-by-regime table with Sharpe/WR/trades, regime transitions timeline, strategy × regime heatmap, market context panel (VIX, yield curve, rates), crypto cycle phase, forex carry rates.

**Alpha Edge tab:** fundamental filter hit/miss with P&L impact, ML filter confidence distribution, conviction distribution histogram with outcome overlay, per-template performance, transaction-cost savings tile.

**Trade Journal tab:** virtualized list of trades with entry/exit time, entry/exit price, pnl, MAE/MFE, conviction, ML confidence, regime, sector. MAE vs MFE scatter. Export CSV.

**Rolling Statistics:** rolling sharpe, beta, alpha, volatility with period selector; Probabilistic Sharpe, IR, Treynor, tracking error.

**Perf Attribution:** per-sector allocation/selection/interaction effects, cumulative stacked area.

**Tear Sheet:** underwater plot, top 5 worst drawdowns with durations, return distribution with skew/kurtosis, annual returns, monthly returns grid.

**TCA:** slippage per symbol/hour-of-day/size-bucket, implementation shortfall (expected vs fill vs close price), fill-rate within N seconds, execution quality trend, worst executions. Per-asset-class breakdown.

**Stress Tests:** scenarios (COVID crash, 2008, inflation shock, rate spike etc.) with estimated loss, loss %, affected positions.

**Alpha Generation:** proprietary alpha attribution (how much of return is alpha vs beta vs luck).

**Gaps:**
- 12 tabs in one page is too many. Some should be sub-pages of specific workflows (e.g., Stress Tests belongs on Risk page, TCA belongs on Orders page).
- No consistent period selector — some tabs use 1M/3M/6M/1Y/ALL, some use 1D/1W/1M/3M.
- Intraday intervals (1h/4h) only supported on a couple of tabs.

### Risk (`RiskNew.tsx`)

**Tabs:** Overview | Positions | Exposures | Advanced | Limits | Alerts.

**Overview:** risk tiles (VaR 95%, current DD, max DD, leverage, beta, total exposure, margin utilisation), risk score (safe/warning/danger) with human-readable reasons, per-strategy risk breakdown.

**Positions:** per-position risk level, risk amount, risk %, SL, TP, filter by level.

**Exposures:** sector exposure bars with limits, asset-class exposure, directional (long/short/net) with limit, correlated pairs heatmap.

**Advanced:** VaR (95% and 99%), stress tests, margin gauge (green/amber/red zones).

**Limits:** editable sliders for max_position_size, max_exposure, max_daily_loss, max_drawdown, max_leverage, risk_per_trade — with validation.

**Alerts:** active + historical risk alerts (VaR breach, drawdown breach, exposure breach, P&L loss, etc.).

**Gaps:**
- Signal-time gates status (C1 VIX, C2 Momentum Crash, C3 Trend Consistency) is documented in the steering file as the runtime defense layer, but there's no UI surface showing if any of them are currently blocking.
- Kill-switch and circuit-breaker state are hidden on the System Health page, not here.
- No visual distinction between "limit currently binding" vs "limit comfortably distant".

### Settings (`SettingsNew.tsx`)

**Tabs:** Trading Mode | API Config | Risk Limits | Position Management | Autonomous | Alpha Edge | Alerts | Users | Shortcuts | Live Trading.

**Trading Mode:** DEMO/LIVE selector (affects what mode=LIVE/DEMO gets sent in every API call).
**API Config:** eToro public_key + user_key per mode, connection test button.
**Risk Limits:** sliders for max_position_size, max_exposure, max_daily_loss, max_drawdown, position_risk, stop_loss, take_profit — per mode.
**Position Management:** trailing stop activation/distance, partial exit levels, correlation adjustment, regime-based sizing multipliers, stale order auto-cancel.
**Autonomous:** huge form (~80 fields) — proposal_count, max_active, watchlist_size, activation thresholds (min_sharpe per asset & interval, min_win_rate per asset & interval, min_trades per asset & interval, min_return_per_trade per asset & interval), conviction thresholds (demo + live crypto + equities), retirement triggers (max_sharpe, max_dd, min_wr, probation_days, rolling_window, consecutive_failures), walk-forward params (train_days, test_days), direction-aware thresholds (5 regimes × long/short × 3 metrics), adaptive risk params.
**Alpha Edge:** fundamental filters on/off + sub-checks (profitable, growing, reasonable_valuation, no_dilution, insider_buying), ML filter on/off + min confidence + retrain frequency, trading frequency caps, strategy template enablement.
**Alerts:** P&L loss/gain thresholds, drawdown threshold, position loss threshold, margin threshold, cycle complete, strategy retired, browser push.
**Users:** admin-only user CRUD (create, edit role/permissions, reset password, delete, list last_login).
**Shortcuts:** reference view of keyboard shortcuts.
**Live Trading:** enabled toggle, base_risk_pct, min/max order size, symbol_cap, mirror_ratio, conviction_threshold (equity), conviction_threshold_crypto.

**Gaps:**
- Autonomous form is so large it's hard to find anything. Needs search-within-form or collapsible sections by concern.
- Changes are immediate-write — no draft/preview/diff. A typo on a slider can derail a running system.
- No per-field "what this affects" inline tooltip that ties the param to a log line or an observable metric.

### System Health (`SystemHealthPage.tsx`)

**Main panel:** service status cards (monitoring_service.running, sub-tasks with last_run age and status, circuit breakers per named service with state + border color, 24h event timeline).
**Side panel:** uptime, error rate 5m, avg response time, blockers count (gates + open CBs).
**Trading gates panel:** kill_switch, market_hours, vix_gate, rejection_blacklist, freshness_sla — each with blocking flag.
**Observability panel:** 30-day decision funnel, top-5 missed-alpha symbols, MAE-at-stop stats.

**Gaps:**
- Backend cycle-error observability gap means cycle-stage exceptions don't surface here (steering doc known issue).
- No WebSocket-health-specific card (connection state, reconnection attempts, last message timestamp).

### Data Management (`DataManagementNew.tsx`)

**Main panel:** sync progress (current/total symbols, elapsed, stats per interval: fetched/cached/skipped/errors/memory), last full sync duration, next scheduled sync, sync logs last 50 lines (live-tailed), quick-update card (updated/errors/elapsed per 10-min cycle), manual trigger buttons (Full Sync, Quick Update, Warm FMP Cache, Sync News Sentiment). DB stats: total bars, by interval, unique symbols, latest/oldest bar, recent 1h symbols table.
**FMP cache:** total_symbols, fresh_count (7-day TTL), coverage %, last_warm_at, running state.
**News sentiment:** Marketaux coverage.
**Data quality table:** per-symbol score, filter by asset class and score bucket.

### Audit Log (`AuditLogPage.tsx`)

**Filters:** event type multi-select (signal, order, position, strategy, rejection), severity, date range, symbol, free-text search (debounced 200ms).
**Table:** virtualized (TanStack Virtual), infinite scroll, row expand → trade lifecycle chain (signal → risk validation → order → fill → position → trailing stop → close, each with timestamp + details).
**Export CSV** with current filters.

### Watchlist (`WatchlistPage.tsx`)

Static list of default watchlist symbols with quote + sparkline, per-symbol quality badge, quick-add to template.

### Position Detail (`PositionDetailView.tsx`)

Per-symbol view — all positions (open + closed) for that symbol, aggregated P&L, timeline chart with entries/exits overlaid on price, total invested, avg entry, best/worst trade.

### Login (`Login.tsx`)

Username/password, error messaging, 5/min/IP rate limit.

---

## 1D. Data model (extracted from `frontend/src/types/`)

Complete entity set used across the UI:

- **Enums:** `TradingMode` (DEMO, LIVE), `OrderType` (MARKET, LIMIT, STOP_LOSS, TAKE_PROFIT), `OrderSide` (BUY, SELL), `OrderStatus` (PENDING, SUBMITTED, FILLED, PARTIALLY_FILLED, CANCELLED, REJECTED), `StrategyStatus` (PROPOSED, BACKTESTED, PAPER, LIVE, RETIRED), `SystemState` (ACTIVE, PAUSED, STOPPED, EMERGENCY_HALT), `ServiceStatus` (RUNNING, STOPPED, ERROR).
- **AccountInfo:** balance, equity, buying_power, margin_used, daily_pnl, total_pnl, trading_mode.
- **Position:** id, symbol, quantity (= dollar amount invested on eToro, not shares), entry_price, current_price, unrealized_pnl (abs + %), realized_pnl, side, strategy_id, strategy_name, opened_at, closed_at, pending_closure, closure_reason, stop_loss, take_profit, invested_amount, sector, asset_class.
- **Order:** id, symbol, side, type, quantity (dollar amount), price, filled_quantity, status, strategy_id, strategy_name, created_at, updated_at, filled_at, filled_price, order_action (entry | close | retirement), slippage, fill_time_seconds, expected_price, etoro_order_id.
- **Strategy:** id, name, description, status, rules (dict), symbols[], allocation_percent, performance_metrics, reasoning, backtest_results, walk_forward_results, source (TEMPLATE | USER), template_name, market_regime, entry_rules, exit_rules, parameters, metadata (template_name, template_type, strategy_category, conviction_score, ml_confidence, fundamental_data, fundamental_checks, requires_fundamental_data, requires_earnings_data), strategy_category (alpha_edge | template_based | manual), strategy_type, created_at, updated_at, activated_at, retired_at.
- **PerformanceMetrics:** total_return, sharpe_ratio, sortino_ratio, max_drawdown, win_rate, avg_win, avg_loss, total_trades, total_pnl, live_orders, open_positions, unrealized_pnl, health_score (0-5), decay_score (0-10).
- **BacktestResults:** same perf metrics + equity_curve[], trades[], backtest_period.
- **WalkForwardResults:** in_sample + out_of_sample metrics, consistency_score.
- **StrategyReasoning:** hypothesis, alpha_sources[] (type, weight, description), market_assumptions[], signal_logic, confidence_factors.
- **MarketData:** symbol, price, change, change_percent, volume, bid, ask, timestamp, source (ETORO | YAHOO_FINANCE).
- **SystemStatus:** state, timestamp, active_strategies, open_positions, reason, uptime_seconds, last_signal_generated, last_order_executed.
- **DependentService:** name, status, endpoint, last_health_check, error_message.
- **Notification:** id, severity (INFO | WARNING | ERROR | CRITICAL), title, message, timestamp, read.
- **TradingSignal:** strategy_id, strategy_name, symbol, action (BUY/SELL), quantity, price, confidence, reasoning, indicators, timestamp.
- **AutonomousStatus:** enabled, market_regime, market_confidence, data_quality, last_cycle_time, next_scheduled_run, cycle_duration, cycle_stats (proposals/backtested/activated/retired counts), portfolio_health, template_stats[].
- **FundamentalAlert:** id, symbol, side, quantity, entry_price, current_price, unrealized_pnl, flag_reason, flag_timestamp, fundamental_data, fundamental_detail, closure_reason, strategy_id, opened_at.
- **TradeJournalEntry:** id, trade_id, strategy_id/name, symbol, entry_time/price/size/reason, exit_time/price/reason, pnl (abs + %), hold_time_hours, MAE, MFE, market_regime, sector, conviction_score, ml_confidence.
- **AutonomousNotification:** id, type (cycle_started | cycle_completed | strategies_proposed | backtest_completed | strategy_activated | strategy_retired | regime_changed | portfolio_rebalanced | error_occurred), severity (info | success | warning | error), title, message, timestamp, read, data, actionButton.
- **Analytics extensions:** `RollingStatsData`, `AttributionData` (with sectors, cumulative_effects), `TearSheetData` (underwater plot, worst drawdowns, return distribution, annual/monthly returns), `TCAData` (slippage by symbol/hour/size, implementation shortfall, fill rate buckets, worst executions per asset class).

**Contexts (state shape):**
- **TradingModeContext** — `{tradingMode, setTradingMode, isLoading}`. Value persisted in `localStorage.alphacent_trading_mode`, synced with backend `/config`. Flips the `?mode=` param on every subsequent API call.
- **PositionsContext** — `{positions, isLoading, refresh}`. Single polling loop (30s, WS-aware) shared across PositionTickerStrip, BookPulseWidget, RiskPulseWidget to eliminate duplicate `getPositions()` calls.
- **NotificationContext** — `{notifications, unreadCount, preferences, addNotification, markAsRead, markAllAsRead, clearNotification, clearAll, updatePreferences}`. Subscribes to `autonomous_notifications` WS channel. Persists to `localStorage` (max 100). Preferences: enabled, soundEnabled, showToasts, severityFilter, eventTypeFilter.
- **ThemeContext** — `{theme: 'dark' | 'light', toggleTheme, setTheme}`. Persisted in `localStorage.alphacent-theme`. Default dark. Writes `data-theme` on `<html>`.

---

## 1E. Current `frontend/package.json` — dependencies to carry forward or drop

**Carry forward** (already the right choice):
- `react` 19.2, `react-dom` 19.2, `react-router-dom` 7.13
- Radix primitives: `@radix-ui/react-*` — dialog, dropdown-menu, popover, select, switch, tabs, tooltip, progress, scroll-area, checkbox, slot, label, separator, radio-group
- `lightweight-charts` 5.1.0 (TradingView)
- `@tanstack/react-table` 8.21, `@tanstack/react-virtual` 3.13
- `framer-motion` 12.34
- `sonner` 2.0 (toasts)
- `lucide-react` 0.575 (icons)
- `react-hook-form` 7.71 + `@hookform/resolvers` 5.2 + `zod` 4.3
- `class-variance-authority` 0.7, `clsx` 2.1, `tailwind-merge` 3.5 (utility class composition)
- `tailwindcss` 4.1 + `tailwindcss-animate` + `autoprefixer` + `postcss`
- `date-fns` 4.1
- `axios` 1.13
- `zustand` 5.0
- `fuse.js` 7.3 (fuzzy search)
- `react-resizable-panels` 4.10 (panel layouts)
- `vite` 6.3, `vitest` 4.0, `typescript` 5.9

**Add:**
- `@tanstack/react-query` 5.x — hybrid poll/cache/WS server-state manager (not currently used — Zustand+ad-hoc fetch is the current pattern).
- `@visx/heatmap` + `@visx/scale` + `@visx/axis` — for regime × template heat, conviction gradient, underwater plot, return distribution. Visx chosen over Nivo/Recharts for custom heatmap layouts we need.
- `recharts` 2.x — for simple bar/line/pie analytics that Visx is overkill for. Two analytics libraries chosen deliberately: Recharts for quick composables, Visx for anything bespoke.

**Drop:**
- `html2canvas` + `jspdf` — the PDF TearSheetGenerator. Move to server-side PDF generation (backend endpoint) or drop entirely. Client-side PDF rendering is a known source of bloat and visual inconsistency.
- No ESLint bundled config changes; keep `eslint` 9.x + `typescript-eslint`.



---

# Phase 2 — Technology Decisions and Design Language

## 2A. What Bloomberg, Refinitiv, and TradingView teach us

Professional terminals have three shared design choices that any trading UI should adopt. Content was rephrased from [Designing High-Density AI News Aggregators](https://natural20.com/coverage/architecture-of-cognitive-efficiency-designing-ai-news-aggregators) and [Bloomberg brand guidelines](https://issuu.com/1rbzojtk4to/docs/bloomberg-brand-guidelines-pdf) for compliance with licensing restrictions.

- **High density, keyboard-driven, semantic colour over decoration.** Bloomberg's 'pro' aesthetic signals expertise: every pixel carries meaning. The surface area per task is high because operators scan — not browse. Decoration costs scan speed.
- **Dark grey (~#121212), not pure black.** True black causes halation on most LCDs and is harder to read for users with astigmatism. All surfaces layer greys.
- **Orange as the saturated accent for actionable entities** (tickers, orders) in Bloomberg's palette. Our system uses green/red for direction and a distinct hue (cyan/blue) for ticker + interactive accents, reserving yellow for warnings and orange for pending/queued.
- **Typography:** monospace for all numbers (so columns of P&L align visually), proportional sans for prose. Tabular figures (`font-variant-numeric: tabular-nums`) so the same digit has the same width, making growing/shrinking numbers less visually jarring.
- **Layout:** multi-panel, resizable, persistent across navigation. A trader's sidebar and metrics bar should not re-render when they switch from Overview to Portfolio.

**We already do resizable panels (`react-resizable-panels` 4.10) and a persistent AppShell. Keep both.**

## 2B. What QuantConnect, Composer, and Alpaca teach us

- **Paper vs live separation must be visual, not just logical.** QuantConnect uses an account-level colour token (paper = blue, live = green/orange). Alpaca uses a persistent top-bar pill. Composer uses a 'live' badge per strategy. Our domain has the extra wrinkle of **per-(template, symbol) graduation** — any UI element tied to a live authorisation needs a distinct `live-active` visual, and the global master switch needs to be the most prominent visual on the page when off.
- **Algorithmic decisions must be transparent.** Show the walk-forward evidence alongside the Sharpe. Show the conviction decomposition (WF edge + signal quality + regime fit + asset tradability + fundamental quality + ...) as a stacked bar so you can see *why* a 74 is a 74.
- **Graduation from paper to live is a workflow, not a button.** It needs a candidate queue, a decision card with the paper equity curve, and a reject with cooldown. The CIO workflow in our /live page today is the right idea but undercooked.

## 2C. What modern dark fintech UIs do well

- **Layered surfaces.** 3–4 background layers (base, surface, elevated, overlay) with ~2% luminosity difference between neighbours. No borders where layering does the job.
- **Number flashing on update.** 300–500ms green/red pulse when a P&L updates via WS. Never animate the number itself scrolling; just tint and fade.
- **Never animate tables or charts.** Tables get rows replaced, full stop. Charts append points; they don't tween.
- **Progressive disclosure.** Deep configuration (our Settings → Autonomous form with ~80 fields) is organised by decision — not by API shape — and searchable.
- **Info tooltips tied to backend metrics.** Every threshold in Settings has a "what does this affect?" link to the log line or the observable it gates.

## 2D. Chart library decisions

| Use case | Library | Why |
|---|---|---|
| Price / OHLC | **TradingView Lightweight Charts v5** | Already a dep, canvas-rendered, handles thousands of bars, crosshair + scale sync built-in, native volume histograms. Nothing in the React ecosystem matches it for candlesticks. |
| Equity curve + drawdown overlay | **TradingView Lightweight Charts** | Same primitive, second pane for drawdown. Axis sync is free, no SVG layering hacks. |
| Returns distribution, MAE/MFE scatter, P&L-by-hour/day bar | **Recharts 2.x** | Declarative, composable, good enough for quick analytics. Not the most performant (SVG) but fine for <500 points. |
| Regime × template heatmap, correlation matrix, underwater plot, conviction gradient | **Visx (`@visx/heatmap`, `@visx/scale`, `@visx/axis`)** | Recharts heatmaps are anaemic; Nivo is opinionated and heavier. Visx gives d3 primitives on React; we control every cell. |
| Sparklines in tables | **Custom SVG** (lightweight, one path) | Don't pull a library for 100×30px lines. |
| Real-time 65-position refresh without jank | **Canvas-based rendering (TradingView) + virtualized tables (TanStack Table + TanStack Virtual)** | Lightweight Charts v5 has `update()` for incremental price push. Tables with 65 rows don't need virtualization, but the strategies table (200+ rows) does. |

Two analytics libraries is a deliberate choice. Using Recharts for simple cases reduces mental overhead. Using Visx for bespoke layouts means no fighting a library for a heatmap shape it wasn't designed for.

## 2E. Component library — primitives, not system

We evaluated Radix UI primitives vs shadcn/ui vs Mantine vs Ark UI. Content was rephrased from [calmops.com](https://calmops.com/web/component-libraries-shadcn-radix-mui), [WorkOS](https://workos.com/blog/what-is-the-difference-between-radix-and-shadcn-ui), and [certificates.dev](https://certificates.dev/blog/starting-a-react-project-shadcnui-radix-and-base-ui-explained) for compliance.

- **Radix UI Primitives** — unstyled, accessible behaviour layer for complex widgets (dialogs, popovers, dropdowns, tabs, switches, tooltips). Own all styling.
- **shadcn/ui** — not a library. A *pattern* of copying Radix-based styled components into your project with CVA for variants. Gives source ownership.
- **Mantine** — full design system, too opinionated for trading data (their defaults are consumer-app-centric: soft shadows, rounded corners, generous padding).
- **Ark UI** — similar to Radix but less mature for React; strong choice if we were using Solid or Vue.

**Decision:** **Radix primitives + our own component layer, written in the shadcn style** (copied source, CVA for variants, Tailwind for styling). We already have most Radix deps. We own everything. Every component is bespoke for trading density — smaller padding, tabular numbers by default, no rounded corners on tables, high-contrast focus rings.

This is what the current frontend already does partially — the rebuild formalises it into a consistent library.

## 2F. State management and data fetching

Two questions, two answers:

### Server state — **TanStack Query 5**

Content was rephrased from [refine.dev](https://refine.dev/blog/react-query-vs-tanstack-query-vs-swr-2025), [logrocket.com](https://blog.logrocket.com/swr-vs-tanstack-query-react/), and [markaicode.com](https://markaicode.com/react-query-vs-swr-2025-performance-comparison) for compliance.

TanStack Query gives us exactly what our pattern needs:
- `staleTime` + `refetchInterval` for polling with back-off.
- `useQuery({ enabled })` to gate on auth state.
- `queryClient.invalidateQueries(['positions'])` from WS handlers — cleanest possible hybrid pattern.
- Built-in loading/error/empty states per query, not re-invented per page.
- Dependent queries (get account first, then get positions for that account) handled natively.
- `useMutation` for write endpoints (close position, approve graduation) with optimistic updates and rollback.

SWR is leaner but lacks first-class mutations, has weaker polling control, and has no `queryKey` taxonomy for WS-driven invalidation.

**Rule:** everything that comes from the backend is a `useQuery`. WS events call `queryClient.invalidateQueries(['accounts', mode])` or `setQueryData(...)` to optimistically patch. No `useEffect(() => fetch())` anywhere in page code. The current ad-hoc polling pattern (`usePolling`) is replaced entirely.

### Client state — **Zustand 5**

TanStack Query owns every byte of server state. Zustand owns only true client state:

- **TradingModeStore** — the DEMO/LIVE selector (persisted to localStorage).
- **LayoutStore** — panel split ratios, fullscreen flags, collapsed sections (persisted).
- **FiltersStore** — per-page filter state (symbol search, status filter, etc.) — opt-in persist.
- **NotificationStore** — autonomous notifications queue + read/unread state (persisted).
- **CommandPaletteStore** — open/closed state, recent commands.
- **ThemeStore** — dark/light (existing ThemeContext migrated).

Zustand over Jotai because almost nothing in trading state is truly atomic and ungrouped; the atom explosion doesn't help us. Zustand selectors (`useStore((s) => s.tradingMode)`) give the same render-scoped subscription precision. Zustand over Context because Context causes every consumer to re-render on any change, and the current PositionsContext/NotificationContext pattern already has that problem.

## 2G. Design language definition

- **Desktop-first.** 1440px minimum comfortable width. Mobile (<768px) shows an 'AlphaCent requires a desktop' screen — mobile is not a use case for a trading CIO view and we refuse to compromise information density to fit one. Tablet (768–1279px) degrades gracefully (single panel stack, critical metrics only).
- **Information density over whitespace.** Default row height 28px (not 48px). Default font size 12–13px. Only headers go above 14px.
- **Monospace numerals everywhere.** Including in prose when a number appears (e.g. '$491,200 equity').
- **Colour as signal, not decoration.** Green = up / approved / live-on. Red = down / rejected / emergency. Cyan = selected / informational. Amber = warning / pending. Every other colour is grey.
- **Motion principle:** motion serves information latency. A number that changed tints for 400ms. A new row slides in 200ms. Nothing dances. No parallax. No scroll-triggered reveals.
- **Persistent shell.** TopNavBar + MetricsBar + PositionTickerStrip + BottomWidgetZone are mounted once per session and never remount on route changes. Already the case in the current AppShell — keep.



---

# Phase 3 — Platform Design

## 3A. Design system specification

### Colour tokens (exact hex values)

All tokens exposed as CSS variables on `:root[data-theme="dark"]`. Light theme in Appendix.

**Background layers** (dark theme):

| Token | Hex | Purpose |
|---|---|---|
| `--bg-0` | `#0a0a0b` | App base (body). Not true black. |
| `--bg-1` | `#101012` | Default panel surface. |
| `--bg-2` | `#16171a` | Elevated surface (cards on panels, modals). |
| `--bg-3` | `#1d1e22` | Overlay / popover / dropdown. |
| `--bg-hover` | `#20222a` | Row hover, clickable hover. |
| `--bg-active` | `#2a2d37` | Active row / selected item. |

**Surfaces and borders:**

| Token | Hex | Purpose |
|---|---|---|
| `--border-subtle` | `#1f2024` | Default divider (cell, row, panel edge). |
| `--border-default` | `#2a2c33` | Emphasised divider. |
| `--border-strong` | `#3a3d46` | Input borders, separator heavy. |
| `--border-focus` | `#5eb0ff` | Keyboard focus ring. |

**Text:**

| Token | Hex | Contrast vs `--bg-1` |
|---|---|---|
| `--text-0` | `#ebedf2` | Primary (headings, numbers, active tab). 14.8:1 |
| `--text-1` | `#c5c8d0` | Body. 11.2:1 |
| `--text-2` | `#8a8e99` | Muted (secondary metadata, column headers). 5.5:1 |
| `--text-3` | `#5a5e68` | Tertiary (placeholder, disabled labels). 3.1:1 AA for large text only. |

**P&L semantic:**

| Token | Hex | Purpose |
|---|---|---|
| `--pnl-up` | `#22c55e` | Positive P&L, approved status, up arrow. |
| `--pnl-up-bg` | `rgba(34, 197, 94, 0.10)` | Row background for positive rows. |
| `--pnl-up-flash` | `#4ade80` | 400ms pulse tint on P&L increase. |
| `--pnl-down` | `#ef4444` | Negative P&L, rejection, emergency. |
| `--pnl-down-bg` | `rgba(239, 68, 68, 0.10)` | |
| `--pnl-down-flash` | `#f87171` | 400ms pulse tint on P&L decrease. |
| `--pnl-flat` | `#8a8e99` | Near-zero change (|pnl_pct| < 0.05%). |

**Regime colours** (pills, tints, chart fills):

| Regime | Token | Hex |
|---|---|---|
| `trending_up_strong` | `--regime-up-strong` | `#16a34a` |
| `trending_up` | `--regime-up` | `#22c55e` |
| `trending_up_weak` | `--regime-up-weak` | `#86efac` |
| `ranging` | `--regime-range` | `#eab308` |
| `trending_down_weak` | `--regime-down-weak` | `#fca5a5` |
| `trending_down` | `--regime-down` | `#ef4444` |
| `trending_down_strong` | `--regime-down-strong` | `#b91c1c` |
| `high_vol` / `volatile` | `--regime-vol` | `#a855f7` |

**Conviction heat gradient** (0–100) — stops at 0, 50, 70, 85, 100:

| Range | Hex |
|---|---|
| 0–39 | `#6b7280` (slate-500) |
| 40–54 | `#94a3b8` (slate-400) |
| 55–64 | `#84cc16` (lime-500) |
| 65–73 | `#22c55e` (green-500) |
| 74–84 | `#16a34a` (green-600) — DEMO live threshold |
| 85–100 | `#15803d` (green-700) |

**Account accent** (consumes entire UI chrome when live is on):

| Token | Hex |
|---|---|
| `--account-demo` | `#3b82f6` (blue-500) |
| `--account-live` | `#10b981` (emerald-500) — only used when master switch is ON |
| `--account-live-off-tint` | `#6b7280` (slate-500) — when live tab viewed but master switch OFF |

**Interactive / informational:**

| Token | Hex | Purpose |
|---|---|---|
| `--accent-primary` | `#3b82f6` | Primary action buttons, links. |
| `--accent-secondary` | `#8b5cf6` | Secondary info (alpha edge marker, ML badge). |
| `--accent-ticker` | `#06b6d4` | Selected ticker, symbol emphasis. |

**Warning / Error / Success** (for notifications & system state — different from P&L):

| Token | Hex |
|---|---|
| `--status-warning` | `#f59e0b` |
| `--status-warning-bg` | `rgba(245, 158, 11, 0.10)` |
| `--status-error` | `#dc2626` (darker than `--pnl-down` so 'system error' reads as more severe than 'red trade') |
| `--status-error-bg` | `rgba(220, 38, 38, 0.12)` |
| `--status-success` | `#059669` (darker than `--pnl-up`) |
| `--status-info` | `#0284c7` |

### Typography

**Font stack (loaded locally via `@fontsource`):**

- **UI (body, labels, headings):** `Inter Variable`, system-ui, sans-serif.
- **Numerals, prices, P&L, symbol tickers, metrics, tables:** `JetBrains Mono Variable`, ui-monospace, SFMono-Regular, Menlo, monospace. `font-variant-numeric: tabular-nums` enabled globally on all `.mono` and `.number` classes.

Both loaded as variable fonts — one request each.

**Type scale** (line-height in parens):

| Token | Size | Usage |
|---|---|---|
| `--text-xs` | `10px (14px)` | Dense table captions, axis labels, breadcrumb ticks. |
| `--text-sm` | `11px (16px)` | Table body, secondary labels, compact metrics. |
| `--text-base` | `12px (16px)` | Default UI text, most form labels, button text. |
| `--text-md` | `13px (18px)` | Card titles, emphasised table numbers. |
| `--text-lg` | `15px (22px)` | Page section headers, metric values on cards. |
| `--text-xl` | `18px (24px)` | Page H1, metric hero numbers. |
| `--text-2xl` | `22px (28px)` | MetricsBar equity number, Overview P&L hero. |
| `--text-3xl` | `28px (32px)` | Graduation card decision value, killswitch confirm. |

**Weights:** 400 (body), 500 (emphasised labels, table headers), 600 (page headers, metric hero), 700 (only for critical numbers that must pop — daily P&L, live equity).

### Spacing system

Base unit `4px`. Scale exposed as CSS vars `--sp-0` … `--sp-8`:

| Token | px |
|---|---|
| `--sp-0` | `0` |
| `--sp-0-5` | `2` |
| `--sp-1` | `4` |
| `--sp-1-5` | `6` |
| `--sp-2` | `8` |
| `--sp-3` | `12` |
| `--sp-4` | `16` |
| `--sp-5` | `20` |
| `--sp-6` | `24` |
| `--sp-8` | `32` |
| `--sp-10` | `40` |
| `--sp-12` | `48` |

**Density rules:**
- Table row padding: `var(--sp-1-5) var(--sp-2)` (6×8).
- Default row height: 28px.
- Panel padding: `var(--sp-2)` on all sides (8px). Never more than `var(--sp-3)` unless the panel is a wizard step.
- Card padding: `var(--sp-3)` (12px).
- Modal padding: `var(--sp-5) var(--sp-6)` (20×24).

### Component states

Every interactive component has **exactly** these states — no more. Each state maps to defined tokens.

| State | Background | Text | Border | Outline |
|---|---|---|---|---|
| default | `--bg-1` | `--text-1` | `--border-subtle` | none |
| hover | `--bg-hover` | `--text-0` | `--border-default` | none |
| active / pressed | `--bg-active` | `--text-0` | `--border-default` | none |
| focus-visible | (same as default) | (same) | (same) | `2px solid --border-focus`, `2px offset` |
| selected (e.g. selected row) | `--bg-active` | `--text-0` | (left border `--accent-primary` 2px) | none |
| loading | `--bg-1` | `--text-3` | `--border-subtle` | skeleton shimmer |
| error | `--bg-1` | `--text-1` | `--status-error` | none |
| empty | (no component rendered) — parent shows empty-state card | | | |
| disabled | `--bg-1` | `--text-3` | `--border-subtle` | cursor: not-allowed, 50% opacity |
| live-active (badge/button when applies to LIVE account) | `--bg-1` | `--text-0` | `--account-live` 2px | dot indicator `--account-live` |

### Animation principles

**Always animate:**
- P&L number flash: 400ms green/red tint (css custom property transition on background-color, ease-out). No position/scale change.
- New signal pulse in SignalFunnel: 800ms opacity 0→1→1, ease-out.
- Cycle stage progress: monotonic 200ms ease-out transitions between stages. Never backwards.
- Toast appearance/dismiss: 200ms.
- Modal/dialog fade+scale: 150ms.
- Route transitions: crossfade 120ms (via Framer Motion AnimatePresence at AppShell level).

**Never animate:**
- Table rows (appear/sort/filter).
- Chart data points or axes.
- Scroll-triggered reveals (no parallax, no 'fade-in on scroll' anywhere).
- Page-level hero content.
- Number value changes (the value just replaces; only the tint animates).

**Easing:** default `cubic-bezier(0.4, 0, 0.2, 1)` (material standard). No bouncy springs in trading UI — it reads as unstable.

### Layout system

**Grid:** CSS grid, no framework. Page-level layouts declare row/column ratios.

**Responsive breakpoints:**

| Name | Min width | Behaviour |
|---|---|---|
| `xs` | 0 | Hard-blocked: 'AlphaCent requires a desktop' full-screen message. |
| `sm` | 768 | Tablet — single-panel stacked navigation, metrics bar collapses to summary pill. |
| `md` | 1024 | Reduced: 2-panel layouts only, side panels collapse. |
| `lg` | 1280 | Default desktop — 3-panel layouts. |
| `xl` | 1536 | Expanded — side drawers persistent. |
| `2xl` | 1920 | Trading station — 4-panel layouts, denser defaults. |

**Panel split ratios** (resizable):

- Overview: 25% | 50% | 25% (metrics | equity chart | activity) — min widths 240/400/240.
- Portfolio: 70% | 30% (positions table | allocation charts) — allocation panel collapsible.
- Strategies: 60% | 40% (strategy table | detail panel) — detail panel hides when nothing selected.
- Autonomous: 30% | 40% | 30% (scheduler/controls | pipeline visual | stream).
- Live: 20% | 60% | 20% (master switch + tiles | main tab content | divergence mini).
- Risk: 30% | 70% (tiles | tab content).
- Analytics: 100% single panel with horizontal tab bar (tabs own the split).
- Settings: 20% | 80% (vertical tab nav | form).
- System Health: 35% | 65% (side metrics | service grid).
- Audit: 25% | 75% (filters | log + lifecycle chain).

All panel ratios persisted per-user in `localStorage.alphacent.layout.<pageId>` and restored on mount.

---

## 3B. Page architecture

Each page follows the same scaffold:

```
<PageTemplate
  title="..."
  description="..." (mode label)
  actions={<HeaderActions />}
>
  <ResizablePanelLayout
    layoutId="..."
    panels={[...]}
  />
</PageTemplate>
```

`PageTemplate` owns title, mode label, header actions bar, and breadcrumbs. `ResizablePanelLayout` owns the split.

### Information architecture — 5 primary surfaces

The 10-page structure of the current frontend mirrors the FastAPI router layout, not the CIO's workflow. We collapse to 5 surfaces, each built around a user job-to-be-done. Every feature from the Phase 1 inventory lands in exactly one surface — nothing dropped.

| Surface | One-line purpose | Route | Tabs |
|---|---|---|---|
| **Command** | "Is the machine making money right now, and what just happened?" | `/` | — (single surface, 3 panels) |
| **Book** | "What do I own, what orders are out, and at what quality did they fill?" | `/book` | Positions · Orders · Execution · Live |
| **Strategies** | "What is the strategy library doing, and which pairs should graduate?" | `/strategies` | Library · Cycle · Templates · Symbols · Graduation · Lab |
| **Guard** | "What could stop us trading, and what is stopping us right now?" | `/guard` | Risk · Gates · System · Circuit Breakers · Alerts · Audit |
| **Research** | "Does our edge exist, and where does it come from?" | `/research` | Performance · Attribution · Trades · Regime · Alpha Edge · Tear Sheet · Stress · Journal |

Settings stays off-nav at `/settings` (keyboard `g ,`). Data Management lives under Guard → System. Watchlist is dropped — symbol watch is now a filter on the library.

**Why these five:**

- **Command** answers now. The CIO lands here; everything else is a drill-down.
- **Book** unifies Portfolio + Orders + Live account — they are the same decision surface with a filter. Today's split forces you to switch pages to understand a single fill.
- **Strategies** unifies the strategy library, the autonomous cycle (which is just the library's time dimension), and the graduation queue (the library's promotion pipeline). Templates, Symbols and research lab come with it because they all answer "what is the library doing?"
- **Guard** unifies Risk + System Health + Trading Gates + Circuit Breakers + Alerts + Audit Log. All five are the same question: "what could stop a trade, and what has stopped one?" Separating them today makes it easy to miss that a stalled monitoring thread is the reason no signals fired.
- **Research** is the deep-dive. Pure analytics, no live actions. Rolling stats, tear sheet, TCA, alpha edge diagnostics, trade journal, stress tests — all answer "does the edge exist and where does it come from."

**Design contract:** each surface has its own shell with shared sub-navigation (tabs or segmented rail). Page-level state (selected filters, sort, selected row, tab) persists in URL and localStorage so deep-linking always works. Keyboard shortcut moves you between surfaces in one keystroke (`g c/b/s/g/r`).

---

### Surface 1 — Command

**Route:** `/`
**Question answered:** *"Is the machine making money right now, and what just happened?"*
**Layout:** 3 panels, resizable. Left 25% (Pulse), Center 50% (Equity), Right 25% (Stream). Fullscreen mode collapses to center only.

**Data sources:**
- `useQuery(['dashboard', mode, interval])` → `GET /account/dashboard/summary?mode=&interval=` — 30s, WS-invalidated on `position_update` / `order_update` / `strategy_update`.
- `useQuery(['analytics-performance', mode, '3M', interval])` → `GET /analytics/performance` — high-resolution equity curve.
- `useQuery(['spy-benchmark', equityPeriod])` → `GET /analytics/spy-benchmark`.
- `useQuery(['strategies', mode, { slim: true }])` → for pipeline counts (60s).
- `useQuery(['autonomous-status'])` → 10s + WS.
- `useQuery(['dashboard-top-movers', mode])` / `['dashboard-recent-signals', mode]` / `['dashboard-strategy-alerts', mode]`.
- `useQuery(['live-summary'])` — 15s + WS (for LIVE state on this page).
- WS subscriptions: `signal_generated`, `order_update`, `autonomous_cycle`, `autonomous_strategies`, `fundamental_alert`, `system_state`.

**Left panel — Pulse**
- **AccountHero** — DEMO/LIVE pill (`AccountToggle`), current equity as `PnLNumber` size `3xl`, daily P&L row, live state indicator (`LivePill`).
- **MetricsStrip** — 8 compact metrics with WS flash: Equity · Daily P&L · Daily % · Unrealized · Win Rate (30d) · Sharpe (30d) · Max DD · Cash.
- **MultiTimeframeReturns** — 1D / 1W / 1M / 3M / 6M / YTD / 1Y / ALL with absolute return + alpha vs SPY. Clicking a row sets the center chart period.
- **RegimeBlock** — current regime pill + confidence + data quality + 20d/50d drift deltas. Click → Research → Regime.
- **HealthScoreCard** — overall score 0-100 + stacked bar decomposition (drawdown / concentration / margin / diversity / MQS). No opaque single numbers.
- **CycleStatusCard** — current cycle stage (if running) or next scheduled time + last cycle's summary (duration, proposed/activated/retired). Click → Strategies → Cycle.
- **StrategyPipelineCounts** — 5 clickable rows: Proposed · Backtested · PAPER · LIVE · Retired. Click → Strategies → Library with preset filter.

**Center panel — Equity**
- **EquityChart** (TradingView LWC) — equity line, drawdown pane, SPY overlay toggleable, realised-P&L dashed line, period selector (1W/1M/3M/6M/1Y/ALL), interval selector (1d/4h/1h).
- Hover readout (top-right): date, equity, drawdown %, alpha vs SPY on that day.
- Fullscreen button (hides Pulse and Stream panels).
- `PnLNumber` hero number above chart: today's return with flash animation.

**Right panel — Stream**
- **SignalFeed** — WS-driven rolling 50-event buffer. Each event: coloured dot (accepted/rejected/blocked), symbol, strategy, reason on hover. Click an event → drawer with full signal_decisions metadata (stage, template, conviction, action). Filter chips: Entries only · Exits only · Rejections only · Live only.
- **OrderFillsTicker** — 10 most recent fills with slippage bps chip. Click → Book → Orders with the order selected.
- **LifecycleFeed** — activations / retirements / graduations from last 24h.
- **AlertsBadge** — count of unread risk + autonomous alerts. Click → Guard → Alerts.

**Empty state:** when `active_strategies === 0 && open_positions === 0` — center shows onboarding card "No active strategies. Run your first cycle?" with CTA to Strategies → Cycle. Fallback: show market regime + current time so the page is never blank.

**Loading state:** per-panel skeleton matched to shape (6 metric tiles blurred, chart shows grid only, feed shows 3 skeleton rows).

**Error state:** per-panel `ErrorState` card with retry + last-known-good timestamp.

**User actions:**
- Toggle benchmark / realised / drawdown overlays.
- Change period or interval.
- Fullscreen chart.
- Click any pipeline stage / mover / signal / order / regime → drill into the appropriate surface with context preserved.

---

### Surface 2 — Book

**Route:** `/book`
**Question answered:** *"What do I own, what orders are out, and at what quality did they fill?"*
**Layout:** top account-segmented control (All · DEMO · LIVE) + tab bar: Positions · Orders · Execution · Live. Each tab: 70/30 split (main table | context side panel).

The account segmented control is global to this surface and filters every tab. When set to LIVE, the "Live" tab gains an extra tile row (virtual vs real mirroring).

**Data sources (shared across tabs):**
- `useQuery(['account-info', mode])` — 30s + WS.
- `useQuery(['positions', mode])` — 30s + WS `position_update`.
- `useQuery(['closed-positions', mode, { limit: 500 }])` — lazy + load-more.
- `useQuery(['pending-closures', mode])` — 60s + WS.
- `useQuery(['fundamental-alerts', mode])` — 60s + WS `fundamental_alert`.
- `useQuery(['orders', mode])` — 15s + WS `order_update`.
- `useQuery(['execution-quality', mode, period])` — 60s.
- `useQuery(['live-summary'])`, `useQuery(['live-config'])`, `useQuery(['live-divergence'])` — for Live tab.

**Tab — Positions**

Secondary tabs: Open · Pending Closures · Fundamental Alerts · Closed.

- **PositionsDataTable** — TanStack Table, virtualized >50 rows. Columns: checkbox, symbol (link to /book/position/:symbol), strategy, side pill, status (Open · Pending Close), invested, entry, current, P&L (`PnLNumber`), holding (colored), opened_at. Row menu: close, modify SL, modify TP, view detail.
- **FilterBar** — search, strategy, side, status. Account-type segmented inherited from surface header.
- **BulkActionBar** — Close selected · Close all (destructive, confirm). Sync with eToro.
- **SidePanel** (30%):
  - Pie chart: allocation by symbol (top 10, "Other" bucket for remainder).
  - Bars: sector exposure with limit lines.
  - Tiles: per-asset-class count + P&L.
  - **DirectionalBar** — long / short / net with limit line (new).
- Closed sub-tab adds Exit Reason column + date-range filter (1d/7d/30d/all).
- Pending Closures sub-tab: each closure as card (symbol, strategy, P&L, reason, Approve / Dismiss), bulk approve-all.
- Fundamental Alerts sub-tab: alert cards with reason expanded, Close / Dismiss / View-position buttons, "Trigger fundamental check" button.

**Modify SL/TP dialog** — DEMO: writes to DB (TSL-enforced). LIVE: dialog shows "LIVE SL modification not supported by eToro API — DB value stored for monitoring, not enforced." Honest surfacing of the limitation.

**Tab — Orders**

Secondary tabs: All · Pending · Cancelled / Failed.

- **OrdersDataTable** — columns: checkbox, symbol, strategy, side, order_type, quantity, price, status pill, slippage (bps), fill_time (s), order_action (entry/close/retirement), created_at, row menu (cancel, delete, close position).
- **FilterBar** — search, status multi-select, side, source (auto/manual), strategy, date range.
- **ManualOrderDialog** — 2-step (fill → review → submit) with expected cost, risk impact, est slippage. Only available when account is set to one mode (not All).
- **BulkActions** — Cancel selected, Delete selected.
- **SidePanel** — OrderFlowTimeline + order-status-distribution pie + cancellation-reason bar.
- Pending sub-tab: unified pending orders + pending closures with per-asset-class market-status header (crypto 24/7, forex 24/5, stocks NYSE/NASDAQ hours). Fixes the current hardcoded US-only view.
- Cancelled/Failed sub-tab: includes the footnote "Entry orders logged as FAILED on market-close deferrals then retried — cosmetic, not real failures" (surfacing known backend behaviour honestly).

**Tab — Execution**

- **MetricTiles** — avg slippage (bps) · fill rate % · avg fill time (s) · rejection rate % · implementation shortfall (bps).
- **SlippageTrendChart** — daily P50/P75/P95 over selected period (new — missing today).
- **SlippageByStrategyBar** (Recharts) — slippage distribution per strategy.
- **SlippageByHourHeatmap** (Visx) — slippage × hour-of-day × day-of-week.
- **RejectionReasonsBar** — rejection count by category.
- **WorstExecutionsTable** — 20 worst fills (expected price, fill price, shortfall bps) with links to the order.
- **FillRateBuckets** — fill-time histogram (0-5s, 5-30s, 30-60s, >60s).
- Per-asset-class breakdown cards (Stocks / ETFs / Crypto / Forex / Commodities / Indices).

**Tab — Live**

Always visible; content changes based on master switch.

- **MasterSwitchBlock** — giant switch, 3 visual states (OFF / ON-no-auth / ON-active) with confirmation on toggle, warn-on-active-positions copy.
- **AccountTiles** — Virtual Equity + real · Today's P&L virtual+real · Open Positions + deployed % · Live Authorizations count.
- **MirrorRatioStrip** — one-line contextual reminder of the mirror math.
- Secondary tabs: Overview · Positions · Orders · Divergence.
  - Overview: live config reference card + recent live fills feed.
  - Positions: LivePositionsTable with columns virtual invested / real invested / both P&L columns, SL with DB-only badge, close action. Same shared `['positions', 'LIVE']` query.
  - Orders: live orders table (shared `['orders', 'LIVE']`).
  - Divergence: DivergenceTable (paper vs live Sharpe, divergence %) + DivergenceHeatmap (Visx) + retire action per row.

**Position detail (`/book/position/:symbol`):**
- PriceChart with all entries/exits overlaid as markers.
- Aggregate P&L card (realised + unrealised), avg entry, best/worst trade, all positions list (open + closed) for this symbol.

**User actions (across surface):**
- Close / bulk close / close all → `POST /account/positions/close` or `/close-all` → optimistic patch.
- Modify SL/TP dialog as specified above.
- Cancel/delete orders → `DELETE /orders/{id}` + `/permanent`.
- Sync with eToro (positions, orders).
- CSV export from any filtered table.
- Place manual order (dialog).
- Approve/dismiss fundamental alerts / pending closures.
- Toggle live master switch / close live position / retire live authorization.

---

### Surface 3 — Strategies

**Route:** `/strategies`
**Question answered:** *"What is the strategy library doing, and which pairs should graduate?"*
**Layout:** tab bar: Library · Cycle · Templates · Symbols · Graduation · Lab. Each tab manages its own split.

**Data sources (shared):**
- `useQuery(['strategies', mode, { slim: true }])` — 60s + WS `strategy_update`.
- `useQuery(['strategy', id])` — on selection, full detail.
- `useQuery(['templates'])`.
- `useQuery(['symbol-stats'])`.
- `useQuery(['template-rankings', mode])`.
- `useQuery(['blacklisted-combos'])`, `useQuery(['idle-demotions'])`.
- `useQuery(['autonomous-status'])` — 10s + WS.
- `useQuery(['autonomous-cycles', { limit: 30 }])`.
- `useQuery(['autonomous-schedules'])`.
- `useQuery(['graduation-queue'])` — 60s.
- `useQuery(['live-strategies'])`.

**Tab — Library** (default landing)

60/40 split: left strategy table, right selected-strategy detail panel (hidden when nothing selected, table expands to 100%).

- **StrategiesDataTable** — columns: checkbox, name (click → select in right panel), status pill (PROPOSED/BACKTESTED/PAPER/LIVE/RETIRED), category chip (alpha_edge / template_based / manual), template, regime pill, symbols count (popover for list), allocation %, Sharpe, total return, max DD, win rate, trades, open positions, **ConvictionBar mini**, health (0-5 colored dot), decay (10→0 countdown), alpha vs SPY, last activated. All columns sortable; multi-sort with shift-click.
- **FilterBar** — search, status, template, regime, source, category, type + **quick pills**: "Signals firing today" · "Idle 7d+" · "Negative live P&L" · "Graduation-eligible" · "Paper ≥ 20 trades".
- **Detail panel** (sticky right when a row selected):
  - **StrategyHeader** — name, status pill, conviction hero number, action buttons (Activate · Deactivate · Retire · Permanently Delete · Backtest · Graduate to LIVE).
  - **Sub-tabs:**
    - *Evidence* — walk-forward results (train vs test Sharpe/return/DD/WR side-by-side, consistency score gauge, bootstrap p5/p50/p95 ribbons), backtest equity curve (LWC), Monte Carlo confidence ribbons, regime distribution of historical trades.
    - *Reasoning* — hypothesis, alpha_sources with weight bars, market_assumptions, signal_logic in monospace block.
    - *Conviction* — **ConvictionDecomposition** stacked bar with all 9 components (WF edge 40 · signal quality 25 · regime fit 20 · asset tradability 15 · fundamental ±15 · carry ±5 · crypto cycle ±5 · sentiment ±1 · factor ±6), hover per segment. Threshold lines at 65 (DEMO) and 74 (LIVE equity) / 68 (LIVE crypto).
    - *Live performance* — live P&L curve since activation, vs backtest expectation line, trade-by-trade journal (MAE/MFE inline).
    - *Configuration* — allocation slider, SL/TP params (read-only for autonomous strategies), symbols list, proposal metadata.
- Compare action (select 2 strategies → Compare → side-by-side dialog).

**Tab — Cycle**

The autonomous cycle as a time dimension of the library. 30/40/30 split: Scheduler+Controls · Pipeline+Funnel · Live Stream.

- **SystemStateControl** — big pill (ACTIVE/PAUSED/STOPPED/EMERGENCY_HALT) + state-change buttons (Start · Pause · Stop · Resume · Reset), only valid transitions enabled.
- **SchedulerPanel** — multi-slot editor: enabled toggle, days chip multi-select, hour/minute UTC dropdowns, next-run preview, add/remove slots. Save only when dirty.
- **ManualCycleTrigger** — asset-class and interval chip filters → "Run Cycle Now" → confirmation → `POST /strategies/autonomous/trigger` with filters.
- **CyclePipelineVisual** (hero) — 9 stages horizontal: Cleanup → Market Analysis → Proposal → Walk-Forward → Monte Carlo → Direction-Aware Thresholds → Conviction Scoring → Activation → Signal Generation. Current stage highlighted `--accent-primary`; per-stage pass/drop counts; drop-off % between stages; red X overlay if stage errored (surfaces cycle-error gap).
- **SignalFunnel** — end-to-end funnel using the `signal_decisions` taxonomy: proposed → wf_validated → activated → signal_emitted → gate_blocked → order_submitted → order_filled. Hover shows rejection reasons aggregated.
- **CycleHistoryList** — last 30 cycles with duration + counts. Expand row for inline breakdown.
- **CycleIntelligencePanel** — templates/asset classes/regimes per cycle.
- **LiveStream** — rolling 100-event feed (proposals, WF results, activations, retirements, signals, fills, errors) with type chip filter, pause/resume toggle.

**Tab — Templates**

- **TemplatesGrid** — cards per template: toggle, rule preview (expand), active count, avg Sharpe / WR / return, total P&L, best/worst symbol, asset classes, timeframe, last proposed/activated. Bulk toggle. Direction filter (long/short).
- **TemplateRankingsTable** (below grid) — sortable leaderboard with family, timeframe filters, visible metrics (trades, win rate, Sharpe, P&L).

**Tab — Symbols**

- **SymbolsDataTable** — Current view (active strategies, usage count) + Lifetime view (proposed, traded, win rate, P&L, best template).
- Per-symbol detail drawer on row click: historical proposals, historical trades, performance over time, regime sensitivity.
- **Blacklists** and **Idle Demotions** read-only tables inline below (accordion).

**Tab — Graduation**

The CIO promotion workflow. Flagship decision surface.

- **GraduationQueueTable** — all candidates (template × symbol with ≥20 paper trades) sorted by qualification score. Columns: template, symbol, paper trades, paper Sharpe, paper win rate, paper P&L, qualification ratio, first paper trade date, regime spread. Click opens GraduationCard.
- **GraduationCard** (drawer 60% width) — see 3C `GraduationCard`. Full CIO card with paper equity curve + conviction distribution + regime distribution + live-config form (position_size, SL%, TP%, conviction_min, notes) + impact preview + Approve/Reject.
- **ActiveLiveTable** — currently-live authorizations with paper vs live Sharpe side-by-side, divergence %, retire action. Cross-links to Book → Live → Divergence for the heatmap view.
- Post-retirement section: retired live authorizations with reason + 14-day cooldown countdown. Re-graduate action when expired.

**Tab — Lab**

Research sandbox (preserves capability not buried in current UI):

- **BacktestRunner** — select strategy → date range → run → progress bar via WS `backtest_progress` → results in LWC + metrics.
- **VibeCodeTranslator** — natural-language → structured trading command preview (for testing manual strategy construction). Calls `POST /strategies/vibe-code/translate`.
- **GenerateStrategy** — prompt + constraints → `POST /strategies/generate` → preview → save or discard.
- **BootstrapRunner** — type filters + min_sharpe → `POST /strategies/bootstrap` → watch cycle run.

**User actions (across surface):**
- Per-strategy: Activate · Deactivate · Retire · Permanently Delete · Backtest · Graduate.
- Cycle: Start/Pause/Stop/Resume/Reset · Trigger Cycle Now · Save Schedule.
- Templates: Toggle per template, bulk toggle.
- Graduation: Approve · Reject (with cooldown) · Retire live.
- Lab: Backtest, translate vibe code, generate strategy, bootstrap.

---

### Surface 4 — Guard

**Route:** `/guard`
**Question answered:** *"What could stop us trading, and what is stopping us right now?"*
**Layout:** 30/70 split. Left = risk score hero + metric tiles + limit editor. Right = tab content.

**Data sources:**
- `useQuery(['risk-metrics', mode])` — 30s + WS.
- `useQuery(['risk-positions', mode])`, `['risk-limits', mode]`, `['risk-history', mode, period]`, `['risk-advanced', mode]`, `['risk-alerts', mode]`.
- `useQuery(['system-health'])` — 15s + WS `system_health`.
- `useQuery(['audit-log', filters])` with pagination + `['trade-lifecycle', id]` on expand.
- `useQuery(['data-sync-status'])`, `['data-quality']`, `['fmp-cache-status']`, `['news-sentiment-status']`, `['monitoring-status']`.

**Left panel (permanent):**
- **RiskScoreHero** — Safe / Warning / Danger pill + 3-line reason list. Click Warning/Danger to pulse the relevant metric tile.
- **RiskMetricTiles** — 6 tiles: VaR 95% · Current DD · Max DD · Leverage · Beta · Margin Utilisation. Each shows value · limit · % of limit.
- **LimitEditor** — inline editable sliders for each limit + **SaveBar** (dirty-state gated). Warning banner if change would breach current state.

**Right panel tabs:**

**Tab — Risk** (default)
- Per-strategy risk breakdown table with VaR contribution.
- Risk score trend chart (last 30 days).
- Position-level risk table: risk level (low/medium/high), risk amount, risk %, SL, TP, filter by level.
- **Exposures sub-section:**
  - Sector exposure horizontal bars with limit lines.
  - Asset-class exposure tiles.
  - **DirectionalExposureBar** — long / short / net with 60% limit line.
  - **CorrelationHeatmap** (Visx) — filter |ρ| > threshold.

**Tab — Gates**

**GateStatusGrid** — one card per gate, traffic-light state (green clear · amber warning · red blocking, pulsing when blocking). Each card shows current input values, last triggered timestamp, last triggered count, description paragraph. Gates covered:

- `kill_switch` (manual emergency stop)
- `market_hours` (per asset class)
- `vix_gate / C1` (VIX > 25 AND VIX_5d > +15% blocks LONG)
- `momentum_crash / C2` (SPY_5d < -3% AND VIX_1d > +10% → regime_fit -10 for LONG)
- `trend_consistency / C3` (blocks SHORT above rising 50d SMA; blocks LONG below falling 50d SMA)
- `rejection_blacklist` (14-day cooldown after manual rejection)
- `freshness_sla` (stale data blocks signals)
- `circuit_breaker_etoro` / `circuit_breaker_yahoo` / `circuit_breaker_fmp`

Gate card click → history drawer showing every trigger of that gate over selected period with which signals were blocked.

**Tab — System**

Merges current System Health + Data Management content into one surface.

- **HealthTiles** — Uptime · Error Rate 5m · Avg Response · Blockers count.
- **WebSocketHealthCard** — connection state, last message timestamp, reconnection attempts, manual reconnect.
- **MonitoringServiceCard** — running flag, sub-tasks grid (position_sync · trailing_stops · partial_exits · quick_update · full_sync · fundamental_exits) with last_run age and status.
- **BackgroundThreadsTable** — thread name, last_run, duration_s, status, symbols_updated.
- **DataSyncPanel** — sync progress (current/total symbols, elapsed, stats per interval), last full-sync duration, next scheduled time, sync logs live-tailed (last 50 lines), manual triggers (Full Sync · Quick Update · Warm FMP · Sync News Sentiment).
- **DbStatsCard** — total bars, by interval breakdown, unique symbols, latest/oldest bar, recent 1h symbols table.
- **DataQualityTable** — per-symbol score with asset-class and score-bucket filters.
- **EventTimeline24h** — horizontal timeline of system events (restarts, circuit trips, data gaps, errors).

**Tab — Circuit Breakers**

- **CircuitBreakerGrid** — one card per named CB (eToro, Yahoo, FMP, FRED, Marketaux, Binance) with state (CLOSED / HALF_OPEN / OPEN), failure count, last trip timestamp, failure threshold, recovery timeout.
- Per-CB timeline chart (last 24h) showing state transitions.
- Reset action per CB (requires confirmation).

**Tab — Alerts**

- **AlertsList** — historical risk + monitoring + autonomous alerts with filter (severity, event type, date range, unread-only).
- Per-alert card: title, message, metric current_value / threshold, timestamp, severity color, Acknowledge action (for critical), Mark read.
- Bulk actions: Mark all read, Clear all (with confirmation).
- **AlertPreferences** button → opens alert config dialog (thresholds, browser push enable).

**Tab — Audit**

- **AuditLogVirtualized** — TanStack Virtual list, infinite scroll, per-row event type badge + timestamp + severity + description.
- **FilterBar** — event type multi-select, severity, date range, symbol, free-text search (debounced 200ms).
- Row expand → **TradeLifecycleChain**: signal → risk validation → order → fill → position → trailing stops → close, each step with timestamp + details.
- Export CSV with current filters.

**User actions (across surface):**
- Edit risk limits → `PUT /risk/limits`.
- Kill-switch confirm dialog → `POST /control/kill-switch`.
- Reset circuit breaker → `POST /control/circuit-breaker/reset`.
- Reset system from emergency halt → `POST /control/system/reset`.
- Acknowledge alert → `POST /alerts/history/{id}/acknowledge`.
- Trigger data sync / quick update / FMP cache / news sentiment.
- Clear blacklists (admin).
- Export audit CSV.

---

### Surface 5 — Research

**Route:** `/research`
**Question answered:** *"Does our edge exist, and where does it come from?"*
**Layout:** horizontal tab bar. Each tab is a full-width content area. Global period selector (1W/1M/3M/6M/1Y/ALL) + interval (1d/4h/1h) persisted in Zustand — switching tabs keeps selection.

**Tabs:**

**Tab — Performance** (default)
- MetricTiles: total_return · Sharpe · Sortino · max DD · win rate · profit factor · daily_returns_count.
- EquityChart (LWC) with drawdown overlay, realised line, SPY overlay.
- Returns distribution histogram (Recharts).
- Monthly returns heatmap (Visx) — years on rows, months on cols.
- Annual returns bar chart.

**Tab — Attribution**
- Per-strategy attribution table: strategy, template, regime, total return, contribution %, Sharpe, trades, win rate.
- Strategy contribution bar chart.
- **Sector attribution** sub-section (moved from the old Perf Attribution tab): per-sector allocation / selection / interaction effects with cumulative stacked area chart.

**Tab — Trades**
- Tiles: total trades, winning, losing, avg holding period, best trade, worst trade.
- Win/loss distribution pie.
- Holding-period histogram.
- P&L by hour-of-day bar.
- P&L by day-of-week bar.
- Trade-size distribution (Recharts).

**Tab — Regime**
- **CurrentRegimesGrid** — 4 cards: Equity · Crypto · Forex · Commodity — each shows regime, confidence, data quality, 20d/50d change, ATR ratio, included symbols.
- **PerformanceByRegimeTable** — regime, total return, Sharpe, trades, win rate.
- **RegimeTransitionsTimeline** — historical regime changes.
- **StrategyRegimeHeatmap** (Visx) — templates on y, regimes on x, cell = total P&L.
- **MarketContextPanel** — VIX, yield curve inversion, fed funds rate, GDP nowcast, CPI, ISM PMI.
- **CryptoCyclePanel** — halving phase, recommendation.
- **CarryRatesPanel** — forex carry differentials.
- **MarketQualityScore** — score (0-100) + grade (High/Normal/Choppy) + component breakdown.

**Tab — Alpha Edge**
- Fundamental filter stats: hit/miss counts, P&L impact per check (profitable · growing · reasonable_valuation · no_dilution · insider_buying).
- ML filter stats: confidence distribution + outcome overlay (win rate per confidence bucket).
- **ConvictionDistribution** histogram with P&L overlay + threshold lines at 65/74.
- Per-template performance with sample size indicator.
- Transaction-cost savings tile.

**Tab — Tear Sheet**
- UnderwaterPlot (Visx) — drawdown ribbon over time.
- Worst-drawdowns table (top 5): rank, start date, trough date, recovery date, depth %, duration days, recovery days.
- Return distribution histogram + skew + kurtosis + annualized vol.
- Annual returns grid (year × return bar).
- Monthly returns heatmap.
- Download PDF button (server-side generation; client-side TearSheetGenerator dropped — see stack decisions).

**Tab — Stress** (moved here from Analytics and Risk)
- Scenario cards: COVID crash · 2008 · inflation shock · rate spike · flash crash · etc. Each with estimated loss, loss %, affected positions, VaR contribution.
- Custom scenario builder: symbol shock % + volatility multiplier + correlation shift + time horizon → preview impact.

**Tab — Journal**
- **TradeJournalVirtualizedList** — per-trade row with entry/exit time, price, size, reason, pnl, hold time, MAE, MFE, conviction, ML confidence, regime, sector.
- Per-trade expand → detailed lifecycle + price chart with entry/exit markers.
- **MaeMfeScatter** (Visx) — MAE on x, MFE on y, cell = pnl sign colour.
- **PatternsPanel** — best patterns + worst patterns + recommendations (from `/analytics/trade-journal/patterns`).
- Export CSV with filters.

**User actions:** purely read-only. No live trading actions from Research — deliberate separation.

---

### Off-nav surfaces

- **`/settings`** — keyboard `g ,`. Vertical tab nav (Trading Mode · API Config · Risk Limits · Position Management · Autonomous · Alpha Edge · Alerts · Live Trading · Users · Shortcuts). Each form: react-hook-form + zod + SaveBar with dirty diff. **AutonomousConfigForm** gets collapsible sections (Cycle Cadence · Strategy Library · Activation Thresholds · Walk-Forward · Conviction · Retirement · Adaptive Risk · Direction-Aware Thresholds) + in-form search. Every field has a FieldInfoTooltip pointing to the log line / metric it gates.
- **`/login`** — username/password, 5/min/IP rate limit.
- **`/book/position/:symbol`** — position detail drill-down (deep-linked).

### Cross-cutting behaviour

### Cross-cutting behaviour

**WebSocket disconnect handling:**
- Global connection-state indicator in TopNavBar (dot: green open / amber reconnecting / red closed).
- On disconnect: all `useQuery` with `refetchInterval` continue polling at their configured rates (TanStack Query's built-in behaviour).
- On reconnect: automatically `queryClient.invalidateQueries()` on the top-level keys — positions, orders, strategies, autonomous-status — to catch up on anything missed.
- Toast on reconnect: "Reconnected after 12s — data refreshed."

**Keyboard shortcuts** (global):

| Shortcut | Action |
|---|---|
| `g c` | Go to Command |
| `g b` | Go to Book |
| `g s` | Go to Strategies |
| `g g` | Go to Guard |
| `g r` | Go to Research |
| `g ,` | Go to Settings |
| `⌘K` / `Ctrl+K` | Open Command Palette |
| `/` | Focus page search |
| `?` | Keyboard shortcut help |
| `Esc` | Close modal / dropdown / drawer |
| `⌘Enter` in forms | Save |
| `j / k` in tables | Move selection up/down |
| `x` in tables | Toggle row checkbox |
| `[ / ]` | Previous / next tab within a surface |
| `⌘\\` | Toggle primary sidebar / panel |



---

## 3C. Component library specification

Every component lives in `src/components/<group>/<Component>.tsx`. Variants via `class-variance-authority`. All props typed with TypeScript interfaces. All stateful components exposed as controlled + uncontrolled via optional prop.

### Primitives (shadcn-style, built on Radix)

| Component | Props | Visual | States |
|---|---|---|---|
| `Button` | `variant: 'primary' \| 'secondary' \| 'ghost' \| 'destructive' \| 'live'`, `size: 'sm' \| 'md' \| 'lg'`, `loading`, `icon`, `iconPosition` | 28/32/36px height, 12/13/14px font | all 9 states |
| `Input` | `size`, `variant: 'default' \| 'filled'`, `prefix`, `suffix`, `error` | 28/32px height | default / hover / focus / error / disabled |
| `Select` | Radix Select wrapped. `value`, `onValueChange`, `options`, `placeholder`, `multi` (custom). | matches Input | all states |
| `MultiSelect` | chips + searchable dropdown | |
| `Tabs` | Radix Tabs. `orientation: 'horizontal' \| 'vertical'`, `variant: 'underline' \| 'pills' \| 'sidebar'` | |
| `Dialog` | Radix Dialog. `size: 'sm' \| 'md' \| 'lg' \| 'xl' \| 'full'` | center overlay, 150ms fade |
| `Popover` | Radix Popover. | |
| `DropdownMenu` | Radix DropdownMenu. | |
| `Tooltip` | Radix Tooltip. 300ms open delay. `variant: 'default' \| 'info' \| 'warning'` | |
| `Switch` | Radix Switch. `size: 'sm' \| 'md' \| 'lg'`. `variant: 'default' \| 'live'` (green for LIVE master switch) | |
| `Checkbox` | Radix Checkbox. | |
| `Badge` | `variant: 'default' \| 'success' \| 'warning' \| 'error' \| 'info' \| 'regime-up' \| 'regime-down' \| 'regime-range' \| 'regime-vol' \| 'demo' \| 'live' \| 'paper' \| 'backtested' \| 'retired'`, `size: 'sm' \| 'md'` | |
| `Card` | `padding: 'sm' \| 'md' \| 'lg'`, `interactive`, `variant: 'default' \| 'elevated' \| 'flush'` | |
| `Skeleton` | `variant: 'text' \| 'block' \| 'circle' \| 'table-row' \| 'chart' \| 'metric-tile'`, `count` | 1200ms shimmer (`--bg-1` → `--bg-2` → `--bg-1`) |
| `Spinner` | `size: 'xs' \| 'sm' \| 'md' \| 'lg'` | only for async buttons, never full-screen |
| `ConfirmDialog` | `title`, `description`, `confirmLabel`, `confirmVariant`, `onConfirm`, `isLoading`, `destructive` | |
| `Toast` (sonner wrapper) | use `toast.success / error / info / warning` from `src/lib/toast.ts` | |

### Layout primitives

| Component | Purpose |
|---|---|
| `AppShell` | Persistent shell (TopNav + MetricsBar + Ticker + Outlet + BottomWidgetZone). Mounted once per session. |
| `PageTemplate` | Inside Outlet. Title + description + actions + children. |
| `ResizablePanelLayout` | Wrapper over `react-resizable-panels` with localStorage persistence per `layoutId`. |
| `PanelHeader` | Panel header bar (32px) with title, actions, optional refresh button. |
| `SectionLabel` | 11px muted uppercase label with optional actions. |
| `MetricGrid` | Grid of metric tiles (2/3/4 cols responsive). |
| `FilterBar` | Flex bar for search input + filter dropdowns with consistent spacing. |
| `SaveBar` | Dirty-state form footer: unsaved changes count + Save + Reset buttons. |
| `EmptyState` | Icon + title + description + optional CTA. Used for "No data" and "No results after filter". |
| `ErrorState` | Icon + title + description + retry button. Used when an API returns error. |

### Trading-specific components

#### `MetricsBar`

Top bar with real-time account metrics. Mounts in AppShell.

```typescript
interface MetricsBarProps {
  mode: TradingMode; // drives ?mode= on all underlying queries
}
```

Internal: 6 tiles horizontally scrolling on narrow viewports — Equity, Daily P&L (PnLNumber), Unrealized (PnLNumber), Open Positions, Today's Orders, Active Strategies. Plus **AccountToggle** on the right, **LivePill** next to it.

Data: `useQuery(['metrics-bar', mode])` → `/account/metrics-bar` — 10s poll + WS.

#### `AccountToggle`

DEMO / LIVE switcher. Segmented control.

```typescript
interface AccountToggleProps {
  value: TradingMode;
  onChange: (mode: TradingMode) => void;
  liveEnabled: boolean; // dims LIVE label if master switch off
}
```

Visual: 2 segments, DEMO blue background when selected, LIVE green when selected AND `liveEnabled === true`, otherwise LIVE greyed with dot.

#### `RegimePill`

```typescript
interface RegimePillProps {
  regime: 'trending_up_strong' | 'trending_up' | 'trending_up_weak' | 'ranging' | 'trending_down_weak' | 'trending_down' | 'trending_down_strong' | 'high_vol' | 'volatile';
  confidence?: number;           // 0-1
  dataQuality?: 'high' | 'medium' | 'low';
  size?: 'sm' | 'md' | 'lg';
  showConfidence?: boolean;
}
```

Visual: rounded 4px, background colored per regime (from design tokens), text white, optional `(87%)` inline. Data quality: small diamond indicator (green/amber/red) after the text.

#### `LivePill`

```typescript
interface LivePillProps {
  state: 'off' | 'on-no-authorisations' | 'on-active';
  authorisationCount?: number;
}
```

Visual:
- `off` → grey dot + `LIVE OFF`, grey text.
- `on-no-authorisations` → amber dot (pulsing 2s period) + `LIVE ON · 0 auth`, amber text.
- `on-active` → green dot (steady) + `LIVE · {N}`, green text on dark-green bg.

#### `PnLNumber`

```typescript
interface PnLNumberProps {
  value: number;
  format?: 'currency' | 'percentage' | 'decimal';
  precision?: number;
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl';
  showSign?: boolean; // default true for non-zero
  flashOnChange?: boolean; // default true
  animate?: boolean; // false disables flash
}
```

Visual: monospace, tabular-nums, colored by sign (`--pnl-up` / `--pnl-down` / `--pnl-flat`). Flash: on value change (tracked via `useRef` previous value), background tints `--pnl-up-flash` or `--pnl-down-flash` for 400ms, fades to default.

#### `ConvictionBar`

```typescript
interface ConvictionBarProps {
  score: number;                    // 0-100
  components?: {
    wf_edge: number;                // 0-40
    signal_quality: number;         // 0-25
    regime_fit: number;             // 0-20
    asset_tradability: number;      // 0-15
    fundamental: number;            // -15 to +15
    carry: number;                  // -5 to +5
    crypto_cycle: number;           // -5 to +5
    sentiment: number;              // -1 to +1
    factor: number;                 // -6 to +6
  };
  size?: 'mini' | 'default' | 'large';
  showValue?: boolean;
  threshold?: number;               // renders vertical line at threshold (e.g. 74 for LIVE)
}
```

Visual:
- `mini` — 4px tall horizontal bar, solid colour from conviction heat gradient by score. No decomposition.
- `default` — 8px tall stacked bar showing each positive component as a segment, negative components subtract from total, grey area = headroom to 100, vertical threshold line.
- `large` — full stacked bar with labels + tooltip per segment, threshold line with label.

#### `EquityChart`

```typescript
interface EquityChartProps {
  equityData: Array<{ date: string; equity: number; realized?: number }>;
  dailyEquity?: Array<{ date: string; equity: number }>;   // for mixed interval fallback
  spyData?: Array<{ date: string; close: number }>;        // benchmark overlay
  drawdownData?: Array<{ date: string; drawdown_pct: number }>;
  period: '1W' | '1M' | '3M' | '6M' | '1Y' | 'ALL';
  onPeriodChange: (p: string) => void;
  interval: '1d' | '4h' | '1h';
  onIntervalChange: (iv: string) => void;
  height?: number;                  // if omitted, AutoHeight measures container
  showBenchmark?: boolean;
  showRealized?: boolean;
  showDrawdown?: boolean;
  crosshair?: boolean;              // default true
}
```

Renders two panes (TradingView LWC v5):
- Pane 1: equity line (`--accent-primary`), optional realized dashed line (`--text-2`), optional SPY overlay (amber).
- Pane 2: drawdown area (red, filled). Hidden if `showDrawdown=false`.
- Crosshair syncs between panes. Hover readout card top-right.
- Period / interval selectors on top-left.

#### `PriceChart`

OHLC with signal markers.

```typescript
interface PriceChartProps {
  symbol: string;
  interval: '1m' | '5m' | '15m' | '30m' | '1h' | '4h' | '1d';
  bars: Array<OHLCV>;
  signals?: Array<{
    timestamp: string;
    type: 'entry' | 'exit' | 'stop' | 'tp';
    side: 'long' | 'short';
    price: number;
    reason?: string;
  }>;
  indicators?: Array<IndicatorConfig>;   // EMA/SMA/RSI/ATR overlays
  height?: number;
}
```

Renders: candlestick series, volume histogram, optional indicator overlays/panes, signal markers as up/down arrows color-coded by type.

#### `StrategyCard`

```typescript
interface StrategyCardProps {
  strategy: Strategy;
  compact?: boolean;
  onClick?: () => void;
  selected?: boolean;
  showConviction?: boolean;
  showLivePnL?: boolean;
}
```

Visual: compact card with name (truncated), template, status pill, conviction mini-bar, Sharpe/return/WR/trades row, alpha vs SPY pill, live auth badge if applicable. Selected state: `--bg-active`, left border `--accent-primary`.

#### `GraduationCard`

The CIO decision card — the single most important decision UI in the app.

```typescript
interface GraduationCardProps {
  candidate: {
    strategy_id: string;
    template_name: string;
    symbol: string;
    paper_trades: number;
    paper_sharpe: number;
    paper_win_rate: number;
    paper_total_pnl: number;
    qualification_ratio: number;
    first_paper_trade: string;
  };
  onApprove: (body: GraduationBody) => Promise<void>;
  onReject: (body: { reason: string }) => Promise<void>;
  onCancel: () => void;
}
```

Layout (modal / side drawer):
- **Top block:** template name + symbol + "Since {first_paper_trade}" subtitle.
- **Evidence block:** paper equity curve (EquityChart small), trades KPI grid (trades, Sharpe, win rate, total P&L), conviction distribution of recent signals for this pair, qualification ratio dial.
- **Config block:** form — position_size (default 500, slider 200–1500 virtual), sl_pct (default 6%), tp_pct (default 15%), conviction_min (default 74 equities / 68 crypto, shown next to each other), notes (textarea).
- **Impact block:** "Approving means: $500 virtual → $50 real per order. Symbol cap $2,000 virtual. Max simultaneous positions: 2. Signals fire every 30 min." (derived from config).
- **Action bar:** Reject (secondary, opens reason textarea), Approve (primary, green, triggers confirmation toast).

#### `SignalFunnel`

```typescript
interface SignalFunnelProps {
  stages: Array<{
    name: string;
    count: number;
    dropReasons?: Record<string, number>;
  }>;
  cycleId?: string;
  compareTo?: Array<{ name: string; count: number }>; // previous cycle
}
```

Visual: horizontal funnel. Each stage is a trapezoid whose height is proportional to count. Between stages, small label `-N (XX%)` showing drop. Hover a stage to see dropReasons popover.

Stages: `proposed` → `wf_validated` → `activated` → `signal_emitted` → `gate_blocked` → `order_submitted` → `order_filled`.

#### `DataTable`

```typescript
interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T>[];          // TanStack Table
  rowKey: (row: T) => string;
  virtualized?: boolean;             // auto-on when >100 rows
  selection?: {
    selected: Set<string>;
    onChange: (s: Set<string>) => void;
    mode: 'single' | 'multi';
  };
  sorting?: {
    state: SortingState;
    onChange: OnChangeFn<SortingState>;
  };
  density?: 'compact' | 'default' | 'comfortable';
  onRowClick?: (row: T) => void;
  emptyState?: React.ReactNode;
  loading?: boolean;
  loadMore?: () => void;
  hasMore?: boolean;
}
```

Built on TanStack Table + TanStack Virtual. Sticky header. Column resize. Column sorting with Shift+click for multi-sort. Keyboard navigation (j/k rows, Enter to click). Density 'compact' = 24px rows / 10px font. 'default' = 28px / 12px. 'comfortable' = 36px / 13px.

#### `HeatMap`

```typescript
interface HeatMapProps {
  data: Array<{ x: string; y: string; value: number }>;
  xLabel?: string;
  yLabel?: string;
  colorScale?: 'divergent' | 'sequential' | 'conviction';
  valueFormat?: (v: number) => string;
  cellSize?: number;
  onClick?: (cell: { x: string; y: string; value: number }) => void;
}
```

Implemented with Visx. Divergent for correlation matrix (red-blue from -1 to +1). Sequential for drop-off %. Conviction for the conviction gradient. Fixed cell sizes (22–40px depending on density). Tooltip on hover with value + x/y labels.

Used for:
- Regime × template performance (Analytics → Regime tab).
- Correlation matrix (Risk → Exposures tab).
- Divergence heatmap (Live → Divergence tab).
- Monthly returns heatmap (Analytics → Tear Sheet / Performance).

#### `GateStatus`

Traffic-light indicator for signal-time gates.

```typescript
interface GateStatusProps {
  gate: {
    name: string;                        // e.g. "VIX Gate (C1)"
    description: string;                 // "Blocks LONG when VIX>25 AND VIX_5d>+15%"
    state: 'clear' | 'warning' | 'blocking';
    currentValues?: Record<string, number | string>;
    lastTriggeredAt?: string;
    lastTriggeredCount?: number;
  };
  onClick?: () => void;
}
```

Visual: card with gate name, traffic-light icon (green clear, amber warning, red blocking — pulsing when blocking), description paragraph, current values grid, "Last triggered: 2h ago (3 blocks)". Click expands to history.

#### `PositionTickerStrip`

Persistent thin strip at bottom of TopNavBar.

```typescript
interface PositionTickerStripProps {
  mode: TradingMode;
}
```

Visual: 24px tall horizontal scroll with top 10 positions by |unrealized_pnl|, each as `AAPL +1.24% $45.20`. Greens / reds colored. Clicking a ticker navigates to `/portfolio/<symbol>`.

Data: shared `useQuery(['positions', mode])` cached.

#### `BottomWidgetZone`

Persistent bottom strip — 3 slots: TopMovers, RecentSignals, StrategyAlerts. Collapsible.

```typescript
interface BottomWidgetZoneProps {
  defaultCollapsed?: boolean;
}
```

Each slot pulls from `/dashboard/*` queries.

#### `CommandPalette`

```typescript
interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}
```

⌘K opens it. Fuzzy search (fuse.js) across:
- Navigation ("go to Portfolio")
- Actions ("trigger cycle", "kill switch", "close all positions")
- Strategies (by name)
- Symbols
- Recent commands (stored in Zustand)

Keyboard-first. Enter executes. Esc closes.

#### `NotificationToast` / `NotificationDrawer`

Sonner for transient toasts. Drawer (right-side slideout) for the full notification history with filters.

### Compose patterns — how components chain together

**Selected-row pattern:** `DataTable` emits `onRowClick`, page state holds `selectedId`, page renders a detail panel conditionally. No dialog-on-dialog.

**Form pattern:** `react-hook-form` at top of form, `zod` for schema, each field uses our primitives (`Input`, `Select`, `Switch`), `SaveBar` listens to `formState.isDirty`.

**Filter pattern:** every filter bar writes into Zustand `filtersStore` under a per-page key, `useQuery` uses the filter slice in its queryKey, so changes trigger refetch and URL syncing (via `react-router` search params).

---

## 3D. Technical stack — final decisions

| Layer | Choice | Justification |
|---|---|---|
| Framework | React 19 + TypeScript 5.9 + Vite 6 | Keep. Fastest dev feedback loop; React 19 `use()` hook for async boundaries. |
| Styling | Tailwind 4 + CSS variables for design tokens | Keep. Tokens as CSS vars means theming works with zero runtime. |
| Component primitives | Radix UI + own layer in shadcn style | Decided in 2E — headless behaviour, own styling. |
| Data fetching / server state | TanStack Query 5 | Decided in 2F. |
| Client state | Zustand 5 (with persist middleware) | Decided in 2F. |
| Price / OHLC charts | TradingView Lightweight Charts 5 | Decided in 2D. |
| Analytics charts — simple | Recharts 2 | Decided in 2D. |
| Analytics charts — bespoke (heatmaps, underwater) | Visx (`@visx/heatmap`, `@visx/scale`, `@visx/axis`, `@visx/tooltip`) | Decided in 2D. |
| Tables | TanStack Table 8 + TanStack Virtual 3 | Keep. Best-in-class. |
| Forms | React Hook Form 7 + Zod 4 | Keep. |
| Animations | Framer Motion 12 | Keep, but use sparingly per animation principles. |
| Toasts | Sonner 2 | Keep. |
| Icons | Lucide 0.575 | Keep. |
| Date | date-fns 4 | Keep. |
| Fuzzy search | Fuse.js 7 | Keep — powers CommandPalette and in-form search. |
| Panel layout | react-resizable-panels 4 | Keep. |
| CSS composition | clsx + tailwind-merge + class-variance-authority | Keep. |
| Fonts | `@fontsource-variable/inter`, `@fontsource-variable/jetbrains-mono` | New — self-hosted for offline EC2 build. |
| Testing | Vitest 4 | Keep (minimal tests — visual QA via storybook later if needed). |
| Linting | ESLint 9 + typescript-eslint | Keep. |
| HTTP client | Fetch-based client written on top of `fetch` with interceptors for session + error classification. Drop axios. | Axios is 14kb; modern fetch with AbortController handles everything we need. |

**Dependencies to drop from current `package.json`:**
- `axios` → replaced with fetch wrapper.
- `html2canvas` + `jspdf` → move tear-sheet PDF to backend or drop (decision: drop; user can screenshot, and the tear sheet data is exportable as CSV anyway).

---

## 3E. Implementation plan — ordered sprints

Each sprint delivers a shippable increment. Deploy after every sprint. Verify the shell renders, then move on.

### Sprint 0 — Foundation (blocker for everything else)

**Goal:** scaffold, design system, all primitive components, empty shell rendered at `https://alphacent.co.uk`.

**Steps:**
1. Archive current frontend: `git mv frontend frontend_v1 && git commit -m "Archive frontend v1 before rebuild"` + `scp -r` current build to `/home/ubuntu/alphacent/frontend_v1_backup` on EC2 (backup already in the Session_Continuation prompt).
2. Scaffold new `frontend/` with Vite + React 19 + TypeScript + Tailwind 4.
3. Install chosen deps (see 3D).
4. Implement `src/lib/design-tokens.ts` + `src/index.css` with every CSS variable from 3A.
5. Build every primitive (Button, Input, Select, Tabs, Dialog, Popover, DropdownMenu, Tooltip, Switch, Checkbox, Badge, Card, Skeleton, Spinner, ConfirmDialog + layout primitives AppShell, PageTemplate, ResizablePanelLayout, PanelHeader, SectionLabel, MetricGrid, FilterBar, SaveBar, EmptyState, ErrorState).
6. Write `src/services/api.ts` as a typed fetch wrapper with session cookie, error classification, and `ApiError` type.
7. Write `src/services/websocket.ts` — thin wrapper around native WebSocket with reconnection, ping/pong, subscription model (or lift the existing file's logic).
8. Set up TanStack Query client in `main.tsx` with default `staleTime: 30_000`, `refetchOnWindowFocus: false`, global error handler that shows toast.
9. Set up Zustand stores: `trading-mode`, `layout`, `theme`, `command-palette`, `notifications`, `filters` (per-page keyed), `research` (period/interval selection).
10. Set up React Router with placeholders for every surface route (`/`, `/book`, `/strategies`, `/guard`, `/research`, `/settings`, `/login`, `/book/position/:symbol`). Sub-tabs via nested routes so deep linking works.
11. Implement AppShell with TopNavBar (5 primary nav items + Settings icon) + MetricsBar + PositionTickerStrip + BottomWidgetZone — all wired to real queries.
12. Deploy to EC2 (`npm run build` → `scp dist/` → nginx already serves `frontend/dist`).

**Exit criteria:** login works, every surface renders a "Coming soon" PageTemplate. MetricsBar shows real data. WebSocket connects. No console errors.

### Sprint 1 — Command

Build Pulse panel (AccountHero, MetricsStrip, MultiTimeframeReturns, RegimeBlock, HealthScoreCard decomposed, CycleStatusCard, StrategyPipelineCounts), EquityChart center panel (LWC with drawdown + SPY + realised overlays), Stream panel (SignalFeed, OrderFillsTicker, LifecycleFeed, AlertsBadge). Empty/loading/error states. Keyboard shortcuts `g c`. Deploy.

### Sprint 2 — Book / Positions

Account-segmented surface header. Positions tab with Open / Pending Closures / Fundamental Alerts / Closed sub-tabs. PositionsDataTable, ModifySL/TPDialog (with LIVE honesty note), BulkActionBar, AllocationPanel with pie + sector bars + DirectionalBar. Position detail route `/book/position/:symbol` with PriceChart and entry/exit markers. CSV export. Keyboard `g b`. Deploy.

### Sprint 3 — Book / Orders + Execution

Orders tab with All / Pending / Cancelled-Failed sub-tabs. OrdersDataTable, ManualOrderDialog (2-step), BulkActionBar, per-asset-class market status header. Execution tab with tiles, SlippageTrendChart (new), SlippageByStrategyBar, SlippageByHourHeatmap (Visx), RejectionReasonsBar, WorstExecutionsTable, FillRateBuckets, per-asset-class breakdown. Sync with eToro actions. Deploy.

### Sprint 4 — Book / Live

Live tab as flagship sub-surface of Book. MasterSwitchBlock (3 states, warn on active positions), AccountTiles (virtual + real), MirrorRatioStrip. Overview/Positions/Orders/Divergence sub-tabs. LivePositionsTable with virtual vs real columns. DivergenceTable + DivergenceHeatmap (Visx) + retire action. Shared `['positions', 'LIVE']` / `['orders', 'LIVE']` query keys across Book. Deploy.

### Sprint 5 — Strategies / Library

StrategiesDataTable with slim payload, quick-pill filters, full detail panel with Evidence / Reasoning / Conviction (ConvictionDecomposition) / Live performance / Configuration sub-tabs. Compare dialog for 2 strategies. Activate/Deactivate/Retire/Permanently Delete/Backtest actions. Keyboard `g s`. Deploy.

### Sprint 6 — Strategies / Cycle

SystemStateControl, SchedulerPanel (multi-slot), ManualCycleTrigger, CyclePipelineVisual (9 stages with error overlay), SignalFunnel (new, end-to-end), CycleHistoryList, CycleIntelligencePanel, LiveStream. All WS subscriptions. Deploy.

### Sprint 7 — Strategies / Templates + Symbols + Graduation + Lab

TemplatesGrid + TemplateRankingsTable. SymbolsDataTable with Current vs Lifetime views + blacklists/idle-demotions accordion. **GraduationCard** flagship (the CIO workflow) + GraduationQueueTable + ActiveLiveTable + retired-with-cooldown section. Lab tab: BacktestRunner, VibeCodeTranslator, GenerateStrategy, BootstrapRunner. Deploy.

### Sprint 8 — Guard / Risk + Gates

RiskScoreHero, RiskMetricTiles, LimitEditor with SaveBar. Risk tab (per-strategy breakdown, trend chart, positions table with risk level, Exposures sub-section with sector bars, DirectionalExposureBar, CorrelationHeatmap Visx). **Gates tab** (new — GateStatusGrid with traffic-light cards for kill_switch, market_hours, C1 VIX, C2 momentum, C3 trend consistency, rejection_blacklist, freshness_sla, per-broker circuit breakers). Keyboard `g g`. Deploy.

### Sprint 9 — Guard / System + Circuit Breakers + Alerts + Audit

System tab (HealthTiles, WebSocketHealthCard, MonitoringServiceCard, BackgroundThreadsTable, DataSyncPanel with live log tail, DbStatsCard, DataQualityTable, EventTimeline24h). Circuit Breakers tab (per-CB cards + transition timelines + reset action). Alerts tab (AlertsList + filters + AlertPreferences dialog). Audit tab (AuditLogVirtualized + TradeLifecycleChain + CSV export). Deploy.

### Sprint 10 — Research / Performance + Attribution + Trades

Performance tab (MetricTiles, EquityChart with overlays, Returns distribution, Monthly returns heatmap Visx, Annual returns bar). Attribution tab (per-strategy table, contribution bar, sector attribution sub-section). Trades tab (all trade analytics tiles + charts + hour/day P&L bars). Shared period + interval selectors in Zustand `research` store. Keyboard `g r`. Deploy.

### Sprint 11 — Research / Regime + Alpha Edge + Tear Sheet + Stress + Journal

Regime tab (CurrentRegimesGrid per-asset-class, StrategyRegimeHeatmap, MarketContext, CryptoCycle, CarryRates, MarketQualityScore). Alpha Edge tab (fundamental + ML filter stats, ConvictionDistribution with thresholds, per-template performance). Tear Sheet tab (UnderwaterPlot Visx, worst-drawdowns table, return distribution with skew/kurtosis, annual + monthly heatmaps, PDF download via backend endpoint). Stress tab (scenario cards + custom builder). Journal tab (TradeJournalVirtualizedList, MaeMfeScatter Visx, PatternsPanel, CSV export). Deploy.

### Sprint 12 — Settings + Cross-cutting polish

Settings at `/settings` with all 10 tabs. **AutonomousConfigForm** with collapsible sections + in-form search + FieldInfoTooltip per field. Users tab (admin CRUD). Shortcuts tab (reference view). Command palette (⌘K) with fuzzy search across navigation/actions/strategies/symbols. Keyboard shortcuts module. Notification drawer. Onboarding empty states. Error boundaries. Final accessibility pass (focus rings, ARIA labels, colour-blind-safe semantic redundancy — always pair colour with icon/text, never colour alone).

### Sprint order rationale

Command first validates the primitives at real density and surfaces every integration point (equity chart, signal feed, metrics bar WS flash). Book next because positions/orders are the highest-traffic data. Strategies library before cycle because the detail panel must exist before the cycle's LiveStream can link into it. Graduation Card gets a dedicated sprint — it is the highest-stakes decision surface in the product. Guard before Research because it surfaces blockers that the CIO needs to see even before opening the deep-dive. Research last among the five surfaces because every chart it needs is already proven in earlier sprints. Settings last so every field knows which log line / metric it gates.

---

# Appendix

## A1. Light theme palette (inverse of dark)

For users who want it. Same token names, inverted luminosity. Not default.

| Token | Hex |
|---|---|
| `--bg-0` | `#fafafa` |
| `--bg-1` | `#ffffff` |
| `--bg-2` | `#f4f5f7` |
| `--bg-3` | `#eceef2` |
| `--text-0` | `#0a0a0b` |
| `--text-1` | `#26272d` |
| `--text-2` | `#5a5e68` |
| `--text-3` | `#8a8e99` |
| `--pnl-up` | `#16a34a` (darker for AA contrast on light bg) |
| `--pnl-down` | `#dc2626` |
| (other tokens unchanged) | |

## A2. Environment variables

| Var | Purpose |
|---|---|
| `VITE_API_BASE_URL` | e.g. `https://alphacent.co.uk` |
| `VITE_WS_BASE_URL` | e.g. `wss://alphacent.co.uk` |
| `VITE_BUILD_SHA` | git commit SHA injected at build time, shown in System Health |
| `VITE_BUILD_TIMESTAMP` | build time, shown in System Health |

## A3. Permissions map — 5-surface collapse

Per `TopNavBar.PAGE_PERMISSION_MAP`:

| Path | Permission page name | Covers (legacy permissions consolidated) |
|---|---|---|
| `/` | command | overview |
| `/book` | book | portfolio, orders, live |
| `/strategies` | strategies | strategies, autonomous |
| `/guard` | guard | risk, system-health, audit-log, data |
| `/research` | research | analytics |
| `/settings` | settings | settings |

Back-compat during migration: the backend `auth.py` ROLE_PERMISSIONS map gains the 5 new permission names as aggregates of the old ones. Old permission names stay valid (existing user rows work). Nav items hidden when the permission is absent. Routes also gated server-side via FastAPI `require_action`.

Migration SQL (one-time, idempotent):

```sql
-- Grant new aggregate permissions based on any legacy permission in the set.
UPDATE users SET permissions = jsonb_set(permissions, '{pages}',
  (SELECT jsonb_agg(DISTINCT p)
   FROM jsonb_array_elements_text(permissions->'pages') AS p(p))
       || CASE WHEN permissions->'pages' ?| ARRAY['overview']
               THEN '["command"]'::jsonb ELSE '[]'::jsonb END
       || CASE WHEN permissions->'pages' ?| ARRAY['portfolio','orders','live']
               THEN '["book"]'::jsonb ELSE '[]'::jsonb END
       || CASE WHEN permissions->'pages' ?| ARRAY['strategies','autonomous']
               THEN '["strategies"]'::jsonb ELSE '[]'::jsonb END
       || CASE WHEN permissions->'pages' ?| ARRAY['risk','system-health','audit-log','data']
               THEN '["guard"]'::jsonb ELSE '[]'::jsonb END
       || CASE WHEN permissions->'pages' ?| ARRAY['analytics']
               THEN '["research"]'::jsonb ELSE '[]'::jsonb END
);
```

## A4. WebSocket connection failure recovery — exact behaviour

**Q: "What happens when the WebSocket disconnects?"**

1. TopNavBar WebSocketIndicator turns amber (reconnecting). All `useQuery` with `refetchInterval` continue polling at their normal rates — data doesn't go stale.
2. Reconnect attempts use exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s, 30s, 30s (max 10 attempts in 5 minutes).
3. On reconnect: `queryClient.invalidateQueries({ queryKey: ['positions'] })`, `['orders']`, `['strategies']`, `['autonomous-status']`, `['account-info']`, `['system-health']`. Plus a toast: `Reconnected after Xs — data refreshed`.
4. After 10 failed attempts: indicator turns red, toast `WebSocket unavailable. Polling continues at reduced cadence.`. Polling intervals double. A manual "Reconnect" action in the indicator tooltip retries immediately.
5. On session expiry detected via 1008 close code: force logout, redirect to `/login`, preserving destination in state for post-login redirect.

## A5. Positive P&L color — exact spec

**Q: "What is the exact colour of a positive P&L number?"**

`#22c55e` (`--pnl-up`). On update, tints to `#4ade80` (`--pnl-up-flash`) for 400ms then fades back. Text is always monospace JetBrains Mono Variable with `font-variant-numeric: tabular-nums` and `font-weight: 600` at size `--text-md` and above; `font-weight: 500` below. Preceded by `+` sign when value is non-zero and positive.

Row-level background tint when row represents a positive outcome: `rgba(34, 197, 94, 0.10)` (`--pnl-up-bg`).

## A6. Graduation gate CIO workflow — step by step

1. **Signal:** PAPER strategy "4H EMA Ribbon Trend Long" has generated ≥20 paper trades for AAPL since activation. Backend nightly job inserts AAPL into `graduation_queue` for this strategy with qualification metrics.
2. **User opens `/live` → Graduation tab.** `useQuery(['graduation-queue'])` returns the queue. Each candidate row displays template, symbol, paper trades count, paper Sharpe, qualification ratio (fraction of cycles that would have fired).
3. **User clicks a candidate.** GraduationCard opens as a right-side drawer (60% width). Equity curve of that (template, symbol) pair's paper trades loads via `useQuery(['strategy-equity-paper', strategy_id, symbol])` — lazy.
4. **User reviews:** paper trades KPIs, conviction distribution, regime distribution of the paper trades (so they can see if all wins happened under `trending_up_strong`).
5. **User sets live params:** position_size slider (default 500 virtual), SL% (default 6%), TP% (default 15%), conviction_min (default 74 equities / 68 crypto — equity/crypto detected from symbol), notes.
6. **Confirmation:** on Approve click, ConfirmDialog shows `"Graduate {template} for {symbol}? ${position_size} virtual = ${position_size * mirror_ratio} real per order. {X} max concurrent positions allowed by symbol_cap."` User confirms.
7. **Mutation:** `useMutation` hits `POST /strategies/{strategy_id}/graduate` with body `{symbol, position_size, sl_pct: sl_pct/100, tp_pct: tp_pct/100, conviction_min, notes}`. Optimistically removes from queue, appends to live-strategies list.
8. **Result:** toast `✅ AAPL approved for live trading — first fill when next signal fires`. Backend writes row to `live_strategies` table. Next time this strategy emits an ENTER_LONG signal for AAPL, the trading scheduler routes it to the live eToro client in addition to the demo client.
9. **Rejection path:** Reject button opens reason textarea. Submit → `POST /strategies/{strategy_id}/reject-graduation` with `{symbol, reason}`. Backend records in `rejection_blacklist` with 14-day cooldown; strategy continues paper trading for all other symbols, can be re-proposed for AAPL after cooldown expires.
10. **Post-graduation:** Live authorization monitored on Divergence tab. If live Sharpe drops below 50% of paper Sharpe over rolling 14-day window, Divergence row flags amber/red; CIO can retire via `POST /live/strategies/{live_id}/retire` → strategy stays on PAPER but live fills stop for that pair.

## A7. EquityChart exact props example

```typescript
<EquityChart
  equityData={equityCurveData}
  dailyEquity={dashboardEquityCurve.filter(d => /^\d{4}-\d{2}-\d{2}$/.test(d.date))}
  spyData={showBenchmark ? spyData : undefined}
  period="3M"
  onPeriodChange={setEquityPeriod}
  interval="1d"
  onIntervalChange={(iv) => { setEquityInterval(iv); refetch(iv); }}
  showDrawdown={true}
  showBenchmark={true}
  showRealized={true}
  crosshair={true}
  height={undefined}   // AutoHeight measures parent panel
/>
```

Renders via TradingView LWC `createChart()` with:
- Main pane: `addLineSeries({ color: 'var(--accent-primary)', lineWidth: 2 })` for equity; `addLineSeries({ color: 'var(--text-2)', lineWidth: 1, lineStyle: LineStyle.Dashed })` for realized; `addLineSeries({ color: 'var(--status-warning)', lineWidth: 1 })` for SPY.
- Drawdown pane (40% of main pane height): `addAreaSeries({ lineColor: 'var(--pnl-down)', topColor: 'rgba(239,68,68,0.3)', bottomColor: 'rgba(239,68,68,0.0)' })`.
- Grid: `vertLines.color: 'var(--border-subtle)'`, `horzLines.color: 'var(--border-subtle)'`.
- Crosshair: magnet mode, `vertLine.color: 'var(--text-3)'`, `horzLine.color: 'var(--text-3)'`.
- Layout: `textColor: 'var(--text-2)'`, `background: { type: ColorType.Solid, color: 'var(--bg-1)' }`.

## A8. Deployment — unchanged from current

- Nginx serves `/home/ubuntu/alphacent/frontend/dist` (new frontend lands here after rebuild).
- Instant rollback: swap `frontend/` and `frontend_v1_backup/` on EC2.
- Build command: `VITE_API_BASE_URL=https://alphacent.co.uk VITE_WS_BASE_URL=wss://alphacent.co.uk npm run build`.
- systemd restart not required — nginx serves static.

## A9. Known backend limitations surfaced honestly in UI

From the steering file, these constraints must be visible to the user where relevant:

1. **eToro LIVE SL update not supported** — positions page shows `(DB-only)` badge next to LIVE SL values and a one-line note.
2. **82% entry-order FAILED rate is cosmetic** — Orders page adds a small footnote when filter by status=FAILED: "Market-closed deferrals logged as FAILED then retried — cosmetic issue, not real failures."
3. **Cycle-error observability gap** — if an autonomous cycle stage throws, the cycle pipeline visual shows a red X on the failing stage with `"Stage error — check logs"`, even though `signal_decisions` may not record it.
4. **1h strategies near-zero** — Strategies table includes a small info pill on the timeframe filter when 1h is selected: "1h strategies require 15+ trades to activate; currently ~1 active system-wide."
5. **MQS persistence NULL** — System Health surfaces MQS with `—` when NULL and explains in tooltip: "MQS persistence bug — computed but not saved. Investigation open."

## A10. Document acceptance criteria

A developer should be able to, starting from this document alone:

- Set up the entire project scaffold and design system (Sprint 0) without asking a single question.
- Know the exact hex of every colour, the exact font stack, the exact size scale.
- Know the shape, behaviour, and props of every component before writing it.
- Know which endpoint backs every piece of data on every page.
- Know how each WebSocket event updates which UI element.
- Know how the CIO graduates a (template, symbol) pair to live, step by step.
- Know what happens when the WebSocket disconnects, when a query fails, when a form is invalid.

If any of the above is unclear after reading, the document has failed and needs an amendment.

