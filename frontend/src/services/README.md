# API Service Layer

This directory contains the API service layer for communicating with the AlphaCent backend.

## Components

### `api.ts`
REST API client for all backend endpoints. Handles:
- Authentication token management (automatic injection in request headers)
- Request/response interceptors
- Error handling (401 redirects to login)
- Type-safe API calls

### `websocket.ts`
WebSocket manager for real-time updates. Features:
- Automatic reconnection with exponential backoff
- Message routing by type
- Connection state management
- Type-safe message handlers

### `auth.ts`
Authentication service for login/logout operations.

### `index.ts`
Unified exports for all services.

## Usage Examples

### REST API Calls

```typescript
import { apiClient } from '../services';

// Get account info
const accountInfo = await apiClient.getAccountInfo('DEMO');

// Get positions
const positions = await apiClient.getPositions('DEMO');

// Place an order
const order = await apiClient.placeOrder({
  symbol: 'AAPL',
  side: 'BUY',
  type: 'MARKET',
  quantity: 10,
  mode: 'DEMO',
});

// Get strategies
const strategies = await apiClient.getStrategies('DEMO');

// Start autonomous trading
await apiClient.startAutonomousTrading(true);
```

### Using with React Hooks

```typescript
import { useApi } from '../hooks';
import { apiClient } from '../services';

function MyComponent() {
  const { data, loading, error, execute } = useApi(
    () => apiClient.getAccountInfo('DEMO')
  );

  useEffect(() => {
    execute();
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  if (!data) return null;

  return <div>Balance: ${data.balance}</div>;
}
```

### WebSocket Real-Time Updates

```typescript
import { wsManager } from '../services';

// Connect to WebSocket
wsManager.connect();

// Subscribe to market data
const unsubscribe = wsManager.onMarketData((data) => {
  console.log('Market data update:', data);
});

// Subscribe to position updates
wsManager.onPositionUpdate((position) => {
  console.log('Position update:', position);
});

// Subscribe to system state changes
wsManager.onSystemState((status) => {
  console.log('System state:', status.state);
});

// Disconnect when done
wsManager.disconnect();
```

### Using WebSocket Hooks

```typescript
import {
  useWebSocketManager,
  useMarketData,
  usePositionUpdates,
  useSystemStatus,
} from '../hooks';

function Dashboard() {
  // Automatically connect/disconnect WebSocket
  const { isConnected } = useWebSocketManager();

  // Subscribe to real-time updates
  const marketData = useMarketData('AAPL');
  const positions = usePositionUpdates();
  const systemStatus = useSystemStatus();

  return (
    <div>
      <div>WebSocket: {isConnected ? 'Connected' : 'Disconnected'}</div>
      <div>System State: {systemStatus?.state}</div>
      <div>Positions: {positions.length}</div>
      {marketData && (
        <div>
          {marketData.symbol}: ${marketData.price}
        </div>
      )}
    </div>
  );
}
```

### API Mutations with Callbacks

```typescript
import { useApiMutation } from '../hooks';
import { apiClient } from '../services';

function StrategyControls({ strategyId }: { strategyId: string }) {
  const { loading, error, execute } = useApiMutation(
    () => apiClient.activateStrategy(strategyId, 'DEMO'),
    {
      onSuccess: () => {
        console.log('Strategy activated successfully');
      },
      onError: (error) => {
        console.error('Failed to activate strategy:', error);
      },
    }
  );

  return (
    <button onClick={() => execute()} disabled={loading}>
      {loading ? 'Activating...' : 'Activate Strategy'}
    </button>
  );
}
```

## Available Endpoints

### Account
- `getAccountInfo(mode)` - Get account balance and info
- `getPositions(mode)` - Get all open positions
- `getPosition(positionId, mode)` - Get specific position

### Orders
- `getOrders(mode)` - Get all orders
- `getOrder(orderId, mode)` - Get specific order
- `placeOrder(params)` - Place a new order
- `cancelOrder(orderId, mode)` - Cancel an order

### Strategies
- `getStrategies(mode)` - Get all strategies
- `getStrategy(strategyId, mode)` - Get specific strategy
- `createStrategy(params)` - Create new strategy
- `updateStrategy(strategyId, params)` - Update strategy
- `retireStrategy(strategyId, mode)` - Retire strategy
- `activateStrategy(strategyId, mode)` - Activate strategy
- `deactivateStrategy(strategyId, mode)` - Deactivate strategy
- `getStrategyPerformance(strategyId, mode)` - Get performance metrics

### Market Data
- `getQuote(symbol)` - Get real-time quote
- `getHistoricalData(params)` - Get historical OHLCV data
- `getSocialInsights(symbol)` - Get social trading insights
- `getSmartPortfolios()` - Get Smart Portfolios

### System Control
- `getSystemStatus()` - Get autonomous trading status
- `startAutonomousTrading(confirmation)` - Start trading
- `pauseAutonomousTrading(confirmation)` - Pause trading
- `stopAutonomousTrading(confirmation)` - Stop trading
- `resumeAutonomousTrading(confirmation)` - Resume trading
- `resetFromEmergencyHalt(confirmation, acknowledgeRisks)` - Reset from emergency halt
- `activateKillSwitch(confirmation, reason)` - Emergency shutdown
- `resetCircuitBreaker(confirmation)` - Reset circuit breaker
- `manualRebalance(confirmation)` - Trigger portfolio rebalance

### Service Management
- `getServicesStatus()` - Get all dependent services status
- `getServiceHealth(serviceName)` - Get specific service health
- `startService(serviceName)` - Start a service
- `stopService(serviceName)` - Stop a service

### Configuration
- `setCredentials(params)` - Set eToro API credentials
- `getConnectionStatus(mode)` - Check eToro connection
- `getRiskConfig(mode)` - Get risk parameters
- `updateRiskConfig(params)` - Update risk parameters
- `getAppConfig()` - Get application configuration
- `updateAppConfig(params)` - Update application configuration

## WebSocket Message Types

- `market_data` - Real-time market data updates
- `position_update` - Position changes (new, updated, closed)
- `order_update` - Order status changes
- `strategy_update` - Strategy changes (activated, deactivated, performance)
- `system_state` - System state changes (ACTIVE, PAUSED, STOPPED, EMERGENCY_HALT)
- `notification` - Critical alerts and notifications
- `service_status` - Dependent service status changes

## Error Handling

The API client automatically handles:
- 401 Unauthorized: Clears token and redirects to login
- Network errors: Throws error with message
- API errors: Extracts error message from response

All API methods throw errors that should be caught:

```typescript
try {
  const data = await apiClient.getAccountInfo('DEMO');
} catch (error) {
  console.error('API call failed:', error.message);
}
```

Or use the `useApi` hook which handles errors automatically:

```typescript
const { data, loading, error } = useApi(() => apiClient.getAccountInfo('DEMO'));
```

## Authentication

The API client automatically includes the authentication token from localStorage in all requests. The token is set by the `authService.login()` method and cleared on logout or 401 responses.

## Environment Variables

Configure the API and WebSocket URLs in `.env`:

```
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
```
