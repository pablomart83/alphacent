"""
FastAPI application for AlphaCent Trading Platform.

Provides REST API and WebSocket endpoints for the trading platform.
Validates: Requirements 16.1, 16.6
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.logging_config import LoggingConfig
from src.core.auth import AuthenticationManager, SessionManager
from src.api.middleware import AuthenticationMiddleware
from src.api.dependencies import init_dependencies
from src.models.database import init_database, get_database

# Setup logging
LoggingConfig.initialize()
logger = logging.getLogger(__name__)

# Global instances
auth_manager: AuthenticationManager = None
session_manager: SessionManager = None



@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Application lifespan manager.

    Starts HTTP server immediately, initializes background services asynchronously.
    """
    global auth_manager, session_manager

    # === PHASE 1: Fast startup — get HTTP server accepting requests ===
    logger.info("AlphaCent Backend Service starting...")

    # Initialize authentication (fast, no network)
    auth_manager = AuthenticationManager(session_timeout_minutes=30)
    session_manager = SessionManager(auth_manager, cleanup_interval_seconds=300)
    session_manager.start_automatic_cleanup()

    # Initialize dependencies
    init_dependencies(auth_manager, session_manager)

    # Initialize database (fast, local file)
    logger.info("Initializing database...")
    init_database("alphacent.db")
    db = get_database()
    logger.info(f"Database initialized")

    # Connect auth manager to DB and ensure admin user exists
    auth_manager.set_database(db)
    auth_manager.ensure_admin_exists("admin123")

    # Restore system state (fast, DB read)
    from src.core.system_state_manager import get_system_state_manager
    state_manager = get_system_state_manager()
    current_state = state_manager.get_current_state()
    logger.info(f"System state restored: {current_state.state.value}")

    logger.info("HTTP server ready — accepting requests")

    # === PHASE 2: Background services — don't block HTTP server ===
    import threading

    def _start_background_services():
        """Initialize eToro client and start monitoring/trading in a background thread."""
        import asyncio
        print("[BG-SERVICES] Background services thread starting...", flush=True)

        try:
            from src.core.monitoring_service import MonitoringService, set_monitoring_service
            from src.api.etoro_client import EToroAPIClient
            from src.models.enums import TradingMode
            from src.core.config import get_config

            config = get_config()
            credentials = config.load_credentials(TradingMode.DEMO)

            if not credentials or not credentials.get("public_key"):
                logger.warning("eToro credentials not configured — background services skipped")
                print("[BG-SERVICES] No credentials — skipping", flush=True)
                return

            etoro_client = EToroAPIClient(
                public_key=credentials["public_key"],
                user_key=credentials["user_key"],
                mode=TradingMode.DEMO
            )
            logger.info("eToro client initialized")
            print("[BG-SERVICES] eToro client initialized", flush=True)

            monitoring_service = MonitoringService(
                etoro_client=etoro_client,
                db=db,
                pending_orders_interval=5,
                order_status_interval=30,
                position_sync_interval=60,
                trailing_stops_interval=30
            )
            set_monitoring_service(monitoring_service)

            # Start monitoring in its own event loop (separate from FastAPI's)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(monitoring_service.start())
            logger.info("Monitoring service started in background thread")
            print("[BG-SERVICES] Monitoring service started", flush=True)

            # Start trading scheduler in the same loop
            from src.core.trading_scheduler import get_trading_scheduler
            scheduler = get_trading_scheduler()
            loop.run_until_complete(scheduler.start())
            logger.info("Trading scheduler started in background thread")
            print("[BG-SERVICES] Trading scheduler started", flush=True)

            # Run the event loop forever (services use asyncio tasks)
            print("[BG-SERVICES] Event loop running forever...", flush=True)
            loop.run_forever()

        except Exception as e:
            print(f"[BG-SERVICES] FAILED: {e}", flush=True)
            import traceback
            traceback.print_exc()
            logger.error(f"Failed to start background services: {e}", exc_info=True)

    bg_thread = threading.Thread(target=_start_background_services, daemon=True, name="bg-services")
    bg_thread.start()

    yield

    # Shutdown
    logger.info("AlphaCent Backend Service shutting down...")

    # Stop monitoring service
    from src.core.monitoring_service import get_monitoring_service
    monitoring_service = get_monitoring_service()
    if monitoring_service:
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            loop.run_until_complete(monitoring_service.stop())
            loop.close()
        except Exception as e:
            logger.warning(f"Error stopping monitoring service: {e}")

    # Stop session cleanup
    if session_manager:
        session_manager.stop_automatic_cleanup()

    logger.info("AlphaCent Backend Service stopped")



def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.
    
    Returns:
        Configured FastAPI application
        
    Validates: Requirements 16.1, 16.6
    """
    app = FastAPI(
        title="AlphaCent Trading Platform API",
        description="REST API for autonomous trading platform",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",  # React frontend (local)
            "http://localhost:5173",  # Vite dev server
            "http://localhost:5174",  # Vite dev server (alternate port)
            "http://34.252.61.149",   # EC2 production
            "https://alphacent.co.uk",  # Production HTTPS
            "https://www.alphacent.co.uk",  # Production HTTPS www
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add authentication middleware
    app.add_middleware(AuthenticationMiddleware)
    
    # Register routers
    from src.api.routers import auth, config, account, strategies, orders, market_data, control, websocket, performance, risk, analytics, signals, alerts
    app.include_router(auth.router)
    app.include_router(config.router)
    app.include_router(alerts.router)
    app.include_router(account.router)
    app.include_router(strategies.router)
    app.include_router(orders.router)
    app.include_router(market_data.router)
    app.include_router(control.router)
    app.include_router(websocket.router)
    app.include_router(performance.router)
    app.include_router(risk.router)
    app.include_router(analytics.router)
    app.include_router(signals.router)
    
    from src.api.routers import data_management
    app.include_router(data_management.router)
    
    logger.info("FastAPI application configured")
    
    return app


# Create application instance
app = create_app()


@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "service": "AlphaCent Trading Platform",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "alphacent-backend"
    }
