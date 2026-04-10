# Order Size Validation Fix - Complete

## Problem
Orders were failing when sent to eToro with error code 720:
```
Error opening position - Initial Leveraged Position Amount is under the minimum 
defined Leveraged Amount in the system. leveraged InitialPositionAmount: 1.00 
MinimumPositionAmount: 10 (Dollars)
```

eToro requires a minimum order size of **$10.00** for all orders.

## Root Cause
The system was allowing orders to be created and submitted with sizes below the $10 minimum, causing them to fail at the eToro API level. This affected:
1. Manual orders placed via API
2. Strategy-generated orders with small position sizes
3. **Vibe Coding orders** - defaulting to $1 when quantity not specified

## Solution Implemented
Added validation at multiple levels to ensure orders always meet the minimum size requirement:

### 1. eToro Client Validation (`src/api/etoro_client.py`)
```python
# Validate minimum order size (eToro requires minimum $10)
if quantity < 10.0:
    raise ValueError(
        f"Order size must be at least $10.00 (eToro minimum). "
        f"Requested: ${quantity:.2f}"
    )
```

### 2. Order Executor Validation (`src/execution/order_executor.py`)
```python
# Validate minimum order size (eToro requires minimum $10)
if position_size < 10.0:
    raise OrderExecutionError(
        f"Order size must be at least $10.00 (eToro minimum). "
        f"Requested: ${position_size:.2f} for {signal.symbol}"
    )
```

### 3. Risk Manager Position Sizing (`src/risk/risk_manager.py`)
```python
# Ensure minimum order size (eToro requires $10 minimum)
MINIMUM_ORDER_SIZE = 10.0
if position_size < MINIMUM_ORDER_SIZE:
    logger.warning(
        f"Calculated position size ${position_size:.2f} is below minimum ${MINIMUM_ORDER_SIZE:.2f}. "
        f"Returning 0 to skip order."
    )
    return 0.0
```

### 4. API Endpoint Validation (`src/api/routers/orders.py`)
```python
# Validate minimum order size (eToro requires minimum $10)
if request.quantity < 10.0:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Order size must be at least $10.00 (eToro minimum). Requested: ${request.quantity:.2f}"
    )
```

### 5. Vibe Coding Frontend Fix (`frontend/src/services/api.ts`)
```typescript
// Changed default from $1 to $10
quantity: command.quantity || 10, // Default to $10 minimum (eToro requirement)
```

### 6. LLM Service Parsing (`src/llm/llm_service.py`)
```python
# Parse quantity and enforce minimum
quantity = data.get("quantity")
if quantity is not None:
    quantity = float(quantity)
    # Enforce eToro minimum of $10
    if quantity < 10.0:
        logger.warning(f"Quantity ${quantity:.2f} below minimum, adjusting to $10.00")
        quantity = 10.0
```

### 7. LLM Prompt Update (`src/llm/llm_service.py`)
Updated the vibe coding prompt to instruct the LLM about the $10 minimum:
```
IMPORTANT RULES:
- quantity is in DOLLARS (not shares), minimum $10
- If user says "10 shares", convert to approximate dollar amount
- If no quantity specified, leave as null (will default to $10)
- If quantity would be less than $10, set to $10
```

## Validation Layers

The fix implements defense-in-depth with multiple validation layers:

1. **LLM Prompt**: Instructs AI to respect $10 minimum
2. **LLM Parsing**: Adjusts quantities below $10 to $10
3. **Frontend/API Layer**: Defaults to $10 for vibe coding, rejects manual orders below $10
4. **Risk Manager Layer**: Prevents strategies from generating position sizes below $10
5. **Order Executor Layer**: Final check before order creation
6. **eToro Client Layer**: Last line of defense before API submission

## Testing

All tests pass successfully:

### Test 1: Direct Client Validation
```
✅ Order below $10 correctly rejected
✅ Order at $10 accepted
✅ Order above $10 accepted
```

### Test 2: Risk Manager Position Sizing
```
✅ Small account ($100) generates valid position size ($10 minimum)
✅ Normal account ($10,000) generates appropriate position size
```

### Test 3: Signal Validation
```
✅ Signals with calculated size below $10 are rejected
✅ Signals with valid size are approved
```

### Test 4: Vibe Coding Validation
```
✅ LLM parsing adjusts quantities below $10 to $10
✅ Frontend defaults to $10 when quantity is null
✅ Prompt instructs LLM about minimum requirement
```

## Impact

- **Manual Orders**: Users cannot submit orders below $10 via the API
- **Strategy Orders**: Strategies will skip signals when calculated position size is below $10
- **Vibe Coding Orders**: Now default to $10 instead of $1, and LLM is instructed about minimum
- **Error Prevention**: Orders will never reach eToro with invalid sizes
- **User Experience**: Clear error messages explain the minimum requirement

## Files Modified

1. `src/api/etoro_client.py` - Added minimum size validation in `place_order()`
2. `src/execution/order_executor.py` - Added minimum size validation in `execute_signal()`
3. `src/risk/risk_manager.py` - Added minimum size check in `calculate_position_size()`
4. `src/api/routers/orders.py` - Added minimum size validation in `place_order()` endpoint
5. `frontend/src/services/api.ts` - Changed default from $1 to $10 in `executeVibeCommand()`
6. `src/llm/llm_service.py` - Added minimum enforcement in `_parse_trading_command()` and updated prompt

## Verification

Run the verification scripts to confirm the fix:
```bash
python verify_order_size_fix.py
python test_vibe_coding_fix.py
```

All validation layers are working correctly and orders below $10 are properly rejected or adjusted.
