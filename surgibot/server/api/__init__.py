"""API module with FastAPI application and WebSocket support."""

from .app import create_app, app

__all__ = ["create_app", "app"]
