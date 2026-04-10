# Requirements Document: AlphaCent Trading Platform

## Introduction

AlphaCent is a personal web-based autonomous trading platform that connects exclusively to eToro via their Public APIs. The platform is a modern, minimalistic web application with a quant trader aesthetic, featuring comprehensive dashboards and real-time monitoring. It runs entirely locally on the user's machine with zero cloud dependencies - the backend service runs on localhost and the React frontend is accessed via browser at localhost. The backend uses a local LLM (Ollama) for AI-powered strategy generation and supports stocks, ETFs, and cryptocurrencies through eToro's trading infrastructure. The platform includes eToro-specific features such as social trading insights, Smart Portfolios, and vibe-coding capabilities.

## Glossary

- **AlphaCent**: The autonomous trading platform system
- **Backend_Service**: Local backend service (Node.js/Python) running on localhost
- **Frontend_UI**: React-based web interface accessed via browser at localhost
- **eToro_API**: eToro's Public API service for trading and market data
- **Strategy_Engine**: Component that generates, backtests, and manages trading strategies
- **Risk_Manager**: Component that enforces trading limits and circuit breakers
- **Order_Executor**: Component that manages order lifecycle via eToro API
- **LLM_Service**: Local Ollama instance for AI-powered strategy generation
- **Dashboard**: React-based web UI for monitoring and control
- **Demo_Mode**: Trading mode using eToro demo account (paper trading)
- **Live_Mode**: Trading mode using eToro live account (real money)
- **Kill_Switch**: Emergency mechanism to halt all trading activity
- **Circuit_Breaker**: Automatic trading halt triggered by loss thresholds
- **Smart_Portfolio**: eToro's managed investment portfolio product
- **Vibe_Coding**: eToro's AI-powered natural language trading workflow tool
- **Social_Insights**: eToro's social trading sentiment and trending data
- **Market_Hours**: Trading hours for different asset classes and exchanges
- **Backtest**: Historical simulation of a trading strategy
- **Position**: An open trade in a financial instrument
- **Order**: A request to buy or sell a financial instrument
- **Strategy**: A set of rules for making trading decisions

## Requirements

### Requirement 1: eToro API Integration

**User Story:** As a trader, I want the platform to connect exclusively to eToro, so that I can trade stocks, ETFs, and cryptocurrencies through a single broker.

#### Acceptance Criteria

1. WHEN the platform initializes, THE eToro_API SHALL authenticate using eToro API public key and user key
2. WHEN authentication succeeds, THE eToro_API SHALL establish a connection to eToro's trading services
3. IF authentication fails, THEN THE AlphaCent SHALL log the error and prevent trading operations
4. THE eToro_API SHALL support market data retrieval for stocks, ETFs, and cryptocurrencies
5. THE eToro_API SHALL support order placement for Market, Limit, Stop Loss, and Take Profit orders
6. THE eToro_API SHALL support account data retrieval including balance, buying power, margin, and positions
7. WHEN the eToro API is unavailable, THE AlphaCent SHALL queue operations and retry with exponential backoff

### Requirement 2: API Credential Management

**User Story:** As a trader, I want to securely configure my eToro API credentials, so that the platform can access my eToro account.

#### Acceptance Criteria

1. THE AlphaCent SHALL provide a configuration interface for entering eToro API public key and user key
2. WHEN API credentials are entered, THE AlphaCent SHALL validate them by attempting authentication with eToro_API
3. THE AlphaCent SHALL encrypt API credentials before storing them locally
4. THE AlphaCent SHALL support separate API credentials for Demo_Mode and Live_Mode
5. WHEN API credentials are invalid or expired, THE AlphaCent SHALL prompt the user to update them
6. THE Dashboard SHALL display API connection status and credential validity
7. THE AlphaCent SHALL provide instructions for obtaining API keys from eToro's developer portal
8. WHEN authenticating with eToro_API, THE AlphaCent SHALL include the API public key and user key in request headers
9. WHEN eToro_API returns an authentication token, THE AlphaCent SHALL store it securely for subsequent API calls
10. WHEN the authentication token expires, THE AlphaCent SHALL automatically re-authenticate using stored credentials

### Requirement 3: Market Data Management

