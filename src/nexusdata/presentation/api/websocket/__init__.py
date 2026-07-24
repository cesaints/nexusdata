"""Notificações em tempo real via WebSocket."""

from nexusdata.presentation.api.websocket.manager import WebSocketConnectionManager
from nexusdata.presentation.api.websocket.subscriber import JobUpdatesSubscriber

__all__ = ["JobUpdatesSubscriber", "WebSocketConnectionManager"]
