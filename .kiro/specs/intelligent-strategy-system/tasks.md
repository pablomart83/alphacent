# Implementation Plan: Intelligent Strategy System (Simplified)

## Overview

This implementation focuses on creating an autonomous end-to-end trading system that proposes, backtests, activates, and manages profitable strategies. We're keeping it simple and practical - no over-engineering.

**Key Principles:**
- Use deterministic DSL for rule interpretation (no LLM needed)
- Use proven strategy templates (no LLM generation needed)
- Focus on autonomous strategy lifecycle, not fancy features
- Reuse existing infrastructure (MarketDataManager, Database, etc.)
- Get to profitable trading quickly

## Tasks

- [x] 1. LLM Service Setup (Historical - No Longer Used)
  - ✅ COMPLETED - LLM service was initially set up for rule interpretation
  - NOTE: System no longer uses LLM - replaced with DSL (Task 9.11.4) and Templates (Task 9.10)
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 9.1, 9.2, 9.3_

- [ ]* 1.1 Write property tests for DSL rule parsing (Optional)
  - **Property 1: DSL Parsing Correctness** - For any valid DSL rule, parser should produce valid AST
  - **Property 2: Code Generation Correctness** - For any valid AST, code generator should produce syntactically valid pandas code
  - **Property 3: Logical Structure Preservation** - For any rule with AND/OR logic, generated code should produce same logical result
  - **Validates: Requirements 1.1, 1.2, 1.3, 1.4**

- [x] 2. Fix Signal Generation to Use Rule Interpretation
  - ✅ COMPLETED - Initially used LLM for rule interpretation
  - NOTE: Task 9.11.4 replaces with DSL for production reliability (no LLM needed)
  - Update `_parse_strategy_rules()` in StrategyEngine to interpret rules
  - Use `eval()` with safe namespace (only pandas, numpy, math) to execute generated code
  - Add basic error handling - if code fails, log error and skip that rule
  - Test with existing momentum strategy to verify it now generates signals
  - _Requirements: 1.1, 1.2, 5.1, 5.2_
  - **Estimated time: 2-3 hours**

- [x] 3. Implement Basic Indicator Library (10 essential indicators)
  - Create `IndicatorLibrary` class with these indicators only:
    - SMA (Simple Moving Average)
    - EMA (Exponential Moving Average)  
    - RSI (Relative Strength Index)
    - MACD (Moving Average Convergence Divergence)
    - Bollinger Bands
    - ATR (Average True Range)
    - Volume MA
    - Price Change % (for momentum)
    - Support/Resistance (simple high/low)
    - Stochastic Oscillator
  - Use pandas for calculations (no external libraries needed)
  - Add simple caching: store results in dict keyed by (symbol, indicator, params)
  - _Requirements: 4.1, 4.2, 10.2_
  - **Estimated time: 3-4 hours**

- [x] 4. Implement Strategy Proposer (Autonomous Strategy Generation)
  - Create `StrategyProposer` class
  - Implement simple market regime detection:
    - Calculate 20-day and 50-day price change
    - If both positive → TRENDING_UP
    - If both negative → TRENDING_DOWN  
    - Otherwise → RANGING
  - Implement `propose_strategies()` method:
    - Select appropriate templates for current regime (Task 9.10)
    - Customize template parameters based on market data (Task 9.9)
    - Return list of Strategy objects with status=PROPOSED
  - _Requirements: 16.1, 16.3, 16.4, 21.1, 21.2_
  - **Estimated time: 2-3 hours**

- [x] 5. Implement Portfolio Manager (Autonomous Activation & Retirement)
  - Create `PortfolioManager` class
  - Implement `evaluate_for_activation()`:
    - Check: Sharpe > 1.5, max_drawdown < 0.15, win_rate > 0.5, total_trades > 20
    - Return True if all conditions met
  - Implement `auto_activate_strategy()`:
    - Calculate allocation: 100% / number_of_active_strategies (max 10 strategies)
    - Call existing `strategy_engine.activate_strategy()` in DEMO mode
  - Implement `check_retirement_triggers()`:
    - Check: Sharpe < 0.5 (30+ trades) OR max_drawdown > 0.15 OR win_rate < 0.4 (50+ trades)
    - Return retirement reason if should retire
  - Implement `auto_retire_strategy()`:
    - Call existing `strategy_engine.deactivate_strategy()`
    - Close all positions for that strategy
  - _Requirements: 17.1, 17.2, 18.1, 18.2, 18.3, 18.4, 19.1, 19.2, 19.3, 20.1_
  - **Estimated time: 3-4 hours**

- [x] 6. Create Autonomous Strategy Loop (The Main Event)
  - Create `AutonomousStrategyManager` class that orchestrates everything
  - Implement `run_strategy_cycle()` method:
    1. Call `StrategyProposer.propose_strategies()` to get 3-5 proposals
    2. For each proposal, call `StrategyEngine.backtest_strategy()`
    3. For each backtested strategy, call `PortfolioManager.evaluate_for_activation()`
    4. If evaluation passes, call `PortfolioManager.auto_activate_strategy()`
    5. For all active strategies, call `PortfolioManager.check_retirement_triggers()`
    6. If retirement needed, call `PortfolioManager.auto_retire_strategy()`
  - Add scheduling: run cycle once per week (configurable)
  - Add logging for all decisions (proposed, activated, retired)
  - _Requirements: 16.1, 17.1, 18.1, 19.1, 20.1_
  - **Estimated time: 2-3 hours**

- [x] 7. Add Simple Database Tables
  - Create migration for `strategy_proposals` table:
    - id, strategy_id, proposed_at, market_regime, backtest_sharpe, activated (boolean)
  - Create migration for `strategy_retirements` table:
    - id, strategy_id, retired_at, reason, final_sharpe, final_return
  - Update ORM models
  - _Requirements: 10.2, 22.1_
  - **Estimated time: 1 hour**

- [x] 8. Add Configuration File
  - Create `config/autonomous_trading.yaml`:
    ```yaml
    autonomous:
      enabled: true
      proposal_frequency: "weekly"  # or "daily"
      max_active_strategies: 10
      min_active_strategies: 5
    
    activation_thresholds:
      min_sharpe: 1.5
      max_drawdown: 0.15
      min_win_rate: 0.5
      min_trades: 20
    
    retirement_thresholds:
      max_sharpe: 0.5
      max_drawdown: 0.15
      min_win_rate: 0.4
      min_trades_for_evaluation: 30
    ```
  - Load config in AutonomousStrategyManager
  - _Requirements: All_
  - **Estimated time: 30 minutes**

- [x] 9. Integration & Testing
  - Test complete autonomous cycle end-to-end:
    1. Manually trigger `run_strategy_cycle()`
    2. Verify strategies are proposed
    3. Verify strategies are backtested
    4. Verify high performers are activated
    5. Verify underperformers are retired
  - Test with real market data (no mocks)
  - Fix any bugs found
  - _Requirements: 23.1, 23.2, 23.3, 23.4_
  - **Estimated time: 2-3 hours**

- [x] 9.5 Fix Critical Integration Issues (Data Quality & Signal Generation)
  - **Context**: Integration test revealed strategies generate zero trades due to data quality and naming issues
  - **Goal**: Ensure strategies generate actual trading signals and backtests produce meaningful results
  - _Requirements: 23.1, 23.2, 23.3, 23.4, 17.1, 17.2_
  - **Estimated time: 4-6 hours**

- [x] 9.5.1 Implement eToro Historical Data Fetching
  - Add `get_historical_data()` method to EToroAPIClient
  - Support date range parameters (start_date, end_date)
  - Return data in standardized format (OHLCV)
  - Handle pagination if needed for large date ranges
  - Add proper error handling and fallback to Yahoo Finance
  - Test with SPY, QQQ, DIA to verify 90+ days of data
  - **Acceptance**: Can fetch 90 days of historical data from eToro API
  - **Estimated time: 1-2 hours**

- [x] 9.5.2 Standardize Indicator Naming Convention
  - Define standard naming format: `{indicator}_{period}` (e.g., "SMA_20", "RSI_14")
  - Update IndicatorLibrary to return standardized keys:
    - `calculate_sma(period=20)` returns key "SMA_20"
    - `calculate_rsi(period=14)` returns key "RSI_14"
    - Apply to all 10 indicators
  - Update LLM prompts to use exact naming convention:
    - Add indicator naming examples to strategy generation prompt
    - Include available indicators with exact names
  - Remove runtime patching code in StrategyEngine (no more "attempting to fix")
  - Add validation: reject strategies with invalid indicator references
  - Test: Generate strategy, verify indicator names match exactly
  - **Acceptance**: No indicator key errors, no runtime patching needed
  - **Estimated time: 2-3 hours**

- [x] 9.5.3 Add Strategy Signal Validation
  - Create `validate_strategy_signals()` method in StrategyEngine
  - Before backtesting, run quick validation:
    - Fetch 30 days of data for first symbol
    - Generate signals using strategy rules
    - Count entry and exit signals
  - Validation criteria:
    - Must generate at least 1 entry signal in 30 days
    - Must generate at least 1 exit signal in 30 days
    - Rules must execute without errors
  - If validation fails:
    - Log detailed error (which rule failed, why)
    - Mark strategy as INVALID
    - Don't proceed to full backtest
    - Optionally: request LLM to revise strategy
  - Update AutonomousStrategyManager to skip invalid strategies
  - **Acceptance**: Only strategies that generate signals are backtested
  - **Estimated time: 1-2 hours**

- [x] 9.5.4 Improve Market Regime Detection Data Requirements
  - Reduce minimum data requirement from 60 days to 30 days
  - Add data quality scoring:
    - EXCELLENT: 60+ days of data
    - GOOD: 45-59 days
    - FAIR: 30-44 days
    - POOR: <30 days
  - Update `analyze_market_conditions()`:
    - Return tuple: (regime, confidence, data_quality)
    - Only default to RANGING if data_quality is POOR
    - Use actual analysis for FAIR or better
  - Add logging showing data quality for each symbol
  - Update AutonomousStrategyManager to:
    - Log data quality in cycle stats
    - Warn if proposing strategies with POOR data quality
  - **Acceptance**: Market regime based on real analysis when 30+ days available
  - **Estimated time: 1 hour**

- [x] 9.5.5 Re-run Integration Test & Verify Results
  - Run `test_e2e_autonomous_system.py` again
  - Verify improvements:
    - ✅ 90+ days of historical data fetched
    - ✅ No indicator naming errors
    - ✅ Market regime detected (not defaulted)
    - ✅ Strategies generate signals (trades > 0)
    - ✅ Backtest results meaningful (Sharpe not inf)
    - ✅ At least 1 strategy meets activation criteria
  - Document results in `TASK_9.5_VERIFICATION.md`
  - If any criteria not met, iterate on fixes
  - **Acceptance**: All verification criteria pass
  - **Estimated time: 30 minutes + iteration time**

- [x] 9.6 Improve LLM Strategy Generation Quality
  - **Context**: LLM occasionally generates indicator name variations (BB_L_20 vs Lower_Band_20) and some strategies don't produce entry signals
  - **Goal**: Improve LLM prompting and validation to generate higher quality strategies with consistent indicator naming
  - _Requirements: 1.1, 1.2, 16.1, 16.3, 23.1_
  - **Estimated time: 3-4 hours**

- [x] 9.6.1 Enhance LLM Prompts with Explicit Indicator Naming Examples
  - Update `interpret_trading_rule()` prompt in LLMService to include comprehensive indicator naming examples:
    - Single-word indicators: RSI_14, SMA_20, EMA_50, ATR_14, STOCH_14
    - Multi-word indicators: VOLUME_MA_20, PRICE_CHANGE_PCT_1
    - Bollinger Bands: BBANDS_20_2_UB, BBANDS_20_2_MB, BBANDS_20_2_LB (or Upper_Band_20, Middle_Band_20, Lower_Band_20)
    - MACD: MACD_12_26_9, MACD_12_26_9_SIGNAL, MACD_12_26_9_HIST
    - Support/Resistance: Support, Resistance (simple names)
  - Add explicit instruction: "Use EXACT indicator names from the available_indicators list. Do not invent variations."
  - Add validation examples showing correct vs incorrect naming
  - Update `_create_proposal_prompt()` in StrategyProposer to include exact indicator naming format
  - **Acceptance**: LLM prompts explicitly show exact indicator naming conventions
  - **Estimated time: 1 hour**

- [x] 9.6.2 Add Strategy Quality Scoring and Filtering
  - Create `score_strategy_quality()` method in StrategyProposer:
    - Complexity score: Count unique indicators used (2-3 is ideal, 1 is too simple, 4+ is too complex)
    - Logic score: Check for balanced entry/exit conditions (both should exist)
    - Diversity score: Penalize strategies that are too similar to existing active strategies
    - Regime appropriateness: Score how well strategy matches current market regime
  - Update `propose_strategies()` to:
    - Generate 2x the requested count (e.g., 10 strategies if count=5)
    - Score each strategy using quality scoring
    - Filter to top N strategies by quality score
    - Log quality scores for transparency
  - Add quality score to Strategy metadata for tracking
  - **Acceptance**: Only high-quality strategies are proposed (quality score > 0.6)
  - **Estimated time: 2 hours**

