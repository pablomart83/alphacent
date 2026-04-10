# Implementation Plan: AlphaCent Trading Platform

## Overview

This implementation plan breaks down the AlphaCent trading platform into incremental, testable tasks. The approach follows a bottom-up strategy: build core infrastructure first (data models, database, API client), then add trading logic (risk management, order execution), then strategy engine, and finally the frontend UI. Each major component includes property-based tests to validate correctness properties from the design document.

The implementation uses Python 3.11+ with FastAPI for the backend, SQLite for persistence, Hypothesis for property-based testing, and React with TypeScript for the frontend.

## Tasks

- [x] 1. Project setup and core infrastructure
  - [x] 1.1 Initialize Python project with dependencies
    - Create project structure (src/, tests/, config/)
    - Set up pyproject.toml with dependencies: FastAPI, SQLAlchemy, Hypothesis, pytest, vectorbt, requests
    - Configure Python 3.11+ environment
    - Set up .gitignore for Python projects
    - _Requirements: 16.1, 16.2_

  - [x] 1.2 Create data models and database schema
    - Implement Strategy, Order, Position, MarketData, TradingSignal, AccountInfo, RiskConfig dataclasses
    - Create SQLAlchemy ORM models for persistence
    - Implement database initialization and migration scripts
    - Add database connection management with SQLite
    - _Requirements: 14.1, 16.9_

  - [ ]* 1.3 Write property test for data persistence round-trip
    - **Property 8: Data persistence round-trip**
    - **Validates: Requirements 4.5, 13.4, 14.1**

  - [x] 1.4 Implement configuration management
    - Create configuration file structure for API credentials, risk parameters, trading modes
    - Implement secure credential storage with encryption (using cryptography library)
    - Add configuration loading and validation
    - Support separate configs for Demo and Live modes
    - _Requirements: 2.1, 2.3, 2.4, 10.7_

  - [ ]* 1.5 Write property test for credential encryption
    - **Property 3: Credential encryption at rest**
    - **Validates: Requirements 2.3, 18.5**


- [x] 2. eToro API client implementation
  - [x] 2.1 Implement eToro API authentication
    - Create EToroAPIClient class with authentication methods
    - Implement API key-based authentication (public key + user key)
    - Add authentication token storage and automatic refresh
    - Handle authentication failures with proper error logging
    - _Requirements: 1.1, 1.2, 1.3, 2.8, 2.9, 2.10_

  - [ ]* 2.2 Write unit tests for authentication flows
    - Test successful authentication with valid credentials
    - Test authentication failure with invalid credentials
    - Test automatic token refresh on expiration
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ]* 2.3 Write property test for authentication token lifecycle
    - **Property 4: Authentication token lifecycle**
    - **Validates: Requirements 2.9, 2.10**

  - [x] 2.4 Implement market data retrieval methods
    - Add get_market_data() for real-time quotes
    - Add get_historical_data() for OHLCV data
    - Implement data validation before returning
    - Add support for stocks, ETFs, and cryptocurrencies
    - _Requirements: 1.4, 3.1, 3.3, 3.4, 3.5_

  - [ ]* 2.5 Write property test for market data validation
    - **Property 5: Market data validation**
    - **Validates: Requirements 3.5**

  - [x] 2.6 Implement account and position methods
    - Add get_account_info() for balance, buying power, margin
    - Add get_positions() for open positions
    - Add get_order_status() for order tracking
    - _Requirements: 1.6_

  - [x] 2.7 Implement order placement methods
    - Add place_order() supporting Market, Limit, Stop Loss, Take Profit
    - Add cancel_order() for pending orders
    - Add close_position() for exiting positions
    - Implement retry logic with exponential backoff for API failures
    - _Requirements: 1.5, 1.7_

  - [ ]* 2.8 Write property test for API retry with exponential backoff
    - **Property 2: API retry with exponential backoff**
    - **Validates: Requirements 1.7**

  - [x] 2.9 Implement social trading and Smart Portfolio methods
    - Add get_social_insights() for sentiment and trending data
    - Add get_smart_portfolios() for Smart Portfolio information
    - _Requirements: 8.1, 8.2, 8.3, 9.1_

- [x] 3. Checkpoint - Verify eToro API client functionality
  - Ensure all tests pass, ask the user if questions arise.


- [x] 4. Market data manager implementation
  - [x] 4.1 Implement MarketDataManager with caching
    - Create MarketDataManager class with eToro API client integration
    - Implement local caching with TTL (time-to-live)
    - Add cache validation and expiration logic
    - Implement fallback to Yahoo Finance when eToro unavailable
    - _Requirements: 3.1, 3.2, 3.6, 3.7_

  - [ ]* 4.2 Write unit tests for market data caching and fallback
    - Test cache hit/miss scenarios
    - Test fallback to Yahoo Finance on eToro failure
    - Test cache expiration and refresh
    - _Requirements: 3.2, 3.6, 3.7_

  - [x] 4.3 Implement market hours management
    - Create MarketHoursManager class with exchange schedules
    - Add is_market_open() method for different asset classes
    - Handle different hours for stocks, ETFs, and cryptocurrencies (24/7)
    - Account for holidays and early closures
    - _Requirements: 12.1, 12.4, 12.7, 15.2_

  - [ ]* 4.4 Write property test for asset class market hours
    - **Property 18: Asset class market hours**
    - **Validates: Requirements 12.4, 15.2**

