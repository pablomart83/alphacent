# Trading Mode Undefined Fix

## Problem
The frontend is sending `mode=undefined` in API requests, causing 422 errors from the backend.

## Root Cause
The `TradingMode` is defined as both a const object AND a type in `frontend/src/types/index.ts`:

```typescript
export const TradingMode = {
  DEMO: 'DEMO',
  LIVE: 'LIVE',
} as const;
export type TradingMode = typeof TradingMode[keyof typeof TradingMode];
```

The `TradingModeContext` was using `TradingMode.DEMO` (the object property) as the initial state, but TypeScript was treating it as the type, causing type confusion. When the context failed to load the trading mode from the backend, it would set `undefined` instead of a valid default.

## Solution Applied

### 1. Fixed TradingModeContext.tsx
Changed the initial state and error handling to explicitly use string literals:

```typescript
// Before:
const [tradingMode, setTradingModeState] = useState<TradingMode>(TradingMode.DEMO);

// After:
const [tradingMode, setTradingModeState] = useState<TradingMode>('DEMO' as TradingMode);
```

Also added a fallback in the API response handling:
```typescript
const mode = config.trading_mode || 'DEMO';
setTradingModeState(mode as TradingMode);
```

## Testing
After this fix:
1. The trading mode will always default to 'DEMO' if the backend fails to provide a value
2. All API calls will receive a valid mode parameter ('DEMO' or 'LIVE')
3. No more 422 errors due to `mode=undefined`

## Files Modified
- `frontend/src/contexts/TradingModeContext.tsx`
