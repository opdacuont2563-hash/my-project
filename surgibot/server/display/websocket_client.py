"""
WebSocket client for Display to receive real-time updates from API server.
"""

import json
import time
import asyncio
import websockets
from typing import Callable, Optional, Dict, Any
from threading import Thread

from ...shared.logging_config import get_display_logger

logger = get_display_logger()


class DisplayWebSocketClient:
    """WebSocket client for receiving real-time updates."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8088,
        on_snapshot: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_update: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_connected: Optional[Callable[[], None]] = None,
        on_disconnected: Optional[Callable[[], None]] = None,
    ):
        """
        Initialize WebSocket client.

        Args:
            host: Server host
            port: Server port
            on_snapshot: Callback for snapshot data
            on_update: Callback for status updates
            on_connected: Callback when connected
            on_disconnected: Callback when disconnected
        """
        self.host = host
        self.port = port
        self.url = f"ws://{host}:{port}/api/ws"

        self.on_snapshot = on_snapshot
        self.on_update = on_update
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected

        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.connected = False

    async def connect(self):
        """Connect to WebSocket server."""
        try:
            self.websocket = await websockets.connect(
                self.url,
                ping_interval=20,
                ping_timeout=10,
            )
            self.connected = True
            logger.info(f"Connected to WebSocket: {self.url}")

            if self.on_connected:
                self.on_connected()

            # Request initial snapshot
            await self.request_snapshot_async()

        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            self.connected = False
            if self.on_disconnected:
                self.on_disconnected()

    async def request_snapshot_async(self):
        """Request snapshot from server."""
        if not self.websocket or not self.connected:
            return

        try:
            # Request list from HTTP API instead
            import requests
            url = f"http://{self.host}:{self.port}/api/list"
            response = requests.get(url, timeout=5)

            if response.ok:
                snapshot = response.json()
                if self.on_snapshot:
                    self.on_snapshot(snapshot)
        except Exception as e:
            logger.error(f"Error requesting snapshot: {e}")

    def request_snapshot(self):
        """Request snapshot (sync wrapper for async)."""
        # This will be called from Tkinter thread, so we need to handle async
        # For now, we'll fetch directly via HTTP
        try:
            import requests
            url = f"http://{self.host}:{self.port}/api/list"
            response = requests.get(url, timeout=5)

            if response.ok:
                snapshot = response.json()
                if self.on_snapshot:
                    self.on_snapshot(snapshot)
        except Exception as e:
            logger.error(f"Error requesting snapshot: {e}")

    async def listen(self):
        """Listen for WebSocket messages."""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")

                    if msg_type == "connected":
                        logger.info("WebSocket handshake complete")

                    elif msg_type == "status_update":
                        # Handle status update
                        update_data = data.get("data", {})
                        if self.on_update:
                            self.on_update(update_data)

                    elif msg_type == "ping":
                        # Respond to ping
                        await self.websocket.send(json.dumps({"type": "pong"}))

                    elif msg_type == "pong":
                        pass  # Ignore pong responses

                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON message: {e}")

        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self.connected = False
            if self.on_disconnected:
                self.on_disconnected()

        except Exception as e:
            logger.error(f"WebSocket listen error: {e}", exc_info=True)
            self.connected = False
            if self.on_disconnected:
                self.on_disconnected()

    async def run_async(self):
        """Run WebSocket client with auto-reconnect."""
        self.running = True

        while self.running:
            try:
                await self.connect()
                await self.listen()
            except Exception as e:
                logger.error(f"WebSocket error: {e}")

            if self.running:
                logger.info("Reconnecting in 5 seconds...")
                await asyncio.sleep(5)

    def run(self):
        """Run WebSocket client (blocking)."""
        try:
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            logger.info("WebSocket client stopped by user")
        except Exception as e:
            logger.error(f"WebSocket client error: {e}", exc_info=True)

    def stop(self):
        """Stop WebSocket client."""
        self.running = False
        if self.websocket:
            try:
                asyncio.run(self.websocket.close())
            except Exception:
                pass
        logger.info("WebSocket client stopped")
