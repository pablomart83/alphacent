# AlphaCent Backend API

FastAPI-based REST API and WebSocket server for the AlphaCent Trading Platform.

## Overview

The backend service provides:
- REST API endpoints for trading operations
- WebSocket connections for real-time updates
- Session-based authentication
- System state management
- Service dependency management

## Architecture

```
src/api/
├── app.py                  # Main FastAPI application
├── middleware.py           # Authentication middleware
├── dependencies.py         # Dependency injection
├── websocket_manager.py    # WebSocket connection manager
└── routers/
    ├── auth.py            # Authentication endpoints
    ├── config.py          # Configuration endpoints
    ├── account.py         # Account and portfolio endpoints
    ├── strategies.py      # Strategy management endpoints
    ├── orders.py          # Order management endpoints
    ├── market_data.py     # Market data endpoints
    ├── control.py         # Control and system state endpoints
    └── websocket.py       # WebSocket endpoint
```

## Running the Backend

### Development Mode

```bash
# Using the startup script
python run_backend.py

# Or directly with uvicorn
uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
```

### Production Mode

```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Endpoints

### Authentication
- `POST /auth/login` - User login
- `POST /auth/logout` - User logout
- `GET /auth/status` - Session validation

### Configuration
- `POST /config/credentials` - Set API credentials
- `GET /config/connection-status` - Check eToro connection
- `GET /config/risk` - Get risk configuration
- `PUT /config/risk` - Update risk configuration
- `GET /config` - Get app configuration
- `PUT /config` - Update app configuration

### Account & Portfolio
- `GET /account` - Get account information
- `GET /account/positions` - Get all positions
- `GET /account/positions/{id}` - Get specific position

### Strategies
- `GET /strategies` - List all strategies
- `POST /strategies` - Create new strategy
- `GET /strategies/{id}` - Get strategy details
- `PUT /strategies/{id}` - Update strategy
- `DELETE /strategies/{id}` - Retire strategy
- `POST /strategies/{id}/activate` - Activate strategy
- `POST /strategies/{id}/deactivate` - Deactivate strategy
- `GET /strategies/{id}/performance` - Get performance metrics

### Orders
- `GET /orders` - List all orders
- `GET /orders/{id}` - Get order details
- `POST /orders` - Place manual order
- `DELETE /orders/{id}` - Cancel order

### Market Data
- `GET /market-data/{symbol}` - Get real-time quote
- `GET /market-data/{symbol}/historical` - Get historical data
- `GET /market-data/social-insights/{symbol}` - Get social insights
- `GET /market-data/smart-portfolios` - Get Smart Portfolios

### Control & System State
- `GET /control/system/status` - Get system status
- `POST /control/system/start` - Start autonomous trading
- `POST /control/system/pause` - Pause autonomous trading
- `POST /control/system/stop` - Stop autonomous trading
- `POST /control/system/resume` - Resume from paused
- `POST /control/system/reset` - Reset from emergency halt
- `POST /control/kill-switch` - Activate kill switch
- `POST /control/circuit-breaker/reset` - Reset circuit breaker
- `POST /control/rebalance` - Manual rebalancing

### Service Management
- `GET /control/services` - Get all services status
- `GET /control/services/{name}/health` - Health check service
- `POST /control/services/{name}/start` - Start service
- `POST /control/services/{name}/stop` - Stop service

### WebSocket
- `WS /ws?session_id={session_id}` - WebSocket connection for real-time updates

## WebSocket Messages

The WebSocket connection sends JSON messages with the following types:

### Connection
```json
{
  "type": "connection",
  "status": "connected",
  "timestamp": "2026-02-14T10:30:00Z"
}
```

### Market Data Update
```json
{
  "type": "market_data",
  "symbol": "AAPL",
  "data": {...},
  "timestamp": "2026-02-14T10:30:00Z"
}
```

### Position Update
```json
{
  "type": "position_update",
  "position": {...},
  "timestamp": "2026-02-14T10:30:00Z"
}
```

### Strategy Performance Update
```json
{
  "type": "strategy_performance",
  "strategy_id": "strat_001",
  "performance": {...},
  "timestamp": "2026-02-14T10:30:00Z"
}
```

### Error Notification
```json
{
  "type": "error",
  "error": {
    "severity": "CRITICAL",
    "title": "Error Title",
    "message": "Error message"
  },
  "timestamp": "2026-02-14T10:30:00Z"
}
```

### System State Change
```json
{
  "type": "system_state",
  "state": {
    "state": "ACTIVE",
    "timestamp": "2026-02-14T10:30:00Z",
    ...
  },
  "timestamp": "2026-02-14T10:30:00Z"
}
```

### Order Update
```json
{
  "type": "order_update",
  "order": {...},
  "timestamp": "2026-02-14T10:30:00Z"
}
```

## Authentication

The API uses session-based authentication with secure cookies:

1. Login via `POST /auth/login` with username and password
2. Receive session cookie in response
3. Include cookie in subsequent requests
4. Session validated by middleware on each request
5. Logout via `POST /auth/logout` to clear session

## CORS Configuration

The API is configured to accept requests from:
- `http://localhost:3000` (React frontend)

## Error Handling

All endpoints return standard HTTP status codes:
- `200` - Success
- `400` - Bad Request (validation error)
- `401` - Unauthorized (authentication required)
- `404` - Not Found
- `500` - Internal Server Error

Error responses include a detail message:
```json
{
  "detail": "Error message"
}
```

## Development

### Adding New Endpoints

1. Create a new router in `src/api/routers/`
2. Define Pydantic models for request/response
3. Implement endpoint handlers
4. Register router in `src/api/app.py`

### Testing

```bash
# Run tests
pytest tests/

# Test specific endpoint
pytest tests/test_api.py::test_login
```

## Requirements Validation

This implementation validates the following requirements:
- **16.1, 16.6**: FastAPI application with REST and WebSocket support
- **18.1, 18.3**: Authentication endpoints
- **2.1, 2.6**: Configuration management
- **11.1, 11.2**: Account and portfolio endpoints
- **11.3**: Strategy management
- **11.4**: Order management
- **11.7, 11.8**: Market data and social insights
- **11.5, 11.11, 11.12, 16.12**: Control and system state management
- **16.1.1-16.1.10**: Service dependency management
- **11.9, 16.11**: Real-time WebSocket updates
