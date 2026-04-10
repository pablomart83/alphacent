# Requirements Document

## Introduction

The AlphaCent trading platform has a complete autonomous trading infrastructure including a strategy engine, LLM service, risk manager, order executor, and trading scheduler. However, no trading strategies have been created yet. This feature enables users to generate trading strategies using natural language, validate them through backtesting, activate them for autonomous trading, and monitor their real-time performance. The goal is to transition from "system ready but idle" to "autonomous trading with validated strategies."

## Glossary

- **Strategy_Engine**: The core component that generates, backtests, manages, and executes trading strategies
- **LLM_Service**: The Ollama-based service that translates natural language prompts into structured strategy definitions
- **Trading_Scheduler**: The autonomous loop that runs every 5 seconds to generate signals and execute trades for active strategies
- **Risk_Manager**: The component that validates trading signals against risk parameters before execution
- **Order_Executor**: The component that submits validated orders to the eToro API
- **Backtest**: Historical simulation of a strategy using vectorbt to calculate performance metrics
- **Strategy_Status**: The lifecycle state of a strategy (PROPOSED, BACKTESTED, DEMO, LIVE, RETIRED)
- **Trading_Mode**: The execution environment (DEMO or LIVE)
- **Performance_Metrics**: Quantitative measures of strategy performance (Sharpe ratio, Sortino ratio, max drawdown, win rate, total return)
- **Strategy_Rules**: The structured definition of entry/exit conditions, indicators, and parameters that define a strategy
- **Strategy_Reasoning**: The captured LLM reasoning process including hypothesis, market assumptions, signal logic, and alpha sources
- **Trading_Signal**: A generated recommendation to buy or sell a specific symbol with quantity and price
- **Signal_Confidence**: A numerical score indicating the strength of a trading signal based on indicator alignment
- **Alpha_Source**: The underlying market inefficiency or pattern that a strategy exploits (momentum, mean reversion, volatility, etc.)
- **Allocation_Percent**: The percentage of total portfolio capital allocated to a specific strategy

## Requirements

### Requirement 1: Generate Trading Strategies from Natural Language

**User Story:** As a trader, I want to generate trading strategies using natural language prompts, so that I can quickly create strategies without writing code.

#### Acceptance Criteria

1. WHEN a user submits a natural language prompt, THE LLM_Service SHALL generate a structured strategy definition including name, description, rules, entry conditions, exit conditions, indicators, and risk parameters
2. WHEN the LLM_Service generates a strategy, THE Strategy_Engine SHALL validate the strategy definition against required fields and constraints
3. WHEN a strategy is successfully generated, THE Strategy_Engine SHALL assign it a unique identifier and set its status to PROPOSED
4. WHEN a strategy is successfully generated, THE Strategy_Engine SHALL persist the strategy to the database
5. IF the LLM_Service fails to generate a valid strategy, THEN THE System SHALL return a descriptive error message to the user
6. WHEN a user provides market context (symbols, timeframe, risk tolerance), THE LLM_Service SHALL incorporate this context into the strategy generation

### Requirement 2: Backtest Strategies Against Historical Data

**User Story:** As a trader, I want to backtest generated strategies against historical data, so that I can validate their performance before risking real capital.

#### Acceptance Criteria

1. WHEN a user requests a backtest for a PROPOSED strategy, THE Strategy_Engine SHALL execute a vectorbt backtest using historical market data
2. WHEN a backtest completes, THE Strategy_Engine SHALL calculate performance metrics including Sharpe ratio, Sortino ratio, max drawdown, win rate, and total return
3. WHEN a backtest completes successfully, THE Strategy_Engine SHALL update the strategy status to BACKTESTED and persist the performance metrics
4. WHEN a backtest fails, THE Strategy_Engine SHALL return a descriptive error message and maintain the strategy status as PROPOSED
5. THE Strategy_Engine SHALL prevent activation of strategies that have not been backtested
6. WHEN backtesting, THE Strategy_Engine SHALL use a configurable historical data period (default: 90 days)
7. FOR ALL valid strategy definitions, backtesting then storing then retrieving SHALL produce equivalent performance metrics (round-trip property)

### Requirement 3: Activate Strategies for Autonomous Trading

**User Story:** As a trader, I want to activate backtested strategies for autonomous trading, so that the system can execute trades automatically based on strategy rules.

#### Acceptance Criteria

1. WHEN a user activates a BACKTESTED strategy, THE Strategy_Engine SHALL update the strategy status to DEMO or LIVE based on the selected trading mode
2. WHEN a strategy is activated, THE Strategy_Engine SHALL record the activation timestamp
3. WHEN a strategy is activated, THE Strategy_Engine SHALL validate that the strategy has been backtested
4. WHEN a strategy is activated, THE Strategy_Engine SHALL validate that total portfolio allocation does not exceed 100%
5. WHEN the Trading_Scheduler runs, THE Strategy_Engine SHALL generate signals for all strategies with status DEMO or LIVE
6. WHEN signals are generated, THE Risk_Manager SHALL validate each signal against risk parameters
7. WHEN signals are validated, THE Order_Executor SHALL submit orders to the eToro API
8. IF a strategy activation fails validation, THEN THE System SHALL return a descriptive error message and maintain the current status

### Requirement 4: Deactivate and Retire Strategies

**User Story:** As a trader, I want to deactivate or retire underperforming strategies, so that I can stop trading strategies that are not meeting expectations.

#### Acceptance Criteria

