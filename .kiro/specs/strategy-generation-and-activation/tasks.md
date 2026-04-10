# Implementation Tasks: Strategy Generation and Activation

## Overview
This task list implements the strategy generation and activation feature to enable autonomous trading with LLM-generated strategies.

## Task Breakdown

### Phase 1: Bootstrap Service and CLI (Quick Win)

#### 1. Create Bootstrap Service
- [x] 1.1 Create `src/strategy/bootstrap_service.py` with `BootstrapService` class
  - [x] 1.1.1 Implement `bootstrap_strategies()` method with strategy templates
  - [x] 1.1.2 Add strategy templates for momentum, mean reversion, and breakout
  - [x] 1.1.3 Implement auto-activation logic based on performance thresholds
  - [x] 1.1.4 Add comprehensive logging for bootstrap process

#### 2. Create CLI Command
- [x] 2.1 Create `src/cli/bootstrap_strategies.py` CLI script
  - [x] 2.1.1 Add argparse for command-line arguments (--auto-activate, --min-sharpe, --strategy-types)
  - [x] 2.1.2 Integrate with BootstrapService
  - [x] 2.1.3 Display progress and results in terminal
  - [x] 2.1.4 Add error handling and user-friendly messages

#### 3. Add Bootstrap API Endpoint
- [x] 3.1 Add `/strategies/bootstrap` POST endpoint to `src/api/routers/strategies.py`
  - [x] 3.1.1 Create `BootstrapRequest` and `BootstrapResponse` Pydantic models
  - [x] 3.1.2 Integrate with BootstrapService
  - [x] 3.1.3 Return summary of created strategies and backtest results

#### 4. Test Bootstrap Functionality
- [x] 4.1 Create `tests/test_bootstrap_service.py`
  - [x] 4.1.1 Test strategy generation from templates
  - [x] 4.1.2 Test automatic backtesting
  - [x] 4.1.3 Test auto-activation logic
  - [x] 4.1.4 Test error handling (LLM unavailable, backtest failures)

### Phase 2: Strategy Generation Enhancements

#### 5. Add Strategy Generation API Endpoint
- [x] 5.1 Add `/strategies/generate` POST endpoint to `src/api/routers/strategies.py`
  - [x] 5.1.1 Create `GenerateStrategyRequest` Pydantic model with prompt and constraints
  - [x] 5.1.2 Integrate with StrategyEngine.generate_strategy()
  - [x] 5.1.3 Return generated strategy with PROPOSED status
  - [x] 5.1.4 Add error handling for LLM failures

#### 6. Enhance LLM Service for Reasoning Capture
- [x] 6.1 Update `src/llm/llm_service.py` to capture reasoning metadata
  - [x] 6.1.1 Create `StrategyReasoning` dataclass
  - [x] 6.1.2 Implement `capture_reasoning()` method to extract hypothesis, alpha sources, assumptions
  - [x] 6.1.3 Update `StrategyDefinition` to include reasoning field
  - [x] 6.1.4 Modify LLM prompt to request reasoning in structured format

#### 7. Update Strategy Data Models
- [x] 7.1 Update `src/models/dataclasses.py` to add reasoning fields
  - [x] 7.1.1 Add `reasoning` field to Strategy dataclass
  - [x] 7.1.2 Add `backtest_results` field to Strategy dataclass
  - [x] 7.1.3 Create `StrategyReasoning` and `AlphaSource` dataclasses
- [x] 7.2 Update `src/models/orm.py` to persist reasoning
  - [x] 7.2.1 Add `reasoning` JSON column to StrategyORM
  - [x] 7.2.2 Add `backtest_results` JSON column to StrategyORM
  - [x] 7.2.3 Update serialization/deserialization methods