**User Story:** As a trader, I want access to real-time and historical market data, so that I can make informed trading decisions.

#### Acceptance Criteria

1. WHEN market data is requested, THE AlphaCent SHALL retrieve it from eToro_API as the primary source
2. IF eToro_API market data is unavailable, THEN THE AlphaCent SHALL fall back to Yahoo Finance
3. THE AlphaCent SHALL provide real-time price updates for all supported instruments
4. THE AlphaCent SHALL provide historical OHLCV data for backtesting and analysis
5. WHEN market data is received, THE AlphaCent SHALL validate data integrity before storage
6. THE AlphaCent SHALL cache market data locally to minimize API calls
7. WHEN cached data expires, THE AlphaCent SHALL refresh it from the primary source

### Requirement 4: Strategy Engine

**User Story:** As a trader, I want to generate, backtest, and manage trading strategies, so that I can automate my trading decisions and maximize returns.

#### Acceptance Criteria

1. WHEN a user requests strategy generation, THE Strategy_Engine SHALL use LLM_Service to propose trading strategies
2. WHEN a strategy is proposed, THE Strategy_Engine SHALL validate it against risk parameters
3. THE Strategy_Engine SHALL backtest strategies using historical market data
4. WHEN backtesting completes, THE Strategy_Engine SHALL calculate performance metrics including returns, Sharpe ratio, and maximum drawdown
5. THE Strategy_Engine SHALL store active strategies with their parameters and state
6. WHEN market conditions change significantly, THE Strategy_Engine SHALL adapt strategy parameters automatically
7. THE Strategy_Engine SHALL generate trading signals based on active strategy rules
8. WHEN a strategy generates a signal, THE Strategy_Engine SHALL pass it to Risk_Manager for validation
9. THE Strategy_Engine SHALL calculate optimal capital allocation across active strategies based on risk-adjusted returns
10. WHEN allocations drift beyond threshold, THE Strategy_Engine SHALL automatically rebalance the portfolio
11. THE Strategy_Engine SHALL retire underperforming strategies based on performance metrics

### Requirement 5: Risk Management

**User Story:** As a trader, I want strict risk controls, so that I can protect my capital from excessive losses.

#### Acceptance Criteria

1. THE Risk_Manager SHALL enforce maximum position size limits per instrument
2. THE Risk_Manager SHALL enforce maximum portfolio exposure limits
3. THE Risk_Manager SHALL enforce maximum daily loss limits
4. WHEN daily loss limit is reached, THE Risk_Manager SHALL activate Circuit_Breaker
5. WHEN Circuit_Breaker is active, THE Risk_Manager SHALL prevent new position entries
6. THE Risk_Manager SHALL validate all trading signals against risk parameters before execution
7. IF a trading signal violates risk parameters, THEN THE Risk_Manager SHALL reject it and log the reason
8. THE Risk_Manager SHALL calculate position sizing based on account balance and risk percentage
9. WHEN Kill_Switch is activated, THE Risk_Manager SHALL immediately halt all trading and close open positions

### Requirement 6: Order Execution

**User Story:** As a trader, I want reliable order execution, so that my trading strategies are implemented correctly.

#### Acceptance Criteria

1. WHEN a validated trading signal is received, THE Order_Executor SHALL create an order request
2. THE Order_Executor SHALL submit orders to eToro_API with appropriate order types
3. WHEN an order is submitted, THE Order_Executor SHALL track its status until completion
4. WHEN an order is filled, THE Order_Executor SHALL update position records
5. IF an order fails, THEN THE Order_Executor SHALL log the error and notify the user
6. THE Order_Executor SHALL support Market, Limit, Stop Loss, and Take Profit order types
7. THE Order_Executor SHALL attach Stop Loss and Take Profit orders to positions automatically
8. WHEN an order is partially filled, THE Order_Executor SHALL track the remaining quantity
9. THE Order_Executor SHALL respect market hours for different asset classes

### Requirement 7: LLM Integration

**User Story:** As a trader, I want AI-powered strategy generation, so that I can discover new trading opportunities.

#### Acceptance Criteria