1. WHEN a user deactivates an active strategy (DEMO or LIVE), THE Strategy_Engine SHALL update the strategy status to BACKTESTED
2. WHEN a strategy is deactivated, THE Trading_Scheduler SHALL stop generating signals for that strategy
3. WHEN a user retires a strategy, THE Strategy_Engine SHALL update the strategy status to RETIRED and record the retirement timestamp
4. WHEN a strategy is retired, THE Strategy_Engine SHALL record the retirement reason
5. THE Strategy_Engine SHALL prevent activation of RETIRED strategies
6. WHEN a strategy is deactivated or retired, THE System SHALL not cancel existing open orders or positions

### Requirement 5: Monitor Strategy Performance in Real-Time

**User Story:** As a trader, I want to monitor strategy performance in real-time, so that I can make informed decisions about which strategies to keep active.

#### Acceptance Criteria

1. WHEN a strategy is active, THE Strategy_Engine SHALL continuously update performance metrics based on executed trades
2. WHEN performance metrics are updated, THE System SHALL broadcast updates via WebSocket to connected clients
3. WHEN a user views the strategies dashboard, THE Frontend SHALL display current performance metrics for each strategy
4. THE Frontend SHALL display strategy status, allocation percentage, symbols, total return, Sharpe ratio, max drawdown, and win rate
5. WHEN a strategy's performance metrics are updated, THE Frontend SHALL reflect the changes without requiring a page refresh
6. FOR ALL active strategies, the displayed performance metrics SHALL match the persisted metrics in the database

### Requirement 6: Bootstrap Initial Strategies via CLI or API

**User Story:** As a system administrator, I want to quickly bootstrap initial strategies, so that I can transition from an idle system to active trading with minimal manual effort.

#### Acceptance Criteria

1. WHEN a bootstrap command is executed, THE System SHALL generate 2-3 sample strategies with different trading approaches (momentum, mean reversion, breakout)
2. WHEN sample strategies are generated, THE System SHALL automatically backtest each strategy
3. WHEN backtests complete, THE System SHALL display performance metrics for each strategy
4. WHEN a bootstrap command is executed, THE System SHALL provide an option to automatically activate strategies that meet minimum performance thresholds
5. THE System SHALL support bootstrap via CLI command or API endpoint
6. WHEN bootstrap completes, THE System SHALL return a summary of created strategies and their backtest results

### Requirement 7: Validate Strategy Constraints and Risk Parameters

**User Story:** As a risk manager, I want the system to validate strategy constraints and risk parameters, so that strategies operate within acceptable risk boundaries.

#### Acceptance Criteria

1. WHEN a strategy is generated, THE Strategy_Engine SHALL validate that risk parameters include max position size, max drawdown threshold, and stop loss percentage
2. WHEN a strategy is activated, THE Strategy_Engine SHALL validate that the strategy's allocation percentage is between 0 and 100
3. WHEN calculating total portfolio allocation, THE Strategy_Engine SHALL ensure the sum of all active strategy allocations does not exceed 100%
4. WHEN a signal is generated, THE Risk_Manager SHALL validate that the position size does not exceed the strategy's max position size
5. IF any validation fails, THEN THE System SHALL reject the operation and return a descriptive error message
6. FOR ALL valid strategies, the risk parameters SHALL remain within configured bounds after any operation

### Requirement 8: Visualize LLM Reasoning and Strategy Generation Process

**User Story:** As a trader, I want to see what the LLM is reasoning and what happens behind the scenes during strategy generation, so that I can understand the strategy's hypothesis, signals, and alpha sources.

#### Acceptance Criteria

1. WHEN the LLM_Service generates a strategy, THE System SHALL capture and store the LLM's reasoning process including hypothesis, market assumptions, and signal logic
2. WHEN a strategy is being generated, THE Frontend SHALL display real-time progress updates showing the generation stages (analyzing prompt, generating rules, validating constraints, creating indicators)
3. WHEN a strategy is displayed, THE Frontend SHALL show the strategy's core hypothesis and market assumptions in human-readable format
4. WHEN a strategy generates signals, THE Frontend SHALL display the signal generation process including which indicators triggered, threshold values, and confidence scores
5. WHEN backtesting is running, THE Frontend SHALL display progress updates including current date being processed, signals generated so far, and preliminary metrics
6. WHEN viewing a strategy, THE Frontend SHALL visualize the alpha sources (momentum, mean reversion, volatility, etc.) and their relative weights
7. WHEN a strategy is active, THE Frontend SHALL display a real-time feed of signal generation events with timestamps, symbols, and reasoning
8. THE Frontend SHALL provide an expandable "Strategy Reasoning" section that shows the LLM's original prompt, generated rules, and validation results

### Requirement 9: Persist and Retrieve Strategy State

**User Story:** As a developer, I want strategy state to be persisted reliably, so that the system can recover from restarts without losing strategy configurations or performance data.

#### Acceptance Criteria

1. WHEN a strategy is created, THE Strategy_Engine SHALL persist the strategy to the database with all fields including reasoning metadata
2. WHEN a strategy is updated, THE Strategy_Engine SHALL persist the updated state to the database
3. WHEN the system restarts, THE Strategy_Engine SHALL load all strategies from the database
4. WHEN the Trading_Scheduler starts, THE System SHALL resume generating signals for all active strategies
5. FOR ALL valid strategies, persisting then retrieving SHALL produce an equivalent strategy object (round-trip property)
6. WHEN performance metrics are updated, THE Strategy_Engine SHALL persist the updates immediately to prevent data loss