- [x] 5. Risk management implementation
  - [x] 5.1 Implement RiskManager class with limit enforcement
    - Create RiskManager with RiskConfig initialization
    - Implement validate_signal() to check all risk parameters
    - Implement calculate_position_size() based on account balance and risk percentage
    - Add check_position_limits() and check_exposure_limits()
    - _Requirements: 5.1, 5.2, 5.6, 5.7, 5.8_

  - [ ]* 5.2 Write property test for risk limits enforcement
    - **Property 10: Risk limits enforcement**
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [ ]* 5.3 Write property test for position sizing calculation
    - **Property 12: Position sizing calculation**
    - **Validates: Requirements 5.8**

  - [ ]* 5.4 Write property test for signal risk validation
    - **Property 9: Signal risk validation**
    - **Validates: Requirements 4.8, 5.6, 5.7**

  - [x] 5.2 Implement circuit breaker logic
    - Add check_circuit_breaker() to monitor daily loss limits
    - Implement activate_circuit_breaker() to halt new positions
    - Add circuit breaker state management and reset logic
    - _Requirements: 5.3, 5.4, 5.5_

  - [ ]* 5.6 Write unit test for circuit breaker activation
    - Test circuit breaker activates at daily loss threshold
    - Test new positions rejected when circuit breaker active
    - _Requirements: 5.4, 5.5_

  - [ ]* 5.7 Write property test for circuit breaker prevents new positions
    - **Property 11: Circuit breaker prevents new positions**
    - **Validates: Requirements 5.5**

  - [x] 5.8 Implement kill switch functionality
    - Add execute_kill_switch() to close all positions and halt trading
    - Implement position closing logic with order tracking
    - Add kill switch state management and logging
    - _Requirements: 5.9_

  - [ ]* 5.9 Write unit test for kill switch execution
    - Test kill switch closes all positions
    - Test kill switch cancels pending orders
    - Test kill switch prevents new trading
    - _Requirements: 5.9_

- [x] 6. Checkpoint - Verify risk management functionality
  - Ensure all tests pass, ask the user if questions arise.


- [ ] 7. Order execution implementation
  - [x] 7.1 Implement OrderExecutor class
    - Create OrderExecutor with eToro client and market hours manager
    - Implement execute_signal() to create and submit orders
    - Add track_order() to monitor order status until completion
    - Implement handle_fill() to update position records
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 7.2 Write property test for order lifecycle management
    - **Property 13: Order lifecycle management**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

  - [x] 7.3 Implement stop loss and take profit attachment
    - Add attach_stop_loss() to create stop loss orders
    - Add attach_take_profit() to create take profit orders
    - Automatically attach to new positions based on strategy risk params
    - _Requirements: 6.7_

  - [ ]* 7.4 Write property test for automatic stop loss and take profit
    - **Property 15: Automatic stop loss and take profit attachment**
    - **Validates: Requirements 6.7**

  - [x] 7.5 Implement order failure handling and partial fills
    - Add handle_order_failure() with logging and user notification
    - Implement partial fill tracking with remaining quantity calculation
    - Add retry logic for transient failures
    - _Requirements: 6.5, 6.8_

  - [ ]* 7.6 Write property test for partial fill tracking
    - **Property 16: Partial fill tracking**
    - **Validates: Requirements 6.8**

  - [ ]* 7.7 Write property test for order failure logging
    - **Property 14: Order failure logging**
    - **Validates: Requirements 6.5**

  - [x] 7.8 Implement market hours enforcement for orders
    - Add market hours check before order submission
    - Implement order queueing for closed markets
    - Add automatic execution at market open
    - _Requirements: 6.9, 12.2, 12.3_

  - [ ]* 7.9 Write property test for market hours enforcement
    - **Property 17: Market hours enforcement**
    - **Validates: Requirements 6.9, 12.2, 12.3**

  - [x] 7.10 Implement position closing methods
    - Add close_position() for single position exit
    - Add close_all_positions() for kill switch
    - Track closed positions and realized P&L
    - _Requirements: 5.9_

- [x] 8. LLM service implementation
  - [x] 8.1 Implement LLMService class for Ollama integration
    - Create LLMService with Ollama connection (localhost:11434)
    - Implement generate_strategy() with prompt formatting
    - Add parse_response() to extract structured strategy definitions
    - Handle Ollama unavailable errors gracefully
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 8.2 Write property test for LLM strategy generation context
    - **Property 20: LLM strategy generation context**
    - **Validates: Requirements 7.3**

  - [ ]* 8.3 Write property test for LLM response parsing
    - **Property 21: LLM response parsing**
    - **Validates: Requirements 7.4**

  - [x] 8.4 Implement strategy validation
    - Add validate_strategy() to check completeness and correctness
    - Validate required fields (name, rules, symbols, risk_params)
    - Validate rules are executable and symbols are valid
    - Implement retry logic for invalid LLM responses
    - _Requirements: 7.5, 7.6_

  - [ ]* 8.5 Write property test for generated strategy validation
    - **Property 22: Generated strategy validation**
    - **Validates: Requirements 7.6**

  - [x] 8.6 Implement vibe-coding translation
    - Add translate_vibe_code() for natural language to trading commands
    - Parse natural language into structured TradingCommand objects
    - Support common trading phrases and intents
    - _Requirements: 7.7_

- [x] 9. Checkpoint - Verify order execution and LLM integration
  - Ensure all tests pass, ask the user if questions arise.