- [x] 9.6.3 Implement Strategy Revision Loop
  - Add `revise_strategy()` method to StrategyProposer:
    - Takes a failed strategy and validation errors
    - Asks LLM to revise the strategy based on specific errors
    - Uses more explicit prompting: "The previous strategy failed because: {errors}. Generate a revised strategy that fixes these issues."
    - Limits to 2 revision attempts per strategy
  - Update AutonomousStrategyManager to use revision loop:
    - If strategy validation fails, attempt revision
    - If revision succeeds, use revised strategy
    - If revision fails, discard and move to next proposal
  - Add revision tracking to database (revision_count, original_strategy_id)
  - **Acceptance**: Failed strategies get 2 revision attempts before being discarded
  - **Estimated time: 1-2 hours**

- [x] 9.6.4 Test and Verify Improvements
  - Run autonomous cycle with improvements
  - Verify metrics:
    - ✅ Indicator naming errors reduced to <10% (from ~30%)
    - ✅ Strategy validation pass rate >60% (from ~40%)
    - ✅ At least 2 strategies meet activation criteria per cycle
    - ✅ Quality scores logged for all proposals
    - ✅ Revision loop successfully improves failed strategies
  - Document results and quality improvements
  - **Acceptance**: All verification criteria pass
  - **Estimated time: 30 minutes + iteration time**

- [x] 9.7 Fix Indicator Library and Strategy Engine Integration
  - **Context**: Task 9.6 revealed critical issues - strategies reference indicators (Bollinger Bands, Support/Resistance) that aren't being calculated, causing 0 entry signals and poor backtest results
  - **Goal**: Fix the disconnect between LLM-generated strategies and indicator calculation to achieve 100% working autonomous system
  - _Requirements: 1.1, 1.2, 4.1, 4.2, 5.1, 5.2, 23.1_
  - **Root Causes Identified**:
    1. Indicator library doesn't calculate Bollinger Bands when strategy references them
    2. Support/Resistance calculation returns 0 for all days (broken)
    3. Strategy engine doesn't map "Bollinger Bands" → ["Upper_Band_20", "Middle_Band_20", "Lower_Band_20"]
    4. LLM generates same strategy repeatedly (no diversity)
  - **Estimated time: 4-6 hours**

- [x] 9.7.1 Fix Indicator Detection and Calculation in Strategy Engine
  - Update `_parse_strategy_rules()` in StrategyEngine to detect indicator references from strategy.rules["indicators"] list
  - Add indicator name mapping:
    - "Bollinger Bands" → calculate and return ["Upper_Band_20", "Middle_Band_20", "Lower_Band_20"]
    - "MACD" → calculate and return ["MACD_12_26_9", "MACD_12_26_9_SIGNAL", "MACD_12_26_9_HIST"]
    - "Support/Resistance" → calculate and return ["Support", "Resistance"]
    - "Stochastic Oscillator" → calculate and return ["STOCH_14"]
  - Update indicator calculation logic to:
    1. Parse strategy.rules["indicators"] list
    2. For each indicator name, call appropriate IndicatorLibrary method
    3. Store all returned keys in indicators dict
    4. Log which indicators were calculated and their keys
  - Test with strategy that uses "Bollinger Bands" - verify Upper_Band_20, Middle_Band_20, Lower_Band_20 are all available
  - **Acceptance**: Strategy referencing "Bollinger Bands" has all 3 band keys available for rule evaluation
  - **Estimated time: 2 hours**

- [x] 9.7.2 Fix Support/Resistance Calculation in Indicator Library
  - Review `calculate_support_resistance()` method in IndicatorLibrary
  - Current issue: Returns 0 for all days
  - Fix calculation to use proper rolling window approach:
    - Support = rolling minimum of low prices over period (default 20 days)
    - Resistance = rolling maximum of high prices over period (default 20 days)
  - Add validation to ensure non-zero values
  - Test with AAPL data - verify Support and Resistance are meaningful values
  - Log support/resistance ranges for debugging
  - **Acceptance**: Support and Resistance return non-zero values that make sense (support < current price < resistance for ranging markets)
  - **Estimated time: 1 hour**

- [x] 9.7.3 Improve Strategy Diversity in LLM Generation
  - Update `_create_proposal_prompt()` in StrategyProposer to include:
    - Explicit diversity instruction: "Generate a UNIQUE strategy different from typical mean reversion"
    - Add strategy number context: "This is strategy #{n} of {total}, make it distinct"
    - Vary the prompt based on strategy number:
      - Strategy 1-2: Focus on mean reversion
      - Strategy 3-4: Focus on momentum/breakout
      - Strategy 5-6: Focus on volatility/oscillators
  - Increase LLM temperature from 0.7 to 0.8 for strategy generation (more randomness)
  - Add seed randomization to prevent identical outputs
  - Test: Generate 6 strategies and verify they have different names and different indicator combinations
  - **Acceptance**: 6 generated strategies have at least 4 different names and use different indicator combinations
  - **Estimated time: 1 hour**

- [x] 9.7.4 Add Comprehensive Indicator Calculation Logging
  - Add detailed logging in StrategyEngine for indicator calculation:
    - Log strategy.rules["indicators"] list
    - Log each indicator being calculated
    - Log the keys returned by each indicator
    - Log the final indicators dict keys
    - Log any missing indicators referenced in rules
  - Add validation check: If rule references indicator key not in indicators dict, log ERROR with:
    - Rule text
    - Referenced indicator key
    - Available indicator keys
    - Suggestion for fix
  - This will help debug future indicator mismatch issues
  - **Acceptance**: Logs clearly show which indicators are calculated and which are missing
  - **Estimated time: 30 minutes**

- [x] 9.7.5 Run Full Integration Test and Verify 100% Success
  - Run `test_e2e_autonomous_system.py` with all fixes
  - Create detailed verification log: `TASK_9.7_VERIFICATION.md`
  - Verify ALL criteria pass:
    - ✅ 6 strategies generated with quality filtering
    - ✅ At least 4 different strategy names (diversity)
    - ✅ All strategies reference indicators that are calculated
    - ✅ No "Failed to parse" errors for indicators
    - ✅ Bollinger Bands strategies have all 3 bands available
    - ✅ Support/Resistance returns non-zero values
    - ✅ Strategies generate meaningful entry signals (>0 days)
    - ✅ Backtest results are reasonable (Sharpe > -2, trades > 1)
    - ✅ At least 1 strategy meets activation criteria (Sharpe > 1.5)
    - ✅ Revision loop works when needed
    - ✅ Quality scores logged for all proposals
  - If ANY criteria fails, iterate and fix
  - Document final results with:
    - Strategy names and indicators used
    - Entry/exit signal counts
    - Backtest results (Sharpe, return, trades)
    - Activation decisions
    - Comparison to baseline (n)
  - **Acceptance**: ALL 11 verification criteria pass, system is 100% functional
  - **Estimated time: 1 hour + iteration time**

- [x] 9.8 Fix Fundamental Strategy Quality Issues
  - **Context**: Integration test revealed strategies generate nonsensical rules (e.g., "RSI below 70" for entry, "RSI above 30" for exit) causing massive signal overlap and only 1 trade per backtest
  - **Goal**: Implement proper strategy rule validation and LLM prompting to generate trading-viable strategies with meaningful entry/exit logic
  - _Requirements: 1.1, 1.2, 8.1, 8.2, 8.3, 16.1, 16.3, 23.1_
  - **Root Causes**:
    1. LLM generates bad thresholds (RSI < 70 instead of RSI < 30 for oversold)
    2. Entry/exit conditions overlap (both trigger on same days)
    3. No validation of whether rules make trading sense
    4. OR logic exposes bad individual conditions
  - **Estimated time: 4-6 hours**

- [x] 9.8.1 Add Strategy Rule Validation
  - Create `validate_strategy_rules()` method in StrategyEngine
  - Validate RSI thresholds:
    - Entry oversold: RSI must be < 35 (not < 70)
    - Exit overbought: RSI must be > 65 (not > 30)
    - Reject if thresholds don't make sense
  - Validate Bollinger Band logic:
    - Entry at lower band: price < Lower_Band
    - Exit at upper band: price > Upper_Band
    - Reject if reversed
  - Validate entry/exit pairing:
    - Calculate signal overlap percentage
    - Reject if > 50% overlap (signals too similar)
    - Require at least 20% of days with entry but no exit
  - Add validation before backtesting in autonomous cycle
  - Log detailed validation failures with suggestions
  - **Acceptance**: Strategies with bad thresholds or high overlap are rejected
  - **Estimated time: 2 hours**

- [x] 9.8.2 Enhance LLM Strategy Generation Prompts
  - Update `_format_strategy_prompt()` with specific threshold examples:
    - RSI oversold entry: "RSI_14 is below 30" (not 70)
    - RSI overbought exit: "RSI_14 rises above 70" (not 30)
    - Bollinger lower entry: "Price crosses below Lower_Band_20"
    - Bollinger upper exit: "Price crosses above Upper_Band_20"
  - Add explicit pairing rules:
    - "If entry uses RSI < 30, exit MUST use RSI > 70"
    - "If entry uses Lower_Band, exit MUST use Upper_Band or Middle_Band"
  - Add anti-patterns to avoid:
    - "NEVER use RSI < 70 for entry (too common)"
    - "NEVER use RSI > 30 for exit (too common)"
    - "NEVER use same threshold for entry and exit"
  - Include example of good strategy:
    ```json
    {
      "entry_conditions": ["RSI_14 is below 30", "Price is below Lower_Band_20"],
      "exit_conditions": ["RSI_14 rises above 70", "Price is above Upper_Band_20"]
    }
    ```
  - **Acceptance**: LLM generates strategies with proper thresholds (RSI < 30 for entry, > 70 for exit)
  - **Estimated time: 1 hour**

- [x] 9.8.3 Improve Signal Overlap Detection and Logging
  - Add detailed overlap analysis in backtest logging:
    - Log entry-only days, exit-only days, overlap days
    - Calculate overlap percentage
    - Log first 5 dates where signals overlap
  - Enhance conflict resolution logic:
    - If overlap > 80%, reject strategy before backtesting
    - If overlap 50-80%, warn but continue
    - If overlap < 50%, proceed normally
  - Add signal quality metrics:
    - Average days between entry signals
    - Average holding period (entry to exit)
    - Signal frequency (signals per month)
  - **Acceptance**: Logs clearly show signal overlap issues, strategies with >80% overlap rejected
  - **Estimated time: 1 hour**

- [x] 9.8.4 Test and Iterate Until Strategies Generate Real Trades
  - Run integration test with all fixes
  - Verify strategies generate:
    - ✅ Proper RSI thresholds (< 30 for entry, > 70 for exit)
    - ✅ Low signal overlap (< 50%)
    - ✅ Multiple trades (> 3 trades in 90 days)
    - ✅ Reasonable holding periods (> 1 day average)
    - ✅ At least 1 strategy with Sharpe > 0
  - If criteria not met, analyze failures and iterate:
    - Check LLM prompt effectiveness
    - Adjust validation thresholds
    - Add more specific examples
  - Document final results with:
    - Strategy rules generated
    - Signal overlap percentages
    - Trade counts and holding periods
    - Sharpe ratios and returns
  - **Acceptance**: At least 2/3 strategies generate >3 trades with <50% overlap
  - **Estimated time: 2-3 hours + iteration**

- [ ] 9.9 Implement Data-Driven Strategy Generation (Level 1)
  - **Context**: Current LLM generates strategies blindly without market data, resulting in unprofitable strategies
  - **Goal**: Feed LLM actual market statistics to enable informed strategy generation
  - _Requirements: 1.1, 1.2, 16.1, 16.3, 21.1, 21.2_
  - **Estimated time: 6-8 hours**

