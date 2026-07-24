"""Gerenciador de conexões WebSocket, particionado por tenant.

Um cliente só recebe eventos do SEU tenant (isolamento reforçado: o tenant vem
do JWT validado, não de um parâmetro controlável pelo cliente).
"""

from __future__ import annotations

import asyncio

import structlog
from starlette.websockets import WebSocket

_log = structlog.get_logger(__name__)


class WebSocketConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, tenant_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(tenant_id, set()).add(websocket)

    async def disconnect(self, tenant_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(tenant_id)
            if conns:
                conns.discard(websocket)
                if not conns:
                    self._connections.pop(tenant_id, None)

    async def broadcast(self, tenant_id: str, message: str) -> None:
        async with self._lock:
            targets = list(self._connections.get(tenant_id, set()))
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(tenant_id, ws)

    @property
    def connection_count(self) -> int:
        return sum(len(c) for c in self._connections.values())