1. WHEN the platform starts, THE LLM_Service SHALL connect to local Ollama instance
2. IF Ollama is not running, THEN THE AlphaCent SHALL log an error and disable strategy generation
3. WHEN strategy generation is requested, THE LLM_Service SHALL provide market context and constraints
4. THE LLM_Service SHALL parse LLM responses into structured strategy definitions
5. WHEN LLM response is invalid, THE LLM_Service SHALL retry with clarified prompts
6. THE LLM_Service SHALL validate generated strategies for completeness and correctness
7. THE LLM_Service SHALL support vibe-coding by translating natural language trading ideas into executable strategies
8. WHEN autonomous trading is started, THE Backend_Service SHALL verify Ollama is running and accessible
9. IF Ollama is not accessible when starting autonomous trading, THE Backend_Service SHALL attempt to start Ollama service or alert the user
10. WHEN autonomous trading is stopped, THE Backend_Service MAY optionally stop Ollama service based on configuration

### Requirement 8: eToro Social Trading Features

**User Story:** As a trader, I want access to eToro's social trading insights, so that I can leverage community sentiment and expert opinions.

#### Acceptance Criteria

1. THE AlphaCent SHALL retrieve social sentiment scores for instruments from eToro_API
2. THE AlphaCent SHALL retrieve trending symbols and their popularity metrics from eToro_API
3. THE AlphaCent SHALL retrieve Pro Investor positions and performance data from eToro_API
4. WHEN social insights are displayed, THE Dashboard SHALL show sentiment scores, trending status, and Pro Investor activity
5. THE Strategy_Engine SHALL optionally incorporate social sentiment into trading signals
6. THE AlphaCent SHALL update social insights at regular intervals

### Requirement 9: Smart Portfolios Integration

**User Story:** As a trader, I want to access eToro Smart Portfolios, so that I can invest in managed portfolio strategies.

#### Acceptance Criteria

1. THE AlphaCent SHALL retrieve available Smart Portfolios from eToro_API
2. WHEN Smart Portfolios are displayed, THE Dashboard SHALL show portfolio composition, performance metrics, and risk ratings
3. THE AlphaCent SHALL support investing in Smart Portfolios via eToro_API
4. THE AlphaCent SHALL track Smart Portfolio positions separately from individual instrument positions
5. WHEN Smart Portfolio performance is requested, THE AlphaCent SHALL retrieve historical returns and benchmark comparisons

### Requirement 10: Trading Modes

**User Story:** As a trader, I want to switch between demo and live trading modes, so that I can test strategies safely before risking real capital.

#### Acceptance Criteria

1. THE AlphaCent SHALL support Demo_Mode using eToro demo account credentials
2. THE AlphaCent SHALL support Live_Mode using eToro live account credentials
3. WHEN switching modes, THE AlphaCent SHALL disconnect from current account and reconnect to target account
4. THE Dashboard SHALL clearly indicate the current trading mode
5. WHEN in Demo_Mode, THE Dashboard SHALL display a prominent warning that trades are simulated
6. THE AlphaCent SHALL prevent accidental mode switches by requiring explicit confirmation
7. THE AlphaCent SHALL maintain separate configuration and state for each mode

### Requirement 11: Dashboard and User Interface

**User Story:** As a trader, I want a comprehensive dashboard, so that I can monitor my portfolio and control the platform.

#### Acceptance Criteria

1. THE Dashboard SHALL display current account balance, buying power, and margin usage
2. THE Dashboard SHALL display all open positions with current P&L
3. THE Dashboard SHALL display active strategies and their performance
4. THE Dashboard SHALL display recent orders and their status
5. THE Dashboard SHALL provide controls for activating Kill_Switch
6. THE Dashboard SHALL provide controls for enabling/disabling strategies
7. THE Dashboard SHALL display real-time market data for watchlist instruments
8. THE Dashboard SHALL display social insights and Smart Portfolio information
9. WHEN data updates are received, THE Dashboard SHALL refresh displays in real-time
10. THE Dashboard SHALL provide a vibe-coding interface for natural language strategy creation
11. THE Dashboard SHALL provide a master control to start/stop all autonomous trading operations
12. THE Dashboard SHALL display the current autonomous trading system status (ACTIVE, PAUSED, STOPPED)
13. WHEN a user logs in, THE Dashboard home page SHALL display last active strategies and their current status
14. WHEN a user logs in, THE Dashboard home page SHALL display performance metrics from the current and previous sessions
15. WHEN a user logs in, THE Dashboard home page SHALL display system operational status and any alerts
16. WHEN autonomous trading is stopped, THE Backend_Service SHALL halt signal generation for all strategies while maintaining existing positions