- [x] 9.9.1 Create Market Statistics Analyzer with Multi-Source Data
  - Create `MarketStatisticsAnalyzer` class in `src/strategy/market_analyzer.py`
  - **Data Sources Integration**:
    - Primary: Yahoo Finance (OHLCV data - already implemented)
    - Secondary: Alpha Vantage (pre-calculated indicators, sector data)
    - Tertiary: FRED (macro economic context - VIX, rates)
    - Implement graceful fallback if external APIs unavailable
  - **Install dependencies**: `pip install alpha-vantage fredapi`
  - **Configuration**: Add API keys to `config/autonomous_trading.yaml`:
    ```yaml
    data_sources:
      alpha_vantage:
        enabled: true
        api_key: "YOUR_FREE_KEY"  # Get from alphavantage.co
        calls_per_day: 500
      fred:
        enabled: true
        api_key: "YOUR_FREE_KEY"  # Get from fred.stlouisfed.org
        calls_per_day: unlimited
    ```
  - Implement `analyze_symbol()` method that calculates:
    - **Volatility metrics**: 
      - ATR/price ratio (from OHLCV)
      - Standard deviation of returns (from OHLCV)
      - Historical volatility (20-day rolling)
      - Try Alpha Vantage ATR first, fallback to calculation
    - **Trend metrics**: 
      - 20d/50d price change (from OHLCV)
      - ADX (Average Directional Index) - calculate or get from Alpha Vantage
      - Trend strength score (0-1)
    - **Mean reversion metrics**: 
      - Hurst exponent (from OHLCV)
      - Autocorrelation (lag-1, lag-5)
      - Mean reversion score (0-1)
    - **Price action**: 
      - Current price, 20d high/low (from OHLCV)
      - Support/resistance levels (from OHLCV)
    - **Market context** (from FRED):
      - VIX (market fear index) - current level
      - 10-year treasury yield (risk-free rate)
      - Market regime indicator (risk-on vs risk-off)
    - **Sector performance** (from Alpha Vantage):
      - Sector of symbol (if available)
      - Sector relative strength
  - Implement `analyze_indicator_distributions()` method:
    - Try Alpha Vantage pre-calculated indicators first (RSI, MACD, etc.)
    - Fallback to local calculation if API unavailable
    - For each indicator (RSI, STOCH, etc.), calculate:
      - Mean, std, min, max
      - Percentage of time in oversold zone (< 30)
      - Percentage of time in overbought zone (> 70)
      - Typical duration in each zone
      - Current value vs historical distribution
  - Implement `get_market_context()` method:
    - Fetch VIX from FRED (market volatility)
    - Fetch treasury yields from FRED (risk-free rate)
    - Calculate risk-on/risk-off score
    - Return macro context for strategy generation
  - Add intelligent caching:
    - Cache OHLCV data for 1 hour
    - Cache Alpha Vantage data for 4 hours (save API calls)
    - Cache FRED data for 24 hours (updates daily)
    - Cache key: (symbol, metric, period, timestamp)
  - Add rate limiting:
    - Track Alpha Vantage calls (max 500/day)
    - Warn when approaching limit
    - Automatically fallback to local calculation
  - Test with AAPL, SPY, QQQ:
    - Verify all metrics calculated correctly
    - Verify Alpha Vantage integration works
    - Verify FRED integration works
    - Verify fallback works when APIs disabled
    - Verify caching reduces API calls
  - **Acceptance**: Returns comprehensive market statistics from multiple sources with graceful fallback
  - **Estimated time: 3-4 hours**

- [x] 9.9.2 Integrate Market Statistics into Strategy Generation
  - Update `StrategyProposer.propose_strategies()` to:
    - Call `MarketStatisticsAnalyzer.analyze_symbol()` for each symbol
    - Call `MarketStatisticsAnalyzer.analyze_indicator_distributions()`
    - Pass statistics to LLM in prompt
  - Update `_create_proposal_prompt()` to include market data section:
    ```
    CRITICAL MARKET DATA:
    - Volatility: {volatility*100:.1f}%
    - Trend strength: {trend_strength:.2f}
    - Mean reversion score: {mean_reversion_score:.2f}
    - RSI below 30 occurs {rsi_pct_oversold:.1f}% of time
    - RSI above 70 occurs {rsi_pct_overbought:.1f}% of time
    - Support levels: {support_levels}
    - Resistance levels: {resistance_levels}
    - Current price: {current_price:.2f}
    
    Design a strategy that:
    1. Uses thresholds that actually trigger in this market
    2. Accounts for the current volatility level
    3. Respects actual support/resistance levels
    ```
  - Add logging to show what market data is being used
  - **Acceptance**: LLM receives comprehensive market statistics in prompt
  - **Estimated time: 2 hours**

- [x] 9.9.3 Add Recent Strategy Performance Tracking
  - Create `StrategyPerformanceTracker` class in `src/strategy/performance_tracker.py`
  - Implement database table `strategy_performance_history`:
    - strategy_type (mean_reversion, momentum, breakout)
    - market_regime (trending_up, trending_down, ranging)
    - sharpe_ratio, total_return, win_rate
    - backtest_date, symbol
  - Implement `track_performance()` method to store backtest results
  - Implement `get_recent_performance()` method:
    - Returns average Sharpe by strategy type and market regime
    - Filters to last 30 days of backtests
    - Returns success rate (% with Sharpe > 0)
  - Update `StrategyProposer` to include performance history in prompt:
    ```
    RECENT STRATEGY PERFORMANCE:
    - Mean reversion strategies: avg Sharpe {sharpe:.2f}, success rate {success_rate:.0%}
    - Momentum strategies: avg Sharpe {sharpe:.2f}, success rate {success_rate:.0%}
    - Breakout strategies: avg Sharpe {sharpe:.2f}, success rate {success_rate:.0%}
    
    Prefer strategy types that have worked recently in this market regime.
    ```
  - **Acceptance**: LLM sees what strategy types have worked recently
  - **Estimated time: 2-3 hours**

- [x] 9.9.4 Test Data-Driven Generation and Measure Improvement
  - Run autonomous cycle with data-driven generation
  - Compare to baseline (iteration 3 results):
    - Baseline: 0/3 strategies with positive Sharpe
    - Target: At least 1/3 strategies with positive Sharpe
  - Verify LLM uses market data:
    - Check logs for market statistics in prompts
    - Verify strategies use appropriate thresholds for current market
    - Verify strategies match recent performance patterns
  - Document improvements in `TASK_9.9_RESULTS.md`:
    - Strategy quality metrics
    - Sharpe ratio distribution
    - Comparison to baseline
    - Examples of improved strategies
  - **Acceptance**: At least 1/3 strategies have positive Sharpe (improvement from 0/3)
  - **Estimated time: 1 hour + iteration**

- [ ] 9.10 Implement Template-Based Strategy Generation (Reliable Foundation)
  - **Context**: LLM-based generation (qwen2.5-coder:7b) produces unreliable strategies with poor validation pass rates and unprofitable results
  - **Goal**: Replace LLM approach with proven template-based generation that guarantees valid, profitable strategies
  - _Requirements: 16.1, 16.3, 16.4, 21.1, 21.2, 23.1_
  - **Estimated time: 6-8 hours**

- [x] 9.10.1 Create Strategy Template Library
  - Create `StrategyTemplateLibrary` class in `src/strategy/strategy_templates.py`
  - Define proven strategy templates for each market regime:
    - **Mean Reversion Templates** (for RANGING markets):
      - RSI Oversold/Overbought: Entry when RSI < 30, exit when RSI > 70
      - Bollinger Band Bounce: Entry at lower band, exit at middle/upper band
      - Stochastic Mean Reversion: Entry when STOCH < 20, exit when STOCH > 80
    - **Trend Following Templates** (for TRENDING markets):
      - Moving Average Crossover: Entry on SMA_20 > SMA_50, exit on crossover down
      - MACD Momentum: Entry on MACD crossover above signal, exit on crossover below
      - Breakout: Entry on price > 20-day high, exit on price < 20-day low
    - **Volatility Templates** (for HIGH_VOLATILITY markets):
      - ATR Breakout: Entry on price move > 2*ATR, exit on reversion
      - Bollinger Breakout: Entry on price > upper band, exit on return to middle
  - Each template includes:
    - Template name and description
    - Market regime suitability
    - Entry conditions (list of rules)
    - Exit conditions (list of rules)
    - Required indicators with exact names
    - Default parameters (periods, thresholds)
    - Expected characteristics (trade frequency, holding period)
  - Implement `get_templates_for_regime()` method to filter by market regime
  - **Acceptance**: Library contains 8-10 proven strategy templates
  - **Estimated time: 2-3 hours**

- [x] 9.10.2 Implement Template-Based Strategy Generator
  - Update `StrategyProposer` to use template-based generation:
    - Remove all LLM calls for strategy generation
    - Implement `generate_from_template()` method:
      - Select appropriate templates for current market regime
      - **Use MarketStatisticsAnalyzer (Task 9.9.1) to get market data**:
        - Fetch volatility metrics (from Yahoo Finance + Alpha Vantage)
        - Fetch trend metrics (from Yahoo Finance)
        - Fetch indicator distributions (RSI, STOCH from Alpha Vantage or local calc)
        - Fetch market context (VIX, rates from FRED)
      - Customize template parameters based on market statistics:
        - Adjust RSI thresholds based on historical distribution (from Alpha Vantage/local)
        - Adjust Bollinger Band periods based on volatility (from Yahoo Finance)
        - Adjust moving average periods based on trend strength (from Yahoo Finance)
      - Create Strategy object with exact indicator names
      - Validate strategy rules match available indicators
  - Implement `customize_template_parameters()` method:
    - **Call MarketStatisticsAnalyzer.analyze_symbol()** for comprehensive market data
    - **Call MarketStatisticsAnalyzer.analyze_indicator_distributions()** for indicator stats
    - Adjust thresholds to match current market conditions
    - Example: If RSI < 30 occurs 5% of time (from Alpha Vantage), use RSI < 35 for more signals
    - Example: If volatility is high (from Yahoo Finance), widen Bollinger Bands
    - Example: If VIX > 20 (from FRED), use more conservative thresholds
  - Add parameter variation to create multiple strategies from same template:
    - Vary RSI thresholds (25/75, 30/70, 35/65) based on distribution
    - Vary moving average periods (10/30, 20/50, 30/90) based on trend strength
    - Vary Bollinger Band parameters (20,2 vs 20,2.5 vs 30,2) based on volatility
  - **Acceptance**: Generates valid strategies without LLM, customized to market conditions using multi-source data
  - **Estimated time: 2-3 hours**

- [ ] 9.10.3 Add Template Validation and Quality Scoring
  - Implement `validate_template_strategy()` method in StrategyProposer:
    - Verify all indicators referenced in rules are calculated
    - Verify entry/exit conditions are logically sound
    - Run quick signal generation test (30 days)
    - Verify minimum signal frequency (at least 3 entry signals in 30 days)
    - Verify low signal overlap (< 40%)
  - Implement `score_template_strategy()` method:
    - Score based on expected trade frequency (2-4 trades/month = optimal)
    - Score based on indicator diversity (2-3 indicators = optimal)
    - Score based on market regime match (higher for regime-appropriate templates)
    - Score based on recent template performance (from PerformanceTracker)
  - Filter strategies to only keep those with quality score > 0.6
  - **Acceptance**: Only high-quality template strategies are proposed
  - **Estimated time: 1-2 hours**

- [x] 9.10.4 Test Template-Based Generation and Measure Improvement
  - Run autonomous cycle with template-based generation
  - Compare to LLM-based baseline (task 9.9 results):
    - LLM Baseline: 0-1/3 strategies profitable, high failure rate, qwen2.5-coder:7b issues
    - Template Target: 2-3/3 strategies profitable, 100% validation pass rate
  - Verify template generation:
    - Check all strategies pass validation (no indicator errors)
    - Verify strategies generate meaningful signals (> 3 trades in 90 days)
    - Verify low signal overlap (< 40%)
    - Verify at least 2/3 strategies have positive Sharpe
    - Verify strategies match market regime
  - **Verify market data integration**:
    - Check MarketStatisticsAnalyzer is called for each symbol
    - Verify data from Yahoo Finance (OHLCV, volatility)
    - Verify data from Alpha Vantage (pre-calculated indicators, if available)
    - Verify data from FRED (VIX, treasury yields, if available)
    - Verify parameter customization uses actual market statistics
    - Example: RSI thresholds adjusted based on actual distribution
    - Example: Bollinger periods adjusted based on actual volatility
  - Document improvements in `TASK_9.10_RESULTS.md`:
    - Validation pass rate (should be 100%)
    - Strategy quality scores
    - Sharpe ratio distribution
    - Trade counts and signal quality
    - Market data sources used (Yahoo/Alpha Vantage/FRED)
    - Parameter customization examples
    - Comparison to LLM baseline
  - **Acceptance**: At least 2/3 strategies profitable, 100% validation pass rate, market data integration working
  - **Estimated time: 1 hour + iteration**

- [ ] 9.11 Implement Walk-Forward Validation and Portfolio Risk Management
  - **Context**: Improve strategy selection with out-of-sample validation and portfolio-level risk management
  - **Goal**: Only select strategies that work out-of-sample, optimize portfolio allocations for risk-adjusted returns
  - _Requirements: 17.1, 17.5, 20.1, 20.2, 20.3_
  - **Estimated time: 4-6 hours**