- [x] 10. Strategy engine implementation
  - [x] 10.1 Implement StrategyEngine core functionality
    - Create StrategyEngine class with LLM service and market data manager
    - Implement generate_strategy() using LLM service
    - Add activate_strategy() and deactivate_strategy() for lifecycle management
    - Implement strategy state persistence to database
    - _Requirements: 4.1, 4.2, 4.5_

  - [ ]* 10.2 Write property test for strategy validation
    - **Property 6: Strategy validation**
    - **Validates: Requirements 4.2**

  - [x] 10.3 Implement backtesting with vectorbt
    - Add backtest_strategy() using vectorbt library
    - Fetch historical data from MarketDataManager
    - Calculate performance metrics (returns, Sharpe, max drawdown)
    - Store backtest results with strategy
    - _Requirements: 4.3, 4.4_

  - [ ]* 10.4 Write property test for backtest metrics completeness
    - **Property 7: Backtest metrics completeness**
    - **Validates: Requirements 4.4**

  - [x] 10.5 Implement signal generation
    - Add generate_signals() based on strategy rules and market data
    - Create TradingSignal objects with action, confidence, reason
    - Pass signals to Risk Manager for validation
    - _Requirements: 4.7, 4.8_
  
  - [x] 10.5.1 Integrate system state checks in signal generation
    - Check system state before generating signals
    - Skip signal generation when state is PAUSED, STOPPED, or EMERGENCY_HALT
    - Log skipped signal generation with reason
    - Resume signal generation when state returns to ACTIVE
    - _Requirements: 11.12, 11.16, 16.12_

  - [x] 10.6 Implement performance monitoring
    - Add monitor_performance() to calculate real-time metrics
    - Calculate daily/weekly/monthly returns, Sharpe, Sortino, drawdown
    - Calculate win rate, average win, average loss
    - Store performance metrics to database
    - _Requirements: 13.1, 13.2, 13.7_

  - [ ]* 10.7 Write property test for performance metrics calculation
    - **Property 25: Performance metrics calculation**
    - **Validates: Requirements 13.1, 13.2, 13.7**

  - [x] 10.8 Implement strategy retirement logic
    - Add retire_strategy() with configurable triggers
    - Check Sharpe ratio, drawdown, win rate, consecutive losses
    - Close positions opened by retired strategy
    - Archive strategy with final metrics
    - _Requirements: 4.11_

  - [x] 10.9 Implement capital allocation optimization
    - Add optimize_allocations() using Sharpe ratio weighting
    - Calculate optimal allocation percentages across strategies
    - Apply minimum/maximum allocation constraints
    - Normalize allocations to 100%
    - _Requirements: 4.9_

  - [x] 10.10 Implement portfolio rebalancing
    - Add rebalance_portfolio() to match target allocations
    - Calculate current allocations from positions
    - Determine required trades to reach targets
    - Create rebalancing orders and validate through Risk Manager
    - Schedule automatic rebalancing (daily at market open)
    - _Requirements: 4.10_

- [x] 11. Performance attribution and benchmarking
  - [x] 11.1 Implement benchmark comparison
    - Add compare_to_benchmark() for SPY, BTC, etc.
    - Fetch benchmark data from market data manager
    - Calculate relative performance and alpha
    - _Requirements: 13.3_

  - [ ]* 11.2 Write property test for benchmark comparison
    - **Property 26: Benchmark comparison**
    - **Validates: Requirements 13.3**

  - [x] 11.3 Implement P&L attribution
    - Add attribute_pnl() to assign P&L to strategies and positions
    - Track P&L by strategy, position, and time period
    - Calculate contribution to total returns
    - _Requirements: 13.6_

  - [ ]* 11.4 Write property test for P&L attribution
    - **Property 27: P&L attribution**
    - **Validates: Requirements 13.6**

- [x] 12. Checkpoint - Verify strategy engine and performance tracking
  - Ensure all tests pass, ask the user if questions arise.


- [x] 13. Data persistence and recovery
  - [x] 13.1 Implement transaction logging
    - Create transaction log for all orders and fills
    - Log with timestamp, order details, fill details
    - Implement log rotation and archival
    - _Requirements: 14.5_

  - [ ]* 13.2 Write property test for transaction logging
    - **Property 28: Transaction logging**
    - **Validates: Requirements 14.5**

  - [x] 13.3 Implement automatic backup system
    - Add create_backup() to backup critical data (strategies, config, state)
    - Schedule automatic backups at regular intervals
    - Implement backup rotation (keep last N backups)
    - _Requirements: 14.2_

  - [x] 13.4 Implement state restoration
    - Add restore_from_backup() to load state on startup
    - Handle backup corruption with fallback to older backups
    - Start with default state if all backups fail
    - _Requirements: 14.3, 14.4_

  - [x] 13.5 Implement data export functionality
    - Add export_data() for manual data export
    - Support CSV and JSON formats
    - Export strategies, orders, positions, performance metrics
    - _Requirements: 14.6_

