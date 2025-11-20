"""
WebSocket support for real-time updates.
Broadcasts status changes to all connected clients.
"""

import json
import asyncio
from typing import Set, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ...shared.logging_config import get_api_logger

logger = get_api_logger()
websocket_router = APIRouter()

# Store active WebSocket connections
active_connections: Set[WebSocket] = set()


class ConnectionManager:
    """Manages WebSocket connections and broadcasts."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Accept and store new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection."""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """
        Broadcast message to all connected clients.

        Args:
            message: Message dictionary to broadcast
        """
        if not self.active_connections:
            return

        # Serialize message
        message_json = json.dumps(message, ensure_ascii=False)

        # Send to all connections
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.error(f"Error sending to WebSocket: {e}")
                disconnected.add(connection)

        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

    async def send_personal(self, message: Dict[str, Any], websocket: WebSocket):
        """
        Send message to specific client.

        Args:
            message: Message dictionary to send
            websocket: Target WebSocket connection
        """
        try:
            message_json = json.dumps(message, ensure_ascii=False)
            await websocket.send_text(message_json)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            self.disconnect(websocket)


# Global connection manager
manager = ConnectionManager()


@websocket_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates.
    Clients connect here to receive status change notifications.
    """
    await manager.connect(websocket)

    try:
        # Send welcome message
        await manager.send_personal(
            {
                "type": "connected",
                "message": "Connected to SurgiBot WebSocket",
                "timestamp": asyncio.get_event_loop().time(),
            },
            websocket,
        )

        # Keep connection alive and handle incoming messages
        while True:
            # Receive message (for ping/pong or client commands)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                message = json.loads(data)

                # Handle ping
                if message.get("type") == "ping":
                    await manager.send_personal(
                        {"type": "pong", "timestamp": asyncio.get_event_loop().time()},
                        websocket,
                    )

            except asyncio.TimeoutError:
                # Send keepalive ping
                try:
                    await manager.send_personal(
                        {"type": "ping", "timestamp": asyncio.get_event_loop().time()},
                        websocket,
                    )
                except Exception:
                    break

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def broadcast_update(update: Dict[str, Any]):
    """
    Broadcast status update to all connected WebSocket clients.

    Args:
        update: Update dictionary containing action and patient info
    """
    message = {
        "type": "status_update",
        "data": update,
        "timestamp": asyncio.get_event_loop().time(),
    }
    await manager.broadcast(message)
    logger.debug(f"Broadcasted update: {update}")


async def broadcast_announcement(announcement: Dict[str, Any]):
    """
    Broadcast announcement to all connected clients.

    Args:
        announcement: Announcement dictionary
    """
    message = {
        "type": "announcement",
        "data": announcement,
        "timestamp": asyncio.get_event_loop().time(),
    }
    await manager.broadcast(message)
    logger.info(f"Broadcasted announcement: {announcement.get('message', '')}")
