#!/usr/bin/env python
"""
Launcher script for SurgiBot API Server.
Run this to start the FastAPI backend.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    import uvicorn
    from surgibot.config import get_settings

    settings = get_settings()

    print("=" * 60)
    print("🚀 SurgiBot API Server")
    print("=" * 60)
    print()
    print(f"Server URL: http://{settings.api_host}:{settings.api_port}")
    print(f"API Docs:   http://{settings.api_host}:{settings.api_port}/docs")
    print(f"WebSocket:  ws://{settings.api_host}:{settings.api_port}/api/ws")
    print()
    print("Press Ctrl+C to stop")
    print()

    uvicorn.run(
        "surgibot.server.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level="info",
    )