- [x] 14. Security implementation
  - [x] 14.1 Implement user authentication
    - Create authentication system with username/password
    - Hash passwords using bcrypt
    - Implement session-based authentication with secure cookies
    - _Requirements: 18.1, 18.2, 18.3_

  - [ ]* 14.2 Write property test for password hashing
    - **Property 31: Password hashing**
    - **Validates: Requirements 18.2**

  - [x] 14.3 Implement session management
    - Add session timeout after inactivity
    - Implement session validation on each request
    - Clear expired sessions automatically
    - _Requirements: 18.4_

  - [ ]* 14.4 Write property test for session timeout enforcement
    - **Property 33: Session timeout enforcement**
    - **Validates: Requirements 18.4**

  - [x] 14.5 Implement input validation and sanitization
    - Add validation for all user inputs
    - Sanitize inputs to prevent injection attacks
    - Return sanitized error messages
    - _Requirements: 18.6_

  - [ ]* 14.6 Write property test for input validation
    - **Property 32: Input validation and sanitization**
    - **Validates: Requirements 18.6**

  - [x] 14.7 Implement rate limiting and security logging
    - Add rate limiting on authentication endpoints
    - Log all authentication attempts with outcome
    - Log security events (failed logins, suspicious activity)
    - _Requirements: 18.7, 18.8_

  - [ ]* 14.8 Write property test for authentication rate limiting
    - **Property 34: Authentication rate limiting**
    - **Validates: Requirements 18.7**

  - [ ]* 14.9 Write property test for security event logging
    - **Property 35: Security event logging**
    - **Validates: Requirements 18.8**

- [ ] 15. Checkpoint - Verify data persistence and security
  - Ensure all tests pass, ask the user if questions arise.


- [x] 16. Error handling and logging
  - [x] 16.1 Implement comprehensive error logging
    - Create logging system with timestamp, severity, component, context
    - Categorize errors by component and severity level
    - Implement rolling log files with automatic rotation
    - _Requirements: 19.1, 19.2, 19.4_

  - [ ]* 16.2 Write property test for error logging format
    - **Property 36: Error logging format**
    - **Validates: Requirements 19.1, 19.2**

  - [x] 16.3 Implement critical error notification
    - Add notification system for critical errors
    - Send notifications to Dashboard via WebSocket
    - Include error details and suggested actions
    - _Requirements: 19.3_

  - [ ]* 16.4 Write property test for critical error notification
    - **Property 37: Critical error notification**
    - **Validates: Requirements 19.3**

  - [x] 16.5 Implement API rate limit monitoring
    - Add rate limit tracking for eToro API
    - Activate throttling when approaching limits
    - Log warnings when throttling active
    - _Requirements: 19.6_

  - [ ]* 16.6 Write property test for API rate limit throttling
    - **Property 38: API rate limit throttling**
    - **Validates: Requirements 19.6**

  - [x] 16.7 Implement graceful degradation
    - Add fallback behavior for non-critical component failures
    - Continue core operations when optional features fail
    - Log degraded mode activation
    - _Requirements: 19.7_

  - [ ]* 16.8 Write property test for graceful degradation
    - **Property 39: Graceful degradation**
    - **Validates: Requirements 19.7**

- [x] 17. Backend API implementation (FastAPI)
  - [x] 17.1 Create FastAPI application structure
    - Initialize FastAPI app with CORS middleware
    - Set up routing for REST endpoints
    - Configure WebSocket support for real-time updates
    - Add authentication middleware
    - _Requirements: 16.1, 16.6_

  - [x] 17.2 Implement authentication endpoints
    - POST /auth/login for user login
    - POST /auth/logout for user logout
    - GET /auth/status for session validation
    - _Requirements: 18.1, 18.3_

  - [x] 17.3 Implement configuration endpoints
    - GET /config for retrieving configuration
    - PUT /config for updating configuration
    - POST /config/credentials for setting API credentials
    - GET /config/connection-status for eToro connection status
    - _Requirements: 2.1, 2.6_

  - [x] 17.4 Implement account and portfolio endpoints
    - GET /account for account info (balance, buying power, margin)
    - GET /positions for all open positions
    - GET /positions/:id for specific position details
    - _Requirements: 11.1, 11.2_

  - [x] 17.5 Implement strategy endpoints
    - GET /strategies for all strategies
    - POST /strategies for creating new strategy
    - PUT /strategies/:id for updating strategy
    - DELETE /strategies/:id for retiring strategy
    - POST /strategies/:id/activate for activating strategy
    - POST /strategies/:id/deactivate for deactivating strategy
    - GET /strategies/:id/performance for performance metrics
    - _Requirements: 11.3_

  - [x] 17.6 Implement order endpoints
    - GET /orders for all orders
    - GET /orders/:id for specific order details
    - POST /orders for manual order placement
    - DELETE /orders/:id for canceling order
    - _Requirements: 11.4_

  - [x] 17.7 Implement market data endpoints
    - GET /market-data/:symbol for real-time quote
    - GET /market-data/:symbol/historical for historical data
    - GET /social-insights/:symbol for social trading data
    - GET /smart-portfolios for Smart Portfolio list
    - _Requirements: 11.7, 11.8_

  - [x] 17.8 Implement control endpoints
    - POST /kill-switch for emergency shutdown
    - POST /circuit-breaker/reset for resetting circuit breaker
    - POST /rebalance for manual portfolio rebalancing
    - _Requirements: 11.5_
  
  - [x] 17.8.1 Implement system state management endpoints
    - GET /system/status for current autonomous trading state
    - POST /system/start for starting autonomous trading
    - POST /system/pause for pausing autonomous trading
    - POST /system/stop for stopping autonomous trading
    - POST /system/resume for resuming from paused state
    - POST /system/reset for resetting from emergency halt
    - Implement state validation and transition logic
    - Add confirmation requirement for state changes
    - Log all state transitions with audit trail
    - _Requirements: 11.11, 11.12, 16.12_
  
  - [x] 17.8.2 Implement system state persistence
    - Create SystemState data model and ORM mapping
    - Save state to database on every change
    - Restore state on backend service startup
    - Implement state validation on restoration
    - Handle invalid states gracefully
    - Create state transition history table
    - _Requirements: 11.12, 14.1, 16.12_
  
  - [x] 17.8.3 Implement service dependency management
    - Create ServiceManager class for managing dependent services
    - Implement Ollama service health checking (localhost:11434)
    - Add automatic service startup on autonomous trading start
    - Implement periodic health checks (every 60 seconds)
    - Handle service failures gracefully (disable features, maintain positions)
    - Add service recovery logic (automatic reconnection attempts)
    - Implement optional service shutdown on trading stop
    - Create service status API endpoints
    - _Requirements: 7.8, 7.9, 16.1.1-16.1.10_
  
  - [x] 17.8.4 Integrate service checks with state transitions
    - Check Ollama availability before transitioning to ACTIVE
    - Transition to PAUSED if services unavailable
    - Alert user with service status and instructions
    - Disable strategy generation when Ollama unavailable
    - Re-enable when service recovers
    - _Requirements: 16.1.2, 16.1.3, 16.1.4, 16.1.5_

  - [x] 17.9 Implement WebSocket handler for real-time updates
    - Create WebSocket endpoint at /ws
    - Push market data updates to connected clients
    - Push position updates on fills
    - Push strategy performance updates
    - Push error notifications
    - Push system state changes to connected clients
    - _Requirements: 11.9, 11.12, 16.11_
    - _Requirements: 11.9, 16.11_