### Requirement 12: Market Hours Management

**User Story:** As a trader, I want the platform to respect market hours, so that orders are only placed when markets are open.

#### Acceptance Criteria

1. THE AlphaCent SHALL maintain a schedule of market hours for all supported exchanges
2. WHEN an order is requested, THE AlphaCent SHALL verify the target market is open
3. IF a market is closed, THEN THE AlphaCent SHALL queue the order for execution at market open
4. THE AlphaCent SHALL handle different market hours for stocks, ETFs, and cryptocurrencies
5. WHEN a market closes, THE AlphaCent SHALL pause strategy execution for that market
6. WHEN a market opens, THE AlphaCent SHALL resume strategy execution for that market
7. THE AlphaCent SHALL account for holidays and early closures

### Requirement 13: Performance Attribution and Benchmarking

**User Story:** As a trader, I want to track strategy performance against benchmarks, so that I can evaluate effectiveness.

#### Acceptance Criteria

1. THE AlphaCent SHALL calculate daily, weekly, and monthly returns for each strategy
2. THE AlphaCent SHALL calculate Sharpe ratio, Sortino ratio, and maximum drawdown for each strategy
3. THE AlphaCent SHALL compare strategy returns against relevant benchmarks (S&P 500, Bitcoin, etc.)
4. WHEN performance metrics are calculated, THE AlphaCent SHALL store them for historical analysis
5. THE Dashboard SHALL display performance charts and metrics for all strategies
6. THE AlphaCent SHALL attribute P&L to specific strategies and positions
7. THE AlphaCent SHALL calculate win rate, average win, and average loss for each strategy

### Requirement 14: Data Persistence and Recovery

**User Story:** As a trader, I want automatic backups and recovery, so that I don't lose critical data.

#### Acceptance Criteria

1. THE AlphaCent SHALL persist all configuration, strategies, and state to local storage
2. THE AlphaCent SHALL create automatic backups of critical data at regular intervals
3. WHEN the platform starts, THE AlphaCent SHALL restore state from the most recent backup
4. IF state restoration fails, THEN THE AlphaCent SHALL log the error and start with default state
5. THE AlphaCent SHALL maintain a transaction log of all orders and fills
6. THE AlphaCent SHALL support manual export of all data for external analysis
7. WHEN data corruption is detected, THE AlphaCent SHALL attempt recovery from backup

### Requirement 15: Cryptocurrency Trading

**User Story:** As a trader, I want to trade cryptocurrencies via eToro, so that I can diversify into digital assets.

#### Acceptance Criteria

1. THE AlphaCent SHALL support cryptocurrency trading for all instruments available on eToro
2. THE AlphaCent SHALL handle 24/7 market hours for cryptocurrency trading
3. THE AlphaCent SHALL apply appropriate risk parameters for cryptocurrency volatility
4. THE AlphaCent SHALL retrieve real-time cryptocurrency prices from eToro_API
5. WHEN cryptocurrency positions are opened, THE Order_Executor SHALL use appropriate order types
6. THE Dashboard SHALL display cryptocurrency positions separately from traditional assets

### Requirement 16: Web Application Architecture

**User Story:** As a trader, I want a local web application, so that I can access my trading platform through a browser while keeping all data and processing on my machine.

#### Acceptance Criteria

