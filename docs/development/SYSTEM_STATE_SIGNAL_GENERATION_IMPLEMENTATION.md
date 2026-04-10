# System State Signal Generation Implementation

## Task 10.5.1: Integrate System State Checks in Signal Generation

### Overview
Successfully integrated system state checks into the signal generation process to ensure signals are only generated when the autonomous trading system is in the ACTIVE state.

### Requirements Validated
- **Requirement 11.12**: Backend service manages autonomous trading state
- **Requirement 11.16**: System halts signal generation when not ACTIVE
- **Requirement 16.12**: Backend continues running independently of frontend

### Implementation Details

#### 1. Updated `StrategyEngine.generate_signals()` Method
**File**: `src/strategy/strategy_engine.py`

Added system state check at the beginning of the `generate_signals()` method:

```python
def generate_signals(self, strategy: Strategy) -> List[TradingSignal]:
    """
    Generate trading signals based on strategy rules and current market data.
    
    Validates: Requirements 11.12, 11.16, 16.12
    """
    from src.core.system_state_manager import get_system_state_manager
    from src.models.enums import SystemStateEnum
    
    # Check system state before generating signals
    state_manager = get_system_state_manager()
    current_state = state_manager.get_current_state()
    
    # Skip signal generation if system is not ACTIVE
    if current_state.state != SystemStateEnum.ACTIVE:
        logger.info(
            f"Skipping signal generation for strategy {strategy.name}: "
            f"system state is {current_state.state.value}, not ACTIVE"
        )
        return []
    
    # Continue with normal signal generation...
```

**Behavior**:
- When system state is **ACTIVE**: Signal generation proceeds normally
- When system state is **PAUSED**: Signal generation is skipped, empty list returned, reason logged
- When system state is **STOPPED**: Signal generation is skipped, empty list returned, reason logged
- When system state is **EMERGENCY_HALT**: Signal generation is skipped, empty list returned, reason logged

#### 2. Fixed Database Session Management
**File**: `src/core/system_state_manager.py`

Fixed import error by updating database session access:

**Before**:
```python
from src.models.database import get_session
session = get_session()
```

**After**:
```python
from src.models.database import get_database
db = get_database()
session = db.get_session()
```

This change was applied to three methods:
- `_load_state_from_db()`
- `_save_state_to_db()`
- `_record_transition()`

#### 3. Comprehensive Test Suite
**File**: `tests/test_system_state_signal_generation.py`

Created comprehensive test suite with 5 test cases:

1. **test_signal_generation_skipped_when_paused**: Verifies signals are not generated when system is PAUSED
2. **test_signal_generation_skipped_when_stopped**: Verifies signals are not generated when system is STOPPED
3. **test_signal_generation_skipped_when_emergency_halt**: Verifies signals are not generated during EMERGENCY_HALT
4. **test_signal_generation_proceeds_when_active**: Verifies signal generation proceeds when system is ACTIVE
5. **test_signal_generation_fails_for_inactive_strategy**: Verifies proper error handling for inactive strategies

**All tests pass successfully** ✓

### System State Flow

```
┌─────────────────────────────────────────────────────────┐
│                  Signal Generation Request              │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
         ┌────────────────────────────┐
         │  Check System State        │
         └────────────┬───────────────┘
                      │
         ┌────────────┴────────────┐
         │                         │
         ▼                         ▼
    [ACTIVE]                  [PAUSED/STOPPED/
         │                     EMERGENCY_HALT]
         │                         │
         ▼                         ▼
┌─────────────────┐      ┌──────────────────┐
│ Generate Signals│      │ Skip Generation  │
│ Proceed Normally│      │ Return []        │
│                 │      │ Log Reason       │
└─────────────────┘      └──────────────────┘
```

### Key Features

1. **Non-Intrusive**: Signal generation gracefully returns empty list when system is not active
2. **Logged**: All skipped signal generations are logged with reason for audit trail
3. **State-Aware**: Respects all system states (ACTIVE, PAUSED, STOPPED, EMERGENCY_HALT)
4. **Backward Compatible**: Existing code continues to work without modification
5. **Well-Tested**: Comprehensive test coverage ensures correctness

### Integration Points

The system state check integrates with:
- **SystemStateManager**: Retrieves current system state
- **Strategy Engine**: Controls signal generation based on state
- **Backend API**: State transitions via `/system/start`, `/system/pause`, `/system/stop` endpoints
- **Frontend UI**: Master control panel displays and controls system state

### Usage Example

```python
# When system is ACTIVE
strategy_engine = StrategyEngine(llm_service, market_data)
signals = strategy_engine.generate_signals(active_strategy)
# Returns: [TradingSignal(...), TradingSignal(...)]

# When system is PAUSED
signals = strategy_engine.generate_signals(active_strategy)
# Returns: []
# Logs: "Skipping signal generation for strategy Test Strategy: system state is PAUSED, not ACTIVE"
```

### Benefits

1. **Safety**: Prevents unwanted trading when system is paused or stopped
2. **Control**: Users have full control over when signals are generated
3. **Auditability**: All state-based decisions are logged
4. **Reliability**: System state persists across restarts
5. **Independence**: Backend operates independently of frontend connection

### Testing Results

```
tests/test_system_state_signal_generation.py::TestSystemStateSignalGeneration::test_signal_generation_skipped_when_paused PASSED
tests/test_system_state_signal_generation.py::TestSystemStateSignalGeneration::test_signal_generation_skipped_when_stopped PASSED
tests/test_system_state_signal_generation.py::TestSystemStateSignalGeneration::test_signal_generation_skipped_when_emergency_halt PASSED
tests/test_system_state_signal_generation.py::TestSystemStateSignalGeneration::test_signal_generation_proceeds_when_active PASSED
tests/test_system_state_signal_generation.py::TestSystemStateSignalGeneration::test_signal_generation_fails_for_inactive_strategy PASSED

5 passed in 6.79s
```

### Next Steps

The implementation is complete and tested. The system now properly checks state before generating signals, ensuring that:
- Signals are only generated when the system is ACTIVE
- Signal generation is skipped (with logging) when system is PAUSED, STOPPED, or in EMERGENCY_HALT
- The backend service operates independently and maintains state across sessions
- All state transitions are properly logged for audit purposes

This completes task 10.5.1 and validates requirements 11.12, 11.16, and 16.12.