- [ ] 18. Checkpoint - Verify backend API functionality
  - Ensure all tests pass, ask the user if questions arise.


- [-] 19. Frontend UI implementation (React + TypeScript)
  - [x] 19.1 Initialize React project with TypeScript
    - Create React app with TypeScript template
    - Set up project structure (components/, pages/, hooks/, services/)
    - Configure Tailwind CSS for styling
    - Set up React Router for navigation
    - _Requirements: 16.4, 16.5_

  - [x] 19.2 Implement authentication UI
    - Create Login page with username/password form
    - Implement authentication service to call backend API
    - Add session management and protected routes
    - Display authentication errors
    - _Requirements: 18.1_

  - [x] 19.3 Implement API service layer
    - Create API client for backend communication
    - Implement REST API calls for all endpoints
    - Add WebSocket connection management
    - Handle authentication tokens in requests
    - _Requirements: 16.6_

  - [x] 19.4 Implement Dashboard layout
    - Create main Dashboard component with grid layout
    - Add navigation sidebar
    - Implement dark theme with high contrast
    - Add responsive layout for desktop
    - _Requirements: 17.1, 17.2, 17.7_

  - [x] 19.5 Implement Account Overview component
    - Display account balance, buying power, margin usage
    - Show daily P&L and total P&L
    - Display trading mode indicator (Demo/Live)
    - Update in real-time via WebSocket
    - _Requirements: 11.1, 10.4_

  - [x] 19.6 Implement Positions component
    - Display all open positions in table format
    - Show symbol, quantity, entry price, current price, unrealized P&L
    - Add position actions (close position, modify stop/target)
    - Update in real-time via WebSocket
    - _Requirements: 11.2_

  - [x] 19.7 Implement Strategies component
    - Display all strategies with status (PROPOSED, BACKTESTED, DEMO, LIVE, RETIRED)
    - Show strategy performance metrics (returns, Sharpe, drawdown)
    - Add strategy actions (activate, deactivate, retire)
    - Display strategy allocation percentages
    - _Requirements: 11.3_

  - [x] 19.8 Implement Orders component
    - Display recent orders with status
    - Show order details (symbol, side, type, quantity, price)
    - Add order actions (cancel pending orders)
    - Update in real-time via WebSocket
    - _Requirements: 11.4_

  - [x] 19.9 Implement Market Data component
    - Display watchlist with real-time quotes
    - Show price, change, volume for each symbol
    - Add/remove symbols from watchlist
    - Update in real-time via WebSocket
    - _Requirements: 11.7_

  - [x] 19.10 Implement Social Insights component
    - Display social sentiment scores for instruments
    - Show trending symbols and popularity metrics
    - Display Pro Investor positions and performance
    - _Requirements: 11.8_

  - [x] 19.11 Implement Smart Portfolios component
    - Display available Smart Portfolios
    - Show portfolio composition, performance, risk ratings
    - Add invest/divest actions
    - _Requirements: 11.8_

  - [x] 19.12 Implement Control Panel component
    - Add Kill Switch button with confirmation dialog
    - Add Circuit Breaker reset button
    - Add manual rebalance trigger
    - Display system status and warnings
    - _Requirements: 11.5, 11.6_
  
  - [x] 19.12.1 Implement Autonomous Trading Master Control
    - Add "Start Autonomous Trading" / "Stop Autonomous Trading" toggle button
    - Add "Pause Trading" / "Resume Trading" controls
    - Display system status indicator (ACTIVE/PAUSED/STOPPED/EMERGENCY_HALT)
    - Implement color-coded status badge (Green/Yellow/Red/Dark Red)
    - Add confirmation dialogs for all state changes
    - Show last state change timestamp and reason
    - Display number of active strategies
    - Persist autonomous trading state across sessions
    - Disable controls appropriately during EMERGENCY_HALT
    - _Requirements: 11.11, 11.12, 11.16, 16.12_
  
  - [x] 19.12.2 Implement Home Page System Status Display
    - Display current autonomous trading status on login
    - Show last active strategies and their current status
    - Display performance metrics from current session
    - Show performance summary from previous sessions
    - Display active positions count and total P&L
    - Show recent trades and orders
    - Display system alerts and warnings
    - Show system uptime and last activity timestamps
    - _Requirements: 11.13, 11.14, 11.15_
  
  - [x] 19.12.3 Implement Dependent Services Status Display
    - Display status of all dependent services (Ollama LLM)
    - Show service health indicator (Running/Stopped/Error)
    - Display service endpoint and last health check time
    - Add manual start/stop/restart controls for each service
    - Show error messages when services are unavailable
    - Display impact on features when services are down
    - Update service status in real-time via WebSocket
    - _Requirements: 16.1.8, 16.1.9_

  - [x] 19.13 Implement Vibe Coding interface
    - Create natural language input component
    - Send vibe-coding commands to backend
    - Display translated trading commands
    - Show execution results
    - _Requirements: 11.10_

  - [x] 19.14 Implement Settings page
    - Create configuration form for API credentials
    - Add risk parameter configuration
    - Add trading mode switcher (Demo/Live)
    - Display connection status
    - _Requirements: 2.1, 2.6_

  - [x] 19.15 Implement Performance Charts
    - Add portfolio performance chart (equity curve)
    - Add strategy performance comparison chart
    - Add P&L attribution chart
    - Use Chart.js or Recharts library
    - _Requirements: 13.5_

  - [x] 19.16 Implement notification system
    - Create notification component for alerts
    - Display critical errors prominently
    - Show order fills, strategy activations, circuit breaker events
    - Add notification history
    - _Requirements: 19.3_