- [x] 9.11.1 Implement Walk-Forward Validation
  - Implement `walk_forward_validate()` method in StrategyEngine:
    - Split data into train/test periods
      - Train period: 60 days
      - Test period: 30 days
    - Backtest on train period
    - Validate on test period (out-of-sample)
    - Return both train and test Sharpe ratios
  - Update `StrategyProposer.propose_strategies()` to use walk-forward validation:
    - Generate 2-3x the requested count using templates
    - Run walk-forward validation on all candidates
    - Require Sharpe > 0.5 on both train AND test periods
    - Select best N strategies by combined train+test Sharpe
  - Implement `select_diverse_strategies()` method:
    - Calculate correlation between strategy returns
    - Select strategies with low correlation (< 0.7)
    - Prefer different strategy types (mean reversion, momentum, breakout)
    - Prefer different indicator combinations
  - Add logging for train vs test performance and diversity metrics
  - **Acceptance**: Only strategies that work out-of-sample are selected, with low correlation
  - **Estimated time: 2-3 hours**

- [x] 9.11.2 Add Portfolio-Level Risk Management
  - Create `PortfolioRiskManager` class in `src/strategy/portfolio_risk.py`
  - Implement `calculate_portfolio_metrics()`:
    - Portfolio Sharpe ratio (weighted average)
    - Portfolio max drawdown (combined equity curve)
    - Strategy correlation matrix
    - Diversification score (1 - avg correlation)
  - Implement `optimize_allocations()`:
    - Start with equal weight allocation
    - Adjust based on individual Sharpe ratios
    - Reduce allocation to highly correlated strategies
    - Ensure no strategy > 20% of portfolio
    - Ensure total allocation = 100%
  - Update `PortfolioManager` to use optimized allocations
  - **Acceptance**: Portfolio allocations optimized for risk-adjusted returns
  - **Estimated time: 1-2 hours**

- [ ] 9.11.3 Test Walk-Forward Validation and Portfolio Optimization
  - Run autonomous cycle with walk-forward validation and portfolio optimization
  - Verify walk-forward validation:
    - Strategies pass on both train and test periods
    - Test Sharpe within 20% of train Sharpe (not overfitted)
    - At least 60% of candidates pass walk-forward validation
  - Verify portfolio optimization:
    - Portfolio Sharpe > individual strategy Sharpes (diversification benefit)
    - Strategy correlation < 0.7
    - No strategy > 20% allocation
    - Total allocation = 100%
  - Compare to baseline (without walk-forward validation):
    - Baseline: Some strategies fail in live trading (overfitted)
    - With walk-forward: Strategies more robust, better live performance
  - Document results in `TASK_9.11_RESULTS.md`:
    - Walk-forward validation pass rate
    - Train vs test Sharpe comparison
    - Portfolio-level metrics
    - Correlation matrix
    - Allocation optimization results
  - **Acceptance**: Walk-forward validation reduces overfitting, portfolio optimization improves risk-adjusted returns
  - **Estimated time: 1 hour + iteration**

- [ ] 9.11.4 Implement Trading Rule DSL (Domain-Specific Language)
  - **Context**: LLM-based rule interpretation generates incorrect trading logic (e.g., "RSI_14 > 70" becomes "data['close'] > indicators['RSI_14']"), causing conflicting signals and poor results
  - **Goal**: Replace LLM with a proper trading DSL (similar to Pine Script/MQL) that's deterministic, extensible, and industry-standard
  - _Requirements: 1.1, 1.2, 5.1, 5.2, 8.1, 8.2_
  - **Why DSL over Templates**:
    1. Industry standard approach (TradingView, MetaTrader, QuantConnect all use DSLs)
    2. More maintainable and extensible than regex patterns
    3. Better error messages and validation
    4. Can add features like variables, functions later
    5. Traders understand DSL syntax naturally
  - **Estimated time: 6-8 hours**

- [x] 9.11.4.1 Define Trading DSL Grammar and Install Parser
  - Install `lark` parser library: `pip install lark`
  - Create `src/strategy/trading_dsl.py` with DSL grammar definition
  - Define grammar using Lark's EBNF syntax:
    ```python
    grammar = """
    ?start: expression
    
    ?expression: or_expr
    
    ?or_expr: and_expr
        | or_expr "OR" and_expr -> or_op
    
    ?and_expr: comparison
        | and_expr "AND" comparison -> and_op
    
    ?comparison: indicator COMPARATOR value -> compare
        | indicator CROSSOVER indicator -> crossover
        | "(" expression ")"
    
    indicator: INDICATOR_NAME "(" [NUMBER ("," NUMBER)*] ")"
        | INDICATOR_NAME
        | "CLOSE" | "OPEN" | "HIGH" | "LOW" | "VOLUME"
    
    value: NUMBER
        | indicator
    
    COMPARATOR: ">" | "<" | ">=" | "<=" | "==" | "!="
    CROSSOVER: "CROSSES_ABOVE" | "CROSSES_BELOW"
    INDICATOR_NAME: /[A-Z_]+/
    NUMBER: /[0-9]+\.?[0-9]*/
    
    %import common.WS
    %ignore WS
    """
    ```
  - Supported DSL syntax:
    - Simple comparisons: `RSI(14) < 30`, `SMA(20) > CLOSE`
    - Crossovers: `SMA(20) CROSSES_ABOVE SMA(50)`
    - Compound: `RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2)`
    - Indicator-to-indicator: `SMA(20) > SMA(50)`
  - Create `TradingDSLParser` class that wraps Lark parser
  - Add method `parse(rule_text)` that returns AST
  - Add comprehensive error handling for syntax errors
  - **Acceptance**: DSL grammar defined, parser can parse valid rules into AST
  - **Estimated time: 2 hours**

- [x] 9.11.4.2 Implement DSL-to-Pandas Code Generator
  - Create `DSLCodeGenerator` class in `src/strategy/trading_dsl.py`
  - Implement AST visitor that converts DSL to pandas code:
    - **Indicator nodes**: 
      - `RSI(14)` → `indicators['RSI_14']`
      - `SMA(20)` → `indicators['SMA_20']`
      - `BB_LOWER(20, 2)` → `indicators['Lower_Band_20']`
      - `CLOSE` → `data['close']`
    - **Comparison nodes**:
      - `RSI(14) < 30` → `indicators['RSI_14'] < 30`
      - `CLOSE > SMA(20)` → `data['close'] > indicators['SMA_20']`
    - **Crossover nodes**:
      - `SMA(20) CROSSES_ABOVE SMA(50)` → `(indicators['SMA_20'] > indicators['SMA_50']) & (indicators['SMA_20'].shift(1) <= indicators['SMA_50'].shift(1))`
    - **Logical nodes**:
      - `A AND B` → `(A) & (B)`
      - `A OR B` → `(A) | (B)`
  - Implement `generate_code(ast)` method that returns pandas expression string
  - Add indicator name mapping:
    - Map DSL indicator names to actual indicator keys
    - Handle multi-output indicators (Bollinger Bands → Upper/Middle/Lower)
    - Validate indicator exists before generating code
  - Add code validation:
    - Check all referenced indicators are available
    - Check operators are valid
    - Check thresholds are numeric
    - Return validation errors if any
  - **Acceptance**: DSL AST is converted to correct pandas code
  - **Estimated time: 2-3 hours**