#### 8. Test Strategy Generation
- [x] 8.1 Create `tests/test_strategy_generation.py`
  - [x] 8.1.1 Test generation with various prompts (momentum, mean reversion, breakout)
  - [x] 8.1.2 Test reasoning capture and persistence
  - [x] 8.1.3 Test validation of generated strategies
  - [x] 8.1.4 Test error handling (invalid prompts, LLM failures)

### Phase 3: Backtesting Enhancements

#### 9. Add Backtest API Endpoint
- [x] 9.1 Add `/strategies/{strategy_id}/backtest` POST endpoint
  - [x] 9.1.1 Create `BacktestRequest` and `BacktestResultsResponse` Pydantic models
  - [x] 9.1.2 Integrate with StrategyEngine.backtest_strategy()
  - [x] 9.1.3 Return backtest results with performance metrics
  - [x] 9.1.4 Add optional start_date and end_date parameters

#### 10. Enhance Backtest Results Storage
- [x] 10.1 Update StrategyEngine to store detailed backtest results
  - [x] 10.1.1 Store equity curve data
  - [x] 10.1.2 Store trade history
  - [x] 10.1.3 Store backtest period (start/end dates)
  - [x] 10.1.4 Update strategy status to BACKTESTED on success

#### 11. Test Backtesting
- [x] 11.1 Create `tests/test_backtesting.py`
  - [x] 11.1.1 Test backtest with different date ranges
  - [x] 11.1.2 Test performance metrics calculation
  - [x] 11.1.3 Test state transition (PROPOSED → BACKTESTED)
  - [x] 11.1.4 Test error handling (insufficient data, invalid symbols)

### Phase 4: Strategy Activation and Validation

#### 12. Enhance Activation Validation
- [x] 12.1 Update `StrategyEngine.activate_strategy()` to validate allocation
  - [x] 12.1.1 Calculate total allocation of active strategies
  - [x] 12.1.2 Reject activation if total would exceed 100%
  - [x] 12.1.3 Add allocation_percent parameter to activation
  - [x] 12.1.4 Update strategy allocation in database

#### 13. Add Allocation Management
- [x] 13.1 Add `/strategies/{strategy_id}/allocation` PUT endpoint
  - [x] 13.1.1 Create `UpdateAllocationRequest` Pydantic model
  - [x] 13.1.2 Validate allocation doesn't exceed limits
  - [x] 13.1.3 Update strategy allocation in database
  - [x] 13.1.4 Broadcast update via WebSocket

#### 14. Test Activation and Allocation
- [x] 14.1 Create `tests/test_activation.py`
  - [x] 14.1.1 Test activation preconditions (must be BACKTESTED)
  - [x] 14.1.2 Test allocation validation (max 100%)
  - [x] 14.1.3 Test state transitions (BACKTESTED → DEMO/LIVE)
  - [x] 14.1.4 Test deactivation (DEMO/LIVE → BACKTESTED)

### Phase 5: Signal Generation Enhancements

#### 15. Enhance Trading Signals with Confidence and Reasoning
- [x] 15.1 Update `src/models/dataclasses.py` TradingSignal
  - [x] 15.1.1 Add `confidence` field (0.0 to 1.0)
  - [x] 15.1.2 Add `reasoning` field (explanation of signal)
  - [x] 15.1.3 Add `indicators` field (dict of indicator values)
  - [x] 15.1.4 Add `metadata` field for additional context

#### 16. Update Signal Generation Logic
- [x] 16.1 Update `StrategyEngine._generate_signal_for_symbol()`
  - [x] 16.1.1 Calculate confidence score based on indicator alignment
  - [x] 16.1.2 Generate reasoning text explaining signal
  - [x] 16.1.3 Include indicator values in signal
  - [x] 16.1.4 Add signal metadata (strategy name, timestamp)

#### 17. Test Signal Generation
- [x] 17.1 Create `tests/test_signal_generation.py`
  - [x] 17.1.1 Test signal generation for active strategies
  - [x] 17.1.2 Test confidence score calculation
  - [x] 17.1.3 Test reasoning generation
  - [x] 17.1.4 Test signal validation through risk manager