- [-] 20. Integration and end-to-end testing
  - [x] 20.1 Implement end-to-end trading flow test
    - Test complete flow: authenticate → generate strategy → backtest → activate → generate signal → validate → execute order → track fill
    - Verify all components work together correctly
    - Test in both Demo and Live modes
    - _Requirements: All_

  - [ ]* 20.2 Write integration tests for strategy lifecycle
    - Test strategy creation, backtesting, activation, signal generation, retirement
    - Verify state transitions and data persistence
    - _Requirements: 4.1-4.11_

  - [ ]* 20.3 Write integration tests for risk management flow
    - Test signal validation, position sizing, limit enforcement, circuit breaker
    - Verify risk limits prevent violations
    - _Requirements: 5.1-5.9_

  - [ ]* 20.4 Write integration tests for order execution flow
    - Test order creation, submission, tracking, fill handling
    - Verify position updates and P&L calculation
    - _Requirements: 6.1-6.9_

- [ ] 21. UX Polish and Production Readiness
  - [x] 21.1 Reorganize Dashboard navigation and component structure
    - Create separate navigation sections: Home, Trading, Portfolio, Market, System
    - Move SystemStatusHome to Home section (default landing page)
    - Group AccountOverview, Positions, Orders under Portfolio section
    - Group Strategies, VibeCoding under Trading section
    - Group MarketData, SocialInsights, SmartPortfolios under Market section
    - Group ControlPanel, ServicesStatus, PerformanceCharts under System section
    - Update DashboardLayout with new navigation structure
    - Implement section-based routing (e.g., /portfolio, /trading, /market, /system)
    - Add active section highlighting in navigation
    - _Requirements: 17.1, 17.2_

  - [x] 21.2 Remove all mock data from frontend components
    - Audit all components for hardcoded mock data
    - Replace mock data in AccountOverview with real API calls
    - Replace mock data in Positions with real API calls
    - Replace mock data in Orders with real API calls
    - Replace mock data in Strategies with real API calls
    - Replace mock data in MarketData with real API calls
    - Replace mock data in SocialInsights with real API calls
    - Replace mock data in SmartPortfolios with real API calls
    - Replace mock data in PerformanceCharts with real API calls
    - Add loading states for all data fetching
    - Add empty states with helpful messages when no data exists
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.7, 11.8, 13.5_

  - [x] 21.3 Remove all mock data from backend services
    - Audit all backend endpoints for mock/placeholder data
    - Ensure /account endpoint returns real eToro account data
    - Ensure /positions endpoint returns real eToro positions
    - Ensure /orders endpoint returns real order history from database
    - Ensure /strategies endpoint returns real strategies from database
    - Ensure /market-data endpoints return real eToro market data
    - Ensure /social-insights endpoint returns real eToro social data
    - Ensure /smart-portfolios endpoint returns real eToro Smart Portfolio data
    - Add proper error handling when eToro API is unavailable
    - Return empty arrays/objects instead of mock data when no real data exists
    - _Requirements: 1.4, 1.6, 3.1, 8.1, 9.1_

  - [x] 21.4 Connect all buttons and actions to real backend services
    - Verify "Start/Stop Autonomous Trading" calls real backend endpoints
    - Verify "Pause/Resume Trading" calls real backend endpoints
    - Verify "Kill Switch" calls real backend endpoint with confirmation
    - Verify "Circuit Breaker Reset" calls real backend endpoint
    - Verify "Manual Rebalance" calls real backend endpoint
    - Verify strategy activation/deactivation calls real backend endpoints
    - Verify position close actions call real backend endpoints
    - Verify order cancellation calls real backend endpoints
    - Verify watchlist add/remove calls real backend endpoints
    - Verify all Settings form submissions call real backend endpoints
    - Add loading indicators for all button actions
    - Add success/error feedback for all actions
    - Disable buttons during action execution to prevent double-clicks
    - _Requirements: 11.3, 11.4, 11.5, 11.12_

  - [x] 21.5 Implement professional loading and error states
    - Create reusable LoadingSpinner component with consistent styling
    - Create reusable ErrorMessage component with retry functionality
    - Add skeleton loaders for data tables (positions, orders, strategies)
    - Add shimmer effects for loading cards (account overview, market data)
    - Implement error boundaries for component-level error handling
    - Add graceful degradation messages when services are unavailable
    - Show specific error messages (not generic "Error occurred")
    - Add retry buttons for failed API calls
    - Implement exponential backoff for automatic retries
    - _Requirements: 19.3, 19.7_

  - [x] 21.6 Improve visual design and consistency
    - Standardize spacing and padding across all components
    - Ensure consistent color scheme (use CSS variables throughout)
    - Standardize button styles (primary, secondary, danger, disabled states)
    - Standardize card/panel styles with consistent borders and shadows
    - Improve typography hierarchy (headings, body text, labels)
    - Add hover states for all interactive elements
    - Add focus states for keyboard navigation accessibility
    - Ensure consistent icon usage (size, color, alignment)
    - Add smooth transitions for state changes (loading, errors, data updates)
    - Improve table designs with better row spacing and hover effects
    - _Requirements: 17.2, 17.7_

  - [x] 21.7 Enhance real-time data updates and WebSocket integration
    - Verify WebSocket connection is established on Dashboard mount
    - Implement automatic reconnection on WebSocket disconnect
    - Add connection status indicator in UI (connected/disconnected)
    - Ensure all components subscribe to relevant WebSocket events
    - Update AccountOverview in real-time on balance changes
    - Update Positions in real-time on position changes
    - Update Orders in real-time on order status changes
    - Update MarketData in real-time on price updates
    - Update SystemStatusHome in real-time on system state changes
    - Add visual indicators for real-time updates (flash/pulse effect)
    - Throttle high-frequency updates to prevent UI jank
    - _Requirements: 11.9, 16.11_

  - [ ] 21.8 Improve form validation and user feedback
    - Add client-side validation for all Settings forms
    - Show validation errors inline (not just on submit)
    - Add field-level validation messages (e.g., "Invalid API key format")
    - Implement password strength indicator for authentication
    - Add confirmation dialogs for destructive actions (delete, retire, kill switch)
    - Show success toasts for successful operations
    - Show error toasts for failed operations with actionable messages
    - Add form dirty state tracking (warn before leaving unsaved changes)
    - Disable submit buttons when form is invalid
    - Add helpful placeholder text and tooltips for complex fields
    - _Requirements: 18.6, 19.3_

  - [ ] 21.9 Add empty states and onboarding guidance
    - Create EmptyState component with icon, message, and action button
    - Add empty state for Positions when no positions exist
    - Add empty state for Orders when no orders exist
    - Add empty state for Strategies with "Create Strategy" CTA
    - Add empty state for MarketData watchlist with "Add Symbol" CTA
    - Add first-time user onboarding flow (welcome message, quick tour)
    - Add contextual help tooltips for complex features
    - Add "Getting Started" guide in Settings or Help section
    - Show helpful messages when eToro credentials not configured
    - Add status indicators showing what needs to be configured
    - _Requirements: 17.1, 17.2_

  - [ ] 21.10 Optimize performance and responsiveness
    - Implement React.memo for expensive components
    - Add useMemo/useCallback for expensive computations
    - Implement virtual scrolling for long lists (positions, orders)
    - Lazy load charts and heavy components
    - Optimize WebSocket message handling (debounce/throttle)
    - Reduce unnecessary re-renders with proper dependency arrays
    - Implement code splitting for routes
    - Optimize bundle size (analyze and remove unused dependencies)
    - Add loading priorities (critical data first, then secondary)
    - Test and optimize for 60fps animations and transitions
    - _Requirements: 16.4, 16.5_

  - [ ] 21.11 Implement comprehensive keyboard navigation
    - Ensure all interactive elements are keyboard accessible
    - Add keyboard shortcuts for common actions (e.g., Ctrl+K for command palette)
    - Implement proper tab order throughout the application
    - Add visible focus indicators for keyboard navigation
    - Support Escape key to close modals and dialogs
    - Support Enter key to submit forms and confirm actions
    - Add keyboard shortcut legend (accessible via ? key)
    - Test with screen readers for accessibility compliance
    - _Requirements: 17.7_

  - [ ] 21.12 Add data export and reporting features
    - Add "Export to CSV" button for Positions table
    - Add "Export to CSV" button for Orders table
    - Add "Export to CSV" button for Strategies performance
    - Add date range selector for historical data export
    - Implement PDF report generation for performance summary
    - Add email report scheduling (daily/weekly/monthly)
    - Include charts and visualizations in exported reports
    - Add export progress indicator for large datasets
    - _Requirements: 14.6_

  - [ ] 21.13 Implement advanced filtering and search
    - Add search/filter for Positions table (by symbol, status)
    - Add search/filter for Orders table (by symbol, status, date)
    - Add search/filter for Strategies (by name, status, performance)
    - Add date range filters for historical data
    - Add multi-select filters (e.g., filter by multiple symbols)
    - Persist filter preferences in localStorage
    - Add "Clear all filters" button
    - Show active filter count in UI
    - _Requirements: 11.2, 11.3, 11.4_

  - [ ] 21.14 Add mobile responsiveness (optional for MVP)
    - Test all components on tablet and mobile viewports
    - Implement responsive grid layouts (stack on mobile)
    - Add mobile-friendly navigation (hamburger menu)
    - Optimize touch targets for mobile (minimum 44x44px)
    - Test forms on mobile keyboards
    - Optimize charts for mobile viewing
    - Add swipe gestures for mobile interactions
    - _Requirements: 17.7_

  - [x] 21.15 Complete backend service integrations
    - Integrate OrderExecutor with order placement endpoint (POST /orders)
    - Integrate OrderExecutor with order cancellation endpoint (DELETE /orders/:id)
    - Integrate RiskManager with kill switch endpoint (POST /kill-switch)
    - Integrate RiskManager with circuit breaker reset endpoint (POST /circuit-breaker/reset)
    - Integrate RiskManager with signal validation in trading scheduler
    - Integrate StrategyEngine with strategy activation endpoint (POST /strategies/:id/activate)
    - Integrate StrategyEngine with strategy deactivation endpoint (POST /strategies/:id/deactivate)
    - Integrate StrategyEngine with strategy update endpoint (PUT /strategies/:id)
    - Integrate StrategyEngine with strategy retirement endpoint (DELETE /strategies/:id)
    - Integrate StrategyEngine with portfolio rebalancing endpoint (POST /rebalance)
    - Integrate ServiceManager with system state transitions (start/pause/stop/resume)
    - Integrate ServiceManager with service control endpoints (POST /services/:name/start, POST /services/:name/stop)
    - Implement system state persistence on startup and shutdown
    - Implement session history tracking in database
    - Test eToro API connection in connection status endpoint (GET /config/connection-status)
    - Connect trading scheduler signal validation to RiskManager
    - Connect trading scheduler signal execution to OrderExecutor
    - _Requirements: 4.1-4.11, 5.1-5.9, 6.1-6.9, 11.3, 11.4, 11.5, 16.1.1-16.1.10_

  - [x] 21.16 Complete frontend action integrations
    - Implement close position action in Positions component (call POST /positions/:id/close)
    - Implement modify stop loss action in Positions component (call PUT /positions/:id/stop-loss)
    - Implement modify take profit action in Positions component (call PUT /positions/:id/take-profit)
    - Implement invest action in SmartPortfolios component (call POST /smart-portfolios/:id/invest)
    - Implement divest action in SmartPortfolios component (call POST /smart-portfolios/:id/divest)
    - Create TradingModeContext to share trading mode across all pages
    - Implement trading mode provider in App.tsx
    - Connect all pages (Home, Trading, Portfolio, Market, System) to TradingModeContext
    - Remove hardcoded TradingMode.DEMO from all page components
    - Fetch trading mode from backend config on app initialization
    - Update trading mode in context when changed in Settings
    - Add loading states for all action buttons
    - Add success/error feedback for all actions
    - _Requirements: 11.2, 11.8, 2.1, 2.6_

  - [x] 21.17 Configure eToro API with proper structure and endpoints
    - Update authentication to use header-based auth (x-api-key, x-user-key, x-request-id)
    - Remove token-based authentication logic (AuthToken class, authenticate() method, token refresh)
    - Update base URLs to official eToro endpoints (https://public-api.etoro.com for authenticated, https://www.etoro.com for public)
    - Implement public market data endpoints (no authentication required)
    - Update get_market_data() to use /sapi/trade-real/rates/{instrumentId}
    - Update get_historical_data() to use /sapi/candles/candles/desc.json/{period}/{count}/{instrumentId}
    - Create instrument ID mapping system (symbol → eToro instrumentId)
    - Implement get_instrument_metadata() using /sapi/instrumentsmetadata/V1.1/instruments/{instrumentId}
    - Build initial instrument ID mapping for common symbols (AAPL, MSFT, BTC, ETH, etc.)
    - Implement instrument search functionality to discover new instrument IDs
    - Update authenticated endpoints for trading operations
    - Update place_order() to use /api/v1/trading/execution/market-open-orders/by-amount
    - Update get_positions() endpoint (verify availability in authenticated API)
    - Update get_account_info() endpoint (verify availability in authenticated API)
    - Implement proper error handling for missing instrument IDs
    - Add fallback to local database when eToro API unavailable
    - Test all endpoints with real eToro credentials
    - Document any endpoints not available in public API
    - Implement local position tracking for endpoints not available via API
    - Add comprehensive logging for API requests and responses
    - Implement rate limiting (conservative 1 request/second to avoid 429 errors)
    - Update API client tests to match new structure
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 3.1, 3.3, 3.4, 3.5_

- [ ] 22. Final checkpoint and deployment preparation
  - [ ] 22.1 Run full test suite
    - Execute all unit tests (target >80% coverage)
    - Execute all property tests (100 iterations minimum)
    - Execute all integration tests
    - Fix any failing tests

  - [ ] 22.2 Create deployment documentation
    - Document installation steps (Python dependencies, Ollama setup)
    - Document configuration (API credentials, risk parameters)
    - Document startup procedures (backend service, frontend dev server)
    - Create troubleshooting guide

  - [ ] 22.3 Create user documentation
    - Document platform features and workflows
    - Create strategy creation guide
    - Document risk management settings
    - Create FAQ for common issues

  - [ ] 22.4 Final verification
    - Ensure all tests pass, ask the user if questions arise.
    - Verify all requirements are implemented
    - Confirm platform is ready for use

## Notes

- Tasks marked with `*` are optional property-based and integration tests that can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation throughout development
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Integration tests validate end-to-end workflows
- The implementation follows a bottom-up approach: infrastructure → trading logic → strategy engine → frontend
- Backend continues running strategies even when browser is closed (requirement 16.12)
