"""
FastAPI application setup and configuration.
Replaces Flask + Waitress with modern async FastAPI.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from ...config import get_settings
from ...core.database import get_db
from ...shared.logging_config import get_api_logger
from .routes import router
from .websocket import websocket_router

logger = get_api_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown events.
    Replaces old @app.on_event decorators.
    """
    # Startup
    logger.info("Starting SurgiBot API server...")

    # Initialize database
    db = get_db()
    logger.info("Database initialized")

    # Load settings
    settings = get_settings()
    logger.info(f"API server listening on {settings.api_host}:{settings.api_port}")

    yield

    # Shutdown
    logger.info("Shutting down SurgiBot API server...")


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI application
    """
    settings = get_settings()

    app = FastAPI(
        title="SurgiBot API",
        description="Real-time Surgery Status Management System API",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(router, prefix="/api")
    app.include_router(websocket_router, prefix="/api")

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "Internal server error",
                "message": str(exc),
            },
        )

    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "ok": True,
            "service": "SurgiBot API",
            "version": "2.0.0",
            "docs": "/docs",
        }

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "surgibot.server.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level="info",
    )