1. THE AlphaCent SHALL consist of a Backend_Service and Frontend_UI running on localhost
2. THE Backend_Service SHALL run on the user's local machine with no cloud dependencies
3. THE Backend_Service SHALL handle all trading logic, API connections, and data persistence
4. THE Frontend_UI SHALL provide a React-based single-page application
5. THE Frontend_UI SHALL be accessible via browser at localhost (e.g., http://localhost:3000)
6. THE Frontend_UI SHALL communicate with Backend_Service via RESTful API and WebSocket connections on localhost
7. THE Frontend_UI SHALL implement a minimalistic, quant trader aesthetic with dark mode support
8. THE AlphaCent SHALL support single-user authentication with secure session management
9. THE Backend_Service SHALL store all data locally on the user's machine
10. THE Frontend_UI SHALL be responsive and optimized for desktop browsers
11. THE Frontend_UI SHALL provide real-time updates via WebSocket for market data and position changes
12. THE Backend_Service SHALL continue running trading strategies even when the browser is closed
13. THE Backend_Service SHALL manage dependent services (Ollama LLM) lifecycle based on autonomous trading state
14. WHEN starting autonomous trading, THE Backend_Service SHALL verify all required services are running and accessible
15. IF required services are not running, THE Backend_Service SHALL attempt to start them or provide clear instructions to the user

### Requirement 16.1: Service Dependency Management

**User Story:** As a trader, I want the platform to automatically manage required services, so that I don't have to manually start/stop dependencies.

#### Acceptance Criteria

1. THE Backend_Service SHALL maintain a list of required dependent services (Ollama LLM)
2. WHEN autonomous trading is started, THE Backend_Service SHALL check if Ollama is running at localhost:11434
3. IF Ollama is not running, THE Backend_Service SHALL attempt to start Ollama using system commands
4. IF Ollama cannot be started automatically, THE Backend_Service SHALL transition to PAUSED state and alert the user with instructions
5. WHEN Ollama becomes unavailable during active trading, THE Backend_Service SHALL disable strategy generation but maintain existing positions
6. THE Backend_Service SHALL periodically health-check Ollama service (every 60 seconds)
7. WHEN autonomous trading is stopped, THE Backend_Service MAY optionally stop Ollama based on user configuration
8. THE Dashboard SHALL display status of all dependent services (Running, Stopped, Error)
9. THE Dashboard SHALL provide manual controls to start/stop dependent services
10. THE AlphaCent SHALL log all service lifecycle events (start, stop, health check failures)

### Requirement 17: User Interface Design

**User Story:** As a trader, I want a beautiful, minimalistic interface, so that I can focus on trading without distractions.

#### Acceptance Criteria

1. THE Frontend_UI SHALL implement a dark theme with high contrast for readability
2. THE Frontend_UI SHALL use a grid-based dashboard layout for organizing information
3. THE Frontend_UI SHALL display key metrics prominently (P&L, account balance, active positions)
4. THE Frontend_UI SHALL use charts and visualizations for performance data
5. THE Frontend_UI SHALL provide customizable dashboard layouts
6. THE Frontend_UI SHALL use monospace fonts for numerical data
7. THE Frontend_UI SHALL implement smooth animations for data updates
8. THE Frontend_UI SHALL provide keyboard shortcuts for common actions
9. THE Frontend_UI SHALL minimize visual clutter and focus on essential information

### Requirement 18: Security

**User Story:** As a trader, I want secure authentication and data protection, so that my trading account and strategies are protected.

#### Acceptance Criteria

1. THE AlphaCent SHALL require username and password authentication
2. THE AlphaCent SHALL hash passwords using bcrypt or similar secure algorithm
3. THE AlphaCent SHALL implement session-based authentication with secure cookies
4. THE AlphaCent SHALL enforce session timeouts after periods of inactivity
5. THE AlphaCent SHALL encrypt sensitive data at rest including API credentials
6. THE AlphaCent SHALL validate and sanitize all user inputs
7. THE AlphaCent SHALL implement rate limiting on authentication endpoints
8. THE AlphaCent SHALL log all authentication attempts and security events

### Requirement 19: Error Handling and Logging

**User Story:** As a trader, I want comprehensive error handling and logging, so that I can diagnose issues and maintain system reliability.

#### Acceptance Criteria

1. WHEN an error occurs, THE AlphaCent SHALL log it with timestamp, severity, and context
2. THE AlphaCent SHALL categorize errors by component and severity level
3. WHEN a critical error occurs, THE AlphaCent SHALL notify the user via Dashboard
4. THE AlphaCent SHALL maintain rolling log files with automatic rotation
5. THE Dashboard SHALL provide access to recent logs and error summaries
6. WHEN API rate limits are approached, THE AlphaCent SHALL throttle requests and log warnings
7. THE AlphaCent SHALL implement graceful degradation when non-critical components fail