### Phase 6: Frontend Integration

#### 18. Add Strategy Generation UI
- [x] 18.1 Create `frontend/src/components/StrategyGenerator.tsx`
  - [x] 18.1.1 Add form for natural language prompt input
  - [x] 18.1.2 Add market context inputs (symbols, timeframe, risk tolerance)
  - [x] 18.1.3 Display generation progress with stages
  - [x] 18.1.4 Show generated strategy with reasoning

#### 19. Add Strategy Reasoning Panel
- [x] 19.1 Create `frontend/src/components/StrategyReasoningPanel.tsx`
  - [x] 19.1.1 Display hypothesis and market assumptions
  - [x] 19.1.2 Visualize alpha sources with weights
  - [x] 19.1.3 Show signal logic explanation
  - [x] 19.1.4 Add expandable section for full details

#### 20. Add Backtest Results Visualization
- [x] 20.1 Create `frontend/src/components/BacktestResults.tsx`
  - [x] 20.1.1 Display performance metrics (Sharpe, Sortino, max DD, win rate)
  - [x] 20.1.2 Show equity curve chart
  - [x] 20.1.3 Display trade history table
  - [x] 20.1.4 Add backtest period information

#### 21. Enhance Strategies Dashboard
- [x] 21.1 Update `frontend/src/components/Strategies.tsx`
  - [x] 21.1.1 Add "Generate Strategy" button
  - [x] 21.1.2 Add "Backtest" button for PROPOSED strategies
  - [x] 21.1.3 Display allocation percentage with edit capability
  - [x] 21.1.4 Show reasoning preview in strategy cards

#### 22. Add Signal Feed Component
- [x] 22.1 Create `frontend/src/components/SignalFeed.tsx`
  - [x] 22.1.1 Display real-time signal generation events
  - [x] 22.1.2 Show symbol, direction, confidence, and reasoning
  - [x] 22.1.3 Add filters by strategy and symbol
  - [x] 22.1.4 Subscribe to WebSocket for live updates

#### 23. Update API Client
- [x] 23.1 Update `frontend/src/services/api.ts`
  - [x] 23.1.1 Add `generateStrategy()` method
  - [x] 23.1.2 Add `backtestStrategy()` method
  - [x] 23.1.3 Add `bootstrapStrategies()` method
  - [x] 23.1.4 Add `updateAllocation()` method

### Phase 7: WebSocket Integration

#### 24. Add Strategy Update Broadcasting
- [x] 24.1 Update `src/api/websocket_manager.py`
  - [x] 24.1.1 Add `broadcast_strategy_update()` method
  - [x] 24.1.2 Add `broadcast_signal_generated()` method
  - [x] 24.1.3 Add `broadcast_backtest_progress()` method

#### 25. Integrate Broadcasting in Strategy Engine
- [x] 25.1 Update StrategyEngine to broadcast updates
  - [x] 25.1.1 Broadcast when strategy is generated
  - [x] 25.1.2 Broadcast when backtest completes
  - [x] 25.1.3 Broadcast when strategy is activated/deactivated
  - [x] 25.1.4 Broadcast when performance metrics update

#### 26. Integrate Broadcasting in Trading Scheduler
- [x] 26.1 Update TradingScheduler to broadcast signals
  - [x] 26.1.1 Broadcast when signals are generated
  - [x] 26.1.2 Broadcast when signals are validated
  - [x] 26.1.3 Broadcast when orders are executed

### Phase 8: Testing and Validation

#### 27. Property-Based Tests
- [ ] 27.1 Create `tests/property_tests/test_strategy_properties.py`
  - [ ] 27.1.1 Property 1: LLM Strategy Generation Completeness
  - [ ] 27.1.2 Property 2: Strategy Validation Correctness
  - [ ] 27.1.3 Property 3: Strategy Creation State Invariant
  - [ ] 27.1.4 Property 10: Portfolio Allocation Invariant
  - [ ] 27.1.5 Property 21: Strategy Persistence Round-Trip

