#!/usr/bin/env python3
"""
Startup script for AlphaCent Backend Service.

Runs the FastAPI application with uvicorn.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable auto-reload during development
        log_level="info"
    )