- [x] 9.11.4.3 Integrate DSL Parser into StrategyEngine
  - Update `StrategyEngine._parse_strategy_rules()` to use DSL parser:
    - Remove all LLM calls for rule interpretation
    - For each rule text, call `TradingDSLParser.parse(rule_text)`
    - If parse succeeds, call `DSLCodeGenerator.generate_code(ast)`
    - If parse fails, log error and skip rule (don't use LLM fallback)
    - Execute generated pandas code with safe namespace
  - Add semantic validation (from Task 9.8.1):
    - RSI entry must use < 35 (not < 70)
    - RSI exit must use > 65 (not > 30)
    - Bollinger entry at lower band must use < Lower_Band
    - Bollinger exit at upper band must use > Upper_Band
    - Entry and exit must use different thresholds
  - Add signal overlap validation:
    - Calculate overlap percentage between entry/exit signals
    - Reject if > 80% overlap
    - Warn if 50-80% overlap
  - Add comprehensive logging:
    - Log original DSL rule text
    - Log parsed AST structure
    - Log generated pandas code
    - Log validation results
    - Log execution results (signal counts)
  - **Acceptance**: StrategyEngine uses DSL parser instead of LLM, generates correct code
  - **Estimated time: 1-2 hours**

- [x] 9.11.4.4 Update Strategy Templates to Use DSL Syntax
  - Update `StrategyTemplateLibrary` (Task 9.10.1) to use DSL syntax:
    - **RSI Mean Reversion**:
      - Entry: `RSI(14) < 30`
      - Exit: `RSI(14) > 70`
    - **Bollinger Band Bounce**:
      - Entry: `CLOSE < BB_LOWER(20, 2)`
      - Exit: `CLOSE > BB_UPPER(20, 2)`
    - **SMA Crossover**:
      - Entry: `SMA(20) CROSSES_ABOVE SMA(50)`
      - Exit: `SMA(20) CROSSES_BELOW SMA(50)`
    - **MACD Momentum**:
      - Entry: `MACD() CROSSES_ABOVE MACD_SIGNAL()`
      - Exit: `MACD() CROSSES_BELOW MACD_SIGNAL()`
  - Update template generation to output DSL syntax
  - Update LLM prompts (if still used) to generate DSL syntax:
    - Add DSL syntax examples to prompts
    - Add instruction: "Use DSL syntax: RSI(14) < 30, not natural language"
  - **Acceptance**: All templates use DSL syntax, LLM generates DSL if used
  - **Estimated time: 1 hour**

- [x] 9.11.4.5 Test DSL Implementation with Real Strategies
  - Create test file `test_trading_dsl.py`
  - Check how previous e2e tests initialised clients, market data, api, services, etc.
  - Test DSL parser with all rule types:
    - Simple comparisons: `RSI(14) < 30`, `SMA(20) > CLOSE`
    - Crossovers: `SMA(20) CROSSES_ABOVE SMA(50)`
    - Compound: `RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2)`
    - Indicator-to-indicator: `SMA(20) > SMA(50)`
  - Test code generation:
    - Verify correct pandas code generated for each rule type
    - Verify indicator name mapping works
    - Verify validation catches errors
  - Test with real strategies from test_portfolio_risk_with_real_data.py:
    - RSI Mean Reversion: Entry `RSI(14) < 30`, Exit `RSI(14) > 70`
    - SMA Crossover: Entry `SMA(20) CROSSES_ABOVE SMA(50)`, Exit `SMA(20) CROSSES_BELOW SMA(50)`
    - Bollinger Bands: Entry `CLOSE < BB_LOWER(20, 2)`, Exit `CLOSE > BB_UPPER(20, 2)`
  - Run full backtest with DSL-based strategies
  - Verify improvements over LLM-based parsing:
    - ✅ 100% correct code generation (no reversed conditions)
    - ✅ No wrong operand comparisons
    - ✅ Entry and exit conditions are different
    - ✅ Strategies generate meaningful trades (>1 trade)
    - ✅ Backtest results make sense (positive Sharpe for mean reversion in ranging market)
    - ✅ Better error messages when rules are invalid
  - Document results in `TASK_9.11.4_RESULTS.md`:
    - DSL syntax examples
    - Comparison to LLM-based parsing (before/after)
    - Rule parsing accuracy (100% vs previous errors)
    - Strategy quality improvements
    - Trade count improvements
    - Sharpe ratio improvements
    - Example DSL rules and generated code
  - **Acceptance**: DSL generates 100% correct code, strategies produce meaningful results, better than LLM
  - **Estimated time: 1-2 hours**

- [ ] 9.11.5 Strategy Quality Improvements (Critical Performance Fixes)
  - **Context**: Current system generates strategies with poor performance (Sharpe 0.12, 93% overfitting, 0.24% return)
  - **Goal**: Implement comprehensive improvements to generate profitable, robust strategies
  - _Requirements: 16.1, 16.3, 17.1, 17.5, 20.1, 23.1_
  - **Estimated time: 12-16 hours**

- [x] 9.11.5.1 Review and Improve Strategy Templates
  - **Context**: Current templates produce strategies with terrible risk/reward (0.24% return, -4.25% drawdown)
  - Audit all strategy templates in `StrategyTemplateLibrary`:
    - Review parameter ranges (RSI thresholds, MA periods, Bollinger bands)
    - Ensure entry/exit logic is sound (not reversed or conflicting)
    - Add stop-loss and take-profit levels to templates
    - Adjust thresholds based on historical market data
  - Improve RSI Mean Reversion template:
    - Entry: RSI < 25 (more extreme oversold)
    - Exit: RSI > 75 OR 5% profit OR 2% stop-loss
    - Add position sizing based on volatility
  - Improve Bollinger Band template:
    - Entry: Price < Lower Band AND RSI < 40
    - Exit: Price > Middle Band OR 3% profit OR 2% stop-loss
    - Widen bands in high volatility (2.5 std instead of 2.0)
  - Improve Moving Average Crossover:
    - Add trend filter (only trade in direction of 200-day MA)
    - Add volume confirmation (volume > 20-day average)
    - Exit on opposite crossover OR 5% profit OR 3% stop-loss
  - Test each template individually with 90-day backtest
  - Target: Each template should achieve Sharpe > 0.5 individually
  - **Acceptance**: Templates produce strategies with Sharpe > 0.5, positive returns, reasonable drawdowns
  - **Estimated time: 3-4 hours**

- [x] 9.11.5.2 Add More Diverse Strategy Types
  - **Context**: Only 3 strategy types (mean reversion, momentum, volatility) - need more diversity
  - Add new strategy templates:
    - **Momentum Strategies**:
      - Price Momentum: Entry on 20-day high, exit on 10-day low
      - MACD Momentum: Entry on MACD > signal AND rising, exit on MACD < signal
      - ADX Trend: Entry when ADX > 25 AND price > SMA(50), exit when ADX < 20
    - **Mean Reversion Strategies**:
      - Stochastic Oversold: Entry when STOCH < 20, exit when STOCH > 80
      - RSI Divergence: Entry on bullish divergence (price lower, RSI higher)
      - Z-Score Reversion: Entry when (price - SMA) / std > 2
    - **Volatility Strategies**:
      - ATR Breakout: Entry on price move > 2*ATR from 20-day MA
      - Bollinger Squeeze: Entry when bands narrow then expand
      - VIX-based: Adjust position size based on VIX level
  - Each template should have:
    - Clear entry/exit rules in DSL syntax
    - Stop-loss and take-profit levels
    - Position sizing rules
    - Expected trade frequency and holding period
  - Test each new template with 90-day backtest
  - **Acceptance**: 8-10 diverse strategy templates, each with Sharpe > 0.3
  - **Estimated time: 3-4 hours**

- [x] 9.11.5.3 Lower Sharpe Threshold and Add Tiered Activation
  - **Context**: Current threshold (Sharpe > 1.5) is too high - nothing gets activated
  - use this test file test_e2e_autonomous_system.py as example for creating tests to initialise clients, apis, market data, etc
  - Implement tiered activation system in `PortfolioManager`:
    - **Tier 1 (High Confidence)**: Sharpe > 1.0, max 30% allocation
    - **Tier 2 (Medium Confidence)**: Sharpe 0.5-1.0, max 15% allocation
    - **Tier 3 (Low Confidence)**: Sharpe 0.3-0.5, max 10% allocation
    - Reject: Sharpe < 0.3
  - Update activation criteria:
    - Remove hard Sharpe > 1.5 requirement
    - Use tiered system for allocation
    - Require: win_rate > 0.45, max_drawdown < 0.20, trades > 10
    - Prefer strategies with low correlation to existing portfolio
  - Add confidence scoring:
    - Score based on: Sharpe, win rate, trade count, walk-forward consistency
    - Higher confidence = higher allocation
  - Update retirement criteria:
    - Retire if Sharpe < 0.2 (30+ trades)
    - Retire if drawdown > 0.25
    - Retire if win_rate < 0.35 (50+ trades)
  - **Acceptance**: Strategies with Sharpe > 0.3 can be activated with appropriate allocation
  - **Estimated time: 2 hours**

- [x] 9.11.5.4 Increase Lookback Period for Backtesting
  - **Context**: 90 days is too short - need more data for robust testing
  - use this test file test_e2e_autonomous_system.py as example for creating tests to initialise clients, apis, market data, etc
  - **Data Source Limits (Free Tier)**:
    - Yahoo Finance (current): **Unlimited years** of daily data, 2000 requests/hour - PRIMARY SOURCE
    - Alpha Vantage: 20+ years available but only **25 API calls/day** - TOO RESTRICTIVE for backtesting
    - FRED: Decades of data, **unlimited calls** - GOOD for macro indicators (VIX, rates)
    - eToro: Real-time only, falls back to Yahoo Finance for historical
  - **Recommendation**: Use Yahoo Finance as primary source (already implemented)
    - Can fetch **1-2 years** of data without issues
    - Free, unlimited history, reliable
    - Already integrated in `get_historical_data()`
  - Update backtest configuration in `config/autonomous_trading.yaml`:
    - Increase backtest period from 90 to **365 days (1 year)**
    - Increase warmup period from 100 to **200 days**
    - Update walk-forward validation: train=**240 days (8 months)**, test=**120 days (4 months)**
    - Total data needed: 365 + 200 = **565 days (~1.5 years)** - well within Yahoo Finance limits
  - Update `StrategyEngine.backtest_strategy()`:
    - Fetch 365 days of data (+ 200 warmup = 565 days total)
    - Run backtest on full 365-day period
    - Ensure sufficient data for all indicators (200-day MA needs 200+ days warmup)
  - Update validation requirements:
    - Require minimum 30 trades in 365 days (not 20 in 90)
    - Adjust trade frequency expectations (2-3 trades/month)
  - Add data quality checks:
    - Verify Yahoo Finance returns full 565 days
    - Log warning if less than 500 days available
    - Fallback to 180 days if symbol has limited history
  - **Acceptance**: Backtests use 365 days of data (1 year), more robust results, Yahoo Finance as reliable free source
  - **Estimated time: 1-2 hours**

- [x] 9.11.5.5 Implement Parameter Optimization Within Templates
  - **Context**: Fixed parameters don't adapt to market conditions
  - Create `ParameterOptimizer` class in `src/strategy/parameter_optimizer.py`
  - use this test file test_e2e_autonomous_system.py as example for creating tests to initialise clients, apis, market data, etc
  - Implement grid search optimization:
    - For RSI: Test thresholds [20, 25, 30] x [70, 75, 80]
    - For MA periods: Test [10, 20, 30] x [30, 50, 90]
    - For Bollinger: Test periods [15, 20, 25] x std [1.5, 2.0, 2.5]
  - Optimization process:
    - Run backtest for each parameter combination
    - Select combination with highest Sharpe ratio
    - Validate on out-of-sample data (walk-forward)
    - Only use if out-of-sample Sharpe > 0.3
  - Add to `StrategyProposer.generate_from_template()`:
    - Call `ParameterOptimizer.optimize()` for each template
    - Use optimized parameters instead of defaults
    - Log optimization results (best params, Sharpe improvement)
  - Add overfitting protection:
    - Limit parameter combinations to avoid overfitting
    - Require out-of-sample validation
    - Penalize complex parameter sets
  - **Acceptance**: Templates use optimized parameters, better performance than defaults
  - **Estimated time: 3-4 hours**

- [x] 9.11.5.6 Add Regime-Specific Templates
  - **Context**: One-size-fits-all templates don't work in all market conditions
  - use this test file test_e2e_autonomous_system.py as example for creating tests to initialise clients, apis, market data, etc
  - Enhance `MarketStatisticsAnalyzer` to detect sub-regimes:
    - **Trending Up**: Strong uptrend (20d change > 5%, 50d change > 10%)
    - **Trending Up (Weak)**: Weak uptrend (20d change 2-5%, 50d change 5-10%)
    - **Trending Down**: Strong downtrend (20d change < -5%, 50d change < -10%)
    - **Trending Down (Weak)**: Weak downtrend (20d change -5% to -2%, 50d change -10% to -5%)
    - **Ranging (Low Vol)**: Sideways, low volatility (ATR/price < 2%)
    - **Ranging (High Vol)**: Sideways, high volatility (ATR/price > 3%)
  - Create regime-specific template variations:
    - **Strong Uptrend**: Momentum strategies (MACD, breakout, trend following)
    - **Weak Uptrend**: Pullback strategies (buy dips to MA, RSI oversold in uptrend)
    - **Strong Downtrend**: Short strategies or cash (avoid longs)
    - **Weak Downtrend**: Bounce strategies (oversold bounces, support levels)
    - **Low Vol Ranging**: Mean reversion (RSI, Bollinger, stochastic)
    - **High Vol Ranging**: Volatility strategies (ATR breakout, Bollinger squeeze)
  - Update `StrategyProposer` to select templates based on sub-regime
  - **Acceptance**: Different templates used for different market conditions, better regime matching
  - **Estimated time: 2-3 hours**

- [x] 9.11.5.7 Add Transaction Costs and Slippage to Backtests
  - **Context**: Current backtests don't account for real trading costs
  - use this test file test_e2e_autonomous_system.py as example for creating tests to initialise clients, apis, market data, etc
  - Update `StrategyEngine.backtest_strategy()` to include:
    - **Commission**: $0.005 per share (or 0.1% of trade value)
    - **Slippage**: 0.05% on entry, 0.05% on exit (market impact)
    - **Spread**: Bid-ask spread (0.02% for liquid stocks)
  - Add to backtest configuration:
    ```yaml
    backtest:
      transaction_costs:
        commission_per_share: 0.005
        commission_percent: 0.001  # 0.1%
        slippage_percent: 0.0005   # 0.05%
        spread_percent: 0.0002     # 0.02%
    ```
  - Update trade execution logic:
    - Entry price = close * (1 + slippage + spread/2) + commission
    - Exit price = close * (1 - slippage - spread/2) - commission
    - Adjust returns and Sharpe calculations
  - Add cost analysis to backtest results:
    - Total costs paid
    - Costs as % of returns
    - Net returns after costs
  - **Acceptance**: Backtests include realistic transaction costs, more accurate performance
  - **Estimated time: 2 hours**

- [x] 9.11.5.8 Enhance FRED Integration for Macro-Aware Strategy Generation
  - **Context**: FRED data (VIX, Treasury yields) is fetched but barely used - only VIX for minor threshold tweaks
  - use this test file test_e2e_autonomous_system.py as example for creating tests to initialise clients, apis, market data, etc
  - **Current Usage**: VIX > 25 → adjust RSI thresholds by ±5 (that's it!)
  - **Goal**: Leverage FRED data for intelligent strategy selection, position sizing, and risk management
  - **Estimated time: 3-4 hours**
  
  **Part 1: Expand FRED Data Collection** (1 hour)
  - Add more economic indicators to `MarketStatisticsAnalyzer.get_market_context()`:
    - **Unemployment Rate** (UNRATE): Labor market health
    - **Fed Funds Rate** (FEDFUNDS): Monetary policy stance
    - **Inflation** (CPIAUCSL): Price stability indicator
    - **S&P 500 PE Ratio** (MULTPL/SP500_PE_RATIO_MONTH): Valuation metric
  - Calculate composite macro regime:
    - **Risk-On**: VIX < 15, unemployment falling, Fed accommodative
    - **Risk-Off**: VIX > 25, unemployment rising, Fed tightening
    - **Transitional**: Mixed signals
  - Cache all indicators for 24 hours (FRED updates daily)
  - **Acceptance**: System fetches 6 macro indicators from FRED, calculates composite regime
  
  **Part 2: Strategy Filtering Based on Macro Regime** (1 hour)
  - Update `StrategyProposer.propose_strategies()` to filter templates by macro regime:
    - **Risk-Off (VIX > 30)**:
      - ❌ Disable momentum/breakout strategies (too risky)
      - ✅ Favor mean reversion and defensive strategies
      - ✅ Reduce strategy count (3 → 2)
    - **Risk-On (VIX < 15)**:
      - ✅ Enable all strategy types
      - ✅ Favor momentum and trend-following
      - ✅ Increase strategy count (3 → 4)
    - **High Inflation (CPI > 5%)**:
      - ✅ Favor commodity-linked strategies
      - ❌ Avoid long-duration strategies
  - Add macro regime to strategy metadata for tracking
  - Log strategy filtering decisions
  - **Acceptance**: Strategy selection adapts to macro conditions, fewer risky strategies in risk-off
  
  **Part 3: Position Sizing Based on VIX** (30 min)
  - Update `PortfolioManager` to adjust position sizes based on VIX:
    - **VIX < 15** (Low fear): 100% of normal position size
    - **VIX 15-20** (Moderate): 75% of normal position size
    - **VIX 20-25** (Elevated): 50% of normal position size
    - **VIX > 25** (High fear): 25% of normal position size
  - Apply VIX adjustment to all new positions
  - Log position size adjustments
  - **Acceptance**: Position sizes scale down as VIX increases, reducing risk exposure
  
  **Part 4: Activation Thresholds Based on Macro Regime** (30 min)
  - Update `PortfolioManager.evaluate_for_activation()` to adjust thresholds:
    - **Risk-Off (VIX > 25)**:
      - Require Sharpe > 0.7 (higher bar, vs 0.5 in normal)
      - Require win_rate > 0.50 (vs 0.45)
      - Require max_drawdown < 0.15 (vs 0.20)
    - **Risk-On (VIX < 15)**:
      - Allow Sharpe > 0.3 (lower bar, easier to activate)
      - Allow win_rate > 0.40
      - Allow max_drawdown < 0.25
  - Log threshold adjustments based on regime
  - **Acceptance**: Activation criteria adapt to market conditions, stricter in risk-off
  
  **Part 5: Enhanced Parameter Customization** (30 min)
  - Update `customize_template_parameters()` to use all FRED data:
    - **Treasury Yields Rising** (10Y > 4.5%):
      - Tighten stop-losses (reduce holding periods)
      - Favor shorter-term strategies
    - **Unemployment Rising**:
      - More conservative entry thresholds
      - Wider stop-losses (avoid whipsaws)
    - **Fed Tightening** (Fed Funds > 5%):
      - Reduce leverage/position sizes
      - Favor defensive sectors
  - Currently only uses VIX - expand to use all indicators
  - **Acceptance**: Parameter customization considers full macro picture, not just VIX
  
  **Part 6: Test and Measure Impact** (30 min)
  - Run autonomous cycle with enhanced FRED integration
  - Compare to baseline (current minimal FRED usage):
    - **Baseline**: Only VIX for threshold tweaks
    - **Enhanced**: Full macro-aware strategy selection and risk management
  - Verify improvements:
    - ✅ Strategy mix changes based on VIX (fewer momentum in risk-off)
    - ✅ Position sizes scale with VIX
    - ✅ Activation thresholds adapt to regime
    - ✅ Parameters consider full macro context
    - ✅ System avoids risky strategies in risk-off environments
  - Document results in `TASK_9.11.5.8_FRED_ENHANCEMENT.md`:
    - Macro regime detection accuracy
    - Strategy filtering decisions
    - Position sizing adjustments
    - Activation threshold changes
    - Risk reduction in high-VIX periods
  - **Acceptance**: System demonstrates macro-aware behavior, reduces risk in adverse conditions
  - **Estimated time: 3-4 hours total**

- [x] 9.11.5.9 Implement Stop-Loss and Take-Profit in Backtests (CRITICAL)
  - **Context**: Backtests don't simulate stop-loss/take-profit - results are unrealistic
  - **Current**: Only uses entry/exit signals from strategy rules, no risk management
  - **Impact**: Strategies look profitable in backtest but will fail in live trading with stops
  - **Goal**: Add realistic stop-loss and take-profit simulation to backtests
  - **Estimated time: 2-3 hours**
  - use this test file test_e2e_autonomous_system.py as example for creating tests to initialise clients, apis, market data, etc
  
  **Part 1: Add Stop-Loss/Take-Profit to Strategy Templates** (30 min)
  - Update `StrategyTemplate` class to include:
    - `stop_loss_pct`: Percentage stop-loss (e.g., 0.02 = 2%)
    - `take_profit_pct`: Percentage take-profit (e.g., 0.05 = 5%)
    - `trailing_stop`: Boolean for trailing stop-loss
  - Update all templates with reasonable defaults:
    - Mean reversion: stop_loss=2%, take_profit=3%
    - Momentum: stop_loss=3%, take_profit=5%
    - Volatility: stop_loss=4%, take_profit=6%
  - **Acceptance**: All templates have stop-loss and take-profit parameters
  
  **Part 2: Implement Stop-Loss/Take-Profit in Vectorbt Backtest** (1.5 hours)
  - Update `_run_vectorbt_backtest()` to use vectorbt's stop-loss/take-profit:
    ```python
    portfolio = vbt.Portfolio.from_signals(
        close,
        entries,
        exits,
        init_cash=100000,
        fees=0.001,
        sl_stop=strategy.risk_params.stop_loss_pct,  # Stop-loss
        tp_stop=strategy.risk_params.take_profit_pct,  # Take-profit
        freq="1D"
    )
    ```
  - Add trailing stop-loss support if template specifies it
  - Log stop-loss and take-profit hits separately from rule-based exits
  - Calculate metrics:
    - % of trades stopped out
    - % of trades hitting take-profit
    - Average loss when stopped out
    - Average gain when hitting take-profit
  - **Acceptance**: Backtests simulate stop-loss and take-profit, metrics show hit rates
  
  **Part 3: Adjust Strategy Evaluation for Realistic Risk/Reward** (30 min)
  - Update activation criteria to account for stop-loss:
    - Require win_rate > 0.50 (since stops will reduce win rate)
    - Require avg_win > 2 * avg_loss (2:1 reward:risk minimum)
  - Update retirement criteria:
    - Retire if stop-loss hit rate > 60% (too many stops)
    - Retire if avg_loss > stop_loss_pct * 1.5 (stops not working)
  - **Acceptance**: Activation/retirement criteria account for stop-loss behavior
  
  **Part 4: Test and Compare Results** (30 min)
  - Run backtests with and without stop-loss/take-profit
  - Compare metrics:
    - Sharpe ratio (should be similar or better with stops)
    - Max drawdown (should be lower with stops)
    - Total trades (should be higher with stops)
    - Win rate (will be lower with stops, but avg_win should be better)
  - Document in `TASK_9.11.5.9_STOP_LOSS_RESULTS.md`:
    - Before/after comparison
    - Stop-loss hit rates
    - Take-profit hit rates
    - Risk/reward improvements
  - **Acceptance**: Backtests with stops show more realistic risk/reward profiles
  - **Estimated time: 2-3 hours total**

- [x] 9.11.5.10 Implement Position Sizing Based on Volatility
  - **Context**: All positions are same size regardless of volatility or risk
  - **Current**: Fixed position size, no risk-based sizing
  - **Goal**: Size positions based on volatility (ATR) and risk per trade
  - use this test file test_e2e_autonomous_system.py as example for creating tests to initialise clients, apis, market data, etc
  - **Estimated time: 2 hours**
  
  **Part 1: Add Position Sizing to Strategy Templates** (30 min)
  - Add position sizing parameters to templates:
    - `risk_per_trade_pct`: Max risk per trade (e.g., 0.01 = 1% of portfolio)
    - `sizing_method`: 'fixed', 'volatility', 'kelly'
  - Default to volatility-based sizing for all templates
  - **Acceptance**: Templates specify position sizing method
  
  **Part 2: Implement Volatility-Based Position Sizing** (1 hour)
  - Create `calculate_position_size()` method in `PortfolioManager`:
    ```python
    def calculate_position_size(
        self,
        portfolio_value: float,
        entry_price: float,
        stop_loss_pct: float,
        risk_per_trade_pct: float,
        atr: float
    ) -> float:
        # Position size = (Portfolio * Risk%) / (Entry * Stop%)
        # Adjusted by ATR for volatility
        risk_amount = portfolio_value * risk_per_trade_pct
        risk_per_share = entry_price * stop_loss_pct
        base_size = risk_amount / risk_per_share
        
        # Adjust for volatility (reduce size in high volatility)
        volatility_adjustment = 1.0 / (1.0 + atr / entry_price)
        adjusted_size = base_size * volatility_adjustment
        
        return adjusted_size
    ```
  - Use in backtests and live trading
  - **Acceptance**: Position sizes scale with volatility and risk parameters
  
  **Part 3: Update Backtests to Use Dynamic Position Sizing** (30 min)
  - Modify `_run_vectorbt_backtest()` to calculate position size per trade
  - Use vectorbt's `size` parameter with dynamic sizing
  - Log position sizes for analysis
  - **Acceptance**: Backtests use volatility-based position sizing
  - **Estimated time: 2 hours total**

- [x] 9.11.5.11 Add Portfolio-Wide Risk Management
  - **Context**: No portfolio-level stop-loss or exposure limits
  - use this test file test_e2e_autonomous_system.py as example for creating tests to initialise clients, apis, market data, etc
  - **Goal**: Implement portfolio-wide risk controls
  - **Estimated time: 1.5 hours**
  
  **Part 1: Portfolio Stop-Loss** (30 min)
  - Add to `PortfolioManager`:
    - `portfolio_stop_loss_pct`: Stop all trading if portfolio down X% (e.g., 10%)
    - `daily_loss_limit_pct`: Stop trading for day if down X% (e.g., 3%)
  - Check before each trade
  - Pause all strategies if triggered
  - **Acceptance**: Portfolio stops trading when loss limits hit
  
  **Part 2: Exposure Limits** (30 min)
  - Add exposure limits:
    - Max total exposure: 100% of portfolio (no leverage)
    - Max per-symbol exposure: 20% of portfolio
    - Max per-strategy exposure: 30% of portfolio
  - Reject trades that would exceed limits
  - **Acceptance**: Exposure limits prevent over-concentration
  
  **Part 3: Correlation-Based Position Limits** (30 min)
  - Calculate correlation between active strategies
  - Reduce position sizes if correlation > 0.7
  - Example: If 3 strategies all long SPY, reduce each to 50% size
  - **Acceptance**: Position sizes reduced for correlated strategies
  - **Estimated time: 1.5 hours total**

- [x] 9.11.5.12 Implement Strategy Correlation Deep Analysis
  - **Context**: Need comprehensive correlation analysis beyond basic pairwise correlation (partially addressed in 9.11.2)
  - use this test file test_e2e_autonomous_system.py as example for creating tests to initialise clients, apis, market data, etc
  - **Goal**: Implement deep correlation analysis to identify hidden relationships between strategies
  - **Estimated time: 2-3 hours**
  
  **Part 1: Multi-Dimensional Correlation Analysis** (1 hour)
  - Extend correlation analysis beyond returns:
    - Signal correlation: Do strategies enter/exit at same times?
    - Drawdown correlation: Do strategies lose money together?
    - Volatility correlation: Do strategies have similar volatility patterns?
  - Calculate correlation matrix for all dimensions
  - Store in database for historical tracking
  - **Acceptance**: System tracks 3+ types of correlation between strategies
  
  **Part 2: Correlation-Based Diversification Score** (1 hour)
  - Create diversification score for portfolio (0-1):
    - 1.0 = perfectly uncorrelated strategies
    - 0.0 = all strategies perfectly correlated
  - Factor in all correlation dimensions
  - Use score to guide strategy activation:
    - Prefer strategies that improve diversification
    - Reject strategies that increase correlation > 0.8
  - **Acceptance**: Portfolio diversification score calculated and used in activation decisions
  
  **Part 3: Correlation Monitoring and Alerts** (30 min)
  - Monitor correlation changes over time
  - Alert when correlation increases significantly (e.g., from 0.3 to 0.7)
  - Log correlation changes in strategy performance history
  - **Acceptance**: System detects and logs correlation regime changes
  - **Estimated time: 2-3 hours total**

- [x] 9.11.5.13 Implement Regime Change Detection During Live Trading
  - **Context**: Market regimes change during live trading, strategies need to adapt
  - **Goal**: Detect regime changes in real-time and adjust strategy behavior
  - use this test file test_e2e_autonomous_system.py as example for creating tests to initialise clients, apis, market data, etc
  - **Estimated time: 2-3 hours**
  
  **Part 1: Real-Time Regime Detection** (1 hour)
  - Implement `detect_regime_change()` in MarketStatisticsAnalyzer:
    - Calculate current regime indicators (volatility, trend, correlation)
    - Compare to regime at strategy activation
    - Detect significant changes (e.g., volatility doubles, trend reverses)
  - Run detection daily for all active strategies
  - Store regime history in database
  - **Acceptance**: System detects when market regime changes from activation baseline
  
  **Part 2: Regime-Based Strategy Adjustment** (1 hour)
  - Add regime change response logic:
    - If volatility increases >50%: Reduce position sizes by 30%
    - If trend reverses: Pause trend-following strategies
    - If correlation spikes: Reduce correlated strategy exposure
  - Log all regime-based adjustments
  - Add override flag for manual control
  - **Acceptance**: Strategies automatically adjust to regime changes
  
  **Part 3: Regime Change Retirement Trigger** (30 min)
  - Add regime change as retirement criterion:
    - If strategy designed for TRENDING but market becomes RANGING for 30+ days
    - If strategy designed for LOW_VOL but volatility increases 2x for 14+ days
  - More aggressive than performance-based retirement
  - **Acceptance**: Strategies retired when regime no longer suitable
  - **Estimated time: 2-3 hours total**

- [x] 9.11.5.14 Implement Performance Degradation Monitoring
  - **Context**: Need to detect when strategy performance degrades before major losses occur
  - **Goal**: Implement early warning system for strategy performance issues
  - use this test file test_e2e_autonomous_system.py as example for creating tests to initialise clients, apis, market data, etc
  - **Estimated time: 2-3 hours**
  
  **Part 1: Rolling Performance Metrics** (1 hour)
  - Calculate rolling metrics for active strategies:
    - 7-day rolling Sharpe ratio
    - 14-day rolling win rate
    - 30-day rolling max drawdown
  - Compare to backtest baseline
  - Store in time-series database for trending
  - **Acceptance**: System tracks rolling performance metrics vs baseline
  
  **Part 2: Degradation Detection Algorithm** (1 hour)
  - Implement degradation detection:
    - Sharpe drops >50% from baseline for 14+ days
    - Win rate drops >30% from baseline for 20+ trades
    - Drawdown exceeds backtest max drawdown by 50%
  - Calculate degradation severity score (0-1)
  - Trigger alerts at different severity levels
  - **Acceptance**: System detects performance degradation early
  
  **Part 3: Graduated Response to Degradation** (30 min)
  - Implement tiered response:
    - Severity 0.3-0.5: Reduce position size by 50%
    - Severity 0.5-0.7: Pause strategy, monitor for 7 days
    - Severity 0.7+: Retire strategy immediately
  - Log all degradation events and responses
  - Add manual override capability
  - **Acceptance**: System responds proportionally to degradation severity
  - **Estimated time: 2-3 hours total**

- [x] 9.11.5.15 Implement Ensemble/Meta-Strategies (Optional)
  - **Context**: Nice-to-have feature for combining multiple strategies intelligently
  - **Goal**: Create meta-strategies that dynamically allocate between underlying strategies
  - use this test file test_e2e_autonomous_system.py as example for creating tests to initialise clients, apis, market data, etc
  - **Estimated time: 4-6 hours**
  
  **Part 1: Meta-Strategy Framework** (2 hours)
  - Create `MetaStrategy` class that wraps multiple base strategies
  - Implement dynamic allocation logic:
    - Allocate more capital to strategies with recent strong performance
    - Reduce allocation to strategies showing degradation
    - Rebalance weekly based on rolling metrics
  - Track meta-strategy as separate entity in database
  - **Acceptance**: Meta-strategy can dynamically allocate between base strategies
  
  **Part 2: Ensemble Signal Aggregation** (2 hours)
  - Implement signal aggregation methods:
    - Voting: Enter if N of M strategies signal entry
    - Weighted: Weight signals by strategy Sharpe ratio
    - Confidence: Only enter if aggregate confidence > threshold
  - Test different aggregation methods
  - Compare ensemble performance to individual strategies
  - **Acceptance**: Ensemble strategies combine signals from multiple base strategies
  
  **Part 3: Meta-Strategy Backtesting** (1-2 hours)
  - Extend backtesting to support meta-strategies
  - Simulate dynamic allocation over time
  - Calculate meta-strategy metrics (Sharpe, drawdown, etc.)
  - Compare to equal-weight portfolio
  - **Acceptance**: Can backtest meta-strategies with dynamic allocation
  - **Estimated time: 4-6 hours total**

- [x] 9.11.5.16 Test All Improvements and Measure Impact
  - Run autonomous cycle with all improvements
  - use this test file test_e2e_autonomous_system.py as example for creating tests to initialise clients, apis, market data, etc
  - Compare to baseline (current results):
    - **Baseline**: Sharpe 0.12, Return 0.24%, Drawdown -4.25%, 4 trades, 93% overfitting
    - **Target**: Sharpe > 0.5, Return > 2%, Drawdown < -10%, 10+ trades, <30% overfitting
  - Verify each improvement:
    - ✅ Improved templates produce Sharpe > 0.5
    - ✅ Diverse strategy types (8-10 templates)
    - ✅ Tiered activation allows Sharpe > 0.3 strategies
    - ✅ 180-day backtests more robust
    - ✅ Parameter optimization improves performance
    - ✅ Regime-specific templates match market conditions
    - ✅ Transaction costs included, realistic returns
    - ✅ Correlation analysis improves diversification
    - ✅ Regime change detection prevents losses
    - ✅ Performance degradation monitoring catches issues early
  - Document results in `TASK_9.11.5_RESULTS.md`:
    - Before/after comparison for each metric
    - Strategy performance distribution
    - Activation rate (% of strategies activated)
    - Portfolio-level metrics
    - Cost impact analysis
    - Overfitting reduction
    - Correlation and diversification metrics
    - Regime change detection effectiveness
    - Degradation monitoring impact
  - **Acceptance**: At least 2/3 strategies have Sharpe > 0.5, portfolio Sharpe > 0.7, realistic returns, improved risk management
  - **Estimated time: 2-3 hours + iteration**

- [ ] 9.12 Implement Extended Backtesting and Robustness Improvements
  - **Context**: Current 1-year backtest period may not be sufficient to validate strategy robustness across different market conditions
  - **Goal**: Extend backtest period to 2-3 years and implement comprehensive out-of-sample testing
  - _Requirements: 17.1, 17.5, 23.1, 23.2_
  - **Estimated time: 4-6 hours**

- [x] 9.12.1 Extend Backtest Period to 2-3 Years
  - **Context**: Task 9.12.2 honest assessment identified need for longer backtest periods
  - Update `config/autonomous_trading.yaml`:
    - Increase backtest days from 365 to **730 days (2 years)**
    - Increase warmup days from 200 to **250 days** (for longer-period indicators)
    - Total data needed: 730 + 250 = **980 days (~2.7 years)**
  - Update `StrategyEngine.backtest_strategy()`:
    - Fetch 730 days of historical data (+ 250 warmup)
    - Verify Yahoo Finance can provide 980 days (should be fine, unlimited history)
    - Add fallback to 365 days if symbol has limited history
  - Update walk-forward validation periods:
    - Train period: **480 days (16 months)**
    - Test period: **240 days (8 months)**
    - This provides more robust out-of-sample validation
  - Update minimum trade requirements:
    - Require minimum **50 trades in 730 days** (3-4 trades/month)
    - Adjust activation criteria accordingly
  - Test with multiple symbols to verify data availability
  - **Acceptance**: Backtests use 2-year period with 250-day warmup, more robust validation
  - **Estimated time: 1-2 hours**

- [x] 9.12.2 Implement Multiple Out-of-Sample Test Periods
  - **Context**: Single walk-forward test may not catch all overfitting issues
  - Implement **rolling window validation** in `StrategyEngine`:
    - Split 2-year data into multiple train/test windows:
      - Window 1: Train on months 1-12, test on months 13-18
      - Window 2: Train on months 7-18, test on months 19-24
      - Window 3: Train on full 24 months, test on most recent 6 months
    - Strategy must pass ALL windows to be considered robust
    - Calculate consistency score: % of windows where Sharpe > 0.3
  - Add **different market regime testing**:
    - Identify bull/bear/sideways periods in historical data
    - Test strategy performance in each regime separately
    - Require positive Sharpe in at least 2 of 3 regimes
  - Update activation criteria:
    - Require consistency score > 60% (pass 2 of 3 windows)
    - Require positive performance in multiple regimes
    - Penalize strategies that only work in one regime
  - Add detailed reporting:
    - Performance by time window
    - Performance by market regime
    - Consistency metrics
    - Overfitting indicators (train vs test variance)
  - **Acceptance**: Strategies tested across multiple time periods and market regimes
  - **Estimated time: 2-3 hours**

- [x] 9.12.3 Enhance Walk-Forward Analysis with Adaptive Parameters
  - **Context**: Current walk-forward validation is static - parameters don't adapt
  - Implement **adaptive walk-forward analysis**:
    - Re-optimize parameters on each training window
    - Test optimized parameters on corresponding test window
    - Verify parameters remain stable across windows (not overfitted)
  - Add **parameter stability analysis**:
    - Track parameter values across windows
    - Calculate parameter variance
    - Reject strategies with high parameter variance (unstable)
  - Implement **regime-adaptive parameters**:
    - Detect regime in training window
    - Optimize parameters for that regime
    - Test if parameters work in test window with same regime
  - Add **degradation detection**:
    - Track performance degradation over time
    - Identify if strategy performance is declining
    - Reject strategies showing consistent degradation
  - Update reporting:
    - Parameter stability metrics
    - Performance trend analysis
    - Regime-specific performance
  - **Acceptance**: Walk-forward analysis adapts parameters and detects degradation
  - **Estimated time: 2-3 hours**

- [x] 9.12.4 Run Extended Backtest Suite and Provide Updated Assessment
  - Run full autonomous cycle with extended backtesting:
    - 2-year backtest period
    - Multiple out-of-sample windows
    - Adaptive walk-forward analysis
  - Compare to previous results (1-year backtest):
    - Strategy quality improvements
    - Overfitting reduction
    - Consistency across time periods
    - Regime-specific performance
  - Document results in `EXTENDED_BACKTEST_ASSESSMENT.md`:
    - Performance across all time windows
    - Consistency scores
    - Parameter stability
    - Regime-specific results
    - Comparison to 1-year baseline
  - **Honest assessment questions**:
    - Do strategies remain profitable across all windows?
    - Is overfitting reduced with longer backtest?
    - Do parameters remain stable?
    - Do strategies adapt to regime changes?
    - Are we ready for live trading?
  - **Acceptance**: Comprehensive assessment with 2-year backtests completed
  - **Estimated time: 1-2 hours + iteration**

- [ ] 9.13 Run Comprehensive E2E Test Suite and Provide Honest Feedback
  - **Context**: Verify all improvements work together end-to-end and assess production readiness
  - **Goal**: Run complete test suite, analyze results honestly, and determine if system is ready for real trading
  - _Requirements: 23.1, 23.2, 23.3, 23.4_
  - **Estimated time: 3-4 hours**

- [x] 9.13.1 Update E2E Test with New Features
  - Update `test_e2e_autonomous_system.py` to test:
    - Template-based generation
    - DSL rule parsing and code generation
    - Market statistics integration (parameter customization)
    - Walk-forward validation (train/test split)
    - Portfolio optimization (risk-adjusted allocations)
  - Add assertions for new metrics:
    - 100% validation pass rate (templates guarantee this)
    - 100% DSL parsing success rate (no LLM errors)
    - At least 2/3 strategies with Sharpe > 0
    - Portfolio Sharpe > 0.5
    - Strategy correlation < 0.7
    - Walk-forward validation pass rate > 60%
    - Test Sharpe within 20% of train Sharpe (not overfitted)
  - Add DSL-specific tests:
    - Test all DSL rule types (comparisons, crossovers, compound)
    - Verify correct pandas code generation
    - Verify semantic validation works (RSI thresholds, etc.)
    - Verify signal overlap detection
  - Add performance benchmarks:
    - Strategy generation time < 2 min
    - DSL parsing time < 100ms per rule
    - Backtest time < 2 min per strategy
    - Full cycle time < 20 min
  - **Acceptance**: E2E test covers all new features including DSL
  - **Estimated time: 1-2 hours**

- [x] 9.13.2 Run Full Test Suite and Provide Honest Assessment
  - Run complete test suite:
    - `test_e2e_autonomous_system.py` (main integration test)
    - `test_trading_dsl.py` (DSL parser and code generator tests)
    - `test_autonomous_strategy_manager.py` (unit tests)
    - `test_strategy_proposer.py` (strategy generation tests)
    - `test_portfolio_manager.py` (portfolio management tests)
  - Create comprehensive test report: `HONEST_ASSESSMENT_AFTER_FIXES.md`
  - **Honest Performance Analysis**:
    - Strategy quality metrics (Sharpe, returns, win rate, drawdown)
    - Trade frequency and holding periods
    - Overfitting analysis (train vs test performance)
    - Transaction cost impact
    - Portfolio-level metrics (diversification, correlation)
    - Activation rate (% of strategies meeting criteria)
  - **Comparison to Baseline** (before Task 9.11.5 improvements):
    - Baseline: Sharpe 0.12, Return 0.24%, Drawdown -4.25%, 4 trades, 93% overfitting
    - After fixes: Document actual results (no sugar-coating)
    - Calculate improvement percentages
  - **Critical Assessment**:
    - What's working well? (be specific)
    - What's still broken? (be honest)
    - Are strategies profitable enough for real trading?
    - Is overfitting under control?
    - Are transaction costs manageable?
    - Is the system generating enough good strategies?
  - **Production Readiness Evaluation**:
    - ✅ or ❌ Technical infrastructure (DSL, templates, backtesting)
    - ✅ or ❌ Strategy quality (profitable, robust, diverse)
    - ✅ or ❌ Risk management (drawdowns, position sizing, diversification)
    - ✅ or ❌ Performance (Sharpe > 0.5, positive returns, reasonable costs)
    - ✅ or ❌ Overfitting protection (walk-forward validation working)
  - **Recommendations**:
    - If ready: Document deployment plan
    - If not ready: List specific issues that need fixing (prioritized)
    - Estimate additional work needed
  - **Bottom Line**: One paragraph honest assessment - is this system ready to trade real money?
  - If critical issues found, document them clearly and create follow-up tasks
  - **Acceptance**: Comprehensive, honest assessment completed with clear production readiness verdict
  - **Estimated time: 2-3 hours**

- [ ] 10. Complete Frontend Integration for Autonomous Strategy System
  - _Requirements: 23.5_
  - **Estimated time: 12-16 hours**

- [ ] 10.1 Backend API Endpoints
  - Add POST `/api/strategies/autonomous/trigger` endpoint to manually trigger cycle
  - Add GET `/api/strategies/autonomous/status` endpoint returning:
    - System enabled/disabled status
    - Last run time, next scheduled run
    - Current market regime (TRENDING_UP/TRENDING_DOWN/RANGING)
    - Cycle statistics (proposals, activations, retirements)
    - Active strategies count
    - Portfolio metrics (total allocation, diversity, correlation)
    - Template usage statistics (which templates used, success rates)
  - Add GET `/api/strategies/autonomous/config` endpoint to get current configuration
  - Add PUT `/api/strategies/autonomous/config` endpoint to update configuration
  - Add GET `/api/strategies/proposals` endpoint to list all proposals with history
  - Add GET `/api/strategies/retirements` endpoint to list retired strategies with metrics
  - Add GET `/api/strategies/templates` endpoint to list available strategy templates
  - **Estimated time: 2-3 hours**

- [ ] 10.2 Autonomous Status Dashboard Component
  - Create `AutonomousStatus.tsx` component displaying:
    - System status (ENABLED/DISABLED) with toggle
    - Current market regime with color-coded badge (green/red/yellow)
    - Last cycle and next scheduled run timestamps
    - Cycle statistics (proposals, activations, retirements)
    - Portfolio health indicators (active count, allocation, diversity, correlation)
    - Template usage stats (most successful templates, usage frequency)
    - Manual trigger button with confirmation
    - Link to settings and history
  - Add to Dashboard.tsx (full width, below System Status)
  - Implement real-time updates via WebSocket for status/regime/cycle changes
  - **Estimated time: 2-3 hours**

- [ ] 10.3 Enhanced Strategy Display
  - Update `Strategies.tsx` to distinguish strategy sources:
    - Add 📋 badge for template-based strategies
    - Add 👤 badge for user-generated strategies
    - Show market regime badge on proposed strategies
    - Show template name (e.g., "RSI Mean Reversion", "MACD Momentum")
    - Display strategy rules in DSL syntax (e.g., "RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2)")
  - Add comprehensive filtering:
    - Filter by source: All / Template-Based / User-Generated
    - Filter by status: All / Proposed / Backtested / Active / Retired
    - Filter by market regime: All / Trending Up / Trending Down / Ranging
    - Filter by template type: All / Mean Reversion / Trend Following / Volatility
  - Add sorting options (performance, date, template type, etc.)
  - Enhanced display for auto-proposed strategies:
    - Show template name and description
    - Show DSL rules with syntax highlighting
    - Show parameter customizations (if any)
    - Show market regime at proposal time
    - Show backtest results inline
    - Show activation/retirement criteria status
    - Show walk-forward validation results (train/test Sharpe)
  - Add bulk actions: Backtest selected, Reject selected, Activate selected
  - **Estimated time: 3-4 hours**

- [ ] 10.4 Autonomous Settings Panel
  - Create `AutonomousSettings.tsx` in Settings page with sections:
    - **General Settings**: 
      - Enable/disable autonomous system
      - Proposal frequency (daily/weekly)
      - Max/min active strategies
    - **Template Settings**:
      - Enable/disable specific templates
      - Template priority/weighting
      - Parameter customization preferences
    - **Activation Thresholds**: Sharpe, Drawdown, Win Rate, Min Trades (with sliders)
    - **Retirement Triggers**: Sharpe, Drawdown, Win Rate, Min Trades (with sliders)
    - **Advanced Settings**: 
      - Backtest period (60/90/120 days)
      - Walk-forward validation settings (train/test split)
      - Portfolio correlation threshold
  - Add real-time validation for all inputs
  - Show current vs. new values side-by-side
  - Add "Reset to Defaults" and "Save Changes" buttons
  - Show last updated timestamp
  - Implement save/load via API endpoints
  - **Estimated time: 2-3 hours**

- [ ] 10.5 Notifications & WebSocket Integration
  - Add WebSocket listeners for autonomous events:
    - New strategies proposed (show count, template types)
    - Template-based generation completed
    - Strategies auto-activated (show name, template, and Sharpe)
    - Strategies auto-retired (show name and reason)
    - Cycle started/completed
    - Backtest completed
    - Walk-forward validation results
    - Errors/warnings
    - Configuration changes
  - Display toast notifications with event icon, message, timestamp, action button
  - Add notification preferences in settings (enable/disable by type, sound alerts)
  - **Estimated time: 1-2 hours**

- [ ] 10.6 Portfolio Visualization & History
  - Create `AutonomousHistory.tsx` component showing:
    - Timeline view of proposals/activations/retirements
    - Filter by date range, market regime, and template type
    - Export to CSV functionality
  - Add portfolio composition chart:
    - Strategies by allocation/regime
    - Strategies by template type
    - Template success rates over time
  - Add performance comparison chart:
    - Performance by template type
    - Performance by market regime
  - Add template analytics:
    - Most successful templates
    - Template usage frequency
    - Average Sharpe by template
  - **Estimated time: 2-3 hours**

- [ ] 10.7 Testing & Polish
  - Test all features with real data
  - Test manual trigger and verify cycle runs
  - Test template-based generation
  - Test settings save/load and validation
  - Test WebSocket real-time updates
  - Test all filtering, sorting, and bulk actions
  - Test template selection and customization
  - Ensure responsive design (mobile/tablet/desktop)
  - Add loading states for all async operations
  - Add error handling with user-friendly messages
  - Add tooltips and help text for all settings
  - Add confirmation dialogs for destructive actions
  - Polish animations and transitions
  - Test edge cases (0 strategies, max strategies, etc.)
  - **Estimated time: 2-3 hours**

## Notes

**Total Estimated Time: 30-40 hours of focused work**
- Backend: 18-24 hours (Tasks 1-9)
- Frontend: 12-16 hours (Task 10)

**What We Cut:**
- ❌ LLM-based rule interpretation (replaced with DSL)
- ❌ LLM-based strategy generation (replaced with templates)
- ❌ Complex security sandbox (using simple `eval()` with safe namespace instead)
- ❌ 50+ indicators (just 10 essential ones)
- ❌ Multi-timeframe analysis (single timeframe is fine)
- ❌ Confidence scoring (binary signals are enough)
- ❌ Strategy versioning (can add later if needed)
- ❌ Learning from historical patterns (can add later)
- ❌ Property-based tests (regular tests are fine for MVP)

**What We Kept (The Important Stuff):**
- ✅ Trading Rule DSL for deterministic rule interpretation (Task 9.11.4 - industry standard)
- ✅ Template-based strategy generation (Task 9.10 - reliable, no LLM required)
- ✅ Autonomous strategy proposal based on market conditions (Task 4 done)
- ✅ Portfolio management with auto-activation/retirement (Task 5 done)
- ✅ Automatic backtesting of proposals
- ✅ Auto-activation of high performers (Sharpe > 1.5)
- ✅ Auto-retirement of underperformers (Sharpe < 0.5)
- ✅ Portfolio management (5-10 diverse strategies)
- ✅ Real market data (no mocks)
- ✅ Full frontend integration with dashboard, settings, and notifications

**Frontend Integration (Task 10) Comprehensive Coverage:**
- 🔌 **7 Backend API Endpoints**: trigger, status, config (get/put), proposals, retirements, templates
- 🎨 **Autonomous Status Dashboard**: 
  - System status with template-based generation indicator
  - Market regime, cycle stats, portfolio health
  - Template usage statistics
- 🤖 **Enhanced Strategy Display**: 
  - Badges for template-based, user-generated
  - Template name and type display
  - DSL rule display with syntax highlighting
  - Filtering by source, status, regime, template type
  - Walk-forward validation results
  - Parameter customization details
- ⚙️ **Comprehensive Settings Panel**: 
  - General settings
  - Template-specific settings (enable/disable, priority)
  - Activation thresholds, retirement triggers
  - Walk-forward validation settings
- 📊 **History & Analytics**: 
  - Proposal/retirement timeline
  - Template performance analytics
  - Template success rates
  - Performance by template type
- 🔔 **Real-time Notifications**: 
  - WebSocket events for all autonomous actions
  - Template generation events
- 📈 **Portfolio Visualization**: 
  - Composition by template type
  - Template success metrics
- 📱 **Responsive Design**: mobile/tablet/desktop support
- ✅ **Complete Testing**: all features, edge cases

**Backend Features Covered in Frontend:**
- ✅ Market regime detection (Task 4) → displayed in dashboard with color coding
- ✅ Strategy proposals (Task 4) → shown in strategies list with 🤖 badge
- ✅ Auto-activation (Task 5) → notifications + status updates
- ✅ Auto-retirement (Task 5) → notifications + retirement history
- ✅ Portfolio metrics (Task 5) → portfolio health indicators
- ✅ Autonomous cycle (Task 6) → manual trigger + scheduled runs display
- ✅ Database tables (Task 7) → proposals/retirements history endpoints
- ✅ Configuration (Task 8) → comprehensive settings panel with all thresholds

**Next Step:** Continue with remaining backend tasks (Tasks 6-9), then complete comprehensive frontend integration (Task 10)!


---

## Updated Notes (After Adding Tasks 9.9-9.12)

**Total Estimated Time: 64-86 hours of focused work**
- Backend Core (Tasks 1-9.8): 30-40 hours ✅ COMPLETED
- Backend Improvements (Tasks 9.9-9.12): 22-30 hours 🔄 UPDATED
- Frontend Integration (Task 10): 12-16 hours

**New Improvement Tasks (9.9-9.12) - UPDATED APPROACH:**
- **Task 9.9**: Data-Driven Strategy Generation (Level 1) - 6-8 hours ✅ COMPLETED
  - Market statistics analyzer with multi-source data
  - Indicator distribution analysis
  - Recent strategy performance tracking
  - Integration into strategy generation
- **Task 9.10**: Template-Based Strategy Generation (Reliable Foundation) - 6-8 hours 🔄 NEW
  - Strategy template library (8-10 proven templates)
  - Template-based generator (no LLM required)
  - Template validation and quality scoring
  - 100% validation pass rate guaranteed
- **Task 9.11**: Optional LLM Enhancement Layer (Advanced) - 4-6 hours 🔄 NEW
  - LLM parameter optimizer (not strategy generator)
  - Strategy ensemble with walk-forward validation
  - Portfolio-level risk management
  - Graceful fallback to templates if LLM unavailable
- **Task 9.12**: Comprehensive E2E Testing - 2-3 hours
  - Update test suite with template-based approach
  - Test both templates-only and templates+LLM modes
  - Document final results

**Expected Improvements:**
- **Baseline (Iteration 3 - LLM-based)**: 0/3 strategies profitable, all negative Sharpe, unreliable generation
- **After Task 9.9 (Data-Driven)**: 1/3 strategies profitable, Sharpe > 0 ✅ COMPLETED
- **After Task 9.10 (Template-Based)**: 2-3/3 strategies profitable, 100% validation pass rate, no LLM required
- **After Task 9.11.1-9.11.3 (Walk-Forward + Portfolio)**: Portfolio Sharpe > 0.5, reduced overfitting
- **After Task 9.11.4 (Trading DSL)**: 100% correct rule parsing, meaningful trades, positive Sharpe for appropriate strategies, industry-standard approach
- **After Task 9.12 (Testing)**: Production-ready system with validated performance

**What We're Adding (Tasks 9.10-9.12) - UPDATED:**
- ✅ Template-based strategy generation (8-10 proven templates)
- ✅ Market regime-specific templates (mean reversion, trend following, volatility)
- ✅ Parameter customization based on market statistics
- ✅ 100% validation pass rate (templates guarantee correctness)
- ✅ Trading Rule DSL (Domain-Specific Language) - industry standard approach
- ✅ Deterministic rule parsing with proper grammar (using Lark parser)
- ✅ Extensible DSL syntax (can add features like variables, functions later)
- ✅ Rule correctness validation (semantic and logical)
- ✅ Walk-forward validation (out-of-sample testing)
- ✅ Portfolio-level risk management and diversification
- ✅ No LLM dependency - system works 100% without any LLM
- ❌ Removed: LLM-based rule interpretation (replaced with DSL)
- ❌ Removed: Template-based regex parsing (replaced with proper DSL)
- ❌ Removed: LLM-based strategy generation (replaced with templates)
- ❌ Removed: qwen2.5-coder:7b dependency
- ❌ Removed: Iterative refinement loop (replaced with templates)

**Backend Features Now Covered in Frontend:**
- ✅ Data-driven generation (Task 9.9) → market statistics displayed in dashboard
- ✅ Template-based generation (Task 9.10) → template selection shown in strategy details
- ✅ Optional LLM optimization (Task 9.11) → LLM enhancement status displayed
- ✅ Portfolio diversification (Task 9.11) → portfolio metrics and correlation matrix displayed

**Key Architecture Changes:**
1. **Primary Strategy Generation**: Template-based (no LLM required)
2. **Primary Rule Interpretation**: Trading DSL with proper grammar (industry standard)
3. **Parser**: Lark LALR parser (proven, fast, maintainable)
4. **No LLM Dependency**: System works 100% without any LLM
5. **Deterministic**: Rule parsing is 100% predictable and correct
6. **Extensible**: Can add new DSL features (variables, functions, loops) later

**Next Steps:**
1. Implement Task 9.11.4 (Trading DSL for rule interpretation) - CRITICAL FIX
2. Complete Tasks 9.11.1-9.11.3 (walk-forward validation, portfolio optimization)
3. Complete Task 9.12 (comprehensive testing with DSL validation)
4. Complete comprehensive frontend integration (Task 10)
5. Deploy to production with monitoring and alerts