#### 28. Integration Tests
- [ ] 28.1 Create `tests/integration/test_strategy_workflow.py`
  - [ ] 28.1.1 Test end-to-end: generate → backtest → activate → signal generation
  - [ ] 28.1.2 Test bootstrap workflow
  - [ ] 28.1.3 Test WebSocket broadcasting
  - [ ] 28.1.4 Test system recovery after restart

#### 29. Error Handling Tests
- [ ] 29.1 Create `tests/test_error_handling.py`
  - [ ] 29.1.1 Test LLM service unavailable
  - [ ] 29.1.2 Test insufficient historical data
  - [ ] 29.1.3 Test allocation exceeds limit
  - [ ] 29.1.4 Test activation precondition failures

### Phase 9: Documentation and Deployment

#### 30. Create User Documentation
- [ ] 30.1 Create `docs/STRATEGY_GENERATION_GUIDE.md`
  - [ ] 30.1.1 Document how to generate strategies
  - [ ] 30.1.2 Document backtesting process
  - [ ] 30.1.3 Document activation and monitoring
  - [ ] 30.1.4 Document bootstrap CLI usage

#### 31. Create Developer Documentation
- [ ] 31.1 Create `docs/STRATEGY_ENGINE_API.md`
  - [ ] 31.1.1 Document StrategyEngine API
  - [ ] 31.1.2 Document LLM Service API
  - [ ] 31.1.3 Document Bootstrap Service API
  - [ ] 31.1.4 Document WebSocket events

#### 32. Database Migration
- [ ] 32.1 Create database migration for new fields
  - [ ] 32.1.1 Add reasoning column to strategies table
  - [ ] 32.1.2 Add backtest_results column to strategies table
  - [ ] 32.1.3 Add allocation_percent column to strategies table
  - [ ] 32.1.4 Test migration on existing database

#### 33. Deployment Checklist
- [ ] 33.1 Verify Ollama is installed and running
- [ ] 33.2 Verify vectorbt is installed
- [ ] 33.3 Run database migration
- [ ] 33.4 Test bootstrap CLI command
- [ ] 33.5 Verify trading scheduler is running
- [ ] 33.6 Monitor logs for errors

## Priority Order

**High Priority (MVP - Get Trading ASAP):**
1. Phase 1: Bootstrap Service and CLI (Tasks 1-4)
2. Phase 4: Strategy Activation and Validation (Tasks 12-14)
3. Phase 8: Basic Testing (Task 28.1.2 - bootstrap workflow test)

**Medium Priority (Full Functionality):**
4. Phase 2: Strategy Generation Enhancements (Tasks 5-8)
5. Phase 3: Backtesting Enhancements (Tasks 9-11)
6. Phase 5: Signal Generation Enhancements (Tasks 15-17)

**Lower Priority (UX and Polish):**
7. Phase 6: Frontend Integration (Tasks 18-23)
8. Phase 7: WebSocket Integration (Tasks 24-26)
9. Phase 8: Comprehensive Testing (Tasks 27, 29)
10. Phase 9: Documentation and Deployment (Tasks 30-33)

## Quick Start Path

To get autonomous trading working as quickly as possible:

1. Complete Tasks 1-4 (Bootstrap Service and CLI)
2. Run: `python -m src.cli.bootstrap_strategies --auto-activate --min-sharpe 0.5`
3. Verify strategies are active in database
4. Monitor trading scheduler logs for signal generation
5. Check eToro demo account for executed trades

## Notes

- All tasks assume Ollama is installed and running locally
- Market data must be available for backtesting (90 days minimum)
- eToro demo credentials must be configured
- System state must be ACTIVE for signal generation
- Trading scheduler runs every 5 seconds when system is ACTIVE
